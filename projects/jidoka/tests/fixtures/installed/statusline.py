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
