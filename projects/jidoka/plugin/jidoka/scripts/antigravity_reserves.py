"""The reserves of an Antigravity account: which bucket a stage's model draws on, and the windows the scheduler checks
before the stage starts.

The scheduler imports it; no command line runs it. reserves.py holds the rules of a reserve, and this module gives them
the windows of an Antigravity account. The account's quota comes in buckets (antigravity_usage.py), each with a session
window that counts as the five-hour window and a weekly window that counts as the seven-day one. A model draws on the
bucket of its family: Gemini for Neon, Flash and Hydrogen, Gemini Argon, and Gemini Carbon. A model of any other family,
such as Claude or GPT, has no bucket to watch, and neither has a bucket that T3 does not list.

The stage of a model is the one the scheduler is about to start: the stage of each lap that goes back to a worker, the
first stage of each ready task, and the stages a finished epic's pass owes, which the scheduler checks before it cuts
the worktree. Its tier is the epic's `stage_tiers` rule for the stage, else the tier the factory skill gives
it, and its model is the model of that tier's route in the machine settings' `antigravity_routes`. The reserve of the
account is the epic's `reserves` rule for `antigravity`, else the machine settings', else 10% of the five-hour window
and 25% of the seven-day window, as reserves.py says. The reserve applies to each start: the stages of one task, or the
stages a finished epic's pass owes, are one start, and a start whose bucket is past a reserve is held back while a
start on another bucket goes on. The epic pauses or parks as reserves.py says only when every start is held back, and
a lap that would go back to a worker on a held-back bucket ends interrupted.

A call that has no reading of the quota holds nothing back. The epic's `reserve.antigravity_unread` metadata holds the
causes of the failures that the epic got a comment for since readings last returned, as a JSON list, so that it gets one
comment the first time a reading fails for a cause and one when readings return.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import antigravity_usage
import holdouts_run
import lap_opening
import reserves
import review
import routes
import validation_merge
from commands import env_as_factory, metadata_of, run, set_metadata, unset_metadata
from epic_reader import Epic
from lap_record import APP_CHECK, BUILD, FULL_TRACK, RESEARCH, SIMPLE_TRACK, SPEC_CHECK, Lap, track_of
from machine_settings import ANTIGRAVITY_ACCOUNT
from rules import is_map_of, of_epic
from texts import is_text

UNREAD_KEY = "reserve.antigravity_unread"
STAGE_TIERS_KEY = "stage_tiers"
FIVE_HOUR_SECONDS = reserves.FIVE_HOUR_SECONDS
SEVEN_DAY_SECONDS = reserves.SEVEN_DAY_SECONDS
WRITING_STAGE_TIERS = {stage: tier for stage, tier in routes.WRITING_STAGE_TIERS if stage != BUILD}
"""The tier of each stage that changes files, as routes.py holds it. The build has two, one for each track, and
`tier_of` picks between them."""
READ_ONLY_STAGE_TIERS = {
    RESEARCH: "light", APP_CHECK: "standard", SPEC_CHECK: "standard", holdouts_run.ACTION: "standard",
    validation_merge.STAGE: "deep", review.lane_stage(review.COMMENTS): "standard",
    review.lane_stage(review.STANDARDS): "standard", review.lane_stage(review.SPEC): "second",
    review.lane_stage(review.DESIGN): "deep",
}
"""The tier the factory skill gives each stage that routes.py does not list as writing."""


@dataclass(frozen=True)
class Family:
    """A family of models and the buckets that serve it: its name in words, and the word that its models' and its
    buckets' names hold."""
    label: str
    word: str


FAMILIES = (Family("Gemini Argon", "argon"), Family("Gemini Carbon", "carbon"), Family("Gemini", "gemini"))
"""The families in the order a name is tried: an Argon or Carbon name holds `gemini` too, so those come before Gemini."""


@dataclass(frozen=True)
class Stage:
    """A stage about to start: its name, the track of its lap, which picks the tier of a build, and the task whose lap
    it is, or None for a stage of the pass."""
    name: str
    track: str
    task: str | None


def family_named(name: str) -> Family | None:
    """The family a model's or a bucket's name belongs to, or None for a name that is not Gemini."""
    lowered = name.lower()
    return next((family for family in FAMILIES if family.word in lowered), None)


def tier_of(stage: Stage, stage_tiers: object) -> str | None:
    """The tier the stage runs on: the epic's `stage_tiers` rule for it, else the factory skill's tier, or None for a
    stage that skill gives none."""
    if is_map_of(stage_tiers, is_text) and stage.name in stage_tiers:
        return str(stage_tiers[stage.name])
    if stage.name == BUILD:
        return "deep" if stage.track == FULL_TRACK else "standard"
    return WRITING_STAGE_TIERS.get(stage.name) or READ_ONLY_STAGE_TIERS.get(stage.name)


def model_of(tier: str, home: Path) -> str | None:
    """The model of the tier's route on an Antigravity host, or None when the machine records no such route or the
    route runs in no T3 Antigravity thread."""
    try:
        route = routes.recorded_route(tier, home, routes.ANTIGRAVITY_HOST)
    except routes.RouteError:
        return None
    return route.model if route.is_antigravity else None


def stages_ahead(epic: Epic, going_back: list[Lap], owed_in_pass: list[str], main_tree: Path) -> list[Stage]:
    """The stages this call may start: those of the laps that go back to a worker, the first stage of each ready task,
    and the stages that pass_stages.stages_owed names for a finished epic's pass, whose track is the simple one since a
    pass stage has none."""
    ready = [Stage(lap_opening.first_stage(str(task["id"]), track_of(metadata_of(task)), main_tree),
                   track_of(metadata_of(task)), str(task["id"]))
             for task in epic.ready_task_beads]
    return ([Stage(lap.stage, lap.track, lap.task) for lap in going_back] + ready
            + [Stage(name, SIMPLE_TRACK, None) for name in owed_in_pass])


def families_ahead(stages: list[Stage], shown: dict, home: Path) -> list[Family]:
    """The families of models the stages draw on, each once, in the order the stages come: the stage's tier, the tier's
    route's model, the model's family. A stage with no tier, no Antigravity route or no Gemini model draws on none."""
    stage_tiers = of_epic(shown).settings.get(STAGE_TIERS_KEY)
    tiers = [tier_of(stage, stage_tiers) for stage in stages]
    models = [model_of(tier, home) for tier in tiers if tier is not None]
    families = [family_named(model) for model in models if model is not None]
    return list(dict.fromkeys(family for family in families if family is not None))


def bucket_of(quota: antigravity_usage.Reading, family: Family) -> antigravity_usage.Bucket | None:
    """The first bucket of the quota that serves the family, or None."""
    return next((bucket for bucket in quota.buckets if family_named(bucket.name) is family), None)


def window_of(held: antigravity_usage.Window | None, name: str, default_seconds: int,
              reserve_percent: float) -> reserves.Window | None:
    """The window as reserves.py holds it, or None for a bucket with no such window or one that names no reset."""
    if held is None or held.resets_at is None:
        return None
    seconds = int(held.duration_minutes * 60) if held.duration_minutes else default_seconds
    return reserves.Window(name, held.used_percent, held.resets_at, seconds, reserve_percent)


def first_past_reserve(windows: list[reserves.Window], now: int) -> reserves.Window | None:
    """The first window past its reserve, else the first window, or None when there is none."""
    return next((window for window in windows if window.is_past_reserve(now)), windows[0] if windows else None)


def reading_of(quota: antigravity_usage.Reading, families: list[Family], five_hour_percent: float,
               seven_day_percent: float, now: int) -> reserves.Reading | None:
    """The windows of the quota's bucket of each family: its session window as the five-hour one and its weekly window
    as the seven-day one, each with its reserve. None when the quota holds no bucket of any family."""
    found = [(family, bucket_of(quota, family)) for family in families]
    buckets = [(family, bucket) for family, bucket in found if bucket is not None]
    if not buckets:
        return None
    five_hour = [window_of(bucket.session, f"{family.label} five-hour", FIVE_HOUR_SECONDS, five_hour_percent)
                 for family, bucket in buckets]
    seven_day = [window_of(bucket.weekly, f"{family.label} seven-day", SEVEN_DAY_SECONDS, seven_day_percent)
                 for family, bucket in buckets]
    return reserves.Reading(first_past_reserve([window for window in five_hour if window is not None], now),
                            first_past_reserve([window for window in seven_day if window is not None], now))


def holding_back(reading: reserves.Reading | None, shown: dict, now: int) -> reserves.Window | None:
    """The window that keeps a start from happening: its five-hour window when past its reserve, else its seven-day
    window when it parks the epic, as reserves.seven_day_past_reserve says."""
    if reading is None:
        return None
    if reading.five_hour is not None and reading.five_hour.is_past_reserve(now):
        return reading.five_hour
    return reserves.seven_day_past_reserve(shown, reading, now)


def reading_for(quota: antigravity_usage.Reading, stages: list[Stage], shown: dict, home: Path,
                now: int) -> reserves.Checked:
    """The reserves applied to each start. The stages of one task, or the stages the pass owes, are one start, held
    back when a bucket its models draw on is past its reserve.

    When every start is held back, the reading holds the windows of all the buckets the stages draw on, so the epic
    pauses or parks as reserves.py says. When another start goes on, the reading holds no window, which ends a pause
    on a reserve, and each task whose start is held back comes with its window. The pass has no task, and it is the
    only start of a finished epic, so it is never held back beside another."""
    five_hour_percent, seven_day_percent = reserves.reserve_percents(shown, home, ANTIGRAVITY_ACCOUNT)
    starts: dict[str | None, list[Stage]] = {}
    for stage in stages:
        starts.setdefault(stage.task, []).append(stage)
    held: dict[str | None, reserves.Window] = {}
    for task, start in starts.items():
        start_reading = reading_of(quota, families_ahead(start, shown, home), five_hour_percent, seven_day_percent,
                                   now)
        window = holding_back(start_reading, shown, now)
        if window is not None:
            held[task] = window
    if len(held) == len(starts):
        return reserves.Checked(
            reading_of(quota, families_ahead(stages, shown, home), five_hour_percent, seven_day_percent, now), {})
    return reserves.Checked(reserves.NO_WINDOW,
                            {task: window for task, window in held.items() if task is not None})


def announced_causes(shown: dict) -> list[str]:
    """The causes of the failures the epic got a comment for since readings last returned."""
    held = metadata_of(shown).get(UNREAD_KEY)
    if isinstance(held, str) and held:
        try:
            held = json.loads(held)
        except ValueError:
            return [held]
    return [str(cause) for cause in held] if isinstance(held, list) else []


def announce(epic: str, shown: dict, refreshed: antigravity_usage.Reading | antigravity_usage.Unread,
             main_tree: Path) -> None:
    """Comments on the epic once when a reading fails for a cause it holds no comment for, and once when readings
    return after a failure, and keeps the causes of the failures in the epic's metadata between calls."""
    announced = announced_causes(shown)
    if isinstance(refreshed, antigravity_usage.Unread):
        if refreshed.cause in announced:
            return
        run(["bd", "comment", epic, f"No Antigravity usage reading: {refreshed.cause}. The reserves hold nothing back "
                                    "until readings return."], main_tree, env_as_factory())
        run(["bd", "update", epic, *set_metadata((UNREAD_KEY, json.dumps([*announced, refreshed.cause])))], main_tree,
            env_as_factory())
    elif announced:
        run(["bd", "comment", epic, "Antigravity usage readings are back, so the reserves hold stages back again."],
            main_tree, env_as_factory())
        run(["bd", "update", epic, *unset_metadata(UNREAD_KEY)], main_tree, env_as_factory())
