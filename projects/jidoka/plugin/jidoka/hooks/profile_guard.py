#!/usr/bin/env python3
"""Holds a lap worker's tool calls to the lap's rules, as a PreToolUse hook in T3's Antigravity profile.

An Antigravity host has no lap mod, so this hook is its stand-in for the lap mod's rules, and it loads in every T3
Antigravity session. Antigravity sends the call as JSON on stdin: a `toolCall` with the tool's `name` and its `args`,
the `cwd` the call runs in and the `workspacePaths` of the session. The hook acts only when `cwd` or one of the
workspace paths is inside a worktree that has a guard record (lap_guard_record.py), and prints nothing everywhere
else, because an empty answer, `{}` or `null`, would deny the call. It never runs a script to learn the rules; the
record holds the lists and the acceptance folders, so it answers well inside the host's timeout.

Inside a lap the hook answers `{"decision": "allow"}` or a deny with its reason, in the lap mod's words:

- `run_command` is judged as the lap mod judges a Bash call: by the lists, with the same list matcher and the same
  splitting of the command into simple commands, and, for a lap worker, by the rules for a delete, a new folder and a
  move, which must name paths that really land inside the worktree and outside every acceptance folder. A command that
  cannot be split, and a call whose `CommandLine` is missing or is not text, are denied.
- `write_file` and `edit_file` must name an absolute `Path`, and `notebook_edit` an absolute `NotebookPath`, that really
  lands inside the worktree, links followed, and outside every acceptance folder the lap may not write in.
- `read_file` is allowed.
- `invoke_subagent`, `define_subagent` and `ask_question` are denied, and so is any other tool, by its name.

A record that cannot be read crashes the hook, which exits nonzero, and the host fails the call closed. `--host`
names the host, which the installer gives every Antigravity hook command.

lap_guard_cases.ts holds the cases that this hook and the lap mod must answer alike.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

import lap_guard_record  # noqa: E402
from delete_paths import changes_folder, deleted_paths, is_delete, placed_paths  # noqa: E402
from list_matcher import are_listed, entries_of, split_into_simple_commands  # noqa: E402
from path_placement import is_absolute, is_really_beneath, is_really_beneath_ignoring_case, spelled  # noqa: E402
from shell_words import ReadCommand, read_commands  # noqa: E402

ANTIGRAVITY = "antigravity"
RUN_COMMAND = "run_command"
READ_FILE = "read_file"
WRITE_PATH_FIELDS = {"write_file": "Path", "edit_file": "Path", "notebook_edit": "NotebookPath"}
STARTS_WORKERS = {"invoke_subagent", "define_subagent"}
ASKS_LIVE = "ask_question"

WAY_OUT = {
    lap_guard_record.LAP: ("lap workers", "park the task with a question that names this call"),
    lap_guard_record.CHECK: ("check workers",
                             "report the holdout you could not test as failed, saying that this call was denied"),
}
UNREADABLE_REASON = ("jidoka: this run_command names no command text, so it cannot be checked against jidoka's "
                     "lists, and the call is denied.")

OFF_LISTS = "off-lists"
OUTSIDE_WORKTREE = "outside-worktree"
PLACED_OUTSIDE_WORKTREE = "placed-outside-worktree"
UNREADABLE_DELETE = "unreadable-delete"
ACCEPTANCE_FOLDERS_UNREAD = "acceptance-folders-unread"


@dataclass(frozen=True)
class Barred:
    """A path that is inside an acceptance folder the lap may not write in, or holds one, so that a move or a delete
    of it would take the folder along."""
    acceptance_folder: str
    relation: str


Refusal = str | Barred


def deny(reason: str) -> dict:
    return {"decision": "deny", "reason": reason}


def off_the_lists(kind: str, call: str) -> dict:
    workers, advice = WAY_OUT[kind]
    return deny(f"jidoka: {call} is off jidoka's lists for {workers}. Find another way, or {advice}.")


def folders_of(event: dict) -> list[Path]:
    """The folders the call may run in: its `cwd`, then each of the session's workspace paths."""
    named = [event.get("cwd"), *(event["workspacePaths"] if isinstance(event.get("workspacePaths"), list) else [])]
    return [Path(folder) for folder in named if isinstance(folder, str) and folder]


def record_for(event: dict) -> lap_guard_record.GuardRecord | None:
    home = lap_guard_record.jidoka_home()
    for folder in folders_of(event):
        record = lap_guard_record.read_record(home, folder)
        if record is not None:
            return record
    return None


def barred_refusal(record: lap_guard_record.GuardRecord, where: str) -> Refusal | None:
    """Why a lap worker may not change `where`, an absolute path: it is inside an acceptance folder the lap may not
    write in, or those folders are unread."""
    if record.barred is None:
        return ACCEPTANCE_FOLDERS_UNREAD
    for folder in record.barred:
        if is_really_beneath_ignoring_case(where, folder, record.worktree):
            return Barred(folder, "inside")
    return None


def write_refusal(record: lap_guard_record.GuardRecord, path: str, base: str) -> Refusal | None:
    """Why a lap worker may not write at `path`, read against `base`, the one rule for every call that changes a path:
    it is the worktree itself or lands outside it, or it is barred."""
    where = spelled(path, base)
    if where is None or where == spelled(record.worktree, "/") \
            or not is_really_beneath(where, record.worktree, record.worktree):
        return OUTSIDE_WORKTREE
    return barred_refusal(record, where)


def removal_refusal(record: lap_guard_record.GuardRecord, path: str, base: str) -> Refusal | None:
    """Why a lap worker may not remove `path` from where it is: it may not write there, or it holds an acceptance
    folder."""
    refusal = write_refusal(record, path, base)
    if refusal is not None:
        return refusal
    where = spelled(path, base)
    for folder in record.barred or []:
        if where is not None and is_really_beneath_ignoring_case(folder, where, record.worktree):
            return Barred(folder, "holds")
    return None


def first_refusal(paths: list[str], refuse: Callable[[str], Refusal | None]) -> Refusal | None:
    for path in paths:
        refusal = refuse(path)
        if refusal is not None:
            return refusal
    return None


def beneath_destinations(sources: list[str], destinations: list[str], base: str) -> list[str]:
    """Where a move into an existing folder puts what it moves: beneath each destination, under the name of each
    source. The words do not say whether the destination is a folder, so these places are judged beside it."""
    names = [where.split("/")[-1] for where in (spelled(source, base) for source in sources) if where is not None]
    return [destination.rstrip("/") + "/" + name for destination in destinations for name in names]


def delete_refusal(record: lap_guard_record.GuardRecord, deleted: list[str], base: str) -> Refusal | None:
    return first_refusal(deleted, lambda path: removal_refusal(record, path, base))


def place_refusal(record: lap_guard_record.GuardRecord, leaving: list[str], arriving: list[str],
                  base: str) -> Refusal | None:
    refusal = first_refusal(leaving, lambda path: removal_refusal(record, path, base)) \
        or first_refusal([*arriving, *beneath_destinations(leaving, arriving, base)],
                         lambda path: write_refusal(record, path, base))
    return PLACED_OUTSIDE_WORKTREE if refusal == OUTSIDE_WORKTREE else refusal


def behind_assignments(part: ReadCommand) -> list[str]:
    return part.words[part.assignments:]


def unlisted_refusal(record: lap_guard_record.GuardRecord, others: list[ReadCommand]) -> str | None:
    """Why the lists refuse a command of `others`, none of which reads paths; None when each is on a list."""
    entries = split_into_simple_commands(entries_of(record.commands))
    unlisted = next((part for part in others if not are_listed([part.words], entries)), None)
    if unlisted is None:
        return None
    is_lap_delete = record.kind == lap_guard_record.LAP and is_delete(behind_assignments(unlisted))
    return UNREADABLE_DELETE if is_lap_delete else OFF_LISTS


def refusal_of(record: lap_guard_record.GuardRecord, command: str, base: str) -> Refusal | None:
    """Why `command` is refused, or None when every simple command of it is on the lists or, for a lap worker, deletes
    only paths that really land inside the worktree, the worktree itself excepted, and makes folders and moves files
    only between such paths, outside every acceptance folder it may not write in, and moves or deletes no folder that
    holds one. A delete, a move or a new folder that follows a change of folder is left to the lists, because its
    relative paths would read against another folder, and so is one behind a variable, whose words do not start with
    the command."""
    parts = read_commands(command)
    if parts is None:
        return OFF_LISTS
    may_read_paths = record.kind == lap_guard_record.LAP and not any(
        changes_folder(behind_assignments(part)) for part in parts)
    others: list[ReadCommand] = []
    for part in parts:
        deleted = deleted_paths(part.words) if may_read_paths else None
        placed = placed_paths(part.words) if may_read_paths else None
        if deleted is None and placed is None:
            others.append(part)
            continue
        if deleted is not None:
            refusal = delete_refusal(record, deleted, base)
        else:
            refusal = place_refusal(record, placed.leaving, placed.arriving, base)
        if refusal is not None:
            return refusal
    return unlisted_refusal(record, others)


def barred_denial(call: str, barred: Refusal) -> dict:
    """The denial of a path that is barred, in one wording for every call that changes a path."""
    if not isinstance(barred, Barred):
        return deny(f"jidoka: {call} is denied, because jidoka could not read which acceptance folders this lap may "
                    "not write in. Park the task with a question that says so.")
    where = "is inside" if barred.relation == "inside" else "holds"
    return deny(f"jidoka: {call} {where} the acceptance folder {barred.acceptance_folder}, which only the spec "
                "task's lap may change. If a spec looks wrong, park the task with a question that says which spec "
                "and why.")


def refused(record: lap_guard_record.GuardRecord, call: str, refusal: Refusal) -> dict:
    if refusal == OFF_LISTS:
        return off_the_lists(record.kind, call)
    if isinstance(refusal, Barred) or refusal == ACCEPTANCE_FOLDERS_UNREAD:
        return barred_denial(call, refusal)
    if refusal == OUTSIDE_WORKTREE:
        why = f"deletes outside the lap's worktree {record.worktree}"
    elif refusal == PLACED_OUTSIDE_WORKTREE:
        why = f"makes a folder or moves a file outside the lap's worktree {record.worktree}"
    else:
        why = ("is a delete whose paths jidoka cannot tell: a lap worker may delete only paths it names one by one, "
               "with no option but -f and -r (git rm: -r, -q and --cached), no glob, variable or `~`, no variable "
               "set in front of it, and no change of folder before it")
    return deny(f"jidoka: {call} {why}. Find another way, or {WAY_OUT[record.kind][1]}.")


def command_of(args: object) -> str | None:
    command = args.get("CommandLine") if isinstance(args, dict) else None
    return command if isinstance(command, str) else None


def base_of(event: dict, record: lap_guard_record.GuardRecord) -> str:
    """The folder a command's relative paths read against: the folder the call runs in, else the worktree."""
    cwd = event.get("cwd")
    return cwd if isinstance(cwd, str) and is_absolute(cwd) else record.worktree


def command_verdict(record: lap_guard_record.GuardRecord, event: dict, args: object) -> dict:
    command = command_of(args)
    if command is None:
        return deny(UNREADABLE_REASON)
    refusal = refusal_of(record, command, base_of(event, record))
    return {"decision": "allow"} if refusal is None else refused(record, f"`{command}`", refusal)


def write_verdict(record: lap_guard_record.GuardRecord, tool: str, field: str, args: object) -> dict:
    path = args.get(field) if isinstance(args, dict) else None
    if not isinstance(path, str) or path == "":
        return deny(f"jidoka: {tool} names no {field}.")
    if not is_absolute(path):
        return deny(f"jidoka: {tool} of {path} is not an absolute path. Name the file by its absolute path inside "
                    f"the lap's worktree {record.worktree}.")
    refusal = write_refusal(record, path, record.worktree)
    if refusal is None:
        return {"decision": "allow"}
    if refusal == OUTSIDE_WORKTREE:
        return deny(f"jidoka: {tool} of {path} is outside the lap's worktree {record.worktree}.")
    return barred_denial(f"{tool} of {path}", refusal)


def asks_live_verdict(record: lap_guard_record.GuardRecord) -> dict:
    if record.kind == lap_guard_record.CHECK:
        return deny("jidoka: a check worker never asks live. Say what you could not test in your report.")
    return deny("jidoka: a lap worker never asks live. End the stage with a question report in the scratch folder and "
                "the outcome question.")


def verdict(record: lap_guard_record.GuardRecord, event: dict, tool_call: dict) -> dict:
    tool, args = tool_call.get("name"), tool_call.get("args")
    if tool == RUN_COMMAND:
        return command_verdict(record, event, args)
    if tool in WRITE_PATH_FIELDS:
        return write_verdict(record, tool, WRITE_PATH_FIELDS[tool], args)
    if tool == READ_FILE:
        return {"decision": "allow"}
    if tool == ASKS_LIVE:
        return asks_live_verdict(record)
    if tool in STARTS_WORKERS:
        return deny(f"jidoka: a lap worker starts no workers, so its {tool} call is denied.")
    return off_the_lists(record.kind, str(tool))


def decision(raw: str) -> dict | None:
    """The answer for the payload, or None when the hook prints nothing: input that is no tool call, or a call
    outside every lap worktree."""
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    tool_call = event.get("toolCall") if isinstance(event, dict) else None
    if not isinstance(tool_call, dict) or not isinstance(tool_call.get("name"), str):
        return None
    record = record_for(event)
    return None if record is None else verdict(record, event, tool_call)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="profile_guard.py")
    parser.add_argument("--host", choices=[ANTIGRAVITY], required=True, help="the host that runs the hook")
    parser.parse_args(argv)
    answer = decision(sys.stdin.read())
    if answer is not None:
        print(json.dumps(answer))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
