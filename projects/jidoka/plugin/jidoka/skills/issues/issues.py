#!/usr/bin/env python3
"""Issues board. Deterministic rendering of beads; no LLM involved.

Usage:
  issues.py                 board: epics collapsed, first N ready beads
  issues.py --all           board with every open bead listed under its epic
  issues.py <epic-id>       one epic, all its open children
  issues.py <bead-id>       issue page for one bead
  issues.py --label <name>  board filtered to one label (also: label:<name>);
                            human and bench work as bare shortcuts
  issues.py --labels        every label in use on open beads, with counts
  issues.py <words...>      search: open beads whose title, description or labels
                            contain every word (case-insensitive), grouped by epic
  issues.py --limit N       how many ready beads to list on the board (default 8)
  issues.py --demo          include each bead's Demo text (default: a ✓ marks that one exists)
  issues.py --doctor        print the raw JSON keys bd returns, for field mapping

Field names differ between bd versions. The FIELD table below lists the
names this script tries, in order; --doctor shows what your bd emits.
"""
import json, re, signal, subprocess, sys
if hasattr(signal, "SIGPIPE"): signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # quiet exit when piped; absent on Windows
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")            # Windows consoles default to cp1252
except Exception: pass

FIELD = {
    "id":       ["id"],
    "title":    ["title"],
    "status":   ["status"],
    "type":     ["issue_type", "type"],
    "priority": ["priority"],
    "assignee": ["assignee", "owner"],
    "labels":   ["labels"],
    "parent":   ["parent", "parent_id"],
    "desc":     ["description"],
    "accept":   ["acceptance_criteria", "acceptance"],
    "notes":    ["notes"],
    "deps":     ["dependencies", "deps"],
    "comments": ["comments"],
}

def bd(*args):
    try:
        out = subprocess.run(["bd", *args, "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"bd {' '.join(args)} failed: {e.stderr.strip()}\n"); return []
    except FileNotFoundError:
        sys.stderr.write("bd not found on PATH\n"); sys.exit(1)
    out = out.strip()
    if not out: return []
    data = parse_json_or_json_lines(out)
    if isinstance(data, dict):
        for k in ("issues", "items", "results", "data"):
            if k in data and isinstance(data[k], list): return data[k]
        return [data]
    return data

def parse_json_or_json_lines(out):
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return [json.loads(l) for l in out.splitlines() if l.strip().startswith("{")]

def f(obj, key, default=None):
    for name in FIELD[key]:
        if name in obj and obj[name] not in (None, ""): return obj[name]
    return default

def labels(b):
    l = f(b, "labels", []) or []
    return [x if isinstance(x, str) else x.get("name", str(x)) for x in l]

def parent_of(b):
    p = f(b, "parent")
    if isinstance(p, dict): p = p.get("id")
    if p: return p
    for d in f(b, "deps", []) or []:
        if isinstance(d, dict) and d.get("type") in ("parent-child", "parent"):
            return d.get("depends_on_id") or d.get("to") or d.get("id")
    return None

def demo_line(b):
    desc = f(b, "desc", "") or ""
    m = re.search(r"^##\s*Demo\s*\n(.+?)(?:\n\s*\n|\n##|\Z)", desc, re.S | re.M)
    return " ".join(m.group(1).split()) if m else ""

def section(desc, name):
    m = re.search(rf"^##\s*{name}\s*\n(.+?)(?:\n##|\Z)", desc or "", re.S | re.M)
    return m.group(1).strip() if m else ""

def k(n): return f"{n/1000:.0f}k" if isinstance(n, (int, float)) and n >= 1000 else str(n)

def load():
    open_ = bd("list", "--status=open") + bd("list", "--status=in_progress")
    ready = {f(b, "id") for b in bd("ready")}
    blocked = {}
    for b in bd("blocked"):
        bl = b.get("blocked_by") or b.get("blockers") or b.get("blocked_by_ids") or []
        blocked[f(b, "id")] = [x if isinstance(x, str) else (x.get("id") or x.get("title")) for x in bl]
    by_id = {f(b, "id"): b for b in open_}
    return by_id, ready, blocked

NEEDS_YOU = ("human", "bench")

def needs_you(b):
    return any(l in NEEDS_YOU for l in labels(b))

def status_of(b, ready, blocked, by_id):
    bid = f(b, "id"); st = f(b, "status", "")
    if needs_you(b): return "needs you"
    if st == "deferred": return "deferred"
    if st == "in_progress": return f"in progress ({f(b, 'assignee', '?')})"
    if bid in ready: return "ready"
    if bid in blocked:
        names = [f(by_id[x], "title", x) if x in by_id else x for x in blocked[bid]]
        return "blocked by " + ", ".join(names[:2]) + (" +%d" % (len(names) - 2) if len(names) > 2 else "")
    return st or "open"

SHOW_DEMO = False

def line(b, ready, blocked, by_id):
    d = demo_line(b)
    mark = "" if f(b, "type") == "epic" else (" ✓" if d else " · no demo")
    s = f"  {f(b,'title')} ({f(b,'id')}) · {status_of(b, ready, blocked, by_id)}{mark}"
    return s + (f"\n      demo: {d}" if d and SHOW_DEMO else "")

def matches(b, words):
    hay = " ".join([f(b, "title", "") or "", f(b, "desc", "") or "", " ".join(labels(b))]).lower()
    return all(w.lower() in hay for w in words)

def board(limit, show_all=False, only_label=None, only_epic=None, words=None):
    by_id, ready, blocked = load()
    beads = list(by_id.values())
    epics = {f(b, "id"): b for b in beads if f(b, "type") == "epic"}
    if only_label: beads = [b for b in beads if only_label.lower() in [l.lower() for l in labels(b)] and f(b, "type") != "epic"]
    if words:
        beads = [b for b in beads if f(b, "type") != "epic" and (matches(b, words) or (parent_of(b) in epics and matches(epics[parent_of(b)], words)))]
        show_all = True
    if only_epic:
        epics = {only_epic: by_id.get(only_epic, {"title": only_epic, "id": only_epic})}
        beads = [b for b in beads if parent_of(b) == only_epic]
        show_all = True
    children = {}
    for b in beads:
        if f(b, "type") == "epic" and not only_epic: continue
        children.setdefault(parent_of(b) or "_none", []).append(b)
    order = lambda b: (0 if f(b,"id") in ready else 1, f(b, "priority", 9) or 9, f(b, "title", ""))
    out, shown, total_ready, total_blocked, total_you = [], 0, 0, 0, 0
    def count(bs):
        r = sum(1 for b in bs if f(b,"id") in ready and not needs_you(b))
        bl = sum(1 for b in bs if f(b,"id") in blocked)
        y = sum(1 for b in bs if needs_you(b))
        return r, bl, y
    groups = [(eid, epics[eid], children.get(eid, [])) for eid in epics] + [("_none", None, children.get("_none", []))]
    for eid, epic, bs in groups:
        if not bs: continue
        r, bl, y = count(bs); total_ready += r; total_blocked += bl; total_you += y
        head = f"{f(epic,'title')} ({eid})" if epic else "Unparented"
        if epic and (d := section(f(epic, "desc", ""), "Destination")): head += f" — {' '.join(d.split())[:90]}"
        out.append(f"\n{head}   ready {r} · blocked {bl} · needs you {y}")
        if epic and only_epic and (desc := f(epic, "desc")): out.append("  " + desc.strip().replace("\n", "\n  "))
        for b in sorted(bs, key=order):
            if show_all or (f(b,"id") in ready and shown < limit):
                out.append(line(b, ready, blocked, by_id)); shown += 1 if f(b,"id") in ready else 0
    if words and not any(children.values()): out.append(f"no open beads match: {' '.join(words)}")
    if only_label and not any(children.values()): out.append(f"no open beads carry label: {only_label}  (`--labels` lists labels in use)")
    out.append(f"\nready {total_ready} · blocked {total_blocked} · needs you {total_you}" + ("" if SHOW_DEMO else "   (✓ has a demo line; --demo shows it)"))
    if not show_all and total_ready > shown:
        out.append(f"showing {shown} of {total_ready} ready. `issues.py <epic-id>` expands one epic; `--all` lists everything; `--limit N` shows more.")
    print("\n".join(out).lstrip("\n"))

def page(bid):
    res = bd("show", bid)
    if not res: print(f"no bead {bid}"); return
    b = res[0]; by_id, ready, blocked = load()
    print(f"{f(b,'title')}  ({bid})")
    print(f"{f(b,'type','?')} · {f(b,'status','?')} · p{f(b,'priority','?')} · {f(b,'assignee') or 'unassigned'} · labels: {', '.join(labels(b)) or 'none'}")
    if (p := parent_of(b)): print(f"epic: {f(by_id.get(p, {}), 'title', p)} ({p})")
    print()
    print(f(b, "desc", "(no description)") or "(no description)")
    if (a := f(b, "accept")): print(f"\nAcceptance:\n{a}")
    bl = blocked.get(bid, [])
    if bl: print("\nBlocked by: " + ", ".join(f"{f(by_id[x],'title',x)} ({x})" if x in by_id else x for x in bl))
    downstream = [x for x, names in blocked.items() if bid in names]
    if downstream: print("Blocks: " + ", ".join(f"{f(by_id[x],'title',x)} ({x})" if x in by_id else x for x in downstream))
    if (n := f(b, "notes")): print(f"\nNotes:\n{n}")
    cs = f(b, "comments", []) or []
    if cs:
        print("\nComments:")
        for c in cs:
            if isinstance(c, dict): print(f"  [{c.get('created_at') or c.get('timestamp') or ''}] {c.get('author') or ''}: {c.get('text') or c.get('body') or c.get('content') or ''}")
            else: print(f"  {c}")
    print()
    step = next_step(b, p, status_of(b, ready, blocked, by_id), bl)
    if step: print(f"next: {step}")

def next_step(b, p, st, bl):
    lb = labels(b)
    # A map bead has no Demo line, so the Demo check would send it to grilling.
    if any(l.startswith("wayfinder:") for l in lb): return f"/jidoka:wayfinder {p or f(b, 'id')}"
    if not demo_line(b) and f(b, "type") != "epic": return "no Demo line — /jidoka:grill-with-docs or /jidoka:to-tickets before implementing"
    if "human" in lb: return "needs you — see description"
    if "bench" in lb: return f"needs you at the bench, /jidoka:bench {f(b, 'id')}"
    if st == "ready": return f"ready to build with /jidoka:bench {f(b, 'id')}"
    if st.startswith("blocked"): return f"look at the blocker first ({bl[0] if bl else '?'})"
    if st.startswith("in progress"): return "a session claimed this; finish or release it"
    return None

def label_counts():
    by_id, ready, blocked = load()
    counts = {}
    for b in by_id.values():
        for l in labels(b): counts[l] = counts.get(l, 0) + 1
    if not counts: print("no labels on open beads"); return
    for l, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])): print(f"  {l}  {n}")

def doctor():
    for cmd in (["ready"], ["list", "--status=open"], ["blocked"]):
        res = bd(*cmd)
        print(f"bd {' '.join(cmd)} --json → {len(res)} items; keys: {sorted(res[0].keys()) if res else 'none'}")
    res = bd("list", "--status=open")
    if res:
        print("bd show <first> --json →"); print(json.dumps(bd("show", f(res[0], "id"))[0], indent=1)[:2000])

ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-[A-Za-z0-9]+(\.[0-9]+)*$")

if __name__ == "__main__":
    a = sys.argv[1:]; limit = 8
    if "--limit" in a:
        i = a.index("--limit"); limit = int(a[i + 1]); del a[i:i + 2]
    if "--demo" in a: SHOW_DEMO = True; a.remove("--demo")
    only_label = None
    if "--label" in a:
        i = a.index("--label"); only_label = a[i + 1]; del a[i:i + 2]
    for x in list(a):
        if x.lower().startswith("label:"): only_label = x.split(":", 1)[1]; a.remove(x)
    if only_label: board(limit, show_all=True, only_label=only_label, words=a or None)
    elif not a: board(limit)
    elif a[0] == "--labels": label_counts()
    elif a[0] == "--all": board(limit, show_all=True)
    elif a[0] == "--doctor": doctor()
    elif len(a) == 1 and a[0] in NEEDS_YOU: board(limit, show_all=True, only_label=a[0])
    elif len(a) == 1 and ID_RE.match(a[0]):
        res = bd("show", a[0])
        if res and f(res[0], "type") == "epic": board(limit, only_epic=a[0])
        elif res: page(a[0])
        else: board(limit, words=a)
    else:
        STOP = {"just","show","me","the","open","items","list","all","please","what","are","for","of","in","and","beads","bead","ready","issues"}
        words = [w for w in a if w.lower() not in STOP] or a
        board(limit, words=words)
