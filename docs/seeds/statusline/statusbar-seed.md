# Claude Code status bar — adoption seed

This file is for Claude Code to read. If you are a person: open Claude Code in
any folder and type

    hey Claude, adopt this file into my settings @/path/to/statusbar-seed.md

Claude does the rest. It will ask you one question (user-wide or this project
only), install a small Python script, wire it into your settings, and verify
it renders. Nothing here needs `jq`, bash, git, or network access.

---

## Instructions for Claude

You are installing a custom status line. Follow these steps in order. Do not
skip the question in step 2. Do not modify the script's logic; copy it exactly
as it appears in the **Script** section below.

### 1. Find a Python

Run, in this order, until one prints a version 3.8 or newer:
`python3 --version`, `python --version`, `py -3 --version`.
Call the winning command `<py>` (`py -3` counts as one command).

If none of the three work, **do not go searching the disk.** No `find`, no
`where`, no `Get-ChildItem`, no poking through Program Files, pyenv, conda,
uv, or Homebrew directories. Instead, ask the human right away:

> I couldn't find Python on your PATH (tried `python3`, `python`, `py -3`).
> Do you have Python 3.8+ installed? If so, paste the full path to the
> executable and I'll use that. If not, tell me and I'll stop here.

Wait for the answer. If they give a path, run `<that path> --version` to
confirm it is 3.8+, then use the path as `<py>` for the rest of the install
(quote it in the settings command if it contains spaces, and use forward
slashes). If they say they don't have Python, tell them where to get it for
their OS and stop. Do not try to install Python yourself.

On Windows, `python` may resolve to the Microsoft Store stub that opens the
Store instead of running. If `python --version` prints nothing or opens a
window, treat it as not found and move to `py -3`, then to the question above.

### 2. Ask where to install

Ask the human this question, offering exactly these two choices (use the
AskUserQuestion tool if it is available; otherwise ask in plain text and wait):

> Install the status bar for **your user** (every project on this machine) or
> **just this project**?
>
> - **User**: script goes to `~/.claude/statusline.py`, setting goes in
>   `~/.claude/settings.json`.
> - **Project**: script goes to `<project>/.claude/statusline.py`, setting goes
>   in `<project>/.claude/settings.local.json` (per-machine, not committed).

Wait for the answer. `<project>` is the directory Claude Code was launched in.

### 3. Write the script

Write the Python from the **Script** section below, byte for byte, to the path
chosen in step 2. Create the `.claude` directory if it does not exist. Do not
reformat, do not "improve", do not strip comments. On macOS and Linux, run
`chmod +x` on it; this is optional and harmless.

### 4. Verify the script before touching settings

Run `<py> <absolute path to statusline.py> --demo`. It must print four sample
bars (labelled `home`, `work`, `post-compact nulls`, `garbage`) with no
traceback. If it prints a traceback, the file was written incorrectly; rewrite
it from the seed and try again. Do not proceed until `--demo` is clean.

### 5. Merge the setting

Read the target settings file if it exists (`~/.claude/settings.json` for a
user install, `<project>/.claude/settings.local.json` for a project install).
Parse it as JSON. Add or replace only the top-level `statusLine` key. Keep every
other key exactly as it was. Write it back with 2-space indentation.

The value to set depends on the OS.

**macOS and Linux (including WSL):**

```json
"statusLine": {
  "type": "command",
  "command": "<py> <absolute path to statusline.py>",
  "refreshInterval": 1
}
```

**Native Windows:** no `refreshInterval` key at all.

```json
"statusLine": {
  "type": "command",
  "command": "<py> <absolute path to statusline.py>"
}
```

**Why no interval on Windows.** Claude Code on Windows launches the status
line command through Git's `bash.exe`, even when the command is plain
`python`. Timer-driven spawns queue up behind any slow shell work Claude is
doing (a `find /` during a coding task, for example) and the backlog has
crashed bash/sh/git machine-wide, at 1, 15, and 30 second intervals. So on
Windows the bar updates only on events: every message, `/compact`, mode
changes, and the moment the cache expires. The script detects Windows itself
and shows the cache expiry as a clock time (`🔥 until 2:47pm`) instead of a
countdown, so nothing looks stale. Do not add `refreshInterval` on Windows,
and say why in your report if the human asks for a live countdown.

Rules for `command`:

- The path **must be absolute**. Claude Code runs the command from the
  session's current directory, which moves when a shell `cd`s. A relative path
  goes blank with no error.
- Use **forward slashes on every platform**, including Windows
  (`"python C:/Users/pat/.claude/statusline.py"`). Valid JSON, and Python
  accepts them.
- Do not expand `~` yourself in the JSON for a user install if the OS shell
  will not expand it; write the real home path (`/Users/pat/...`,
  `C:/Users/pat/...`).
- If the settings file already had a `statusLine`, tell the human what it was
  before replacing it, and keep a copy of the old value in your final report.

On macOS/Linux, `refreshInterval` makes the cache countdown tick between
messages. The script runs locally in about 25 ms and uses no API tokens. If
the human says they would rather it only update per message, omit the key;
they can also set `CC_STATUS_COUNTDOWN=0` to get the clock-time form.

### 6. Verify end to end

Pipe a realistic payload through the exact command you wrote into settings,
with `COLUMNS=120` in the environment, and confirm two lines come back:

```
echo '{"model":{"display_name":"Test"},"effort":{"level":"high"},"session_id":"verify","workspace":{"current_dir":"/tmp"},"context_window":{"total_input_tokens":42000,"context_window_size":200000,"used_percentage":21,"current_usage":{"cache_read_input_tokens":40000,"cache_creation_input_tokens":2000}},"prompt_cache":{"warm":true,"cache_write_tokens":50000},"cost":{"total_cost_usd":0.5,"total_duration_ms":600000}}' | <the command from settings>
```

Expected: a first line starting with `Test · high │ ctx 42k / 200k` and a
second line starting with `cache 40k read · 2k write`. On Windows use
PowerShell's `echo` or write the JSON to a temp file and redirect it in.

Then delete the verify state file so it does not linger:
`~/.claude/statusline-state/verify.json`.

### 7. Report

Tell the human, in a few lines:

- where the script went and which settings file changed;
- that the bar appears after they restart Claude Code (or at the next message
  in a running session; if it does not show, restart);
- that they can tune it with environment variables (list from the **Tuning**
  section) or by editing the constants at the top of the script;
- that `--dump` on the command in settings logs every raw payload to
  `~/.claude/statusline-dump.jsonl` for debugging, and to remove it afterwards.

Do not offer to add more segments, colors, or features. The bar is intentionally
small.

---

## What the bar shows

Two lines. Colors mean "act"; the default state has no color.

```
Opus 4.1 · xhigh │ ctx 162k / 200k ▂▃▄▆▇ ⚠ >150k │ $4.87 · $4.12/h
cache 158k read · 4k write · 85k total · 🔥 3:42 (2:47pm)           campfire
```

**Line 1**

- Model display name, bold. Effort level; `xhigh`/`max` amber. `no-think`
  appears only when extended thinking is off. `fast` appears only in fast mode.
- `ctx <prompt tokens> / <window>`. Absolute tokens, not percent, so the number
  means the same on a 200k and a 1M model. Amber once past the smart zone
  (150k by default) with a `⚠ >150k` tag. Red past 90% of the window.
- Sparkline of the last 12 context sizes for this session, and `cN` if N
  compactions were detected (a drop of more than 40%).
- Session cost and cost per wall-clock hour (after the first minute).

**Line 2**

- `cache <read> read · <write> write` are the last API call's cache-read and
  cache-creation tokens. Write is the expensive one: amber above 8k, red above
  30k.
- `<n> total` is session-wide cache-write tokens, dimmed.
- `🔥 m:ss (h:mmpm)` counts down until the prompt cache goes cold and shows
  the local wall-clock time it happens; amber under a minute. On native
  Windows (no refresh timer) it is `🔥 until h:mmpm` with no countdown. `cold`
  means the next turn will re-write the whole prompt.
- Right-aligned label: repo name when Claude Code detected a git repo, else
  `P4CLIENT` from the environment or a `.p4config` found walking up from the
  current directory, else the folder name. File reads only. It never runs
  `git` or `p4`.

**Deliberately absent:** rate limits, PR state, git dirty/ahead/behind,
Perforce opened files, cache hit percent. The script spawns no subprocesses.

## Tuning

Environment variables, read at each refresh. Set them in the shell that
launches Claude Code, or edit the constants at the top of the script.

| Variable | Default | Meaning |
|---|---|---|
| `CC_STATUS_LINES` | `2` | `1` for a single-line bar |
| `CC_STATUS_ASCII` | `0` | `1` for no emoji or box-drawing characters |
| `CC_STATUS_SMART_ZONE` | `150000` | context tokens where the amber warning starts |
| `CC_STATUS_WRITE_WARN` | `8000` | last-call cache-write tokens for amber |
| `CC_STATUS_WRITE_BAD` | `30000` | last-call cache-write tokens for red |
| `CC_STATUS_SPARK` | `1` | `0` disables the sparkline and the state file |
| `CC_STATUS_COUNTDOWN` | `1` (`0` on Windows) | `0` shows `until h:mmpm` instead of a countdown |

Facts the design relies on, verified against Claude Code 2.1.263:
`cost.total_cost_usd` includes subagent usage and Claude Code's own housekeeping
calls; `prompt_cache.expires_at` is epoch seconds; the script is re-run on each
assistant message, after `/compact`, on mode changes, when the cache expiry
time is reached, and on the `refreshInterval` timer. On Windows the command is
launched through Git's `bash.exe`; never set `refreshInterval` there.

---

## Script

Write this to `statusline.py` exactly as shown.

```python
#!/usr/bin/env python3
"""Claude Code status line. Reads Claude Code's JSON on stdin, prints one or two lines.

Fields: https://code.claude.com/docs/en/statusline

Rules this script keeps:
  - No subprocesses. Ever. Pure JSON, one small state file, nothing else.
  - Every field may be missing or null. Missing prints as an em dash, never a fake zero.
  - Never crashes, never writes to stderr. A broken bar is worse than a blank one.
  - Portable: no jq, no bash. Runs on macOS, Linux, and Windows Python 3.8+.

Install (absolute path, forward slashes on every platform):
  { "statusLine": { "type": "command", "command": "python3 /abs/path/statusline.py" } }
On macOS/Linux add "refreshInterval": 1 for a live cache countdown. On native Windows do NOT set
refreshInterval: Claude Code launches this command through git's bash.exe, and timer-driven spawns pile up
behind slow shell work (e.g. a `find /`) until bash/sh/git crash machine-wide. Windows renders the cache
expiry as a clock time instead of a countdown, and the bar still updates on every message.

Debug:
  python3 statusline.py --demo          # render the built-in sample payloads
  python3 statusline.py --dump < json   # also append the raw payload to ~/.claude/statusline-dump.jsonl
"""
import json, os, sys, time
from datetime import datetime, timezone

# ----------------------------------------------------------------------------- config
# Environment variables override these so one shared file can be tuned per person.
SMART_ZONE_TOKENS = int(os.environ.get("CC_STATUS_SMART_ZONE", 150_000))  # absolute, same meaning on 200k and 1M models
CACHE_WRITE_WARN  = int(os.environ.get("CC_STATUS_WRITE_WARN", 8_000))    # last-call cache writes above this go amber
CACHE_WRITE_BAD   = int(os.environ.get("CC_STATUS_WRITE_BAD", 30_000))    # ...and above this go red
LINES             = int(os.environ.get("CC_STATUS_LINES", 2))             # 1 or 2
SPARKLINE         = os.environ.get("CC_STATUS_SPARK", "1") != "0"         # context history sparkline (needs state file)
ASCII             = os.environ.get("CC_STATUS_ASCII", "0") == "1"         # no emoji, no box-drawing
# Native Windows gets no refreshInterval (see the docstring), so a countdown would sit stale between
# messages. There the cache segment shows only the wall-clock expiry time. WSL is posix and keeps the countdown.
COUNTDOWN         = os.environ.get("CC_STATUS_COUNTDOWN", "0" if os.name == "nt" else "1") == "1"
SPARK_POINTS      = 12
STATE_DIR         = os.path.join(os.path.expanduser("~"), ".claude", "statusline-state")

# ----------------------------------------------------------------------------- glyphs
SEP   = " | "  if ASCII else " │ "
DOT   = " - "  if ASCII else " · "
WARN  = "!"    if ASCII else "⚠"
FLAME = "cache" if ASCII else "🔥"
BARS  = "_.-=#" if ASCII else "▁▂▃▄▅▆▇█"

# ----------------------------------------------------------------------------- ansi
def _c(code):
    return lambda s: f"\033[{code}m{s}\033[0m" if s else s
dim, red, amber, green, bold = _c("2"), _c("31"), _c("33"), _c("32"), _c("1")

# ----------------------------------------------------------------------------- helpers
def get(d, *path):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur

def isnum(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)

def k(n):
    """Token count as 12k / 1.2M / 987. Em dash when unknown."""
    if not isnum(n):
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.0f}k"
    return f"{n:.0f}"

def money(x):
    return f"${x:.2f}" if isnum(x) else "$—"

def epoch(v):
    """Accept epoch seconds, epoch ms, or ISO-8601. Return epoch seconds or None."""
    if isnum(v):
        return v / 1000 if v > 1e11 else v
    if isinstance(v, str) and v:
        try:
            s = v.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return None
    return None

def mmss(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"

def clock12(ts):
    """Epoch seconds -> local 12-hour time like 2:47pm. Portable (no %-I on Windows)."""
    try:
        lt = time.localtime(ts)
        h = lt.tm_hour % 12 or 12
        return f"{h}:{lt.tm_min:02d}{'am' if lt.tm_hour < 12 else 'pm'}"
    except Exception:
        return "?"

# ----------------------------------------------------------------------------- state (sparkline + turn tracking)
def load_state(session_id):
    if not session_id:
        return {}
    try:
        with open(os.path.join(STATE_DIR, f"{session_id}.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(session_id, state):
    if not session_id:
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, f"{session_id}.json"), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass

def update_history(state, ctx, size):
    """Append the current context size when it changed. Detect compaction as a large drop."""
    if not isnum(ctx):
        return state
    hist = state.get("ctx", [])
    if hist and hist[-1] == ctx:
        return state
    if hist and ctx < hist[-1] * 0.6 and hist[-1] > 20_000:
        state["compacts"] = state.get("compacts", 0) + 1
        state["since_compact"] = 0
    else:
        state["since_compact"] = state.get("since_compact", 0) + 1
    hist.append(ctx)
    state["ctx"] = hist[-SPARK_POINTS:]
    state["size"] = size if isnum(size) else state.get("size")
    return state

def sparkline(state):
    hist = state.get("ctx") or []
    size = state.get("size")
    if len(hist) < 2 or not isnum(size) or size <= 0:
        return ""
    out = []
    for v in hist:
        idx = min(len(BARS) - 1, int((v / size) * len(BARS)))
        out.append(BARS[idx])
    return "".join(out)

# ----------------------------------------------------------------------------- location label (zero subprocesses)
def find_p4client(start):
    """P4CLIENT from the environment, else from a .p4config found walking up from start."""
    env = os.environ.get("P4CLIENT")
    if env:
        return env
    names = [os.environ.get("P4CONFIG") or ".p4config", "p4config.txt"]
    cur = start or os.getcwd()
    for _ in range(40):
        for name in names:
            path = os.path.join(cur, name)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line.upper().startswith("P4CLIENT="):
                            return line.split("=", 1)[1].strip()
            except Exception:
                pass
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None

def location_label(d):
    repo = get(d, "workspace", "repo", "name")
    if repo:
        return repo
    cwd = get(d, "workspace", "current_dir") or get(d, "cwd")
    client = find_p4client(cwd)
    if client:
        return client
    return os.path.basename(cwd.rstrip("/\\")) if cwd else ""

# ----------------------------------------------------------------------------- segments
def seg_model(d):
    model = get(d, "model", "display_name") or "?"
    parts = [bold(model)]
    effort = get(d, "effort", "level")
    if effort:
        parts.append(amber(effort) if effort in ("xhigh", "max") else effort)
    if get(d, "thinking", "enabled") is False:
        parts.append(dim("no-think"))
    if get(d, "fast_mode") is True:
        parts.append(amber("fast"))
    agent = get(d, "agent", "name")
    if agent:
        parts.append(dim(f"@{agent}"))
    return DOT.join(parts)

def seg_context(d, state):
    ctx  = get(d, "context_window", "total_input_tokens")   # whole prompt of the last call, cache included
    size = get(d, "context_window", "context_window_size")
    pct  = get(d, "context_window", "used_percentage")
    text = f"ctx {k(ctx)} / {k(size)}"
    color = None
    if isnum(pct) and pct >= 90:
        color = red
    elif isnum(ctx) and ctx >= SMART_ZONE_TOKENS:
        color = amber
    if color:
        text = color(text)
    extras = []
    if SPARKLINE:
        s = sparkline(state)
        if s:
            extras.append(dim(s))
    if isnum(ctx) and ctx >= SMART_ZONE_TOKENS:
        extras.append((red if color is red else amber)(f"{WARN} >{k(SMART_ZONE_TOKENS)}"))
    if state.get("compacts"):
        extras.append(dim(f"c{state['compacts']}"))
    return " ".join([text] + extras)

def seg_cost(d):
    cost = get(d, "cost", "total_cost_usd")
    dur  = get(d, "cost", "total_duration_ms")
    text = money(cost)
    if isnum(cost) and isnum(dur) and dur > 60_000:
        text += DOT + f"{money(cost / (dur / 3_600_000))}/h"
    return text

def seg_cache(d, now):
    read  = get(d, "context_window", "current_usage", "cache_read_input_tokens")
    write = get(d, "context_window", "current_usage", "cache_creation_input_tokens")
    total = get(d, "prompt_cache", "cache_write_tokens")
    warm  = get(d, "prompt_cache", "warm")
    exp   = epoch(get(d, "prompt_cache", "expires_at"))

    w = f"{k(write)} write"
    if isnum(write):
        w = red(w) if write >= CACHE_WRITE_BAD else amber(w) if write >= CACHE_WRITE_WARN else w
    parts = [f"cache {k(read)} read", w]
    if isnum(total):
        parts.append(dim(f"{k(total)} total"))

    if warm and exp:
        left = exp - now
        if left > 0:
            t = f"{FLAME} {mmss(left)} ({clock12(exp)})" if COUNTDOWN else f"{FLAME} until {clock12(exp)}"
            parts.append(green(t) if left > 60 else amber(t))
        else:
            parts.append(dim("cold"))
    elif warm is True:
        parts.append(green("warm"))
    elif warm is False:
        parts.append(dim("cold"))
    return DOT.join(parts)

# ----------------------------------------------------------------------------- layout
def visible_len(s):
    out, i = 0, 0
    while i < len(s):
        if s[i] == "\033":
            j = s.find("m", i)
            i = (j + 1) if j != -1 else len(s)
            continue
        out += 2 if ord(s[i]) > 0x1F000 else 1   # emoji are double width
        i += 1
    return out

def render(d, now=None):
    now = now if now is not None else time.time()
    session = get(d, "session_id")
    state = load_state(session)
    state = update_history(state,
                           get(d, "context_window", "total_input_tokens"),
                           get(d, "context_window", "context_window_size"))
    save_state(session, state)

    cols = 0
    try:
        cols = int(os.environ.get("COLUMNS") or 0)
    except Exception:
        pass

    label = dim(location_label(d))
    line1 = SEP.join([seg_model(d), seg_context(d, state), seg_cost(d)])
    line2 = seg_cache(d, now)

    if LINES == 1:
        one = SEP.join([line1, line2])
        if label and (not cols or visible_len(one) + visible_len(label) + 3 <= cols):
            one += SEP + label
        return one

    if label:
        pad = cols - visible_len(line2) - visible_len(label) if cols else 0
        line2 = line2 + (" " * pad if pad >= 2 else SEP) + label
    return line1 + "\n" + line2

# ----------------------------------------------------------------------------- demo payloads
DEMOS = {
    "home, warm cache, past smart zone": {
        "model": {"display_name": "Opus 4.1"}, "effort": {"level": "xhigh"}, "thinking": {"enabled": True},
        "session_id": "demo-1", "workspace": {"current_dir": "/Users/jeff/src/campfire", "repo": {"name": "campfire"}},
        "context_window": {"total_input_tokens": 162_400, "context_window_size": 200_000, "used_percentage": 81,
                           "current_usage": {"cache_read_input_tokens": 158_000, "cache_creation_input_tokens": 4_400}},
        "prompt_cache": {"warm": True, "expires_at": None, "cache_write_tokens": 84_921, "hit_ratio": 0.91},
        "cost": {"total_cost_usd": 4.87, "total_duration_ms": 71 * 60_000},
        "rate_limits": {"five_hour": {"used_percentage": 40}},
    },
    "work, p4, cold cache, big write": {
        "model": {"display_name": "Sonnet 5"}, "effort": {"level": "high"}, "thinking": {"enabled": True},
        "session_id": "demo-2", "workspace": {"current_dir": "C:/p4/jeff_ws/tools/pipeline"},
        "context_window": {"total_input_tokens": 84_000, "context_window_size": 1_000_000, "used_percentage": 8,
                           "current_usage": {"cache_read_input_tokens": 0, "cache_creation_input_tokens": 84_000}},
        "prompt_cache": {"warm": False, "cache_write_tokens": 190_000},
        "cost": {"total_cost_usd": 0.87, "total_duration_ms": 18 * 60_000},
    },
    "post-compact nulls": {
        "model": {"display_name": "Opus 4.1"}, "effort": {"level": "medium"}, "session_id": "demo-3",
        "workspace": {"current_dir": "/work/projects"},
        "context_window": {"total_input_tokens": None, "context_window_size": 200_000, "used_percentage": None, "current_usage": None},
        "prompt_cache": None, "cost": {"total_cost_usd": 12.10, "total_duration_ms": 3 * 3_600_000},
    },
    "garbage": None,
}

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if "--demo" in sys.argv:
        now = time.time()
        for name, payload in DEMOS.items():
            if payload and payload.get("prompt_cache") and payload["prompt_cache"].get("warm"):
                payload["prompt_cache"]["expires_at"] = int(now + 222)  # epoch seconds, as the CLI emits it
            print(f"--- {name}")
            print(render(payload if payload else {}, now))
            print()
        return

    raw = sys.stdin.read()
    try:
        d = json.loads(raw)
        if not isinstance(d, dict):
            d = {}
    except Exception:
        d = {}

    if "--dump" in sys.argv:
        try:
            with open(os.path.join(os.path.expanduser("~"), ".claude", "statusline-dump.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": time.time(), "payload": d}) + "\n")
        except Exception:
            pass

    print(render(d))

if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("statusline: error")   # never crash, never stderr
```
