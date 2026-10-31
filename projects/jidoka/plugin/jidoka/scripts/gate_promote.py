"""Promoting a holdout at the acceptance gate: the human keeps a scenario the epic's holdouts hold, and landing files
it as a planning bead for the coaching skill to start from.

`gate.promoted` on the epic lists the holdouts the human promoted, each as `{"holdout": <number>, "bead": <id or
null>}`. The number is the holdout's place among all the epic's holdouts, counted from 1, as holdouts.py numbers them.
The bead is null until landing files it, and a rerun of the landing files only the holdouts that have none, so a
partial landing makes no second bead. The planning bead has no parent, carries the human label and holds the scenario
in its description. Holdouts that were not promoted retire at landing with the rest.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from commands import HUMAN_LABEL, CommandError, metadata_of, run, set_metadata
from epic_task import file_outside
from holdouts import Holdout, of_epic

PROMOTED_KEY = "gate.promoted"


class PromoteError(Exception):
    """A reason a holdout cannot be promoted, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Promotion:
    """A promoted holdout, by its number, and the planning bead landing filed for it, None until then."""
    holdout: int
    bead: str | None


def promotions_of(shown: dict) -> list[Promotion]:
    """The promotions the epic records, in the order they were made."""
    value = metadata_of(shown).get(PROMOTED_KEY)
    if value in (None, ""):
        return []
    try:
        listed = json.loads(value) if isinstance(value, str) else value
        return [Promotion(int(each["holdout"]), None if each["bead"] is None else str(each["bead"]))
                for each in listed]
    except (ValueError, KeyError, TypeError) as error:
        raise PromoteError(f"the {PROMOTED_KEY} metadata of the epic cannot be read: {error!r}") from error


def recorded(promotions: list[Promotion]) -> list[str]:
    text = json.dumps([{"holdout": each.holdout, "bead": each.bead} for each in promotions])
    return set_metadata((PROMOTED_KEY, text))


def promote(shown: dict, number: int, env: dict[str, str], main_tree: Path) -> str:
    """Records the promotion of the numbered holdout of the epic, given as bd show prints it, and returns the line
    that says so; promoting one twice changes nothing."""
    epic = str(shown["id"])
    holdouts = of_epic(shown)
    if not 1 <= number <= len(holdouts):
        held = f"{len(holdouts)} holdout{'' if len(holdouts) == 1 else 's'}" if holdouts else "no holdouts"
        raise PromoteError(f"{epic} holds {held}, so there is no holdout {number} to promote")
    kept = promotions_of(shown)
    if number not in {each.holdout for each in kept}:
        run(["bd", "update", epic, *recorded([*kept, Promotion(number, None)])], main_tree, env)
    return f"Holdout {number} of {epic} is promoted. Landing files a planning bead that holds its scenario."


def rows(shown: dict) -> list[dict]:
    """What `items` prints for each holdout of the epic: its number, its app, its scenario and whether the human
    promoted it."""
    promoted = {each.holdout for each in promotions_of(shown)}
    return [{"number": number, "app": holdout.app, "scenario": holdout.scenario, "promoted": number in promoted}
            for number, holdout in enumerate(of_epic(shown), start=1)]


def description_of(epic: str, title: str, number: int, holdout: Holdout) -> str:
    return (f"The human promoted holdout {number} of {epic}, {title}, at the acceptance gate. Planning turns the "
            f"scenario into acceptance specs with the human, with the coaching skill.\n\nApp: {holdout.app}\n\n"
            f"Scenario:\n\n{holdout.scenario}")


def file_promoted(shown: dict, env: dict[str, str], main_tree: Path) -> list[str]:
    """Files a planning bead for each promoted holdout of the epic, given as bd show prints it, that has none, records
    its id on the epic as soon as it exists, and returns the steps that failed. A failed step leaves the holdouts in
    place, so a rerun files what is missing."""
    epic = str(shown["id"])
    title = str(shown.get("title") or "")
    holdouts = of_epic(shown)
    kept = promotions_of(shown)
    failed: list[str] = []
    for index, promotion in enumerate(kept):
        if promotion.bead is not None:
            continue
        if not 1 <= promotion.holdout <= len(holdouts):
            failed.append(f"file the planning bead of holdout {promotion.holdout}: the epic holds no such holdout")
            continue
        holdout = holdouts[promotion.holdout - 1]
        try:
            bead = file_outside(f"Holdout {promotion.holdout} of {title}, promoted to acceptance specs",
                                description_of(epic, title, promotion.holdout, holdout), epic, [HUMAN_LABEL],
                                main_tree)
            kept[index] = Promotion(promotion.holdout, bead)
            run(["bd", "update", epic, *recorded(kept)], main_tree, env)
        except CommandError as error:
            failed.append(f"file the planning bead of holdout {promotion.holdout}: {error}")
    return failed
