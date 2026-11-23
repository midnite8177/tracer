#!/usr/bin/env python3
"""jidoka's context report. Measures what loads into a Claude Code session in
this repo and what each jidoka skill pulls in when invoked. No LLM involved.

Under a T3 Antigravity session, which routes.host_of_environment decides, nothing records what loaded, so the report
computes it from files. The rules are the GEMINI.md and AGENTS.md of each folder from the cwd up to the repo root and the
files of .agents/rules, each counted to at most 24 KB and all of them to 20k tokens. The plugins are the ones the
profile's config.json enables among those in its plugins folder. The SessionStart output is what the profile copy's own
hook prints when run with an Antigravity payload, `bd prime` included. CLAUDE.md is reported as not loaded, and the
skills are named as the profile copy names them, with the `jidoka-` prefix.

Usage:
  context.py                      the report
  context.py --min N              hide rows under N KB (default 1)
  context.py --scripts <folder>   the plugin's scripts folder, which holds routes.py; the plugin's own when left out

Token figures are estimates (bytes / 4); real counts vary by content.
"""
import glob, json, os, re, shutil, signal, subprocess, sys
from dataclasses import dataclass
from pathlib import Path
if hasattr(signal, "SIGPIPE"): signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # quiet exit when piped; absent on Windows
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")            # Windows consoles default to cp1252
except Exception: pass

HOME = os.path.expanduser("~")
ROOT = os.path.normpath(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip() or os.getcwd())
INSTALLED_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
BENCH_SKILLS = ("bench", "tdd", "unslop", "spec-check", "no-comments")
WARN_BYTES, WARN_LINES = 16 * 1024, 200
CMD_TIMEOUT_SECONDS = 20
# Folders above git that can be the Git for Windows root: <Git>/cmd/git.exe is one below it, <Git>/mingw64/bin/git.exe two.
GIT_FOLDERS_ABOVE_GIT = 3
BYTES_PER_TOKEN = 4
RULE_FILE_CAP_BYTES = 24 * 1024
RULE_BUDGET_BYTES = 20_000 * BYTES_PER_TOKEN
RULE_FILE_NAMES = ("GEMINI.md", "AGENTS.md")
ANTIGRAVITY_SKILL_PREFIX = "jidoka-"
ANTIGRAVITY_SESSION_START = {"cwd": ROOT, "workspacePaths": [ROOT], "hook_event_name": "SessionStart", "source": "startup"}
HOOK_LABEL = "jidoka SessionStart hook"
NO_SH = "no sh on the PATH or in the usr/bin of the Git for Windows that holds git"
NOT_MEASURABLE = "Not measurable here: the system prompt and tool definitions (tens of thousands of tokens, fixed), and the conversation itself."
LIVE_BREAKDOWN = " Run /context inside a session for the live breakdown."

def scripts_folder(argv):
    """The plugin's scripts folder, which holds routes.py: the one --scripts names, else the folder of the plugin this
    file sits in. A skill's copy in a T3 profile holds no scripts, so its SKILL.md names the folder."""
    return argv[argv.index("--scripts") + 1] if "--scripts" in argv else str(Path(__file__).resolve().parents[2] / "scripts")

sys.path.append(scripts_folder(sys.argv[1:]))
import claude_project, routes, t3_profiles

@dataclass
class Report:
    """What one host's report holds, which main prints the same way for every host: the rows of each table, the lines
    that come before the startup table and after it, the slash command that runs bench, and the closing note."""
    startup: list
    bench: list
    invoke: list
    preface: list
    after_startup: list
    bench_command: str
    closing: str

def measured(data):
    """Size and line count of bytes."""
    return len(data), data.count(b"\n") + (0 if not data or data.endswith(b"\n") else 1)

def size(path):
    try:
        with open(path, "rb") as fh: data = fh.read()
    except OSError: return None
    return measured(data)

def measured_all(paths):
    """Size and line count of the readable files among paths, added together."""
    sizes = [s for s in map(size, paths) if s is not None]
    return sum(s[0] for s in sizes), sum(s[1] for s in sizes)

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
    """Claude Code auto-memory dir for this repo: the memory folder of the project folder claude_project names. None
    when the repo has no project folder or the folder has no memory."""
    project = claude_project.folder_of(Path(HOME, ".claude", "projects"), ROOT)
    memory = project / "memory" if project else None
    return str(memory) if memory and memory.is_dir() else None

def shell(label):
    """The sh that runs jidoka's hooks: the first on the PATH, else the usr/bin/sh.exe of the Git for Windows that
    holds git. None, after a line on stderr that names the row of the label, when there is neither."""
    found = shutil.which("sh")
    if found: return found
    git = shutil.which("git")
    for folder in list(Path(git).parents)[:GIT_FOLDERS_ABOVE_GIT] if git else []:
        candidate = folder / "usr" / "bin" / "sh.exe"
        if candidate.is_file(): return str(candidate)
    print(f"context: {label}: {NO_SH}", file=sys.stderr)
    return None

def cmd_output(args, stdin, label):
    """What the command prints, or None when it cannot be measured. A label names the row on stderr, with the command
    and why it could not be measured; None keeps the failure quiet."""
    def fail(why):
        if label: print(f"context: {label}: {' '.join(args)}: {why}", file=sys.stderr)
        return None
    try: done = subprocess.run(args, input=stdin.encode("utf-8"), capture_output=True, timeout=CMD_TIMEOUT_SECONDS, cwd=ROOT)
    except subprocess.TimeoutExpired: return fail(f"no answer in {CMD_TIMEOUT_SECONDS} seconds")
    except OSError as e: return fail(f"did not start: {e}")
    if done.returncode != 0:
        return fail(f"exit code {done.returncode}, stderr: {done.stderr.decode('utf-8', errors='replace').strip()}")
    return done.stdout

def cmd_bytes(args, stdin, label):
    """Size and line count of what the command prints, or None when it cannot be measured."""
    out = cmd_output(args, stdin, label)
    return None if out is None else (len(out), out.count(b"\n") + 1)

def hook_measure():
    sh = shell(HOOK_LABEL)
    if sh is None: return None
    runner = Path(INSTALLED_PLUGIN_ROOT, "bin", "jidoka-run").as_posix()
    hook = Path(INSTALLED_PLUGIN_ROOT, "hooks", "session_start.py").as_posix()
    return cmd_bytes([sh, runner, hook], json.dumps({"cwd": ROOT, "hook_event_name": "SessionStart", "source": "startup"}), HOOK_LABEL)

def add(rows, label, path=None, measured=None):
    """Appends the row of a file, or of the size and line count measured, to rows; a file that cannot be read and a
    measure that is None add none."""
    m = measured if measured is not None else (size(path) if path else None)
    if m is None: return
    rows.append((label, m[0], m[1]))

def claude_code_startup_rows():
    rows = []
    for p in [os.path.join(HOME, ".claude", "CLAUDE.md")] + sorted(glob.glob(os.path.join(HOME, ".claude", "rules", "**", "*.md"), recursive=True)):
        add(rows, "~" + p[len(HOME):], p)
    seen = set()
    for name in ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"):
        p = os.path.join(ROOT, name)
        if os.path.isfile(p) and p not in seen:
            seen.add(p); add(rows, name, p)
            for imp in imports_of(p):
                if imp not in seen: seen.add(imp); add(rows, "  ↳ " + os.path.relpath(imp, ROOT), imp)
    for p in sorted(glob.glob(os.path.join(ROOT, ".claude", "rules", "**", "*.md"), recursive=True)):
        add(rows, os.path.relpath(p, ROOT), p)
    md = memory_dir()
    if md:
        idx = os.path.join(md, "MEMORY.md")
        if os.path.isfile(idx):
            m = size(idx); add(rows, "auto-memory MEMORY.md (first 200 lines / 25 KB load)", measured=(min(m[0], 25 * 1024), min(m[1], 200)))
    add(rows, "bd prime (SessionStart hook output)", measured=cmd_bytes(["bd", "prime"], "", None))
    add(rows, "jidoka SessionStart hook output", measured=hook_measure())
    return rows

def folders_up_to_root():
    """The folders from the cwd up to the repo root, nearest first; the root alone when the cwd is not inside it."""
    cwd, root = Path(os.getcwd()).resolve(), Path(ROOT).resolve()
    chain = [cwd, *cwd.parents]
    return chain[:chain.index(root) + 1] if root in chain else [root]

def rule_files():
    """The files Antigravity reads as rules, in the order the budget is spent: GEMINI.md and AGENTS.md of each folder
    from the cwd up to the repo root, then the markdown files of the root's .agents/rules."""
    named = [folder / name for folder in folders_up_to_root() for name in RULE_FILE_NAMES]
    ruled = sorted(Path(ROOT, ".agents", "rules").glob("**/*.md"))
    return [path for path in named + ruled if path.is_file()]

def rule_rows():
    """One row for each rule file with what counts of it: at most 24 KB of the file, and only what is left of the 20k
    tokens that all the rules share, so a file past the budget counts as nothing."""
    left, found = RULE_BUDGET_BYTES, []
    for path in rule_files():
        try: data = path.read_bytes()
        except OSError: continue
        counted, notes = data[:RULE_FILE_CAP_BYTES], []
        if len(data) > RULE_FILE_CAP_BYTES: notes.append(f"capped at {RULE_FILE_CAP_BYTES // 1024} KB")
        if len(counted) > left:
            counted = counted[:left]
            notes.append(f"cut to the {RULE_BUDGET_BYTES // BYTES_PER_TOKEN // 1000}k-token rule budget")
        left -= len(counted)
        label = os.path.relpath(path, ROOT) + (f" ({', '.join(notes)})" if notes else "")
        found.append((label, *measured(counted)))
    return found

def antigravity_profile():
    """The profile whose jidoka copy holds this script, else the first profile that holds a jidoka copy. None when no
    profile holds one."""
    here = Path(os.path.realpath(__file__))
    profiles = t3_profiles.profiles_with_a_copy()
    mine = [profile for profile in profiles if t3_profiles.copy_in(profile).resolve() in here.parents]
    return (mine or profiles or [None])[0]

def plugins_enabled_in(profile):
    """The plugins whose folder is in the profile's plugins folder and whose entry in config.json says enabled, each
    with the number of skills it carries."""
    try: held = json.loads(Path(profile, "config", "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): return []
    entries = held.get("plugins") if isinstance(held, dict) else None
    if not isinstance(entries, dict): return []
    found = []
    for name, entry in sorted(entries.items()):
        folder = Path(profile, "config", "plugins", name)
        if isinstance(entry, dict) and entry.get("enabled") is True and folder.is_dir():
            found.append((name, len(list(folder.glob("skills/*/SKILL.md")))))
    return found

def injected_text(out):
    """The system message of an Antigravity SessionStart answer, which is the text that loads into the session; the
    output itself when it is not that answer."""
    try:
        steps = json.loads(out.decode("utf-8")).get("injectSteps")
        return "".join(step["systemMessage"]["systemMessage"] for step in steps).encode("utf-8")
    except (ValueError, AttributeError, KeyError, TypeError): return out

def profile_hook_measure(copy):
    """Size and line count of what the profile copy's SessionStart hooks print when run with an Antigravity payload,
    or None when the copy names no such hook or one of them cannot be run."""
    try: held = json.loads(Path(copy, "hooks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): held = None
    handlers = held.get("jidoka", {}).get("SessionStart") if isinstance(held, dict) and isinstance(held.get("jidoka"), dict) else None
    commands = [h["command"] for h in handlers or [] if isinstance(h, dict) and isinstance(h.get("command"), str)]
    if not commands:
        print(f"context: {HOOK_LABEL}: {Path(copy, 'hooks.json')} names no SessionStart hook", file=sys.stderr)
        return None
    sh = shell(HOOK_LABEL)
    if sh is None: return None
    printed = [cmd_output([sh, "-c", command], json.dumps(ANTIGRAVITY_SESSION_START), HOOK_LABEL) for command in commands]
    if None in printed: return None
    text = b"".join(injected_text(out) for out in printed)
    return len(text), text.count(b"\n") + 1

def repo_doc_rows():
    """The rows of the repo's own glossary, context and ADR files, which a bench session reads."""
    rows = []
    for name in ("GLOSSARY.md", "GLOSSARY-MAP.md", "CONTEXT.md", "CONTEXT-MAP.md"):
        add(rows, name, os.path.join(ROOT, name))
    for p in sorted(glob.glob(os.path.join(ROOT, "src", "*", "GLOSSARY.md")) + glob.glob(os.path.join(ROOT, "src", "*", "CONTEXT.md"))): add(rows, os.path.relpath(p, ROOT), p)
    adrs = sorted(glob.glob(os.path.join(ROOT, "docs", "adr", "*.md")))
    if adrs: add(rows, f"docs/adr/*.md ({len(adrs)} files, read as relevant)", measured=measured_all(adrs))
    return rows

def bench_rows(plugin_root, prefix):
    """The rows of the bench section: the repo's docs, jidoka's tracker and domain docs from the plugin at plugin_root,
    and the skills bench loads, whose folders and names start with prefix."""
    rows = repo_doc_rows()
    add(rows, "tracker doc (jidoka docs/issue-tracker.md)", os.path.join(plugin_root, "docs", "issue-tracker.md"))
    add(rows, "domain doc (jidoka docs/domain.md)", os.path.join(plugin_root, "docs", "domain.md"))
    for sk in BENCH_SKILLS:
        d = os.path.join(plugin_root, "skills", prefix + sk)
        files = sorted(glob.glob(os.path.join(d, "*.md")))
        if files: add(rows, f"skill {prefix}{sk} ({len(files)} files)", measured=measured_all(files))
    return rows

def skill_rows(plugin_root):
    """One row for each skill of the plugin at plugin_root, with the markdown files of its folder."""
    rows = []
    for d in sorted(glob.glob(os.path.join(plugin_root, "skills", "*"))):
        files = sorted(glob.glob(os.path.join(d, "*.md")))
        if files: add(rows, os.path.basename(d), measured=measured_all(files))
    return rows

def fill_claude_code():
    """The report for a Claude Code session, from the files Claude Code loads and the plugin this script sits in."""
    return Report(startup=claude_code_startup_rows(), bench=bench_rows(INSTALLED_PLUGIN_ROOT, ""),
                  invoke=skill_rows(INSTALLED_PLUGIN_ROOT), preface=[], after_startup=[],
                  bench_command=routes.slash_command("bench"), closing=NOT_MEASURABLE + LIVE_BREAKDOWN)

def fill_antigravity():
    """The report for a T3 Antigravity session, from the files of the profile and the repo."""
    profile = antigravity_profile()
    claude_md = size(os.path.join(ROOT, "CLAUDE.md"))
    not_loaded = ["CLAUDE.md" + (f" ({claude_md[0] / 1024:.1f} KB in this repo)" if claude_md else "") + ": Antigravity reads GEMINI.md and AGENTS.md, not CLAUDE.md",
                  "A SessionStart hook in ~/.gemini never reaches a T3 session; jidoka's hook runs from the T3 profile"]
    report = Report(startup=rule_rows(), bench=[], invoke=[],
                    preface=["T3 Antigravity session, computed from files: nothing records what loaded" + (f"; profile {profile}" if profile else "")],
                    after_startup=["\nNot loaded here", *[f"  {line}" for line in not_loaded]],
                    bench_command=routes.slash_command("bench"), closing=NOT_MEASURABLE)
    plugins = []
    if profile is None:
        print(f"context: no T3 Antigravity profile under {t3_profiles.profiles_folder()} holds a jidoka copy, so the plugins, the SessionStart output and the skills are not measured", file=sys.stderr)
    else:
        copy = t3_profiles.copy_in(profile)
        plugins = plugins_enabled_in(profile)
        add(report.startup, "jidoka SessionStart hook output (bd prime included)", measured=profile_hook_measure(copy))
        report.bench = bench_rows(str(copy), ANTIGRAVITY_SKILL_PREFIX)
        report.invoke = skill_rows(str(copy))
    report.after_startup += [f"\nPlugins enabled in the profile's config.json   {len(plugins)}",
                             *[f"  {name}  ({skills} skills)" for name, skills in plugins]]
    return report

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
    report = (fill_antigravity if routes.host_of_environment() == routes.ANTIGRAVITY_HOST else fill_claude_code)()
    print(f"context for {ROOT}")
    for line in report.preface: print(line)
    fmt(report.startup, "Loads every session, before you type anything", None, minkb)
    for line in report.after_startup: print(line)
    fmt(report.bench, f"Added when {report.bench_command} runs (plus the bead itself and any files it opens)", None, minkb)
    fmt(report.invoke, "Each skill, loaded only when invoked", "for reference; not part of startup", minkb)
    print(f"\n⚠ = over {WARN_BYTES//1024} KB or {WARN_LINES} lines. Tokens are bytes/4, an estimate.")
    print(report.closing)
