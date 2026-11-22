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
`wait_step` is one step of the manager's wait: it waits at most one T3 step for the run, and a run found past the
deadline, before or after the wait, ends cut off, stopped with an interrupt when it still runs. `report` reads the
thread's last reply, prices the thread's provider turns in the ledger and archives the thread. A stage's thread is
archived, never deleted, because the lap's worktree outlives it (ADR 0012). The ledger rows `report` writes name the
thread as their agent, so the scheduler's report of the same worker gives them its outcome and writes none.

The stage's state is the file t3-stage.json in the lap's scratch folder. The calls to T3 are t3_worker.py's.
"""
from __future__ import annotations

import json
import shlex
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import clock
import lap_guard_record
import lap_lists
import lap_outcomes
import lap_protected
import lap_record
import launcher
import ledger
import routes
import settings_reader
import t3_worker
from commands import SCRATCH_FOLDER, CommandError, metadata_of, parent_of

STATE_NAME = "t3-stage.json"
RUNNING = "running"
ENDED = "ended"
CUT_OFF = "cut off"
CUT_OFF_REASON = "jidoka: the stage ran past its wall clock"
STOP_REASON = "jidoka: the lap ended while the stage ran"
INSTRUCTIONS = {lap_record.APP_CHECK: Path("agents") / "app-check.md",
                lap_record.SPEC_CHECK: Path("skills") / "spec-check" / "SKILL.md"}
FRONT_MATTER_FENCE = "---"


class StageError(Exception):
    """A stage that cannot start, wait or report, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Stage:
    """What the manager's calls share about one running stage: its thread, the tier it runs on, the second after which
    it is cut off, and whether it was."""
    thread: str
    tier: str
    deadline: int
    wall_seconds: int
    cut_off: bool

    def to_record(self) -> dict:
        return {"thread": self.thread, "tier": self.tier, "deadline": self.deadline,
                "wall_seconds": self.wall_seconds, "cut_off": self.cut_off}


def state_path(worktree: Path) -> Path:
    return worktree / SCRATCH_FOLDER / STATE_NAME


def write_state(worktree: Path, stage: Stage) -> None:
    path = state_path(worktree)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stage.to_record()), encoding="utf-8")


def read_state(worktree: Path) -> Stage:
    """The stage `start` recorded in the worktree's scratch folder."""
    path = state_path(worktree)
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
        return Stage(str(held["thread"]), str(held["tier"]), int(held["deadline"]), int(held["wall_seconds"]),
                     held["cut_off"] is True)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise StageError(f"{path} does not hold a started stage, so no stage started in {worktree}: {error}") from error


def call_for(mode: str, worktree: Path, home: Path) -> str:
    """The command line that makes the manager's next call of factory.py, which `start` and `wait_step` print."""
    return (f"{launcher.command_for('factory.py')} {mode} --worktree {shlex.quote(str(worktree))} "
            f"--jidoka-home {shlex.quote(str(home))}")


def barred_folders(worktree: Path, home: Path, main_tree: Path) -> list[str] | None:
    """The acceptance folders the lap's worker may not write in, as the lap mod reads them from `lap_protected.py`:
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


def guard_record(worktree: Path, stage: str, home: Path, main_tree: Path) -> lap_guard_record.GuardRecord:
    """What the profile guard holds the stage's worker to. A check worker holds the check list and is barred from no
    folder, as the lap mod treats it; any other worker holds the lap list of its stage."""
    resolved = str(worktree.resolve())
    if stage == lap_record.APP_CHECK:
        commands = lap_lists.check_list(settings_reader.read_settings(home, main_tree))
        return lap_guard_record.GuardRecord(worktree=resolved, kind=lap_lists.CHECK, stage=stage, commands=commands,
                                            barred=[])
    return lap_guard_record.GuardRecord(
        worktree=resolved, kind=lap_lists.LAP, stage=stage,
        commands=lap_lists.lap_list(worktree, home, main_tree), barred=barred_folders(worktree, home, main_tree))


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


def start(worktree: Path, prompt_file: Path, tier: str, home: Path, main_tree: Path, host: str,
          plugin_root: Path) -> dict:
    """Writes the guard record, launches the stage's thread and returns what the manager needs: the `thread`, the
    `deadline` in epoch seconds, the `wall_seconds`, and the `wait` and `report` calls. Everything that can refuse
    comes before the guard record, so a refusal leaves none, and a launch that fails removes it."""
    task = lap_record.task_in_worktree(worktree, main_tree)
    metadata = metadata_of(task)
    stage = lap_record.stage_of(metadata)
    if not task or stage not in lap_record.WORKER_STAGES:
        raise StageError(f"the factory starts a worker for a lap at the {', '.join(lap_record.WORKER_STAGES)} stage, "
                         f"and {worktree} holds a lap at the {stage or 'no'} stage")
    route = routes.recorded_route(tier, home, host)
    if not route.is_antigravity:
        raise StageError(f"the {tier} tier's route is on {route.harness}, not a T3 Antigravity thread, so the "
                         "factory cannot start a worker on it here")
    prompt = prompt_file.read_text(encoding="utf-8")
    if not prompt.strip():
        raise StageError(f"{prompt_file} holds no prompt")
    message = first_message(stage, prompt, plugin_root)
    lap_guard_record.write_record(home, guard_record(worktree, stage, home, main_tree))
    request = request_id(str(task["id"]), metadata, stage)
    try:
        thread = t3_worker.launch(t3_worker.title_of(str(task.get("title") or "")), message, worktree,
                                  t3_worker.model_selection(route), request)
    except t3_worker.T3Error:
        lap_guard_record.remove_record(home, worktree)
        raise
    wall_seconds = lap_record.wall_clock_seconds(stage)
    deadline = clock.now() + wall_seconds
    write_state(worktree, Stage(thread, tier, deadline, wall_seconds, False))
    return {"thread": thread, "deadline": deadline, "wall_seconds": wall_seconds,
            "wait": call_for("wait", worktree, home), "report": call_for("report", worktree, home)}


def wait_step(worktree: Path, home: Path) -> dict:
    """One step of the manager's wait. A stage found past its deadline is stopped and recorded cut off, and says
    `cut off`; otherwise T3 is asked to wait for the run at most one step. The deadline is read again after the wait,
    so a run that ended or still ran past it ends cut off too, as the scheduler's report of an overdue stage does.
    Otherwise the stage says `running` or `ended`. The `next` of the answer is the call the manager makes after it."""
    stage = read_state(worktree)
    if not stage.cut_off and clock.now() > stage.deadline:
        stage = cut_off_at_deadline(worktree, stage, True)
    if stage.cut_off:
        state = CUT_OFF
    else:
        running = t3_worker.is_running_after_wait(stage.thread)
        if clock.now() > stage.deadline:
            stage = cut_off_at_deadline(worktree, stage, running)
            state = CUT_OFF
        else:
            state = RUNNING if running else ENDED
    return {"state": state, "thread": stage.thread, "deadline": stage.deadline,
            "next": call_for("wait" if state == RUNNING else "report", worktree, home)}


def cut_off_at_deadline(worktree: Path, stage: Stage, still_running: bool) -> Stage:
    """The stage recorded cut off, with its thread interrupted when its run still goes on."""
    if still_running:
        t3_worker.interrupt(stage.thread, CUT_OFF_REASON)
    cut = replace(stage, cut_off=True)
    write_state(worktree, cut)
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
    ledger.record_run_or_say(home, main_tree, epic, ledger.Where.of_lap(lap, now),
                             ledger.Worker(stage.thread, stage.tier, False), outcome, now)


def report(worktree: Path, home: Path, main_tree: Path) -> dict:
    """Reads the thread's last reply, prices the thread in the ledger, archives the thread and removes the worktree's
    guard record. The answer holds the `thread`, whether the stage was `cut_off` and the `reply`, empty when the worker
    left none. The record goes once the read has answered, whether or not the archive does, since a thread that was
    read has ended its run. A read that fails leaves the record, because the worker may still act; a stop or a resume
    removes it."""
    stage = read_state(worktree)
    reply = t3_worker.last_reply(stage.thread)
    try:
        price_thread(stage, worktree, home, main_tree)
        t3_worker.archive(stage.thread)
    finally:
        lap_guard_record.remove_record(home, worktree)
    return {"thread": stage.thread, "cut_off": stage.cut_off, "reply": reply}


def stop_thread(worktree: Path) -> bool:
    """Interrupts the thread of the stage `start` recorded in the worktree and archives it, for a lap that ends while
    its worker may still run. True means no worker of the stage can act in the worktree any longer, so the caller may
    remove the guard record: there was no stage thread to stop, or the thread was interrupted. False means the thread
    may still run, and the record stays to hold it. A worktree with no state file makes no call to T3.

    A failed archive after a good interrupt is only a line on stderr, since an interrupted thread has stopped. Nothing
    here raises, so a stop never fails as a whole because T3 could not be reached."""
    if not state_path(worktree).is_file():
        return True
    try:
        stage = read_state(worktree)
    except StageError as error:
        print(f"jidoka: {state_path(worktree)} names no thread ({error.__cause__}), so the guard record of {worktree} "
              "stays while its thread may still run", file=sys.stderr)
        return False
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
    return True


def release(worktree: Path, home: Path) -> None:
    """Ends the stage thread of a lap that ends while its worker may still run, and removes the worktree's guard record
    once no worker can act in it, as `stop_thread` decides. A thread that cannot be interrupted leaves the record."""
    if stop_thread(worktree):
        lap_guard_record.remove_record(home, worktree)
