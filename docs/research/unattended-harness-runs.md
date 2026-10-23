# Unattended runs in Claude Code, Codex and T3 Code

Researched on 2026-10-20 against Claude Code 2.1.304, codex-cli 0.163.0
(tag `rust-v0.163.0`) and T3 Code `main` at commit `fe27e8e` (latest release
v0.1.0). The Claude Code and Codex docs move fast and carry many
version notes, so check the version before relying on a detail.

## Short answer

All three can run agents in parallel git worktrees and set the model and
effort per agent. They differ in who answers a permission prompt when nobody
is watching.

- Claude Code has the most ways to answer a prompt without a person.
  A `claude -p` or Agent SDK run starts in Manual mode and denies anything
  that needs approval, unless an allow rule, a hook, a `canUseTool` callback
  or a `--permission-prompt-tool` answers it. On top of that sit auto mode (a
  classifier reviews each action), `dontAsk` (exact allowlist) and
  `bypassPermissions` (containers only). A `PreToolUse` hook can return
  `defer`, which makes a `-p` run exit at the tool call and resume later
  with the answer. That fits a lap that parks on a question and frees its
  slot. Worktrees come from `--worktree`, from background sessions, or from
  `isolation: worktree` on a subagent or workflow agent.
- Codex keeps the boundary in the sandbox. `codex exec` forces the
  approval policy to `never` and rejects any approval request, so a command
  either fits the sandbox (`read-only`, `workspace-write`) or fails back to
  the model. The ways past that are execpolicy rules, `--approve-for-me`
  (a reviewer agent decides) and `danger-full-access`. A program that wants
  to put an approval in front of a person has to be a client of
  `codex app-server`. Worktrees
  come from `codex exec --worktree`. Model and effort are `-m` and
  `-c model_reasoning_effort=...`.
- T3 Code wraps the CLIs. It drives Claude through the Claude Agent
  SDK, Codex through `codex app-server` and Pi through RPC mode. Each thread
  gets its own provider, model, effort, permission mode and optionally a
  worktree. Approvals show up in the web, desktop and mobile apps, with push
  notifications through T3 Connect. Its MCP tool `delegate_task` runs a
  child thread on another provider.

At work, on an API key with no Remote Control, nearly all of Claude Code
that runs locally still works: `-p`, the Agent SDK, background sessions,
subagents, dynamic workflows, hooks, auto mode and channels. What drops out
is Remote Control, cloud sessions, routines and most of the desktop app.
Codex on an API key keeps the CLI, `exec`, the SDKs and the app-server. It
loses cloud features and, as far as the docs show, phone control through the
ChatGPT app. T3 Code
uses whatever login each CLI has, so it works with API keys too, if it is
installed at all.

The approval-from-a-phone path that works at work without T3 is one jidoka
builds itself. Claude Code gives it `PermissionRequest` hooks (command or
HTTP), `canUseTool`, `--permission-prompt-tool` and `defer`. Codex gives it
the app-server's approval requests. Claude Code channels (Telegram, Discord)
with permission relay are a ready-made option that also runs on a Console
API key. They are a research preview, and the docs describe the relay
against the interactive terminal dialog, so whether it answers prompts in a
`-p` run is unconfirmed.

On Windows, Claude Code runs natively, but its Bash sandbox doesn't. Native
Windows runs commands unsandboxed, and the sandbox needs WSL2. Codex has a
native Windows sandbox. T3 Code has a Windows desktop app and CLI but no
Windows background service.

## Claude Code

### Parallel runs in worktrees

| Way to run | How it gets a worktree | Notes |
| :- | :- | :- |
| Interactive `claude` | `claude --worktree <name>` (`-w`) creates `.claude/worktrees/<name>` on branch `worktree-<name>` | Needs workspace trust first. Claude can also enter one with the `EnterWorktree` tool. [worktrees] |
| `claude -p` | `claude -p --worktree <name>` | Skips the trust check. There is no exit prompt, so Claude Code doesn't remove `-p` worktrees, and each keeps its lock until a later session's stale-lock sweep releases it. [worktrees] |
| Background sessions (`claude --bg`, `claude agents`) | The session moves into its own worktree under `.claude/worktrees/` before its first edit | Each session is its own process under a supervisor. `--bg` cannot combine with `-p`. Research preview. [agent-view] |
| Subagents | `isolation: worktree` in frontmatter, or `isolation: "worktree"` on the Agent tool call | Temporary worktree, removed if unchanged. 20 concurrent subagents by default (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`). [sub-agents], [sdk-ts] |
| Dynamic workflows | `agent(prompt, { isolation: 'worktree' })` in the script | Up to 16 concurrent agents by default (`CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`), 1,000 per run. Available in `-p` and the SDK. [workflows], [workflow-skill] |
| Agent SDK | Point `cwd` at a worktree you created; `projectConfigRoot` names the trusted checkout it came from | One session per `cwd`. Neither SDK can change `cwd` mid-session. [sdk-config], [sdk-ts] |
| Agent teams | None | Experimental, off by default. Teammates share the checkout, so the docs say to split files between them. [agents], [agent-teams] |

Worktrees branch from the remote default branch unless `worktree.baseRef`
is `"head"`. A `.worktreeinclude` file copies gitignored files such as
`.env` into each new worktree. While a session is isolated, Claude Code
blocks edits and git commands aimed at the main checkout, and the same
checks cover its subagents. [worktrees]

A background session that changed files in its own worktree is told to
commit and push the branch, and to open a draft pull request when the task
calls for it, unless `CLAUDE.md` or the task says the human handles git.
[agent-view]

### Model and effort per agent

| Scope | Model | Effort |
| :- | :- | :- |
| One run | `--model`, or `ANTHROPIC_MODEL` | `--effort low\|medium\|high\|xhigh\|max`, or `CLAUDE_CODE_EFFORT_LEVEL` |
| Background session | `claude --bg --model ...`, or `claude agents --model ...` as the dispatch default | `claude agents --effort ...` |
| Subagent | `model` in frontmatter, or a per-call `model` parameter | `effort` in frontmatter, or a per-call `effort` parameter |
| Workflow agent | `agent(..., { model })` | `agent(..., { effort })` |
| Agent SDK session | `model` option, `setModel()` | `effort` option, `applyFlagSettings({ effortLevel })` |
| SDK-defined subagent | `AgentDefinition.model` | `AgentDefinition.effort` |

Sources: [cli-ref], [model-config], [sub-agents], [agent-view],
[workflow-skill], [sdk-config], [sdk-ts].

Two rules bite. `CLAUDE_CODE_EFFORT_LEVEL` beats every frontmatter and
per-call effort. `CLAUDE_CODE_SUBAGENT_MODEL` is only a default, unless
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` is also set, which then pins every
subagent, teammate and workflow agent to one model. Opus 5.5, Sonnet 5.5
and Haiku 5.5 default to `medium` effort; most other models default to
`high`. [model-config], [sub-agents]

### Permission prompts

The modes, from the docs' table: `default` (shown as Manual), `acceptEdits`,
`plan`, `auto`, `dontAsk` and `bypassPermissions`. [permission-modes]

- **Which mode a run starts in.** Interactive terminal sessions start in
  `auto` from v2.1.283. `claude -p` and the Agent SDK start in `default`
  from v2.1.302, and there a call that needs approval is denied unless
  something approves it. A `defaultMode` of `auto` or `bypassPermissions`
  takes effect only from user, managed or `--settings` files, never from a
  project's `.claude/settings.json` or `.claude/settings.local.json`.
  [permission-modes], [agent-view]
- **Rules.** `permissions.allow`, `ask` and `deny` in settings, or
  `--allowedTools` and `--disallowedTools`. Deny wins, then ask, then allow,
  whatever the specificity. A deny rule holds even in `bypassPermissions`.
  `Agent(name)` rules control subagents and `Workflow(name)` rules control
  workflow launches. [permissions], [workflows]
- **Auto mode.** A classifier reviews each action. It works on every plan
  and on the Anthropic API with Opus 4.6+, Sonnet 4.6+, Haiku 5.5 or Fable.
  After 3 blocks in a row or 20 in total it falls back to prompting; in `-p`
  with no prompt tool the blocked action just doesn't run and Claude keeps
  going. On a direct API connection the server can do the review at no
  charge; when it can't, the classifier's own requests are billed.
  [permission-modes], [classifier-billing]
- **`dontAsk`.** It denies everything that would prompt and keeps the
  allowlist. The docs suggest it for locked-down CI. [permission-modes]
- **`bypassPermissions`.** Also `--dangerously-skip-permissions`, and meant
  for containers and VMs. It refuses to start as root on macOS and Linux, and a
  background session in this mode needs the disclaimer accepted in
  `~/.claude/settings.json`. [permission-modes]
- **Hooks.** `PreToolUse` runs before every call and can allow, deny, ask
  or `defer`. `PermissionRequest` runs only when Claude Code is about to
  prompt, including in runs that can't show a prompt, and can allow, deny,
  rewrite the input or change the mode. Neither can override a deny or ask
  rule. Hooks can be shell commands, HTTP calls, MCP tool calls, prompts or
  agents, and command hooks time out after 600 seconds by default. [hooks],
  [permissions]
- **`defer`.** Only in `-p`, and only when Claude made a single tool call in
  the turn. The run exits with `stop_reason: "tool_deferred"` and the
  pending call saved; the caller resumes the session later and the hook
  answers then. There is no timeout beyond the 30-day transcript sweep.
  [hooks]
- **Hosts.** In the SDK, `canUseTool` gets whatever the rules and mode leave
  open and can wait indefinitely. In `-p`, `--permission-prompt-tool` names
  an MCP tool that answers. `--permission-prompts none` (SDK
  `permissionPrompts: 'none'`) denies instead of waiting and tells Claude not
  to retry. [headless], [sdk-permissions], [sdk-user-input], [cli-ref]
- **Sandbox.** The Bash sandbox limits files and network for shell
  commands, and its auto-allow mode cuts prompts without a classifier. It
  runs on macOS, Linux and WSL2 only. [sandboxing]
- **Things no mode approves.** Explicit ask rules, `AskUserQuestion`, MCP
  tools marked `requiresUserInteraction`, and `rm` of a critical path such as
  `~`. In a terminal in `auto` or `bypassPermissions` mode, the
  critical-path prompt has a two-minute countdown and then denies; in `-p`
  and the SDK, auto mode denies it at once. [permission-modes]
- **Background work.** Background subagents surface their prompts in the
  parent session. Workflow runs pause only for agent permission prompts and usage limits;
  there is no other mid-run input. [sub-agents], [workflows]

### Approval from a phone

| Route | Auth it needs | Fits unattended work? |
| :- | :- | :- |
| Remote Control (`claude --remote-control`, `claude remote-control --spawn worktree`) with "Push when actions required" | claude.ai subscription. "API keys are not supported." | Interactive sessions only. [remote-control] |
| Channels (Telegram, Discord, iMessage plugins) with permission relay | claude.ai or a Console API key. Not Bedrock, Vertex or Foundry. Team and Enterprise must enable them. | Research preview. Start with `--channels`. Channels can run under `-p`, but the docs describe the relay as a second copy of the terminal dialog, so relay in a `-p` run is unconfirmed. The development flag for unpublished channels is ignored under `-p` and the SDK. Anyone on the sender allowlist can approve. [channels], [channels-ref] |
| Your own relay: a `PermissionRequest` hook, `canUseTool`, `--permission-prompt-tool`, or `defer` then resume | Any | Yes. This is the only route that covers `-p` and the SDK. [hooks], [sdk-user-input] |
| `Notification` hook with matcher `permission_prompt` | Any | Alerts only; it can't answer. Fires after about six seconds of waiting. [hooks] |
| T3 Code mobile app | Whatever the CLI uses | See T3 Code below. |

### On an API key at work

The docs say the CLI and everything that runs locally work on every
provider. Subagents, hooks, sandboxing, workflows and the Agent SDK are on
the every-provider list; auto mode and channels are marked available on the
Anthropic Console. The agent view docs tell a failing background dispatch
to "confirm you have run `/login` or configured an API key", so background
sessions run on a key too. The subscription-only list includes cloud
sessions, the desktop app (apart from Desktop on 3P), cloud scheduled tasks,
ultrareview, Remote Control, the Chrome extension and computer use.
Cross-session messaging is limited to one machine on a Console key.
[feature-availability], [agent-view]

`--bare` never reads the subscription login and needs `ANTHROPIC_API_KEY`
or an `apiKeyHelper`; the docs recommend it for scripted calls and say it
will become the default for `-p`. [headless]

On policy, the docs say developers building on the Agent SDK should use API
keys and that third parties may not offer claude.ai login in their products.
They don't say how that applies to a tool one person writes for their own
use on their own subscription. Unconfirmed. [legal], [sdk-overview]

### Windows

- Native Windows 10 1809+ is supported. With Git for Windows, Claude Code
  uses Git Bash for the Bash tool; without it, the PowerShell tool. [setup]
- The Bash sandbox does not run on native Windows; use WSL2. [sandboxing]
- Auto mode as the built-in default needs v2.1.233 or later on native
  Windows. [permission-modes]
- Worktrees work. For PowerShell commands only the working-directory
  isolation check applies. [worktrees]
- Background sessions run on Windows; the docs' version history has
  Windows-specific fixes. [agent-view]
- Hooks can run in PowerShell with `"shell": "powershell"`. [hooks]
- The Agent SDK ships a `win32-x64` binary. [sdk-ts]
- Channel plugins need Bun. Whether they run on native Windows isn't stated.
  Unconfirmed.

## Codex

### Parallel runs in worktrees

| Way to run | How it gets a worktree | Notes |
| :- | :- | :- |
| Interactive `codex` | `/worktree` | Creates a managed git worktree. The desktop docs put managed worktrees in `$CODEX_HOME/worktrees` on a detached HEAD; the CLI page doesn't say. [codex-commands], [codex-worktrees] |
| `codex exec` | `codex exec --worktree "<task>"`, or `codex exec fork <id> --worktree` | Can't combine with `resume`, `review`, `--ephemeral` or `--ignore-user-config`. Run several processes for parallel laps. [codex-commands] |
| Subagents | None documented | On by default. They inherit the parent's sandbox, approval policy, provider and MCP servers; a custom agent file can't change those. Cap with `agents.max_concurrent_threads_per_session`. [codex-subagents] |
| TypeScript SDK | `workingDirectory` per thread | Spawns `codex exec --experimental-json`, so `exec`'s approval rules apply. [codex-ts-sdk], [codex-ts-exec] |
| Python SDK, app-server | `cwd` per thread or per turn | JSON-RPC to `codex app-server`. [codex-sdk], [codex-app-server] |
| ChatGPT desktop app | Worktree mode per chat, Handoff to Local | Desktop app, not the CLI. [codex-worktrees] |

A `.worktreeinclude` file copies ignored files into managed worktrees.
Codex requires a git repository unless `--skip-git-repo-check` is passed.
[codex-worktrees], [codex-exec]

### Model and effort per agent

| Scope | Model | Effort |
| :- | :- | :- |
| One run | `-m <model>` | `-c model_reasoning_effort=<level>` |
| Profile | `-p <profile>` layers `$CODEX_HOME/<name>.config.toml` | same file |
| Subagent | `model` in the agent's TOML, `agents.default_subagent_model`, or the spawn request | `model_reasoning_effort` in the TOML, `agents.default_subagent_reasoning_effort` |
| TypeScript SDK | `model` thread option | `modelReasoningEffort` thread option |
| Python SDK | `model` | `effort` on `run()` or `turn()` |
| App-server | `model` on `thread/start` or `turn/start` | `effort` on `turn/start` |

Levels depend on the model; the config reference lists `low`, `medium`,
`high`, `xhigh`, `max` and `ultra`. On an API key, the models are whatever
the key can reach. Sources: [codex-exec-help], [codex-config-ref],
[codex-subagents], [codex-ts-sdk], [codex-py-api], [codex-app-server],
[codex-pricing].

### Permission prompts

Codex has two controls. The sandbox decides what a command can reach, and
the approval policy decides when Codex stops to ask. [codex-security]

- **Sandbox.** The modes are `read-only`, `workspace-write` and
  `danger-full-access`. `workspace-write` keeps `.git`, `.agents`, `.codex`
  and `.aws` read-only and has no network unless
  `sandbox_workspace_write.network_access = true`. Permission profiles
  (`default_permissions`) give finer control over paths and network.
  [codex-security], [codex-permissions]
- **Approval policy.** The values are `on-request`, `never` and
  `granular`. `untrusted` is retired and can stop Codex from starting.
  [codex-security]
- **`codex exec`.** It sets the policy to `never` unless the reviewer is
  `auto_review`. When a request arrives anyway it is rejected with
  "command execution approval is not supported in exec mode", and MCP
  elicitations are cancelled. A command that needs more than the sandbox
  fails back to the model. [codex-exec-src]
- **Auto-review.** `approvals_reviewer = "auto_review"` with `on-request`,
  or `--approve-for-me`, sends each approval request to a reviewer agent
  instead of a person. It checks for exfiltration, credential probing,
  security weakening and destructive actions, and it fails closed. It stops
  the turn after 3 denials in a row or 10 in the last 50 reviews. It only
  sees actions that already need approval. [codex-auto-review]
- **Rules.** `prefix_rule()` entries in `rules/*.rules` decide `allow`,
  `prompt` or `forbidden` for commands that would run outside the sandbox.
  The strictest match wins, and Codex splits simple `bash -lc` chains before
  matching. Project rules load only in trusted projects; `--ignore-rules`
  skips them. [codex-rules], [codex-exec]
- **Hooks.** `PreToolUse` can deny or rewrite a call; `ask` is parsed but
  not supported yet. `PermissionRequest` runs when Codex is about to ask and
  can allow or deny. Non-managed hooks must be reviewed and trusted first;
  `--dangerously-bypass-hook-trust` skips that for one run. [codex-hooks]
- **Hosts.** A client of `codex app-server` receives
  `item/commandExecution/requestApproval` and
  `item/fileChange/requestApproval` and answers `accept`,
  `acceptForSession`, `decline` or `cancel`. That is the only documented way
  for a program to put a Codex approval in front of a person. The Python
  SDK only offers `deny_all` and `auto_review`, and the TypeScript SDK wraps
  `exec`. [codex-app-server], [codex-py-approval], [codex-ts-sdk]
- **Safety pauses.** If safety monitoring pauses a task, the CLI can't
  resume it; the task ends. [codex-security]

For unattended local work the docs recommend `--sandbox workspace-write`
and keeping `--dangerously-bypass-approvals-and-sandbox` for a dedicated
sandbox VM. [codex-commands]

### Approval from a phone

The ChatGPT mobile app can start tasks, follow them and approve commands on
a connected Mac or Windows PC. The host must run the ChatGPT desktop app,
signed in to the same ChatGPT account and workspace, and setup can't start
from the CLI. [codex-mobile], [codex-remote]

The API key plan lists "no cloud-based features" [codex-pricing], so phone
control on an API key looks unavailable. The docs don't say so in as many
words. Unconfirmed. `codex remote-control` starts the app-server daemon
"when eligible"; who is eligible isn't documented. Unconfirmed.
[codex-commands]

Without the ChatGPT app, the phone route is a jidoka-owned app-server client
or a `PermissionRequest` hook in an interactive session.

### On an API key at work

`codex login --with-api-key`, or `CODEX_API_KEY` for a single `exec` run.
The API key plan covers the CLI, the SDK and the IDE extension, bills at API
prices and excludes cloud features. Codex cloud needs a ChatGPT sign-in.
[codex-exec], [codex-auth], [codex-pricing]

### Windows

The CLI installs natively on Windows. Its sandbox has three
implementations: `mxc` (recommended, no admin setup), `elevated` (needs
admin-approved setup) and `unelevated` (weaker network isolation). Under
WSL2, Codex uses the Linux sandbox; WSL1 stopped working in 0.115. The
ChatGPT desktop app on Windows supports parallel chats and worktrees.
[codex-cli], [codex-win-sandbox], [codex-wsl], [codex-security]

## T3 Code

### How it runs agents

T3 Code is a server plus web, desktop and mobile clients. It runs the
provider CLIs installed on the machine. Claude goes through the Claude
Agent SDK, Codex through `codex app-server`, and Pi through
`pi --mode rpc`. Each needs to be installed and logged in on that machine.
[t3-readme], [t3-install], [t3-mcp]

### Parallel runs in worktrees

Threads can start in a new worktree, which T3 places in the `worktrees`
folder of its home directory. Cleanup rules are per project.
[t3-project-settings]

The MCP server `t3-code`, which T3 injects into each provider session,
gives the agent orchestration tools. [t3-mcp]

- `delegate_task` creates a child thread, optionally on another provider
  instance and model, with a runtime mode no broader than the parent's.
  The docs don't say whether the child gets its own worktree. Unconfirmed.
- `create_threads` makes up to 20 top-level threads that share the parent's
  worktree.
- `t3_thread_launch` takes `workspaceStrategy: worktree` with a `baseRef`,
  which gives one new thread its own worktree.

### Model and effort per agent

A thread's model selection is a provider instance, a model and a set of
options; `t3_thread_configure` changes it. For Claude models the bundled
manifest defines an `effort` option; on the Fable 5 profile it runs from
`low` to `max`, plus `ultracode` and `ultrathink`. For Codex the model list
and efforts come from Codex's app-server; for Pi, from Pi's own thinking
levels. `delegate_task` takes a provider and a model but no effort, and the
docs don't say which effort a child runs at. Unconfirmed.
[t3-thread-tools], [t3-model-selection], [t3-manifest],
[t3-model-manifest-doc], [t3-pi], [t3-mcp]

### Permission prompts

T3 Code has four modes per thread: Supervised, Auto-accept edits, Auto and
Full access. Full access is the default for new threads. [t3-permission-modes]

| T3 mode | Claude permission mode | Codex approval, reviewer, sandbox |
| :- | :- | :- |
| Supervised | `default` | `untrusted`, user, `readOnly` |
| Auto-accept edits | `acceptEdits` | `on-request`, user, `workspaceWrite` |
| Auto | `auto` | `on-request`, `auto_review`, `workspaceWrite` |
| Full access | `bypassPermissions` | `never`, user, `dangerFullAccess` |

The table comes from the adapters' source and covers the plain case, with
no plan mode and no sandbox or approval override. [t3-claude-adapter],
[t3-codex-adapter]
Supervised on Codex sends `untrusted`, which the Codex docs call retired.
What that does on codex-cli 0.163.0 is unconfirmed. Pi has no Auto mode;
T3 enforces the mode through Pi's tool hook, which is not an OS sandbox.
Claude can still ask in Full access when its own settings disable bypass
mode. [t3-permission-modes], [t3-pi]

Child threads don't route approvals to the parent agent. They wait for a
person. [t3-mcp]

### Approval from a phone

The mobile app (iOS, Android) shows pending approvals with "Allow once",
"Allow session" and "Decline". It reaches the server through T3 Connect, a
hosted relay with sign-in, or through a pairing link over a LAN or tailnet.
Push notifications for "needs approval" need T3 Connect; a direct or
Tailscale connection alone doesn't send them. [t3-approval-card],
[t3-remote], [t3-notifications]

### On an API key at work

T3 uses each CLI's own login and configuration. Provider instances can carry
their own environment variables, "such as API keys or a custom base URL".
So a Claude instance with `ANTHROPIC_API_KEY` and a Codex CLI logged in with
an API key should both work. The Codex page talks about ChatGPT plans and
"an existing Codex CLI login"; a Codex API key through T3 isn't spelled out.
Unconfirmed. [t3-install], [t3-claude], [t3-codex]

### Windows

There is a desktop app (`winget install T3Tools.T3Code`, or scoop) and a
PowerShell installer for the `t3` CLI. The desktop app can run agents
inside a WSL distro. The background service is macOS and Linux only;
"Windows background services are not supported." [t3-readme], [t3-install],
[t3-background]

## What is left at work

The case here is an API key, no Remote Control, maybe no T3 Code, and
Windows.

| Need | Claude Code | Codex |
| :- | :- | :- |
| Unattended run | `claude -p`, Agent SDK, `claude --bg` | `codex exec`, SDKs, app-server |
| Parallel worktrees | `-p --worktree`, background sessions, subagent and workflow `isolation: worktree` | `codex exec --worktree`, several processes |
| Model and effort per agent | yes, every scope | yes, run, profile, subagent, SDK |
| Prompt answered without a person | allowlist, `dontAsk`, auto mode, hooks | sandbox, rules, `--approve-for-me` |
| Prompt answered by a person later | `defer` then resume, `canUseTool`, `--permission-prompt-tool`, `PermissionRequest` hook | app-server client |
| Phone approval | channels (preview; relay in `-p` unconfirmed), or a jidoka relay | jidoka relay over the app-server |
| OS sandbox on native Windows | no (WSL2 only) | yes |

## Unconfirmed

- Whether a personal tool may drive the Agent SDK or `claude -p` on a
  claude.ai subscription. The docs address third-party products, not this
  case.
- Whether Codex phone control or `codex remote-control` works on an API
  key.
- Whether a Codex `PermissionRequest` hook fires under `codex exec`, with or
  without `--approve-for-me`. With the `never` policy no approval is asked,
  so probably not.
- Whether a Codex execpolicy `allow` rule lets a command run outside the
  sandbox under `exec`'s forced `never` policy.
- What T3's `untrusted` approval policy for Codex Supervised does on
  codex-cli 0.163.0.
- Whether a T3 `delegate_task` child gets its own worktree, and which
  effort it runs at.
- Whether Claude Code's channel permission relay answers prompts in a `-p`
  run.
- Whether the TypeScript Codex SDK's `approvalPolicy` option survives
  `exec` forcing `never`.
- Whether a Codex API key works as a T3 provider login.
- Whether Claude Code channel plugins run on native Windows.

## Sources

Local CLI help, read on 2026-10-20: `claude --help`, `claude agents --help`
(2.1.304); `codex --help`, `codex exec --help`, `codex features list`
(0.163.0).

Claude Code docs (Markdown at the same URL plus `.md`):

- [agents]: https://code.claude.com/docs/en/agents
- [worktrees]: https://code.claude.com/docs/en/worktrees
- [agent-view]: https://code.claude.com/docs/en/agent-view
- [agent-teams]: https://code.claude.com/docs/en/agent-teams
- [sub-agents]: https://code.claude.com/docs/en/sub-agents
- [workflows]: https://code.claude.com/docs/en/workflows
- [headless]: https://code.claude.com/docs/en/headless
- [cli-ref]: https://code.claude.com/docs/en/cli-reference
- [model-config]: https://code.claude.com/docs/en/model-config
- [permission-modes]: https://code.claude.com/docs/en/permission-modes
- [permissions]: https://code.claude.com/docs/en/permissions
- [hooks]: https://code.claude.com/docs/en/hooks
- [sandboxing]: https://code.claude.com/docs/en/sandboxing
- [classifier-billing]: https://code.claude.com/docs/en/auto-mode-classifier-billing
- [remote-control]: https://code.claude.com/docs/en/remote-control
- [channels]: https://code.claude.com/docs/en/channels
- [channels-ref]: https://code.claude.com/docs/en/channels-reference
- [feature-availability]: https://code.claude.com/docs/en/feature-availability
- [setup]: https://code.claude.com/docs/en/setup
- [legal]: https://code.claude.com/docs/en/legal-and-compliance
- [sdk-overview]: https://code.claude.com/docs/en/agent-sdk/overview
- [sdk-config]: https://code.claude.com/docs/en/agent-sdk/configuration
- [sdk-permissions]: https://code.claude.com/docs/en/agent-sdk/permissions
- [sdk-user-input]: https://code.claude.com/docs/en/agent-sdk/user-input
- [sdk-ts]: https://code.claude.com/docs/en/agent-sdk/typescript
- [workflow-skill]: the `workflow-authoring` skill built into Claude Code
  2.1.304, which documents the `agent()` options `model`, `effort` and
  `isolation`

Codex docs (developers.openai.com/codex now points to learn.chatgpt.com):

- [codex-exec]: https://learn.chatgpt.com/docs/non-interactive-mode
- [codex-commands]: https://learn.chatgpt.com/docs/developer-commands
- [codex-cli]: https://learn.chatgpt.com/docs/codex/cli
- [codex-security]: https://learn.chatgpt.com/docs/agent-approvals-security
- [codex-permissions]: https://learn.chatgpt.com/docs/permissions
- [codex-auto-review]: https://learn.chatgpt.com/docs/sandboxing/auto-review
- [codex-rules]: https://learn.chatgpt.com/docs/agent-configuration/rules
- [codex-hooks]: https://learn.chatgpt.com/docs/hooks
- [codex-subagents]: https://learn.chatgpt.com/docs/agent-configuration/subagents
- [codex-worktrees]: https://learn.chatgpt.com/docs/environments/git-worktrees
- [codex-config-ref]: https://learn.chatgpt.com/docs/config-file/config-reference
- [codex-sdk]: https://learn.chatgpt.com/docs/codex-sdk
- [codex-app-server]: https://learn.chatgpt.com/docs/app-server
- [codex-auth]: https://learn.chatgpt.com/docs/auth
- [codex-pricing]: https://learn.chatgpt.com/docs/pricing
- [codex-mobile]: https://learn.chatgpt.com/docs/mobile
- [codex-remote]: https://learn.chatgpt.com/docs/remote-connections
- [codex-win-sandbox]: https://learn.chatgpt.com/docs/windows/windows-sandbox
- [codex-wsl]: https://learn.chatgpt.com/docs/windows/wsl

Codex source at `rust-v0.163.0`:

- [codex-exec-src]: https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/exec/src/lib.rs
  (forced `never` at lines 589 to 591, reviewer rebuild from line 779,
  rejected approvals from line 2097, cancelled elicitations at line 2081)
- [codex-exec-help]: `codex exec --help`, 0.163.0
- [codex-ts-sdk]: https://github.com/openai/codex/blob/rust-v0.163.0/sdk/typescript/README.md
  and https://github.com/openai/codex/blob/rust-v0.163.0/sdk/typescript/src/threadOptions.ts
- [codex-ts-exec]: https://github.com/openai/codex/blob/rust-v0.163.0/sdk/typescript/src/exec.ts
  (`["exec", "--experimental-json"]` at line 95)
- [codex-py-api]: https://github.com/openai/codex/blob/rust-v0.163.0/sdk/python/docs/api-reference.md
- [codex-py-approval]: https://github.com/openai/codex/blob/rust-v0.163.0/sdk/python/src/openai_codex/_approval_mode.py

T3 Code, repository https://github.com/pingdotgg/t3code at commit
`fe27e8e3dc12dcbb108e9a28fd9b8cb65f34ae92`:

- [t3-readme]: README.md
- [t3-install]: docs/user/install.md
- [t3-permission-modes]: docs/user/permission-modes.md
- [t3-claude]: docs/user/providers-claude.md
- [t3-codex]: docs/user/providers-codex.md
- [t3-pi]: docs/user/providers-pi.md
- [t3-remote]: docs/user/remote-access.md
- [t3-notifications]: docs/user/mobile-notifications.md
- [t3-background]: docs/user/background-service.md
- [t3-project-settings]: docs/user/project-settings.md
- [t3-mcp]: docs/orchestration-v2/orchestrator-mcp-server.md
- [t3-model-manifest-doc]: docs/internals/model-manifest.md
- [t3-thread-tools]: apps/server/src/mcp/toolkits/thread/tools.ts
- [t3-model-selection]: packages/contracts/src/modelSelection.ts
- [t3-manifest]: apps/server/src/provider/model-manifest.json
- [t3-claude-adapter]: apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts
  (`permissionModeForClaudeRuntimePolicy`, line 1994)
- [t3-codex-adapter]: apps/server/src/orchestration-v2/Adapters/CodexAdapterV2.ts
  (`codexRuntimeModeTurnDefaults`, line 679)
- [t3-approval-card]: apps/mobile/src/features/threads/PendingApprovalCard.tsx
