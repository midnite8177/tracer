"""The local-model trial: the tidy of an epic's first pass, run twice from the same head so that the human can judge the
local tier's route on one real pass.

An epic whose factory rules hold `local_trial` and whose pass count is zero gets two tidies, one after the other. The
local tidy comes first: its actions hold `route` local, and its worktree is .worktrees/local-tidy-<epic>. Its settle
commits what the workers left, as the tidy does, but keeps the commit on the ref refs/jidoka/tidy-trial/<epic> and
leaves the epic branch where it was. The native tidy comes next, from the same head: its actions hold `route` native and
`native_route`, the local tier's native route, and its settle is the tidy's own, so it lands on the epic branch. The
first call that hands a tidy out records, beside the batches, the second it was handed out and the route the tidy runs
on, so that a change of the settings before the settle changes neither. Each settle records its tidy in the epic's
`tidy.trial` metadata: the route that ran, the wall time from that first call to the settle, the head both started
from, the commit and the files it changed; the local tidy also records each batch, whether the local model did it
(true when the batch's T3 child ended done, false for a batch that fell back to the native route) and whether the
child ran out its wall clock. The gate page reads the record, and landing or dropping the epic deletes the ref. Later
passes tidy once, as every epic does.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import clock
import ledger
import pass_ledger
import pass_support
import routes
import rules
import t3_tidy
import tidy
from commands import SCRATCH_FOLDER, env_as_factory, metadata_of, read_bead, run, set_metadata
from epic_branch import required_head
from lap_outcomes import CUT_OFF, DONE
from pass_support import Committed, accepts_any_change
from settings_reader import Settings
from worktrees import remove_worktree

TRIAL_KEY = "tidy.trial"
LOCAL = "local"
NATIVE = "native"
TIER = "local"
REF_PREFIX = "refs/jidoka/tidy-trial/"
STARTED_FILE = "tidy-started"


@dataclass(frozen=True)
class TrialBatch:
    """One tidy batch of the local tidy, whether the local model did it, and whether its child ran out the stage's
    wall clock. A batch the local model did not do fell back to the native route, so its edits are the native
    route's."""
    number: int
    local: bool
    cut_off: bool


@dataclass(frozen=True)
class TrialTidy:
    """One of the trial's two tidies: which route ran it, the harness, model and effort that route names, the seconds
    it took, the head it started from, the commit it ended at (the head again when it changed nothing), the files
    it changed and, for the local tidy, each batch and who did it."""
    route: str
    harness: str | None
    model: str | None
    effort: str | None
    seconds: int
    base: str
    commit: str
    files: tuple[str, ...]
    batches: tuple[TrialBatch, ...]


@dataclass(frozen=True)
class HandedOut:
    """What the first call that handed a tidy out recorded: the second it did, and the route the tidy runs on."""
    started: int
    route: routes.Route | None


def ref_of(epic: str) -> str:
    """The ref that keeps the local tidy's commit."""
    return f"{REF_PREFIX}{epic}"


def trial_of(shown: dict) -> dict[str, TrialTidy]:
    """The tidies the epic records, by route; none when it records none."""
    stored = metadata_of(shown).get(TRIAL_KEY)
    if stored in (None, ""):
        return {}
    try:
        recorded = json.loads(stored) if isinstance(stored, str) else stored
        return {route: TrialTidy(**{**each, "files": tuple(each["files"]),
                                    "batches": tuple(TrialBatch(**batch) for batch in each["batches"])})
                for route, each in recorded.items()}
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise tidy.TidyError(f"the {TRIAL_KEY} metadata of the epic cannot be read: {error!r}") from error


def tidy_owed(shown: dict) -> str | None:
    """The route of the trial tidy that the next tidy is: local on the first pass of an epic on trial that has run no
    tidy, native after it, and None when the epic is not on trial, is past its first pass or has run both."""
    if not rules.of_epic(shown).local_trial:
        return None
    ran = trial_of(shown)
    if LOCAL in ran:
        return NATIVE if NATIVE not in ran else None
    return LOCAL if pass_support.count_of(shown, pass_ledger.PASSES_KEY) == 0 else None


def route_named(which: str) -> tidy.TidyRoute:
    if which == LOCAL:
        return tidy.TidyRoute(LOCAL, None)
    return tidy.TidyRoute(NATIVE, routes.native_route_of(TIER))


def started_file(scratch: Path) -> Path:
    return scratch / STARTED_FILE


def note_start(scratch: Path, route: routes.Route | None) -> None:
    """Records the second the tidy was first handed out and the route it runs on, unless an earlier call did. A tidy
    with no complete route records an empty object."""
    path = started_file(scratch)
    if not path.is_file():
        recorded = route.as_dict() if route is not None else {}
        path.write_text(json.dumps({"started": clock.now(), "route": recorded}), encoding="utf-8")


def route_ran_on(which: str, home: Path) -> routes.Route | None:
    """The route of the trial tidy as the ledger reads it, or None when the settings give no complete route."""
    return ledger.route_of(home, TIER, which == NATIVE)


def route_recorded(recorded: dict) -> routes.Route | None:
    """The route that `note_start` recorded, or None when it recorded none."""
    try:
        return routes.Route.parse(TIER, recorded)
    except routes.RouteError:
        return None


def handed_out(scratch: Path, which: str, home: Path) -> HandedOut:
    """What the first call recorded. A tidy with no record is read as handed out now, on the route the settings give,
    so its wall time is nothing."""
    try:
        recorded = json.loads(started_file(scratch).read_text(encoding="utf-8"))
        if isinstance(recorded["started"], int) and isinstance(recorded["route"], dict):
            return HandedOut(recorded["started"], route_recorded(recorded["route"]))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return HandedOut(clock.now(), route_ran_on(which, home))


def to_run(epic: str, shown: dict, branch: str, settings: Settings, home: Path,
           main_tree: Path) -> tidy.TidyToRun | None:
    """The tidy this pass still owes: the next one of the trial when the epic is on trial, else the ordinary tidy."""
    which = tidy_owed(shown)
    if which is None:
        return tidy.to_run(epic, shown, branch, settings, home, main_tree)
    stage = tidy.LOCAL_STAGE if which == LOCAL else tidy.STAGE
    owed = tidy.to_run_as(stage, route_named(which), epic, shown, branch, settings, home, main_tree)
    if owed is not None:
        note_start(owed.stage.scratch, route_ran_on(which, home))
    return owed


def tidy_ran(route: str, handed: HandedOut, base: str, settled: Committed, batches: tuple[TrialBatch, ...]
             ) -> TrialTidy:
    seconds = max(0, clock.now() - handed.started)
    ran = handed.route
    return TrialTidy(route, ran.harness if ran else None, ran.model if ran else None, ran.effort if ran else None,
                     seconds, base, settled.head, tuple(settled.changed), batches)


def batches_of(scratch: Path) -> tuple[TrialBatch, ...]:
    """Each batch of the local tidy, in order, with whether its T3 child ended done and whether it ran out the wall
    clock. The batch folders are the ones `to_run` made, so a batch that never ran as a child is among them and fell
    back."""
    outcomes = [t3_tidy.batch_outcome(folder) for folder in tidy.batch_folders(scratch)]
    return tuple(TrialBatch(number, outcome == DONE, outcome == CUT_OFF) for number, outcome in enumerate(outcomes, 1))


def trial_with(shown: dict, ran: TrialTidy) -> tuple[str, str]:
    kept = {**trial_of(shown), ran.route: ran}
    return TRIAL_KEY, json.dumps({route: asdict(each) for route, each in kept.items()}, separators=(",", ":"))


def settle(epic: str, branch: str, settings: Settings, home: Path, main_tree: Path) -> Committed:
    """Settles the tidy that the epic's trial owes: the local tidy is kept on its ref, and the native tidy lands as the
    tidy does. An epic not on trial settles the ordinary tidy."""
    shown = read_bead(epic, main_tree)
    which = tidy_owed(shown)
    if which is None:
        return tidy.settle(epic, branch, settings, home, main_tree)
    if which == NATIVE:
        base = required_head(branch, main_tree, tidy.TidyError)
        handed = handed_out(tidy.STAGE.worktree_of(epic, main_tree) / SCRATCH_FOLDER, NATIVE, home)
        return tidy.settle_recording(epic, branch, settings, home, main_tree, lambda settled: [
            trial_with(shown, tidy_ran(NATIVE, handed, base, settled, ()))])
    return settle_local(epic, shown, branch, settings, home, main_tree)


def settle_local(epic: str, shown: dict, branch: str, settings: Settings, home: Path, main_tree: Path) -> Committed:
    found = pass_support.owed_in_worktree(tidy.LOCAL_STAGE, epic, shown, branch, settings, main_tree)
    handed = handed_out(found.scratch, LOCAL, home)
    batches = batches_of(found.scratch)
    settled = pass_support.commit_worktree(found, accepts_any_change, settings)
    ran = tidy_ran(LOCAL, handed, found.head, settled, batches)
    run(["git", "update-ref", ref_of(epic), settled.head], main_tree, None)
    remove_worktree(found.worktree, main_tree)
    env = env_as_factory()
    run(["bd", "comment", epic, f"The local tidy changed {len(settled.changed)} files in {ran.seconds} s, and the "
                                f"commit {settled.head} stays on {ref_of(epic)}, not on the epic branch."],
        main_tree, env)
    run(["bd", "update", epic, *set_metadata(trial_with(shown, ran))], main_tree, env)
    return settled


def diff_of(ran: TrialTidy, main_tree: Path) -> str:
    """What the tidy changed, from the head it started from to its commit."""
    return tidy.diff_of(ran.base, ran.commit, list(ran.files), main_tree) if ran.files else ""
