#!/usr/bin/env python3
"""Keeps the heartbeat of a manager fresh for a host with no lap mod, such as a T3 Antigravity session.

Under Claude Code the lap mod beats once a minute. A host with no lap mod has nothing that beats while its manager
sits idle, so the epic's heartbeat would go stale and the factory would read as stopped. The scheduler starts a
detached beater for the manager's T3 thread on each call of a manager when the session is the thread, as
routes.thread_of_environment says. At most one beater runs for a thread: its pid is kept in
<jidoka-home>/beater/<thread>.json, and a call while that process runs starts nothing.

  beater.py run --thread <id> [--interval <seconds>] [--jidoka-home <folder>]
      Every --interval seconds, 60 unless $JIDOKA_BEAT_INTERVAL_SECONDS holds another, renews the heartbeat of each
      epic the factory runs whose heartbeat is fresh and names the thread (heartbeat.beat). It exits 0 as soon as a
      beat renews none: the manager stopped, another session claimed the epic, or the thread holds no fresh epic. It
      never asks whether the host still lives. After each beat it runs the watcher's checks on each epic it beat,
      and when one fires while T3's state db shows no run in progress in the thread, it sends the thread the
      carry-on prompt with `t3 thread send` (the `t3` command is $T3CODE_CLI_PATH, else `t3` on the PATH). When the
      thread's latest run failed (wake_after_failed_run), it counts the failed runs in a row as wake.py's --failures,
      waits pause.wait_seconds for that count and sends wake.py's carry-on text; a completed run resets the count. It
      reads T3's provider status first, with the token at <jidoka-home>/t3-token over the port in $JIDOKA_T3_PORT, else
      3773. A signed-out account pauses the epic on the auth cause and sends factory-paused, and wakes nobody, while
      an unreadable status or no token backs off and wakes. It also
      runs `notify.py permission-prompt` once for each runtime request of the thread that T3 shows pending, and writes
      the ledger row of each completed run of the thread from the run's provider turns (ledger.record_request, one row
      for each model). The ids it handled stay in <jidoka-home>/beater/<thread>.handled, so a beater that starts again
      repeats none of them. $JIDOKA_NOW stands in for the clock the beater waits on, so a test passes a back-off
      without waiting. A lap worker's thread has no beater, so its prompts and turns are left out. It exits 1 when the
      beats cannot run, with the reason on stderr.

Exit codes:
  0  the thread holds no fresh epic any more.
  1  it could not run, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import clock
import epics
import file_lock
import heartbeat
import home_files
import ledger
import pause
import processes
import provider_status
import rules
import settings_reader
import t3_token
import t3_turns
import t3_wake
import wake
import watch
from commands import COMMAND_TIMEOUT_SECONDS, CommandError
from epic_reader import EpicReadError

BEATER_FOLDER = "beater"
HANDLED_SUFFIX = ".handled"
BEAT_INTERVAL_SECONDS = 60
INTERVAL_VARIABLE = "JIDOKA_BEAT_INTERVAL_SECONDS"


def file_stem(thread: str) -> str:
    """The thread id as a file name, with each character that no file name may hold written as an underscore."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", thread)


def record_path(home: Path, thread: str) -> Path:
    return home / BEATER_FOLDER / f"{file_stem(thread)}.json"


def lock_path(home: Path, thread: str) -> Path:
    return home / BEATER_FOLDER / f"{file_stem(thread)}.lock"


def running_beater(home: Path, thread: str) -> int | None:
    """The pid of the process that the thread's record names while it runs, else None. A process of that pid that
    began at another moment is not the beater."""
    try:
        held = json.loads(record_path(home, thread).read_text(encoding="utf-8"))
        pid, began = int(held["pid"]), held["started"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return pid if processes.is_alive(pid) and (began is None or processes.started_at(pid) == began) else None


def write_record(home: Path, thread: str, pid: int) -> None:
    home_files.write_in_home(home / BEATER_FOLDER, record_path(home, thread).name,
                             json.dumps({"thread": thread, "pid": pid, "started": processes.started_at(pid)}))


def remove_record(home: Path, thread: str, pid: int) -> None:
    """Deletes the thread's record when it names this pid, and leaves the record of another beater of the thread."""
    try:
        held = json.loads(record_path(home, thread).read_text(encoding="utf-8"))
        if int(held["pid"]) == pid:
            record_path(home, thread).unlink(missing_ok=True)
    except (OSError, ValueError, KeyError, TypeError):
        return


def start(home: Path, thread: str, folder: Path) -> int | None:
    """Starts a detached beater for the thread from the folder, unless one runs, and returns its pid; None when one
    already runs. The process is detached from the host's session or console, so it outlives the call."""
    command = [sys.executable, str(Path(__file__).resolve()), "run", "--thread", thread, "--jidoka-home", str(home)]
    with file_lock.exclusive(lock_path(home, thread)):
        if running_beater(home, thread) is not None:
            return None
        beater = subprocess.Popen(command, cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, **processes.detached_options())
        write_record(home, thread, beater.pid)
    return beater.pid


def wake_when_idle(home: Path, main_tree: Path, thread: str, beaten: list[str],
                   baselines: dict[str, watch.Snapshot]) -> None:
    """Does what the waker does for each beaten epic, for a manager whose host T3 never releases: when a check of the
    watcher fires (unpark, new task, pause over, room freed) and T3 shows no run in progress in the thread, sends the
    thread the carry-on prompt once. The epic's baseline then moves to what fired, so the event sends no second prompt.

    An event that fires while a run is in progress stays pending, and the prompt goes at the first beat that finds the
    thread idle; the manager's own turn may not have seen it. A state db that cannot be read, or a send that fails,
    leaves the event pending too. A change that is no reason to wake, a merge, moves the baseline and sends nothing.

    The first read of an epic is its baseline as it stands, ready tasks that fit included: the scheduler call that
    started the beater opens its laps after it, so a task that fits at the first read is about to get a lap and is no
    room that freed.

    A bead labeled human after the baseline joins the baseline's parked set at the next beat and sends nothing, so that
    taking the label off sends one prompt. The watcher keeps no such bead in what it waits on; the beater does, because
    it lives across many turns and the factory state tells the human that every labeled bead wakes it."""
    for epic in beaten:
        now = clock.now()
        after = watch.snapshot_of(epic, main_tree, home, now)
        before = baselines.setdefault(epic, after)
        before = replace(before, parked=before.parked | after.parked)
        baselines[epic] = before
        change = watch.change_between(before, after, now)
        if change is None:
            continue
        if change.event not in t3_wake.WAKE_EVENTS:
            baselines[epic] = after
            continue
        try:
            if t3_turns.has_run_in_progress(thread):
                continue
            t3_wake.send(thread, t3_wake.carry_on_prompt(epic, change.event, home))
        except (t3_turns.NoRunState, CommandError):
            continue
        baselines[epic] = after


@dataclass(frozen=True)
class Handled:
    """The ids of the runtime requests the beater announced, of the completed runs it wrote rows for and of the failed
    runs it dealt with, each failed run with the second it was dealt with. They are kept in the thread's file so that a
    beater that starts again repeats none of them."""
    requests: frozenset[str]
    runs: frozenset[str]
    failures: dict[str, int]


def handled_path(home: Path, thread: str) -> Path:
    return home / BEATER_FOLDER / f"{file_stem(thread)}{HANDLED_SUFFIX}"


def read_handled(home: Path, thread: str) -> Handled:
    """What the thread's file holds, or nothing handled when the file is missing or unreadable."""
    try:
        held = json.loads(handled_path(home, thread).read_text(encoding="utf-8"))
        failures = {str(run): int(second) for run, second in held.get("failures", {}).items()}
        return Handled(frozenset(str(each) for each in held["requests"]), frozenset(str(each) for each in held["runs"]),
                       failures)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return Handled(frozenset(), frozenset(), {})


@dataclass(frozen=True)
class ThreadDuties:
    """What the beater has dealt with for one thread, and the one writer of the thread's handled file. A mark records
    that a request, a run or a failed run was dealt with, so a beater that starts again repeats none. `due` holds the
    second each pending wake after a failed run is due. It lives as long as the beater, so that a failed run is seen
    once."""
    home: Path
    thread: str
    due: dict[str, int]

    def handled(self) -> Handled:
        return read_handled(self.home, self.thread)

    def write(self, handled: Handled) -> None:
        home_files.write_in_home(self.home / BEATER_FOLDER, handled_path(self.home, self.thread).name,
                                 json.dumps({"requests": sorted(handled.requests), "runs": sorted(handled.runs),
                                             "failures": handled.failures}))

    def mark_request(self, request: str) -> None:
        handled = self.handled()
        self.write(replace(handled, requests=handled.requests | {request}))

    def mark_run(self, run: str) -> None:
        handled = self.handled()
        self.write(replace(handled, runs=handled.runs | {run}))

    def mark_failure(self, run: str, now: int) -> None:
        """Records the failed run as dealt with at this second and drops its wake."""
        handled = self.handled()
        self.write(replace(handled, failures={**handled.failures, run: now}))
        self.due.pop(run, None)


def send_notice(home: Path, main_tree: Path, thread: str) -> bool:
    """Runs `notify.py permission-prompt` for the thread's epic, and says whether it exited 0. The script names the
    epic by the thread, which the epic's heartbeat records as its session."""
    command = [sys.executable, str(Path(__file__).resolve().with_name("notify.py")), "permission-prompt", "--session",
               thread, "--jidoka-home", str(home)]
    try:
        done = subprocess.run(command, cwd=main_tree, capture_output=True, text=True, encoding="utf-8",
                              timeout=COMMAND_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"beater: the approval notice for thread {thread} was not sent: {error}", file=sys.stderr)
        return False
    if done.returncode != 0:
        print(f"beater: the approval notice for thread {thread} was not sent: {done.stderr.strip()}", file=sys.stderr)
    return done.returncode == 0


def announce_requests(duties: ThreadDuties, main_tree: Path) -> None:
    """Sends the approval notice once for each runtime request of the thread that waits for an answer. A request id is
    handled when its notice went out, and a notice that failed is tried again at the next beat. A state db that cannot
    be read sends nothing."""
    try:
        pending = t3_turns.pending_requests(duties.thread)
    except t3_turns.NoRunState:
        return
    for request in pending:
        if request not in duties.handled().requests and send_notice(duties.home, main_tree, duties.thread):
            duties.mark_request(request)


def write_manager_rows(duties: ThreadDuties, main_tree: Path, epic: str) -> None:
    """Writes the ledger rows of each completed run of the thread that has none yet, on the epic: the run's provider
    turns, one row for each model, priced as a lap worker's are. A run whose turns T3 does not give yet is left, and
    tried again at the next beat. A state db that cannot be read writes nothing."""
    try:
        runs = t3_turns.completed_runs(duties.thread)
    except t3_turns.NoRunState:
        return
    for run in runs:
        if run.run in duties.handled().runs:
            continue
        try:
            for turns in t3_turns.read_run_turns(duties.thread, run.run):
                ledger.record_request(duties.home, main_tree, epic, turns.model, turns.tokens, run.wall_seconds)
        except t3_turns.NoTurns:
            continue
        except (ledger.LedgerError, OSError) as error:
            print(f"beater: took no row for run {run.run} of thread {duties.thread}: {error}", file=sys.stderr)
            continue
        duties.mark_run(run.run)


def account_is_signed_out(home: Path) -> bool:
    """True when T3 says the Antigravity account is signed out. No token, and a status that cannot be read, are not
    that answer: no error text decides anything, and the caller backs off."""
    token = t3_token.read_token(home)
    if token is None:
        return False
    try:
        status = provider_status.read_antigravity_status(token, provider_status.port_of_environment(),
                                                         provider_status.DEFAULT_TIMEOUT_SECONDS)
    except provider_status.NoStatus:
        return False
    return not status.signed_in


def failed_runs_in_a_row(thread: str) -> list[str]:
    """The ids of the runs at the end of the thread's history that failed, with no other run between them, the oldest
    first. A run that completed, one that was interrupted and one still running ends the row."""
    row: list[str] = []
    for each in t3_turns.thread_runs(thread):
        row = [*row, each.run] if each.failed else []
    return row


def wake_after_failed_run(duties: ThreadDuties, main_tree: Path, epic: str, now: int) -> None:
    """Deals with the thread's latest run when it failed, once for each failed run, as the lap mod does for a host's
    turn that ended on an API error. The failed runs in a row are wake.py's failures. T3's provider status is read
    when the run is first seen: an account that is signed out pauses the epic on the auth cause and sends
    factory-paused, which wakes nobody, because only the human clears it; any other answer, and no answer, sets the
    wake due after pause.wait_seconds, and at the first beat at or after that second, if the run is still the thread's
    latest, the thread is sent wake.py's carry-on text. A run that is no longer the latest, because another began,
    drops its wake. A send that fails is tried again at the next beat. A state db that cannot be read does nothing.

    The duties hold the second each pending wake is due, and the runs dealt with."""
    home, due = duties.home, duties.due
    try:
        failed = failed_runs_in_a_row(duties.thread)
    except t3_turns.NoRunState:
        return
    if not failed or failed[-1] in duties.handled().failures:
        due.clear()
        return
    latest = failed[-1]
    if latest not in due:
        due.clear()
        if account_is_signed_out(home):
            try:
                wake.pause_and_notify(epic, pause.AUTH, home, main_tree)
            except (epics.EpicsError, EpicReadError, CommandError, OSError) as error:
                print(f"beater: the epic {epic} was not paused: {error}", file=sys.stderr)
                return
            duties.mark_failure(latest, now)
            return
        due[latest] = now + pause.wait_seconds(len(failed) - 1)
    if now < due[latest]:
        return
    try:
        t3_wake.send(duties.thread, wake.wake_text(epic, home))
    except CommandError:
        return
    duties.mark_failure(latest, now)


def run(home: Path, main_tree: Path, thread: str, interval_seconds: int) -> None:
    """Beats the thread's epics every interval until a beat renews none, wakes the manager when it sits idle, and does
    the lap mod's other work for the manager: the wake after a failed turn, the approval notices and the rows of the
    manager's own runs. It waits on a Clock, so a test's stand-in clock moves through a back-off without waiting."""
    baselines: dict[str, watch.Snapshot] = {}
    duties = ThreadDuties(home, thread, {})
    ticking = clock.from_environment()
    while beaten := heartbeat.beat(home, main_tree, thread):
        wake_when_idle(home, main_tree, thread, beaten, baselines)
        wake_after_failed_run(duties, main_tree, beaten[0], ticking.now())
        announce_requests(duties, main_tree)
        write_manager_rows(duties, main_tree, beaten[0])
        ticking.sleep(interval_seconds)


def interval_of_environment() -> int:
    held = os.environ.get(INTERVAL_VARIABLE, "").strip()
    return int(held) if held.isdigit() and int(held) >= 1 else BEAT_INTERVAL_SECONDS


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="beater.py", description="Keep a manager's heartbeat fresh.")
    modes = parser.add_subparsers(dest="mode", required=True)
    running = modes.add_parser("run", help="beat the epics whose fresh heartbeat names the thread")
    running.add_argument("--thread", required=True, help="the T3 thread id")
    running.add_argument("--interval", type=int, help="seconds between two beats")
    running.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    thread = args.thread.strip()
    interval = args.interval if args.interval is not None else interval_of_environment()
    if not thread:
        parser.error("--thread needs a thread id")
    if interval < 1:
        parser.error("--interval needs a whole number of seconds from 1 up")
    home = settings_reader.jidoka_home(args.jidoka_home)
    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        run(home, main_tree, thread, interval)
    except (epics.EpicsError, EpicReadError, CommandError, settings_reader.SettingsError, rules.RulesError,
                OSError) as error:
        print(f"beater: {error}", file=sys.stderr)
        return 1
    finally:
        remove_record(home, thread, os.getpid())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
