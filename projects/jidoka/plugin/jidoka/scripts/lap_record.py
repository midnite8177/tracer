"""A lap as its task's metadata records it.

This module owns the lap's metadata format: every key a lap is recorded under, the names of its stages, a reader for
each key and a writer for each move a lap makes. A writer that takes the lap returns the lap after the move and the
`--set-metadata` arguments of a `bd update` that records it, so the record and the lap in memory cannot drift, and
the caller can add a label or another argument to the same call. No other script spells a lap key
or the name of a lap's stage, so a change to how a lap is recorded stays in this file. The module also owns how a new
lap starts and is named, the wall clocks of its stages and the cap on its tries. The `merge` of gate.py names a
decision and the `merged` of watch.py names a change, and neither is a stage.

The scheduler decides what runs next and lap_stages.py settles how a stage ended. Both read a lap through this
module, so neither imports the other. The outcomes a report ends a stage with, and the scheduler's error, are in
lap_outcomes.py. The module also finds the task a lap worktree holds, from the worktree's branch, which the lap lists
and the rules read. It imports only caps.py, commands.py, epic_branch.py, lap_outcomes.py and worktrees.py, so any
script can import it without a cycle.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

import caps
from commands import (FACTORY_ACTOR, NONE_YET, SCRATCH_FOLDER, NotAWholeNumber, bd_show, capture, count_in,
                      metadata_of, set_metadata, whole_number_in)
from epic_branch import checked_out_branch
from lap_outcomes import BLOCKED, PASS, SchedulerError
from worktrees import stage_worktree

BUILD_WALL_CLOCK_SECONDS = 60 * 60
OTHER_WALL_CLOCK_SECONDS = 30 * 60
FIRST_LAP = 1
NO_TRIES = 0
LAP_FOLDER_PREFIX = "lap-"
RESEARCH = "research"
BUILD = "build"
APP_CHECK = "app-check"
SPEC_CHECK = "spec-check"
MERGE = "merge"
MERGED = "merged"
PARKED = "parked"
INTERRUPTED = "interrupted"
WORKER_STAGES = (RESEARCH, BUILD, APP_CHECK, SPEC_CHECK, MERGE)
RESTING_STAGES = (PARKED, BLOCKED, INTERRUPTED)
STAGE_WORDS = {SPEC_CHECK: "Spec check", APP_CHECK: "app check"}
SIMPLE_TRACK = "simple"
FULL_TRACK = "full"
LAP_BRANCH_PREFIX = "lap/"
REBASE_STATES = ("rebase-merge", "rebase-apply")
HEADS_PREFIX = "refs/heads/"
STAGE_KEY = "lap.stage"
NUMBER_KEY = "lap.number"
SLOT_KEY = "lap.slot"
TRIES_KEY = "lap.tries"
WORKSPACE_KEY = "lap.workspace"
BRANCH_KEY = "lap.branch"
AREA_KEY = "lap.area"
TRACK_KEY = "lap.track"
APP_KEY = "lap.app"
FILTER_KEY = "lap.filter"
SPEC_PASSED_KEY = "lap.speccheck"
FINDINGS_KEY = "lap.findings"
APP_FINDINGS_KEY = "lap.appfindings"
TEST_FAILURES_KEY = "lap.testfailures"
STARTED_KEY = "lap.started"
SEND_BACKS_KEY = "lap.sendbacks"
MERGE_TRIES_KEY = "lap.mergetries"
MERGE_BASE_KEY = "lap.mergebase"
MERGE_WHY_KEY = "lap.mergewhy"
CUTOFFS_KEY_PREFIX = "lap.cutoffs."
BRIEF_PREFIX = "research brief: "


@dataclass(frozen=True)
class Lap:
    """One task's lap as its metadata records it, or as this call opens it."""
    task: str
    title: str
    area: str
    number: int
    slot: int
    branch: str
    worktree: Path
    stage: str
    tries: int
    started: int | None
    cutoffs: int
    send_backs: int
    merge_tries: int
    merge_why: str
    merge_base: str
    track: str
    app: str
    test_filter: str
    spec_passed: bool
    findings: str
    app_findings: str
    test_failures: int

    @property
    def scratch(self) -> Path:
        return self.worktree / SCRATCH_FOLDER

    def fields(self) -> dict:
        return {"task": self.task, "title": self.title, "area": self.area, "lap": self.number, "slot": self.slot,
                "branch": self.branch, "worktree": str(self.worktree), "scratch": str(self.scratch),
                "track": self.track}


def counted(metadata: dict, key: str) -> int:
    """The whole number the lap metadata holds under the key, zero when it holds nothing."""
    try:
        return count_in(metadata, key)
    except NotAWholeNumber as error:
        raise SchedulerError(str(error)) from error


def required_number(metadata: dict, key: str) -> int:
    """The whole number the lap metadata holds under the key; a lap that holds none is an error."""
    try:
        number = whole_number_in(metadata, key)
    except NotAWholeNumber as error:
        raise SchedulerError(str(error)) from error
    if number is None:
        raise SchedulerError(f"the lap metadata holds no {key}, where it needs a whole number")
    return number


def started_of(metadata: dict) -> int | None:
    try:
        return int(str(metadata.get(STARTED_KEY)))
    except ValueError:
        return None


def track_of(metadata: dict) -> str:
    return FULL_TRACK if metadata.get(TRACK_KEY) == FULL_TRACK else SIMPLE_TRACK


def stage_of(metadata: dict) -> str:
    """The stage the metadata records, or an empty string for a task that never held a lap."""
    return str(metadata.get(STAGE_KEY) or "")


def number_of(metadata: dict) -> str:
    """The lap number as the metadata holds it, or an empty string when the task never held a lap."""
    return str(metadata.get(NUMBER_KEY) or "")


def previous_number(metadata: dict) -> int | None:
    """The number of the last lap the task held, or None when it never held one."""
    return None if metadata.get(NUMBER_KEY) is None else required_number(metadata, NUMBER_KEY)


def area_of(metadata: dict) -> str:
    return str(metadata.get(AREA_KEY) or "")


def branch_of(metadata: dict) -> str:
    return str(metadata.get(BRANCH_KEY) or "")


def workspace_of(metadata: dict) -> str:
    return str(metadata.get(WORKSPACE_KEY) or "")


def tries_in(metadata: dict) -> int:
    return counted(metadata, TRIES_KEY)


def merge_tries_in(metadata: dict) -> int:
    return counted(metadata, MERGE_TRIES_KEY)


def try_cap(stage: str) -> int:
    """The tries a lap may use at the stage: the merge worker's own cap at the merge, the lap's cap elsewhere."""
    return caps.MERGE_TRY_CAP if stage == MERGE else caps.TRY_CAP


def tries_used(metadata: dict, stage: str) -> int:
    """The tries the lap's metadata counts against the stage's cap."""
    return merge_tries_in(metadata) if stage == MERGE else tries_in(metadata)


def findings_of(metadata: dict) -> str:
    return findings_text(metadata, FINDINGS_KEY)


def app_findings_of(metadata: dict) -> str:
    return findings_text(metadata, APP_FINDINGS_KEY)


def findings_text(metadata: dict, key: str) -> str:
    """The findings a check sent back, as the metadata holds them under the key, or an empty string."""
    stored = metadata.get(key)
    return json.dumps(stored) if isinstance(stored, list) else str(stored or "")


def words(stage: str) -> str:
    """The stage as a sentence names it: the Spec check is a glossary term, the others are plain."""
    return STAGE_WORDS.get(stage, stage)


def wall_clock_seconds(stage: str) -> int:
    return BUILD_WALL_CLOCK_SECONDS if stage == BUILD else OTHER_WALL_CLOCK_SECONDS


def is_past_wall_clock(stage: str, started: int | None, now: int) -> bool:
    """True when the stage started more than its wall clock ago; a lap that records no start never is."""
    return started is not None and now - started > wall_clock_seconds(stage)


def open_lap(task: dict) -> Lap | None:
    metadata = metadata_of(task)
    stage = stage_of(metadata)
    if not stage or stage in RESTING_STAGES:
        return None
    return Lap(task=str(task["id"]), title=str(task.get("title") or ""), area=area_of(metadata),
               number=required_number(metadata, NUMBER_KEY), slot=required_number(metadata, SLOT_KEY),
               branch=branch_of(metadata), worktree=Path(workspace_of(metadata)),
               stage=stage, tries=required_number(metadata, TRIES_KEY), started=started_of(metadata),
               cutoffs=counted(metadata, cutoffs_key(stage)),
               send_backs=counted(metadata, SEND_BACKS_KEY),
               merge_tries=merge_tries_in(metadata),
               merge_why=str(metadata.get(MERGE_WHY_KEY) or ""),
               merge_base=str(metadata.get(MERGE_BASE_KEY) or ""), track=track_of(metadata),
               app=str(metadata.get(APP_KEY) or ""), test_filter=str(metadata.get(FILTER_KEY) or ""),
               spec_passed=metadata.get(SPEC_PASSED_KEY) == PASS, findings=findings_of(metadata),
               app_findings=app_findings_of(metadata),
               test_failures=counted(metadata, TEST_FAILURES_KEY))


def new_lap(task: dict, slot: int, stage: str, now: int, main_tree: Path) -> Lap:
    """The lap a ready task opens: the number after the one it left, the branch and worktree its id names, and the
    stage, with no tries, cutoffs, send-backs or merge tries, because each is a cap on one lap."""
    metadata = metadata_of(task)
    task_id = str(task["id"])
    previous = previous_number(metadata)
    return Lap(task=task_id, title=str(task.get("title") or ""), area=area_of(metadata),
               number=FIRST_LAP if previous is None else previous + 1, slot=slot,
               branch=f"{LAP_BRANCH_PREFIX}{task_id}",
               worktree=stage_worktree(LAP_FOLDER_PREFIX, task_id, main_tree), stage=stage, tries=NO_TRIES,
               started=now, cutoffs=NONE_YET, send_backs=NONE_YET, merge_tries=NONE_YET,
               merge_why="", merge_base="", track=track_of(metadata), app="", test_filter="", spec_passed=False,
               findings=findings_of(metadata), app_findings=app_findings_of(metadata),
               test_failures=NONE_YET)


class NotALapWorktree(Exception):
    """A folder that is no lap's worktree, worded for the person who reads stderr."""


def lap_branch_in(worktree: Path) -> str:
    """The branch checked out in the worktree, or the branch its rebase in progress rewrites, whose HEAD is detached
    until the rebase ends; empty when it is neither."""
    checked_out = checked_out_branch(worktree)
    if checked_out:
        return checked_out
    for state in REBASE_STATES:
        found = capture(["git", "rev-parse", "--git-path", f"{state}/head-name"], worktree, None)
        head_name = worktree / found.stdout.strip()
        if found.returncode == 0 and head_name.is_file():
            ref = head_name.read_text(encoding="utf-8").strip()
            return ref[len(HEADS_PREFIX):] if ref.startswith(HEADS_PREFIX) else ""
    return ""


def task_in_worktree(worktree: Path, main_tree: Path) -> dict:
    """The task a lap worktree holds, as bd shows it; empty when bd shows none. A folder whose branch is no lap's
    raises NotALapWorktree."""
    branch = lap_branch_in(worktree)
    if not branch.startswith(LAP_BRANCH_PREFIX):
        raise NotALapWorktree(f"{worktree} is not a lap worktree: its branch is {branch or 'unknown'}, not "
                              f"{LAP_BRANCH_PREFIX}<task>")
    return bd_show(branch[len(LAP_BRANCH_PREFIX):], main_tree) or {}


def cutoffs_key(stage: str) -> str:
    return f"{CUTOFFS_KEY_PREFIX}{stage}"


def opening(lap: Lap) -> list[str]:
    """The arguments of the `bd update` that opens the lap: the task is in progress under the factory's actor, and
    every record of the lap holds the value the lap starts with. A full-track lap starts with no Spec check result
    from an earlier lap; its findings stay, because the build the lap starts is the one that answers them."""
    clearing = clearing_spec_pass() if lap.track == FULL_TRACK else []
    return ["--status=in_progress", f"--assignee={FACTORY_ACTOR}",
            *set_metadata((NUMBER_KEY, lap.number), (STAGE_KEY, lap.stage), (TRIES_KEY, lap.tries),
                          (WORKSPACE_KEY, lap.worktree), (SLOT_KEY, lap.slot), (BRANCH_KEY, lap.branch),
                          (STARTED_KEY, lap.started), (cutoffs_key(lap.stage), lap.cutoffs),
                          (SEND_BACKS_KEY, lap.send_backs), (MERGE_TRIES_KEY, lap.merge_tries),
                          (TEST_FAILURES_KEY, lap.test_failures)),
            *clearing]


def resting(stage: str) -> list[str]:
    """The arguments that end the lap at rest in a resting stage: the task is open and unassigned."""
    return ["--status=open", "--assignee=", *set_metadata((STAGE_KEY, stage))]


def resting_with_tries(stage: str, tries: int) -> list[str]:
    """The arguments that end the lap at rest in a resting stage, with the tries it holds then."""
    return [*resting(stage), *set_metadata((TRIES_KEY, tries))]


def recording_merge() -> list[str]:
    """The arguments that record the lap's stage as merged, once the gate has closed its task."""
    return set_metadata((STAGE_KEY, MERGED))


def assigning(track: str, area: str) -> list[str]:
    """The arguments that give a task the track and the area its lap needs before the scheduler can open it."""
    return set_metadata((TRACK_KEY, track), (AREA_KEY, area))


def clearing_spec_pass() -> list[str]:
    return set_metadata((SPEC_PASSED_KEY, ""))


def entering(lap: Lap, stage: str) -> tuple[Lap, list[str]]:
    """The lap at the stage, whose cutoffs start at none when the stage is a new one, and the arguments that record
    it."""
    cutoffs = lap.cutoffs if stage == lap.stage else NONE_YET
    return dataclasses.replace(lap, stage=stage, cutoffs=cutoffs), set_metadata((STAGE_KEY, stage))


def at_build(lap: Lap) -> Lap:
    """The lap as the build's own tries and stage see it, with its metadata left as it is."""
    return dataclasses.replace(lap, stage=BUILD)


def counting_tries(lap: Lap, tries: int) -> tuple[Lap, list[str]]:
    return dataclasses.replace(lap, tries=tries), set_metadata((TRIES_KEY, tries))


def retrying(lap: Lap, tries: int) -> tuple[Lap, list[str]]:
    """The lap that goes back to its stage with the tries counted, and the arguments that record it."""
    counted, counting = counting_tries(lap, tries)
    entered, entering_arguments = entering(counted, lap.stage)
    return entered, [*counting, *entering_arguments]


def counting_cutoffs(lap: Lap, cutoffs: int) -> tuple[Lap, list[str]]:
    return dataclasses.replace(lap, cutoffs=cutoffs), set_metadata((cutoffs_key(lap.stage), cutoffs))


def counting_merge_tries(lap: Lap, tries: int) -> tuple[Lap, list[str]]:
    return dataclasses.replace(lap, merge_tries=tries), set_metadata((MERGE_TRIES_KEY, tries))


def counting_test_failures(lap: Lap, failures: int) -> tuple[Lap, list[str]]:
    return dataclasses.replace(lap, test_failures=failures), set_metadata((TEST_FAILURES_KEY, failures))


def restarting_clock(lap: Lap, now: int) -> tuple[Lap, list[str]]:
    return dataclasses.replace(lap, started=now), set_metadata((STARTED_KEY, now))


def calling_merge_worker(lap: Lap, why: str, base: str) -> tuple[Lap, list[str]]:
    entered, entering_arguments = entering(lap, MERGE)
    called = dataclasses.replace(entered, merge_why=why, merge_base=base)
    return called, [*entering_arguments, *set_metadata((MERGE_WHY_KEY, why), (MERGE_BASE_KEY, base))]


def naming_tests(lap: Lap, app: str, test_filter: str) -> tuple[Lap, list[str]]:
    return dataclasses.replace(lap, app=app, test_filter=test_filter), set_metadata((APP_KEY, app),
                                                                                      (FILTER_KEY, test_filter))


def moving_to_full_track(lap: Lap) -> tuple[Lap, list[str]]:
    return dataclasses.replace(lap, track=FULL_TRACK), set_metadata((TRACK_KEY, FULL_TRACK))


def passing_spec_check(lap: Lap) -> tuple[Lap, list[str]]:
    return dataclasses.replace(lap, spec_passed=True), set_metadata((SPEC_PASSED_KEY, PASS))


def recording_findings(lap: Lap, spec_json: str, app_json: str) -> tuple[Lap, list[str]]:
    """The lap with the Spec check's pass cleared and the findings the checks sent back, and the arguments that record
    it; empty strings clear the findings too."""
    recorded = dataclasses.replace(lap, spec_passed=False, findings=spec_json, app_findings=app_json)
    return recorded, [*clearing_spec_pass(), *set_metadata((FINDINGS_KEY, spec_json), (APP_FINDINGS_KEY, app_json))]


def sending_back(lap: Lap, stage: str, send_backs: int, spec_json: str, app_json: str) -> tuple[Lap, list[str]]:
    """The lap that goes back to the stage with a send-back counted and the checks' findings kept, and the arguments
    that record it."""
    counted = dataclasses.replace(lap, send_backs=send_backs)
    entered, entering_arguments = entering(counted, stage)
    recorded, recording_arguments = recording_findings(entered, spec_json, app_json)
    counting = set_metadata((SEND_BACKS_KEY, send_backs))
    return recorded, [*counting, *entering_arguments, *recording_arguments]
