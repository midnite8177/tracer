**Tried and reversed.**

- A relative status-line path goes blank when the session `cd`s. The path
  is absolute, with forward slashes.
- `jq` and bash in the status line are not portable. It is Python.
- `refreshInterval` 15 on Windows still crash-stormed. Native Windows gets
  no `refreshInterval` at all.

<!-- seed -->
# Block 5 — status line (optional, ask first)

One shareable status line for Claude Code that works unchanged at home
(subscription, git repos) and at work (API keys, Perforce workspaces, git
projects run from a parent folder that is not itself a repo). Nothing in
it depends on beads, so it is safe to hand to a coworker on its own.
Priorities, in order: cost (subagents included), context usage, cache
usage, then model and effort. Design reference: the project's
`statusline.md`; standalone install seed: `statusbar-seed.md`. This block
is the same script, carried here so tracer stays one file.

**Principles.** No subprocesses, ever: the script reads stdin JSON, one
small state file, and optionally a `.p4config`; it never runs `git` or
`p4`, and renders in about 25 ms. Absolute numbers over percentages
(`ctx 162k / 200k`, `4k write`), since a token count means the same on a
200k and a 1M model. Color means act: the resting state has no color,
amber is "look", red is "do something now". Never lie, never crash: any
field can be missing or null (before the first call, after `/compact`);
missing prints as `—`, never a fake `0`, and the worst case is the text
`statusline: error`. Portable: Python 3.8+, no `jq`, no bash, forward
slashes everywhere.

**Layout.** Two lines by default (`CC_STATUS_LINES=1` collapses to one):

```
Opus 4.1 · xhigh │ ctx 162k / 200k ▂▃▄▆▇ ⚠ >150k │ $4.87 · $4.12/h
cache 158k read · 4k write · 85k total · 🔥 3:42 (2:47pm)           campfire
```

| Segment | Source | Rule |
|---|---|---|
| Model | `model.display_name` | bold, always |
| Effort | `effort.level` | always; `xhigh` / `max` amber |
| Thinking, fast, agent | `thinking.enabled`, `fast_mode`, `agent.name` | `no-think` only when off; `fast` only when on; `@name` only under `--agent` |
| Context | `context_window.total_input_tokens`, `.context_window_size`, `.used_percentage` | `ctx <in> / <size>`; amber at the smart zone (150k tokens, absolute) with `⚠ >150k`; red at 90% of window |
| Sparkline, compactions | per-session state file | last 12 distinct context sizes, dim; `cN` after N drops of more than 40% |
| Cost | `cost.total_cost_usd`, `.total_duration_ms` | `$x.xx · $y.yy/h`; the rate appears after 60 s of wall clock |
| Cache read / write | `current_usage.cache_read_input_tokens` / `.cache_creation_input_tokens` | last call; write amber at 8k, red at 30k |
| Cache total | `prompt_cache.cache_write_tokens` | session-wide writes, dim |
| Cache timer | `prompt_cache.warm`, `.expires_at` | macOS/Linux: `🔥 m:ss (h:mmpm)`, countdown plus the local clock time it goes cold. Native Windows: `🔥 until h:mmpm`, no countdown (no refresh timer there). Green, amber under 60 s; `cold` when expired or `warm=false` |
| Label | `workspace.repo.name`, else `P4CLIENT`, else `.p4config` walk-up, else folder name | dim, right-aligned via `COLUMNS` |

`total_input_tokens` is the whole prompt of the last call, cache reads and
writes included, which is what the smart-zone rule is about, so that is
what `ctx` shows. `total_output_tokens` is only the last response's size
and is omitted. Cost per hour is wall clock, not API time: it falls while
the human thinks and rises during long autonomous runs, which is the
intended reading. Verified against Claude Code 2.1.263: `cost.total_cost_usd`
includes subagents and Claude Code's own small housekeeping calls;
`prompt_cache.expires_at` is epoch seconds; the script re-runs on each
assistant message, after `/compact`, on mode changes, when the cache
expiry is reached, and on the `refreshInterval` timer. **Windows launches
the command through Git's `bash.exe`** even for plain `python`. With
several Claude windows open, timer-driven spawns piled up and
crash-stormed bash, sh and git machine-wide, at intervals of 1, 15, and
30 seconds, and hit coworkers too. Working theory: the spawns queue
behind slow shell work Claude runs during coding tasks (a `find /` under
MSYS is a huge I/O hit), and the interval only sets how fast the backlog
grows. Decision: **no `refreshInterval` on native Windows.** Event-driven
refresh still fires on each message and at cache expiry, and the script
detects Windows and switches the cache segment to the clock-time form so
nothing sits stale. (Related, not done: a Bash deny rule or CLAUDE.md
line steering Claude away from `find /` on Windows would address the
root cause.)

**Deliberately absent:** rate limits, PR state, git dirty/ahead/behind,
Perforce opened files, cache hit percent (absolute tokens instead), and
anything that would need a subprocess.

**State file.** `~/.claude/statusline-state/<session_id>.json`, written
only when the context size changes; deleting the directory is always
safe. It lives under the home directory, not the repo, so stealth has
nothing to exclude.

**Tuning.** Environment variables, read at each refresh; or edit the
constants at the top of the script.

| Variable | Default | Meaning |
|---|---|---|
| `CC_STATUS_LINES` | `2` | `1` for a single-line bar |
| `CC_STATUS_ASCII` | `0` | `1` for no emoji or box-drawing |
| `CC_STATUS_SMART_ZONE` | `150000` | amber threshold, absolute tokens |
| `CC_STATUS_WRITE_WARN` | `8000` | last-call cache-write tokens for amber |
| `CC_STATUS_WRITE_BAD` | `30000` | last-call cache-write tokens for red |
| `CC_STATUS_SPARK` | `1` | `0` hides the sparkline (the state file is still written so compaction counting keeps working) |
| `CC_STATUS_COUNTDOWN` | `1`; `0` on native Windows | `0` renders `until h:mmpm` instead of a countdown |

Flags: `--demo` renders four built-in payloads (home, work, post-compact
nulls, garbage) for a no-install smoke test; `--dump` appends every raw
payload to `~/.claude/statusline-dump.jsonl` for debugging.

**Install.** Ask the human: **user-wide** (`~/.claude/statusline.py`,
`statusLine` in `~/.claude/settings.json`) or **this project only**
(`<repo>/.claude/statusline.py`, `statusLine` in
`<repo>/.claude/settings.local.json`, per-machine and uncommitted). Under
stealth, project-only. Write the script from the block below byte for
byte; `chmod +x` on macOS and Linux is harmless and optional. Run
`<py> <absolute path> --demo` and require four sample bars with no
traceback before touching settings. Then read the target settings file,
parse it, add or replace only the top-level `statusLine` key, keep every
other key as it was, and write it back with two-space indentation; if a
`statusLine` was already there, tell the human what it was and keep the
old value in the report. The value depends on the OS.

macOS and Linux (including WSL):

```json
{ "statusLine": { "type": "command", "command": "python3 /absolute/path/to/statusline.py", "refreshInterval": 1 } }
```

Native Windows, **no `refreshInterval` key at all**:

```json
{ "statusLine": { "type": "command", "command": "python C:/Users/jeff/.claude/statusline.py" } }
```

The Windows rule is a hard constraint, for the reason above. Do not add
the key there; if the human asks for a live countdown, say why not. The
bar still updates on every message, `/compact`, mode change, and cache
expiry, and the script shows the expiry as a clock time
(`🔥 until 2:47pm`) so it never looks stale.

The path **must be absolute** (Claude Code runs it from the session's
current directory, which moves; a relative path goes blank with no
error) and uses **forward slashes on every platform**
(`"python C:/Users/jeff/.claude/statusline.py"` on Windows). Write the
real home path, not `~`. On macOS/Linux the timer costs nothing (local,
about 25 ms, no API tokens); omit `refreshInterval` if the human would
rather the bar update only per message, and they can set
`CC_STATUS_COUNTDOWN=0` to get the clock-time form there too.

**Verify end to end.** Pipe this through the exact configured command
with `COLUMNS=120` set, and expect a first line starting
`Test · high │ ctx 42k / 200k` and a second starting
`cache 40k read · 2k write`:

```
{"model":{"display_name":"Test"},"effort":{"level":"high"},"session_id":"verify","workspace":{"current_dir":"/tmp"},"context_window":{"total_input_tokens":42000,"context_window_size":200000,"used_percentage":21,"current_usage":{"cache_read_input_tokens":40000,"cache_creation_input_tokens":2000}},"prompt_cache":{"warm":true,"cache_write_tokens":50000},"cost":{"total_cost_usd":0.5,"total_duration_ms":600000}}
```

Then delete `~/.claude/statusline-state/verify.json`. The bar appears
after Claude Code restarts (or at the next message in a running
session). Do not offer more segments, colors, or features; the bar is
small on purpose.

`statusline.py`:

```python
{{include installed/statusline.py}}
```

---

