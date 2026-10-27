"""The caps on a lap, the wall clocks of its stages, and the brake on an epic.

The scheduler imports it; no command line runs it. A cap parks one task and
never stops the factory. The caps of a lap are three build tries, two
send-backs from the checks together, three cutoffs of one stage, and two
tries of the merge worker. The human's own stop is no cutoff: a lap an
earlier session left with no worker goes back to its stage without counting
one.

A stage that runs past its wall clock ends cut off: 60 minutes for the build
and 30 for every other stage. The lap records when its stage started as
`lap.started`, in seconds since the epoch, and the scheduler measures from
that.

The brake is the epic's record of laps that parked in a row at one stage with
no merge between. The epic's metadata holds `brake.stage` and `brake.laps`.
At three laps the brake is on: no new lap opens, while the laps already
open run on. The scheduler then records the ids of the epic's beads as
`brake.beads`, and the brake lifts when the epic holds a bead that is not
among them, the fix task the manager filed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commands import bd_show, env_as_factory, run

TRY_CAP = 3
MERGE_TRY_CAP = 2
SEND_BACK_CAP = 2
CUTOFF_CAP = 3
BUILD_WALL_CLOCK_SECONDS = 60 * 60
OTHER_WALL_CLOCK_SECONDS = 30 * 60
BRAKE_LAPS = 3

BUILD = "build"
STARTED_KEY = "lap.started"
SEND_BACKS_KEY = "lap.sendbacks"
MERGE_TRIES_KEY = "lap.mergetries"
MERGE_BASE_KEY = "lap.mergebase"
MERGE_WHY_KEY = "lap.mergewhy"
CUTOFFS_KEY_PREFIX = "lap.cutoffs."
BRAKE_STAGE_KEY = "brake.stage"
BRAKE_LAPS_KEY = "brake.laps"
BRAKE_BEADS_KEY = "brake.beads"
NONE_YET = 0


def cutoffs_key(stage: str) -> str:
    return f"{CUTOFFS_KEY_PREFIX}{stage}"


def wall_clock_seconds(stage: str) -> int:
    return BUILD_WALL_CLOCK_SECONDS if stage == BUILD else OTHER_WALL_CLOCK_SECONDS


def is_past_wall_clock(stage: str, started: int | None, now: int) -> bool:
    """True when the stage started more than its wall clock ago; a lap that records no start never is."""
    return started is not None and now - started > wall_clock_seconds(stage)


def count_in(metadata: dict, key: str) -> int:
    """The whole number the metadata holds under the key, or none yet when it holds nothing usable."""
    try:
        return int(str(metadata.get(key)))
    except ValueError:
        return NONE_YET


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
    metadata = epic.get("metadata") if isinstance(epic.get("metadata"), dict) else {}
    return Brake(str(metadata.get(BRAKE_STAGE_KEY) or ""), count_in(metadata, BRAKE_LAPS_KEY))


def write_brake(epic_id: str, brake: Brake, beads: str, main_tree: Path) -> None:
    run(["bd", "update", epic_id, "--set-metadata", f"{BRAKE_STAGE_KEY}={brake.stage}",
         "--set-metadata", f"{BRAKE_LAPS_KEY}={brake.laps}", "--set-metadata", f"{BRAKE_BEADS_KEY}={beads}"],
        main_tree, env_as_factory())


def note_parked_lap(epic_id: str, stage: str, main_tree: Path) -> None:
    """Counts a lap that parked at the stage: one more in a row when the last also parked there, else the first."""
    shown = bd_show(epic_id, main_tree) or {}
    before = brake_of(shown)
    laps = before.laps + 1 if before.stage == stage else 1
    metadata = shown.get("metadata") if isinstance(shown.get("metadata"), dict) else {}
    beads = str(metadata.get(BRAKE_BEADS_KEY) or "") if before.is_on and before.stage == stage else ""
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
    metadata = epic.get("metadata") if isinstance(epic.get("metadata"), dict) else {}
    known = str(metadata.get(BRAKE_BEADS_KEY) or "")
    if not known:
        write_brake(str(epic["id"]), brake, ",".join(bead_ids), main_tree)
        return brake
    if set(bead_ids) - set(known.split(",")):
        lifted = Brake("", NONE_YET)
        write_brake(str(epic["id"]), lifted, "", main_tree)
        return lifted
    return brake
