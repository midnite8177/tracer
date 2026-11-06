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
import json
import sys
from pathlib import Path

import clock
import lap_record
import review
import routes
import rules
import settings_reader
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, read_bead
from lane_report import REVIEW_STAGE, Lane, LaneError, prompt_of, record, write_report
from lap_outcomes import DONE, FAILED
from prices import Tokens
from t3_child import CHILD, ChildError, check_child_run, record_start, started_state

T3 = routes.T3_HARNESS
STATE_NAME = "t3-spec-start.json"
REPLY_NAME = "t3-spec-reply.txt"
READ_ONLY = "You only read. Change no file, create no file, and run no command that writes."
ROUTE_FIELDS = ("provider", "model", "effort")


def state_path(report: Path) -> Path:
    return report.with_name(STATE_NAME)


def reply_path(report: Path) -> Path:
    return report.with_name(REPLY_NAME)


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
    lane.report.unlink(missing_ok=True)
    return record_start(state_path(lane.report), reply_path(lane.report), lane.epic, route, wall_seconds, main_tree,
                        {}, delegate_task_of(prompt, route))


def finish(report: Path, home: Path, main_tree: Path) -> int:
    """Writes the report from the reply and records the row. Returns the number of findings; raises LaneError for a
    failed run."""
    try:
        state = started_state(state_path(report), {}, "lane")
    except ChildError as error:
        raise LaneError(str(error)) from error
    seconds = max(0, clock.now() - state["started"])
    outcome = FAILED
    report.unlink(missing_ok=True)
    try:
        text = check_child_run(state, seconds, main_tree, "the lane only reads")
        found = write_report(report, text, CHILD)
        outcome = DONE
        return found
    except (CommandError, ChildError) as error:
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
