#!/usr/bin/env python3
"""Files the problems a review finds in old code as design findings, and adds a sighting when one is met again.

`design_findings.py --open [FILE ...]` prints the open design findings as a JSON list of {"bead", "file", "title",
"sightings"}, the most sighted first and the older bead first among equals. With FILEs it keeps only the findings
about those files. Planning reads this list.

`design_findings.py EPIC REPORT` reads REPORT, a JSON list of {"file", "line", "title", "note"}, one for each problem
the epic's review met in code the epic did not write, and prints a JSON list of {"bead", "file", "title", "new",
"sightings"}. Run it from inside any checkout of the repo.

A design finding is a bead outside every epic, a task labeled `design`, one for each problem. A problem is named by its
file and its title, ignoring case and spacing, which the finding keeps in its `design.problem` metadata. A problem with
no open design finding becomes a new one. A problem that has one gets a sighting: a comment on the finding that names
the epic and the line, so the finding's comments are its sightings, the first one written when the finding is filed.
A report that names one problem twice counts one sighting. Everything is written to bd with BEADS_ACTOR set to jidoka.

Exit codes:
  0  the report was settled.
  1  the report is unusable or a bd command failed, with the reason on stderr; nothing is written when the report is
     unusable.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import repo_settings
from commands import CommandError, bd_comments, bd_list, env_as_factory, metadata_of, run
from epic_task import file_outside
from report_text import ReportError, listed_report, located_texts, shortened_title

DESIGN_LABEL = "design"
PROBLEM_KEY = "design.problem"
SIGHTING_PREFIX = "Sighting: "


class DesignFindingError(Exception):
    """A reason a report cannot be settled, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Problem:
    """A problem a review met in old code, at a line of a file."""
    file: str
    line: int
    title: str
    note: str

    @property
    def key(self) -> str:
        return f"{self.file}::{' '.join(self.title.lower().split())}"

    @property
    def bead_title(self) -> str:
        return shortened_title(f"{self.title} in {self.file}")

    def sighting(self, epic: str) -> str:
        return f"{SIGHTING_PREFIX}{epic} met this at {self.file}:{self.line}. {self.note}"

    def description(self) -> str:
        return "\n".join(["## What", "",
                          f"A review met this problem in old code at {self.file}:{self.line}:", "",
                          f"{self.title}: {self.note}", "",
                          "Each comment on this bead is a sighting of the problem in an epic's review."])


@dataclass(frozen=True)
class Settled:
    """A problem and the design finding that holds it: whether this report filed it, and how many sightings it has."""
    bead: str
    problem: Problem
    new: bool
    sightings: int

    def fields(self) -> dict:
        return {"bead": self.bead, "file": self.problem.file, "title": self.problem.title, "new": self.new,
                "sightings": self.sightings}


def problem_of(value: object, number: int) -> Problem:
    texts, line = located_texts(value, f"finding {number} of the report", "a file, line, title and note")
    return Problem(texts["file"], line, texts["title"], texts["note"])


def read_report(path: Path) -> list[Problem]:
    listed = listed_report(path, f"the report {path}", DesignFindingError)
    return [problem_of(each, number) for number, each in enumerate(listed, 1)]


def open_beads(main_tree: Path) -> list[tuple[str, dict]]:
    """The open design findings as the problem each keeps and its bead."""
    held = []
    for bead in bd_list(["--label", DESIGN_LABEL, "--type", "task", "--limit", "0"], main_tree):
        key = metadata_of(bead).get(PROBLEM_KEY)
        if isinstance(key, str):
            held.append((key, bead))
    return held


def open_findings(main_tree: Path) -> dict[str, str]:
    """The open design findings by the problem each keeps."""
    return {key: str(bead["id"]) for key, bead in open_beads(main_tree)}


def ranked_findings(files: list[str], main_tree: Path) -> list[dict]:
    """The open design findings about the files, or about any file when none is named, the most sighted first."""
    ranked = []
    for key, bead in open_beads(main_tree):
        file = key.split("::", 1)[0]
        if files and file not in files:
            continue
        bead_id = str(bead["id"])
        ranked.append({"bead": bead_id, "file": file, "title": str(bead.get("title", "")),
                       "sightings": sightings_of(bead_id, main_tree)})
    return sorted(ranked, key=lambda each: (-each["sightings"], each["bead"]))


def sightings_of(bead: str, main_tree: Path) -> int:
    return sum(1 for each in bd_comments(bead, main_tree) if str(each.get("text", "")).startswith(SIGHTING_PREFIX))


def file_finding(problem: Problem, main_tree: Path) -> str:
    bead = file_outside(problem.bead_title, problem.description(), None, [DESIGN_LABEL], main_tree)
    run(["bd", "update", bead, "--set-metadata", f"{PROBLEM_KEY}={problem.key}"], main_tree, env_as_factory())
    return bead


def settle(epic: str, problems: list[Problem], main_tree: Path) -> list[Settled]:
    """Files each distinct problem that has no open design finding, and writes the epic's sighting on every one."""
    held = open_findings(main_tree)
    settled = []
    for problem in {each.key: each for each in problems}.values():
        bead = held.get(problem.key)
        is_new = bead is None
        if bead is None:
            bead = file_finding(problem, main_tree)
        run(["bd", "comment", bead, problem.sighting(epic)], main_tree, env_as_factory())
        settled.append(Settled(bead, problem, is_new, sightings_of(bead, main_tree)))
    return settled


def print_open(files: list[str]) -> int:
    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), repo_settings.GIT_TIMEOUT_SECONDS)
        ranked = ranked_findings(files, main_tree)
    except (repo_settings.SettingsError, CommandError, OSError) as error:
        print(f"design_findings: {error}", file=sys.stderr)
        return 1
    print(json.dumps(ranked, indent=2))
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--open"]:
        return print_open(argv[1:])
    parser = argparse.ArgumentParser(prog="design_findings.py", description=__doc__.split("\n")[0])
    parser.add_argument("epic", help="the epic whose review met the problems")
    parser.add_argument("report", type=Path, help="the JSON list of problems")
    args = parser.parse_args(argv)
    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), repo_settings.GIT_TIMEOUT_SECONDS)
        settled = settle(args.epic, read_report(args.report), main_tree)
    except (DesignFindingError, ReportError, repo_settings.SettingsError, CommandError, OSError) as error:
        print(f"design_findings: {error}", file=sys.stderr)
        return 1
    print(json.dumps([each.fields() for each in settled], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
