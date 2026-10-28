"""Which epics the factory holds and which of them run, as bd shows them.

The scripts that tell the human, beat the heartbeat and print the status read the epics through this module. An epic
runs when it is open, carries the `factory` label, and is neither parked on the human nor at the acceptance gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import gate
import park
from bench import FACTORY_LABEL
from caps import metadata_of
from commands import bd_show, run
from epic_reader import CLOSED, EPIC_TYPE


class EpicsError(Exception):
    """A reason the epics cannot be read, worded for the person who reads stderr."""


def shown_or_refuse(bead: str, main_tree: Path) -> dict:
    shown = bd_show(bead, main_tree)
    if shown is None:
        raise EpicsError(f"bd show printed nothing usable for {bead}")
    return shown


def labels_of(shown: dict) -> list[str]:
    return [str(label) for label in shown.get("labels") or []]


def is_closed(shown: dict) -> bool:
    return shown.get("status") == CLOSED


def at_the_gate(shown: dict) -> bool:
    return metadata_of(shown).get(gate.GATE_STATE_KEY) == gate.WAITING


def epics_of(main_tree: Path) -> list[dict]:
    """Every epic of the repo as bd shows it, by id."""
    listing = run(["bd", "list", "--all", "--limit", "0", "--json"], main_tree, None)
    try:
        listed = json.loads(listing or "[]")
    except ValueError as error:
        raise EpicsError(f"bd list did not print JSON: {listing.strip()[:200]!r}") from error
    ids = sorted(str(item["id"]) for item in listed
                 if isinstance(item, dict) and item.get("id") and item.get("issue_type") == EPIC_TYPE)
    return [shown_or_refuse(epic, main_tree) for epic in ids]


def is_running(shown: dict) -> bool:
    """True for an open epic the factory holds that is neither parked nor at the gate."""
    labels = labels_of(shown)
    return (FACTORY_LABEL in labels and park.HUMAN_LABEL not in labels and not is_closed(shown)
            and not at_the_gate(shown))


def running_epics(main_tree: Path) -> list[str]:
    """The ids of the epics that run, by id."""
    return [str(shown["id"]) for shown in epics_of(main_tree) if is_running(shown)]
