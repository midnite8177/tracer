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
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

import clock
import lap_record
import ledger
import processes
import repo_settings
import review
import routes
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, read_bead
from lap_outcomes import DONE, FAILED
from prices import Tokens

CODEX = routes.CODEX_HARNESS
REVIEW_STAGE = "review"
LANE_TIER = routes.SECOND_TIER
OUTPUT_NAME = "last-message.txt"
STDERR_TAIL_LINES = 5
FENCED_BLOCK = re.compile(r"```[A-Za-z]*\s*\n(.*?)```", re.DOTALL)
CODE_REVIEW_SKILL = Path("skills") / "code-review" / "SKILL.md"


class LaneError(Exception):
    """A reason the lane's run failed, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Lane:
    """The Spec lane's action as the manager passes it: where it reads and writes, and what it reads."""
    epic: str
    worktree: Path
    report: Path
    base: str
    head: str
    files: list[str]
    docs: list[str]
    wall_seconds: int


@dataclass(frozen=True)
class CodexRun:
    """How a codex run ended: the exit code, None when the wall clock stopped it, what it printed on stdout and
    stderr, and the last message it wrote."""
    code: int | None
    stdout: str
    stderr: str
    message: str


def prompt_of(lane: Lane, epic: dict, plugin: Path) -> str:
    docs = "\n".join(f"- {each}" for each in lane.docs) or "- none"
    files = "\n".join(f"- {each}" for each in lane.files)
    return "\n".join([
        f"You are the Spec lane of the review of the epic {lane.epic}. The run is unattended: ask nothing. You work in "
        "a read-only sandbox, so change no file and write nothing.",
        "",
        f"Read {plugin / CODE_REVIEW_SKILL} and run its unattended mode for the spec lane alone, over "
        f"`git diff {lane.base} {lane.head}` limited to these files:",
        files,
        "",
        "The house rules and the glossary are at these paths:",
        docs,
        "",
        f"The epic, {epic.get('title') or lane.epic}:",
        str(epic.get("description") or ""),
        "",
        "End your reply with a JSON list and nothing after it: one object for each finding, with the keys \"file\", "
        f"\"line\", \"title\", \"note\", \"size\" ({', '.join(review.SIZES)}) and \"confidence\" "
        f"({', '.join(review.CONFIDENCES)}). Write [] when you find nothing."])


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


def run_codex(command: list[str], prompt: str, lane: Lane, last_message: Path) -> CodexRun:
    try:
        process = subprocess.Popen(command, cwd=lane.worktree, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                   **processes.detached_options())
    except OSError as error:
        raise LaneError(f"cannot run codex: {error}") from error
    code: int | None
    try:
        stdout, stderr = process.communicate(prompt, timeout=lane.wall_seconds)
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


def findings_text(message: str) -> str:
    """The JSON list in codex's last message: the whole message, else its last fenced block, else the text from its
    first bracket to its last."""
    candidates = [message.strip(), *reversed([each.strip() for each in FENCED_BLOCK.findall(message)])]
    if "[" in message and "]" in message:
        candidates.append(message[message.index("["):message.rindex("]") + 1])
    for each in candidates:
        try:
            if isinstance(json.loads(each), list):
                return each
        except ValueError:
            continue
    raise LaneError("codex's last message holds no JSON list of findings")


def failure_of(ended: CodexRun, lane: Lane) -> str | None:
    """Why the run failed, or None when it ended well."""
    if ended.code is None:
        return f"codex ran past its wall clock of {lane.wall_seconds} seconds and was stopped"
    if ended.code != 0:
        tail = " | ".join(ended.stderr.strip().splitlines()[-STDERR_TAIL_LINES:])
        return f"codex exited {ended.code}" + (f": {tail}" if tail else "")
    if not ended.message.strip():
        return "codex ended with an empty last message"
    return None


def write_report(lane: Lane, message: str) -> int:
    """Writes the report from the message and returns the number of findings; leaves no report when the review's
    settle would refuse it."""
    lane.report.parent.mkdir(parents=True, exist_ok=True)
    lane.report.write_text(findings_text(message), encoding="utf-8")
    try:
        return len(review.lane_findings(lane.report, review.SPEC))
    except review.ReviewError as error:
        lane.report.unlink(missing_ok=True)
        raise LaneError(f"codex's findings are not a usable report: {error}") from error


def record(home: Path, main_tree: Path, lane: Lane, route: dict, tokens: Tokens, seconds: int, outcome: str) -> None:
    model, effort = ledger.text_or_none(route.get("model")), ledger.text_or_none(route.get("effort"))
    ran = ledger.Ran(tokens, CODEX, model, effort)
    where = replace(ledger.Where.of_pass(REVIEW_STAGE), wall_seconds=seconds)
    ledger.record_ran_or_say(home, main_tree, lane.epic, where, ledger.Worker(None, LANE_TIER, False), ran, outcome,
                             clock.now())


def run_lane(lane: Lane, home: Path, main_tree: Path) -> int:
    """Runs the lane and records its row. Returns the number of findings; raises LaneError for a failed run."""
    route = routes.recorded_route(LANE_TIER, home)
    plugin = Path(__file__).resolve().parent.parent
    started = clock.now()
    tokens = Tokens(0, 0, 0, 0)
    outcome = FAILED
    lane.report.unlink(missing_ok=True)
    try:
        prompt = prompt_of(lane, read_bead(lane.epic, main_tree), plugin)
        with tempfile.TemporaryDirectory(prefix="jidoka-codex-") as folder:
            last_message = Path(folder) / OUTPUT_NAME
            ended = run_codex(codex_command(route, lane, last_message), prompt, lane, last_message)
        tokens = tokens_in(ended.stdout)
        failure = failure_of(ended, lane)
        if failure is not None:
            raise LaneError(failure)
        found = write_report(lane, ended.message)
        outcome = DONE
        return found
    except CommandError as error:
        raise LaneError(str(error)) from error
    finally:
        record(home, main_tree, lane, route, tokens, max(0, clock.now() - started), outcome)


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
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = repo_settings.jidoka_home(args.jidoka_home)
        lane = Lane(args.epic, Path(args.worktree), Path(args.report), args.base, args.head, args.file,
                    args.doc or [], args.wall_seconds)
        found = run_lane(lane, home, main_tree)
    except (LaneError, CommandError, routes.RouteError, repo_settings.SettingsError, OSError) as error:
        print(f"codex_lane: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"lane": review.SPEC, "report": str(lane.report), "findings": found}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
