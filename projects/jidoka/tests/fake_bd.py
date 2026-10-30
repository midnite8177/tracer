"""A stand-in for bd that keeps its beads in one JSON file, for the tests of the scripts that read and write beads.

Real bd opens its embedded Dolt database on every call, which takes a
second or more, and a scheduler test makes a couple of dozen calls. This
fake answers in the time Python takes to start.

It speaks only the calls that scheduler.py, handoff.py, holdouts.py,
targeted_tests.py, merge_gate.py, bench.py, land.py, notify.py, resume.py and the issues and
context skills' scripts make, and the ones their tests make to set up and
read beads:
  show <id>... --json
  list [--parent <id>] --all --limit 0 --json
  list [--status <status>] --json
  list --label <label> --type <type> --limit 0 --json
  ready --json
  blocked --json
  create --title <title> [--type <type>] [--parent <id>] [--labels <label,...>] [--priority <n>]
         [--description <text>] [--deps <id|discovered-from:id>,...] --json
  update <id> [--claim] [--status <status>] [--assignee <name>] [--parent <id>] [--add-label <label>]
         [--set-metadata <key>=<value>]... [--unset-metadata <key>]...
  label add|remove <id> <label>
  comment <id> <text>
  comments <id> --json
  close <id> --reason <text>
  dep add <id> --blocked-by <id>
  prime
A flag takes its value as --flag=value or as --flag value, as bd's does.
Any other subcommand, flag or form of list exits 1 naming it on stderr, so
a script that starts making a new call fails its tests until the fake
learns it, and test_fake_bd.py checks the fake's answer against real bd's.

What it prints keeps the shape of bd 1.2's output in the fields the scripts
read. A field with no value is left out, as bd leaves it out: no assignee,
no description, no labels, no metadata. Labels come sorted. A metadata
value that reads as a JSON number, true, false or null is stored as that,
and anything else as the text given, as bd stores it. A task's id is its
parent's id and a number. Each bare id --deps names is a bead the new one
waits on, as bd reads a bare id there, and each discovered-from:<id> is a
link that waits on nothing. A task created under a parent starts with the parent's labels, as bd copies them, besides any
--labels it is given. bd keeps one link per pair of beads, so a --deps
entry that names the --parent is dropped and only parent-child stays. A
bead is ready when it is open and waits on no bead that is still open, and
blocked when it is not closed and waits on one; blocked prints the ids of
the beads not yet closed that it waits on. A claim sets the assignee to the actor and the status to
in_progress, and fails when another actor is the assignee. The actor, who
also writes each comment, is BEADS_ACTOR, or else the repo's git user.name.
prime prints a fixed text in place of bd's workflow notes. A list without
--limit 0 prints every match, where bd stops at 50; no test makes that many.

The store is <repo>/.beads/fake-bd.json, found from the working folder
upward, so the main checkout and any worktree under it share it, or else
in the folder that holds the repo's common git folder, so a linked
worktree elsewhere shares it too, as bd finds its database. Each call reads
it whole and replaces it whole; the scripts and their tests call bd one
call at a time, so no call holds a lock.
"""
from __future__ import annotations

import getpass
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

STORE = Path(".beads") / "fake-bd.json"
DEFAULT_TYPE = "task"
DEFAULT_PRIORITY = 2
STATUSES = {"open", "in_progress", "blocked", "deferred", "closed"}
BLOCKS = "blocks"
PARENT_CHILD = "parent-child"
DISCOVERED_FROM = "discovered-from"
CLOSED = "closed"
PRIME_TEXT = "# Beads Workflow Context\n\nThe fake bd stands in for bd prime here.\n"


class Refused(Exception):
    """A call the fake does not answer, worded for the person who reads the test's failure."""


@dataclass
class Flags:
    """The arguments of one call: its positionals in order, and the values each flag was given."""
    positionals: list[str] = field(default_factory=list)
    values: dict[str, list[str]] = field(default_factory=dict)
    switches: set[str] = field(default_factory=set)

    def one(self, name: str) -> str | None:
        given = self.values.get(name)
        return given[-1] if given else None


def new_store(path: Path, prefix: str) -> None:
    """Writes an empty store whose bead ids start with prefix and a dash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"prefix": prefix, "next": 1, "beads": {}, "comments": []}), encoding="utf-8")


def main_checkout(cwd: Path) -> Path | None:
    """The folder that holds the repo's common git folder, which is the main checkout seen from a linked worktree."""
    done = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        return None
    return Path(done.stdout.strip()).parent


def store_path(cwd: Path) -> Path:
    for folder in (cwd, *cwd.parents):
        if (folder / STORE).is_file():
            return folder / STORE
    main = main_checkout(cwd)
    if main is not None and (main / STORE).is_file():
        return main / STORE
    raise Refused(f"no fake beads store {STORE} in {cwd}, a folder above it or its repo's main checkout")


def save(path: Path, store: dict) -> None:
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(store), encoding="utf-8")
    os.replace(partial, path)


def parse(command: str, args: list[str], takes_values: set[str], switches: set[str]) -> Flags:
    flags = Flags()
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        if not arg.startswith("--"):
            flags.positionals.append(arg)
            continue
        name, has_value, value = arg.partition("=")
        if name in switches and not has_value:
            flags.switches.add(name)
        elif name in takes_values:
            if not has_value:
                if index >= len(args):
                    raise Refused(f"bd {command} {name} needs a value")
                value = args[index]
                index += 1
            flags.values.setdefault(name, []).append(value)
        else:
            raise Refused(f"the fake bd does not take {name} on bd {command}")
    return flags


def need_json(command: str, flags: Flags) -> None:
    if "--json" not in flags.switches:
        raise Refused(f"the fake bd answers bd {command} only with --json")


def need_positionals(command: str, flags: Flags, count: int) -> None:
    if len(flags.positionals) != count:
        raise Refused(f"bd {command} takes {count} arguments here, not {flags.positionals}")


def bead_in(store: dict, bead_id: str) -> dict:
    bead = store["beads"].get(bead_id)
    if bead is None:
        raise Refused(f"no issue found matching {bead_id!r}")
    return bead


def actor(cwd: Path) -> str:
    named = os.environ.get("BEADS_ACTOR")
    if named:
        return named
    done = subprocess.run(["git", "config", "user.name"], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8")
    return done.stdout.strip() or getpass.getuser()


def typed(value: str) -> object:
    """The metadata value as bd stores it: a JSON number, boolean or null as that, and anything else as text."""
    try:
        parsed = json.loads(value)
    except ValueError:
        return value
    if parsed is None or isinstance(parsed, (bool, int)):
        return parsed
    if isinstance(parsed, float) and math.isfinite(parsed):
        return int(parsed) if parsed.is_integer() else parsed
    return value


def plain(bead: dict) -> dict:
    """The bead's own fields as bd prints them, leaving out each one that holds nothing."""
    printed = {key: bead[key] for key in ("id", "title", "status", "priority", "issue_type")}
    for key in ("assignee", "close_reason", "description"):
        if bead.get(key):
            printed[key] = bead[key]
    if bead["metadata"]:
        printed["metadata"] = bead["metadata"]
    if bead["labels"]:
        printed["labels"] = sorted(bead["labels"])
    if bead.get("parent"):
        printed["parent"] = bead["parent"]
    return printed


def shown(store: dict, bead: dict) -> dict:
    """The bead as bd show prints it: its own fields, and each bead it waits on or sits under with the link's type."""
    links = [(target, BLOCKS) for target in bead["blocked_by"]]
    links.extend((target, DISCOVERED_FROM) for target in bead.get("discovered_from", []))
    if bead.get("parent"):
        links.append((bead["parent"], PARENT_CHILD))
    printed = plain(bead)
    if links:
        printed["dependencies"] = [{**plain(store["beads"][target]), "dependency_type": kind}
                                   for target, kind in links]
    return printed


def show(store: dict, flags: Flags) -> bool:
    need_json("show", flags)
    if not flags.positionals:
        raise Refused("bd show needs an id")
    found = []
    for bead_id in flags.positionals:
        if bead_id in store["beads"]:
            found.append(shown(store, store["beads"][bead_id]))
        else:
            print(f"Error fetching {bead_id}: no issue found matching {bead_id!r}", file=sys.stderr)
    if not found:
        print(json.dumps({"error": "no issues found matching the provided IDs"}, indent=2))
        return False
    print(json.dumps(found, indent=2))
    return True


def open_blockers(store: dict, bead: dict) -> list[str]:
    return sorted(blocker for blocker in bead["blocked_by"] if store["beads"][blocker]["status"] != CLOSED)


def list_beads(store: dict, flags: Flags) -> bool:
    need_json("list", flags)
    need_positionals("list", flags, 0)
    parent, status = flags.one("--parent"), flags.one("--status")
    every = "--all" in flags.switches
    label, kind = flags.one("--label"), flags.one("--type")
    if label is not None or kind is not None:
        if label is None or kind is None or flags.one("--limit") != "0" or every or parent is not None \
                or status is not None:
            raise Refused("the fake bd answers bd list with --label and --type only as "
                          "list --label <label> --type <type> --limit 0 --json")
        print(json.dumps([plain(bead) for bead in store["beads"].values()
                          if bead["status"] != CLOSED and label in bead["labels"] and bead["issue_type"] == kind],
                         indent=2))
        return True
    if every or parent is not None or "--limit" in flags.values:
        if not every or flags.one("--limit") != "0" or status is not None:
            raise Refused("the fake bd answers bd list only as list [--parent <id>] --all --limit 0 --json, "
                          "list [--status <status>] --json or list --label <label> --type <type> --limit 0 --json")
    elif status is not None and status not in STATUSES:
        raise Refused(f"bd list --status takes one of {sorted(STATUSES)}, not {status!r}")

    def listed(bead: dict) -> bool:
        if parent is not None:
            return bead.get("parent") == parent
        if status is not None:
            return bead["status"] == status
        return every or bead["status"] != CLOSED

    print(json.dumps([plain(bead) for bead in store["beads"].values() if listed(bead)], indent=2))
    return True


def ready(store: dict, flags: Flags) -> bool:
    need_json("ready", flags)
    need_positionals("ready", flags, 0)
    print(json.dumps([plain(bead) for bead in store["beads"].values()
                      if bead["status"] == "open" and not open_blockers(store, bead)], indent=2))
    return True


def blocked(store: dict, flags: Flags) -> bool:
    need_json("blocked", flags)
    need_positionals("blocked", flags, 0)
    waiting = []
    for bead in store["beads"].values():
        blockers = open_blockers(store, bead)
        if bead["status"] != CLOSED and blockers:
            waiting.append({**plain(bead), "blocked_by_count": len(blockers), "blocked_by": blockers})
    print(json.dumps(waiting, indent=2))
    return True


def prime(flags: Flags) -> bool:
    need_positionals("prime", flags, 0)
    print(PRIME_TEXT, end="")
    return True


def create(store: dict, flags: Flags) -> bool:
    need_json("create", flags)
    need_positionals("create", flags, 0)
    title = flags.one("--title")
    if not title:
        raise Refused("bd create needs --title")
    parent = flags.one("--parent")
    inherited: list[str] = []
    if parent is None:
        bead_id = f"{store['prefix']}-{store['next']}"
        store["next"] += 1
    else:
        under = bead_in(store, parent)
        under["children"] += 1
        bead_id = f"{parent}.{under['children']}"
        inherited = list(under["labels"])
    priority = flags.one("--priority")
    labels = flags.one("--labels")
    blockers, origins = [], []
    for dep_spec in (flags.one("--deps") or "").split(","):
        kind, has_kind, target = dep_spec.rpartition(":")
        if not target:
            continue
        if has_kind and kind != DISCOVERED_FROM:
            raise Refused(f"the fake bd takes --deps only as bead ids or {DISCOVERED_FROM}:<id>, not {dep_spec!r}")
        bead_in(store, target)
        if target != parent:
            (origins if has_kind else blockers).append(target)
    bead = {"id": bead_id, "title": title, "status": "open",
            "priority": int(priority) if priority is not None else DEFAULT_PRIORITY,
            "issue_type": flags.one("--type") or DEFAULT_TYPE, "assignee": "", "close_reason": "",
            "description": flags.one("--description") or "",
            "metadata": {}, "labels": [*inherited, *(label for label in (labels or "").split(",")
                                                       if label and label not in inherited)],
            "parent": parent or "", "blocked_by": blockers, "discovered_from": origins, "children": 0}
    store["beads"][bead_id] = bead
    print(json.dumps(plain(bead), indent=2))
    return True


def add_label(bead: dict, label: str) -> None:
    if label not in bead["labels"]:
        bead["labels"].append(label)


def update(store: dict, flags: Flags, cwd: Path) -> bool:
    need_positionals("update", flags, 1)
    bead = bead_in(store, flags.positionals[0])
    if "--claim" in flags.switches:
        claimer = actor(cwd)
        if bead["assignee"] and bead["assignee"] != claimer:
            print(f"Error claiming {bead['id']}: issue already claimed by {bead['assignee']}", file=sys.stderr)
            return False
        bead["assignee"] = claimer
        bead["status"] = "in_progress"
    status = flags.one("--status")
    if status is not None:
        if status not in STATUSES:
            raise Refused(f"bd update --status takes one of {sorted(STATUSES)}, not {status!r}")
        bead["status"] = status
    assignee = flags.one("--assignee")
    if assignee is not None:
        bead["assignee"] = assignee
    parent = flags.one("--parent")
    if parent is not None:
        bead_in(store, parent)
        bead["parent"] = parent
    for label in flags.values.get("--add-label", []):
        add_label(bead, label)
    for pair in flags.values.get("--set-metadata", []):
        key, has_value, value = pair.partition("=")
        if not has_value or not key:
            raise Refused(f"bd update --set-metadata takes key=value, not {pair!r}")
        bead["metadata"][key] = typed(value)
    for key in flags.values.get("--unset-metadata", []):
        bead["metadata"].pop(key, None)
    return True


def label(store: dict, flags: Flags) -> bool:
    need_positionals("label", flags, 3)
    action, bead_id, name = flags.positionals
    bead = bead_in(store, bead_id)
    if action == "add":
        add_label(bead, name)
    elif action == "remove":
        bead["labels"] = [kept for kept in bead["labels"] if kept != name]
    else:
        raise Refused(f"the fake bd does not answer bd label {action}")
    return True


def comment(store: dict, flags: Flags, cwd: Path) -> bool:
    need_positionals("comment", flags, 2)
    bead_id, text = flags.positionals
    bead_in(store, bead_id)
    store["comments"].append({"id": str(len(store["comments"]) + 1), "issue_id": bead_id, "author": actor(cwd),
                              "text": text})
    return True


def comments(store: dict, flags: Flags) -> bool:
    need_json("comments", flags)
    need_positionals("comments", flags, 1)
    bead_id = flags.positionals[0]
    bead_in(store, bead_id)
    print(json.dumps([posted for posted in store["comments"] if posted["issue_id"] == bead_id], indent=2))
    return True


def close(store: dict, flags: Flags) -> bool:
    need_positionals("close", flags, 1)
    bead = bead_in(store, flags.positionals[0])
    bead["status"] = CLOSED
    bead["close_reason"] = flags.one("--reason") or ""
    return True


def dep(store: dict, flags: Flags) -> bool:
    need_positionals("dep", flags, 2)
    action, bead_id = flags.positionals
    blocker = flags.one("--blocked-by")
    if action != "add" or blocker is None:
        raise Refused("the fake bd answers bd dep only as dep add <id> --blocked-by <id>")
    bead = bead_in(store, bead_id)
    bead_in(store, blocker)
    if blocker not in bead["blocked_by"]:
        bead["blocked_by"].append(blocker)
    return True


def answer(argv: list[str], cwd: Path) -> bool:
    """Answers one call, saving the store when the call changed it; returns whether the call succeeded."""
    if not argv:
        raise Refused("bd needs a subcommand")
    command, args = argv[0], argv[1:]
    path = store_path(cwd)
    store = json.loads(path.read_text(encoding="utf-8"))
    if command == "show":
        return show(store, parse(command, args, set(), {"--json"}))
    if command == "list":
        return list_beads(store, parse(command, args, {"--parent", "--limit", "--status", "--label", "--type"},
                                       {"--all", "--json"}))
    if command == "ready":
        return ready(store, parse(command, args, set(), {"--json"}))
    if command == "blocked":
        return blocked(store, parse(command, args, set(), {"--json"}))
    if command == "comments":
        return comments(store, parse(command, args, set(), {"--json"}))
    if command == "prime":
        return prime(parse(command, args, set(), set()))
    writes = {
        "create": lambda: create(store, parse(command, args, {"--title", "--type", "--parent", "--labels",
                                                              "--priority", "--description", "--deps"},
                                              {"--json"})),
        "update": lambda: update(store, parse(command, args, {"--status", "--assignee", "--parent", "--add-label",
                                                              "--set-metadata", "--unset-metadata"},
                                              {"--claim"}), cwd),
        "label": lambda: label(store, parse(command, args, set(), set())),
        "comment": lambda: comment(store, parse(command, args, set(), set()), cwd),
        "close": lambda: close(store, parse(command, args, {"--reason"}, set())),
        "dep": lambda: dep(store, parse(command, args, {"--blocked-by"}, set())),
    }
    if command not in writes:
        raise Refused(f"the fake bd does not answer bd {command}")
    succeeded = writes[command]()
    save(path, store)
    return succeeded


def main(argv: list[str]) -> int:
    try:
        return 0 if answer(argv, Path.cwd()) else 1
    except Refused as refused:
        print(f"fake bd: {refused}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
