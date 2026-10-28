"""Sending an epic back from the acceptance gate: the human's notes, the send-back worker's proposals, and the tasks.

A note is one problem the human sees, in the human's words. A note pinned to a diff line is written
`<file>:<line>: <text>`; any other note is its text. The notes are numbered from 1 in the order they are given.

The send-back worker reads the notes and the epic, and writes one proposal for each note to a JSON file: a list of
objects with
  note   the number of the note it answers.
  title  the new task's title.
  demo   the task's Demo line.
  seams  the task's Seams line.
  area   the area the task touches.
  track  `simple` or `full`.
The human confirms or changes the proposals before this module files them. A proposal list that leaves a note
unanswered, answers a note twice or answers one that does not exist is refused, and nothing is filed.

Each proposal becomes a task in the epic, with the track and the area its proposal names, and a description whose
What section holds the note, and the file and line it is pinned to.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from epic_task import NewTask, file_task
from lap_record import FULL_TRACK, SIMPLE_TRACK
from report_text import listed_report

TRACKS = (SIMPLE_TRACK, FULL_TRACK)
PINNED_NOTE = re.compile(r"(?P<file>\S+?):(?P<line>[1-9][0-9]*): (?P<text>.+)", re.DOTALL)
SENT_BACK_PREFIX = "Sent back at the acceptance gate"


class SendBackError(Exception):
    """A reason the send back files nothing, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Note:
    """One problem the human found, and the file and line of the diff it is pinned to when it is pinned."""
    number: int
    text: str
    file: str | None
    line: int | None

    @property
    def where(self) -> str | None:
        return None if self.file is None else f"{self.file}, line {self.line}"


@dataclass(frozen=True)
class Proposal:
    """The task a send-back worker proposes for one note."""
    note: int
    title: str
    demo: str
    seams: str
    area: str
    track: str


@dataclass(frozen=True)
class Filed:
    """A note and the task it became."""
    note: Note
    task: str
    proposal: Proposal


def notes_of(given: list[str]) -> list[Note]:
    """The notes as the human wrote them, numbered from 1; a send back needs at least one."""
    if not given:
        raise SendBackError("a send back needs at least one --note, one for each problem")
    notes = []
    for number, text in enumerate(given, 1):
        pinned = PINNED_NOTE.fullmatch(text.strip())
        if not text.strip():
            raise SendBackError(f"note {number} is empty")
        if pinned is None:
            notes.append(Note(number, text.strip(), None, None))
        else:
            notes.append(Note(number, pinned["text"].strip(), pinned["file"], int(pinned["line"])))
    return notes


def text_in(item: dict, field: str, where: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SendBackError(f"{where} needs a {field} that is a non-empty string")
    return value.strip()


def proposal_of(item: object, position: int) -> Proposal:
    where = f"proposal {position}"
    if not isinstance(item, dict):
        raise SendBackError(f"{where} must be an object with a note, a title, a demo, seams, an area and a track")
    number = item.get("note")
    if isinstance(number, bool) or not isinstance(number, int):
        raise SendBackError(f"{where} needs a note that is the number of a note")
    track = text_in(item, "track", where)
    if track not in TRACKS:
        raise SendBackError(f"{where} has the track {track}, and a track is {' or '.join(TRACKS)}")
    return Proposal(number, text_in(item, "title", where), text_in(item, "demo", where),
                    text_in(item, "seams", where), text_in(item, "area", where), track)


def proposals_for(notes: list[Note], report: Path) -> list[Proposal]:
    """The send-back worker's proposals, one for each note and in the order of the notes."""
    listed = listed_report(report, f"the send-back worker's proposals {report}", SendBackError)
    proposals = [proposal_of(item, position) for position, item in enumerate(listed, 1)]
    numbers = [each.note for each in proposals]
    for note in notes:
        if numbers.count(note.number) != 1:
            raise SendBackError(f"note {note.number} needs exactly one proposal, and the report holds "
                                f"{numbers.count(note.number)}")
    stray = sorted(set(numbers) - {note.number for note in notes})
    if stray:
        raise SendBackError(f"the report answers note {stray[0]}, and the human gave {len(notes)} "
                            f"note{'' if len(notes) == 1 else 's'}")
    return sorted(proposals, key=lambda each: each.note)


def description_of(epic: str, note: Note, proposal: Proposal) -> str:
    what = [note.text, "", f"It is pinned to {note.where} of the epic's diff."] if note.where else [note.text]
    return "\n".join(["## What", "", *what, "", f"The human sent {epic} back from the acceptance gate with this note.",
                      "", "## Demo", "", proposal.demo, "", "## Seams", "", proposal.seams])


def file_tasks(epic: str, notes: list[Note], proposals: list[Proposal], env: dict[str, str],
               main_tree: Path) -> list[Filed]:
    """Files one task in the epic for each note, in the order of the notes, under the actor of `env`."""
    return [Filed(note, file_task(epic, NewTask(proposal.title, description_of(epic, note, proposal), proposal.area,
                                                proposal.track), None, env, main_tree), proposal)
            for note, proposal in zip(notes, proposals)]


def comment_of(epic: str, filed: list[Filed]) -> str:
    """The comment on the epic that pairs each note with the task it became."""
    lines = [f"{SENT_BACK_PREFIX} with {len(filed)} note{'' if len(filed) == 1 else 's'}:"]
    for each in filed:
        pinned = f" ({each.note.where})" if each.note.where else ""
        lines.append(f"{each.note.number}. {each.note.text}{pinned} -> {each.task} {each.proposal.title}")
    lines += ["", f"{epic} leaves the gate. Its pass count starts again, and the next pass runs these tasks."]
    return "\n".join(lines)


def printed_lines(epic: str, filed: list[Filed]) -> str:
    """What the script prints: the new tasks in the order of the notes, and the step that runs them."""
    return "\n".join([f"{epic} is sent back with {len(filed)} new task{'' if len(filed) == 1 else 's'}:",
                      *(f"{each.note.number}. {each.task} {each.proposal.title}" for each in filed),
                      f"Its pass count starts again. Start the factory on {epic} to run the next pass."])
