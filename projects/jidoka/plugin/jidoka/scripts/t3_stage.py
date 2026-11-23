"""A lap's stage as a T3 thread, on a host that has no lap mod and no tool of its own that starts a worker.

Every stage of a lap that has a worker starts here: research, build, app check, Spec check and merge. `start` makes the
three things a stage needs in this order. It writes the lap worktree's guard record, so that the profile guard holds
the worker's run_command calls to the lists of its kind, and its writes out of the acceptance folders, from its first
call. It launches the thread in the lap's existing worktree, on the route's model and thought level, titled `lap · `
and the task's title. And it records the thread and the stage's deadline in the lap's scratch folder.

A T3 thread has no agent type, so a stage whose worker has instructions of its own gets them at the head of the
thread's first message, from the plugin's own files: the app check's agent file, and the Spec check's skill. The
guard record's kind is `check` for the app check, whose worker holds the check list, and `lap` for every other stage,
whose list holds the stage's own grants, such as the merge worker's.
`wait` is one of the manager's waits: it waits up to STEPS_IN_ONE_WAIT T3 steps for the run, and a run found past the
deadline, before or after the wait, ends cut off, stopped with an interrupt when it still runs. `report` reads the
thread's last reply, prices the thread's provider turns in the ledger and archives the thread. A stage's thread is
archived, never deleted, because the lap's worktree outlives it (ADR 0012). The ledger rows `report` writes name the
thread as their agent, so the scheduler's report of the same worker gives them its outcome and writes none.

A pass's test cleanup, each tidy batch, each review lane that runs on the host's provider, including the design lane, and
the fix worker start the same way, in the pass's worktree, which a folder named for the stage and its epic marks
(`cleanup-<epic>`, `tidy-<epic>`, `local-tidy-<epic>`, `review-<epic>`, `fix-<epic>`). The thread is titled `lap · `,
the epic's title and the stage. The guard record has the kind `lap` and the commands `lap_lists.py` prints for a pass
worktree, which are the epic's looks and no merge grant. It bars no folder, as the lap mod bars none there: the stage
refuses a change inside an acceptance folder when it settles. The workers of a pass share its worktree and so its guard
record, which stays until every thread the worktree started was reported. Each tidy batch keeps its state in its own
scratch folder, and each review lane in a folder of its own inside the review's scratch folder, which holds the lanes'
reports; a lane that names none is refused. The second tier's Spec lane is no thread: it runs through codex_lane.py or t3_lane.py,
as the second tier's route says. The scheduler's report of a pass worker prices its thread, so a pass's `report` writes no ledger row.

The validation worker and the validation merge worker start the same way, in the validation worktree, a folder named
`validation-<epic>`, which both work in; the epic's record says which is owed (`validation.merge` for the merge worker,
else the pending holdouts for the validation worker), and a worktree whose epic owes neither is refused. Their threads
are titled `lap · `, the epic's title and `holdouts` or `validation-merge`. The validation worker's thread opens with the
validation agent's instructions, and its guard record has the kind `check` and the check list, as the app check's has.
The merge worker's guard record has the kind `lap` and the lap list the worktree prints, which holds the grants of
merging main. Neither bars a folder. The scheduler's report of either worker prices its thread, so their `report`
writes no ledger row. The acceptance specs that validation runs are run by the scheduler, in no thread.

The stage's state is the file t3-stage.json in the stage's scratch folder, the lap's own for a lap. A stop or a
restart of the factory ends every stage thread whose state a worktree holds, in its scratch folder or in a folder
directly under it, and marks it reported so that a later start is a new launch. The calls to T3 are t3_worker.py's.
"""
from __future__ import annotations

import json
import shlex
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import clock
import cleanup
import epics
import holdouts_run
import lap_guard_record
import lap_lists
import lap_outcomes
import lap_protected
import lap_record
import launcher
import ledger
import pass_ledger
import pass_support
import review
import routes
import settings_reader
import t3_worker
import tidy
import validation_merge
from commands import SCRATCH_FOLDER, CommandError, head_of, metadata_of, parent_of, read_bead
from worktrees import stage_worktree

STATE_NAME = "t3-stage.json"
PASS_STAGES = {cleanup.STAGE.prefix: cleanup.ACTION, tidy.STAGE.prefix: tidy.ACTION,
               tidy.LOCAL_STAGE.prefix: tidy.ACTION, review.REVIEW_PREFIX: review.REVIEW_ACTION,
               review.FIX_PREFIX: review.FIX_ACTION}
RUNNING = "running"
ENDED = "ended"
CUT_OFF = "cut off"
STEPS_IN_ONE_WAIT = 6
LONGEST_WAIT_SECONDS = STEPS_IN_ONE_WAIT * t3_worker.WAIT_STEP_MILLISECONDS // 1000
"""The most seconds one `wait` call lasts, which a help string says without writing the figure by hand."""
CUT_OFF_REASON = "jidoka: the stage ran past its wall clock"
STOP_REASON = "jidoka: the lap ended while the stage ran"
VALIDATION_PREFIX = validation_merge.WORKTREE_PREFIX
INSTRUCTIONS = {lap_record.APP_CHECK: Path("agents") / "app-check.md",
                holdouts_run.ACTION: Path("agents") / "validation.md",
                lap_record.SPEC_CHECK: Path("skills") / "spec-check" / "SKILL.md"}
FRONT_MATTER_FENCE = "---"


class StageError(Exception):
    """A stage that cannot start, wait or report, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Stage:
    """What the manager's calls share about one running stage: its thread, the tier it runs on, the route the thread
    launched on, the second after which it is cut off, whether it was, how many times the scratch folder's stage
    launched, and whether the thread was reported. The route is kept as launched, so that a settings change in between
    does not change the price of the thread, and a stage that reran on the tier's native route is priced from that
    route."""
    thread: str
    tier: str
    route: routes.Route
    deadline: int
    wall_seconds: int
    cut_off: bool
    launches: int
    reported: bool

    def to_record(self) -> dict:
        return {"thread": self.thread, "tier": self.tier, "route": self.route.as_dict(), "deadline": self.deadline,
                "wall_seconds": self.wall_seconds, "cut_off": self.cut_off, "launches": self.launches,
                "reported": self.reported}


def lap_scratch(worktree: Path) -> Path:
    """The scratch folder of a lap's stage, which a stage of the worktree keeps its state in unless its batch has a
    scratch folder of its own."""
    return worktree / SCRATCH_FOLDER


def state_path(scratch: Path) -> Path:
    return scratch / STATE_NAME


def write_state(scratch: Path, stage: Stage) -> None:
    path = state_path(scratch)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stage.to_record()), encoding="utf-8")


def read_state(scratch: Path) -> Stage:
    """The stage `start` recorded in the scratch folder."""
    path = state_path(scratch)
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
        tier = str(held["tier"])
        return Stage(str(held["thread"]), tier, routes.Route.parse(tier, held["route"]), int(held["deadline"]),
                     int(held["wall_seconds"]), held["cut_off"] is True, int(held.get("launches", 1)),
                     held.get("reported") is True)
    except (OSError, ValueError, KeyError, TypeError, routes.RouteError) as error:
        raise StageError(f"{path} does not hold a started stage, so no stage started in {scratch}: {error}") from error


def call_for(mode: str, worktree: Path, scratch: Path, home: Path) -> str:
    """The command line that makes the manager's next call of factory.py, which `start` and `wait` print. A stage
    whose scratch folder is not its worktree's own names it."""
    named = "" if scratch == lap_scratch(worktree) else f" --scratch {shlex.quote(str(scratch))}"
    return (f"{launcher.command_for('factory.py')} {mode} --worktree {shlex.quote(str(worktree))}{named} "
            f"--jidoka-home {shlex.quote(str(home))}")


def barred_folders(worktree: Path, home: Path, main_tree: Path) -> list[str] | None:
    """The acceptance folders the lap's worker may not write in, as the lap mod reads them from `lap_protected.py`.
    None when they cannot be read, so that the guard denies every write rather than judge it by an empty list."""
    try:
        return lap_protected.barred_folders(worktree, home, main_tree)
    except lap_protected.PRINTABLE_ERRORS:
        return None


def without_front_matter(text: str) -> str:
    """The text of a plugin file without the YAML front matter that names it for the host, which a thread has no use
    for."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_FENCE:
        return text.strip()
    for end in range(1, len(lines)):
        if lines[end].strip() == FRONT_MATTER_FENCE:
            return "\n".join(lines[end + 1:]).strip()
    return text.strip()


def first_message(stage: str, prompt: str, plugin_root: Path) -> str:
    """The thread's first message: the prompt, behind the instructions of the stage's worker when it has any."""
    instructions = INSTRUCTIONS.get(stage)
    if instructions is None:
        return prompt
    text = without_front_matter((plugin_root / instructions).read_text(encoding="utf-8"))
    return f"{text}\n\n{FRONT_MATTER_FENCE}\n\n{prompt}"


def check_record(worktree: Path, stage: str, home: Path, main_tree: Path) -> lap_guard_record.GuardRecord:
    """The record of a check worker, which holds the check list and the launcher calls of the holdouts and app scripts
    and is barred from no folder, as the lap mod treats it."""
    commands = [*lap_lists.check_list(settings_reader.read_settings(home, main_tree)), *lap_lists.check_scripts()]
    return lap_guard_record.GuardRecord(worktree=str(worktree.resolve()), kind=lap_lists.CHECK, stage=stage,
                                        commands=commands, barred=[])


CHECK_STAGES = (lap_record.APP_CHECK, holdouts_run.ACTION)
"""The stages whose worker is a check worker, which the profile guard holds to the check list."""


def guard_record(worktree: Path, stage: str, in_a_lap: bool, home: Path, main_tree: Path
                 ) -> lap_guard_record.GuardRecord:
    """What the profile guard holds the stage's worker to, the one place that picks the record's shape. A check worker
    holds the check list and bars no folder. Any other worker holds the lap list of its stage, and bars the acceptance
    folders of its task when it works in a lap, which a pass worktree has none of."""
    if stage in CHECK_STAGES:
        return check_record(worktree, stage, home, main_tree)
    return lap_guard_record.GuardRecord(
        worktree=str(worktree.resolve()), kind=lap_lists.LAP, stage=stage,
        commands=lap_lists.lap_list(worktree, home, main_tree),
        barred=barred_folders(worktree, home, main_tree) if in_a_lap else [])


def request_id(task_id: str, metadata: dict, stage: str) -> str:
    """The `clientRequestId` of a stage's launch. It holds every count that sends a lap back to a stage it has run
    (tries, send-backs, merge tries, the stage's cutoffs) and the epic head the merge worker was called at, so each
    fresh start of the stage in one lap is a new launch to T3. A start repeated with no count changed, and the retry
    of one failed launch, keep the id, so T3 answers with the thread the first call made."""
    tries = lap_record.tries_in(metadata)
    send_backs = lap_record.counted(metadata, lap_record.SEND_BACKS_KEY)
    merge_tries = lap_record.merge_tries_in(metadata)
    cutoffs = lap_record.counted(metadata, lap_record.cutoffs_key(stage))
    base = str(metadata.get(lap_record.MERGE_BASE_KEY) or "") if stage == lap_record.MERGE else ""
    return (f"jidoka-{task_id}-lap{lap_record.number_of(metadata)}-{stage}-"
            f"t{tries}-s{send_backs}-m{merge_tries}-c{cutoffs}" + (f"-b{base[:12]}" if base else ""))


@dataclass(frozen=True)
class Launch:
    """What a thread's launch names besides its route, message and workspace: the thread's title, the launch's request
    id, the number of times the scratch folder launched it, and the seconds after which the thread is cut off."""
    title: str
    request: str
    launches: int
    wall_seconds: int


@dataclass(frozen=True)
class StageLaunch:
    """A stage's launch with the stage it is and the record that holds its worker."""
    stage: str
    launch: Launch
    record: lap_guard_record.GuardRecord


@dataclass(frozen=True)
class PassStage:
    """The stage of a pass that a worktree's folder names, and the epic that holds it. The validation worktree names
    no stage, since its merge worker and its validation worker both work in it: its stage is empty, and the epic's
    record says which of the two is owed."""
    epic: str
    stage: str


def named_pass_stage(worktree: Path, main_tree: Path) -> PassStage | None:
    """The pass stage the worktree's folder names, which is empty for the validation worktree, or None when the folder
    is no pass worktree of a stage that starts as a thread."""
    for prefix, stage in PASS_STAGES.items():
        epic = lap_lists.epic_named_by(worktree, main_tree, [prefix])
        if epic:
            return PassStage(epic, stage)
    epic = lap_lists.epic_named_by(worktree, main_tree, [VALIDATION_PREFIX])
    return PassStage(epic, "") if epic else None


def pass_stage_in(worktree: Path, main_tree: Path) -> PassStage | None:
    """The pass stage that starts in the worktree, with the stage of a validation worktree's worker resolved from the
    epic's record, or None when the folder is no pass worktree of a stage that starts as a thread."""
    named = named_pass_stage(worktree, main_tree)
    if named is None or named.stage:
        return named
    return PassStage(named.epic, validation_stage_of(named.epic, read_bead(named.epic, main_tree)))


def validation_stage_of(epic: str, shown: dict) -> str:
    """The stage of the validation worktree's worker, as the epic records it: the merge worker while the epic owes a
    merge, otherwise the validation worker while its holdouts are pending."""
    if validation_merge.owes_merge(shown):
        return validation_merge.STAGE
    if epics.awaits_holdouts(shown):
        return holdouts_run.ACTION
    raise StageError(f"{epic} owes neither a merge worker nor a run of its holdouts, so no worker starts in its "
                     "validation worktree")


def previous_state(scratch: Path) -> Stage | None:
    try:
        return read_state(scratch)
    except StageError:
        return None


def launches_after(previous: Stage | None) -> int:
    """The count of this launch of a pass stage in its scratch folder: the first, a repeat of the one that was not
    reported, which T3 answers with the thread it made, or the one after a reported thread, which is a new launch."""
    if previous is None:
        return 1
    return previous.launches + 1 if previous.reported else previous.launches


def pass_launch(passing: PassStage, worktree: Path, scratch: Path, home: Path, main_tree: Path) -> StageLaunch:
    """The launch of a pass stage. Its request id holds the epic's pass, the worktree's head and the launch's count, so
    that a pass after a red validation, or a rerun after a stage that was reported, is a new launch to T3. The
    validation worker's record is a check record, and the validation merge worker's holds the grants of merging
    main."""
    shown = read_bead(passing.epic, main_tree)
    stage = passing.stage
    launches = launches_after(previous_state(scratch))
    request = (f"jidoka-{passing.epic}-pass{pass_support.count_of(shown, pass_ledger.PASSES_KEY)}-{stage}-"
               f"{scratch.name}-{(head_of('HEAD', worktree) or '')[:12]}-n{launches}")
    title = t3_worker.pass_title_of(str(shown.get("title") or ""), stage)
    return StageLaunch(stage, Launch(title, request, launches, lap_record.wall_clock_seconds(stage)),
                       guard_record(worktree, stage, False, home, main_tree))


def lap_launch(worktree: Path, home: Path, main_tree: Path) -> StageLaunch:
    task = lap_record.task_in_worktree(worktree, main_tree)
    metadata = metadata_of(task)
    stage = lap_record.stage_of(metadata)
    if not task or stage not in lap_record.WORKER_STAGES:
        raise StageError(f"the factory starts a worker for a lap at the {', '.join(lap_record.WORKER_STAGES)} stage, "
                         f"and {worktree} holds a lap at the {stage or 'no'} stage")
    title = t3_worker.title_of(str(task.get("title") or ""))
    return StageLaunch(stage, Launch(title, request_id(str(task["id"]), metadata, stage), 1,
                                     lap_record.wall_clock_seconds(stage)),
                       guard_record(worktree, stage, True, home, main_tree))


def refuse_a_stray_scratch(worktree: Path, scratch: Path) -> None:
    """Refuses a scratch folder that is not the worktree's own or one inside it, where a stage's state would outlive
    the worktree or be read as another worktree's."""
    own = lap_scratch(worktree).resolve()
    held = scratch.resolve()
    if held != own and own not in held.parents:
        raise StageError(f"{scratch} is not the scratch folder of {worktree} or a folder in it")


def refuse_a_lane_that_shares_the_scratch(passing: PassStage | None, worktree: Path, scratch: Path) -> None:
    """Refuses a review lane that keeps its state in the worktree's own scratch folder, which the review's other lanes
    would share, so that their launches would carry one request id and T3 would answer them with one thread."""
    if passing is not None and passing.stage == review.REVIEW_ACTION \
            and scratch.resolve() == lap_scratch(worktree).resolve():
        raise StageError(f"each lane of the review needs a scratch folder of its own, a folder in {scratch}, because "
                         "the lanes share the worktree")


def antigravity_route(tier: str, home: Path, host: str, starter: str) -> routes.Route:
    """The route the machine records for the tier in the host's table, which must be a T3 Antigravity thread. The starter
    names who cannot start a worker on any other route, in the refusal."""
    route = routes.recorded_route(tier, home, host)
    if not route.is_antigravity:
        raise StageError(f"the {tier} tier's route is on {route.harness}, not a T3 Antigravity thread, so {starter} "
                         "cannot start a worker on it here")
    return route


def prompt_in(prompt_file: Path) -> str:
    """The text of the prompt file, which must hold some."""
    prompt = prompt_file.read_text(encoding="utf-8")
    if not prompt.strip():
        raise StageError(f"{prompt_file} holds no prompt")
    return prompt


def launch_on_route(route: routes.Route, tier: str, scratch: Path, message: str, workspace: dict, launch: Launch
                    ) -> Stage:
    """Launches a thread on the route, which a worker of any kind starts through, and records it in the scratch folder
    with the route and its deadline. The thread has the launch's title and the message as its first prompt, binds to the
    workspace that `t3_worker.in_worktree` or `t3_worker.in_project_checkout` names, and carries the launch's request
    id. A T3 failure raises T3Error and records nothing."""
    thread = t3_worker.launch(launch.title, message, workspace, t3_worker.model_selection(route), launch.request)
    stage = Stage(thread, tier, route, clock.now() + launch.wall_seconds, launch.wall_seconds, False, launch.launches,
                  False)
    write_state(scratch, stage)
    return stage


def started(stage: Stage, wait: str, report: str) -> dict:
    """What the manager needs from a launch: the `thread`, the `deadline` in epoch seconds, the `wall_seconds`, and the
    `wait` and `report` calls."""
    return {"thread": stage.thread, "deadline": stage.deadline, "wall_seconds": stage.wall_seconds, "wait": wait,
            "report": report}


def start(worktree: Path, scratch: Path, prompt_file: Path, tier: str, route: routes.Route, home: Path,
          main_tree: Path, plugin_root: Path) -> dict:
    """Writes the guard record, launches the stage's thread on the route and returns what `started` holds. The caller
    picks the route: the tier's recorded one by `antigravity_route`, or the native one by `routes.native_route_on` for
    the rerun of a stage whose own route failed. Everything that can refuse comes before the guard record, so a refusal
    leaves none, and a launch that fails removes it unless another thread of the worktree still holds it."""
    refuse_a_stray_scratch(worktree, scratch)
    passing = pass_stage_in(worktree, main_tree)
    refuse_a_lane_that_shares_the_scratch(passing, worktree, scratch)
    staged = (pass_launch(passing, worktree, scratch, home, main_tree) if passing is not None
              else lap_launch(worktree, home, main_tree))
    message = first_message(staged.stage, prompt_in(prompt_file), plugin_root)
    lap_guard_record.write_record(home, staged.record)
    try:
        stage = launch_on_route(route, tier, scratch, message, t3_worker.in_worktree(worktree), staged.launch)
    except t3_worker.T3Error:
        remove_record_of_a_stage_nobody_runs(home, worktree, scratch)
        raise
    return started(stage, call_for("wait", worktree, scratch, home), call_for("report", worktree, scratch, home))


def wait_for_run(scratch: Path) -> tuple[Stage, str]:
    """Waits for the run of the stage recorded in `scratch` to end, and returns the stage with the state the wait ends
    in. A stage found past its deadline is stopped and recorded cut off, and says `cut off`; otherwise T3 is asked to
    wait for the run, step after step, until it ends, the deadline passes or STEPS_IN_ONE_WAIT steps went by. The
    steps share one call so that the host yields the manager's turn once for the whole wait. The deadline is read
    again after the wait, so a run that ended or still ran past it ends cut off too, as the scheduler's report of an
    overdue stage does. Otherwise the stage says `running` or `ended`."""
    stage = read_state(scratch)
    if not stage.cut_off and clock.now() > stage.deadline:
        stage = cut_off_at_deadline(scratch, stage, True)
    if stage.cut_off:
        return stage, CUT_OFF
    running = True
    for _ in range(STEPS_IN_ONE_WAIT):
        running = t3_worker.is_running_after_wait(stage.thread)
        if not running or clock.now() > stage.deadline:
            break
    if clock.now() > stage.deadline:
        return cut_off_at_deadline(scratch, stage, running), CUT_OFF
    return stage, RUNNING if running else ENDED


def wait_answer(scratch: Path, wait_call: str, report_call: str) -> dict:
    """What a manager's `wait` prints: the `state` that `wait_for_run` ends in, the `thread`, the `deadline` and the
    `next` call, which is `wait_call` while the run goes on and `report_call` once it ended or was cut off."""
    stage, state = wait_for_run(scratch)
    return {"state": state, "thread": stage.thread, "deadline": stage.deadline,
            "next": wait_call if state == RUNNING else report_call}


def wait(worktree: Path, scratch: Path, home: Path) -> dict:
    """The manager's wait for the stage's run, answered as `wait_answer` does with the calls of this worktree."""
    return wait_answer(scratch, call_for("wait", worktree, scratch, home), call_for("report", worktree, scratch, home))


def cut_off_at_deadline(scratch: Path, stage: Stage, still_running: bool) -> Stage:
    """The stage recorded cut off, with its thread interrupted when its run still goes on."""
    if still_running:
        t3_worker.interrupt(stage.thread, CUT_OFF_REASON)
    cut = replace(stage, cut_off=True)
    write_state(scratch, cut)
    return cut


def price_thread(stage: Stage, worktree: Path, home: Path, main_tree: Path) -> None:
    """Writes the ledger rows of the stage's thread, from its provider turns, on the lap the worktree holds, so that the
    scheduler's report of the same worker finds it priced. The rows end `done`, or `cut off` for a stage that was cut
    off; the scheduler's report gives them the worker's own outcome. A lap or an epic that cannot be found, and a
    ledger that cannot take the rows, are a line on stderr and no failure: the reply the worker left matters more."""
    try:
        task = lap_record.task_in_worktree(worktree, main_tree)
        lap = lap_record.open_lap(task) if task else None
        epic = parent_of(task)
    except (lap_record.NotALapWorktree, CommandError) as error:
        print(f"jidoka: the thread {stage.thread} was not priced: {error}", file=sys.stderr)
        return
    if lap is None or not epic:
        print(f"jidoka: the thread {stage.thread} was not priced, because {worktree} holds no open lap of an epic",
              file=sys.stderr)
        return
    now = clock.now()
    outcome = lap_outcomes.CUT_OFF if stage.cut_off else lap_outcomes.DONE
    ledger.record_route_run_or_say(home, main_tree, epic, ledger.Where.of_lap(lap, now),
                                   ledger.Worker(stage.thread, stage.tier, False), stage.route, outcome, now)


def state_folders(worktree: Path) -> list[Path]:
    """The scratch folders of the worktree that hold a stage's state file: its own and each folder directly under it,
    where a tidy batch or a review lane keeps its state."""
    folder = lap_scratch(worktree)
    return [path.parent for pattern in (STATE_NAME, f"*/{STATE_NAME}") for path in sorted(folder.glob(pattern))]


def another_stage_runs(worktree: Path, scratch: Path) -> bool:
    """True when a stage other than the one in `scratch` has a thread in the worktree that nobody reported, or a state
    file that cannot be read, which may name a thread that still runs."""
    for held in state_folders(worktree):
        if held.resolve() == scratch.resolve():
            continue
        state = previous_state(held)
        if state is None or not state.reported:
            return True
    return False


def remove_record_of_a_stage_nobody_runs(home: Path, worktree: Path, scratch: Path) -> None:
    """Removes the worktree's guard record unless another stage of the worktree may still run under it, as the tidy
    batches of a pass do side by side."""
    if not another_stage_runs(worktree, scratch):
        lap_guard_record.remove_record(home, worktree)


def no_step(*_: object) -> None:
    """The step of a report that a worker has none of."""


def report_thread(scratch: Path, before_archive: Callable[[Stage], None], after_reported: Callable[[], None]) -> dict:
    """Reads the last reply of the stage recorded in `scratch`, runs `before_archive` on the stage, archives the
    thread, records that it was reported and runs `after_reported`, even when the archive fails. The answer holds the
    `thread`, whether the stage was `cut_off` and the `reply`, empty when the worker left none. A read that fails
    records nothing, because the worker may still act."""
    stage = read_state(scratch)
    reply = t3_worker.last_reply(stage.thread)
    try:
        before_archive(stage)
        t3_worker.archive(stage.thread)
    finally:
        write_state(scratch, replace(stage, reported=True))
        after_reported()
    return {"thread": stage.thread, "cut_off": stage.cut_off, "reply": reply}


def report(worktree: Path, scratch: Path, home: Path, main_tree: Path) -> dict:
    """Reports the stage as `report_thread` does, pricing the thread of a lap in the ledger before the archive and
    removing the worktree's guard record when no other stage of the worktree still runs. The record goes once the read
    has answered, whether or not the archive does, since a thread that was read has ended its run. A read that fails
    leaves the record, because the worker may still act; a stop or a resume removes it. A pass's thread is priced by
    the scheduler's report of its worker, which names the thread."""
    def price(stage: Stage) -> None:
        if named_pass_stage(worktree, main_tree) is None:
            price_thread(stage, worktree, home, main_tree)

    return report_thread(scratch, price, lambda: remove_record_of_a_stage_nobody_runs(home, worktree, scratch))


def stop_stage(worktree: Path, scratch: Path) -> bool:
    """Interrupts the thread of the stage recorded in the scratch folder and archives it, and records the stage as
    reported, so that a start of the stage after it is a new launch to T3 instead of the answer with the thread that
    was stopped. True means the stage's worker cannot act any longer: it had no thread running, or the thread was
    interrupted. False means the thread may still run."""
    try:
        stage = read_state(scratch)
    except StageError as error:
        print(f"jidoka: {state_path(scratch)} names no thread ({error.__cause__}), so the guard record of {worktree} "
              "stays while its thread may still run", file=sys.stderr)
        return False
    if stage.reported:
        return True
    try:
        t3_worker.interrupt(stage.thread, STOP_REASON)
    except t3_worker.T3Error as error:
        print(f"jidoka: thread {stage.thread} of {worktree} was not interrupted, so its guard record stays: {error}",
              file=sys.stderr)
        return False
    try:
        t3_worker.archive(stage.thread)
    except t3_worker.T3Error as error:
        print(f"jidoka: thread {stage.thread} of {worktree} was interrupted and not archived: {error}",
              file=sys.stderr)
    write_state(scratch, replace(stage, reported=True))
    return True


def stop_thread(worktree: Path) -> bool:
    """Interrupts the thread of every stage `start` recorded in the worktree, in its own scratch folder or in a folder
    under it, and archives them, for a lap or a pass that ends while its workers may still run. True means no worker of
    the worktree can act in it any longer, so the caller may remove the guard record: there was no stage thread to
    stop, or every thread was interrupted. False means a thread may still run, and the record stays to hold it. A
    worktree with no state file makes no call to T3.

    A failed archive after a good interrupt is only a line on stderr, since an interrupted thread has stopped. Nothing
    here raises, so a stop never fails as a whole because T3 could not be reached."""
    stopped = [stop_stage(worktree, scratch) for scratch in state_folders(worktree)]
    return all(stopped)


def release(worktree: Path, home: Path) -> None:
    """Ends the stage threads of a lap or a pass that ends while its workers may still run, and removes the worktree's
    guard record once no worker can act in it, as `stop_thread` decides. A thread that cannot be interrupted leaves the
    record."""
    if stop_thread(worktree):
        lap_guard_record.remove_record(home, worktree)


def release_pass(epic: str, home: Path, main_tree: Path) -> None:
    """Ends the stage threads in every pass worktree of the epic, which a stop or a restart of the epic's factory
    leaves with no manager to wait for them."""
    for prefix in (*PASS_STAGES, VALIDATION_PREFIX):
        release(stage_worktree(prefix, epic, main_tree), home)
