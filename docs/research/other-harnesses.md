# What Pi, nanocoder and OpenCode can run

Read on 2026-10-20 against each project's repository, docs site and changelog,
plus T3 Code's repository. The commits read are listed at the end.

## Short answer

OpenCode is the closest fit for jidoka outside Claude Code and Codex. It reads
`SKILL.md` skills straight out of `.claude/skills`, including tracer's nested
layout, defines subagents as Markdown files with their own model and
permission rules, has a scriptable `opencode run` plus an HTTP server and SDK,
ships native Windows binaries, and T3 Code drives it as a built-in provider.
The gaps are hooks, which are TypeScript plugins rather than shell commands,
and `CLAUDE.md`, which OpenCode 2 no longer reads at all.

Pi loads `SKILL.md` skills and `AGENTS.md` or `CLAUDE.md`, and gained native
MCP support three weeks ago. It ships no subagents and no approval prompts on
purpose. Both come from TypeScript extensions, so jidoka would carry a Pi
extension to get either. Its print, JSON and RPC modes are the best documented
of the three.

nanocoder is the weakest fit. Its "skills" are its own `skill.yaml` bundles,
not Agent Skills, it reads only a root `AGENTS.md`, and T3 Code has no
provider for it. It does have the most Claude-like shell hooks and lets each
subagent pick its own local model.

One finding changes the home picture. The "Pi" provider in T3 Code at home
does not run Pi. Its binary path is `omp`, which is oh-my-pi, a fork of Pi.
T3 Code's maintainers call that swap unsupported and closed a bug about it as
not planned. oh-my-pi itself reads more of the Claude Code layout than any of
the three, so it gets its own section below.

## Which projects these names mean

- **Pi** is the coding agent at [earendil-works/pi](https://github.com/earendil-works/pi),
  formerly `badlogic/pi-mono` by Mario Zechner, published on npm as
  `@earendil-works/pi-coding-agent`, version 1.3.0 of 2026-10-15. T3 Code's Pi
  provider updates that npm package
  ([driver.ts](https://github.com/pingdotgg/t3code/blob/main/packages/provider-pi/src/server/driver.ts)).
  Inflection's Pi chatbot is not a coding agent and is not meant here.
- **oh-my-pi** is [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi), "Fork
  of Pi by @mariozechner" per its README, binary `omp`, npm
  `@oh-my-pi/pi-coding-agent` 18.12.4. The home machine has `omp` 18.12.2 at
  `~/.local/bin/omp`, and `~/.t3/userdata/settings.json` sets the T3 Pi
  instance's `binaryPath` to `omp`. Its `~/.omp/agent/models.yml` defines the
  local Qwen 3.8 model as an OpenAI-compatible endpoint on another LAN host.
- **nanocoder** is [Nano-Collective/nanocoder](https://github.com/Nano-Collective/nanocoder),
  npm `@nanocollective/nanocoder` 1.31.0 of 2026-09-26. A different tool called
  Nanocode exists; the spelling in the question and the npm name both point
  here.
- **OpenCode** is [anomalyco/opencode](https://github.com/anomalyco/opencode),
  formerly `sst/opencode`, site [opencode.ai](https://opencode.ai). It is the one
  T3 Code installs with `opencode auth login`
  ([T3 README](https://github.com/pingdotgg/t3code/blob/main/README.md)). Two
  lines are live: V1 is npm `opencode-ai` 1.19.3, and V2 is npm `@opencode/cli`
  2.1.1, released 2026-10-20. The older Go project
  [opencode-ai/opencode](https://github.com/opencode-ai/opencode) is archived
  and continues as Charm's [Crush](https://github.com/charmbracelet/crush); it
  is not meant here.

## Comparison

| | Pi 1.3 | oh-my-pi 18.12 (home) | nanocoder 1.31 | OpenCode V1 1.19 / V2 2.1 |
|---|---|---|---|---|
| `SKILL.md` skills | Yes, Agent Skills spec | Yes | No, own `skill.yaml` bundles | Yes |
| Reads `.claude/skills` | No, add the path in settings | Yes, one level deep only | No | Yes, nested dirs included |
| `AGENTS.md` | Yes, cwd and ancestors | Yes | Project root only | Yes |
| `CLAUDE.md` | Yes, if no `AGENTS.md` in that dir | Yes | No, only imported by `nanocoder init` | V1 as fallback; V2 no |
| Subagents | None built in; example extension | Built-in `task` tool | Built-in `agent` tool | Built-in, Markdown agents |
| Reads `.claude/agents` | No | No, skipped on purpose | No | V2 no; V1 unconfirmed |
| MCP servers | Yes, since 0.99.0 | Yes, reads Claude's MCP files | Yes, project `.mcp.json` | Yes |
| Hooks | TypeScript extension events | TypeScript extensions | Shell commands in config | TypeScript plugins |
| Headless | `-p`, `--mode json`, `--mode rpc`, SDK | `-p`, `--mode json/rpc`, `omp acp` | `run`, `--json`, `--acp` | `run --format json`, `serve`, SDK, `acp` |
| Permission model | None; project trust only | Approval modes, default yolo | Five modes plus allowlist | allow/ask/deny rules per agent |
| Model per agent | Via extension frontmatter | Yes, plus model roles | Yes, provider and model | Yes |
| Local models | Yes | Yes | Yes | Yes |
| Windows | Native or WSL | Native | Native, no OS sandbox | Native; V1 docs advise WSL |
| In T3 Code | Built-in Pi provider | Unsupported under Pi provider | Local ACP command only, untested | Built-in OpenCode provider |

## Pi

Pi calls itself "a minimal, extensible agent harness" and says it "skips
features like sub-agents and plan mode"
([README](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md)).
That design choice drives most of the answers below.

**Skills.** Pi implements the Agent Skills specification. It lists each
skill's name, description and path in the system prompt and the model reads
`SKILL.md` when a task matches; `/skill:name` forces one
([skills](https://pi.dev/docs/latest/skills)). It scans `~/.pi/agent/skills/`,
`.pi/skills/`, `~/.agents/skills/` and `.agents/skills/`, the last one walking
up to the repository root, and discovers `SKILL.md` directories recursively.
It does not scan `.claude/skills`; I found no `.claude` path in Pi's source. A
`skills` array in `settings.json` adds more paths
([settings](https://pi.dev/docs/latest/settings)). Project skills load only
after the user grants project trust.

**Context files.** In each directory Pi takes the first of
`AGENTS.override.md`, `AGENTS.md`, `AGENTS.MD`, `CLAUDE.md`, `CLAUDE.MD`, from
the agent directory, the working directory and its parents
([configuration](https://pi.dev/docs/latest/configuration),
[resource-loader.ts](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/resource-loader.ts)).
A directory with both files contributes only its `AGENTS.md`. Context files
load without project trust. Pi's docs say nothing about `@` imports inside them;
unconfirmed.

**Subagents.** None built in. The repo ships an example `subagent` extension
that runs each child as a separate `pi` process, with agent definitions in
`~/.pi/agent/agents/*.md` carrying `tools` and `model` frontmatter, and single,
parallel and chain modes
([example README](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/examples/extensions/subagent/README.md)).

**MCP.** Added in 0.99.0 on 2026-09-29
([CHANGELOG](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/CHANGELOG.md)).
Servers come from `~/.pi/agent/mcp.json` and, after project trust,
`.pi/mcp.json`, over stdio or streamable HTTP with OAuth; SSE is rejected. The
`mcpServers` shape matches Claude Code's, and the docs say to copy entries
across ([mcp](https://pi.dev/docs/latest/mcp)). Pi does not read Claude's
`.mcp.json` itself.

**Hooks.** Hooks are TypeScript extensions that subscribe to events such as
`tool_call`, which can block a call, `tool_result`, `before_agent_start` and
`session_start` ([extensions](https://pi.dev/docs/latest/extensions)). There is
no shell-command hook in configuration, so a Claude Code `SessionStart` hook
like `bd prime` would need a small extension.

**Headless.** `--print` returns the final text and exits nonzero on error,
`--mode json` streams JSONL events, `--mode rpc` keeps a bidirectional JSONL
session open, and a TypeScript SDK embeds the agent in-process
([cli-integration](https://pi.dev/docs/latest/cli-integration),
[rpc](https://pi.dev/docs/latest/rpc), [sdk](https://pi.dev/docs/latest/sdk)).
Upstream Pi has no ACP mode; the ACP Registry lists a third-party adapter,
[pi-acp](https://github.com/agentclientprotocol/registry/blob/main/pi-acp/agent.json).

**Permissions.** Pi "does not ask for approval before every tool call," and its
security page names a container or VM as "usually the strongest practical
option" ([security](https://pi.dev/docs/latest/security)). Project trust only decides
whether `.pi/` settings, extensions, skills and MCP servers load. Print, JSON
and RPC modes cannot show the trust prompt, so automated runs pass `--approve`
or `--no-approve`. `--tools` and `--exclude-tools` narrow the tool set
([cli](https://pi.dev/docs/latest/cli)). Approval prompts exist only as an
extension; the repo has a `permission-gate.ts` example.

**Models.** `--model provider/id:thinking` picks the session model. Ollama, LM
Studio, vLLM and SGLang go in `models.json`, and a built-in extension drives a
llama.cpp router ([models](https://pi.dev/docs/latest/models),
[llama-cpp](https://pi.dev/docs/latest/llama-cpp)). A model per agent exists
only through the subagent extension's `model:` field.

**Windows.** Native, with Git Bash for the `bash` tool or an optional
`powershell` tool, or inside WSL. The installer is
`irm https://pi.dev/install.ps1 | iex` ([windows](https://pi.dev/docs/latest/windows)).

**In T3 Code.** A built-in "Pi" driver, off by default, that runs the user's
own `pi --mode rpc` and needs Pi 0.80.5 or newer
([providers-pi.md](https://github.com/pingdotgg/t3code/blob/main/docs/user/providers-pi.md),
[settings.ts](https://github.com/pingdotgg/t3code/blob/main/packages/provider-pi/src/settings.ts)).
T3 lists Pi's models and thinking levels, shows Pi skills in the `$` menu, and
renders extension dialogs. It enforces its permission modes by injecting an
extension whose `tool_call` handler asks before commands and edits, so
Supervised, Auto-accept edits and Full access work and Auto is hidden. The same
extension bridges T3's own MCP tools, such as `delegate_task`, into Pi
([mcpExtensionSource.ts](https://github.com/pingdotgg/t3code/blob/main/packages/provider-pi/src/server/mcpExtensionSource.ts)).
If Pi's example subagent extension is installed, T3 shows its children in the
subagent UI, but they cannot be opened as threads.

## oh-my-pi, the Pi that runs at home

oh-my-pi keeps Pi's core and adds the parts Pi leaves out. Where Pi says no,
oh-my-pi usually says yes, and it also reads other tools' files.

- **Skills.** Reads `.claude/skills/*/SKILL.md`, `.agents`, `.codex`,
  `.opencode`, `.github/skills` and its own `.omp` skills, but only one level
  under each `skills/` root
  ([skills.md](https://github.com/can1357/oh-my-pi/blob/main/docs/skills.md)).
  Tracer's skills sit at `.claude/skills/tracer/skills/<name>/SKILL.md`, so the
  `claude` provider would miss them; `skills.customDirectories` can point at the
  nested folder.
- **Context files.** Standalone `AGENTS.md` and `CLAUDE.md` walking up to the
  repo root, `.claude/CLAUDE.md`, and a `contextFiles.extra` list that can add
  `AGENTS.local.md`, with `@` imports resolved
  ([context-files.md](https://github.com/can1357/oh-my-pi/blob/main/docs/context-files.md)).
- **Subagents.** A built-in `task` tool with bundled agents and Markdown agents
  in `.omp/agents/`. It skips `.claude/agents` on purpose because "their
  frontmatter schema is not the OMP task-agent contract"
  ([task/discovery.ts](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/task/discovery.ts)).
- **MCP.** Reads servers from Claude Code's `~/.claude.json` and
  `.claude/mcp.json`, a root `.mcp.json`, and Cursor, VS Code and OpenCode
  configs
  ([mcp-config.md](https://github.com/can1357/oh-my-pi/blob/main/docs/mcp-config.md)).
- **Hooks.** TypeScript only, including modules under `.claude/hooks/pre/` and
  `post/` ([hooks.md](https://github.com/can1357/oh-my-pi/blob/main/docs/hooks.md)).
  It reads `.claude/settings.json` as data; whether it runs that file's shell
  `hooks` entries is unconfirmed.
- **Permissions.** `tools.approvalMode` is `always-ask`, `always-ask-cached`,
  `write` or `yolo`, and yolo is the default
  ([approval-mode.md](https://github.com/can1357/oh-my-pi/blob/main/docs/approval-mode.md)).
- **Headless and models.** `omp --help` on the installed binary lists `-p`,
  `--mode json|rpc|rpc-ui`, an `omp acp` subcommand, `--max-time`, and model
  roles such as `--smol`, `--slow` and `--plan`. Local endpoints go in
  `models.yml`, with discovery for Ollama, llama.cpp and LM Studio
  ([models.md](https://github.com/can1357/oh-my-pi/blob/main/docs/models.md)).
- **Windows.** One native binary, installed with
  `irm https://omp.sh/install.ps1 | iex`
  ([README](https://github.com/can1357/oh-my-pi/blob/main/README.md)).

T3 Code does not support it. Issue
[#19490](https://github.com/pingdotgg/t3code/issues/19490) reports that with
`binaryPath: omp` turns never settle, because oh-my-pi ends a turn with
`session_settled` where Pi sends `agent_settled`. The reply, posted by a bot
on a maintainer's behalf, calls this "an unsupported swap" and closes it as
not planned. An earlier request to add oh-my-pi over ACP,
[#8985](https://github.com/pingdotgg/t3code/issues/8985), was closed the same
way. A third-party commenter on #19490 lists more mismatches and offers a shim
that sits in the binary path. It is on npm as
[omp-t3](https://www.npmjs.com/package/omp-t3), but the GitHub repository it
names returned 404 when I checked, so I could not read its source.

I also found in source that T3 asks Pi for `get_commands`. oh-my-pi's RPC has no such command, only
`get_available_commands`, so T3's `$` menu would show no oh-my-pi skills
([status.ts](https://github.com/pingdotgg/t3code/blob/main/packages/provider-pi/src/server/status.ts),
[rpc-types.ts](https://github.com/can1357/oh-my-pi/blob/main/packages/coding-agent/src/modes/rpc/rpc-types.ts)).
A cleaner route may be T3's "Local ACP command" with `omp acp`. I found no
report that it works.

## nanocoder

nanocoder is a local-first terminal agent from a community collective
([README](https://github.com/Nano-Collective/nanocoder/blob/main/README.md)).
It has many of Claude Code's features under its own names and file layouts.

**Skills.** Not Agent Skills. A nanocoder skill is either one Markdown file in
`.nanocoder/commands|agents|tools/` or a bundle in `.nanocoder/skills/<name>/`
with a `skill.yaml` manifest and `commands/`, `agents/` and `tools/` folders.
Bundles can subscribe to file changes, cron schedules or CI failures, which a
per-project daemon fires unattended
([skills](https://docs.nanocollective.org/nanocoder/docs/latest/features/skills)).
A search of the source for `SKILL.md`, `.claude/skills` and `.agents/skills`
found nothing.

**Context files.** `AGENTS.md` at the project root only, appended to the
system prompt; the `nano` tune profile leaves it out by default
([prompt-builder.ts](https://github.com/Nano-Collective/nanocoder/blob/main/source/utils/prompt-builder.ts)).
`CLAUDE.md` is not read at runtime. `nanocoder init` reads it, among other
rule files, to write a new `AGENTS.md`.

**Subagents.** The main agent has an `agent` tool, runs up to five subagents
in parallel, and ships one built-in, `explore`. Custom agents live in
`.nanocoder/agents/*.md` or the user config folder, with `provider`, `model`,
`contextWindow`, `tools` and `disallowedTools` frontmatter
([subagents](https://docs.nanocollective.org/nanocoder/docs/latest/features/subagents)).
Subagents cannot spawn more subagents in the daemon's headless mode.

**MCP.** A project `.mcp.json` and a global one, with stdio, HTTP and
WebSocket transports and a per-server `alwaysAllow` list
([mcp-configuration](https://docs.nanocollective.org/nanocoder/docs/latest/configuration/mcp-configuration)).
The file name matches Claude Code's, but nanocoder requires a `transport`
field and its loader has no alias for Claude's `type`, so Claude entries need
editing ([mcp-config-loader.ts](https://github.com/Nano-Collective/nanocoder/blob/main/source/config/mcp-config-loader.ts)).

**Hooks.** The closest of the three to Claude Code. Shell commands under
`nanocoder.hooks` in `agents.config.json` run at `session-start`,
`session-end`, `user-prompt-submit`, `pre-tool-use`, `post-tool-use` and
`pre-compact`. A nonzero exit from `pre-tool-use` or `user-prompt-submit`
vetoes the action, and stdout goes back to the model. Context arrives in
environment variables rather than stdin JSON. A project `hooks` block replaces
the global one instead of merging
([hooks](https://docs.nanocollective.org/nanocoder/docs/latest/features/hooks)).

**Headless.** `nanocoder run "..."` with `--mode`, `--prompt-file` and
`--trust-directory`. `--plain --json` prints one JSON object with the final
text, every tool call, changed files and token use. It exits 0 on success, 1
on error and 2 when a tool needed approval
([commands](https://docs.nanocollective.org/nanocoder/docs/latest/features/commands)).
`--acp` serves the Agent Client Protocol over stdio
([acp](https://docs.nanocollective.org/nanocoder/docs/latest/features/acp)).

**Permissions.** Five modes: normal, auto-accept, yolo, plan and architect.
`run` defaults to auto-accept, where bash, commits and destructive file
operations still need approval. Nobody is there to give it, so a `run` that
reaches one of those exits unless `nanocoder.alwaysAllow` or yolo mode covers
it. An optional OS sandbox for `execute_bash` covers macOS and Linux
only
([development-modes](https://docs.nanocollective.org/nanocoder/docs/latest/features/development-modes),
[configuration](https://docs.nanocollective.org/nanocoder/docs/latest/configuration)).

**Models.** Provider pages cover Ollama, llama.cpp, LM Studio, vLLM, MLX
server, LocalAI, llama-swap and generic OpenAI-compatible endpoints
([providers](https://github.com/Nano-Collective/nanocoder/tree/main/docs/configuration/providers)).
Each subagent can name its own provider and model, for example a small local
model for research under a cloud model for the main session.

**Windows.** Runs natively from npm with config in `%APPDATA%\nanocoder`.
Hooks and custom tools run through `cmd.exe`, the daemon autostarts through
Task Scheduler, and CI runs a Windows-only subset of tests
([pr-checks.yml](https://github.com/Nano-Collective/nanocoder/blob/main/.github/workflows/pr-checks.yml),
[CHANGELOG](https://github.com/Nano-Collective/nanocoder/blob/main/CHANGELOG.md)).
The installation page does not mention Windows; of its methods, only npm
applies there.

**In T3 Code.** Not a built-in provider, and not in the
[ACP Registry](https://github.com/agentclientprotocol/registry) as of
2026-10-20. T3's "Local ACP command" option accepts any executable plus
arguments ([providers-acp.md](https://github.com/pingdotgg/t3code/blob/main/docs/user/providers-acp.md)),
so `nanocoder` with `--acp` should appear as a provider. That is untested.

## OpenCode

OpenCode is in the middle of a major version change. V2 is a separate
package, `@opencode/cli`, at 2.1.1 as of 2026-10-20, and opencode.ai serves V1
docs at `/docs` and V2 docs at `/v2/docs`. The migration guide says V1 agent
definitions, commands and skills "should continue to work without changes,"
but V1 plugins do not run in V2
([migrate-v1](https://opencode.ai/v2/docs/migrate-v1)).

**Skills.** `SKILL.md` in `.opencode/skills`, `.claude/skills` and
`.agents/skills`, walking up to the project root, plus the same three under
the home directory. V2 finds `SKILL.md` nested in grouping folders up to six
levels deep, and V1 uses `skills/**/SKILL.md`, so tracer's nested layout loads
in both ([V2 skills](https://opencode.ai/v2/docs/skills),
[V1 skill source](https://github.com/anomalyco/opencode/blob/v1.19.3/packages/opencode/src/skill/index.ts)).
The model loads a skill through a `skill` tool.

**Context files.** V1 reads `AGENTS.md`, falls back to `CLAUDE.md` when the
project has no `AGENTS.md`, and falls back to `~/.claude/CLAUDE.md` globally
([V1 rules](https://opencode.ai/docs/rules/)). V2 "recognizes `AGENTS.md` only.
It does not use `CLAUDE.md` as a fallback." It combines every `AGENTS.md` from
the workspace up to the project root, loads nested ones as the agent reads
into a folder, and notices edits mid-session
([V2 instructions](https://opencode.ai/v2/docs/instructions)).

**Subagents.** Markdown agents in `.opencode/agents/` or
`~/.config/opencode/agents/` with `mode: subagent`, a `model`, and their own
permission rules. The built-in primary agents are Build and Plan, and the
built-in subagents are General and Explore. The parent's `subagent` permission
decides which agents it may launch
([V2 agents](https://opencode.ai/v2/docs/agents)). In V2 source, the only
consumer of `.claude` directories I found is skill discovery
([compatibility.ts](https://github.com/anomalyco/opencode/blob/dev/packages/core/src/config/plugin/compatibility.ts)).

**MCP.** Local and remote servers with OAuth, added with `opencode mcp add`.
V2 moves them under `mcp.servers`
([V2 MCP servers](https://opencode.ai/v2/docs/mcp-servers)). I found no reading
of Claude's `.mcp.json` in V2 source.

**Hooks.** TypeScript plugins in `.opencode/plugins/` or from npm. V1 plugins
use named hooks such as `tool.execute.before`; V2 has a new plugin API with
hooks per domain, for example `ctx.session.hook("prompt", ...)`
([V1 plugins](https://opencode.ai/docs/plugins/),
[V2 plugins](https://opencode.ai/v2/docs/build/plugins)). Neither version's
docs describe shell-command hooks in configuration.

**Headless.** `opencode run` takes `--model`, `--agent`, `--format json` and
`--auto`, and can attach to a running server. `opencode serve` exposes an HTTP
API that the SDK and T3 Code use, and `opencode acp` speaks ACP
([V2 commands](https://opencode.ai/v2/docs/cli/commands),
[V1 CLI](https://opencode.ai/docs/cli/)).

**Permissions.** Rules of action, resource and effect, where the effect is
`allow`, `ask` or `deny`. V2 orders them in one array, the last match wins,
and an unmatched check asks ([V2 permissions](https://opencode.ai/v2/docs/permissions)).
Each agent can carry its own rules. In `opencode run` nobody can answer, so an
`ask` is rejected unless `--auto` is passed; `deny` always holds
([noninteractive.ts](https://github.com/anomalyco/opencode/blob/dev/packages/cli/src/run/noninteractive.ts)).
V1 asks before touching paths outside the project; V2 allows that by
default.

**Models.** Each agent names `provider/model#variant`. Local models go through
the OpenAI-compatible provider package, and the V1 docs walk through
llama.cpp, LM Studio and Ollama
([V2 providers](https://opencode.ai/v2/docs/providers),
[V1 providers](https://opencode.ai/docs/providers/)).

**Windows.** V2 publishes native Windows x64 and ARM64 binaries and a desktop
app but says "Windows package managers are not supported"
([V2 intro](https://opencode.ai/v2/docs)). 2.1.0 added persistent terminals on
Windows ([CHANGELOG](https://github.com/anomalyco/opencode/blob/dev/CHANGELOG.md)).
The V1 docs still recommend WSL "for the best experience"
([V1 Windows](https://opencode.ai/docs/windows-wsl/)).

**In T3 Code.** A built-in driver that needs OpenCode 1.14.19 or newer,
supports V2 from 2.0.18, and marks 1.x "Limited support"
([providers-opencode.md](https://github.com/pingdotgg/t3code/blob/main/docs/user/providers-opencode.md)).
T3 starts `opencode serve` itself or connects to a server URL with a password,
and reads models, agents and skills from `opencode models --verbose`,
`opencode agent list` and `opencode debug skill`
([OpenCodeRuntime.ts](https://github.com/pingdotgg/t3code/blob/main/packages/provider-opencode/src/server/OpenCodeRuntime.ts)).
OpenCode's primary agents show up as an "Agent" option in the composer, and
T3's plan mode uses OpenCode's `plan` agent. T3 writes its permission modes as
OpenCode permission rules; Auto behaves like Supervised because OpenCode has no
automatic reviewer. OpenCode is also in the ACP Registry, which runs
`opencode acp`.

## T3 Code's side

T3 Code runs agents on the machine that hosts its server, whichever device
the user connects from. Providers come three ways
([install.md](https://github.com/pingdotgg/t3code/blob/main/docs/user/install.md),
[providers-acp.md](https://github.com/pingdotgg/t3code/blob/main/docs/user/providers-acp.md)):

1. Built-in drivers, including Pi and OpenCode, each with a binary path,
   launch arguments or server URL, and per-instance environment variables.
2. Agents from the official ACP Registry, which T3 downloads into its own
   tools folder.
3. A "Local ACP command", any installed executable that speaks ACP.

At home, `~/.t3/userdata/settings.json` holds one provider instance, Pi,
enabled and set to `binaryPath: omp`. OpenCode has no instance there, which fits
its showing as disabled. The installed app is T3 Code Nightly
0.1.1-nightly.20261018.

Two T3 features matter for a factory. First, T3's `delegate_task` MCP tool
starts a child thread on a chosen provider instance and model, with its own
runtime mode. Codex, Claude, OpenCode, OpenCode 2, Pi and Registry agents can
all run those children
([orchestrator-mcp-server.md](https://github.com/pingdotgg/t3code/blob/main/docs/orchestration-v2/orchestrator-mcp-server.md)).
Second, T3 exposes an MCP endpoint that outside agents, such as Claude Code in
a terminal, can use to start and steer threads on any configured provider
([outside-agents.md](https://github.com/pingdotgg/t3code/blob/main/docs/user/outside-agents.md)).
A factory could hand T3 the job of running a step on Pi or OpenCode instead of
spawning each CLI itself.

T3 Code installs on Windows with winget or scoop, or with
`irm https://t3.codes/install.ps1 | iex`
([README](https://github.com/pingdotgg/t3code/blob/main/README.md)). Its
OpenCode driver has Windows-specific code that runs `opencode.exe` directly
instead of npm's `.CMD` shim. I did not find Windows notes for the Pi driver.

## What this means for jidoka

The portable layer is thin: `SKILL.md` skills and `AGENTS.md`. No single
skills folder reaches every harness. `.agents/skills/<name>/SKILL.md` loads in
Pi, oh-my-pi and OpenCode, and `.claude/skills/<name>/SKILL.md` loads in Claude
Code, oh-my-pi and OpenCode, so one harness always needs a settings entry or a
link. I did not check Codex here. Tracer's current two-level nesting under
`.claude/skills/tracer/skills/` also hides its skills from oh-my-pi. nanocoder
shares none of this layer.

Subagents, hooks and permissions do not port. Each harness has its own agent
file format, and the hooks are shell commands in Claude Code and nanocoder but
TypeScript in Pi, oh-my-pi and OpenCode. A factory that depends on a
`SessionStart` hook or on spawning named subagents needs one adapter per
harness. Running headless is the easy part. Each one has a one-shot mode with
JSON output.

All four run natively on Windows, and so does T3 Code, so the work machine
does not narrow the choice. If jidoka adds one harness beyond Claude Code and
Codex, I would start with OpenCode V2. I would not plan around oh-my-pi inside
T3 Code until the settle bug has a supported fix.

## Unconfirmed

- Whether Pi expands `@` imports inside `AGENTS.md` or `CLAUDE.md`.
- Whether oh-my-pi runs the shell `hooks` in `.claude/settings.json`, and
  whether its Claude-plugin provider picks up tracer's
  `.claude/skills/tracer/.claude-plugin/plugin.json` layout.
- Whether `omp acp` or the `omp-t3` shim works as a T3 Code provider.
- Whether `nanocoder --acp` works as a T3 Code Local ACP command.
- Whether OpenCode V1 reads `.claude/agents`; its docs list only OpenCode
  folders and I checked the source of V2 only.
- Whether T3 Code's Pi driver works on Windows.
- None of the harnesses was run during this research. Every claim comes from
  docs and source, except the `omp --help` output and the home settings files.

## Sources read

| Project | Commit or version | Date |
|---|---|---|
| [pingdotgg/t3code](https://github.com/pingdotgg/t3code) | `main` at `5bcc90e` | 2026-10-20 |
| [earendil-works/pi](https://github.com/earendil-works/pi) | `main` at `22dc6c2`, Pi 1.3.0 | 2026-10-20 |
| [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi) | `main` at `10b9b49`; installed `omp` 18.12.2 | 2026-10-20 |
| [Nano-Collective/nanocoder](https://github.com/Nano-Collective/nanocoder) | `main` at `c72945d`, 1.31.0 | 2026-10-20 |
| [anomalyco/opencode](https://github.com/anomalyco/opencode) | `dev` at `db1fbe8` (V2 2.1.1); tag `v1.19.3` | 2026-10-20 |
| [agentclientprotocol/registry](https://github.com/agentclientprotocol/registry) | `main` listing | 2026-10-20 |
