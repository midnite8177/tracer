# Plugin packaging, Codex skills, and skill licenses

Research for the "Design new tracer factory workflow" map, done on
2026-10-20. Versions checked: Claude Code 2.1.304, codex-cli 0.163.0, and
the `openai/codex` source on `main` at `36512a34ff`. Citations in square
brackets point to the source list at the end.

## Short answer

A Claude Code plugin can carry skills, subagents, hooks, a JavaScript
hooks module that the docs call a mod, MCP and LSP servers, workflow
scripts, a `bin/`
folder that goes on `PATH`, monitors, output styles, themes, channels,
prompts for user configuration, and dependencies on other plugins. It
cannot carry permission rules, `autoMode` rules, a main status line, or
always-loaded CLAUDE.md text. Its `settings.json` honors two keys only,
`agent` and `subagentStatusLine` [CC-components]. Three parts of a plugin
can still approve tool calls: a skill's `allowed-tools` for the turn that
invokes it, a `PreToolUse` hook that returns `allow`, and a mod that
handles `tool.check` [CC-skills, CC-perms].

Install scopes. User scope records the plugin in `~/.claude/settings.json`
and leaves nothing in the repo. Project scope writes `enabledPlugins` into
the committed `.claude/settings.json`. Local scope writes
`.claude/settings.local.json`, which Claude Code adds to the global git
excludes the first time it writes it. A folder with
`.claude-plugin/plugin.json` under `~/.claude/skills/` loads in every
session as `<name>@skills-dir` with no install step at all; tracer uses
the same mechanism today, but from the repo's `.claude/skills/`
[CC-install, CC-loading, CC-settings].

Pinning and updates. A `version` in `plugin.json` holds users on that
cached copy until the string changes. A marketplace entry can pin a git
`ref` and a full `sha`, and `marketplace add owner/repo#ref` pins the
catalog itself. Third-party marketplaces do not auto-update by default.
`claude plugin update` fetches the new version, and it applies after a
restart or `/reload-plugins` [CC-loading, CC-mkt-ref, CC-host].

Can a plugin stay invisible in a shared repo? Yes. A user-scope install, or a user-level
skills-directory plugin, puts nothing in the repo. A per-repo opt-in can
live in `.claude/settings.local.json`, which stays out of git.

Approvals. Run from a shell, `claude plugin marketplace add` and
`claude plugin install` finished with no prompt in a test on this machine
[Lab]. Claude Code writes the files itself, so no agent tool call passes
through the permission system. The tracer install went badly because an
agent wrote files into `.claude/`, which is a protected path. In auto mode
each such write goes to the classifier, and in default mode each one
prompts [CC-modes]. The prompts that remain are narrow: a marketplace that
installs by running a command, unset `userConfig` options, workspace trust
for plugins that live in the repo, and the per-server approval for MCP
servers a repo plugin declares [CC-install, CC-loading, CC-components].

Plugins work on Windows. The docs list Windows rules for hook shells, path
separators, link-mode plugins and git [CC-trouble, CC-hooks, CC-mkt-ref].

Codex reads the same `SKILL.md` format, which both tools describe as the
Agent Skills open standard [CC-skills, CX-skills]. It looks in
`.agents/skills` and `~/.agents/skills`, not in `.claude/skills`. Codex has
a plugin format of its own and also reads Claude's
`.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` as
fallbacks [CX-package, CX-src-protocol, CX-src-marketplace]. In a test,
codex-cli 0.163.0 installed a Claude-format plugin from a Claude-format
marketplace with no prompt [Lab]. Codex plugins carry skills, MCP
servers, apps and hooks. The Codex manifest has no place for subagents,
workflows or a `bin/` folder [CX-src-manifest]. Codex ignores `disable-model-invocation`; the Codex switch
is `policy.allow_implicit_invocation: false` in the skill's
`agents/openai.yaml` [CX-src-parser, CX-skills]. Codex skips plugin hooks
until the human trusts them in `/hooks`, and asks again whenever a hook
changes [CX-hooks].

Licenses. All three sources are MIT: mattpocock/skills ("Copyright (c)
2026 Matt Pocock"), pstack ("Copyright (c) 2026 Lauren Tan", in
`pstack/LICENSE`), and humanlayer/skills ("Copyright (c) 2026
HumanLayer"). The one condition is that the copyright and permission
notice go with all copies or substantial portions. Claude Code copies only
the plugin directory into its cache, so a plugin that redistributes these
skills has to carry the notices inside that directory [CC-loading]. Two
loose ends turned up. `THIRD-PARTY-NOTICES.md` does not list HumanLayer,
though the seed carries `show-me` verbatim. And `unslop` follows the
early section layout of blader/humanizer, an MIT skill by Siqi Chen that
credits Wikipedia's "Signs of AI writing" page, whose text is CC BY-SA
4.0. Pstack credits neither. Whether that makes `unslop` a derivative is
unconfirmed.

## 1. What a Claude Code plugin can carry

A plugin is a directory of components that Claude Code installs and loads
as one unit [CC-overview]. It usually has a manifest at
`.claude-plugin/plugin.json`. Only `name` is required, and the manifest
itself is optional [CC-manifest]. Each component has a default folder
[CC-components]:

| Component | Default location | What it gives | Notes |
| :- | :- | :- | :- |
| Skills | `skills/<name>/SKILL.md` | `/<plugin>:<name>` | A `skills` key adds directories; it does not replace the default scan |
| Commands | `commands/*.md` | `/<plugin>:<file>` | Older format; skills supersede it |
| Subagents | `agents/*.md` | `<plugin>:<name>` | `permissionMode`, `hooks`, `mcpServers` and `initialPrompt` in agent frontmatter are ignored |
| Hooks | `hooks/hooks.json` | Lifecycle hooks | Registered when the plugin loads, so they fire whether or not a plugin skill runs |
| Mod | a `modules` entry in `hooks/hooks.json` | JavaScript hooks that can draw panes, add commands and answer tool calls | See [CC-perms] for how a mod's approval ranks |
| MCP servers | `.mcp.json` | `plugin:<plugin>:<server>`; tools `mcp__plugin_<plugin>_<server>__<tool>` | `.mcpb` bundles accepted |
| LSP servers | `.lsp.json` | Diagnostics and symbol navigation | The binary must already be on `PATH` |
| Workflows | `workflows/*.js` | `/<plugin>:<meta.name>` | Scripts that orchestrate many subagents [CC-workflows] |
| Executables | `bin/` | Bare commands in the Bash tool's `PATH` | Placed after the user's own entries, so a plugin cannot shadow `git` |
| Monitors | `monitors/monitors.json` | Background commands whose output reaches Claude | Interactive sessions only, never under `-p` |
| Output styles, themes | `output-styles/`, `themes/` | Entries in `/output-style`, `/theme` | |
| Channels | `channels` in the manifest | Inbound messages bound to one of the plugin's MCP servers | |
| Default settings | `settings.json` | `agent` and `subagentStatusLine` only | Every other key is dropped at load |
| User config | `userConfig` in the manifest | Values the user is asked for; sensitive ones go to secure storage | Exported to hooks as `CLAUDE_PLUGIN_OPTION_<KEY>` |
| Dependencies | `dependencies` in the manifest | Other plugins, with semver ranges | Ranges resolve against `<name>--v<version>` git tags [CC-deps] |

What a plugin cannot carry:

- Permission rules. `permissions.allow`, `deny` and `ask` live in settings
  files, and a plugin's `settings.json` keeps only `agent` and
  `subagentStatusLine` [CC-components, CC-manifest].
- `autoMode` rules. The classifier reads `autoMode` from user settings
  and managed settings, and ignores it in `.claude/settings.json` and
  `.claude/settings.local.json` [CC-automode].
- A main status line. Only `subagentStatusLine` passes. Tracer's
  `.claude/statusline.py` would need another home.
- Always-loaded instructions. Claude Code does not load a `CLAUDE.md` at
  the plugin root, and `claude plugin validate` warns about one
  [CC-components]. Two ways remain: a skill, which loads on demand, or a
  `SessionStart` hook, whose `additionalContext` is added to every session
  [CC-hooks].

What a plugin can do in place of permission rules:

- A skill's `allowed-tools` grants the listed tools for the turn that
  invokes the skill, and the grant clears with the next user message.
  Workspace trust does not gate this field [CC-skills].
- A `PreToolUse` hook that returns `permissionDecision: "allow"` skips the
  prompt. Deny and ask rules still win over it [CC-perms, CC-hooks].
- A mod that handles `tool.check` answers after the `PreToolUse` hooks.
  With no managed settings on the machine and no Team or Enterprise login
  as the credential, a mod can approve a call that a deny rule refuses, and
  in auto mode its approval skips the classifier. A session on an API key
  counts as having no such login [CC-perms]. That is the strongest lever
  a plugin has. It is also the one most likely to surprise a reviewer.

Everything a plugin runs, it runs as the user. Hooks, monitors, MCP and LSP
servers run outside the sandbox [CC-security].

## 2. Install scopes: user level and per repo

| How the plugin arrives | Where it is recorded | Repo footprint | Notes |
| :- | :- | :- | :- |
| Marketplace install, user scope (the default) | `enabledPlugins` and `extraKnownMarketplaces` in `~/.claude/settings.json`; files under `~/.claude/plugins/` | None | Loads in every project, and in the terminal, the desktop app and VS Code on that machine |
| Marketplace install, project scope | `enabledPlugins` in `.claude/settings.json` | A committed settings entry | Each collaborator still installs it once; it does not download by itself unless the entry uses a relative-path source |
| Marketplace install, local scope | `.claude/settings.local.json` | None, the file is git-excluded | Claude Code adds `**/.claude/settings.local.json` to the global git excludes the first time it writes the file; a hand-made file is not excluded |
| Skills-directory plugin, user level | A folder with `.claude-plugin/plugin.json` under `~/.claude/skills/` | None | Loads in place, every session, as `<name>@skills-dir`; `claude plugin init` scaffolds one |
| Skills-directory plugin, project level | A folder under the repo's `.claude/skills/` | Files in the repo, hidden today through `.git/info/exclude` | Loads only after workspace trust, only from the session's primary working directory, and from the main checkout when the desktop app opens a worktree |
| Session-only | `--plugin-dir`, `--plugin-url` or the `CLAUDE_CODE_PLUGIN_DIRS` variable | None | Wins over same-named installed plugins |
| Managed | Managed settings | None | Force-enables or blocks, and nothing overrides it |

Sources: [CC-install, CC-loading, CC-create, CC-settings].

When two copies share a manifest name, Claude Code loads one of them in
this order: managed, then session-only, then marketplace-installed, then
skills-directory, then synced from claude.ai. Between two
skills-directory copies, the one in `~/.claude/skills/` wins over the
project's [CC-loading].

A user-level skills-directory plugin can still be opted in per repo.
Its manifest sets `defaultEnabled: false`, and a repo that wants it sets
`"<name>@skills-dir": true` in `.claude/settings.local.json`. The loading
reference states that a settings entry overrides `defaultEnabled` for
skills-directory plugins [CC-loading, CC-manifest]. I did not test this
combination.

Jeff's machine already runs one user-level skills-directory plugin,
`smells@skills-dir` at `~/.claude/skills/smells`, version `0.1.0+seed.2`
[claude plugin list].

## 3. Pinning a version and taking updates

Claude Code computes a version for each installed plugin and uses it as
the cache key and the update test [CC-loading]:

1. The manifest's `version` comes first.
2. Then the marketplace entry's `version`.
3. Otherwise a value from the source type: a 12-character commit SHA for
   `github`, `url` and `git-subdir` sources, the archive's SHA-256 for
   `archive`, `unknown` for `npm` and for a local directory outside git.

Because the manifest wins, a fixed `"version": "1.0.0"` keeps every user
on the cached copy however many commits land, until the string changes.
Leaving `version` out of both places makes users track commits instead
[CC-host].

Pins available to the marketplace author [CC-mkt-ref, CC-host]:

- A plugin entry's `github`, `url` or `git-subdir` source takes `ref` and
  `sha`. With both set, Claude Code checks out the `sha`.
- An `archive` source takes a `sha256`, and a changed download is refused.
- A user who adds `owner/repo#stable` gets that branch or tag of the
  catalog. Release channels are two catalogs pointing at two refs; Claude
  Code has no channel concept of its own.

How updates arrive [CC-loading, CC-install]:

- Auto-update is on by default for Anthropic's official marketplaces and
  off for every other marketplace. When on, it runs up to ten minutes after
  the first message of an interactive session and updates the files on
  disk. The running session keeps the old version.
- `claude plugin update <name>@<marketplace>` updates one plugin and ends
  with "Restart to apply changes." `claude plugin marketplace update` with
  no name refreshes every catalog but leaves installed plugins at their
  versions.
- Old version directories stay for 14 days, so a session that loaded them
  keeps working.
- A plugin loaded in place from a local-path marketplace, and any
  skills-directory plugin, loads its current files at each session start;
  its version string pins nothing.

The official marketplace shows the pattern in practice. Its entry for
`mattpocock-skills` is
`{"source": "url", "url": "https://github.com/mattpocock/skills.git", "sha": "49dd158d10..."}`,
a commit from 2026-10-09 that is not the `v1.3.1` tag commit
`24fe0ef773` [CC-official-mkt]. Matt Pocock's own ADR notes that a release
reaches installed users when that pin moves, not when he tags [L-mp-adr].

## 4. Staying invisible in a shared repo

These leave nothing for collaborators to see:

- A user-scope marketplace install.
- A user-level skills-directory plugin in `~/.claude/skills/<name>/`.
- A local-scope install, whose only file, `.claude/settings.local.json`,
  is excluded through the global git excludes once Claude Code writes it.
  On Windows the file sits beside `.claude/settings.json` in the working
  directory rather than at the repository root [CC-settings]; the global
  exclude pattern `**/.claude/settings.local.json` covers both places.
- `CLAUDE_CODE_PLUGIN_DIRS` set in the shell profile.

The project-level skills-directory plugin that tracer uses stays hidden
only through `.git/info/exclude`, and it carries the costs listed in
section 2: workspace trust, no loading from a subdirectory, and the main
checkout's copy in desktop-app worktrees.

Beads in stealth mode is a separate question; this note does not cover
it.

## 5. Approvals during install and update

### Why the tracer install fought the classifier

Writes to `.claude/` are protected-path writes. In default and
`acceptEdits` modes each one prompts. In auto mode each one goes to the
classifier, and `permissions.allow` rules such as `Edit(.claude/**)` do not
pre-approve them [CC-modes]. The listed exceptions are worktrees under
`.claude/worktrees/`, plan files, background-session scratch space and
memory directories; `.claude/skills/` is not among them. The seed has the
agent write the tracer-native and carried skills, write
`.claude-plugin/plugin.json`, and apply the patch list, all under
`.claude/skills/tracer/` [Local-seed]. Each of those edits is a separate
protected-path decision. The fetch step clones a repository and copies
from it in one shell command, which may also read as "downloading and
executing code", a category the classifier blocks by default [CC-modes].
That last link is my inference; the docs do not say which rule fired.

### What a plugin install asks for

Shell commands [CC-install, CC-cli]:

- `claude plugin marketplace add <source>` adds a marketplace without a
  confirmation step.
- `claude plugin install <name>@<marketplace>` installs without prompting,
  at user scope unless `--scope` says otherwise. It never prompts for
  `userConfig`; values go in with `--config KEY=VALUE` or later through
  `claude plugin configure --values-stdin`.
- `claude plugin install <name> --marketplace <source>` does both in one
  command, from v2.1.292.
- A marketplace whose plugin installs by running a command shows that
  command and needs `--yes` or `--accept-command <sha256>` when no one is
  at a terminal.

Inside a session, `/plugin install` opens a panel with a trust warning and
a scope choice, and the `userConfig` dialog opens for unset options. That
is one human interaction, not one per file [CC-install, CC-components].

Repo-supplied plugins add trust steps [CC-loading, CC-perms]:

- A project-level skills-directory plugin loads only after the human
  accepts the workspace trust dialog for that folder.
- MCP servers declared by a repo plugin need the same per-server approval
  as a project `.mcp.json`.
- Monitors in a repo plugin do not load.

### Test on this machine

I built a one-skill plugin with a `SessionStart` hook and a Claude-format
marketplace under `/tmp`, then ran these with `CLAUDE_CONFIG_DIR` pointed
at an empty temp directory so Jeff's settings stayed untouched [Lab]:

```text
$ claude plugin marketplace add /tmp/jidoka-research/lab/mkt
✔ Successfully added marketplace: lab (declared in user settings)
$ claude plugin install hello@lab
✔ Successfully installed plugin: hello@lab (scope: user)
$ claude plugin update hello@lab        # after bumping version to 0.1.1
✔ Plugin "hello" updated from 0.1.0 to 0.1.1 for scope user. Restart to apply changes.
```

All three exited 0 with stdin closed; a command that needed an answer
would have failed instead. The settings file afterwards held only
`extraKnownMarketplaces.lab` and `enabledPlugins["hello@lab"]`.

One case stays open. When the agent runs `claude plugin install` through
its Bash tool, that is a single tool call for the permission system and,
in auto mode, for the classifier. The docs do not say how the classifier
judges it. Unconfirmed. The predictable path is for the human to run the
command in a shell, or for jidoka's installer to be a script the human
starts.

## 6. Windows

The plugin docs treat Windows as supported and list its differences:

- Hooks in shell form run through Git Bash on Windows, or PowerShell when
  Git Bash is missing; a hook can set `"shell": "powershell"`.
  `${CLAUDE_PLUGIN_ROOT}` arrives with forward slashes on purpose
  [CC-trouble, CC-hooks].
- Git for Windows is optional for Claude Code itself; without it the
  Bash tool is replaced by the PowerShell tool [CC-setup]. Adding a git
  marketplace needs `git` on `PATH` [CC-trouble].
- `bin/` executables reach the Bash tool and the unsandboxed PowerShell
  tool, not sandboxed PowerShell [CC-components].
- Link-mode command sources are refused on Windows, and a UNC path fails a
  command source [CC-mkt-ref].
- Component paths with backslashes load only on Windows, so write forward
  slashes [CC-loading].
- Before v2.1.295, a project or local uninstall could leave a second
  record behind when the folder path differed in case [CC-trouble].

Plugins synced from claude.ai load only in sessions signed in with a
claude.ai account, and not when an `apiKeyHelper` or a token variable
supplies the credential [CC-loading]. The docs state no such limit for
marketplace or skills-directory plugins. That matters for the work machine,
which runs Claude Code on an API key.

## 7. Codex

### Skills

Codex skills are directories with a `SKILL.md`, "built on the open agent
skills standard" [CX-skills]. Claude Code says the same of its skills
[CC-skills]. The Agent Skills spec defines six frontmatter fields: `name`,
which must match the directory name, `description`, `license`,
`compatibility`, `metadata` and an experimental `allowed-tools` [AS-spec].

Where Codex looks [CX-skills]:

| Scope | Location |
| :- | :- |
| Repo | `.agents/skills` in every directory from the working directory up to the repo root |
| User | `~/.agents/skills` |
| Admin | `/etc/codex/skills` |
| System | Bundled with Codex |

Codex does not read `.claude/skills` or `~/.claude/skills`; neither path
appears in the docs, and a search of the `openai/codex` source for
`claude/skills` found nothing. The Claude Code skills docs do not mention
`.agents/skills` either [CC-skills]. Codex follows symlinked skill folders
in its own locations [CX-skills].

How Codex reads a Claude skill. Its parser takes `name`, `description`
and `metadata.short-description`, falls back to the directory name when
`name` is missing, requires `description`, and ignores unknown keys
[CX-src-parser]. So `disable-model-invocation`, `argument-hint` and
`allowed-tools` have no effect in Codex. A skill that Claude Code hides
from the model would be picked implicitly by Codex unless its
`agents/openai.yaml` sets `policy.allow_implicit_invocation: false`
[CX-skills]. HumanLayer's `show-me` ships exactly that file next to its
`disable-model-invocation: true` [L-hl]. Upstream mattpocock skills ship
the file too; the one in `tdd` holds display metadata only. Tracer's fetch
step deletes those `agents/` folders today [L-mp, Local-seed].

Claude Code substitutes `${CLAUDE_PLUGIN_ROOT}` inside skill text
[CC-components]. A code search of `openai/codex` found the variable only
in the hook engine [CX-src-hooks]. Codex lists each skill's file path in
the initial skill list instead [CX-skills], so a skill that names its
scripts relative to its own folder works in both.

Codex also has `/import`, which copies Claude Code instructions, settings,
skills, plugins, hooks, slash commands and subagents into Codex. The
desktop app can keep the import in sync [CX-import]. That is a copy, not a
shared install.

### Plugins

Codex has its own plugin format. The portable form is a root `plugin.json`
that declares the Agent Plugins schema, with `skills/` and `mcp.json` at
the root. OpenAI-specific fields sit under `extensions.com.openai`, and an
older `.codex-plugin/plugin.json` still works [CX-package]. The Codex
source looks for a manifest in this order: a root `plugin.json` with an
Agent Plugins `$schema`, then `.codex-plugin/plugin.json`, then
`.claude-plugin/plugin.json`, then `.cursor-plugin/plugin.json`
[CX-src-namespace, CX-src-protocol]. Marketplace files are found at
`.agents/plugins/marketplace.json`, `.agents/plugins/api_marketplace.json`,
`.claude-plugin/marketplace.json` or `.cursor-plugin/marketplace.json`
[CX-src-marketplace]. The docs call the Claude locations
"legacy-compatible" and say "OpenAI also accepts legacy and
Claude-compatible manifests, but new packages should use this format"
[CX-package].

What a Codex plugin carries: skills, MCP servers, apps (`.app.json`),
lifecycle hooks, and presentation assets [CX-package, CX-plugins]. The
manifest parser also reads a `commands` key, and has no field for
agents, workflows or `bin/` [CX-src-manifest]. OpenAI's guide for Claude
plugin authors says to turn commands and agents into skills, to call
bundled executables by a package-relative path, to remove Claude-only
settings, and to move output styles, LSP servers, themes, monitors,
channels and dependencies into skills before removing them
[CX-submit-claude]. That guide is written for the public directory. Codex
custom agents are TOML files in `~/.codex/agents/` or `.codex/agents/`,
outside any plugin [CX-subagents].

Hooks. Codex looks for `hooks/hooks.json` in the plugin, sets
`PLUGIN_ROOT` and `PLUGIN_DATA`, and also sets `CLAUDE_PLUGIN_ROOT` and
`CLAUDE_PLUGIN_DATA` "for compatibility with existing plugin hooks".
Installing or enabling a plugin does not trust its hooks. Codex skips them
until the human trusts the exact definition in `/hooks`, and it records
trust by hash, so every changed hook needs a new review [CX-hooks]. The
packaging guide says hooks are supported "for plugins installed manually
in Codex desktop", and that a plugin with hooks cannot go in the public
directory [CX-package]. The hooks page describes `/hooks` review in the
CLI without that desktop limit. I did not run a Codex session to see a
plugin hook fire. Unconfirmed for the CLI.

Marketplace sources. Codex accepts a relative path, `local`, `url`,
`git-subdir` and `npm` sources, each git source with `ref` or `sha`
[CX-src-marketplace, CX-package]. It has no `github` source type, which
Claude Code has. An entry Codex cannot resolve is skipped
[CX-package]. A marketplace shared by both tools should use relative
paths, `url` or `git-subdir`.

Install, update and stealth in Codex [CX-cli, CX-package, CX-config-ref]:

- `codex plugin marketplace add <source> [--ref REF]` records the
  marketplace in `~/.codex/config.toml`. `codex plugin add
  <plugin>@<marketplace>` installs into
  `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`.
- There is no `codex plugin update` in 0.163.0. `codex plugin marketplace
  upgrade` refreshes git catalogs. Re-running `codex plugin add` after a
  version bump replaced the cached copy [Lab].
- A repo can enable a plugin with `[plugins."name@marketplace"]` in
  `.codex/config.toml`, which Codex loads only for trusted projects. The
  config reference lists no per-project plugin switch in the user file,
  so a per-repo opt-in that stays out of git means an excluded
  `.codex/config.toml`.
- Codex instruction files have a stealth catch. In each directory Codex
  reads `AGENTS.override.md`, else `AGENTS.md`, else a fallback name, and
  "includes at most one file per directory" [CX-agents-md]. A private
  `AGENTS.override.md` at the repo root therefore hides a committed
  `AGENTS.md` there, and a fallback such as `AGENTS.local.md` never loads
  while `AGENTS.md` exists.

### Test with codex-cli 0.163.0

Against the same Claude-format marketplace from section 5, with
`CODEX_HOME` pointed at an empty temp directory [Lab]:

```text
$ codex plugin marketplace add /tmp/jidoka-research/lab/mkt
Added marketplace `lab` from /private/tmp/jidoka-research/lab/mkt.
$ codex plugin add hello@lab
Added plugin `hello` from marketplace `lab`.
Installed plugin root: .../cx/plugins/cache/lab/hello/0.1.0
$ codex plugin list
Marketplace `lab`
/private/tmp/jidoka-research/lab/mkt/.claude-plugin/marketplace.json
hello@lab  installed, enabled  0.1.0
```

No prompts. Codex read `.claude-plugin/marketplace.json` and
`.claude-plugin/plugin.json` and wrote two tables to `config.toml`:
`[marketplaces.lab]` and `[plugins."hello@lab"] enabled = true`. The cache
directory took the manifest's `0.1.0`, though the packaging guide says
local plugins cache under `local`. Claude Code's validator accepted the
shared marketplace with one warning, `plugins[0].policy: Unknown field`,
for the Codex-only `policy` block. I did not start a Codex session, so
whether the skill then appears under `$` was not checked.

### Windows

The ChatGPT desktop app on Windows supports plugins and skills, runs
natively with PowerShell and a Windows sandbox, or runs the agent in WSL2
[CX-windows]. Codex hooks take a `commandWindows` override
[CX-hooks]. With an OpenAI API key, Codex CLI can "browse, install, and
manage supported OpenAI-curated plugins", and some plugins are missing
because their OAuth flows are unsupported [CX-plugins]. The docs do not
say whether local-marketplace plugins behave differently under an API
key. Unconfirmed.

### Cross-tool standards

- Agent Skills, at agentskills.io, defines the `SKILL.md` directory
  format [AS-spec]. Claude Code and Codex both cite it.
- Agent Plugins, at agent-plugins.org, defines a package of skills and
  MCP servers around a root `plugin.json`. Version 1.0.0 is published and
  1.1.0 is a draft. Its steering committee lists people from Amazon,
  Cursor, Microsoft, OpenAI and Vercel, and no one from Anthropic
  [AP-spec]. Codex reads it first [CX-src-namespace]. The Claude Code docs
  do not mention it. They place the manifest at
  `.claude-plugin/plugin.json` and say nothing about a root `plugin.json`
  [CC-manifest].

In practice one plugin directory can serve both tools today:
`.claude-plugin/plugin.json`, `skills/<name>/SKILL.md` with an
`agents/openai.yaml` beside each skill that should stay user-invoked, and
a `.claude-plugin/marketplace.json` with relative-path sources. Subagents,
workflows and `bin/` would work in Claude Code only.

## 8. Licenses and attribution

| Source | License | Notice | Where checked |
| :- | :- | :- | :- |
| `mattpocock/skills` | MIT | "Copyright (c) 2026 Matt Pocock" | `LICENSE` at tag `v1.3.1` (commit `24fe0ef773`); `plugin.json` there says `"license": "MIT"` [L-mp] |
| pstack: `unslop`, `no-comments`, `show-me-your-work`, agent `comment-sicko` | MIT | "Copyright (c) 2026 Lauren Tan" | `pstack/LICENSE` in `cursor/plugins` at `93b00b8`; same text on `main`. `cursor/plugins` has no root license, and GitHub reports none for the repo [L-pstack] |
| HumanLayer `show-me` | MIT | "Copyright (c) 2026 HumanLayer" | `LICENSE` at the root of `humanlayer/skills`, `main` at `653b6411c1`; the plugin's `plugin.json` says `"license": "MIT"` [L-hl] |

The MIT term is one sentence: "The above copyright notice and this
permission notice shall be included in all copies or substantial portions
of the Software." There is no notice-file format, no change log
requirement and no advertising clause.

What that means for a jidoka plugin:

- Tracer today clones mattpocock/skills at install time and redistributes
  none of it [Local-notices]. A plugin that ships modified copies of those
  skills redistributes them, so the Matt Pocock notice has to ship too.
- The notices have to sit inside the plugin directory. Claude Code copies
  only that directory into `~/.claude/plugins/cache/...`, and files outside
  it are not copied [CC-loading]. Codex copies into its own cache the same
  way [Lab]. A `LICENSE` or `THIRD-PARTY-NOTICES.md` at the plugin root
  meets the term. The Agent Skills `license` field can also name a bundled
  license file per skill [AS-spec]; Claude Code accepts it and does
  nothing with it [CC-skills].
- The plugin manifest's `license` field is an SPDX identifier for the
  plugin as a whole [CC-manifest]. It does not replace the notices.

Gaps found in this repo:

- `THIRD-PARTY-NOTICES.md` names pstack and mattpocock/skills only. The
  seed's Block 4d carries HumanLayer's `show-me` verbatim, apart from the
  open command in its last bullet, and credits it as "MIT, HumanLayer; Dex
  Horthy"
  [Local-seed]. The license's holder is "HumanLayer". The notices file
  needs a HumanLayer section.
- Block 4d records commit `93b00b8` for the pstack files but no commit for
  `show-me`. The file has five commits upstream, the latest `bba9d13` on
  2026-09-12 [L-hl].
- `unslop`'s numbered patterns follow the early `blader/humanizer`
  `SKILL.md` (commit `47a6432`, 2026-01-18) section for section. Its
  sections 1 to 12 match humanizer's 1 to 12, its style section matches
  humanizer's 13 to 18 plus one colon rule, and its communication and
  filler sections match humanizer's 19 to 24. Its sections 26 to 31 have
  no counterpart there [L-humanizer, Local-seed].
  Humanizer is MIT, "Copyright (c) 2025 Siqi Chen", and says it is "based
  on Wikipedia's 'Signs of AI writing' page". Wikipedia text is under CC
  BY-SA 4.0 [L-wp]. Pstack's `unslop` credits neither. Whether `unslop` is
  a derivative, and whether a list of pattern names carries
  share-alike obligations, is a legal question this research does not
  settle. Unconfirmed. Crediting humanizer and the Wikipedia page in the
  notices costs little.

## Unconfirmed

- How the auto-mode classifier judges `claude plugin install` run by the
  agent through Bash.
- Which classifier rule blocked the original tracer install steps.
- Per-repo opt-in of a user-level skills-directory plugin through
  `defaultEnabled: false` plus `"<name>@skills-dir": true` in
  `.claude/settings.local.json`; documented, not tested.
- Whether Codex CLI, as opposed to the desktop app, runs plugin hooks.
- Whether a Codex plugin's skills show up under `$` after a CLI install;
  the install succeeded, a session was not started.
- Codex local-marketplace plugins under API-key authentication.
- Whether Codex drops symlinks when it copies a plugin into its cache, as
  Matt Pocock's ADR reports [L-mp-adr].
- Whether T3 Code loads marketplace-installed Claude Code plugins. The
  Agent SDK docs say an installed plugin can be passed by its path under
  `~/.claude/plugins/` [CC-sdk-plugins]; they do not say the SDK loads it
  from `enabledPlugins` by itself.
- Whether `unslop` derives from `blader/humanizer`.

## Sources

Claude Code documentation, fetched 2026-10-20 as Markdown from
`https://code.claude.com/docs/en/<page>.md`:

- [CC-overview] https://code.claude.com/docs/en/plugins/overview
- [CC-components] https://code.claude.com/docs/en/plugins/components
- [CC-manifest] https://code.claude.com/docs/en/plugins/manifest-reference
- [CC-loading] https://code.claude.com/docs/en/plugins/loading
- [CC-install] https://code.claude.com/docs/en/plugins/install
- [CC-create] https://code.claude.com/docs/en/plugins/create
- [CC-mkt-ref] https://code.claude.com/docs/en/plugins/marketplace-reference
- [CC-host] https://code.claude.com/docs/en/plugins/host-marketplace
- [CC-deps] https://code.claude.com/docs/en/plugins/dependencies
- [CC-security] https://code.claude.com/docs/en/plugins/security
- [CC-trouble] https://code.claude.com/docs/en/plugins/troubleshooting
- [CC-skills] https://code.claude.com/docs/en/skills
- [CC-perms] https://code.claude.com/docs/en/permissions
- [CC-modes] https://code.claude.com/docs/en/permission-modes
- [CC-automode] https://code.claude.com/docs/en/auto-mode-config
- [CC-settings] https://code.claude.com/docs/en/settings
- [CC-hooks] https://code.claude.com/docs/en/hooks
- [CC-workflows] https://code.claude.com/docs/en/workflows
- [CC-setup] https://code.claude.com/docs/en/setup
- [CC-sdk-plugins] https://code.claude.com/docs/en/agent-sdk/plugins
- [CC-official-mkt] https://github.com/anthropics/claude-plugins-official/blob/main/.claude-plugin/marketplace.json
- [CC-cli] `claude plugin <command> --help` on Claude Code 2.1.304
- [claude plugin list] `claude plugin list` on Jeff's machine, read only

Codex and OpenAI, fetched 2026-10-20:

- [CX-skills] https://learn.chatgpt.com/docs/build-skills
- [CX-plugins] https://learn.chatgpt.com/docs/plugins
- [CX-package] https://developers.openai.com/plugins/build/plugins
- [CX-submit-claude] https://developers.openai.com/plugins/guides/submit-claude-plugin
- [CX-hooks] https://learn.chatgpt.com/docs/hooks
- [CX-config-ref] https://learn.chatgpt.com/docs/config-file/config-reference
- [CX-agents-md] https://learn.chatgpt.com/docs/agent-configuration/agents-md
- [CX-subagents] https://learn.chatgpt.com/docs/agent-configuration/subagents
- [CX-import] https://learn.chatgpt.com/docs/import
- [CX-windows] https://learn.chatgpt.com/docs/windows/windows-app
- [CX-src-protocol] https://github.com/openai/codex/blob/main/codex-rs/exec-server-protocol/src/protocol.rs, `DISCOVERABLE_PLUGIN_MANIFEST_PATHS`
- [CX-src-namespace] https://github.com/openai/codex/blob/main/codex-rs/utils/plugins/src/plugin_namespace.rs, `find_plugin_manifest_path`
- [CX-src-manifest] https://github.com/openai/codex/blob/main/codex-rs/core-plugins/src/manifest.rs
- [CX-src-marketplace] https://github.com/openai/codex/blob/main/codex-rs/core-plugins/src/marketplace.rs, `MARKETPLACE_MANIFEST_RELATIVE_PATHS` and `RawMarketplaceManifestPluginSourceObject`
- [CX-src-parser] https://github.com/openai/codex/blob/main/codex-rs/skills/src/parser.rs, `SkillFrontmatter`
- [CX-src-hooks] https://github.com/openai/codex/blob/main/codex-rs/hooks/src/engine/discovery.rs
- [CX-cli] `codex plugin <command> --help` on codex-cli 0.163.0

Standards:

- [AS-spec] https://agentskills.io/specification
- [AP-spec] https://github.com/agentplugins/agent-plugins-spec, README and MAINTAINERS.md at `ff8ab5e392`; https://agent-plugins.org

Licenses and upstream files:

- [L-mp] https://github.com/mattpocock/skills/blob/v1.3.1/LICENSE and `.claude-plugin/plugin.json` at the same tag
- [L-mp-adr] https://github.com/mattpocock/skills/blob/v1.3.1/.agents/adr/0002-ship-as-a-claude-code-plugin.md. Its claims that Codex takes `skills` only as a single path and drops symlinks are out of date on the first point: Codex `main` parses a string or an array of strings [CX-src-manifest]. The symlink claim was not checked.
- [L-pstack] https://github.com/cursor/plugins/blob/93b00b8/pstack/LICENSE and `pstack/.cursor-plugin/plugin.json` at the same commit
- [L-hl] https://github.com/humanlayer/skills/blob/main/LICENSE, `plugins/show-me/.claude-plugin/plugin.json` and `plugins/show-me/skills/show-me/agents/openai.yaml`, `main` at `653b6411c1`
- [L-humanizer] https://github.com/blader/humanizer, `LICENSE` and `README.md` on `main`, `SKILL.md` at `47a6432`
- [L-wp] https://en.wikipedia.org/wiki/Wikipedia:Copyrights

This repo:

- [Local-notices] `THIRD-PARTY-NOTICES.md`
- [Local-seed] `docs/seeds/tracer/tracer.md`, steps 5 to 8 and Block 4d

Test:

- [Lab] A one-skill plugin and a Claude-format marketplace built under
  `/tmp/jidoka-research/lab`, installed with `CLAUDE_CONFIG_DIR` and
  `CODEX_HOME` set to empty temp directories, on 2026-10-20.
