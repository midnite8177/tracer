"""Which epics the factory holds, which of them run, and the state of each, as bd shows them.

An epic's state is read from the human label, the `gate.state` metadata that puts it at the acceptance gate and the
`validation.holdouts` metadata that holds it for a run of its holdouts. This module names those two keys and their
values, and the scripts that write them import the names from here. The scheduler, the resume, and the scripts that
tell the human, beat the heartbeat and print the status read an epic's state through the module. An epic runs when it
is open, carries the `factory` label, and is neither parked on the human nor at the acceptance gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commands import FACTORY_LABEL, bd_list, is_labeled_for_human, labels_of, metadata_of, read_bead
from epic_reader import CLOSED, EPIC_TYPE

GATE_STATE_KEY = "gate.state"
WAITING = "waiting"
HOLDOUTS_PENDING_KEY = "validation.holdouts"
PENDING = "pending"


class EpicsError(Exception):
    """A reason the epics cannot be read, worded for the person who reads stderr."""


def is_closed(shown: dict) -> bool:
    return shown.get("status") == CLOSED


def at_the_gate(shown: dict) -> bool:
    return metadata_of(shown).get(GATE_STATE_KEY) == WAITING


def awaits_holdouts(shown: dict) -> bool:
    """True when the epic's suite passed and the run of its holdouts has not been settled."""
    return metadata_of(shown).get(HOLDOUTS_PENDING_KEY) == PENDING


RUNNING = "running"
PARKED = "parked"
AT_THE_GATE = "at the acceptance gate"


@dataclass(frozen=True)
class State:
    """What holds an epic: the human's label, the acceptance gate, and the run of its holdouts that its validation
    waits on."""
    labeled_for_human: bool
    at_the_gate: bool
    awaiting_holdouts: bool

    @property
    def name(self) -> str:
        """The state the human reads: at the gate, parked on the human, or running."""
        if self.at_the_gate:
            return AT_THE_GATE
        return PARKED if self.labeled_for_human else RUNNING

    @property
    def is_running(self) -> bool:
        return self.name == RUNNING

    @property
    def waits_on_nothing(self) -> bool:
        """True when neither the human, the gate nor a run of holdouts holds the epic."""
        return not (self.labeled_for_human or self.at_the_gate or self.awaiting_holdouts)


def state_of(shown: dict) -> State:
    return State(is_labeled_for_human(shown), at_the_gate(shown), awaits_holdouts(shown))


def epics_of(main_tree: Path) -> list[dict]:
    """Every epic of the repo that is not closed, as bd shows it, by id. The list says which epics are closed, so a
    closed one, of which a repo gathers more with every epic it lands, costs no bd show."""
    ids = sorted(str(item["id"]) for item in bd_list(["--all", "--limit", "0"], main_tree)
                 if item.get("id") and item.get("issue_type") == EPIC_TYPE and item.get("status") != CLOSED)
    return [read_bead(epic, main_tree) for epic in ids]


def is_running(shown: dict) -> bool:
    """True for an open epic the factory holds that is neither parked nor at the gate."""
    return FACTORY_LABEL in labels_of(shown) and not is_closed(shown) and state_of(shown).is_running


def running_epics(main_tree: Path) -> list[str]:
    """The ids of the epics that run, by id."""
    return [str(shown["id"]) for shown in epics_of(main_tree) if is_running(shown)]
