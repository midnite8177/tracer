#!/usr/bin/env python3
"""Reads a handed-off epic's beads and prints what the manager does next.

Run it from inside any checkout of the repo. The epic's tasks are its
children that are neither closed nor epics. A lap is open while its task is
not closed and its metadata holds a `lap.stage` other than parked.

`next <epic>` is the call a manager makes when it starts, so it takes every
open lap at the build for one an earlier session left with no worker. It
reports each on stderr as cut off and prints it as a build action, in slot
order, with its tries unchanged. It makes the checks below, then opens a lap for each ready task,
in bd priority order and then by id, while the open laps of the epic number
fewer than the repo settings' lap_limit, and never for a task whose area an
open lap already holds. A task is ready when every bead it waits on is
closed, it has no open lap, no assignee and no `human` label, and its
`lap.area` metadata names its area.

Opening a lap makes, or reuses, the worktree <main checkout>/.worktrees/lap-<task>
on the branch lap/<task>, cut from the epic branch the epic records as
`factory.branch`, and the lap's scratch folder <worktree>/.scratch. The
repo's info/exclude gets `.worktrees/` and `/.scratch/`, so neither shows in
any worktree's git status. In a repo whose settings keep the glossary and
ADRs private, each worktree gets the links private_docs.share makes to the
main checkout's copies, and a worktree that holds its own copy stops the
call, with the reason on stderr, before any task is claimed. Then, with BEADS_ACTOR set to jidoka, the task
goes to in_progress with the assignee jidoka, and its metadata gets
`lap.number` (1), `lap.stage` (build), `lap.tries` (0), `lap.workspace` (the
worktree), `lap.slot` (the lowest slot from 1 up that no open lap of the
epic holds) and `lap.branch`. A rerun after a failure reuses the worktree
and branch it finds.

`report <epic> <task> <outcome> [--app <app> --filter <filter>]` takes how
the build of the task's open lap ended, one outcome of a fixed set, and
makes the checks below first:
  done       the build finished, with the app and the filter the builder
             named. The scheduler first stages everything the build left
             in the lap's worktree, apart from the scratch folder, and
             commits it as one commit whose message is the task's title,
             under the repo's git user. A build that left no changes makes
             no commit. Then the scheduler runs that app's targeted tests
             with that
             filter, through targeted_tests.py, on the lap's head rebased
             onto the epic branch, and again after a fresh rebase when the
             epic branch moved during the run. A pass goes to the merge gate,
             merge_gate.py. When the gate finds the epic branch moved since
             the run, the tests run again, and that is not a try.
  failed     the build worker failed.
  cut off    the build worker ended for a reason outside its work; the lap
             goes back to the build, and that is not a try.
A failed build, a red targeted run, a filter the targeted tests refuse or
that runs no tests, and a lap the merge gate finds with no commit the epic
branch lacks are each a try: the lap's `lap.tries` goes up by one, a comment
says why, and the lap goes back to the build. The third try parks the task.
So do a conflict while rebasing the lap onto the epic branch, naming the
files, and any other refusal of the merge gate, naming its check. A
parked task gets `lap.stage` parked, status open, no assignee, the human
label and a comment saying why; its worktree and branch stay. Its lap no
longer holds a slot or an area, and the task is not ready while it carries
the human label. A merged lap's task is closed, and its worktree and lap
branch are gone. Everything the scheduler, the targeted tests and the merge
gate write on a lap, they write with BEADS_ACTOR set to jidoka. The output
of the tests and the gate goes to stderr. Then the call does what `next`
does, and its actions start with the lap that went back to the build.

When `next` or `report` finds the epic with every task closed, a bead
that has neither the human label nor a gate.state in its metadata, it
runs validation, validation.py, before anything else. Green leaves the epic
at the acceptance gate, with the human label, gate.state waiting and a gate
comment. Red files a task in the epic, and this call opens its lap with the
others. A merge of main that conflicts stops the call with the files named.

Each call prints one JSON object:
  epic       the epic's id.
  branch     the epic branch.
  lap_limit  the repo settings' lap limit.
  validation null, or when this call ran validation, its result (pass or
             fail), head (the commit validated), tests, skipped, seconds
             and filed (the id of the task a red run filed, or null).
  no_area    the ids of the open tasks that have no `lap.area`, such as one
             added after handoff. No lap opens for them. Each is also named
             on stderr with the bd command that sets its area, and the task
             is ready once it has one. A task that is assigned, labeled
             human or in an open lap is left out.
  actions    the lap a report sent back to the build, then the laps this
             call opened, each with action ("build"), task, title, area,
             lap (its number), slot, branch, worktree and scratch. An empty
             list when nothing goes back, and no task is ready or none fits.
  laps       every open lap of the epic after this call, with the fields
             of an action but action, and with stage and tries.

The checks, each refusal saying what to do, all reported at once:
  the epic or one of its tasks waits on an open bead outside the epic;
  the epic holds an epic;
  the repo has no repo settings on this machine, or they hold no lap limit;
  an app has no test command, or the repo has no full suite;
  a holdout names a task outside the epic;
  the epic does not carry the factory label;
  the epic records no epic branch, or the branch it records is gone;
  an app that has holdouts or acceptance specs has no way in.
An epic whose tasks are all closed passes, with no actions.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  success.
  1  it refused, or a git or bd command failed, with the reason on stderr;
     a refusal writes nothing. A report also refuses a task with no open
     lap at the build stage, done without --app and --filter, the other
     outcomes with them, and an app the targeted tests cannot run.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import itertools
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import git_exclude
import holdouts
import merge_gate
import private_docs
import repo_settings
import targeted_tests
import validation
from bench import FACTORY_LABEL, WORKTREE_FOLDER, BenchError, Workspace, hide_worktrees, make_worktree
from commands import COMMAND_TIMEOUT_SECONDS, FACTORY_ACTOR, CommandError, capture, env_as_factory, head_of, \
    run
from handoff import BLOCKING, BRANCH_KEY, CLOSED, ONBOARD, Epic, HandoffError, Rerun, epic_of, recorded_branch, \
    problems_while_held

HUMAN_LABEL = validation.HUMAN_LABEL
BUILD = "build"
PARKED = "parked"
DONE = "done"
FAILED = "failed"
CUT_OFF = "cut off"
OUTCOMES = [DONE, FAILED, CUT_OFF]
TRY_CAP = 3
FIRST_LAP = 1
FIRST_SLOT = 1
NO_TRIES = 0
LAP_BRANCH_PREFIX = "lap/"
LAP_FOLDER_PREFIX = "lap-"
SCRATCH_FOLDER = ".scratch"
NOTHING_STAGED = 0
CHANGES_STAGED = 1
HANDOFF = "/jidoka:handoff"
RERUN = Rerun(on_the_holding_epic="Run the scheduler on the epic that holds it",
              after_onboarding="run the scheduler again")


class SchedulerError(Exception):
    """A reason the script writes nothing more, worded for the person who reads stderr."""


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

    @property
    def scratch(self) -> Path:
        return self.worktree / SCRATCH_FOLDER

    def fields(self) -> dict:
        return {"task": self.task, "title": self.title, "area": self.area, "lap": self.number, "slot": self.slot,
                "branch": self.branch, "worktree": str(self.worktree), "scratch": str(self.scratch)}


def metadata_of(bead: dict) -> dict:
    metadata = bead.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def tasks_of(epic: Epic) -> list[dict]:
    task_ids = {task.id for task in epic.tasks}
    return [child for child in epic.children if str(child["id"]) in task_ids]


def whole_number(value: object) -> int:
    try:
        return int(str(value))
    except ValueError as error:
        raise SchedulerError(f"the lap metadata holds {value!r} where it needs a whole number") from error


def open_lap(task: dict) -> Lap | None:
    metadata = metadata_of(task)
    if not metadata.get("lap.stage") or metadata["lap.stage"] == PARKED:
        return None
    return Lap(task=str(task["id"]), title=str(task.get("title") or ""), area=str(metadata.get("lap.area") or ""),
               number=whole_number(metadata.get("lap.number")), slot=whole_number(metadata.get("lap.slot")),
               branch=str(metadata.get("lap.branch") or ""), worktree=Path(str(metadata.get("lap.workspace") or "")),
               stage=str(metadata["lap.stage"]), tries=whole_number(metadata.get("lap.tries")))


def waits_on_open_bead(task: dict) -> bool:
    return any(isinstance(link, dict) and link.get("dependency_type") == BLOCKING and link.get("status") != CLOSED
               for link in task.get("dependencies") or [])


def is_ready(task: dict) -> bool:
    return (open_lap(task) is None and not task.get("assignee") and HUMAN_LABEL not in (task.get("labels") or [])
            and bool(metadata_of(task).get("lap.area")) and not waits_on_open_bead(task))


def lacks_only_an_area(task: dict) -> bool:
    """A task no lap will open for because its `lap.area` is missing, such as one added after handoff."""
    return (open_lap(task) is None and not task.get("assignee") and HUMAN_LABEL not in (task.get("labels") or [])
            and not metadata_of(task).get("lap.area"))


def by_priority(task: dict) -> tuple[int, str]:
    priority = task.get("priority")
    return (priority if isinstance(priority, int) else sys.maxsize, str(task["id"]))


def lap_limit_of(settings: dict) -> int:
    limit = settings.get("lap_limit")
    return limit if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0 else 0


def scheduler_problems(epic: Epic, settings: dict, main_tree: Path) -> list[str]:
    problems = problems_while_held(epic, settings, RERUN)
    if settings and not lap_limit_of(settings):
        problems.append(f"the repo settings hold no lap limit. Run {ONBOARD} again to record one")
    if FACTORY_LABEL not in (epic.shown.get("labels") or []):
        problems.append(f"{epic.id} does not carry the {FACTORY_LABEL} label, so the factory does not hold it. "
                        f"Hand it off first with {HANDOFF} {epic.id}")
    branch = recorded_branch(epic)
    if not branch:
        problems.append(f"{epic.id} records no epic branch as its {BRANCH_KEY} metadata. Hand it off again "
                        f"with {HANDOFF} {epic.id}")
    elif head_of(f"refs/heads/{branch}", main_tree) is None:
        problems.append(f"the epic branch {branch} that {epic.id} records does not exist. Restore it, or take "
                        f"the {FACTORY_LABEL} label off {epic.id} and hand it off again")
    return problems


def is_finished(epic: Epic) -> bool:
    """Every task of the epic is closed, and the epic waits on neither the human nor the acceptance gate."""
    return (bool(epic.children) and not epic.tasks and validation.HUMAN_LABEL not in (epic.shown.get("labels") or [])
            and validation.GATE_STATE_KEY not in metadata_of(epic.shown))


def planned_laps(ready: list[dict], held: list[Lap], limit: int, main_tree: Path) -> list[Lap]:
    """The laps that fit beside the open ones: within the limit, one per area, each on the lowest free slot."""
    areas = {lap.area for lap in held}
    slots = {lap.slot for lap in held}
    planned: list[Lap] = []
    for task in sorted(ready, key=by_priority):
        if len(held) + len(planned) >= limit:
            break
        area = str(metadata_of(task)["lap.area"])
        if area in areas:
            continue
        slot = next(number for number in itertools.count(FIRST_SLOT) if number not in slots)
        task_id = str(task["id"])
        planned.append(Lap(task=task_id, title=str(task.get("title") or ""), area=area, number=FIRST_LAP,
                           slot=slot, branch=f"{LAP_BRANCH_PREFIX}{task_id}",
                           worktree=main_tree / WORKTREE_FOLDER / f"{LAP_FOLDER_PREFIX}{task_id}", stage=BUILD,
                           tries=NO_TRIES))
        areas.add(area)
        slots.add(slot)
    return planned


def open_workspace(lap: Lap, epic_head: str, home: Path, main_tree: Path) -> None:
    make_worktree(Workspace(lap.branch, lap.worktree, epic_head), main_tree)
    private_docs.share(main_tree, lap.worktree.resolve(), home)
    lap.scratch.mkdir(exist_ok=True)


def record(lap: Lap, main_tree: Path) -> None:
    run(["bd", "update", lap.task, "--status=in_progress", f"--assignee={FACTORY_ACTOR}",
         "--set-metadata", f"lap.number={lap.number}",
         "--set-metadata", f"lap.stage={lap.stage}",
         "--set-metadata", f"lap.tries={lap.tries}",
         "--set-metadata", f"lap.workspace={lap.worktree}",
         "--set-metadata", f"lap.slot={lap.slot}",
         "--set-metadata", f"lap.branch={lap.branch}"], main_tree, env_as_factory())


def checked_epic(bead: str, settings: dict, main_tree: Path) -> Epic:
    epic = epic_of(bead, main_tree, RERUN)
    problems = scheduler_problems(epic, settings, main_tree)
    if problems:
        raise SchedulerError(f"the factory takes no next move on {epic.id}, and nothing was written:\n"
                             + "\n".join(f"  {problem}" for problem in problems))
    return epic


def next_moves(bead: str, home: Path, main_tree: Path, rebuilds: list[Lap], restarting: bool) -> dict:
    """Opens the laps that fit and prints them as build actions, after the rebuilds of laps sent back.

    When restarting, no worker of this manager is running, so every open lap at the build was left by an
    earlier session: each is reported cut off and goes back to the build with its tries unchanged.
    """
    settings = repo_settings.load(repo_settings.settings_path(home, main_tree))
    epic = checked_epic(bead, settings, main_tree)
    validated = None
    if is_finished(epic):
        validated = validation.validate(epic.id, recorded_branch(epic), settings, home, main_tree)
        epic = checked_epic(bead, settings, main_tree)
    tasks = tasks_of(epic)
    held = [lap for lap in map(open_lap, tasks) if lap is not None]
    if restarting:
        rebuilds = [lap for lap in sorted(held, key=lambda lap: lap.slot) if lap.stage == BUILD]
        for lap in rebuilds:
            print(f"scheduler: {lap.task} was cut off, left at the {BUILD} with no worker, so its lap goes back "
                  f"to the {BUILD} and no try is counted", file=sys.stderr)
    limit = lap_limit_of(settings)
    unplaced = [str(task["id"]) for task in sorted(tasks, key=by_priority) if lacks_only_an_area(task)]
    for task_id in unplaced:
        print(f"scheduler: {task_id} has no area, so no lap opens for it. Run bd update {task_id} "
              "--set-metadata lap.area=<area>", file=sys.stderr)
    planned = planned_laps([task for task in tasks if is_ready(task)], held, limit, main_tree)
    epic_branch = recorded_branch(epic)
    epic_head = head_of(f"refs/heads/{epic_branch}", main_tree)
    if epic_head is None:
        raise SchedulerError(f"the epic branch {epic_branch} went away during the call, and nothing was written")
    if planned:
        hide_worktrees(main_tree)
        git_exclude.add(git_exclude.exclude_file(main_tree), [git_exclude.exclude_line(SCRATCH_FOLDER, True)])
    for lap in planned:
        open_workspace(lap, epic_head, home, main_tree)
    for lap in planned:
        record(lap, main_tree)
    return {"epic": epic.id, "branch": epic_branch, "lap_limit": limit,
            "validation": validated.fields() if validated is not None else None, "no_area": unplaced,
            "actions": [{"action": BUILD, **lap.fields()} for lap in rebuilds + planned],
            "laps": [{**lap.fields(), "stage": lap.stage, "tries": lap.tries}
                     for lap in sorted(held + planned, key=lambda lap: lap.slot)]}


def building_lap(epic: Epic, task_id: str) -> Lap:
    for task in tasks_of(epic):
        if str(task["id"]) == task_id:
            lap = open_lap(task)
            if lap is None:
                raise SchedulerError(f"{task_id} has no open lap, so it takes no outcome, and nothing was written")
            if lap.stage != BUILD:
                raise SchedulerError(f"the lap of {task_id} is at the stage {lap.stage}, not {BUILD}, so it takes "
                                     "no build outcome, and nothing was written")
            return lap
    raise SchedulerError(f"{task_id} is not an open task of {epic.id}, and nothing was written")


def refuse_arguments(outcome: str, app: str | None, test_filter: str | None) -> None:
    if outcome == DONE and not (app and test_filter):
        raise SchedulerError(f"{DONE} needs --app and --filter, the app and the filter the builder named, and "
                             "nothing was written")
    if outcome != DONE and (app is not None or test_filter is not None):
        raise SchedulerError(f"--app and --filter go only with {DONE}, and nothing was written")


def park(lap: Lap, tries: int, why: str, main_tree: Path) -> None:
    """Ends the lap parked: the task waits on the human, open and unassigned, with its worktree and branch kept."""
    env = env_as_factory()
    run(["bd", "comment", lap.task, f"Parked: {why}. The worktree {lap.worktree} and the branch {lap.branch} "
         f"keep the work. Take the {HUMAN_LABEL} label off to give the task a new lap."], main_tree, env)
    run(["bd", "update", lap.task, "--status=open", "--assignee=", f"--add-label={HUMAN_LABEL}",
         "--set-metadata", f"lap.stage={PARKED}", "--set-metadata", f"lap.tries={tries}"], main_tree, env)


def count_try(lap: Lap, why: str, main_tree: Path) -> list[Lap]:
    """Counts a failed try. The third parks the task; an earlier one sends the lap back to the build."""
    tries = lap.tries + 1
    if tries >= TRY_CAP:
        park(lap, tries, f"build try {tries} of {TRY_CAP} failed: {why}", main_tree)
        return []
    env = env_as_factory()
    run(["bd", "comment", lap.task, f"Build try {tries} of {TRY_CAP} failed: {why}. The lap goes back to the build."],
        main_tree, env)
    run(["bd", "update", lap.task, "--set-metadata", f"lap.tries={tries}"], main_tree, env)
    return [dataclasses.replace(lap, tries=tries)]


def commit_build(lap: Lap) -> None:
    """Commits what the build left in the lap's worktree, outside the scratch folder, under the task's title."""
    env = env_as_factory()
    run(["git", "add", "--all"], lap.worktree, env)
    run(["git", "reset", "--quiet", "--", SCRATCH_FOLDER], lap.worktree, env)
    staged = capture(["git", "diff", "--cached", "--quiet"], lap.worktree, env)
    if staged.returncode == NOTHING_STAGED:
        return
    if staged.returncode != CHANGES_STAGED:
        raise CommandError(f"git diff --cached failed in {lap.worktree}: {staged.stderr.strip()}")
    run(["git", "commit", "--quiet", "--message", lap.title], lap.worktree, env)


def through_the_gate(lap: Lap, app: str, test_filter: str, epic_branch: str, settings: dict, home: Path,
                     main_tree: Path) -> list[Lap]:
    """Runs the targeted tests and, when they pass, the merge gate; returns the lap when it goes back to the build."""
    while True:
        try:
            with contextlib.redirect_stdout(sys.stderr):
                tested = targeted_tests.targeted_tests(lap.task, lap.worktree, epic_branch,
                                                       targeted_tests.Integration.REBASE, app, test_filter, home,
                                                       env_as_factory())
        except targeted_tests.MergeConflict as conflict:
            park(lap, lap.tries, f"rebasing the lap onto {epic_branch} conflicts in {', '.join(conflict.files)}",
                 main_tree)
            return []
        except targeted_tests.FilterRefused as refused:
            return count_try(lap, f"the filter needs fixing: {refused}", main_tree)
        except targeted_tests.TestRunError as error:
            raise SchedulerError(f"the targeted tests of {lap.task} did not run: {error}") from error
        if not tested.passed:
            return count_try(lap, f"the targeted tests failed with exit code {tested.exit_code}", main_tree)
        try:
            with contextlib.redirect_stdout(sys.stderr):
                merged = merge_gate.merge(merge_gate.LapToMerge(lap.task, lap.branch, lap.worktree, epic_branch),
                                          settings, home, main_tree)
        except merge_gate.EpicBranchMoved as moved:
            print(f"scheduler: {moved}, so the targeted tests run again", file=sys.stderr)
            continue
        except merge_gate.EmptyLap as empty:
            return count_try(lap, str(empty), main_tree)
        except merge_gate.GateRefused as refused:
            park(lap, lap.tries, f"the merge gate refused the lap: {refused}", main_tree)
            return []
        if merged.failed_steps:
            raise SchedulerError(f"{epic_branch} has the lap's commit {merged.sha}, but these steps failed:\n"
                                 + "\n".join(f"  {step}" for step in merged.failed_steps))
        return []


def report(bead: str, task_id: str, outcome: str, app: str | None, test_filter: str | None, home: Path,
           main_tree: Path) -> dict:
    settings = repo_settings.load(repo_settings.settings_path(home, main_tree))
    epic = checked_epic(bead, settings, main_tree)
    lap = building_lap(epic, task_id)
    refuse_arguments(outcome, app, test_filter)
    if outcome == CUT_OFF:
        rebuilds = [lap]
    elif outcome == FAILED:
        rebuilds = count_try(lap, "the build worker reported that the build failed", main_tree)
    else:
        commit_build(lap)
        rebuilds = through_the_gate(lap, str(app), str(test_filter), recorded_branch(epic), settings, home,
                                    main_tree)
    return next_moves(bead, home, main_tree, rebuilds, False)


def main(argv: list[str]) -> int:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("epic")
    shared.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    parser = argparse.ArgumentParser(prog="scheduler.py", description="Print the manager's next moves on a "
                                                                       "handed-off epic.")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("next", parents=[shared], help="restart the laps left at the build, open the laps that fit "
                                                    "and print the next moves")
    reporting = modes.add_parser("report", parents=[shared], help="take how a lap's build ended, and print the "
                                                                  "next moves")
    reporting.add_argument("task")
    reporting.add_argument("outcome", choices=OUTCOMES)
    reporting.add_argument("--app", help="with done, the app whose targeted tests the builder named")
    reporting.add_argument("--filter", help="with done, the filter the builder named")
    args = parser.parse_args(argv)

    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = repo_settings.jidoka_home(args.jidoka_home)
        if args.mode == "next":
            printed = next_moves(args.epic, home, main_tree, [], True)
        else:
            printed = report(args.epic, args.task, args.outcome, args.app, args.filter, home, main_tree)
    except (SchedulerError, validation.ValidationError, HandoffError, BenchError, CommandError,
            repo_settings.SettingsError, holdouts.HoldoutsError, private_docs.ClashError, OSError) as error:
        print(f"scheduler: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
