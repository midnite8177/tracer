"""The gate comment, and the items it lists for the human beside the commits and figures: the assumptions, the public
API changes and the open beads found outside the epic. `reach_the_gate` writes the comment and puts the epic at the
gate; the validation calls it, and the gate page lists the same commits through `merged_commits`.

An assumption and a public API change are comments on the epic or one of its children. A comment that starts with
`assumption:` is an assumption, as bench work posts one, and a comment that starts with `public API change:` names a
change to a library's public API in plain words. The gate numbers the assumptions, the epic's own first and then each
child's in the order bd lists the children, so the human can name one by its number. A bead found outside the epic
is a bead that is not closed, has no parent, and is linked discovered-from to the epic or to one of its children; the
review's large findings and a lap's or a pass's discovered work outside the epic are such beads.

Each part is a list of lines that is empty when there is nothing to show, as the gate comment's other parts are.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cleanup
import review
from commands import bd_comments, bd_list, bd_show, run
from epic_reader import child_ids, shown_beads
from epic_task import DISCOVERED_FROM
from epics import GATE_STATE_KEY, WAITING
from pass_support import MAIN_BRANCH, park_epic

GATE_COMMENT_HEADING = "Acceptance gate:"
ASSUMPTION_PREFIX = "assumption:"
API_CHANGE_PREFIX = "public API change:"
CLOSED = "closed"


@dataclass(frozen=True)
class Noted:
    """A comment of one kind on the epic or one of its children: the bead, its title, and the text after the
    prefix."""
    bead: str
    title: str
    text: str

    def row(self) -> str:
        return f"{self.bead} {self.title}: {self.text}"


@dataclass(frozen=True)
class FoundOutside:
    """An open bead outside the epic, and the bead of the epic it was found in."""
    bead: str
    title: str
    found_in: str


@dataclass(frozen=True)
class GateItems:
    """What the gate lists about the epic's beads, read from bd in one go."""
    assumptions: list[Noted]
    api_changes: list[Noted]
    outside: list[FoundOutside]

    def lines(self) -> list[str]:
        lines: list[str] = []
        if self.assumptions:
            lines += ["", "Assumptions:", *(f"{number}. {each.row()}" for number, each in
                                             numbered(self.assumptions))]
        if self.api_changes:
            lines += ["", "Public API changes:", *(f"- {each.row()}" for each in self.api_changes)]
        if self.outside:
            lines += ["", "Found outside the epic, still open:",
                      *(f"- {each.bead} {each.title}, found in {each.found_in}" for each in self.outside)]
        return lines


def numbered(assumptions: list[Noted]) -> list[tuple[int, Noted]]:
    """The assumptions with the number the gate gives each, from 1, which the human names in `wrong`."""
    return list(enumerate(assumptions, 1))


def noted(bead: str, title: str, comments: list[dict], prefix: str) -> list[Noted]:
    texts = (str(each.get("text") or "").strip() for each in comments)
    return [Noted(bead, title, text[len(prefix):].strip()) for text in texts if text.startswith(prefix)]


def found_outside(epic: str, children: list[str], main_tree: Path) -> list[FoundOutside]:
    """The open beads with no parent that are linked discovered-from to the epic or one of its children."""
    ours = {epic, *children}
    candidates = [str(bead["id"]) for bead in bd_list(["--all", "--limit", "0"], main_tree)
                  if bead.get("status") != CLOSED and not bead.get("parent") and str(bead.get("id")) not in ours]
    found = []
    for bead in shown_beads(candidates, main_tree):
        origins = [str(link.get("id")) for link in bead.get("dependencies") or []
                   if link.get("dependency_type") == DISCOVERED_FROM and str(link.get("id")) in ours]
        if origins:
            found.append(FoundOutside(str(bead["id"]), str(bead.get("title") or ""), origins[0]))
    return found


def notes_of(epic: str, title: str, children: list[str], main_tree: Path) -> tuple[list[Noted], list[Noted]]:
    """The assumptions and the public API changes on the epic and its children, in the order the gate lists them."""
    beads = [(epic, title), *((str(each["id"]), str(each.get("title") or ""))
                              for each in shown_beads(children, main_tree))]
    assumptions: list[Noted] = []
    api_changes: list[Noted] = []
    for bead, bead_title in beads:
        comments = bd_comments(bead, main_tree)
        assumptions += noted(bead, bead_title, comments, ASSUMPTION_PREFIX)
        api_changes += noted(bead, bead_title, comments, API_CHANGE_PREFIX)
    return assumptions, api_changes


def numbered_assumptions(epic: str, title: str, main_tree: Path) -> list[tuple[int, Noted]]:
    """The assumptions on the epic and its children, each with the number the gate comment gives it."""
    return numbered(notes_of(epic, title, child_ids(epic, main_tree), main_tree)[0])


def assumption(epic: str, title: str, number: int, main_tree: Path, error: type[Exception]) -> Noted:
    """The assumption the gate comment numbers so; raises the caller's error when the epic has none with that number."""
    listed = numbered_assumptions(epic, title, main_tree)
    for each_number, each in listed:
        if each_number == number:
            return each
    raise error(f"{epic} has {len(listed)} assumption{'' if len(listed) == 1 else 's'}, so there is no assumption "
                f"{number}")


def outside_of(epic: str, main_tree: Path) -> list[FoundOutside]:
    return found_outside(epic, child_ids(epic, main_tree), main_tree)


def gate_items(epic: str, title: str, main_tree: Path) -> GateItems:
    """Reads the assumptions, the public API changes and the beads found outside the epic from bd."""
    children = child_ids(epic, main_tree)
    assumptions, api_changes = notes_of(epic, title, children, main_tree)
    return GateItems(assumptions, api_changes, found_outside(epic, children, main_tree))


def merged_commits(branch_head: str, main_tree: Path) -> list[str]:
    """One line for each commit the epic branch holds that main lacks, merge commits left out, oldest first."""
    listed = run(["git", "log", "--no-merges", "--reverse", "--format=%h %s", f"{MAIN_BRANCH}..{branch_head}"],
                 main_tree, None)
    return listed.splitlines()


def reach_the_gate(epic: str, branch: str, validated_head: str, figures: list[str], hand_run: list[str],
                   main_tree: Path) -> None:
    """Puts the epic at the acceptance gate: one comment that starts with the heading and lists the commits the epic
    branch holds that main lacks, the validation's figures, the tests the test cleanup removed, the review's findings
    of low confidence, the assumptions, the public API changes, the open beads found outside the epic and the
    hand-run lines, then gate.state waiting and the human label, last, so a labeled epic always has its comment."""
    shown = bd_show(epic, main_tree)
    notes = [*cleanup.removed_lines(shown), *review.low_confidence_lines(shown),
             *gate_items(epic, str(shown.get("title") or ""), main_tree).lines()] if shown is not None else []
    lines = [f"{GATE_COMMENT_HEADING} {epic} waits for the human, on the epic branch {branch} at {validated_head}.",
             "", "Merged into the epic branch:", *(f"- {commit}" for commit in merged_commits(validated_head, main_tree)),
             "", *figures, *notes, *hand_run,
             "", f"/jidoka:accept {epic} writes the review guide page and takes the human's choice."]
    park_epic(epic, "\n".join(lines), {GATE_STATE_KEY: WAITING}, main_tree)
