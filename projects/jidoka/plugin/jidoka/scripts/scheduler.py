#!/usr/bin/env python3
"""Reads a handed-off epic's beads and prints what the manager does next.

Run it from inside any checkout of the repo. The epic's tasks are its
children that are neither closed nor epics. A lap is open while its task is
not closed and its metadata holds a `lap.stage` other than parked or blocked.

`next <epic>` is the call a manager makes when it starts, so it resumes the
epic. It refuses, writing nothing, when the epic's heartbeat is fresh, because
a manager already runs it. Each call of a manager that succeeds claims the epic with a fresh heartbeat, as
heartbeat.py describes. Then it takes every
open lap at the build or the merge for one an earlier session left with no
worker, unless the human's brake holds it. Git wins where it disagrees with
the record: a lap whose branch git shows merged into the epic branch closes its
task as a merge does, and the records of worktrees whose folders are gone are
dropped. For each other lap it stops the orphan workers left in its worktree,
abandons a rebase left half done, and ends the lap interrupted as `stop` does,
which counts no cutoff and no try, so that the task is ready again with a new
lap on the work it left. A merge lock whose holder is gone is cleared. It
reports each on stderr. It makes the checks below, then opens a lap for each ready task,
in bd priority order and then by id, while the open laps of the epic number
fewer than the lap limit, which is the repo settings' lap_limit or the epic's
own factory rule when that is lower, read afresh on every call, and never for a task whose area an
open lap already holds. A task is ready when every bead it waits on is
closed, it has no open lap, no assignee and no `human` label, and its
`lap.area` metadata names its area.

`stop <epic>` is the call a manager makes when the human tells the host to
stop at once. It ends every open lap of the epic interrupted: the task is
open with no assignee, `lap.stage` is interrupted, an `Interrupted:`
comment says so, and its worktree and branch are kept. A stop is no
cutoff, no try and no park, so it changes no count and leaves the brake as
it was, and the interrupted task is ready again with a new lap, as after a
park. Then it sends the factory-stopped notification through notify.py,
which sends nothing when the epic has no open task left, and prints the
host's line for it on stderr. It leaves the epic's heartbeat stale, so
that no beat from a host still open shows a manager. It prints `{"epic", "interrupted"}`, the ids
of the tasks whose laps it ended. A notification that cannot be sent is a
line on stderr and no failure.

`report <epic> <task> "cut off" --cause <cause>` takes a worker that a usage limit, an outage, a billing error
or an auth failure cut off (`usage-limit`, `outage`, `billing` or `auth`) and pauses the epic, as pause.py
describes: the lap ends interrupted as `stop` ends it, no cutoff, try or park is counted, and the epic's
`pause` metadata records the cause and the second its wait ends, 5, 15 and 30 minutes after the first, second and
third failed retry, then an hour. While the pause waits, no stage starts and no lap opens, whichever call is
made, and a lap that would go back to a worker ends interrupted instead. A billing error, an auth failure and an
outage past an hour send the factory-paused notification through notify.py. A report without a cause from a
worker, once the wait is over, ends the pause. `carry-on <epic>` is the call that goes on after a pause, an
unpark, a new task or a merge: it does what `report` does after any outcome, with no restart and no heartbeat
check, and opens a lap for each ready task, which includes the tasks a pause interrupted. The JIDOKA_NOW
variable stands in for the clock, as clock.py says.

Opening a lap makes, or reuses, the worktree <main checkout>/.worktrees/lap-<task>
on the branch lap/<task>, cut from the epic branch the epic records as
`factory.branch`, and the lap's scratch folder <worktree>/.scratch. The
repo's info/exclude gets `.worktrees/` and `/.scratch/`, so neither shows in
any worktree's git status. In a repo whose settings keep the glossary and
ADRs private, each worktree gets the links private_docs.share makes to the
main checkout's copies, and a worktree that holds its own copy stops the
call, with the reason on stderr, before any task is claimed. Then, with BEADS_ACTOR set to jidoka, the task
goes to in_progress with the assignee jidoka, and its metadata gets
`lap.number` (1, or one more than the number of the lap the task left parked, blocked or interrupted), `lap.stage` (build), `lap.tries` (0), `lap.workspace` (the
worktree), `lap.slot` (the lowest slot from 1 up that no open lap of the
epic holds) and `lap.branch`. A rerun after a failure, and the lap that follows
a park, reuse the worktree and branch they find. A new lap starts with no tries,
no cutoffs, no send-backs and no merge tries, because each is a cap on one lap.

`report <epic> <task> <outcome> [--app <app> --filter <filter>] [--why <why>]`
takes how the build of the task's open lap ended, one outcome of a fixed set,
and makes the checks below first:
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
  failed     the build worker failed. `--why` carries the worker's own
             reason into the try's comment and the park's, and goes with no
             other outcome; without it they say the worker reported that the
             stage failed.
  cut off    the build worker ended for a reason outside its work; the lap
             goes back to the build, and that is not a try. A stage that
             runs past its wall clock, 60 minutes for the build and 30 for
             any other stage, from `lap.started`, ends cut off whatever the
             worker reported. The third cutoff of a stage in a lap parks the
             task. A manager that restarts, through `next`, is the human's
             stop and counts no cutoff.
  send back  a check sent the lap's diff back to the build. It is not a try;
             the second send-back of a lap, from the checks together, parks
             the task.
  question   the build needs a decision. The worker left a question report
             in the lap's scratch folder, and park.py posts it on the task
             and parks the task, with the options in its metadata. The lap
             keeps its tries, and its slot and area are free for the next
             ready task. A missing or unusable report is a try instead.
  blocked    the build cannot finish without work it discovered. The worker
             left a discovered-work report in the lap's scratch folder, and
             discovered.py files each finding, linked discovered-from to the
             task: a finding placed `blocks` or `epic` in the epic, with the
             task's area and the simple track, and one placed `outside` with
             no parent. The task waits on each `blocks` task and its lap
             ends blocked: `lap.stage` blocked, status open, no assignee, no
             human label, a `Blocked:` comment, and its worktree and branch
             kept. It holds no slot or area, and it is ready again, with a
             new lap, once every task it waits on is closed. A missing or
             unusable report, or one with no `blocks` finding, is a try
             instead. A `done` report files the findings placed `epic` and
             `outside` before it commits, and a `blocks` finding on a `done`
             is a try.
A task whose `lap.track` metadata is `full` has a lap with more stages,
in this order: the research brief (`research`, on the light tier), the build
(on the deep tier), the targeted tests, the app check (`app-check`, on the
standard tier, only when a holdout names the task), the Spec check
(`spec-check`, on the standard tier), then the merge gate. Its lap starts at
the research, unless the task already holds a `research brief:` comment, and
any other task starts at the build.
  research   `done` takes no --app and --filter. The worker left the brief in
             `research-brief.md` in the lap's scratch folder, and the
             scheduler posts it on the task as a `research brief:` comment
             and sends the lap to the build. A missing or empty brief is a
             try of the research.
  build      a `done` records the app and the filter on the task, then runs
             the targeted tests as above. A pass sends the lap, with a
             comment, to the app check when a holdout names the task, and
             else to the Spec check, instead of the merge gate.
  app-check  the worker reads the holdouts that name the task through
             `holdouts.py read <epic> --task <task>`, runs the app on the
             lap's slot and tests it from outside, before it reads the diff.
             It leaves `app-check.json` in the scratch folder, as
             app_check.py describes, and its report is `done`, with no
             --app and no --filter. Every holdout green sends the lap to the
             Spec check. A red one sends the lap back to the build with no
             try: the action of that build carries `app_check`, a list of
             {holdout, verdict, saw} for each failed holdout and never a
             step, and the task gets the same words as a comment. It counts
             with the Spec check's send-backs, so the second send-back of the
             lap, from both checks together, parks the task. A report that
             is missing or unusable is a try of the app check. A lap holds
             its slot for as long as it is open, so two app checks never run
             on one slot.
  spec-check the worker left its outcome block, as the spec-check skill
             defines it, in `spec-check.json` in the scratch folder, and the
             report names its outcome:
             pass          the lap goes to the merge gate with the targeted
                           run it holds; the tests run again only when the
                           epic branch moved since, and the lap goes back to
                           the build when they then fail.
             send back     the block's findings are posted on the task and
                           kept in its `lap.findings` metadata, and the lap
                           goes back to the build, whose action carries them
                           as `findings`, a list of {kind, file, line, bead,
                           note}, until a build is done. It is no try; the
                           second send-back of the lap parks the task. A
                           block that is missing or unusable is a try of the
                           Spec check.
             cannot judge  the task parks with the block's reason, and no
                           try is counted.
             Any `done` there is refused.
A failed build, a red targeted run, a filter the targeted tests refuse or
that runs no tests, and a lap the merge gate finds with no commit the epic
branch lacks are each a try: the lap's `lap.tries` goes up by one, a comment
says why, and the lap goes back to the build. The third try parks the task.
The second red targeted run of a simple lap's own build, counted in the
task's `lap.testfailures`, also sets `lap.track` to `full` and posts a comment
that begins `Moved to the full track` and names the evidence. The lap stays at
the build, and its next build runs the full track's later stages. No other
cause moves a task, and a full task never moves back.
Every cap that parks a task names itself in the comment: the try cap, the
send-back cap, the cutoff cap or the merge try cap. A refusal of the merge
gate parks the task too, naming its check. A parked task frees its slot and
its area, so the other laps keep running. Three parked laps in a row at one
stage with no merge between turn the epic's brake on, as caps.py describes,
and no new lap opens until the epic holds a bead it did not hold then, the
fix task.

The `human` label is also the human's brake. A stage already running
finishes, and its report is taken as always, but no stage starts on a task
that carries the label, and none starts on any task of an epic that carries
it: no lap opens, and a lap that goes back to the build or to the merge
worker, or that `next` finds left with no worker, is not in the actions. It
stays open, with its tries, in `laps`. Taking the label off lets the next
`next` or `report` start them, a restart counting no cutoff.

Newer work on the epic branch calls the merge worker instead of counting a
try: a conflict while rebasing the lap onto the epic branch, naming the
files, or targeted tests that fail on a lap the rebase brought newer work
into. The lap goes to the stage merge with a comment, its tries unchanged,
and `lap.mergewhy` and `lap.mergebase` (the epic branch's head then) in the
task's metadata. Its action is a merge, on the deep tier, with the reason.
The merge worker rebases the lap onto the epic branch in the lap's worktree,
resolves the conflicts, and fixes what the merge broke. A report on a lap at
the merge takes the same outcomes as the build, with these differences:
  done       the worker reconciled the lap. A worktree left in the middle
             of a rebase, or a lap head that lacks `lap.mergebase`, is a
             merge try. Otherwise the scheduler folds what the worker left
             into the lap's own commit and runs the targeted tests and the
             merge gate as for a build. A conflict or red tests that newer
             work causes again call the merge worker, with no try.
  failed     a merge try.
A merge try raises `lap.mergetries` by one and calls the merge worker again;
the second parks the task. A parked task gets `lap.stage` parked, status
open, no assignee, the human label and a comment saying why; its worktree
and branch stay. Its lap no
longer holds a slot or an area, and the task is not ready while it carries
the human label. A merged lap's task is closed, and its worktree and lap
branch are gone. Everything the scheduler, the targeted tests and the merge
gate write on a lap, they write with BEADS_ACTOR set to jidoka. The output
of the tests and the gate goes to stderr. Then the call does what `next`
does, and its actions start with the lap that went back to a worker.

When `next` or `report` finds the epic with every task closed, a bead
that has neither the human label nor a gate.state in its metadata, it
runs validation, validation.py, before anything else. Green leaves the epic
at the acceptance gate, with the human label, gate.state waiting and a gate
comment. Red files a task in the epic, and this call opens its lap with the
others. A merge of main that conflicts stops the call with the files named.
An epic that holds holdouts is not at the gate when its suite is green: its
result is pending, and `actions` ends with a holdouts action, as validation.py
describes, which every call repeats until the report is taken, so a manager
that restarts starts the worker again.

`report-holdouts <epic>` takes the validation worker's report, which is the
worker's job done and no outcome of a lap. Every holdout green puts the epic at
the gate. Each red holdout files one task in the epic, with what a user saw and
never the holdout's steps, and this call opens its lap with the others, so the
epic goes into another pass. A report that is missing, unusable or quotes a
scenario refuses the call and writes nothing, and the next `next` starts the
worker again. A worker that ends failed or cut off is not reported.

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
             then the laps this call opened, then the holdouts run when
             the epic waits on one, each lap with action ("research",
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
import contextlib
import dataclasses
import itertools
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import app_check
import caps
import clock
import discovered
import git_exclude
import heartbeat
import holdouts
import merge_gate
import notify
import park
import pause
import private_docs
import repo_settings
import resume
import rules
import spec_check
import targeted_tests
import validation
from bench import FACTORY_LABEL, WORKTREE_FOLDER, BenchError, Workspace, hide_worktrees, make_worktree
from commands import COMMAND_TIMEOUT_SECONDS, FACTORY_ACTOR, CommandError, capture, env_as_factory, head_of, \
    run
from handoff import BLOCKING, BRANCH_KEY, CLOSED, ONBOARD, TRACK, Epic, HandoffError, Rerun, epic_of, \
    recorded_branch, problems_while_held

HUMAN_LABEL = park.HUMAN_LABEL
RESEARCH = "research"
BUILD = "build"
APP_CHECK = "app-check"
SPEC_CHECK = "spec-check"
MERGE = "merge"
WORKER_STAGES = (RESEARCH, BUILD, APP_CHECK, SPEC_CHECK, MERGE)
STAGE_WORDS = {SPEC_CHECK: "Spec check", APP_CHECK: "app check"}
FULL_TRACK = "full"
TRACK_KEY = "lap.track"
APP_KEY = "lap.app"
FILTER_KEY = "lap.filter"
SPEC_PASSED_KEY = "lap.speccheck"
FINDINGS_KEY = "lap.findings"
APP_FINDINGS_KEY = "lap.appfindings"
TEST_FAILURES_KEY = "lap.testfailures"
TEST_FAILURES_TO_MOVE = 2
RESEARCH_BRIEF = "research-brief.md"
BRIEF_PREFIX = "research brief: "
PARKED = park.PARKED
BLOCKED = discovered.BLOCKED
INTERRUPTED = "interrupted"
INTERRUPTED_PREFIX = "Interrupted: "
RESTING_STAGES = (PARKED, BLOCKED, INTERRUPTED)
DONE = "done"
FAILED = "failed"
CUT_OFF = "cut off"
QUESTION = "question"
SEND_BACK = "send back"
BLOCKED_OUTCOME = "blocked"
PASS = spec_check.PASS
CANNOT_JUDGE = spec_check.CANNOT_JUDGE
OUTCOMES = [DONE, FAILED, CUT_OFF, QUESTION, SEND_BACK, BLOCKED_OUTCOME, PASS, CANNOT_JUDGE]
FIRST_LAP = 1
FIRST_SLOT = 1
NO_TRIES = 0
SECONDS_PER_MINUTE = 60
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


def started_of(metadata: dict) -> int | None:
    try:
        return int(str(metadata.get(caps.STARTED_KEY)))
    except ValueError:
        return None


def track_of(metadata: dict) -> str:
    return FULL_TRACK if metadata.get(TRACK_KEY) == FULL_TRACK else TRACK


def findings_text(metadata: dict, key: str) -> str:
    """The findings a check sent back, as the metadata holds them under the key, or an empty string."""
    stored = metadata.get(key)
    return json.dumps(stored) if isinstance(stored, list) else str(stored or "")


def words(stage: str) -> str:
    """The stage as a sentence names it: the Spec check is a glossary term, the others are plain."""
    return STAGE_WORDS.get(stage, stage)


def open_lap(task: dict) -> Lap | None:
    metadata = metadata_of(task)
    if not metadata.get("lap.stage") or metadata["lap.stage"] in RESTING_STAGES:
        return None
    stage = str(metadata["lap.stage"])
    return Lap(task=str(task["id"]), title=str(task.get("title") or ""), area=str(metadata.get("lap.area") or ""),
               number=whole_number(metadata.get("lap.number")), slot=whole_number(metadata.get("lap.slot")),
               branch=str(metadata.get("lap.branch") or ""), worktree=Path(str(metadata.get("lap.workspace") or "")),
               stage=stage, tries=whole_number(metadata.get("lap.tries")), started=started_of(metadata),
               cutoffs=caps.count_in(metadata, caps.cutoffs_key(stage)),
               send_backs=caps.count_in(metadata, caps.SEND_BACKS_KEY),
               merge_tries=caps.count_in(metadata, caps.MERGE_TRIES_KEY),
               merge_why=str(metadata.get(caps.MERGE_WHY_KEY) or ""),
               merge_base=str(metadata.get(caps.MERGE_BASE_KEY) or ""), track=track_of(metadata),
               app=str(metadata.get(APP_KEY) or ""), test_filter=str(metadata.get(FILTER_KEY) or ""),
               spec_passed=metadata.get(SPEC_PASSED_KEY) == PASS, findings=findings_text(metadata, FINDINGS_KEY),
               app_findings=findings_text(metadata, APP_FINDINGS_KEY),
               test_failures=caps.count_in(metadata, TEST_FAILURES_KEY))


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


def is_finished(epic: Epic) -> bool:
    """Every task of the epic is closed, and the epic waits on neither the human nor the acceptance gate."""
    return (bool(epic.children) and not epic.tasks and validation.HUMAN_LABEL not in (epic.shown.get("labels") or [])
            and validation.GATE_STATE_KEY not in metadata_of(epic.shown)
            and not validation.awaits_holdouts(epic.shown))


def has_work_to_wait_for(epic: Epic) -> bool:
    """The epic has an open task and is not at the acceptance gate, so a manager with nothing running waits for a
    change instead of ending."""
    return bool(epic.tasks) and validation.GATE_STATE_KEY not in metadata_of(epic.shown)


def next_lap_number(task: dict) -> int:
    """The number of the lap a ready task gets: the first, or one more than the lap it left parked, blocked or
    interrupted."""
    previous = metadata_of(task).get("lap.number")
    return FIRST_LAP if previous is None else whole_number(previous) + 1


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
        area = str(metadata_of(task)["lap.area"])
        if area in areas:
            continue
        slot = next(number for number in itertools.count(FIRST_SLOT) if number not in slots)
        task_id = str(task["id"])
        track = track_of(metadata_of(task))
        planned.append(Lap(task=task_id, title=str(task.get("title") or ""), area=area, number=next_lap_number(task),
                           slot=slot, branch=f"{LAP_BRANCH_PREFIX}{task_id}",
                           worktree=main_tree / WORKTREE_FOLDER / f"{LAP_FOLDER_PREFIX}{task_id}",
                           stage=first_stage(task_id, track, main_tree), tries=NO_TRIES, started=now,
                           cutoffs=caps.NONE_YET, send_backs=caps.NONE_YET, merge_tries=caps.NONE_YET,
                           merge_why="", merge_base="", track=track, app="", test_filter="", spec_passed=False,
                           findings=findings_text(metadata_of(task), FINDINGS_KEY),
                           app_findings=findings_text(metadata_of(task), APP_FINDINGS_KEY),
                           test_failures=caps.NONE_YET))
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
         "--set-metadata", f"lap.branch={lap.branch}",
         "--set-metadata", f"{caps.STARTED_KEY}={lap.started}",
         "--set-metadata", f"{caps.cutoffs_key(lap.stage)}={lap.cutoffs}",
         "--set-metadata", f"{caps.SEND_BACKS_KEY}={lap.send_backs}",
         "--set-metadata", f"{caps.MERGE_TRIES_KEY}={lap.merge_tries}",
         "--set-metadata", f"{TEST_FAILURES_KEY}={lap.test_failures}", *fresh_checks(lap)], main_tree,
        env_as_factory())


def fresh_checks(lap: Lap) -> list[str]:
    """The metadata argument that gives a full-track lap no Spec check result from an earlier lap. Findings stay,
    because the build the lap starts is the one that answers them."""
    return ["--set-metadata", f"{SPEC_PASSED_KEY}="] if lap.track == FULL_TRACK else []


def restart_clock(lap: Lap, now: int, main_tree: Path) -> None:
    """A stage that reruns starts its wall clock again."""
    run(["bd", "update", lap.task, "--set-metadata", f"{caps.STARTED_KEY}={now}"], main_tree, env_as_factory())


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
    labeled = {str(task["id"]) for task in tasks_of(epic) if HUMAN_LABEL in (task.get("labels") or [])}
    running = [lap for lap in map(open_lap, tasks_of(epic))
               if lap is not None and lap.stage in WORKER_STAGES and lap.task not in labeled]
    for lap in sorted(running, key=lambda lap: lap.slot):
        merged = resume.merged_head(lap.branch, lap.title, epic_branch, main_tree)
        if merged is not None:
            close_merged_lap(lap, merged, epic_branch, epic.id, main_tree)
            continue
        for pid in resume.stop_orphans(lap.worktree):
            print(f"scheduler: stopped process {pid}, a worker left running in {lap.worktree}", file=sys.stderr)
        if lap.worktree.is_dir():
            abandon_rebase(lap)
        print(f"scheduler: {lap.task} was left at the {lap.stage} with no worker, so its lap ends interrupted and "
              "a new lap starts on its worktree", file=sys.stderr)
        interrupt_for_stop(lap, main_tree)
        interrupted.add(lap.task)
    return interrupted


def next_moves(bead: str, home: Path, main_tree: Path, rebuilds: list[Lap], restarting: bool) -> dict:
    """Opens the laps that fit and prints them as build actions, after the rebuilds of laps sent back.

    When restarting, no worker of this manager is running, so every open lap at a worker stage was left by an
    earlier session. The call refuses when the epic's heartbeat is fresh, resumes the factory as resume_laps
    describes, and opens a new lap for each task whose lap it ended.
    """
    settings = repo_settings.load(repo_settings.settings_path(home, main_tree))
    epic = checked_epic(bead, settings, main_tree)
    if restarting:
        refuse_second_manager(epic.id, home)
    resumed: set[str] = set()
    if restarting:
        resumed = resume_laps(epic, home, main_tree)
        epic = checked_epic(bead, settings, main_tree)
    validated = None
    holdouts_run = None
    if is_finished(epic):
        validated = validation.validate(epic.id, recorded_branch(epic), settings, home, main_tree)
        holdouts_run = validated.waiting
        epic = checked_epic(bead, settings, main_tree)
    elif validation.awaits_holdouts(epic.shown):
        holdouts_run = validation.holdouts_to_run(epic.id, epic.shown, home, main_tree)
    tasks = tasks_of(epic)
    held = [lap for lap in map(open_lap, tasks) if lap is not None]
    if restarting:
        rebuilds = [lap for lap in sorted(held, key=lambda lap: lap.slot) if lap.stage in WORKER_STAGES]
    epic_parked = HUMAN_LABEL in (epic.shown.get("labels") or [])
    labeled = {str(task["id"]) for task in tasks if HUMAN_LABEL in (task.get("labels") or [])}
    stopped = [lap for lap in rebuilds if epic_parked or lap.task in labeled]
    rebuilds = [lap for lap in rebuilds if lap not in stopped]
    if epic_parked:
        print(f"scheduler: {epic.id} carries the {HUMAN_LABEL} label, so no stage starts and no lap opens until it "
              "is taken off. The stages already running finish", file=sys.stderr)
    for lap in stopped:
        print(f"scheduler: {lap.task} waits at the {lap.stage} for the {HUMAN_LABEL} label to come off, so no stage "
              "starts on it", file=sys.stderr)
    limit = rules.of_epic(epic.shown).lap_limit_under(rules.repo_lap_limit(settings))
    unplaced = [str(task["id"]) for task in sorted(tasks, key=by_priority) if lacks_only_an_area(task)]
    for task_id in unplaced:
        print(f"scheduler: {task_id} has no area, so no lap opens for it. Run bd update {task_id} "
              "--set-metadata lap.area=<area>", file=sys.stderr)
    now = clock.now()
    held_pause = pause.held_by(epic.shown)
    waiting = held_pause if held_pause is not None and held_pause.is_waiting(now) else None
    if waiting is not None:
        print(f"scheduler: {epic.id} is paused on {pause.WORDS[waiting.cause]} for {waiting.until - now} more "
              "seconds, so no stage starts and no lap opens until then", file=sys.stderr)
        for lap in rebuilds:
            interrupt_lap(lap, f"the factory paused on {pause.WORDS[waiting.cause]} before the {lap.stage} could "
                               "start again", "the factory goes on after the pause", main_tree)
        held = [lap for lap in held if lap not in rebuilds]
        rebuilds = []
        announce_pause(epic.id, home, main_tree)
    for lap in rebuilds:
        restart_clock(lap, now, main_tree)
    brake = caps.brake_after_new_beads(epic.shown, [str(child["id"]) for child in epic.children], main_tree)
    if brake.is_on:
        print(f"scheduler: {brake.laps} laps in a row parked at the {brake.stage} with no merge between, so no new "
              f"lap opens until a fix task is filed in {epic.id}. The laps already open run on", file=sys.stderr)
    openable = [task for task in tasks if is_ready(task) and (not brake.is_on or str(task["id"]) in resumed)]
    planned = [] if epic_parked or waiting is not None else planned_laps(openable, held, limit, now, main_tree)
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
    metadata = {str(task["id"]): metadata_of(task) for task in tasks}
    heartbeat.claim(home, epic.id, clock.now())
    return {"epic": epic.id, "branch": epic_branch, "lap_limit": limit,
            "validation": validated.fields() if validated is not None else None, "no_area": unplaced,
            "brake": brake.fields() if brake.is_on else None,
            "paused": waiting.fields(now) if waiting is not None else None,
            "watch": has_work_to_wait_for(epic),
            "actions": [action_of(lap, answer_fields(lap, metadata[lap.task], epic.id, home, main_tree))
                        for lap in rebuilds + planned] + ([holdouts_run.fields()] if holdouts_run is not None else []),
            "laps": [{**lap.fields(), "stage": lap.stage, "tries": lap.tries}
                     for lap in sorted(held + planned, key=lambda lap: lap.slot)]}


def working_lap(epic: Epic, task_id: str) -> Lap:
    for task in tasks_of(epic):
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


def park_lap(lap: Lap, epic: str, tries: int, why: str, main_tree: Path) -> None:
    """Ends the lap parked: the task waits on the human, open and unassigned, with its worktree and branch kept.

    The parked lap counts toward the epic's brake.
    """
    park.park(lap.task, tries, f"{park.PARKED_PREFIX}{why}. The worktree {lap.worktree} and the branch {lap.branch} "
                               f"keep the work. Take the {HUMAN_LABEL} label off to give the task a new lap.", [],
              main_tree)
    caps.note_parked_lap(epic, lap.stage, main_tree)


def ask(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Parks the task on the question the worker left; a report that cannot be posted counts a try."""
    try:
        park.park_on_question(lap.task, lap.tries, lap.scratch, lap.worktree, lap.branch, main_tree)
    except park.QuestionError as error:
        return count_try(lap, epic, f"the question could not be posted: {error}", main_tree)
    return []


def block(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Files the discovered work the lap cannot finish without and ends the lap blocked on it.

    A report that is missing, unusable or names no blocking finding counts a try of the stage instead.
    """
    try:
        findings = discovered.read_findings(lap.scratch)
        blockers = discovered.blockers_in(findings)
        if not blockers:
            raise discovered.DiscoveryError(f"the {BLOCKED_OUTCOME} outcome needs a finding in "
                                            f"{discovered.DISCOVERED_REPORT} whose placement is {discovered.BLOCKS}")
        filed = discovered.file_findings(findings, lap.task, lap.area, epic, main_tree)
    except discovered.DiscoveryError as error:
        return count_stage_try(lap, epic, f"the discovered work could not be filed: {error}", main_tree)
    discovered.block(lap.task, lap.tries, [item for item in filed if item.finding.placement == discovered.BLOCKS],
                     lap.worktree, lap.branch, main_tree)
    discovered.clear_report(lap.scratch)
    return []


def file_discovered_work(lap: Lap, epic: str, main_tree: Path) -> str | None:
    """Files the discovered work a finished stage reported; returns why it could not, or None.

    A finished stage has nothing it cannot finish without, so a finding that blocks the task is refused.
    """
    try:
        findings = discovered.read_findings(lap.scratch)
        if discovered.blockers_in(findings):
            raise discovered.DiscoveryError(f"a {DONE} stage has no finding whose placement is {discovered.BLOCKS}. "
                                            f"End {BLOCKED_OUTCOME} instead")
        discovered.file_findings(findings, lap.task, lap.area, epic, main_tree)
    except discovered.DiscoveryError as error:
        return f"the discovered work could not be filed: {error}"
    discovered.clear_report(lap.scratch)
    return None


def count_try(lap: Lap, epic: str, why: str, main_tree: Path) -> list[Lap]:
    """Counts a failed try of the lap's stage. The third parks the task; an earlier one sends the lap back to the
    stage."""
    tries = lap.tries + 1
    name = words(lap.stage)
    if tries >= caps.TRY_CAP:
        park_lap(lap, epic, tries, f"the try cap of {caps.TRY_CAP} is reached: {name} try {tries} of {caps.TRY_CAP} "
                                   f"failed: {why}", main_tree)
        return []
    env = env_as_factory()
    run(["bd", "comment", lap.task,
         f"{name[:1].upper()}{name[1:]} try {tries} of {caps.TRY_CAP} failed: {why}. The lap goes back to the "
         f"{name}."], main_tree, env)
    run(["bd", "update", lap.task, "--set-metadata", f"lap.tries={tries}", "--set-metadata",
         f"lap.stage={lap.stage}"], main_tree, env)
    return [dataclasses.replace(lap, tries=tries)]


def cut_off(lap: Lap, epic: str, why: str, main_tree: Path) -> list[Lap]:
    """Counts a cutoff of the stage. The third parks the task; an earlier one reruns the stage, and no try is counted."""
    cutoffs = lap.cutoffs + 1
    if cutoffs >= caps.CUTOFF_CAP:
        park_lap(lap, epic, lap.tries, f"the cutoff cap of {caps.CUTOFF_CAP} is reached: the {lap.stage} was cut off "
                                       f"{cutoffs} of {caps.CUTOFF_CAP} times, the last time because {why}",
                 main_tree)
        return []
    env = env_as_factory()
    run(["bd", "comment", lap.task, f"The {lap.stage} was cut off, cutoff {cutoffs} of {caps.CUTOFF_CAP}, because "
                                    f"{why}. The lap goes back to the {lap.stage} and no try is counted."],
        main_tree, env)
    run(["bd", "update", lap.task, "--set-metadata", f"{caps.cutoffs_key(lap.stage)}={cutoffs}"], main_tree, env)
    return [dataclasses.replace(lap, cutoffs=cutoffs)]


def send_back(lap: Lap, epic: str, findings: list[spec_check.Finding], failed_holdouts: list[app_check.Verdict],
              main_tree: Path) -> list[Lap]:
    """Counts a send-back from the checks. The cap's last one parks the task; an earlier one reruns the build.

    A Spec check's findings, and the holdouts the app check saw fail, go on the task as a comment and in its
    metadata, where the next build reads them. A failed holdout is kept as its number, its verdict and what a user
    saw, never its steps.
    """
    send_backs = lap.send_backs + 1
    if send_backs >= caps.SEND_BACK_CAP:
        park_lap(lap, epic, lap.tries, f"the send-back cap of {caps.SEND_BACK_CAP} is reached: the checks sent the "
                                       f"diff back {send_backs} of {caps.SEND_BACK_CAP} times"
                                       + findings_in_words(findings, failed_holdouts), main_tree)
        return []
    stage = BUILD if lap.stage in (SPEC_CHECK, APP_CHECK) else lap.stage
    spec_json = spec_check.as_json(findings) if findings else ""
    app_json = app_check.as_json(failed_holdouts) if failed_holdouts else ""
    env = env_as_factory()
    run(["bd", "comment", lap.task, f"The checks sent the diff back, send-back {send_backs} of "
                                    f"{caps.SEND_BACK_CAP}. The lap goes back to the {stage} and no try is "
                                    f"counted.{findings_in_words(findings, failed_holdouts)}"], main_tree, env)
    run(["bd", "update", lap.task, "--set-metadata", f"{caps.SEND_BACKS_KEY}={send_backs}",
         "--set-metadata", f"lap.stage={stage}", "--set-metadata", f"{SPEC_PASSED_KEY}=",
         "--set-metadata", f"{FINDINGS_KEY}={spec_json}", "--set-metadata", f"{APP_FINDINGS_KEY}={app_json}"],
        main_tree, env)
    return [dataclasses.replace(lap, stage=stage, send_backs=send_backs, spec_passed=False, findings=spec_json,
                                app_findings=app_json)]


def findings_in_words(findings: list[spec_check.Finding], failed_holdouts: list[app_check.Verdict]) -> str:
    spec = f"\nThe {words(SPEC_CHECK)}'s findings:\n{spec_check.describe(findings)}" if findings else ""
    app = f"\nThe {words(APP_CHECK)}'s findings:\n{app_check.describe(failed_holdouts)}" if failed_holdouts else ""
    return f"{spec}{app}"


def spec_check_sent_back(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Takes the Spec check's send back: its findings go to a new build. A block that is missing or unusable counts a
    try of the Spec check."""
    try:
        findings = spec_check.read_findings(lap.scratch)
    except spec_check.SpecCheckError as error:
        return count_try(lap, epic, f"the outcome block cannot be used: {error}", main_tree)
    spec_check.clear_report(lap.scratch)
    return send_back(lap, epic, findings, [], main_tree)


def spec_check_cannot_judge(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Takes the Spec check's cannot judge: the task parks with its reason, and no try is counted."""
    try:
        reason = spec_check.read_reason(lap.scratch)
    except spec_check.SpecCheckError as error:
        reason = f"it gave no usable reason ({error})"
    spec_check.clear_report(lap.scratch)
    park_lap(lap, epic, lap.tries, f"the {words(SPEC_CHECK)} cannot judge the diff: {reason}", main_tree)
    return []


def enter_stage(lap: Lap, stage: str, main_tree: Path) -> Lap:
    """Moves the lap to the stage and returns it; the stage's own cutoffs start at none for the lap's records."""
    run(["bd", "update", lap.task, "--set-metadata", f"lap.stage={stage}"], main_tree, env_as_factory())
    return dataclasses.replace(lap, stage=stage, cutoffs=caps.NONE_YET)


def research_done(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Posts the research brief the worker left in the scratch folder on the task and sends the lap to the build. A
    missing or empty brief counts a try of the research."""
    path = lap.scratch / RESEARCH_BRIEF
    try:
        brief = path.read_text(encoding="utf-8").strip()
    except OSError:
        brief = ""
    if not brief:
        return count_try(lap, epic, f"the research brief {path} is missing or empty", main_tree)
    run(["bd", "comment", lap.task, f"{BRIEF_PREFIX}{brief}"], main_tree, env_as_factory())
    path.unlink(missing_ok=True)
    return [enter_stage(lap, BUILD, main_tree)]


def start_spec_check(lap: Lap, main_tree: Path) -> list[Lap]:
    """Sends a full-track lap whose targeted tests passed to the Spec check, before the merge gate."""
    run(["bd", "comment", lap.task, f"The targeted tests passed. The lap goes to the {words(SPEC_CHECK)}, before "
                                    "the merge gate."], main_tree, env_as_factory())
    return [enter_stage(lap, SPEC_CHECK, main_tree)]


def start_checks(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Sends a full-track lap whose targeted tests passed to its first check: the app check when a holdout names its
    task, else the Spec check."""
    if not holdouts.numbered_naming(lap.task, holdouts.read(epic, main_tree)):
        return start_spec_check(lap, main_tree)
    run(["bd", "comment", lap.task, f"The targeted tests passed. The lap goes to the {words(APP_CHECK)}, then to "
                                    f"the {words(SPEC_CHECK)}, before the merge gate."], main_tree, env_as_factory())
    return [enter_stage(lap, APP_CHECK, main_tree)]


def app_check_done(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Takes the app check's report: every holdout that names the task green sends the lap on to the Spec check, and
    a red one sends the diff back to the build with the holdout's number, its verdict and what a user saw. A report
    that is missing or unusable counts a try of the app check."""
    every_holdout = holdouts.read(epic, main_tree)
    try:
        verdicts = app_check.read_verdicts(lap.scratch, lap.task, every_holdout)
    except app_check.AppCheckError as error:
        return count_try(lap, epic, f"the report cannot be used: {error}", main_tree)
    app_check.clear_report(lap.scratch)
    failed = [verdict for verdict in verdicts if not verdict.passed]
    if failed:
        return send_back(lap, epic, [], failed, main_tree)
    return start_spec_check(lap, main_tree)


def spec_check_passed(lap: Lap, epic: str, epic_branch: str, settings: dict, home: Path, main_tree: Path) -> list[Lap]:
    """Takes the Spec check's pass: the lap goes to the merge gate with the targeted run it already has.

    The tests run again only when the epic branch moved since that run. The lap returns to the build when they then
    fail, so the build's try count and its stage are what a red run counts against.
    """
    building = dataclasses.replace(lap, stage=BUILD, spec_passed=True)
    if not (lap.app and lap.test_filter):
        return count_try(building, epic, "the lap records no app and filter for its targeted tests", main_tree)
    run(["bd", "comment", lap.task, f"The {words(SPEC_CHECK)} passed: the diff does what the task says, and nothing "
                                    "more."], main_tree, env_as_factory())
    run(["bd", "update", lap.task, "--set-metadata", f"{SPEC_PASSED_KEY}={PASS}"], main_tree, env_as_factory())
    spec_check.clear_report(lap.scratch)
    return through_the_gate(building, epic, lap.app, lap.test_filter, epic_branch, settings, home, main_tree,
                            tested_already=True)


def stage_work(lap: Lap) -> bool:
    """Stages everything a worker left in the lap's worktree outside the scratch folder; True when any change is
    staged."""
    env = env_as_factory()
    run(["git", "add", "--all"], lap.worktree, env)
    run(["git", "reset", "--quiet", "--", SCRATCH_FOLDER], lap.worktree, env)
    staged = capture(["git", "diff", "--cached", "--quiet"], lap.worktree, env)
    if staged.returncode not in (NOTHING_STAGED, CHANGES_STAGED):
        raise CommandError(f"git diff --cached failed in {lap.worktree}: {staged.stderr.strip()}")
    return staged.returncode == CHANGES_STAGED


def commit_build(lap: Lap) -> None:
    """Commits what the build left in the lap's worktree, outside the scratch folder, under the task's title."""
    if stage_work(lap):
        run(["git", "commit", "--quiet", "--message", lap.title], lap.worktree, env_as_factory())


def commit_reconciliation(lap: Lap, epic_branch: str) -> None:
    """Folds what the merge worker left into the lap's own commit, so the epic branch keeps one commit per task.

    A lap with no commit of its own gets a commit under the task's title instead.
    """
    own = run(["git", "rev-list", f"refs/heads/{epic_branch}..HEAD"], lap.worktree, None).split()
    if not own:
        commit_build(lap)
    elif stage_work(lap):
        run(["git", "commit", "--quiet", "--amend", "--no-edit"], lap.worktree, env_as_factory())


def rebase_unfinished(lap: Lap) -> bool:
    """True when the lap's worktree is off the lap branch, as it is in the middle of a rebase."""
    return merge_gate.checked_out_branch(lap.worktree) != lap.branch


def abandon_rebase(lap: Lap) -> None:
    """Puts a worktree whose rebase a worker left unfinished back on the lap branch as it was."""
    if rebase_unfinished(lap):
        capture(["git", "rebase", "--abort"], lap.worktree, env_as_factory())


def count_merge_try(lap: Lap, epic: str, why: str, main_tree: Path) -> list[Lap]:
    """Counts a failed try of the merge worker. The second parks the task; the first calls the worker again."""
    abandon_rebase(lap)
    tries = lap.merge_tries + 1
    if tries >= caps.MERGE_TRY_CAP:
        park_lap(lap, epic, lap.tries, f"the merge try cap of {caps.MERGE_TRY_CAP} is reached: merge try {tries} of "
                                       f"{caps.MERGE_TRY_CAP} failed: {why}", main_tree)
        return []
    env = env_as_factory()
    run(["bd", "comment", lap.task, f"Merge try {tries} of {caps.MERGE_TRY_CAP} failed: {why}. The lap goes back to "
                                    f"the {MERGE} worker."], main_tree, env)
    run(["bd", "update", lap.task, "--set-metadata", f"{caps.MERGE_TRIES_KEY}={tries}"], main_tree, env)
    return [dataclasses.replace(lap, merge_tries=tries)]


def call_merge_worker(lap: Lap, epic_branch: str, why: str, main_tree: Path) -> list[Lap]:
    """Sends the lap to the merge worker, which reconciles it with newer work on the epic branch. No try is counted.

    The lap records the epic branch's head as of the call, which a reconciled lap must hold.
    """
    base = head_of(f"refs/heads/{epic_branch}", main_tree) or ""
    env = env_as_factory()
    run(["bd", "comment", lap.task, f"Merge worker called: {why}. The lap goes to the {MERGE} stage and no try is "
                                    "counted."], main_tree, env)
    run(["bd", "update", lap.task, "--set-metadata", f"lap.stage={MERGE}",
         "--set-metadata", f"{caps.MERGE_WHY_KEY}={why}", "--set-metadata", f"{caps.MERGE_BASE_KEY}={base}"],
        main_tree, env)
    cutoffs = lap.cutoffs if lap.stage == MERGE else caps.NONE_YET
    return [dataclasses.replace(lap, stage=MERGE, cutoffs=cutoffs, merge_why=why, merge_base=base)]


def brings_newer_work(lap: Lap, epic_branch: str, main_tree: Path) -> bool:
    """True when the epic branch holds a commit the lap's head lacks, so the targeted tests rebase it in."""
    epic_head = head_of(f"refs/heads/{epic_branch}", main_tree)
    lap_head = head_of(f"refs/heads/{lap.branch}", main_tree)
    return epic_head is not None and lap_head is not None and not merge_gate.contains(epic_head, lap_head, main_tree)


def reconciled(lap: Lap, epic: str, app: str, test_filter: str, epic_branch: str, settings: dict, home: Path,
               main_tree: Path) -> list[Lap]:
    """Takes the merge worker's done: its work joins the lap's commit and the lap goes through the gate again."""
    if rebase_unfinished(lap):
        return count_merge_try(lap, epic, "the merge worker left the rebase unfinished", main_tree)
    lap_head = head_of(f"refs/heads/{lap.branch}", main_tree)
    if lap.merge_base and (lap_head is None or not merge_gate.contains(lap.merge_base, lap_head, main_tree)):
        return count_merge_try(lap, epic, f"the lap does not hold {epic_branch} at {lap.merge_base}, so the merge "
                                          "worker reconciled nothing", main_tree)
    commit_reconciliation(lap, epic_branch)
    return through_the_gate(lap, epic, app, test_filter, epic_branch, settings, home, main_tree, tested_already=False)


def count_stage_try(lap: Lap, epic: str, why: str, main_tree: Path) -> list[Lap]:
    """Counts a failed try of the stage the lap is at: a build try, or a try of the merge worker."""
    if lap.stage == MERGE:
        return count_merge_try(lap, epic, why, main_tree)
    return count_try(lap, epic, why, main_tree)


def count_red_tests(lap: Lap, epic: str, why: str, main_tree: Path) -> list[Lap]:
    """Counts a red targeted run of the lap's own build as a try. The second one in a simple lap moves the task to
    the full track, with a comment that names the evidence; a task on the full track never moves back, and nothing
    else moves a task."""
    if lap.stage != BUILD or lap.track == FULL_TRACK:
        return count_stage_try(lap, epic, why, main_tree)
    failures = lap.test_failures + 1
    env = env_as_factory()
    run(["bd", "update", lap.task, "--set-metadata", f"{TEST_FAILURES_KEY}={failures}"], main_tree, env)
    lap = dataclasses.replace(lap, test_failures=failures)
    if failures >= TEST_FAILURES_TO_MOVE:
        run(["bd", "comment", lap.task, f"Moved to the full track: the targeted tests failed twice in this simple "
                                        f"lap, the last time because {why}."], main_tree, env)
        run(["bd", "update", lap.task, "--set-metadata", f"{TRACK_KEY}={FULL_TRACK}"], main_tree, env)
        lap = dataclasses.replace(lap, track=FULL_TRACK)
    return count_try(lap, epic, why, main_tree)


def through_the_gate(lap: Lap, epic: str, app: str, test_filter: str, epic_branch: str, settings: dict, home: Path,
                     main_tree: Path, tested_already: bool) -> list[Lap]:
    """Runs the targeted tests and, when they pass, the merge gate; returns the lap when it goes back to a worker.

    A full-track lap whose tests pass goes to the Spec check first, unless it has passed it. A lap that has passed
    it, with tested_already, goes to the gate with the targeted run it holds, and runs the tests again only when the
    epic branch moved since.

    A conflict rebasing onto newer work on the epic branch, or tests that fail once that work is in, call the
    merge worker and count no try.
    """
    run_tests = not tested_already
    while True:
        newer_work = brings_newer_work(lap, epic_branch, main_tree)
        if run_tests:
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    tested = targeted_tests.targeted_tests(lap.task, lap.worktree, epic_branch,
                                                           targeted_tests.Integration.REBASE, app, test_filter, home,
                                                           env_as_factory())
            except targeted_tests.MergeConflict as conflict:
                return call_merge_worker(lap, epic_branch, f"rebasing the lap onto {epic_branch} conflicts in "
                                                           f"{', '.join(conflict.files)}", main_tree)
            except targeted_tests.FilterRefused as refused:
                return count_stage_try(lap, epic, f"the filter needs fixing: {refused}", main_tree)
            except targeted_tests.TestRunError as error:
                raise SchedulerError(f"the targeted tests of {lap.task} did not run: {error}") from error
            if not tested.passed:
                why = f"the targeted tests failed with exit code {tested.exit_code}"
                if newer_work:
                    return call_merge_worker(lap, epic_branch,
                                             f"{why} once newer work on {epic_branch} was merged in", main_tree)
                return count_red_tests(lap, epic, why, main_tree)
            if lap.track == FULL_TRACK and not lap.spec_passed:
                return start_checks(lap, epic, main_tree)
        try:
            with contextlib.redirect_stdout(sys.stderr):
                merged = merge_gate.merge(merge_gate.LapToMerge(lap.task, lap.branch, lap.worktree, epic_branch),
                                          settings, home, main_tree)
        except merge_gate.EpicBranchMoved as moved:
            print(f"scheduler: {moved}, so the targeted tests run again", file=sys.stderr)
            run_tests = True
            continue
        except merge_gate.EmptyLap as empty:
            return count_stage_try(lap, epic, str(empty), main_tree)
        except merge_gate.GateRefused as refused:
            park_lap(lap, epic, lap.tries, f"the merge gate refused the lap: {refused}", main_tree)
            return []
        if merged.failed_steps:
            raise SchedulerError(f"{epic_branch} has the lap's commit {merged.sha}, but these steps failed:\n"
                                 + "\n".join(f"  {step}" for step in merged.failed_steps))
        caps.note_merge(epic, main_tree)
        return []


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
    if caps.is_past_wall_clock(lap.stage, lap.started, clock.now()) and outcome != CUT_OFF:
        print(f"scheduler: the {lap.stage} of {task_id} ran past its wall clock of "
              f"{caps.wall_clock_seconds(lap.stage) // SECONDS_PER_MINUTE} minutes, so it ends cut off whatever "
              f"the worker reported", file=sys.stderr)
        outcome = CUT_OFF
        cutoff_why = (f"the {lap.stage} ran past its wall clock of "
                      f"{caps.wall_clock_seconds(lap.stage) // SECONDS_PER_MINUTE} minutes")
    else:
        cutoff_why = f"the {lap.stage} worker ended for a reason outside its work"
    if outcome == CUT_OFF:
        rebuilds = cut_off(lap, epic.id, cutoff_why, main_tree)
    elif outcome == FAILED:
        failed_why = why or f"the {lap.stage} worker reported that the {lap.stage} failed"
        rebuilds = count_stage_try(lap, epic.id, failed_why, main_tree)
    elif outcome == QUESTION:
        rebuilds = ask(lap, epic.id, main_tree)
    elif outcome == SEND_BACK and lap.stage == SPEC_CHECK:
        rebuilds = spec_check_sent_back(lap, epic.id, main_tree)
    elif outcome == SEND_BACK:
        rebuilds = send_back(lap, epic.id, [], [], main_tree)
    elif outcome == BLOCKED_OUTCOME:
        rebuilds = block(lap, epic.id, main_tree)
    elif outcome == PASS:
        rebuilds = spec_check_passed(lap, epic.id, recorded_branch(epic), settings, home, main_tree)
    elif outcome == CANNOT_JUDGE:
        rebuilds = spec_check_cannot_judge(lap, epic.id, main_tree)
    elif lap.stage == RESEARCH:
        rebuilds = research_done(lap, epic.id, main_tree)
    elif lap.stage == APP_CHECK:
        rebuilds = app_check_done(lap, epic.id, main_tree)
    elif lap.stage == MERGE:
        rebuilds = reconciled(lap, epic.id, str(app), str(test_filter), recorded_branch(epic), settings, home,
                              main_tree)
    else:
        rebuilds = build_done(lap, epic.id, str(app), str(test_filter), recorded_branch(epic), settings, home,
                              main_tree)
    return next_moves(bead, home, main_tree, rebuilds, False)


def report_holdouts(bead: str, home: Path, main_tree: Path) -> dict:
    """Takes the validation worker's report on the epic's holdouts, then does what `carry-on` does.

    A red holdout files a task in the epic, and this call opens its lap with the others.
    """
    settings = repo_settings.load(repo_settings.settings_path(home, main_tree))
    epic = checked_epic(bead, settings, main_tree)
    settled = validation.settle_holdouts(epic.id, recorded_branch(epic), settings, home, main_tree)
    printed = next_moves(bead, home, main_tree, [], False)
    printed["validation"] = settled.fields()
    return printed


def build_done(lap: Lap, epic: str, app: str, test_filter: str, epic_branch: str, settings: dict, home: Path,
               main_tree: Path) -> list[Lap]:
    """Takes a finished build: files its discovered work, commits what it left, and sends the lap through the
    targeted tests. A full-track lap records the app and the filter for the merge gate it reaches after the Spec check,
    and starts with no Spec check result, because the build changed the diff."""
    unfiled = file_discovered_work(lap, epic, main_tree)
    if unfiled is not None:
        return count_try(lap, epic, unfiled, main_tree)
    commit_build(lap)
    if lap.track == FULL_TRACK:
        run(["bd", "update", lap.task, "--set-metadata", f"{APP_KEY}={app}",
             "--set-metadata", f"{FILTER_KEY}={test_filter}", "--set-metadata", f"{SPEC_PASSED_KEY}=",
             "--set-metadata", f"{FINDINGS_KEY}=", "--set-metadata", f"{APP_FINDINGS_KEY}="], main_tree,
            env_as_factory())
        lap = dataclasses.replace(lap, app=app, test_filter=test_filter, spec_passed=False, findings="",
                                  app_findings="")
    return through_the_gate(lap, epic, app, test_filter, epic_branch, settings, home, main_tree, tested_already=False)


def interrupt_lap(lap: Lap, because: str, afterwards: str, main_tree: Path) -> None:
    """Ends the lap interrupted: the task is open and unassigned, with its worktree and branch kept.

    The lap's tries, cutoffs and send-backs stay as they were, and the epic's brake is not touched. The comment
    says why the lap ended and when its task gets a new lap.
    """
    env = env_as_factory()
    run(["bd", "comment", lap.task, f"{INTERRUPTED_PREFIX}{because}. The worktree {lap.worktree} and the branch "
                                    f"{lap.branch} keep the work. The task gets a new lap when {afterwards}."],
        main_tree, env)
    run(["bd", "update", lap.task, "--status=open", "--assignee=", "--set-metadata", f"lap.stage={INTERRUPTED}"],
        main_tree, env)


def interrupt_for_stop(lap: Lap, main_tree: Path) -> None:
    interrupt_lap(lap, f"the factory stopped during the {lap.stage}", "the factory starts again", main_tree)


def announce(event: str, epic: str, home: Path, main_tree: Path) -> None:
    """Sends the notification and puts the line the host shows on stderr.

    Missing a notification loses nothing, so one that cannot be sent never fails the call.
    """
    try:
        print(notify.notify(event, epic, home, main_tree), file=sys.stderr)
    except notify.NothingToSend as reason:
        print(f"scheduler: no {event} notification: {reason}", file=sys.stderr)
    except (notify.NotifyError, HandoffError, CommandError, OSError) as error:
        print(f"scheduler: the {event} notification was not sent: {error}", file=sys.stderr)


def announce_stop(epic: str, home: Path, main_tree: Path) -> None:
    announce(notify.FACTORY_STOPPED, epic, home, main_tree)


def announce_pause(epic: str, home: Path, main_tree: Path) -> None:
    """Notifies the human of a pause that waits on them, as notify.py judges."""
    announce(notify.FACTORY_PAUSED, epic, home, main_tree)


def stop(bead: str, home: Path, main_tree: Path) -> dict:
    """Ends every open lap of the epic interrupted, then announces the stop."""
    epic = epic_of(bead, main_tree, RERUN)
    held = [lap for lap in map(open_lap, tasks_of(epic)) if lap is not None]
    for lap in held:
        interrupt_for_stop(lap, main_tree)
    heartbeat.mark_stopped(home, epic.id, clock.now())
    announce_stop(epic.id, home, main_tree)
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
    modes.add_parser("report-holdouts", parents=[shared], help="take the validation worker's report on the epic's "
                                                               "holdouts, and print the next moves")
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
            printed = report_holdouts(args.epic, home, main_tree)
        elif args.mode == "stop":
            printed = stop(args.epic, home, main_tree)
        else:
            printed = report(args.epic, args.task, args.outcome, args.app, args.filter, args.cause, args.why, home,
                             main_tree)
    except (SchedulerError, validation.ValidationError, HandoffError, BenchError, CommandError,
            repo_settings.SettingsError, holdouts.HoldoutsError, private_docs.ClashError, OSError) as error:
        print(f"scheduler: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
