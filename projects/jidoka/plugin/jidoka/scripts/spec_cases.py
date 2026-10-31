#!/usr/bin/env python3
"""Writes the test cases the human approved onto the epic's spec task, and prints them back.

The cases live in one section of the spec task's description, headed `## Acceptance specs`, so that the spec task's
build worker reads them with the rest of its task, and the spec approval page can show each case beside its plain
reading. The section holds the test cases, each with its plain reading and its answer to "if this feature were
deleted, would the spec still pass?", and the interface table of what the protocol driver does not offer yet. The rest
of the description stays as it was.

`write <epic>` reads one JSON object on stdin, `{"cases": [...], "interface": [...]}`. A case is `{"name", "reading",
"deletion"}`: the spec's name in the words of the app's users, a plain reading of it, and the answer to the deletion
question. An interface row is `{"interface", "shape", "cases"}`: one thing the driver does not offer, how the app
reaches it, and the numbers, counted from 1, of the cases that need it. `interface` is a list that may be empty.
`write` checks the shape, finds the epic's spec task through the `acceptance.spec_task` metadata that specs.py records,
and replaces the section of its description in place, or adds the section at the end when the description lacks it.
It runs under the repo's git user.name and prints the section. A write that changes nothing writes nothing.

`read <epic>` prints the section as the spec task holds it, or nothing when the spec task has none.

Exit codes:
  0  success.
  1  it refused, or a bd command failed, with the reason on stderr; a refusal writes nothing.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import settings_reader
import specs
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, env_as_git_user, run
from epic_reader import EpicReadError, Rerun, epic_of

SECTION_HEADING = "## Acceptance specs"
RERUN = Rerun(on_the_holding_epic="Name the spec task on the epic that holds it")
HEADING_LINE = re.compile(r"^## ")
NO_INTERFACE = "The protocol driver already offers everything the test cases need."
INTERFACE_LEAD = "The protocol driver does not offer these yet."
INTERFACE_COLUMNS = ("Interface", "Shape", "Cases")


class SpecCasesError(Exception):
    """Test cases that cannot be written or read, worded for the person who reads stderr."""


@dataclass(frozen=True)
class SpecCase:
    """One acceptance spec as the human approved it: its name in the users' words, its plain reading and its answer
    to the deletion question."""
    name: str
    reading: str
    deletion: str


@dataclass(frozen=True)
class InterfaceRow:
    """One thing the protocol driver does not offer yet, how the app reaches it, and the numbers of the cases that
    need it."""
    interface: str
    shape: str
    cases: tuple[int, ...]


def text_of(value: object) -> str | None:
    """The value as one line of words, or None when it is not text or holds no letter or digit."""
    if not isinstance(value, str):
        return None
    words = " ".join(value.split())
    return words if any(character.isalnum() for character in words) else None


def parsed_cases(given: object) -> list[SpecCase]:
    if not (isinstance(given, list) and given):
        raise SpecCasesError("cases is not a list with at least one test case")
    found = []
    for number, case in enumerate(given, start=1):
        fields = [text_of(case.get(key)) for key in ("name", "reading", "deletion")] if isinstance(case, dict) else []
        if not fields or None in fields:
            raise SpecCasesError(f"case {number} is not an object with a name, a reading and a deletion answer, "
                                 "each in words")
        found.append(SpecCase(*fields))
    names = [case.name for case in found]
    twice = next((name for name in names if names.count(name) > 1), None)
    if twice is not None:
        raise SpecCasesError(f"two cases are named {twice!r}. Name each case once")
    return found


def parsed_interface(given: object, case_count: int) -> list[InterfaceRow]:
    if not isinstance(given, list):
        raise SpecCasesError("interface is not a list")
    found = []
    for number, row in enumerate(given, start=1):
        interface = text_of(row.get("interface")) if isinstance(row, dict) else None
        shape = text_of(row.get("shape")) if isinstance(row, dict) else None
        users = row.get("cases") if isinstance(row, dict) else None
        if interface is None or shape is None or not (isinstance(users, list) and users):
            raise SpecCasesError(f"interface row {number} is not an object with an interface and a shape in words, "
                                 "and the numbers of the cases that need it")
        outside = [user for user in users if not (isinstance(user, int) and not isinstance(user, bool)
                                                  and 1 <= user <= case_count)]
        if outside:
            raise SpecCasesError(f"interface row {number} names case {outside[0]!r}, and the cases are numbered "
                                 f"1 to {case_count}")
        found.append(InterfaceRow(interface, shape, tuple(sorted(set(users)))))
    return found


def cell(text: str) -> str:
    return text.replace("|", "\\|")


def rendered(cases: list[SpecCase], interface: list[InterfaceRow]) -> str:
    """The section as it sits in the description."""
    lines = [SECTION_HEADING, "", "### Test cases", ""]
    for number, case in enumerate(cases, start=1):
        lines += [f"{number}. {case.name}", f"   - Plain reading: {case.reading}",
                  f"   - If this feature were deleted: {case.deletion}"]
    lines += ["", "### Interface table", ""]
    if not interface:
        lines.append(NO_INTERFACE)
    else:
        lines += [INTERFACE_LEAD, "", f"| {' | '.join(INTERFACE_COLUMNS)} |", "| --- | --- | --- |"]
        lines += [f"| {cell(row.interface)} | {cell(row.shape)} | {', '.join(str(user) for user in row.cases)} |"
                  for row in interface]
    return "\n".join(lines)


def section_bounds(lines: list[str]) -> tuple[int, int] | None:
    """The first and past-the-last line of the section, or None when the description lacks it."""
    start = next((index for index, line in enumerate(lines) if line.strip() == SECTION_HEADING), None)
    if start is None:
        return None
    end = next((index for index in range(start + 1, len(lines)) if HEADING_LINE.match(lines[index])), len(lines))
    return start, end


def section_of(description: str) -> str:
    """The section as the description holds it, an empty string when it holds none."""
    lines = description.split("\n")
    bounds = section_bounds(lines)
    return "" if bounds is None else "\n".join(lines[bounds[0]:bounds[1]]).strip()


def with_section(description: str, section: str) -> str:
    """The description with the section in place of the one it held, or after its last line when it held none."""
    lines = description.rstrip("\n").split("\n") if description.strip() else []
    bounds = section_bounds(lines)
    if bounds is None:
        return "\n".join([*lines, "", section]) if lines else section
    start, end = bounds
    after = lines[end:]
    return "\n".join([*lines[:start], section, *(["", *after] if after else [])])


def spec_task_bead(epic_id: str, main_tree: Path) -> dict:
    epic = epic_of(epic_id, main_tree, RERUN)
    task = specs.spec_task_of(epic.shown)
    if not task:
        raise SpecCasesError(f"{epic.id} records no spec task. File it with to-tickets, then record it with "
                             f"specs.py spec-task {epic.id} <task>")
    return specs.task_in(epic, task)


@dataclass(frozen=True)
class Proposal:
    """The JSON object on stdin once it is checked: the cases, the interface rows, and the case objects as given, for a
    caller that reads a field of its own from them."""
    cases: list[SpecCase]
    interface: list[InterfaceRow]
    given_cases: list[dict]


def parsed_proposal(raw: str) -> Proposal:
    """Decodes `{"cases": [...], "interface": [...]}` and checks it; raises SpecCasesError for what it refuses."""
    try:
        given = json.loads(raw)
    except ValueError as error:
        raise SpecCasesError(f"the input is not valid JSON: {error}") from error
    if not (isinstance(given, dict) and "cases" in given and "interface" in given):
        raise SpecCasesError('the input is not an object with "cases" and "interface"')
    cases = parsed_cases(given["cases"])
    return Proposal(cases, parsed_interface(given["interface"], len(cases)), given["cases"])


def write(epic_id: str, raw: str, main_tree: Path) -> str:
    proposal = parsed_proposal(raw)
    section = rendered(proposal.cases, proposal.interface)
    task = spec_task_bead(epic_id, main_tree)
    description = str(task.get("description") or "")
    changed = with_section(description, section)
    if changed != description.rstrip("\n"):
        run(["bd", "update", str(task["id"]), f"--description={changed}"], main_tree, env_as_git_user(main_tree))
    return section


def read(epic_id: str, main_tree: Path) -> str:
    return section_of(str(spec_task_bead(epic_id, main_tree).get("description") or ""))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="spec_cases.py", description="Write the approved test cases onto the "
                                                                       "epic's spec task, or print them back.")
    modes = parser.add_subparsers(dest="mode", required=True)
    writing = modes.add_parser("write", help="store the JSON object of cases and interface rows on stdin")
    writing.add_argument("epic")
    reading = modes.add_parser("read", help="print the cases the spec task's description holds")
    reading.add_argument("epic")
    args = parser.parse_args(argv)
    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        printed = (write(args.epic, sys.stdin.read(), main_tree) if args.mode == "write"
                   else read(args.epic, main_tree))
    except (SpecCasesError, specs.SpecsError, EpicReadError, CommandError, settings_reader.SettingsError,
            OSError) as error:
        print(f"spec_cases: {error}", file=sys.stderr)
        return 1
    if printed:
        print(printed)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
