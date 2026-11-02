#!/usr/bin/env python3
"""Runs the Spec lane of a pass's review as a T3 child task, for a second tier that routes to t3.

The manager starts the child with T3's own tools, so this script runs on either side of the child's run.

  t3_lane.py start <epic> --worktree <review worktree> --report <review-spec.json> --base <sha> --head <sha>
      --file <path> ... [--doc <path> ...] [--wall-seconds <n>]
      Records the route, the time and a fingerprint of the main checkout, next to the report. It prints one JSON
      object: `delegate_task`, the arguments of T3's `delegate_task` call, which the manager passes as they are (the
      child's task sends it to read the review worktree by absolute paths and to write nothing); `reply`, the path
      where the manager saves the child's last reply, verbatim, before `finish`; and `wall_seconds` and `deadline`,
      the stage's wall clock and the time in epoch seconds after which the manager cancels the child. It refuses
      when the second tier's route is not on t3 or lacks a provider, a model or an effort.
  t3_lane.py finish --report <review-spec.json>
      Reads the epic, the route and the reply path from what `start` recorded, so a change of the settings in between
      does not change the route the row names. It writes the lane's report from the reply: a JSON list of findings,
      read as the review's settle reads a native lane's report. It writes the one ledger row of the run on the epic,
      stage `review`, harness t3, the route's model and effort, the wall time from `start` and the outcome, with no
      tokens, because a T3 task result carries none.

T3 starts the child in the main checkout or in a checkout of its own, and the lane only reads, so `finish` fails the
run when the main checkout differs from what `start` saw. Any failure exits 1 and leaves no report: a run past the
stage's wall clock, a missing or empty reply, a reply that holds no usable list of findings, a main checkout that
changed, a `start` that never ran, and a route the settings cannot give. The script retries nothing. The failed run is
a failed route, which the manager passes to `route.py fallback`.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  `start` printed the task, or `finish` wrote the report and recorded the row.
  1  the run failed, with the reason on stderr, and no report is left; or it could not start.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import clock
import lap_record
import review
import routes
import rules
import settings_reader
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, read_bead, run
from lane_report import REVIEW_STAGE, Lane, LaneError, prompt_of, record, write_report
from lap_outcomes import DONE, FAILED
from prices import Tokens

T3 = routes.T3_HARNESS
CHILD = "the T3 child"
STATE_NAME = "t3-spec-start.json"
REPLY_NAME = "t3-spec-reply.txt"
READ_ONLY = "You only read. Change no file, create no file, and run no command that writes."
ROUTE_FIELDS = ("provider", "model", "effort")


def state_path(report: Path) -> Path:
    return report.with_name(STATE_NAME)


def reply_path(report: Path) -> Path:
    return report.with_name(REPLY_NAME)


def fingerprint(main_tree: Path) -> str:
    """What the main checkout holds: the commit it is on, every path git reports as changed or untracked, and the size
    and modification time of each, so that a file edited again after it was already changed shows."""
    head = run(["git", "rev-parse", "HEAD"], main_tree, None).strip()
    status = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], main_tree, None)
    digest = hashlib.sha256(f"{head}\0{status}".encode("utf-8", errors="replace"))
    for entry in status.split("\0"):
        if len(entry) < 4:
            continue
        path = main_tree / entry[3:]
        try:
            stat = path.stat()
            digest.update(f"{entry[3:]}\0{stat.st_size}\0{stat.st_mtime_ns}\0".encode("utf-8", errors="replace"))
        except OSError:
            digest.update(f"{entry[3:]}\0gone\0".encode("utf-8", errors="replace"))
    return digest.hexdigest()


def t3_route(home: Path) -> dict:
    route = routes.recorded_route(routes.SECOND_TIER, home)
    if route.get("harness") != T3:
        raise LaneError(f"the {routes.SECOND_TIER} tier's route is on {route.get('harness')}, not on {T3}")
    missing = [field for field in ROUTE_FIELDS if not rules.is_text(route.get(field))]
    if missing:
        raise LaneError(f"the {routes.SECOND_TIER} tier's {T3} route lacks a {' and a '.join(missing)}")
    return route


def delegate_task_of(prompt: str, route: dict) -> dict:
    """The arguments of T3's `delegate_task` call for the child: a review in the shared checkout, run in the
    background, with no runtime mode so that the child keeps its default."""
    return {"task": prompt, "role": "review", "isolation": "shared", "mode": "async",
            "target": {"providerInstanceId": route["provider"], "model": route["model"],
                       "options": {"effort": route["effort"]}}}


def start(lane: Lane, wall_seconds: int, home: Path, main_tree: Path) -> dict:
    route = t3_route(home)
    plugin = Path(__file__).resolve().parent.parent
    prompt = prompt_of(lane, read_bead(lane.epic, main_tree), plugin, READ_ONLY, True)
    started = clock.now()
    lane.report.unlink(missing_ok=True)
    reply_path(lane.report).unlink(missing_ok=True)
    state_path(lane.report).parent.mkdir(parents=True, exist_ok=True)
    state = {"epic": lane.epic, "route": route, "reply": str(reply_path(lane.report)), "started": started,
             "wall_seconds": wall_seconds, "main": fingerprint(main_tree)}
    state_path(lane.report).write_text(json.dumps(state), encoding="utf-8")
    return {"delegate_task": delegate_task_of(prompt, route), "reply": state["reply"], "wall_seconds": wall_seconds,
            "deadline": started + wall_seconds}


def started_state(report: Path) -> dict:
    path = state_path(report)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LaneError(f"{path} was not read, so the lane never started: {error}") from error
    if not (isinstance(state, dict) and isinstance(state.get("epic"), str) and isinstance(state.get("route"), dict)
            and isinstance(state.get("reply"), str) and isinstance(state.get("started"), int)
            and isinstance(state.get("wall_seconds"), int) and isinstance(state.get("main"), str)):
        raise LaneError(f"{path} does not hold the start of a lane")
    return state


def finish(report: Path, home: Path, main_tree: Path) -> int:
    """Writes the report from the reply and records the row. Returns the number of findings; raises LaneError for a
    failed run."""
    state = started_state(report)
    seconds = max(0, clock.now() - state["started"])
    outcome = FAILED
    report.unlink(missing_ok=True)
    try:
        if seconds > state["wall_seconds"]:
            raise LaneError(f"{CHILD} ran past the wall clock of {state['wall_seconds']} seconds")
        if fingerprint(main_tree) != state["main"]:
            raise LaneError(f"the main checkout {main_tree} changed while the child ran, and the lane only reads")
        reply = Path(state["reply"])
        text = reply.read_text(encoding="utf-8", errors="replace") if reply.is_file() else ""
        if not text.strip():
            raise LaneError(f"{CHILD} left no reply at {reply}")
        found = write_report(report, text, CHILD)
        outcome = DONE
        return found
    except CommandError as error:
        raise LaneError(str(error)) from error
    finally:
        record(home, main_tree, state["epic"], state["route"], T3, Tokens(0, 0, 0, 0), seconds, outcome)
        state_path(report).unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="t3_lane.py", description="Run the Spec lane of a review as a T3 child task.")
    modes = parser.add_subparsers(dest="mode", required=True)
    starting = modes.add_parser("start", help="record the start and print the arguments of the delegate_task call")
    starting.add_argument("epic")
    starting.add_argument("--worktree", required=True, help="the review worktree, which the child reads")
    starting.add_argument("--report", required=True, help="the lane's report, review-spec.json in the scratch folder")
    starting.add_argument("--base", required=True, help="the base of the review's diff")
    starting.add_argument("--head", required=True, help="the head of the review's diff")
    starting.add_argument("--file", action="append", required=True, help="a file of the diff; once for each")
    starting.add_argument("--doc", action="append", help="the path of the glossary or a house rules file; once each")
    starting.add_argument("--wall-seconds", type=int, default=lap_record.wall_clock_seconds(REVIEW_STAGE),
                          help="the wall clock of the stage, after which the manager cancels the child")
    starting.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    finishing = modes.add_parser("finish", help="write the report from the child's reply and record the run")
    finishing.add_argument("--report", required=True, help="the lane's report, as given to start")
    finishing.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = settings_reader.jidoka_home(args.jidoka_home)
        if args.mode == "start":
            lane = Lane(args.epic, Path(args.worktree), Path(args.report), args.base, args.head, args.file,
                        args.doc or [])
            print(json.dumps(start(lane, args.wall_seconds, home, main_tree)))
        else:
            found = finish(Path(args.report), home, main_tree)
            print(json.dumps({"lane": review.SPEC, "report": args.report, "findings": found}))
    except (LaneError, CommandError, routes.RouteError, settings_reader.SettingsError, OSError) as error:
        print(f"t3_lane: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
