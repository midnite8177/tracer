"""The caps on a lap, the wall clocks of its stages, and the brake on an epic.

The scheduler imports it; no command line runs it. The caps of a lap park one
task and never stop the factory: three build tries, two send-backs from the
checks together, three cutoffs of one stage, and two tries of the merge
worker. The validation worker has the try cap too, and its cap parks the
epic; holdouts_run.py counts those runs. A stop is no cutoff: a lap an earlier
session left with no worker ends interrupted, and its task gets a new lap,
without counting one.

`count_against_cap` is the one count of a try, a cutoff, a send-back or a run against its cap.

A stage that runs past its wall clock ends cut off. lap_record.py holds the
wall clocks, the record of when a stage started and the check against them.

The brake is the epic's record of laps that parked in a row at one stage with
no merge between. The epic's metadata holds `brake.stage` and `brake.laps`.
At three laps the brake is on: no new lap opens, while the laps already
open run on. The scheduler then records the ids of the epic's beads as
`brake.beads`, and the brake lifts when the epic holds a bead that is not
among them, the fix task the manager filed.

Every record above lives in a bead's metadata, which commands.py reads and writes.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from commands import NONE_YET, bd_show, count_in, env_as_factory, metadata_of, run, set_metadata

TRY_CAP = 3
MERGE_TRY_CAP = 2
SEND_BACK_CAP = 2
CUTOFF_CAP = 3
BRAKE_LAPS = 3

BRAKE_STAGE_KEY = "brake.stage"
BRAKE_LAPS_KEY = "brake.laps"
BRAKE_BEADS_KEY = "brake.beads"


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


def count_against_cap(bead: str, number: int, cap: int, park: Callable[[], None], comment: str,
                      recording: list[str], main_tree: Path) -> bool:
    """Counts one more against a cap on the bead. A number that reaches the cap calls `park` and writes nothing
    else; a lower one posts the comment and records the count with the `bd update` arguments. Returns True when it
    parked."""
    if number >= cap:
        park()
        return True
    env = env_as_factory()
    run(["bd", "comment", bead, comment], main_tree, env)
    run(["bd", "update", bead, *recording], main_tree, env)
    return False


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
