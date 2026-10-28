"""The caps on a lap, the wall clocks of its stages, and the brake on an epic.

The scheduler imports it; no command line runs it. The caps of a lap park one
task and never stop the factory: three build tries, two send-backs from the
checks together, three cutoffs of one stage, and two tries of the merge
worker. The validation worker has the try cap too, and its cap parks the
epic; validation.py counts those runs. A stop is no cutoff: a lap an earlier
session left with no worker ends interrupted, and its task gets a new lap,
without counting one.

A stage that runs past its wall clock ends cut off. lap_record.py holds the
wall clocks, the record of when a stage started and the check against them.

The brake is the epic's record of laps that parked in a row at one stage with
no merge between. The epic's metadata holds `brake.stage` and `brake.laps`.
At three laps the brake is on: no new lap opens, while the laps already
open run on. The scheduler then records the ids of the epic's beads as
`brake.beads`, and the brake lifts when the epic holds a bead that is not
among them, the fix task the manager filed.

Every record above lives in a bead's metadata, so the module also holds `metadata_of`, the one reader of it that the
scripts share. It imports only commands.py, so any script can import it without a cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commands import bd_show, env_as_factory, run, set_metadata

TRY_CAP = 3
MERGE_TRY_CAP = 2
SEND_BACK_CAP = 2
CUTOFF_CAP = 3
BRAKE_LAPS = 3

BRAKE_STAGE_KEY = "brake.stage"
BRAKE_LAPS_KEY = "brake.laps"
BRAKE_BEADS_KEY = "brake.beads"
NONE_YET = 0


def metadata_of(bead: dict) -> dict:
    """The metadata object bd shows on the bead, or an empty one when it shows none."""
    metadata = bead.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


class NotAWholeNumber(ValueError):
    """A metadata value that should hold a whole number and holds something else."""


def whole_number_in(metadata: dict, key: str) -> int | None:
    """The whole number the metadata holds under the key, or None when it holds nothing.

    A value that is not a whole number raises NotAWholeNumber. A caller that counts from zero takes None as zero, and
    a caller that needs the value takes None as an error.
    """
    value = metadata.get(key)
    if value is None or value == "":
        return None
    try:
        return int(str(value))
    except ValueError as error:
        raise NotAWholeNumber(f"the {key} metadata holds {value!r} where it needs a whole number") from error


def count_in(metadata: dict, key: str) -> int:
    """The whole number the metadata holds under the key, or none yet when it holds nothing."""
    counted = whole_number_in(metadata, key)
    return NONE_YET if counted is None else counted


@dataclass(frozen=True)
class Brake:
    """The laps in a row that parked at one stage, as the epic records them."""
    stage: str
    laps: int

    @property
    def is_on(self) -> bool:
        return self.laps >= BRAKE_LAPS

    def fields(self) -> dict:
        return {"stage": self.stage, "laps": self.laps}


def brake_of(epic: dict) -> Brake:
    metadata = metadata_of(epic)
    return Brake(str(metadata.get(BRAKE_STAGE_KEY) or ""), count_in(metadata, BRAKE_LAPS_KEY))


def write_brake(epic_id: str, brake: Brake, beads: str, main_tree: Path) -> None:
    run(["bd", "update", epic_id, *set_metadata((BRAKE_STAGE_KEY, brake.stage), (BRAKE_LAPS_KEY, brake.laps),
                                                (BRAKE_BEADS_KEY, beads))], main_tree, env_as_factory())


def note_parked_lap(epic_id: str, stage: str, main_tree: Path) -> None:
    """Counts a lap that parked at the stage: one more in a row when the last also parked there, else the first."""
    shown = bd_show(epic_id, main_tree) or {}
    before = brake_of(shown)
    laps = before.laps + 1 if before.stage == stage else 1
    beads = str(metadata_of(shown).get(BRAKE_BEADS_KEY) or "") if before.is_on and before.stage == stage else ""
    write_brake(epic_id, Brake(stage, laps), beads, main_tree)


def note_merge(epic_id: str, main_tree: Path) -> None:
    """A merge ends the run of parked laps, and lifts the brake with it."""
    shown = bd_show(epic_id, main_tree) or {}
    if brake_of(shown).laps != NONE_YET:
        write_brake(epic_id, Brake("", NONE_YET), "", main_tree)


def brake_after_new_beads(epic: dict, bead_ids: list[str], main_tree: Path) -> Brake:
    """The epic's brake as of now, recording the beads it holds the first time it sees the brake on.

    A bead the epic holds that the record lacks is the fix task, and it lifts the brake.
    """
    brake = brake_of(epic)
    if not brake.is_on:
        return brake
    known = str(metadata_of(epic).get(BRAKE_BEADS_KEY) or "")
    if not known:
        write_brake(str(epic["id"]), brake, ",".join(bead_ids), main_tree)
        return brake
    if set(bead_ids) - set(known.split(",")):
        lifted = Brake("", NONE_YET)
        write_brake(str(epic["id"]), lifted, "", main_tree)
        return lifted
    return brake
