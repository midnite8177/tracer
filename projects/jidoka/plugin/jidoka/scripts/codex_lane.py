#!/usr/bin/env python3
"""Runs the Spec lane of a pass's review in `codex exec`, for a second tier that routes to codex.

`codex_lane.py <epic> --worktree <review worktree> --report <review-spec.json> --base <sha> --head <sha> --file <path>
...` is what the manager runs in place of an agent for the lane's action, passing the action's own fields. It starts
`codex exec` in the review worktree in a read-only sandbox, with the route's model and effort when the route names
them, and under the stage's wall clock, which bounds codex's own retries of a lost connection, and sends it the lane's
prompt on stdin. A read-only sandbox cannot write the lane's report, so the script writes it from codex's last message:
a JSON list of findings, read as the review's settle reads a native lane's report. A report that settle would refuse
is a failed run, and the script leaves no report behind for a failed run.

It writes the one ledger row of the run on the epic, stage `review`, harness codex, with the token totals codex printed.

Any failure exits 1 and leaves no report: codex missing or erroring, a usage limit, a run past its wall clock, an empty
last message, a last message that holds no usable list of findings, and a route the settings cannot give. The script
retries nothing.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  the report is written and the row is recorded.
  1  the run failed, with the reason on stderr, and no report is left; or it could not start.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import clock
import lap_record
import ledger
import processes
import settings_reader
import review
import routes
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, read_bead
from lane_report import REVIEW_STAGE, Lane, LaneError, prompt_of, record, write_report
from lap_outcomes import DONE, FAILED
from prices import Tokens

CODEX = routes.CODEX_HARNESS
OUTPUT_NAME = "last-message.txt"
STDERR_TAIL_LINES = 5
READ_ONLY_SANDBOX = "You work in a read-only sandbox, so change no file and write nothing."


@dataclass(frozen=True)
class CodexRun:
    """How a codex run ended: the exit code, None when the wall clock stopped it, what it printed on stdout and
    stderr, and the last message it wrote."""
    code: int | None
    stdout: str
    stderr: str
    message: str


def codex_command(route: dict, lane: Lane, last_message: Path) -> list[str]:
    command = ["codex", "exec", "--sandbox", "read-only", "--cd", str(lane.worktree), "--json",
               "--output-last-message", str(last_message)]
    if route.get("model"):
        command += ["--model", str(route["model"])]
    if route.get("effort"):
        command += ["-c", f"model_reasoning_effort={json.dumps(str(route['effort']))}"]
    return [*command, "-"]


def stop(process: subprocess.Popen) -> None:
    """Ends codex and everything it started."""
    try:
        processes.end_group(process.pid)
    except OSError:
        process.kill()


def run_codex(command: list[str], prompt: str, lane: Lane, wall_seconds: int, last_message: Path) -> CodexRun:
    try:
        process = subprocess.Popen(command, cwd=lane.worktree, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                   **processes.detached_options())
    except OSError as error:
        raise LaneError(f"cannot run codex: {error}") from error
    code: int | None
    try:
        stdout, stderr = process.communicate(prompt, timeout=wall_seconds)
        code = process.returncode
    except subprocess.TimeoutExpired:
        stop(process)
        stdout, stderr = process.communicate()
        code = None
    message = last_message.read_text(encoding="utf-8", errors="replace") if last_message.is_file() else ""
    return CodexRun(code, stdout or "", stderr or "", message)


def tokens_in(stdout: str) -> Tokens:
    """The token totals of the `turn.completed` events codex printed. Codex counts cached tokens inside its input
    tokens, so they are taken out of the input and priced as cache reads."""
    fresh = cached = output = 0
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        usage = event.get("usage") if isinstance(event, dict) and event.get("type") == "turn.completed" else None
        if not isinstance(usage, dict):
            continue
        counted = {key: ledger.count_of(usage.get(key)) for key in ("input_tokens", "cached_input_tokens",
                                                                    "output_tokens")}
        fresh += max(0, counted["input_tokens"] - counted["cached_input_tokens"])
        cached += counted["cached_input_tokens"]
        output += counted["output_tokens"]
    return Tokens(fresh, output, cached, 0)


def failure_of(ended: CodexRun, wall_seconds: int) -> str | None:
    """Why the run failed, or None when it ended well."""
    if ended.code is None:
        return f"codex ran past its wall clock of {wall_seconds} seconds and was stopped"
    if ended.code != 0:
        tail = " | ".join(ended.stderr.strip().splitlines()[-STDERR_TAIL_LINES:])
        return f"codex exited {ended.code}" + (f": {tail}" if tail else "")
    if not ended.message.strip():
        return "codex ended with an empty last message"
    return None


def run_lane(lane: Lane, wall_seconds: int, home: Path, main_tree: Path) -> int:
    """Runs the lane and records its row. Returns the number of findings; raises LaneError for a failed run."""
    route = routes.recorded_route(routes.SECOND_TIER, home)
    plugin = Path(__file__).resolve().parent.parent
    started = clock.now()
    tokens = Tokens(0, 0, 0, 0)
    outcome = FAILED
    lane.report.unlink(missing_ok=True)
    try:
        prompt = prompt_of(lane, read_bead(lane.epic, main_tree), plugin, READ_ONLY_SANDBOX, False)
        with tempfile.TemporaryDirectory(prefix="jidoka-codex-") as folder:
            last_message = Path(folder) / OUTPUT_NAME
            ended = run_codex(codex_command(route, lane, last_message), prompt, lane, wall_seconds, last_message)
        tokens = tokens_in(ended.stdout)
        failure = failure_of(ended, wall_seconds)
        if failure is not None:
            raise LaneError(failure)
        found = write_report(lane.report, ended.message, "codex")
        outcome = DONE
        return found
    except CommandError as error:
        raise LaneError(str(error)) from error
    finally:
        record(home, main_tree, lane.epic, route, CODEX, tokens, max(0, clock.now() - started), outcome)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="codex_lane.py", description="Run the Spec lane of a review in codex exec.")
    parser.add_argument("epic")
    parser.add_argument("--worktree", required=True, help="the review worktree, which codex reads")
    parser.add_argument("--report", required=True, help="the lane's report, review-spec.json in the scratch folder")
    parser.add_argument("--base", required=True, help="the base of the review's diff")
    parser.add_argument("--head", required=True, help="the head of the review's diff")
    parser.add_argument("--file", action="append", required=True, help="a file of the diff; once for each")
    parser.add_argument("--doc", action="append", help="the path of the glossary or a house rules file; once for each")
    parser.add_argument("--wall-seconds", type=int, default=lap_record.wall_clock_seconds(REVIEW_STAGE),
                        help="the wall clock of the stage, after which codex is stopped")
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = settings_reader.jidoka_home(args.jidoka_home)
        lane = Lane(args.epic, Path(args.worktree), Path(args.report), args.base, args.head, args.file,
                    args.doc or [])
        found = run_lane(lane, args.wall_seconds, home, main_tree)
    except (LaneError, CommandError, routes.RouteError, settings_reader.SettingsError, OSError) as error:
        print(f"codex_lane: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"lane": review.SPEC, "report": str(lane.report), "findings": found}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
