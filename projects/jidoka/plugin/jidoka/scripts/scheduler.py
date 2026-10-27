#!/usr/bin/env python3
"""Reads a handed-off epic's beads and prints what the manager does next.

Run it from inside any checkout of the repo. The epic's tasks are its
children that are neither closed nor epics. A lap is open while its task is
not closed and its metadata holds `lap.stage`.

`next <epic>` makes the checks below, then opens a lap for each ready task,
in bd priority order and then by id, while the open laps of the epic number
fewer than the repo settings' lap_limit, and never for a task whose area an
open lap already holds. A task is ready when every bead it waits on is
closed, it has no open lap, no assignee and no `human` label, and its
`lap.area` metadata names its area.

Opening a lap makes, or reuses, the worktree <main checkout>/.worktrees/lap-<task>
on the branch lap/<task>, cut from the epic branch the epic records as
`factory.branch`, and the lap's scratch folder <worktree>/.scratch. The
repo's info/exclude gets `.worktrees/` and `/.scratch/`, so neither shows in
any worktree's git status. Then, with BEADS_ACTOR set to jidoka, the task
goes to in_progress with the assignee jidoka, and its metadata gets
`lap.number` (1), `lap.stage` (build), `lap.tries` (0), `lap.workspace` (the
worktree), `lap.slot` (the lowest slot from 1 up that no open lap of the
epic holds) and `lap.branch`. A rerun after a failure reuses the worktree
and branch it finds.

It prints one JSON object:
  epic       the epic's id.
  branch     the epic branch.
  lap_limit  the repo settings' lap limit.
  actions    the laps this call opened, each with action ("build"), task,
             title, area, lap (its number), slot, branch, worktree and
             scratch. An empty list when no task is ready or none fits.
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
     a refusal writes nothing.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import git_exclude
import holdouts
import repo_settings
from bench import FACTORY_LABEL, WORKTREE_FOLDER, BenchError, Workspace, hide_worktrees, make_worktree
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, head_of, run
from handoff import BLOCKING, BRANCH_KEY, CLOSED, ONBOARD, Epic, HandoffError, Rerun, epic_of, recorded_branch, \
    problems_while_held

ACTOR = "jidoka"
HUMAN_LABEL = "human"
BUILD = "build"
FIRST_LAP = 1
FIRST_SLOT = 1
NO_TRIES = 0
LAP_BRANCH_PREFIX = "lap/"
LAP_FOLDER_PREFIX = "lap-"
SCRATCH_FOLDER = ".scratch"
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
    if not metadata.get("lap.stage"):
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


def open_workspace(lap: Lap, epic_head: str, main_tree: Path) -> None:
    make_worktree(Workspace(lap.branch, lap.worktree, epic_head), main_tree)
    lap.scratch.mkdir(exist_ok=True)


def record(lap: Lap, main_tree: Path) -> None:
    env = {**os.environ, "BEADS_ACTOR": ACTOR}
    run(["bd", "update", lap.task, "--status=in_progress", f"--assignee={ACTOR}",
         "--set-metadata", f"lap.number={lap.number}",
         "--set-metadata", f"lap.stage={lap.stage}",
         "--set-metadata", f"lap.tries={lap.tries}",
         "--set-metadata", f"lap.workspace={lap.worktree}",
         "--set-metadata", f"lap.slot={lap.slot}",
         "--set-metadata", f"lap.branch={lap.branch}"], main_tree, env)


def next_moves(bead: str, home: Path, main_tree: Path) -> dict:
    epic = epic_of(bead, main_tree, RERUN)
    settings = repo_settings.load(repo_settings.settings_path(home, main_tree))
    problems = scheduler_problems(epic, settings, main_tree)
    if problems:
        raise SchedulerError(f"the factory takes no next move on {epic.id}, and nothing was written:\n"
                             + "\n".join(f"  {problem}" for problem in problems))
    tasks = tasks_of(epic)
    held = [lap for lap in map(open_lap, tasks) if lap is not None]
    limit = lap_limit_of(settings)
    planned = planned_laps([task for task in tasks if is_ready(task)], held, limit, main_tree)
    epic_branch = recorded_branch(epic)
    epic_head = head_of(f"refs/heads/{epic_branch}", main_tree)
    if epic_head is None:
        raise SchedulerError(f"the epic branch {epic_branch} went away during the call, and nothing was written")
    if planned:
        hide_worktrees(main_tree)
        git_exclude.add(git_exclude.exclude_file(main_tree), [git_exclude.exclude_line(SCRATCH_FOLDER, True)])
    for lap in planned:
        open_workspace(lap, epic_head, main_tree)
    for lap in planned:
        record(lap, main_tree)
    return {"epic": epic.id, "branch": epic_branch, "lap_limit": limit,
            "actions": [{"action": BUILD, **lap.fields()} for lap in planned],
            "laps": [{**lap.fields(), "stage": lap.stage, "tries": lap.tries}
                     for lap in sorted(held + planned, key=lambda lap: lap.slot)]}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="scheduler.py", description="Print the manager's next moves on a "
                                                                       "handed-off epic.")
    modes = parser.add_subparsers(dest="mode", required=True)
    nexting = modes.add_parser("next", help="open the laps that fit and print the next moves")
    nexting.add_argument("epic")
    nexting.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = repo_settings.jidoka_home(args.jidoka_home)
        printed = next_moves(args.epic, home, main_tree)
    except (SchedulerError, HandoffError, BenchError, CommandError, repo_settings.SettingsError,
            holdouts.HoldoutsError, OSError) as error:
        print(f"scheduler: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
