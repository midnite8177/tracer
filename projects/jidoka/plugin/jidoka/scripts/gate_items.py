"""The items the acceptance gate lists for the human beside the commits and figures: the assumptions, the public API
changes and the open beads found outside the epic.

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

from commands import bd_comments, bd_list
from epic_reader import child_ids, shown_beads
from epic_task import DISCOVERED_FROM

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
                                             enumerate(self.assumptions, 1))]
        if self.api_changes:
            lines += ["", "Public API changes:", *(f"- {each.row()}" for each in self.api_changes)]
        if self.outside:
            lines += ["", "Found outside the epic, still open:",
                      *(f"- {each.bead} {each.title}, found in {each.found_in}" for each in self.outside)]
        return lines


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


def assumptions_of(epic: str, title: str, main_tree: Path) -> list[Noted]:
    """The assumptions on the epic and its children; the gate numbers them from 1 in this order."""
    return notes_of(epic, title, child_ids(epic, main_tree), main_tree)[0]


def outside_of(epic: str, main_tree: Path) -> list[FoundOutside]:
    return found_outside(epic, child_ids(epic, main_tree), main_tree)


def gate_items(epic: str, title: str, main_tree: Path) -> GateItems:
    """Reads the assumptions, the public API changes and the beads found outside the epic from bd."""
    children = child_ids(epic, main_tree)
    assumptions, api_changes = notes_of(epic, title, children, main_tree)
    return GateItems(assumptions, api_changes, found_outside(epic, children, main_tree))
