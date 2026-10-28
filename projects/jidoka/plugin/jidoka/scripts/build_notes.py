"""Posts the assumptions and the public API changes a build worker reports, where the acceptance gate reads them.

The scheduler imports it; no command line runs it. A build worker never posts a comment. It lists what it assumed and
what it changed in a library's public API in the JSON file `build-notes.json` in its worktree's scratch folder: an
object whose `assumptions` and `public_api_changes` are each a list of plain sentences, and either may be left out. A
build that ended done has each entry posted on its task as a comment that starts with `assumption:` or
`public API change:`, which gate_items.py lists.
"""
from __future__ import annotations

from pathlib import Path

from commands import env_as_factory, run
from gate_items import API_CHANGE_PREFIX, ASSUMPTION_PREFIX
from report_text import parsed_report

NOTES_REPORT = "build-notes.json"
ASSUMPTIONS = "assumptions"
API_CHANGES = "public_api_changes"


class NotesError(Exception):
    """A reason a build-notes report cannot be posted, worded for the worker that writes the next one."""


def entries_of(report: dict, key: str) -> list[str]:
    entries = report.get(key, [])
    if not isinstance(entries, list) or not all(isinstance(entry, str) and entry.strip() for entry in entries):
        raise NotesError(f"`{key}` in {NOTES_REPORT} must be a list of non-empty strings")
    return [entry.strip() for entry in entries]


def read_comments(scratch: Path) -> list[str]:
    """The comments the report asks for, assumptions first; none when the build left no report, and NotesError when
    it is unusable."""
    path = scratch / NOTES_REPORT
    if not path.exists():
        return []
    report = parsed_report(path, f"the build-notes report {path}", NotesError)
    if not isinstance(report, dict):
        raise NotesError(f"the build-notes report {path} must be a JSON object with {ASSUMPTIONS} and {API_CHANGES}")
    return [*(f"{ASSUMPTION_PREFIX} {entry}" for entry in entries_of(report, ASSUMPTIONS)),
            *(f"{API_CHANGE_PREFIX} {entry}" for entry in entries_of(report, API_CHANGES))]


def post_notes(task: str, scratch: Path, main_tree: Path) -> None:
    """Posts each entry of the report on the task under the actor jidoka and removes the report. A report that is
    unusable posts nothing and raises NotesError."""
    comments = read_comments(scratch)
    env = env_as_factory()
    for comment in comments:
        run(["bd", "comment", task, comment], main_tree, env)
    (scratch / NOTES_REPORT).unlink(missing_ok=True)
