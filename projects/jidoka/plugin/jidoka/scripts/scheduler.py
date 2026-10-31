#!/usr/bin/env python3
"""Reads a handed-off epic's beads and prints what the manager does next.

Run it from inside any checkout of the repo. The epic's tasks are its children that are neither closed nor epics. A
lap is open while its task is not closed and its metadata holds a `lap.stage` other than parked or blocked. This
module is the command line and the choice of the next moves. How a stage settles lives in the module of that stage,
which this text names where a mode hands over to it.

`next <epic>` is the call a manager makes when it starts, so it resumes the epic. It refuses, writing nothing, when
the epic's heartbeat is fresh, because a manager already runs it. Each call of a manager that succeeds claims the
epic with a fresh heartbeat that records the session in $JIDOKA_SESSION_ID, as heartbeat.py describes. It takes
every open lap at a worker stage for one an earlier session left with no worker, unless the human's brake holds it.
Git wins where it disagrees with the record. A lap whose branch git shows merged into the epic branch closes its
task as a merge does, and it drops the records of worktrees whose folders are gone. For each other lap it stops
the orphan workers left in its worktree, abandons a rebase left half done, and ends the lap interrupted as `stop`
does, which counts no cutoff and no try, so that the task is ready again with a new lap on the work it left. A merge
lock whose holder is gone is cleared. It reports each on stderr. Then it makes the checks below and opens the laps.

`carry-on <epic>` is the call that goes on after a pause, an unpark, a new task or a merge. It does what `next` does
after any outcome, with no restart and no heartbeat check.

`stop <epic>` is the call a manager makes when the human tells the host to stop at once. It ends every open lap of
the epic interrupted. The task is open with no assignee, `lap.stage` is interrupted, an `Interrupted:` comment says
so, and its worktree and branch are kept. A stop is no cutoff, no try and no park, so it changes no count and leaves
the brake as it was, and the interrupted task is ready again with a new lap. Then it sends the factory-stopped
notification through notify.py, which sends nothing when the epic has no open task left, and prints the host's line
for it on stderr. It leaves the epic's heartbeat stale, so that no beat from a host still open shows a manager. It
prints `{"epic", "interrupted"}`, the ids of the tasks whose laps it ended. A notification that cannot be sent is a
line on stderr and no failure.

`report <epic> <task> <outcome> [--app <app> --filter <filter>] [--why <why>] [--cause <cause>] [--agent <id>]
[--tier <tier>]` takes how the
worker of the task's open lap ended, one outcome of `done`, `failed`, `cut off`, `send back`, `question`, `blocked`,
`pass` or `cannot judge`, makes the checks below first, settles the lap as lap_stages.py describes, and then does what
`next` does, so its actions start with the lap that went back to a worker. `done` at the build or the merge needs
--app and --filter, and no other outcome takes them; --why goes only with `failed` and --cause only with `cut off`;
`pass` and `cannot judge` belong to the Spec check, which never ends `done`. A stage that runs past its wall clock,
as caps.py says, ends cut off whatever the worker reported. A task with no open lap at a worker stage takes no
outcome.

`report <epic> <task> "cut off" --cause <cause>` takes a worker that a usage limit, an outage, a billing error or an
auth failure cut off (`usage-limit`, `outage`, `billing` or `auth`) and pauses the epic, as pause.py describes: the
lap ends interrupted as `stop` ends it, no cutoff, try or park is counted, and the epic's `pause` metadata records
the cause and the second its wait ends. While the pause waits, no stage starts and no lap opens, whichever call is
made, and a lap that would go back to a worker ends interrupted instead. A billing error, an auth failure and an
outage past an hour send the factory-paused notification through notify.py. A report without a cause from a worker,
once the wait is over, ends the pause. The JIDOKA_NOW variable stands in for the clock, as clock.py says.

Opening a lap makes, or reuses, the worktree <main checkout>/.worktrees/lap-<task> on the branch lap/<task>, cut
from the epic branch the epic records as `factory.branch`, and the lap's scratch folder <worktree>/.scratch. The
repo's info/exclude gets `.worktrees/` and `/.scratch/`, so neither shows in any worktree's git status. In a repo
whose settings keep the glossary and ADRs private, each worktree gets the links private_docs.share makes to the main
checkout's copies, and a worktree that holds its own copy stops the call, with the reason on stderr, before any task
is claimed. Then, with BEADS_ACTOR set to jidoka, the task goes to in_progress with the assignee jidoka, and its
metadata gets `lap.number` (1, or one more than the number of the lap the task left parked, blocked or interrupted),
`lap.stage` (the build, or the research on the full track while the task holds no `research brief:` comment),
`lap.tries` (0), `lap.workspace` (the worktree), `lap.slot` (the lowest slot from 1 up that no open lap on the
machine holds, as slots.py says) and `lap.branch`. A rerun after a failure, and the lap that follows a park, reuse
the worktree and branch they find. A reused lap branch that lacks the epic branch's head is first rebased onto it
under the merge lock, with the work its worktree holds uncommitted kept as it was, so the lap starts from the work
left behind on top of the epic branch as it is now. A rebase that conflicts is aborted, and the task parks with the
conflicting files named and no action, its worktree and branch as they were. A new lap starts with no tries, no
cutoffs, no send-backs and no merge tries, because each is a cap on one lap.
A lap opens for each ready task, in bd priority order and then by id, while the open laps of the epic number fewer
than the lap limit, which is the lowest of the machine settings' lap_limit (4 when they hold none), the repo
settings' lap_limit and the epic's own factory rule, read afresh on every call, and never for a task whose area an
open lap already holds, whether a lap of this epic or of another running epic of the same repo. The open laps of
every running epic on the machine, in any repo, number no more than the machine settings' lap limit together;
slots.py holds that rule and the one that keeps each running epic at least one slot. A task is ready when every bead
it waits on is closed, it has no open lap, no assignee and no `human` label, and its `lap.area` metadata names its
area.

An epic whose spend has reached its budget, as budget.py describes, starts no stage: no lap opens, no pass stage runs,
and a lap that would go back to a worker ends interrupted as a pause ends it. The stages already running finish and
are reported as always. When none runs, the call parks the epic with a comment that names the spend and sends the
epic-parked notification through notify.py.

Every call reads the account's usage windows afresh, as reserves.py describes. A five-hour window past its reserve
pauses the epic on the cause `reserve` until the window resets, and a reading under the reserve ends that pause. A
seven-day window past its reserve stops the epic as a reached budget does, but the epic parks with a question that
gives the projection of the window and three choices, once for each window.

The `human` label is also the human's brake. A stage already running finishes, and its report is taken as always, but
no stage starts on a task that carries the label, and none starts on any task of an epic that carries it, no lap
opens, and a lap that goes back to a worker, or that `next` finds left with no worker, is not in the actions. It
stays open, with its tries, in `laps`. Taking the label off lets the next `next` or `report` start them, a restart
counting no cutoff. The epic's other brake, three parked laps in a row at one stage with no merge between, is
caps.py's.

When `next` or `report` finds the epic with every task closed and held by neither the human, the acceptance gate nor
a run of its holdouts (epics.state_of), the pass begins. Each stage of a pass prints its own action and repeats it on
every call until the stage is reported, so a manager that restarts starts the worker again. The stages come in this
order, and the module named holds the rules of the stage. Each report mode takes the worker's report, commits what it
left on the epic branch, prints the stage's fields under its key, and does what `carry-on` does:
  test cleanup  cleanup.py: `report-cleanup <epic>`.
  tidy          tidy.py: `report-tidy <epic>`.
  review        review.py: `report-review <epic>`, then `report-fix <epic>` when the review leaves a `fix` action.
  validation    holdouts_run.py `validate`, which runs validation.py once the stages above owe nothing. An epic that
                holds holdouts ends with a holdouts action until holdouts_run.py takes
                `report-holdouts <epic> [--ended failed|cut-off] [--why <why>]`.
  validation's merge  validation_merge.py, before validation: it merges main into the epic branch in the validation
                worktree, and when that conflicts the stage prints a `merge` action with no task, for the validation
                worktree, naming the conflicting `files`, and records `validation.merge` on the epic. It repeats the
                action until `report-merge <epic> [--ended failed|cut-off] [--why <why>]` takes the merge worker's
                report. A merge worker that finished the merge lets the next validation run on it, and validation
                takes the record off.
Each of these report modes, `report-holdouts` included, takes `--worker <agent id> <tier> [done|failed|cut-off]` once
for each worker it reports, and the review reports one for each lane. The call writes a ledger row for each, with no
task and the stage's name (`test-cleanup`, `tidy`, `review`, `fix` or `holdouts`), before it settles the stage, so a
refused report still prices the run. A stage that failed or was cut off is reported with `--ended failed|cut-off`
(`report-holdouts` also takes `--why`): the call settles nothing and prints what `carry-on` prints, so the stage is
still owed. Each worker's row ends as the third value of its `--worker` says, else as `--ended` says, else `done`, so
the batches or lanes that finished are priced `done` beside the one that failed. A report that names no worker writes
no row.
pass_ledger.py holds the cap on passes, and gate.py the acceptance gate. An epic at the gate whose human label came off
with no decision is parked again, as gate_guard.py says. A report that is missing or unusable refuses
the call and writes nothing. A stage that files tasks in the epic has this call open their laps.

Each call prints one JSON object:
  epic       the epic's id.
  branch     the epic branch.
  lap_limit  the lap limit this call applied: the lowest of the machine settings' lap limit, the repo settings'
             lap limit and the epic's factory rule.
  validation null, or when this call ran validation, its result (pass,
             fail or pending), head (the commit validated), tests, skipped,
             seconds, filed (the id of the first task a red run filed, or
             null) and filed_all (every id it filed).
  brake      null, or when the brake is on, {"stage", "laps"}.
  no_area    the ids of the open tasks that have no `lap.area`, such as one
             added after handoff. No lap opens for them. Each is also named
             on stderr with the bd command that sets its area, and the task
             is ready once it has one. A task that is assigned, labeled
             human or in an open lap is left out.
  paused     null, or while the epic's pause waits, {"cause", "since", "until", "retries", "wait_seconds"}.
  watch      true when the epic has an open task and is not at the acceptance gate, so a manager with nothing
             running waits with watch.py instead of ending. It stays true while the ready tasks wait on the
             room of another running epic, and watch.py then ends when that room frees.
  actions    the lap a report sent back to a worker or on to the next one,
             then the laps this call opened, then the pass stage's actions
             (test-cleanup, tidy, fix or the review lanes), then the
             holdouts run when the epic waits on one, each lap with action ("research",
             "build", "app-check", "spec-check" or "merge"), task, title,
             area, lap (its number), slot, branch, worktree, scratch, track
             ("simple" or "full"), answer, findings (null unless a Spec
             check sent the diff back), app_check (null unless the app
             check did), specs (the acceptance specs the task makes pass,
             an empty list for a task that makes none) and specs_command
             (null for a task that makes none, else the words a build's
             call to run_specs.py starts with), for a merge its reason,
             and for an app check the path of its report.
             An empty list when nothing goes back, and no task is ready or
             none fits. The answer is null unless the task's last park was
             a question. Then it is {"source": "comment", "text"} holding
             every comment anyone but jidoka posted since the question, or
             {"source": "recommendation", "text"} holding the recommended
             option's name when there are none. The human answers by taking
             the human label off; the task is ready again, and its new lap
             reuses the worktree and branch with their commits. An answer
             that asks back is for the build to reply to with a new
             question report, which parks the task again.
  laps       every open lap of the epic after this call, with the fields
             of an action but action, and with stage and tries.

The checks, each refusal saying what to do, all reported at once:
  the epic or one of its tasks waits on an open bead outside the epic;
  the epic holds an epic;
  the repo has no repo settings on this machine, or they hold no lap limit;
  the epic's factory rules cannot be read;
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
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import app_check
import budget
import caps
import clock
import gate_guard
import git_exclude
import heartbeat
import holdouts
import holdouts_run
import lap_record
import launcher
import ledger
import lap_stages
import merge_gate
import notify
import park
import pass_ledger
import pass_stages
import pause
import permission_question
import private_docs
import settings_reader
import reserves
import resume
import rules
import slots
import spec_check
import specs
from bench import BenchError, Workspace, make_worktree
from commands import (COMMAND_TIMEOUT_SECONDS, FACTORY_LABEL, HUMAN_LABEL, SCRATCH_FOLDER, CommandError,
                      NotAWholeNumber, bd_comments, env_as_factory, labels_of, metadata_of,
                      run, set_metadata)
from epic_branch import branch_head
from epic_reader import (BRANCH_KEY, ONBOARD, Epic, EpicReadError, Rerun, by_priority, epic_of, is_unclaimed,
                         problems_while_held)
from epics import state_of
from lap_outcomes import BLOCKED, CANNOT_JUDGE, CUT_OFF, DONE, FAILED, PASS, QUESTION, SEND_BACK, SchedulerError
from lap_record import (APP_CHECK, BRIEF_PREFIX, BUILD, FULL_TRACK, MERGE, RESEARCH, SPEC_CHECK, WORKER_STAGES, Lap,
                        open_lap, track_of, words)
from lap_stages import GateContext, interrupt_for_stop, interrupt_lap
from pass_support import PassError
from worktrees import hide_worktrees

SCRIPT = "scheduler"
PASS_ENDINGS = ("failed", "cut-off")
PASS_OUTCOMES = {"failed": FAILED, "cut-off": CUT_OFF}
WORKER_OUTCOMES = {"done": DONE, **PASS_OUTCOMES}
NATIVE_ROUTE = "native"
OUTCOMES = [DONE, FAILED, CUT_OFF, QUESTION, SEND_BACK, BLOCKED, PASS, CANNOT_JUDGE]
SECONDS_PER_MINUTE = 60
HANDOFF = "/jidoka:handoff"
RERUN = Rerun(on_the_holding_epic="Run the scheduler on the epic that holds it",
              after_onboarding="run the scheduler again")


def lacks_only_an_area(task: dict) -> bool:
    """A task no lap will open for because its `lap.area` is missing, such as one added after handoff."""
    return is_unclaimed(task) and not lap_record.area_of(metadata_of(task))


def scheduler_problems(epic: Epic, settings: dict, main_tree: Path) -> list[str]:
    problems = problems_while_held(epic, settings, RERUN)
    if settings and not rules.repo_lap_limit(settings):
        problems.append(f"the repo settings hold no lap limit. Run {ONBOARD} again to record one")
    try:
        rules.of_epic(epic.shown)
    except rules.RulesError as error:
        problems.append(f"{error}. Write them again with rules.py")
    if FACTORY_LABEL not in labels_of(epic.shown):
        problems.append(f"{epic.id} does not carry the {FACTORY_LABEL} label, so the factory does not hold it. "
                        f"Hand it off first with {HANDOFF} {epic.id}")
    branch = epic.branch
    if not branch:
        problems.append(f"{epic.id} records no epic branch as its {BRANCH_KEY} metadata. Hand it off again "
                        f"with {HANDOFF} {epic.id}")
    elif branch_head(branch, main_tree) is None:
        problems.append(f"the epic branch {branch} that {epic.id} records does not exist. Restore it, or take "
                        f"the {FACTORY_LABEL} label off {epic.id} and hand it off again")
    return problems


def is_parked(epic: Epic) -> bool:
    """The epic carries the human label, the human's brake, so no stage starts and no lap opens."""
    return state_of(epic.shown).labeled_for_human


def is_finished(epic: Epic) -> bool:
    """Every task of the epic is closed, and the epic waits on neither the human, the acceptance gate nor a run of
    its holdouts."""
    return bool(epic.children) and not epic.tasks and state_of(epic.shown).waits_on_nothing


def has_work_to_wait_for(epic: Epic) -> bool:
    """The epic has an open task and is not at the acceptance gate, so a manager with nothing running waits for a
    change instead of ending."""
    return bool(epic.tasks) and not state_of(epic.shown).at_the_gate


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


def restart_clock(lap: Lap, now: int, main_tree: Path) -> Lap:
    """A stage that reruns starts its wall clock again."""
    restarted, arguments = lap_record.restarting_clock(lap, now)
    run(["bd", "update", lap.task, *arguments], main_tree, env_as_factory())
    return restarted


def checked_epic(bead: str, settings: dict, main_tree: Path) -> Epic:
    epic = epic_of(bead, main_tree, RERUN)
    problems = scheduler_problems(epic, settings, main_tree)
    if problems:
        raise SchedulerError(f"the factory takes no next move on {epic.id}, and nothing was written:\n"
                             + "\n".join(f"  {problem}" for problem in problems))
    return epic


def answer_fields(lap: Lap, metadata: dict, epic: str, home: Path, main_tree: Path) -> dict | None:
    """The answer the lap's build carries when its task was parked on a question, and None otherwise.

    The answer to a permission question also puts the denied call's pattern on the list it names, so the
    worker the lap starts is allowed the call.
    """
    answer = park.answer_of(lap.task, str(metadata.get(park.RECOMMENDED_KEY) or ""), main_tree)
    if answer is None:
        return None
    denial = park.denial_in(metadata)
    if denial is not None:
        try:
            permission_question.allow_answered(denial, answer.replies, epic, home, main_tree)
        except (permission_question.AnswerError, rules.RulesError, settings_reader.SettingsError) as error:
            print(f"scheduler: the answer on {lap.task} allowed no call: {error}", file=sys.stderr)
    return answer.fields()


def action_of(lap: Lap, answer: dict | None, made_to_pass: list[str]) -> dict:
    """The action that starts the lap's worker: a build, a merge worker with the reason it was called, or an app check
    with the path of the report it writes. It names the specs the task makes pass and, when there are some, the words
    that start the worker's call to run_specs.py."""
    extra = {}
    if lap.stage == MERGE:
        extra = {"reason": lap.merge_why}
    elif lap.stage == APP_CHECK:
        extra = {"report": str(lap.scratch / app_check.APP_CHECK_REPORT)}
    return {"action": lap.stage, **lap.fields(), **extra, "answer": answer, "specs": made_to_pass,
            "specs_command": launcher.run_specs_command() if made_to_pass else None,
            "findings": spec_check.from_stored(lap.findings) or None,
            "app_check": spec_check.from_stored(lap.app_findings) or None}


def refuse_second_manager(epic: str, home: Path) -> None:
    """Refuses a manager on an epic whose heartbeat is fresh, because a manager already runs it."""
    now = clock.now()
    seconds = heartbeat.fresh_age_seconds(home, epic, now)
    if seconds is not None:
        wait = heartbeat.FRESH_SECONDS - seconds + 1
        raise SchedulerError(f"{epic} already has a manager: its heartbeat is {seconds} seconds old, and a heartbeat "
                             f"is fresh for {heartbeat.FRESH_SECONDS}. If that manager is gone, run this again in "
                             f"{wait} seconds. Nothing was written")


def close_merged_lap(lap: Lap, sha: str, epic_branch: str, epic: str, main_tree: Path) -> None:
    """Closes the task of a lap that git shows merged, as the merge gate would have."""
    merged = merge_gate.close_out(merge_gate.LapToMerge(lap.task, lap.branch, lap.worktree, epic_branch), sha,
                                  main_tree)
    print(f"scheduler: {lap.task} is merged into {epic_branch} at {sha}, though its record said the {lap.stage}, "
          "so git wins and its task is closed", file=sys.stderr)
    for step in merged.failed_steps:
        print(f"scheduler: closing {lap.task}: {step}", file=sys.stderr)
    caps.note_merge(epic, main_tree)


def resume_laps(epic: Epic, home: Path, main_tree: Path) -> set[str]:
    """Brings a stopped factory's records and machine in line with git; returns the tasks whose laps it ended
    interrupted.

    The merge lock of a dead holder is cleared and the records of lost worktrees are dropped. Each open lap at a
    worker stage that the human's brake does not hold is checked against git: a lap git shows merged closes its
    task, and any other ends interrupted, after its orphan workers stop and a rebase it left half done is
    abandoned, so the task is ready for a new lap on its worktree and branch.
    """
    cleared = resume.clear_dead_merge_lock(home, clock.now())
    if cleared is not None:
        print(f"scheduler: {cleared}", file=sys.stderr)
    resume.prune_worktrees(main_tree)
    if is_parked(epic):
        return set()
    epic_branch = epic.branch
    interrupted: set[str] = set()
    labeled = epic.labeled_task_ids
    running = [lap for lap in map(open_lap, epic.open_task_beads)
               if lap is not None and lap.stage in WORKER_STAGES and lap.task not in labeled]
    for lap in sorted(running, key=lambda lap: lap.slot):
        merged = resume.merged_head(lap.branch, lap.title, epic_branch, main_tree)
        if merged is not None:
            close_merged_lap(lap, merged, epic_branch, epic.id, main_tree)
            continue
        for pid in resume.stop_orphans(lap.worktree):
            print(f"scheduler: stopped process {pid}, a worker left running in {lap.worktree}", file=sys.stderr)
        if lap.worktree.is_dir():
            lap_stages.abandon_rebase(lap)
        print(f"scheduler: {lap.task} was left at the {lap.stage} with no worker, so its lap ends interrupted and "
              "a new lap starts on its worktree", file=sys.stderr)
        interrupt_for_stop(lap, main_tree)
        interrupted.add(lap.task)
    return interrupted


@dataclass(frozen=True)
class PassState:
    """What settling the epic's own state left: the epic as bd shows it now, the validation this call ran, the holdouts
    the epic waits on, and the pass stage's actions."""
    epic: Epic
    validated: pass_stages.Settled | None
    holdouts_run: holdouts_run.HoldoutsToRun | None
    pass_actions: list[dict]


@dataclass(frozen=True)
class Holds:
    """What holds the epic's laps in this call: the laps that start again, the laps still open, the pause that waits,
    and the brake."""
    rebuilds: list[Lap]
    held: list[Lap]
    waiting: pause.Pause | None
    brake: caps.Brake
    epic_parked: bool
    will_park: bool

    @property
    def stops_new_laps(self) -> bool:
        return self.epic_parked or self.waiting is not None or self.will_park


@dataclass(frozen=True)
class Parking:
    """Why the epic starts no new stage and parks once none runs: what it reached, in words that follow the epic's id,
    when its laps start again, and how it parks."""
    reason: str
    resumes_when: str
    park: Callable[[], None]


@dataclass(frozen=True)
class Standstill:
    """What keeps the epic from starting a stage in this call: a pause that waits, or a reached budget or a passed
    seven-day reserve that parks it once no stage runs."""
    waiting: pause.Pause | None
    parking: Parking | None

    @property
    def is_on(self) -> bool:
        return self.waiting is not None or self.parking is not None


def parking_of(epic: Epic, reading: reserves.Reading | None, now: int, home: Path,
               main_tree: Path) -> Parking | None:
    """The parking that holds the epic: its budget when reached, else its seven-day reserve when passed."""
    reached = budget.reached_by(epic.shown, home)
    if reached is not None:
        return Parking(reached.reason, budget.RESUMES_WHEN, lambda: park_at_the_budget(epic, reached, home, main_tree))
    window = reserves.seven_day_past_reserve(epic.shown, reading, now)
    if window is not None:
        return Parking(window.reason, reserves.RESUMES_WHEN,
                       lambda: park_at_the_reserve(epic, window, now, home, main_tree))
    return None


def settle_epic(epic: Epic, settings: dict, home: Path, main_tree: Path) -> PassState:
    """Settles the epic's own state: the pass it owes, the pass cap, and the holdouts it waits on. The epic is read
    again after each step that writes on it."""
    ran = pass_stages.PassRun([], None)
    if gate_guard.is_unlabeled_at_the_gate(epic.shown):
        gate_guard.park_again(epic.id, main_tree)
        epic = checked_epic(epic.id, settings, main_tree)
    if is_finished(epic):
        ran = pass_stages.run_pass(epic, settings, home, main_tree)
        if ran.validated is not None:
            epic = checked_epic(epic.id, settings, main_tree)
    if pass_ledger.parks_at_the_cap(epic.shown, bool(epic.tasks)):
        pass_ledger.park_at_the_cap(epic.id, epic.shown, home, main_tree)
        epic = checked_epic(epic.id, settings, main_tree)
        notify.announce(notify.EPIC_PARKED, epic.id, home, main_tree, SCRIPT)
    to_run = ran.holdouts
    if to_run is None:
        to_run = pass_stages.holdouts_owed(epic, home, main_tree)
    return PassState(epic, ran.validated, to_run, ran.actions)


def running_laps(held: list[Lap]) -> list[Lap]:
    """The open laps at a worker stage, by slot. With no worker of this manager running, an earlier session left
    each of them."""
    return [lap for lap in sorted(held, key=lambda lap: lap.slot) if lap.stage in WORKER_STAGES]


def apply_holds(epic: Epic, held: list[Lap], rebuilds: list[Lap], standstill: Standstill, now: int,
                home: Path, main_tree: Path) -> Holds:
    """Decides what holds the epic's laps. The human label, on the epic or on a task, keeps a lap from starting
    again, a standstill ends the laps that would start again interrupted, and the laps that go on start their wall
    clock again. The brake holds only the laps that have not opened."""
    labeled = epic.labeled_task_ids
    epic_parked = is_parked(epic)
    stopped = [lap for lap in rebuilds if epic_parked or lap.task in labeled]
    starting = [lap for lap in rebuilds if lap not in stopped]
    if epic_parked:
        print(f"scheduler: {epic.id} carries the {HUMAN_LABEL} label, so no stage starts and no lap opens until it "
              "is taken off. The stages already running finish", file=sys.stderr)
    for lap in stopped:
        print(f"scheduler: {lap.task} waits at the {lap.stage} for the {HUMAN_LABEL} label to come off, so no stage "
              "starts on it", file=sys.stderr)
    waiting, parking = standstill.waiting, standstill.parking
    interruption = None
    if waiting is not None:
        print(f"scheduler: {epic.id} is paused on {pause.WORDS[waiting.cause]} for {waiting.until - now} more "
              "seconds, so no stage starts and no lap opens until then", file=sys.stderr)
        interruption = (f"the factory paused on {pause.WORDS[waiting.cause]}", "the factory goes on after the pause")
    elif parking is not None:
        interruption = (f"{epic.id} {parking.reason}", parking.resumes_when)
    if interruption is not None:
        because, resumes_when = interruption
        for lap in starting:
            interrupt_lap(lap, f"{because} before the {lap.stage} could start again", resumes_when, main_tree)
        held = [lap for lap in held if lap not in starting]
        starting = []
    if waiting is not None:
        notify.announce(notify.FACTORY_PAUSED, epic.id, home, main_tree, SCRIPT)
    starting = [restart_clock(lap, now, main_tree) for lap in starting]
    brake = caps.brake_after_new_beads(epic.shown, [str(child["id"]) for child in epic.children], main_tree)
    if brake.is_on:
        print(f"scheduler: {brake.laps} laps in a row parked at the {brake.stage} with no merge between, so no new "
              f"lap opens until a fix task is filed in {epic.id}. The laps already open run on", file=sys.stderr)
    return Holds(starting, held, waiting, brake, epic_parked, parking is not None)


def park_at_the_budget(epic: Epic, reached: budget.Reached, home: Path, main_tree: Path) -> None:
    """Parks the epic whose budget is reached, now that no stage of it runs, and tells the human."""
    print(f"scheduler: {epic.id} spent ${reached.spent:.2f} of its budget of ${reached.budget:.2f}, so no stage "
          "starts and it is parked", file=sys.stderr)
    budget.park_epic_at(epic.id, reached, main_tree)
    notify.announce(notify.EPIC_PARKED, epic.id, home, main_tree, SCRIPT)


def park_at_the_reserve(epic: Epic, window: reserves.Window, now: int, home: Path, main_tree: Path) -> None:
    """Parks the epic whose seven-day window is past its reserve, now that no stage of it runs, asks the human, and
    tells the human."""
    print(f"scheduler: {epic.id} is on an account whose {window.name} window is {window.used_percent:g}% used, past "
          "its reserve, so no stage starts and it is parked with a question", file=sys.stderr)
    reserves.park_epic_at(epic.id, window, now, home, main_tree)
    notify.announce(notify.EPIC_PARKED, epic.id, home, main_tree, SCRIPT)


def unplaced_tasks(tasks: list[dict]) -> list[str]:
    """The ids of the tasks no lap opens for because they have no area, each named on stderr with the command that
    sets it."""
    unplaced = [str(task["id"]) for task in sorted(tasks, key=by_priority) if lacks_only_an_area(task)]
    for task_id in unplaced:
        setting = " ".join(set_metadata((lap_record.AREA_KEY, "<area>")))
        print(f"scheduler: {task_id} has no area, so no lap opens for it. Run bd update {task_id} {setting}",
              file=sys.stderr)
    return unplaced


def open_laps(epic: Epic, holds: Holds, resumed: set[str], limit: rules.LapLimits, now: int, home: Path,
              main_tree: Path) -> list[Lap]:
    """Opens a lap for each ready task that fits beside the open laps of the epic and of the machine, and whose area
    no other running epic of the repo holds, unless the epic is parked or paused; the brake lets through only the
    tasks whose laps this call ended.

    The slots of the laps the epic holds and of the laps it opens are recorded for the machine, as slots.py says,
    before any lap is opened. A lap that ends gives its slot back at the epic's next call.
    """
    openable = {str(task["id"]): task for task in sorted(epic.ready_task_beads, key=by_priority)
                if not holds.brake.is_on or str(task["id"]) in resumed}
    epic_branch = epic.branch
    epic_head = branch_head(epic_branch, main_tree)
    if epic_head is None:
        raise SchedulerError(f"the epic branch {epic_branch} went away during the call, and nothing was written")

    candidates = [] if holds.stops_new_laps else [slots.Candidate(task, lap_record.area_of(metadata_of(bead)))
                                                   for task, bead in openable.items()]
    placements = slots.share(slots.Standing(home, epic.id, main_tree, limit.machine, now), holds.held, candidates,
                             limit.epic)
    planned = [lap_record.new_lap(openable[placed.task], placed.slot,
                                  first_stage(placed.task, track_of(metadata_of(openable[placed.task])), main_tree),
                                  now, main_tree)
               for placed in placements]
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


def next_moves(bead: str, home: Path, main_tree: Path, rebuilds: list[Lap], restarting: bool) -> dict:
    """Prints the laps that go back to a worker or start, after the rebuilds of laps a report sent back.

    The call claims the epic's heartbeat for the session it runs in, as heartbeat.claim says. It reads the specs each
    task makes pass first, so metadata that cannot be read stops the call before a lap opens that would get no worker.

    When restarting, no worker of this manager is running, so every open lap at a worker stage was left by an
    earlier session. The call refuses when the epic's heartbeat is fresh, resumes the factory as resume_laps
    describes, and opens a new lap for each task whose lap it ended.
    """
    settings = settings_reader.read_settings(home, main_tree)
    epic = checked_epic(bead, settings, main_tree)
    resumed: set[str] = set()
    if restarting:
        refuse_second_manager(epic.id, home)
        resumed = resume_laps(epic, home, main_tree)
        epic = checked_epic(bead, settings, main_tree)
    now = clock.now()
    reading = reserves.read(home, now, epic.shown)
    if reserves.sync_pause(epic.id, epic.shown, reading, now, main_tree):
        epic = checked_epic(bead, settings, main_tree)
    standstill = Standstill(pause.waiting_at(epic.shown, now), parking_of(epic, reading, now, home, main_tree))
    state = PassState(epic, None, None, []) if standstill.is_on else settle_epic(epic, settings, home, main_tree)
    epic = state.epic
    tasks = epic.open_task_beads
    open_now = [lap for lap in map(open_lap, tasks) if lap is not None]
    holds = apply_holds(epic, open_now, running_laps(open_now) if restarting else rebuilds, standstill, now, home,
                        main_tree)
    if standstill.parking is not None and not holds.held:
        standstill.parking.park()
    limit = rules.lap_limits(epic.shown, settings, home)
    unplaced = unplaced_tasks(tasks)
    try:
        made_to_pass = {str(task["id"]): specs.specs_of(task) for task in tasks}
    except specs.SpecsError as error:
        raise SchedulerError(str(error)) from error
    heartbeat.claim(home, epic.id, clock.now())
    planned = open_laps(epic, holds, resumed, limit, now, home, main_tree)
    metadata = {str(task["id"]): metadata_of(task) for task in tasks}
    return {"epic": epic.id, "branch": epic.branch, "lap_limit": limit.epic,
            "validation": state.validated.fields() if state.validated is not None else None, "no_area": unplaced,
            "brake": holds.brake.fields() if holds.brake.is_on else None,
            "paused": holds.waiting.fields(now) if holds.waiting is not None else None,
            "watch": has_work_to_wait_for(epic),
            "actions": [action_of(lap, answer_fields(lap, metadata[lap.task], epic.id, home, main_tree),
                                  made_to_pass[lap.task])
                        for lap in holds.rebuilds + planned] + state.pass_actions
                       + ([state.holdouts_run.fields()] if state.holdouts_run is not None else []),
            "laps": [{**lap.fields(), "stage": lap.stage, "tries": lap.tries}
                     for lap in sorted(holds.held + planned, key=lambda lap: lap.slot)]}


def working_lap(epic: Epic, task_id: str) -> Lap:
    for task in epic.open_task_beads:
        if str(task["id"]) == task_id:
            lap = open_lap(task)
            if lap is None:
                raise SchedulerError(f"{task_id} has no open lap, so it takes no outcome, and nothing was written")
            if lap.stage not in WORKER_STAGES:
                raise SchedulerError(f"the lap of {task_id} is at the stage {lap.stage}, not one of "
                                     f"{', '.join(WORKER_STAGES)}, so it takes no worker outcome, and nothing was "
                                     "written")
            return lap
    raise SchedulerError(f"{task_id} is not an open task of {epic.id}, and nothing was written")


@dataclass(frozen=True)
class Reported:
    """What a worker's report gives the settling of its lap: the app and the filter it named for its targeted tests,
    and the words that say why a failed or cut off stage ended."""
    app: str | None
    test_filter: str | None
    failed_why: str
    cutoff_why: str


@dataclass(frozen=True)
class Ending:
    """How a stage settles when its worker ends it with an outcome: whether the report names the targeted tests, and
    the call that settles the lap and returns the laps that go back to a worker."""
    names_tests: bool
    settle: Callable[[Lap, Reported, GateContext], list[Lap]]


def named_tests(lap: Lap, reported: Reported, context: GateContext) -> Lap:
    return lap_stages.name_tests(lap, str(reported.app), str(reported.test_filter), context.main_tree)


ANY_STAGE = None
ENDINGS: dict[tuple[str, str | None], Ending] = {
    (CUT_OFF, ANY_STAGE): Ending(False, lambda lap, reported, context: lap_stages.cut_off(
        lap, context.epic, reported.cutoff_why, context.main_tree)),
    (FAILED, ANY_STAGE): Ending(False, lambda lap, reported, context: lap_stages.count_try(
        lap, context.epic, reported.failed_why, context.main_tree)),
    (QUESTION, ANY_STAGE): Ending(False, lambda lap, reported, context: lap_stages.ask(
        lap, context.epic, context.home, context.main_tree)),
    (SEND_BACK, SPEC_CHECK): Ending(False, lambda lap, reported, context: lap_stages.spec_check_sent_back(
        lap, context.epic, context.main_tree)),
    (SEND_BACK, ANY_STAGE): Ending(False, lambda lap, reported, context: lap_stages.send_back(
        lap, context.epic, [], [], context.main_tree)),
    (BLOCKED, ANY_STAGE): Ending(False, lambda lap, reported, context: lap_stages.block(
        lap, context.epic, context.main_tree)),
    (PASS, SPEC_CHECK): Ending(False, lambda lap, reported, context: lap_stages.spec_check_passed(lap, context)),
    (CANNOT_JUDGE, SPEC_CHECK): Ending(False, lambda lap, reported, context: lap_stages.spec_check_cannot_judge(
        lap, context.epic, context.main_tree)),
    (DONE, RESEARCH): Ending(False, lambda lap, reported, context: lap_stages.research_done(
        lap, context.epic, context.main_tree)),
    (DONE, BUILD): Ending(True, lambda lap, reported, context: lap_stages.build_done(
        named_tests(lap, reported, context), context)),
    (DONE, APP_CHECK): Ending(False, lambda lap, reported, context: lap_stages.app_check_done(
        lap, context.epic, context.main_tree)),
    (DONE, MERGE): Ending(True, lambda lap, reported, context: lap_stages.reconciled(
        named_tests(lap, reported, context), context)),
}


def ending_for(outcome: str, stage: str) -> Ending:
    """The ending the table holds for the outcome at the stage; an outcome the stage cannot take is refused."""
    ending = ENDINGS.get((outcome, stage)) or ENDINGS.get((outcome, ANY_STAGE))
    if ending is not None:
        return ending
    if outcome == DONE:
        raise SchedulerError(f"the {words(SPEC_CHECK)} ends {PASS}, {SEND_BACK} or {CANNOT_JUDGE}, never {DONE}, "
                             "and nothing was written")
    raise SchedulerError(f"{outcome} is an outcome of the {words(SPEC_CHECK)}, and the lap is at the {stage}, "
                         "so nothing was written")


def refuse_arguments(ending: Ending, said: WorkerReport) -> None:
    if ending.names_tests and not (said.app and said.test_filter):
        raise SchedulerError(f"{DONE} needs --app and --filter, the app and the filter the builder named, and "
                             "nothing was written")
    if not ending.names_tests and (said.app is not None or said.test_filter is not None):
        raise SchedulerError(f"--app and --filter go only with {DONE} at the {BUILD} or the {MERGE}, and nothing was "
                             "written")
    if said.cause is not None and said.outcome != CUT_OFF:
        raise SchedulerError(f"--cause goes only with {CUT_OFF}, and nothing was written")
    if said.why is not None and said.outcome != FAILED:
        raise SchedulerError(f"--why goes only with {FAILED}, and nothing was written")


def pause_on_trouble(lap: Lap, epic: Epic, cause: str, main_tree: Path) -> list[Lap]:
    """Pauses the epic on the trouble the worker met, as pause.after_trouble says, and ends the lap interrupted.

    The cutoff counts toward no cap, because the trouble is not the lap's own, and the lap's task gets a new lap
    when the pause ends.
    """
    paused = pause.meet_trouble(epic.id, cause, clock.now(), main_tree)
    if paused is not None:
        run(["bd", "comment", epic.id, f"Paused: the {lap.stage} of {lap.task} met {pause.WORDS[cause]}. Nothing "
                                       f"new starts until {paused.until}, the second the next retry may start, "
                                       f"after {paused.retries} failed retries."], main_tree, env_as_factory())
    interrupt_lap(lap, f"the {lap.stage} was cut off by {pause.WORDS[cause]}, so the factory paused",
                  "the pause ends", main_tree)
    return []


def end_pause_after_a_retry_that_worked(epic: Epic, main_tree: Path) -> None:
    """A worker that ends without the trouble once the pause's wait is over shows the trouble gone."""
    held = pause.held_by(epic.shown)
    if held is not None and not held.is_waiting(clock.now()):
        pause.clear(epic.id, main_tree)


@dataclass(frozen=True)
class PassWorker:
    """A worker a pass stage's report names, and the ending the report gives it, one of WORKER_OUTCOMES' keys; None
    when it gives none and the report's own ending stands."""
    worker: ledger.Worker
    ending: str | None


def record_pass_in_ledger(epic: str, stage: str, outcome: str, workers: list[PassWorker], home: Path,
                          main_tree: Path) -> None:
    """Prices the runs of the workers of one pass stage in the ledger, a row for each worker, with the worker's own
    ending or else the report's `outcome`."""
    for each in workers:
        ended = outcome if each.ending is None else WORKER_OUTCOMES[each.ending]
        ledger.record_run_or_say(home, main_tree, epic, ledger.Where.of_pass(stage), each.worker, ended, clock.now())


@dataclass(frozen=True)
class WorkerReport:
    """What a worker's report names: its outcome, the app and the filter of its targeted tests, the trouble that cut
    it off, and why it failed."""
    outcome: str
    app: str | None
    test_filter: str | None
    cause: str | None
    why: str | None


def report(bead: str, task_id: str, said: WorkerReport, worker: ledger.Worker, home: Path, main_tree: Path) -> dict:
    settings = settings_reader.read_settings(home, main_tree)
    epic = checked_epic(bead, settings, main_tree)
    lap = working_lap(epic, task_id)
    outcome, cause = said.outcome, said.cause
    ending = ending_for(outcome, lap.stage)
    refuse_arguments(ending, said)
    now = clock.now()
    is_overdue = outcome != CUT_OFF and lap_record.is_past_wall_clock(lap.stage, lap.started, now)
    ledger.record_run_or_say(home, main_tree, epic.id, ledger.Where.of_lap(lap, now), worker,
                             CUT_OFF if is_overdue else outcome, now)
    if cause is not None:
        pause_on_trouble(lap, epic, cause, main_tree)
        return next_moves(bead, home, main_tree, [], False)
    end_pause_after_a_retry_that_worked(epic, main_tree)
    if is_overdue:
        past = f"ran past its wall clock of {lap_record.wall_clock_seconds(lap.stage) // SECONDS_PER_MINUTE} minutes"
        print(f"scheduler: the {lap.stage} of {task_id} {past}, so it ends cut off whatever the worker reported",
              file=sys.stderr)
        ending = ENDINGS[(CUT_OFF, ANY_STAGE)]
        cutoff_why = f"the {lap.stage} {past}"
    else:
        cutoff_why = f"the {lap.stage} worker ended for a reason outside its work"
    failed_why = said.why or f"the {lap.stage} worker reported that the {lap.stage} failed"
    context = GateContext(epic.id, epic.branch, settings, home, main_tree)
    rebuilds = ending.settle(lap, Reported(said.app, said.test_filter, failed_why, cutoff_why), context)
    return next_moves(bead, home, main_tree, rebuilds, False)


def report_stage(mode: str, bead: str, ended: str | None, why: str | None, workers: list[PassWorker], home: Path,
                 main_tree: Path) -> dict:
    """Takes the report of a pass stage's workers, prices their runs, settles the stage on the epic branch, then does
    what `carry-on` does.

    Workers that ended failed or cut off (`ended`) are priced with that ending unless the report gives a worker its
    own, and settle nothing, so the stage is still owed and the next call starts its worker again. A stage that counts
    its ended runs counts this one with `why`, and the cap parks the epic and notifies.

    A red holdout files a task in the epic, and this call opens its lap with the others.
    """
    stage = pass_stages.REPORT_MODES[mode]
    settings = settings_reader.read_settings(home, main_tree)
    epic = checked_epic(bead, settings, main_tree)
    record_pass_in_ledger(epic.id, stage.stage, DONE if ended is None else PASS_OUTCOMES[ended], workers, home,
                          main_tree)
    if ended is not None:
        if stage.count_ended_run is not None and stage.count_ended_run(epic.id, ended, why, main_tree):
            notify.announce(notify.EPIC_PARKED, epic.id, home, main_tree, SCRIPT)
        return next_moves(bead, home, main_tree, [], False)
    settled = stage.settle(epic.id, epic.branch, settings, home, main_tree)
    printed = next_moves(bead, home, main_tree, [], False)
    printed[stage.key] = settled.fields()
    return printed


def stop(bead: str, home: Path, main_tree: Path) -> dict:
    """Ends every open lap of the epic interrupted, then announces the stop."""
    epic = epic_of(bead, main_tree, RERUN)
    held = [lap for lap in map(open_lap, epic.open_task_beads) if lap is not None]
    for lap in held:
        interrupt_for_stop(lap, main_tree)
    heartbeat.mark_stopped(home, epic.id, clock.now())
    notify.announce(notify.FACTORY_STOPPED, epic.id, home, main_tree, SCRIPT)
    return {"epic": epic.id, "interrupted": [lap.task for lap in sorted(held, key=lambda lap: lap.slot)]}


def workers_of(args: argparse.Namespace) -> list[PassWorker]:
    """The workers a report names, each `AGENT TIER`, then `native` when the worker ran on the tier's native route,
    then optionally the worker's ending."""
    workers = []
    for given in args.worker:
        if len(given) < 2:
            raise SchedulerError(f"--worker takes an agent id and a tier, not {' '.join(given)}, and nothing was "
                                 "written")
        on_native = given[2:3] == [NATIVE_ROUTE]
        after = given[3:] if on_native else given[2:]
        if len(after) > 1 or (after and after[0] not in WORKER_OUTCOMES):
            raise SchedulerError(f"--worker takes an agent id, a tier, optionally {NATIVE_ROUTE} and optionally the "
                                 f"worker's ending, one of {', '.join(WORKER_OUTCOMES)}, not {' '.join(given)}, and "
                                 "nothing was written")
        workers.append(PassWorker(ledger.Worker(given[0], given[1], on_native), after[0] if after else None))
    return workers


def main(argv: list[str]) -> int:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("epic")
    shared.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    parser = argparse.ArgumentParser(prog="scheduler.py", description="Print the manager's next moves on a "
                                                                       "handed-off epic.")
    modes = parser.add_subparsers(dest="mode", required=True)
    worked = argparse.ArgumentParser(add_help=False)
    worked.add_argument("--worker", nargs="+", action="append", metavar="AGENT TIER [native] [ENDING]", default=[],
                        help="the agent id the host gave a worker, which names its tokens, the tier it ran on, "
                             "native when it ran on the tier's native route because its own route failed, and "
                             "optionally how it ended (done, failed or cut-off), which stands for --ended; once for "
                             "each worker the report covers")
    modes.add_parser("next", parents=[shared], help="restart the laps left at the build, open the laps that fit "
                                                    "and print the next moves")
    modes.add_parser("stop", parents=[shared], help="end every open lap interrupted, because the human stopped the "
                                                    "host, and send the stopped notification")
    modes.add_parser("carry-on", parents=[shared], help="print the next moves when the pause is over, a task was "
                                                        "unparked or added, or a lap merged, with no restart")
    for mode, stage in pass_stages.REPORT_MODES.items():
        stage_report = modes.add_parser(mode, parents=[shared, worked], help=stage.help)
        stage_report.add_argument("--ended", choices=PASS_ENDINGS, help="workers that failed or were cut off: price "
                                                                       "their runs and settle nothing")
        if stage.count_ended_run is not None:
            stage_report.add_argument("--why", help="with --ended failed, the why of the worker's failed block")
    reporting = modes.add_parser("report", parents=[shared], help="take how a lap's build ended, and print the "
                                                                  "next moves")
    reporting.add_argument("task")
    reporting.add_argument("outcome", choices=OUTCOMES)
    reporting.add_argument("--app", help="with done, the app whose targeted tests the builder named")
    reporting.add_argument("--filter", help="with done, the filter the builder named")
    reporting.add_argument("--cause", choices=pause.CAUSES, help="with cut off, the trouble that cut the worker off")
    reporting.add_argument("--why", help="with failed, the why of the worker's failed block")
    reporting.add_argument("--agent", help="the agent id the host gave the worker, which names its tokens")
    reporting.add_argument("--tier", help="the tier the worker ran on")
    reporting.add_argument("--route", choices=[NATIVE_ROUTE], help="native, when the worker ran on the tier's "
                                                                   "native route because its own route failed")
    args = parser.parse_args(argv)

    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = settings_reader.jidoka_home(args.jidoka_home)
        if args.mode == "next":
            printed = next_moves(args.epic, home, main_tree, [], True)
        elif args.mode == "carry-on":
            printed = next_moves(args.epic, home, main_tree, [], False)
        elif args.mode in pass_stages.REPORT_MODES:
            printed = report_stage(args.mode, args.epic, args.ended, getattr(args, "why", None), workers_of(args),
                                   home, main_tree)
        elif args.mode == "stop":
            printed = stop(args.epic, home, main_tree)
        else:
            said = WorkerReport(args.outcome, args.app, args.filter, args.cause, args.why)
            worker = ledger.Worker(args.agent, args.tier, args.route == NATIVE_ROUTE)
            printed = report(args.epic, args.task, said, worker, home, main_tree)
    except (SchedulerError, NotAWholeNumber, PassError, EpicReadError, BenchError, CommandError,
            settings_reader.SettingsError, holdouts.HoldoutsError, private_docs.ClashError, OSError) as error:
        print(f"scheduler: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
