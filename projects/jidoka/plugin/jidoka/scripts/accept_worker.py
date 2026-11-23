#!/usr/bin/env python3
"""Starts the accept skill's workers as T3 threads on an Antigravity host, and waits on them and reads their replies.

The accept skill has two workers, the review guide worker and the send-back worker. Antigravity's own subagent asks
for approval on run_command and write_file in the main checkout, even in Full access, and the prompt times out, so the
worker fails. A T3 thread launched in full access does not ask. Under any other host the skill starts the worker as a
subagent, and this script refuses to run.

The worker is no lap worker and works in no lap's worktree, so the thread is bound to the project's own checkout, the
folder the manager's session runs in. That is why this script writes no guard record: the profile guard finds a record
by walking up from the folder of each call, so a record for the checkout would hold the manager to the lap lists too.
The worker's limits are the ones its prompt states. It reads the repo and writes one file in the checkout's `.scratch`
folder, which is what the thread's full access allows.

  accept_worker.py start --worker <guide|send-back> --epic <epic-id> --prompt <file> --tier <tier>
      Launches the worker as a thread titled `lap · <epic title> · <worker>` on the tier's route, with the file's text
      as its prompt, and prints one JSON object: `thread`, `deadline` (epoch seconds), `wall_seconds`, and `wait` and
      `report`, the calls that follow.
  accept_worker.py wait --worker <guide|send-back>
      One wait, at most six steps of 45 seconds, which ends early when the run ends. Prints `state`, which is `running`, `ended` or `cut off`, the
      `thread`, the `deadline` and `next`, the call to make then. A worker past its deadline is interrupted, and ends
      cut off.
  accept_worker.py report --worker <guide|send-back>
      Reads the thread's last reply, archives the thread and prints `thread`, `cut_off` and `reply`.

A worker's state is the file t3-stage.json in the folder `.scratch/accept-<worker>` of the main checkout; t3_stage.py
reads and writes it. The calls to T3 are t3_worker.py's. The run is found from the folder the script runs in, so
every call of one run is made from inside the repo.

Exit codes:
  0  the mode printed its object.
  1  the mode failed, with its reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from dataclasses import replace
from pathlib import Path

import launcher
import routes
import settings_reader
import t3_stage
import t3_worker
from commands import COMMAND_TIMEOUT_SECONDS, SCRATCH_FOLDER, CommandError, read_bead

GUIDE = "guide"
SEND_BACK = "send-back"
WORKERS = {GUIDE: "review guide", SEND_BACK: "send-back"}
FOLDER_PREFIX = "accept-"
ACCEPT_WORKER_WALL_CLOCK_SECONDS = 30 * 60
"""The seconds after the start of an accept worker's thread when `wait` cuts it off, for either worker."""
ERRORS = (t3_stage.StageError, t3_worker.T3Error, CommandError, routes.RouteError, settings_reader.SettingsError,
          OSError)


def stage_folder(main_tree: Path, worker: str) -> Path:
    """The scratch folder that holds the state of the accept worker, inside the main checkout's own."""
    return main_tree / SCRATCH_FOLDER / f"{FOLDER_PREFIX}{worker}"


def call_for(mode: str, worker: str, home: Path) -> str:
    """The command line that makes the manager's next call of this script."""
    return f"{launcher.command_for('accept_worker.py')} {mode} --worker {worker} --jidoka-home {shlex.quote(str(home))}"


def request_id(epic: str, worker: str, launches: int, prompt: str) -> str:
    """The `clientRequestId` of a launch. It holds the epic, the worker, the count of launches the stage folder has made
    and a digest of the prompt, so a start repeated for one prompt, or the retry of a failed launch, keeps the id and T3
    answers with the thread the first call made, while a new prompt or a launch after a reported thread is a new one."""
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
    return f"jidoka-accept-{epic}-{worker}-n{launches}-{digest}"


def start(worker: str, epic: str, prompt_file: Path, tier: str, home: Path, main_tree: Path, host: str) -> dict:
    """Launches the worker's thread in the main checkout and records it, and returns what the manager needs."""
    route = t3_stage.antigravity_route(tier, home, host, "the accept skill")
    prompt = t3_stage.prompt_in(prompt_file)
    scratch = stage_folder(main_tree, worker)
    launches = t3_stage.launches_after(t3_stage.previous_state(scratch))
    title = t3_worker.pass_title_of(str(read_bead(epic, main_tree).get("title") or ""), WORKERS[worker])
    stage = t3_stage.launch_on_route(route, tier, scratch, title, prompt, t3_worker.in_project_checkout(),
                                     request_id(epic, worker, launches, prompt), launches,
                                     ACCEPT_WORKER_WALL_CLOCK_SECONDS)
    return t3_stage.started(stage, call_for("wait", worker, home), call_for("report", worker, home))


def wait_step(worker: str, home: Path, main_tree: Path) -> dict:
    """One step of the manager's wait, as t3_stage.waited ends it."""
    stage, state = t3_stage.waited(stage_folder(main_tree, worker))
    return {"state": state, "thread": stage.thread, "deadline": stage.deadline,
            "next": call_for("wait" if state == t3_stage.RUNNING else "report", worker, home)}


def report(worker: str, main_tree: Path) -> dict:
    """Reads the thread's last reply and archives the thread, which is marked reported even when the archive fails."""
    scratch = stage_folder(main_tree, worker)
    stage = t3_stage.read_state(scratch)
    reply = t3_worker.last_reply(stage.thread)
    try:
        t3_worker.archive(stage.thread)
    finally:
        t3_stage.write_state(scratch, replace(stage, reported=True))
    return {"thread": stage.thread, "cut_off": stage.cut_off, "reply": reply}


def run(args: argparse.Namespace) -> int:
    host = routes.host_of_environment()
    if host != routes.ANTIGRAVITY_HOST:
        print(f"accept_worker: {args.mode} starts a worker as a T3 thread, which only an Antigravity host does; this "
              "session is not one", file=sys.stderr)
        return 1
    try:
        home = settings_reader.jidoka_home(args.jidoka_home)
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        if args.mode == "start":
            printed = start(args.worker, args.epic, Path(args.prompt), args.tier, home, main_tree, host)
        elif args.mode == "wait":
            printed = wait_step(args.worker, home, main_tree)
        else:
            printed = report(args.worker, main_tree)
    except ERRORS as error:
        print(f"accept_worker: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="accept_worker.py",
                                     description="Run the accept skill's workers as T3 threads.")
    modes = parser.add_subparsers(dest="mode", required=True)
    starting = modes.add_parser("start", help="launch the worker as a T3 thread in the main checkout")
    starting.add_argument("--epic", required=True, help="the epic the worker's thread is titled for")
    starting.add_argument("--prompt", required=True, help="the file that holds the worker's prompt")
    starting.add_argument("--tier", required=True, help="the tier whose route the thread runs on")
    waiting = modes.add_parser("wait", help="wait one step for the worker's run")
    reporting = modes.add_parser("report", help="read the worker's last reply and archive its thread")
    for sub in (starting, waiting, reporting):
        sub.add_argument("--worker", required=True, choices=sorted(WORKERS), help="which accept worker")
        sub.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
