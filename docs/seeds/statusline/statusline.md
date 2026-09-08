# Claude Code status bar — design reference

Status: first draft, 2026-09-07. Script and adoption seed live in
`claude/statusbar-seed.md` in this project (the seed embeds the full
`statusline.py`). This document is the *why* and the *what*; the seed is the
*how to install*. Another document that wants to incorporate the bar can link
to the seed for installation and lift sections from here for description.

## Purpose

One shareable status line for Claude Code that works unchanged at home
(subscription, git repos) and at work (API keys, mostly Perforce, git projects
run from a parent folder that is not itself a repo). Coworkers do not use
beads, so nothing here depends on it. Priorities, in order: cost (including
subagents), context usage, cache usage, then model and effort.

## Principles

- **No subprocesses.** The script reads stdin JSON, one small state file, and
  optionally a `.p4config`. It never runs `git`, `p4`, or anything else.
  Runs in about 25 ms.
- **Absolute numbers over percentages.** `ctx 162k / 200k`, `4k write`.
  A token count means the same thing on a 200k and a 1M model; a percent does
  not.
- **Color means act.** The resting state has no color. Amber is "look",
  red is "do something now".
- **Never lie, never crash.** Any field can be missing or null (before the
  first call, after `/compact`). Missing prints as `—`, never a fake `0`.
  All exceptions are caught; the worst case is the text `statusline: error`.
- **Portable.** Python 3.8+, no `jq`, no bash, forward-slash paths, works on
  macOS, Linux, Windows.
- **Small on purpose.** Presets are environment variables and top-of-file
  constants, not a plugin system.

## Layout

Two lines by default (`CC_STATUS_LINES=1` collapses to one).

```
Opus 4.1 · xhigh │ ctx 162k / 200k ▂▃▄▆▇ ⚠ >150k │ $4.87 · $4.12/h
cache 158k read · 4k write · 85k total · 🔥 3:42                    campfire
```

| Segment | Source field(s) | Rendering rule |
|---|---|---|
| Model | `model.display_name` | bold, always shown |
| Effort | `effort.level` | always shown; `xhigh` / `max` amber |
| Thinking | `thinking.enabled` | `no-think` (dim) only when `false` |
| Fast mode | `fast_mode` | `fast` (amber) only when `true` |
| Agent | `agent.name` | `@name` (dim) only when `--agent` used |
| Context | `context_window.total_input_tokens`, `.context_window_size`, `.used_percentage` | `ctx <in> / <size>`; amber at ≥ smart zone (150k tokens, absolute) with `⚠ >150k`; red at ≥ 90% of window |
| Sparkline | per-session state file | last 12 distinct context sizes, scaled to window size; dim |
| Compactions | state file | `cN` (dim) after N drops of > 40% from > 20k |
| Cost | `cost.total_cost_usd`, `.total_duration_ms` | `$x.xx · $y.yy/h`; the rate appears after 60 s of wall clock |
| Cache read | `context_window.current_usage.cache_read_input_tokens` | last call, absolute |
| Cache write | `context_window.current_usage.cache_creation_input_tokens` | last call, absolute; amber ≥ 8k, red ≥ 30k |
| Cache total | `prompt_cache.cache_write_tokens` | session-wide writes, dim |
| Cache timer | `prompt_cache.warm`, `.expires_at` | `🔥 m:ss` green, amber under 60 s; `cold` when expired or `warm=false` |
| Label | `workspace.repo.name` → `P4CLIENT` env → `.p4config` walk-up → basename of `workspace.current_dir` | dim, right-aligned using `COLUMNS` |

Notes on the numbers:

- `context_window.total_input_tokens` is the whole prompt of the most recent
  API call, cache reads and writes included. That is the number the smart-zone
  rule is about, so it is what `ctx` shows.
- `total_output_tokens` is only the last response's size and is omitted; it
  invites a false comparison against the session.
- Cost per hour is wall-clock, not API time. It falls while the human is
  thinking and rises during long autonomous runs. That is the intended
  reading: what an unattended session burns.

## Environment detection

Nothing is configured per machine. The same file renders correctly everywhere:

- `workspace.repo` exists only when Claude Code detected a git repo, so the
  label is the repo name at home and falls through at work.
- At work, `P4CLIENT` (env or `.p4config`) names the workspace. The walk-up
  reads `.p4config` (or `$P4CONFIG`, or `p4config.txt`) from `current_dir`
  upward. File reads only.
- `rate_limits` is present only on subscriptions. It is not displayed, so the
  bar does not need to know which account type it is under.

## Deliberately excluded

- Rate limits and PR state (not wanted).
- Git dirty / ahead / behind, Perforce opened files, pending changelists
  (would require subprocesses; `p4` calls are server round trips).
- Cache hit ratio as a percent (absolute tokens preferred).
- Current tool, pending permission, subagent count: not in the payload. They
  could be approximated by tailing `transcript_path`; rejected for v1 to keep
  the script trivially auditable.

## State file

`~/.claude/statusline-state/<session_id>.json`, written only when the context
size changes. Holds the last 12 context sizes, the window size, and a
compaction counter. Deleting the directory is always safe. `CC_STATUS_SPARK=0`
disables the sparkline; the file is still written (cheap) so compaction
counting keeps working.

## Tuning

| Variable | Default | Meaning |
|---|---|---|
| `CC_STATUS_LINES` | `2` | `1` for a single-line bar |
| `CC_STATUS_ASCII` | `0` | `1` for no emoji or box-drawing |
| `CC_STATUS_SMART_ZONE` | `150000` | amber threshold, absolute tokens |
| `CC_STATUS_WRITE_WARN` | `8000` | last-call cache-write tokens for amber |
| `CC_STATUS_WRITE_BAD` | `30000` | last-call cache-write tokens for red |
| `CC_STATUS_SPARK` | `1` | `0` hides the sparkline |

Flags on the command: `--demo` renders four built-in payloads (normal, cold
cache with a big write, post-compact nulls, garbage input) for a no-install
smoke test; `--dump` appends every raw payload to
`~/.claude/statusline-dump.jsonl`.

## Install shapes

- **User:** `~/.claude/statusline.py` + `statusLine` in `~/.claude/settings.json`.
- **Project:** `<project>/.claude/statusline.py` + `statusLine` in
  `<project>/.claude/settings.local.json` (per-machine, uncommitted, because
  the command needs an absolute path).
- `"refreshInterval": 1` makes the cache timer tick; the script is local and
  uses no API tokens.
- The adoption seed asks the human which of the two they want, writes the
  script, runs `--demo`, merges the setting without disturbing other keys,
  and pipes a sample payload through the exact configured command.

## Verified facts (Claude Code 2.1.263)

- `cost.total_cost_usd` **includes subagents**. Test: a headless session that
  spawned one general-purpose agent. Main transcript wrote 47,771
  cache-creation tokens; the subagent transcript
  (`<session>/subagents/agent-*.jsonl`) wrote 37,150; the session total was
  84,921. Exact. The per-model cost table summed to the reported total, and it
  also includes Claude Code's own small Haiku calls.
- `prompt_cache.expires_at` is **epoch seconds** (`Math.ceil(expiresAt/1000)`
  in the CLI source). `ttl` is emitted beside it. The script also accepts
  epoch ms and ISO-8601 in case that changes.
- Refresh triggers (docs): each assistant message, `/compact` completion,
  permission or vim mode changes, the `refreshInterval` timer, and the moment
  `expires_at` is reached. Updates are debounced at 300 ms; an in-flight
  script is cancelled when a new update arrives.
- `tput cols` does not work inside the script. `COLUMNS` and `LINES` are set
  in the environment by Claude Code.
- Subagent transcripts are separate files with `isSidechain: true`; the main
  transcript can contain duplicate usage entries for one streamed message, so
  any future transcript-tailing must dedupe by message id.

## Open ideas, not built

- Turn timer and last tool name from tailing `transcript_path` (last 64 KB).
- "Needs you" flag when the last transcript entry is an `AskUserQuestion`.
- Live subagent count from open `Agent` tool calls in the transcript.
- One-line "narrow" preset that drops the sparkline and label first.
