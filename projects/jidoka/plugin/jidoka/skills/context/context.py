#!/usr/bin/env python3
"""jidoka's context report. Measures what loads into a Claude Code session in
this repo and what each jidoka skill pulls in when invoked. No LLM involved.

Usage:
  context.py            the report
  context.py --min N    hide rows under N KB (default 1)

Token figures are estimates (bytes / 4); real counts vary by content.
"""
import glob, json, os, re, signal, subprocess, sys
if hasattr(signal, "SIGPIPE"): signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # quiet exit when piped; absent on Windows
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")            # Windows consoles default to cp1252
except Exception: pass

HOME = os.path.expanduser("~")
ROOT = os.path.normpath(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or os.getcwd())
INSTALLED_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
BENCH_SKILLS = ("bench", "tdd", "unslop", "spec-check", "no-comments")
WARN_BYTES, WARN_LINES = 16 * 1024, 200

def size(path):
    try:
        with open(path, "rb") as fh: data = fh.read()
    except OSError: return None
    return len(data), data.count(b"\n") + (0 if not data or data.endswith(b"\n") else 1)

def imports_of(path):
    """@path imports in a CLAUDE.md-style file, resolved relative to that file."""
    out = []
    try: text = open(path, encoding="utf-8", errors="replace").read()
    except OSError: return out
    text = re.sub(r"```.*?```", "", text, flags=re.S); text = re.sub(r"`[^`\n]*`", "", text)
    for m in re.finditer(r"(?<![\w/])@(~?[\w./-]+)", text):
        p = os.path.expanduser(m.group(1))
        if not os.path.isabs(p): p = os.path.join(os.path.dirname(path), p)
        if os.path.isfile(p): out.append(p)
    return out

def memory_dir():
    """Claude Code auto-memory dir for this repo: ~/.claude/projects/<encoded path>/memory.

    Claude Code names the folder after the repo path with every character other
    than a letter or digit turned into "-". The match ignores case because
    macOS and Windows paths do.
    """
    enc = re.sub(r"[^A-Za-z0-9]", "-", ROOT).strip("-")
    cands = [d for d in glob.glob(os.path.join(HOME, ".claude", "projects", "*", "memory"))
             if os.path.basename(os.path.dirname(d)).strip("-").lower() == enc.lower()]
    return cands[0] if cands else None

def cmd_bytes(args, stdin):
    try:
        out = subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=20, cwd=ROOT).stdout
        return len(out.encode()), out.count("\n") + 1
    except Exception: return None

rows = {"startup": [], "invoke": [], "bench": []}

def add(group, label, path=None, measured=None):
    m = measured if measured is not None else (size(path) if path else None)
    if m is None: return
    rows[group].append((label, m[0], m[1]))

for p in [os.path.join(HOME, ".claude", "CLAUDE.md")] + sorted(glob.glob(os.path.join(HOME, ".claude", "rules", "**", "*.md"), recursive=True)):
    add("startup", "~" + p[len(HOME):], p)
seen = set()
for name in ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"):
    p = os.path.join(ROOT, name)
    if os.path.isfile(p) and p not in seen:
        seen.add(p); add("startup", name, p)
        for imp in imports_of(p):
            if imp not in seen: seen.add(imp); add("startup", "  ↳ " + os.path.relpath(imp, ROOT), imp)
for p in sorted(glob.glob(os.path.join(ROOT, ".claude", "rules", "**", "*.md"), recursive=True)):
    add("startup", os.path.relpath(p, ROOT), p)
md = memory_dir()
if md:
    idx = os.path.join(md, "MEMORY.md")
    if os.path.isfile(idx):
        m = size(idx); add("startup", "auto-memory MEMORY.md (first 200 lines / 25 KB load)", measured=(min(m[0], 25 * 1024), min(m[1], 200)))
add("startup", "bd prime (SessionStart hook output)", measured=cmd_bytes(["bd", "prime"], ""))
add("startup", "jidoka SessionStart hook output", measured=cmd_bytes(
    ["sh", os.path.join(INSTALLED_PLUGIN_ROOT, "bin", "jidoka-run"), os.path.join(INSTALLED_PLUGIN_ROOT, "hooks", "session_start.py")],
    json.dumps({"cwd": ROOT, "hook_event_name": "SessionStart", "source": "startup"})))

for name in ("GLOSSARY.md", "GLOSSARY-MAP.md", "CONTEXT.md", "CONTEXT-MAP.md"):
    add("bench", name, os.path.join(ROOT, name))
for p in sorted(glob.glob(os.path.join(ROOT, "src", "*", "GLOSSARY.md")) + glob.glob(os.path.join(ROOT, "src", "*", "CONTEXT.md"))): add("bench", os.path.relpath(p, ROOT), p)
adrs = sorted(glob.glob(os.path.join(ROOT, "docs", "adr", "*.md")))
if adrs:
    tot = [size(p) for p in adrs]; add("bench", f"docs/adr/*.md ({len(adrs)} files, read as relevant)", measured=(sum(x[0] for x in tot), sum(x[1] for x in tot)))
add("bench", "tracker doc (jidoka docs/issue-tracker.md)", os.path.join(INSTALLED_PLUGIN_ROOT, "docs", "issue-tracker.md"))
add("bench", "domain doc (jidoka docs/domain.md)", os.path.join(INSTALLED_PLUGIN_ROOT, "docs", "domain.md"))
for sk in BENCH_SKILLS:
    d = os.path.join(INSTALLED_PLUGIN_ROOT, "skills", sk)
    files = sorted(glob.glob(os.path.join(d, "*.md")))
    if files:
        tot = [size(p) for p in files]; add("bench", f"skill {sk} ({len(files)} files)", measured=(sum(x[0] for x in tot), sum(x[1] for x in tot)))

for d in sorted(glob.glob(os.path.join(INSTALLED_PLUGIN_ROOT, "skills", "*"))):
    files = sorted(glob.glob(os.path.join(d, "*.md")))
    if not files: continue
    tot = [size(p) for p in files]; add("invoke", os.path.basename(d), measured=(sum(x[0] for x in tot), sum(x[1] for x in tot)))

def fmt(rows_, title, note, minkb):
    rows_ = sorted(rows_, key=lambda r: -r[1])
    total = sum(r[1] for r in rows_)
    print(f"\n{title}   ~{total//1024} KB ≈ {total//4:,} tokens")
    if note: print(f"  {note}")
    for label, b, lines in rows_:
        if b < minkb * 1024 and not label.startswith("  ↳"): continue
        flag = "  ⚠" if (b > WARN_BYTES or lines > WARN_LINES) else ""
        print(f"  {b/1024:6.1f} KB  {lines:5d} lines  ≈{b//4:6,} tok  {label}{flag}")
    hidden = sum(1 for r in rows_ if r[1] < minkb * 1024)
    if hidden: print(f"  ({hidden} smaller than {minkb} KB hidden; --min 0 shows all)")

if __name__ == "__main__":
    a = sys.argv[1:]; minkb = 1
    if "--min" in a: minkb = float(a[a.index("--min") + 1])
    print(f"context for {ROOT}")
    fmt(rows["startup"], "Loads every session, before you type anything", None, minkb)
    fmt(rows["bench"], "Added when /jidoka:bench runs (plus the bead itself and any files it opens)", None, minkb)
    fmt(rows["invoke"], "Each skill, loaded only when invoked", "for reference; not part of startup", minkb)
    print(f"\n⚠ = over {WARN_BYTES//1024} KB or {WARN_LINES} lines. Tokens are bytes/4, an estimate.")
    print("Not measurable here: the system prompt and tool definitions (tens of thousands of tokens, fixed), and the conversation itself. Run /context inside a session for the live breakdown.")
