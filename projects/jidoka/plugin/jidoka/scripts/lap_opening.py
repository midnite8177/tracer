"""Opens the laps of an epic: which ready tasks get a lap, within the lap limits, and the workspace of each.

The holds the scheduler works out say when laps may open (`Holds.lets_open`), and this module does it. Opening a lap
makes, or reuses, the worktree <main checkout>/.worktrees/lap-<task> on the branch lap/<task>, cut from the epic branch
the epic records as `factory.branch`, and the lap's scratch folder <worktree>/.scratch. The repo's info/exclude gets
`.worktrees/` and `/.scratch/`, so neither shows in any worktree's git status. In a repo whose settings keep the
glossary and ADRs private, each worktree gets the links private_docs.share makes to the main checkout's copies, and a
worktree that holds its own copy stops the call, with the reason on stderr, before any task is claimed. Then, with
BEADS_ACTOR set to jidoka, the task goes to in_progress with the assignee jidoka, and its metadata gets `lap.number`
(1, or one more than the number of the lap the task left parked, blocked or interrupted), `lap.stage` (the build, or
the research on the full track while the task holds no `research brief:` comment), `lap.tries` (0), `lap.workspace`
(the worktree), `lap.slot` (the lowest slot from 1 up that no open lap on the machine holds, as slots.py says) and
`lap.branch`. A rerun after a failure, and the lap that follows a park, reuse the worktree and branch they find. A
reused lap branch that lacks the epic branch's head is first rebased onto it under the merge lock, with the work its
worktree holds uncommitted kept as it was, so the lap starts from the work left behind on top of the epic branch as it
is now. A rebase that conflicts is aborted, and the task parks with the conflicting files named and no action, its
worktree and branch as they were, and that lap does not open. A new lap starts with no tries, no cutoffs, no
send-backs and no merge tries, because each is a cap on one lap.

A lap opens for each ready task, in bd priority order and then by id, while the open laps of the epic number fewer than
the lap limit, which is the lowest of the machine settings' lap_limit (4 when they hold none), the repo settings'
lap_limit and the epic's own factory rule, read afresh on every call, and never for a task whose area an open lap
already holds, whether a lap of this epic or of another running epic of the same repo. The open laps of every running
epic on the machine, in any repo, number no more than the machine settings' lap limit together; slots.py holds that
rule and the one that keeps each running epic at least one slot. A task is ready when every bead it waits on is closed,
it has no open lap, no assignee and no `human` label, and its `lap.area` metadata names its area.
"""
from __future__ import annotations

from pathlib import Path

import git_exclude
import lap_record
import lap_stages
import private_docs
import rules
import slots
from bench import Workspace, make_worktree
from commands import SCRATCH_FOLDER, bd_comments, env_as_factory, metadata_of, run
from epic_branch import branch_head
from epic_reader import Epic, by_priority
from lap_holds import Holds
from lap_outcomes import SchedulerError
from lap_record import BRIEF_PREFIX, BUILD, FULL_TRACK, RESEARCH, Lap, track_of
from worktrees import hide_worktrees


def first_stage(task: str, track: str, main_tree: Path) -> str:
    """The stage a new lap starts at, the research brief on the full track while the task has none, else the build."""
    if track == FULL_TRACK and not any(str(comment.get("text") or "").startswith(BRIEF_PREFIX)
                                       for comment in bd_comments(task, main_tree)):
        return RESEARCH
    return BUILD


def open_workspace(lap: Lap, epic_head: str, home: Path, main_tree: Path) -> list[str]:
    """Makes the lap's worktree, or brings the one it reuses onto the epic head, and returns the files that conflict
    with the epic branch, empty when none does."""
    make_worktree(Workspace(lap.branch, lap.worktree, epic_head), main_tree)
    conflicted = lap_stages.rebase_onto_epic_head(lap, epic_head, home)
    private_docs.share(main_tree, lap.worktree.resolve(), home)
    lap.scratch.mkdir(exist_ok=True)
    return conflicted


def park_on_conflict(lap: Lap, epic: Epic, conflicted: list[str], main_tree: Path) -> None:
    lap_stages.park_lap(lap, epic.id, lap.tries,
                        f"the work left behind conflicts with {epic.branch} in {', '.join(conflicted)}, so the "
                        "rebase onto it was aborted before the lap started", main_tree)


def record(lap: Lap, main_tree: Path) -> None:
    run(["bd", "update", lap.task, *lap_record.opening(lap)], main_tree, env_as_factory())


def planned_laps(epic: Epic, holds: Holds, resumed: set[str], limit: rules.LapLimits, now: int, home: Path,
                 main_tree: Path) -> list[Lap]:
    """The new laps that fit, each with the slot it takes, in the order they open. The slots of the laps the epic
    holds and of the laps planned are recorded for the machine, as slots.py says. Only the tasks the holds let open
    are planned."""
    openable = {str(task["id"]): task for task in sorted(epic.ready_task_beads, key=by_priority)
                if holds.lets_open(str(task["id"]), resumed)}
    candidates = [slots.Candidate(task, lap_record.area_of(metadata_of(bead))) for task, bead in openable.items()]
    placements = slots.share(slots.Standing(home, epic.id, main_tree, limit.machine, now), holds.held, candidates,
                             limit.epic)
    return [lap_record.new_lap(openable[placed.task], placed.slot,
                               first_stage(placed.task, track_of(metadata_of(openable[placed.task])), main_tree),
                               now, main_tree)
            for placed in placements]


def open_laps(epic: Epic, holds: Holds, resumed: set[str], limit: rules.LapLimits, now: int, home: Path,
              main_tree: Path) -> list[Lap]:
    """Opens a lap for each ready task that fits beside the open laps of the epic and of the machine, and whose area
    no other running epic of the repo holds, and that the holds let open; the brake lets through only the tasks whose
    laps this call ended, named in `resumed`.

    The slots of the laps the epic holds and of the laps it opens are recorded for the machine, as slots.py says,
    before any lap is opened. A lap that ends gives its slot back at the epic's next call.
    """
    epic_branch = epic.branch
    epic_head = branch_head(epic_branch, main_tree)
    if epic_head is None:
        raise SchedulerError(f"the epic branch {epic_branch} went away during the call, and nothing was written")

    planned = planned_laps(epic, holds, resumed, limit, now, home, main_tree)
    if planned:
        hide_worktrees(main_tree)
        git_exclude.add(git_exclude.exclude_file(main_tree), [git_exclude.exclude_line(SCRATCH_FOLDER, True)])
    conflicts = {lap.task: open_workspace(lap, epic_head, home, main_tree) for lap in planned}
    for lap in planned:
        record(lap, main_tree)
    for lap in planned:
        if conflicts[lap.task]:
            park_on_conflict(lap, epic, conflicts[lap.task], main_tree)
    return [lap for lap in planned if not conflicts[lap.task]]
