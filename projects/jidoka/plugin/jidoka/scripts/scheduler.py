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
Git wins where it disagrees with the record: a lap whose branch git shows merged into the epic branch closes its
task as a merge does, and the records of worktrees whose folders are gone are dropped. For each other lap it stops
the orphan workers left in its worktree, abandons a rebase left half done, and ends the lap interrupted as `stop`
does, which counts no cutoff and no try, so that the task is ready again with a new lap on the work it left. A merge
lock whose holder is gone is cleared. It reports each on stderr. Then it makes the checks below and opens the laps.

`carry-on <epic>` is the call that goes on after a pause, an unpark, a new task or a merge: it does what `next` does
after any outcome, with no restart and no heartbeat check.

`stop <epic>` is the call a manager makes when the human tells the host to stop at once. It ends every open lap of
the epic interrupted: the task is open with no assignee, `lap.stage` is interrupted, an `Interrupted:` comment says
so, and its worktree and branch are kept. A stop is no cutoff, no try and no park, so it changes no count and leaves
the brake as it was, and the interrupted task is ready again with a new lap. Then it sends the factory-stopped
notification through notify.py, which sends nothing when the epic has no open task left, and prints the host's line
for it on stderr. It leaves the epic's heartbeat stale, so that no beat from a host still open shows a manager. It
prints `{"epic", "interrupted"}`, the ids of the tasks whose laps it ended. A notification that cannot be sent is a
line on stderr and no failure.

`report <epic> <task> <outcome> [--app <app> --filter <filter>] [--why <why>] [--cause <cause>]` takes how the
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
`lap.tries` (0), `lap.workspace` (the worktree), `lap.slot` (the lowest slot from 1 up that no open lap of the epic
holds) and `lap.branch`. A rerun after a failure, and the lap that follows a park, reuse the worktree and branch they
find. A new lap starts with no tries, no cutoffs, no send-backs and no merge tries, because each is a cap on one lap.
A lap opens for each ready task, in bd priority order and then by id, while the open laps of the epic number fewer
than the lap limit, which is the repo settings' lap_limit or the epic's own factory rule when that is lower, read
afresh on every call, and never for a task whose area an open lap already holds. A task is ready when every bead it
waits on is closed, it has no open lap, no assignee and no `human` label, and its `lap.area` metadata names its area.

The `human` label is also the human's brake. A stage already running finishes, and its report is taken as always, but
no stage starts on a task that carries the label, and none starts on any task of an epic that carries it: no lap
opens, and a lap that goes back to a worker, or that `next` finds left with no worker, is not in the actions. It
stays open, with its tries, in `laps`. Taking the label off lets the next `next` or `report` start them, a restart
counting no cutoff. The epic's other brake, three parked laps in a row at one stage with no merge between, is
caps.py's.

When `next` or `report` finds the epic with every task closed, a bead that has neither the human label nor a
gate.state in its metadata, the pass begins. Each stage of a pass prints its own action, runs no validation, and
repeats the action on every call until the stage is reported, so a manager that restarts starts the worker again. The
stages come in this order, each in the module that settles it, and each has a mode that takes the worker's report,
commits what it left on the epic branch, and does what `carry-on` does:
  test cleanup  cleanup.py: a `test-cleanup` action; `report-cleanup <epic>`. The printed JSON also holds `cleanup`,
                the new `head` and the `removed` tests.
  tidy          tidy.py: a `tidy` action; `report-tidy <epic>`. It also holds `tidy`, the new `head` and the
                `changed` files.
  review        review.py: one `review` action for each lane; `report-review <epic>` takes the four reports at
                once. It also holds `review`, the `head` it covered, the `fixes`, the `filed` tasks and the `low`
                findings. A review with findings to fix leaves a `fix` action, which every call repeats until
                `report-fix <epic>`; it also holds `fix`, the new `head`, the `changed` files and the `filed` tasks.
                An epic that holds open tasks after its third pass parks with a question instead of opening laps,
                and sends the epic-parked notification; taking the human label off runs the next pass.
  validation    validation.py runs once the stages above owe nothing. Green leaves the epic at the acceptance gate,
                with the human label, gate.state waiting and a gate comment. Red files a task in the epic, and this
                call opens its lap with the others. A merge of main that conflicts stops the call with the files
                named. An epic that holds holdouts is not at the gate when its suite is green: its result is
                pending, and `actions` ends with a holdouts action, which every call repeats until
                `report-holdouts <epic>` takes the validation worker's report. A worker that ended failed or cut off
                is reported with `--ended failed` (and `--why`) or `--ended cut-off`: each counts a run, and the
                third parks the epic with the why and sends the epic-parked notification.
A report that is missing or unusable, or a worktree that changed a file outside the files its stage may touch,
refuses the call and writes nothing. A stage that files tasks in the epic has this call open their laps.

Each call prints one JSON object:
  epic       the epic's id.
  branch     the epic branch.
  lap_limit  the lap limit this call applied: the repo settings' lap limit,
             or the epic's factory rule when that is lower.
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
             running waits with watch.py instead of ending.
  actions    the lap a report sent back to a worker or on to the next one,
             then the laps this call opened, then the pass stage's actions
             (test-cleanup, tidy, fix or the review lanes), then the
             holdouts run when the epic waits on one, each lap with action ("research",
             "build", "app-check", "spec-check" or "merge"), task, title,
             area, lap (its number), slot, branch, worktree, scratch, track
             ("simple" or "full"), answer, findings (null unless a Spec
             check sent the diff back) and app_check (null unless the app
             check did), for a merge its reason, and for an app check the
             path of its report.
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
import itertools
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import app_check
import caps
import clock
import gate
import git_exclude
import heartbeat
import holdouts
import lap_record
import lap_stages
import merge_gate
import notify
import park
import pass_ledger
import pass_stages
import pause
import private_docs
import repo_settings
import resume
import rules
import spec_check
import validation
from bench import FACTORY_LABEL, BenchError, Workspace, hide_worktrees, make_worktree
from caps import metadata_of
from commands import (COMMAND_TIMEOUT_SECONDS, SCRATCH_FOLDER, CommandError, env_as_factory, head_of, run,
                      set_metadata)
from epic_reader import (BLOCKING, BRANCH_KEY, CLOSED, ONBOARD, Epic, EpicReadError, Rerun, epic_of,
                         problems_while_held, recorded_branch)
from lap_record import APP_CHECK, BLOCKED_OUTCOME, BRIEF_PREFIX, BUILD, CANNOT_JUDGE, CUT_OFF, DONE, FAILED, \
    FULL_TRACK, INTERRUPTED, MERGE, PASS, QUESTION, RESEARCH, SEND_BACK, SPEC_CHECK, WORKER_STAGES, GateContext, Lap, \
    SchedulerError, open_lap, track_of, words
from park import HUMAN_LABEL
from pass_support import PassError

SCRIPT = "scheduler"
HOLDOUTS_ENDINGS = ("failed", "cut-off")
INTERRUPTED_PREFIX = "Interrupted: "
OUTCOMES = [DONE, FAILED, CUT_OFF, QUESTION, SEND_BACK, BLOCKED_OUTCOME, PASS, CANNOT_JUDGE]
FIRST_SLOT = 1
SECONDS_PER_MINUTE = 60
HANDOFF = "/jidoka:handoff"
RERUN = Rerun(on_the_holding_epic="Run the scheduler on the epic that holds it",
              after_onboarding="run the scheduler again")


def waits_on_open_bead(task: dict) -> bool:
    return any(isinstance(link, dict) and link.get("dependency_type") == BLOCKING and link.get("status") != CLOSED
               for link in task.get("dependencies") or [])


def is_ready(task: dict) -> bool:
    return (open_lap(task) is None and not task.get("assignee") and HUMAN_LABEL not in (task.get("labels") or [])
            and bool(lap_record.area_of(metadata_of(task))) and not waits_on_open_bead(task))


def lacks_only_an_area(task: dict) -> bool:
    """A task no lap will open for because its `lap.area` is missing, such as one added after handoff."""
    return (open_lap(task) is None and not task.get("assignee") and HUMAN_LABEL not in (task.get("labels") or [])
            and not lap_record.area_of(metadata_of(task)))


def by_priority(task: dict) -> tuple[int, str]:
    priority = task.get("priority")
    return (priority if isinstance(priority, int) else sys.maxsize, str(task["id"]))


def scheduler_problems(epic: Epic, settings: dict, main_tree: Path) -> list[str]:
    problems = problems_while_held(epic, settings, RERUN)
    if settings and not rules.repo_lap_limit(settings):
        problems.append(f"the repo settings hold no lap limit. Run {ONBOARD} again to record one")
    try:
        rules.of_epic(epic.shown)
    except rules.RulesError as error:
        problems.append(f"{error}. Write them again with rules.py")
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


def is_parked(epic: Epic) -> bool:
    """The human's brake: the epic carries the human label, so no stage starts and no lap opens."""
    return HUMAN_LABEL in (epic.shown.get("labels") or [])


def is_finished(epic: Epic) -> bool:
    """Every task of the epic is closed, and the epic waits on neither the human nor the acceptance gate."""
    return (bool(epic.children) and not epic.tasks and not is_parked(epic)
            and gate.GATE_STATE_KEY not in metadata_of(epic.shown)
            and not validation.awaits_holdouts(epic.shown))


def has_work_to_wait_for(epic: Epic) -> bool:
    """The epic has an open task and is not at the acceptance gate, so a manager with nothing running waits for a
    change instead of ending."""
    return bool(epic.tasks) and gate.GATE_STATE_KEY not in metadata_of(epic.shown)


def first_stage(task: str, track: str, main_tree: Path) -> str:
    """The stage a new lap starts at: the research brief on the full track while the task has none, else the build."""
    if track == FULL_TRACK and not any(str(comment.get("text") or "").startswith(BRIEF_PREFIX)
                                       for comment in park.posted_comments(task, main_tree)):
        return RESEARCH
    return BUILD


def planned_laps(ready: list[dict], held: list[Lap], limit: int, now: int, main_tree: Path) -> list[Lap]:
    """The laps that fit beside the open ones: within the limit, one per area, each on the lowest free slot."""
    areas = {lap.area for lap in held}
    slots = {lap.slot for lap in held}
    planned: list[Lap] = []
    for task in sorted(ready, key=by_priority):
        if len(held) + len(planned) >= limit:
            break
        area = lap_record.area_of(metadata_of(task))
        if area in areas:
            continue
        slot = next(number for number in itertools.count(FIRST_SLOT) if number not in slots)
        stage = first_stage(str(task["id"]), track_of(metadata_of(task)), main_tree)
        planned.append(lap_record.new_lap(task, slot, stage, now, main_tree))
        areas.add(area)
        slots.add(slot)
    return planned


def open_workspace(lap: Lap, epic_head: str, home: Path, main_tree: Path) -> None:
    make_worktree(Workspace(lap.branch, lap.worktree, epic_head), main_tree)
    private_docs.share(main_tree, lap.worktree.resolve(), home)
    lap.scratch.mkdir(exist_ok=True)


def record(lap: Lap, main_tree: Path) -> None:
    run(["bd", "update", lap.task, *lap_record.opening(lap)], main_tree, env_as_factory())


def restart_clock(lap: Lap, now: int, main_tree: Path) -> None:
    """A stage that reruns starts its wall clock again."""
    run(["bd", "update", lap.task, *lap_record.restarting_clock(now)], main_tree, env_as_factory())


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
            park.allow_answered(denial, answer, epic, home, main_tree)
        except (park.QuestionError, rules.RulesError, repo_settings.SettingsError) as error:
            print(f"scheduler: the answer on {lap.task} allowed no call: {error}", file=sys.stderr)
    return answer.fields()


def action_of(lap: Lap, answer: dict | None) -> dict:
    """The action that starts the lap's worker: a build, a merge worker with the reason it was called, or an app check
    with the path of the report it writes."""
    extra = {}
    if lap.stage == MERGE:
        extra = {"reason": lap.merge_why}
    elif lap.stage == APP_CHECK:
        extra = {"report": str(lap.scratch / app_check.APP_CHECK_REPORT)}
    return {"action": lap.stage, **lap.fields(), **extra, "answer": answer,
            "findings": spec_check.from_stored(lap.findings) or None,
            "app_check": spec_check.from_stored(lap.app_findings) or None}


def refuse_second_manager(epic: str, home: Path) -> None:
    """Refuses a manager on an epic whose heartbeat is fresh, because a manager already runs it."""
    seconds = heartbeat.beat_age_seconds(home, epic, clock.now())
    if seconds is not None and seconds <= heartbeat.FRESH_SECONDS:
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
    if HUMAN_LABEL in (epic.shown.get("labels") or []):
        return set()
    epic_branch = recorded_branch(epic)
    interrupted: set[str] = set()
    labeled = {str(task["id"]) for task in epic.open_task_beads if HUMAN_LABEL in (task.get("labels") or [])}
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
    validated: validation.Validated | None
    holdouts_run: validation.HoldoutsToRun | None
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

    @property
    def stops_new_laps(self) -> bool:
        return self.epic_parked or self.waiting is not None


def settle_epic(epic: Epic, settings: dict, home: Path, main_tree: Path) -> PassState:
    """Settles the epic's own state: the pass stage it owes, else its validation, the pass cap, and the holdouts it
    waits on. The epic is read again after each step that writes on it."""
    validated = None
    holdouts_run = None
    pass_actions: list[dict] = []
    if is_finished(epic):
        pass_actions = pass_stages.pass_stage_actions(epic, settings, home, main_tree)
        if not pass_actions:
            validated = validation.validate(epic.id, recorded_branch(epic), settings, home, main_tree)
            holdouts_run = validated.waiting
            epic = checked_epic(epic.id, settings, main_tree)
    if pass_ledger.parks_at_the_cap(epic.shown, bool(epic.tasks)):
        pass_ledger.park_at_the_cap(epic.id, epic.shown, main_tree)
        epic = checked_epic(epic.id, settings, main_tree)
        notify.announce(notify.EPIC_PARKED, epic.id, home, main_tree, SCRIPT)
    if holdouts_run is None and not is_parked(epic) and validation.awaits_holdouts(epic.shown):
        holdouts_run = validation.holdouts_to_run(epic.id, epic.shown, home, main_tree)
    return PassState(epic, validated, holdouts_run, pass_actions)


def running_laps(held: list[Lap]) -> list[Lap]:
    """The open laps at a worker stage, by slot: with no worker of this manager running, an earlier session left
    each of them."""
    return [lap for lap in sorted(held, key=lambda lap: lap.slot) if lap.stage in WORKER_STAGES]


def apply_holds(epic: Epic, held: list[Lap], rebuilds: list[Lap], now: int, home: Path, main_tree: Path) -> Holds:
    """Decides what holds the epic's laps. The human label, on the epic or on a task, keeps a lap from starting
    again, a pause that waits ends the laps that would start again interrupted, and the laps that go on start their
    wall clock again. The brake holds only the laps that have not opened."""
    labeled = {str(task["id"]) for task in epic.open_task_beads if HUMAN_LABEL in (task.get("labels") or [])}
    epic_parked = is_parked(epic)
    stopped = [lap for lap in rebuilds if epic_parked or lap.task in labeled]
    starting = [lap for lap in rebuilds if lap not in stopped]
    if epic_parked:
        print(f"scheduler: {epic.id} carries the {HUMAN_LABEL} label, so no stage starts and no lap opens until it "
              "is taken off. The stages already running finish", file=sys.stderr)
    for lap in stopped:
        print(f"scheduler: {lap.task} waits at the {lap.stage} for the {HUMAN_LABEL} label to come off, so no stage "
              "starts on it", file=sys.stderr)
    held_pause = pause.held_by(epic.shown)
    waiting = held_pause if held_pause is not None and held_pause.is_waiting(now) else None
    if waiting is not None:
        print(f"scheduler: {epic.id} is paused on {pause.WORDS[waiting.cause]} for {waiting.until - now} more "
              "seconds, so no stage starts and no lap opens until then", file=sys.stderr)
        for lap in starting:
            interrupt_lap(lap, f"the factory paused on {pause.WORDS[waiting.cause]} before the {lap.stage} could "
                               "start again", "the factory goes on after the pause", main_tree)
        held = [lap for lap in held if lap not in starting]
        starting = []
        notify.announce(notify.FACTORY_PAUSED, epic.id, home, main_tree, SCRIPT)
    for lap in starting:
        restart_clock(lap, now, main_tree)
    brake = caps.brake_after_new_beads(epic.shown, [str(child["id"]) for child in epic.children], main_tree)
    if brake.is_on:
        print(f"scheduler: {brake.laps} laps in a row parked at the {brake.stage} with no merge between, so no new "
              f"lap opens until a fix task is filed in {epic.id}. The laps already open run on", file=sys.stderr)
    return Holds(starting, held, waiting, brake, epic_parked)


def unplaced_tasks(tasks: list[dict]) -> list[str]:
    """The ids of the tasks no lap opens for because they have no area, each named on stderr with the command that
    sets it."""
    unplaced = [str(task["id"]) for task in sorted(tasks, key=by_priority) if lacks_only_an_area(task)]
    for task_id in unplaced:
        setting = " ".join(set_metadata((lap_record.AREA_KEY, "<area>")))
        print(f"scheduler: {task_id} has no area, so no lap opens for it. Run bd update {task_id} {setting}",
              file=sys.stderr)
    return unplaced


def open_laps(epic: Epic, holds: Holds, resumed: set[str], limit: int, now: int, home: Path,
              main_tree: Path) -> list[Lap]:
    """Opens a lap for each ready task that fits beside the open laps, unless the epic is parked or paused; the
    brake lets through only the tasks whose laps this call ended."""
    openable = [task for task in epic.open_task_beads
                if is_ready(task) and (not holds.brake.is_on or str(task["id"]) in resumed)]
    planned = [] if holds.stops_new_laps else planned_laps(openable, holds.held, limit, now, main_tree)
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
    return planned


def next_moves(bead: str, home: Path, main_tree: Path, rebuilds: list[Lap], restarting: bool) -> dict:
    """Prints the laps that go back to a worker or start, after the rebuilds of laps a report sent back.

    The call claims the epic's heartbeat for the session it runs in, as heartbeat.claim says.

    When restarting, no worker of this manager is running, so every open lap at a worker stage was left by an
    earlier session. The call refuses when the epic's heartbeat is fresh, resumes the factory as resume_laps
    describes, and opens a new lap for each task whose lap it ended.
    """
    settings = repo_settings.load(repo_settings.settings_path(home, main_tree))
    epic = checked_epic(bead, settings, main_tree)
    resumed: set[str] = set()
    if restarting:
        refuse_second_manager(epic.id, home)
        resumed = resume_laps(epic, home, main_tree)
        epic = checked_epic(bead, settings, main_tree)
    state = settle_epic(epic, settings, home, main_tree)
    epic = state.epic
    tasks = epic.open_task_beads
    open_now = [lap for lap in map(open_lap, tasks) if lap is not None]
    now = clock.now()
    holds = apply_holds(epic, open_now, running_laps(open_now) if restarting else rebuilds, now, home, main_tree)
    limit = rules.of_epic(epic.shown).lap_limit_under(rules.repo_lap_limit(settings))
    unplaced = unplaced_tasks(tasks)
    planned = open_laps(epic, holds, resumed, limit, now, home, main_tree)
    heartbeat.claim(home, epic.id, clock.now())
    metadata = {str(task["id"]): metadata_of(task) for task in tasks}
    return {"epic": epic.id, "branch": recorded_branch(epic), "lap_limit": limit,
            "validation": state.validated.fields() if state.validated is not None else None, "no_area": unplaced,
            "brake": holds.brake.fields() if holds.brake.is_on else None,
            "paused": holds.waiting.fields(now) if holds.waiting is not None else None,
            "watch": has_work_to_wait_for(epic),
            "actions": [action_of(lap, answer_fields(lap, metadata[lap.task], epic.id, home, main_tree))
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


def refuse_arguments(outcome: str, app: str | None, test_filter: str | None, cause: str | None, why: str | None,
                     stage: str) -> None:
    if outcome == DONE and stage == SPEC_CHECK:
        raise SchedulerError(f"the {words(SPEC_CHECK)} ends {PASS}, {SEND_BACK} or {CANNOT_JUDGE}, never {DONE}, "
                             "and nothing was written")
    if outcome in (PASS, CANNOT_JUDGE) and stage != SPEC_CHECK:
        raise SchedulerError(f"{outcome} is an outcome of the {words(SPEC_CHECK)}, and the lap is at the {stage}, "
                             "so nothing was written")
    names_tests = outcome == DONE and stage in (BUILD, MERGE)
    if names_tests and not (app and test_filter):
        raise SchedulerError(f"{DONE} needs --app and --filter, the app and the filter the builder named, and "
                             "nothing was written")
    if not names_tests and (app is not None or test_filter is not None):
        raise SchedulerError(f"--app and --filter go only with {DONE} at the {BUILD} or the {MERGE}, and nothing was "
                             "written")
    if cause is not None and outcome != CUT_OFF:
        raise SchedulerError(f"--cause goes only with {CUT_OFF}, and nothing was written")
    if why is not None and outcome != FAILED:
        raise SchedulerError(f"--why goes only with {FAILED}, and nothing was written")


def pause_on_trouble(lap: Lap, epic: Epic, cause: str, main_tree: Path) -> list[Lap]:
    """Pauses the epic on the trouble the worker met, as pause.after_trouble says, and ends the lap interrupted.

    The cutoff counts toward no cap, because the trouble is not the lap's own, and the lap's task gets a new lap
    when the pause ends.
    """
    held = pause.held_by(epic.shown)
    paused = pause.after_trouble(held, cause, clock.now())
    if paused != held:
        pause.write(epic.id, paused, main_tree)
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


def report(bead: str, task_id: str, outcome: str, app: str | None, test_filter: str | None, cause: str | None,
           why: str | None, home: Path, main_tree: Path) -> dict:
    settings = repo_settings.load(repo_settings.settings_path(home, main_tree))
    epic = checked_epic(bead, settings, main_tree)
    lap = working_lap(epic, task_id)
    refuse_arguments(outcome, app, test_filter, cause, why, lap.stage)
    if cause is not None:
        pause_on_trouble(lap, epic, cause, main_tree)
        return next_moves(bead, home, main_tree, [], False)
    end_pause_after_a_retry_that_worked(epic, main_tree)
    if lap_record.is_past_wall_clock(lap.stage, lap.started, clock.now()) and outcome != CUT_OFF:
        print(f"scheduler: the {lap.stage} of {task_id} ran past its wall clock of "
              f"{lap_record.wall_clock_seconds(lap.stage) // SECONDS_PER_MINUTE} minutes, so it ends cut off whatever "
              f"the worker reported", file=sys.stderr)
        outcome = CUT_OFF
        cutoff_why = (f"the {lap.stage} ran past its wall clock of "
                      f"{lap_record.wall_clock_seconds(lap.stage) // SECONDS_PER_MINUTE} minutes")
    else:
        cutoff_why = f"the {lap.stage} worker ended for a reason outside its work"
    context = GateContext(epic.id, recorded_branch(epic), settings, home, main_tree)
    if outcome == CUT_OFF:
        rebuilds = lap_stages.cut_off(lap, epic.id, cutoff_why, main_tree)
    elif outcome == FAILED:
        failed_why = why or f"the {lap.stage} worker reported that the {lap.stage} failed"
        rebuilds = lap_stages.count_try(lap, epic.id, failed_why, main_tree)
    elif outcome == QUESTION:
        rebuilds = lap_stages.ask(lap, epic.id, main_tree)
    elif outcome == SEND_BACK and lap.stage == SPEC_CHECK:
        rebuilds = lap_stages.spec_check_sent_back(lap, epic.id, main_tree)
    elif outcome == SEND_BACK:
        rebuilds = lap_stages.send_back(lap, epic.id, [], [], main_tree)
    elif outcome == BLOCKED_OUTCOME:
        rebuilds = lap_stages.block(lap, epic.id, main_tree)
    elif outcome == PASS:
        rebuilds = lap_stages.spec_check_passed(lap, context)
    elif outcome == CANNOT_JUDGE:
        rebuilds = lap_stages.spec_check_cannot_judge(lap, epic.id, main_tree)
    elif lap.stage == RESEARCH:
        rebuilds = lap_stages.research_done(lap, epic.id, main_tree)
    elif lap.stage == APP_CHECK:
        rebuilds = lap_stages.app_check_done(lap, epic.id, main_tree)
    elif lap.stage == MERGE:
        rebuilds = lap_stages.reconciled(lap_stages.name_tests(lap, str(app), str(test_filter), main_tree), context)
    else:
        rebuilds = lap_stages.build_done(lap_stages.name_tests(lap, str(app), str(test_filter), main_tree), context)
    return next_moves(bead, home, main_tree, rebuilds, False)


def report_holdouts(bead: str, ended: str | None, why: str | None, home: Path, main_tree: Path) -> dict:
    """Takes the validation worker's report on the epic's holdouts, then does what `carry-on` does.

    A worker that ended failed or cut off (`ended`) counts a run instead, and the cap parks the epic and notifies.

    A red holdout files a task in the epic, and this call opens its lap with the others.
    """
    settings = repo_settings.load(repo_settings.settings_path(home, main_tree))
    epic = checked_epic(bead, settings, main_tree)
    if ended is not None:
        reason = why or f"the validation worker ended {ended} with no reason"
        if validation.count_failed_run(epic.id, ended, reason, main_tree):
            notify.announce(notify.EPIC_PARKED, epic.id, home, main_tree, SCRIPT)
        return next_moves(bead, home, main_tree, [], False)
    settled = validation.settle_holdouts(epic.id, recorded_branch(epic), settings, home, main_tree)
    printed = next_moves(bead, home, main_tree, [], False)
    printed["validation"] = settled.fields()
    return printed


def report_stage(mode: str, bead: str, home: Path, main_tree: Path) -> dict:
    """Takes the report of a pass stage's worker, settles the stage on the epic branch, then does what `carry-on`
    does."""
    stage = pass_stages.REPORT_MODES[mode]
    settings = repo_settings.load(repo_settings.settings_path(home, main_tree))
    epic = checked_epic(bead, settings, main_tree)
    settled = stage.settle(epic.id, recorded_branch(epic), settings, home, main_tree)
    printed = next_moves(bead, home, main_tree, [], False)
    printed[stage.key] = settled.fields()
    return printed


def interrupt_lap(lap: Lap, because: str, afterwards: str, main_tree: Path) -> None:
    """Ends the lap interrupted: the task is open and unassigned, with its worktree and branch kept.

    The lap's tries, cutoffs and send-backs stay as they were, and the epic's brake is not touched. The comment
    says why the lap ended and when its task gets a new lap.
    """
    env = env_as_factory()
    run(["bd", "comment", lap.task, f"{INTERRUPTED_PREFIX}{because}. The worktree {lap.worktree} and the branch "
                                    f"{lap.branch} keep the work. The task gets a new lap when {afterwards}."],
        main_tree, env)
    run(["bd", "update", lap.task, *lap_record.resting(INTERRUPTED)], main_tree, env)


def interrupt_for_stop(lap: Lap, main_tree: Path) -> None:
    interrupt_lap(lap, f"the factory stopped during the {lap.stage}", "the factory starts again", main_tree)


def stop(bead: str, home: Path, main_tree: Path) -> dict:
    """Ends every open lap of the epic interrupted, then announces the stop."""
    epic = epic_of(bead, main_tree, RERUN)
    held = [lap for lap in map(open_lap, epic.open_task_beads) if lap is not None]
    for lap in held:
        interrupt_for_stop(lap, main_tree)
    heartbeat.mark_stopped(home, epic.id, clock.now())
    notify.announce(notify.FACTORY_STOPPED, epic.id, home, main_tree, SCRIPT)
    return {"epic": epic.id, "interrupted": [lap.task for lap in sorted(held, key=lambda lap: lap.slot)]}


def main(argv: list[str]) -> int:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("epic")
    shared.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    parser = argparse.ArgumentParser(prog="scheduler.py", description="Print the manager's next moves on a "
                                                                       "handed-off epic.")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("next", parents=[shared], help="restart the laps left at the build, open the laps that fit "
                                                    "and print the next moves")
    modes.add_parser("stop", parents=[shared], help="end every open lap interrupted, because the human stopped the "
                                                    "host, and send the stopped notification")
    modes.add_parser("carry-on", parents=[shared], help="print the next moves when the pause is over, a task was "
                                                        "unparked or added, or a lap merged, with no restart")
    holdouts_report = modes.add_parser("report-holdouts", parents=[shared], help="take the validation worker's "
                                       "report on the epic's holdouts, and print the next moves")
    holdouts_report.add_argument("--ended", choices=HOLDOUTS_ENDINGS, help="a worker that failed or was cut off: "
                                                                          "count the run instead of a report")
    holdouts_report.add_argument("--why", help="with --ended failed, the why of the worker's failed block")
    for mode, stage in pass_stages.REPORT_MODES.items():
        modes.add_parser(mode, parents=[shared], help=stage.help)
    reporting = modes.add_parser("report", parents=[shared], help="take how a lap's build ended, and print the "
                                                                  "next moves")
    reporting.add_argument("task")
    reporting.add_argument("outcome", choices=OUTCOMES)
    reporting.add_argument("--app", help="with done, the app whose targeted tests the builder named")
    reporting.add_argument("--filter", help="with done, the filter the builder named")
    reporting.add_argument("--cause", choices=pause.CAUSES, help="with cut off, the trouble that cut the worker off")
    reporting.add_argument("--why", help="with failed, the why of the worker's failed block")
    args = parser.parse_args(argv)

    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = repo_settings.jidoka_home(args.jidoka_home)
        if args.mode == "next":
            printed = next_moves(args.epic, home, main_tree, [], True)
        elif args.mode == "carry-on":
            printed = next_moves(args.epic, home, main_tree, [], False)
        elif args.mode == "report-holdouts":
            printed = report_holdouts(args.epic, args.ended, args.why, home, main_tree)
        elif args.mode in pass_stages.REPORT_MODES:
            printed = report_stage(args.mode, args.epic, home, main_tree)
        elif args.mode == "stop":
            printed = stop(args.epic, home, main_tree)
        else:
            printed = report(args.epic, args.task, args.outcome, args.app, args.filter, args.cause, args.why, home,
                             main_tree)
    except (SchedulerError, caps.NotAWholeNumber, PassError, EpicReadError, BenchError, CommandError,
            repo_settings.SettingsError, holdouts.HoldoutsError, private_docs.ClashError, OSError) as error:
        print(f"scheduler: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
