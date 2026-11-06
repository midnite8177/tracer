#!/usr/bin/env python3
"""Runs one tidy batch as a T3 child task on OpenCode, for a local tier that routes to t3 OpenCode.

The manager starts the child with T3's own tools, so this script runs on either side of the child's run.

  t3_tidy.py start --action <file> [--doc <path> ...] [--wall-seconds <n>]
      Reads the batch's action, the JSON object the scheduler printed, from the file. Records the route, the time, the
      batch's files and a fingerprint of the main checkout, next to the batch's scratch folder. It prints one JSON
      object: `delegate_task`, the arguments of T3's `delegate_task` call, which the manager passes as they are (the
      child gets the batch's diff and its files by absolute path, and edits them with OpenCode's edit tool; it runs in
      T3's auto-accept-edits mode, so a shell command asks for an approval that no one gives; the call is a `wait`
      with the stage's wall clock as its timeout, and T3 ends a wait as soon as the child asks for an approval); `reply`,
      the path where the manager saves the child's last reply, verbatim, before `finish`; and `wall_seconds` and
      `deadline`, the stage's wall clock and the time in epoch seconds after which the manager cancels the child. It
      refuses when the local tier's route is not a t3 OpenCode route or lacks a provider, a model or an effort.
  t3_tidy.py finish --scratch <batch scratch> [--asked-for-approval]
      Reads the route and the reply path from what `start` recorded, so a change of the settings in between does not
      change the route the row names. It writes the one ledger row of the run on the epic, stage `tidy`, tier `local`,
      harness t3, the route's model and effort, the wall time from `start` and the outcome, with no tokens, because a
      T3 task result carries none. It also leaves `t3-tidy-result.json` in the batch's scratch folder, holding the
      outcome, which the local-model trial's gate page reads to say whether the local model did the batch.
      `--asked-for-approval` is the manager's word that T3 ended the wait because the child asked for an approval,
      after the manager cancelled the child. The batch then fails for that reason, whatever the reply file holds.

The child edits the files of the tidy's worktree and nothing is committed here: the tidy's settle commits what every
batch left. Any failure exits 1: a child that asked for an approval, a run past the stage's wall clock, a missing or
empty reply, a reply that does not end `{"outcome": "done"}`, a main checkout that differs from what `start` saw, a
`start` that never ran, and a route the settings cannot give. A failed run leaves its batch's files as the head holds
them, so the rerun starts from the same files. Its row is `cut off` for a run past the wall clock and `failed` for any
other failure. T3's auto-accept-edits mode holds a shell command for an approval, which the lap mod that ADR 0005 relies
on cannot answer for a T3 child; ending the batch at the request keeps the approval from holding the batch's slot until
the wall clock runs out. The script retries nothing. The failed run is a failed route, which
the manager passes to `route.py fallback`, with the batch as part of the mark so that each batch falls back once.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  `start` printed the task, or `finish` recorded a batch that ended done.
  1  the run failed, with the reason on stderr; or it could not start.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import clock
import ledger
import lap_record
import routes
import rules
import settings_reader
import tidy
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, run
from lap_outcomes import CUT_OFF, DONE, FAILED
from prices import Tokens
from t3_child import CHILD, ChildError, WallClockExceeded, check_child_run, record_start, started_state

T3 = routes.T3_HARNESS
TIER = "local"
RUNTIME_MODE = "auto-accept-edits"
STATE_NAME = "t3-tidy-start.json"
REPLY_NAME = "t3-tidy-reply.txt"
RESULT_NAME = "t3-tidy-result.json"
ROUTE_FIELDS = ("provider", "model", "effort")
OWN_START_FIELDS = {"worktree": str, "head": str, "files": list}
NO_COMMENTS_SKILL = Path("skills") / "no-comments" / "SKILL.md"
UNSLOP_SKILL = Path("skills") / "unslop" / "SKILL.md"


class TidyChildError(Exception):
    """A reason the batch's run failed, worded for the person who reads stderr."""


def state_path(scratch: Path) -> Path:
    return scratch / STATE_NAME


def reply_path(scratch: Path) -> Path:
    return scratch / REPLY_NAME


def result_path(scratch: Path) -> Path:
    return scratch / RESULT_NAME


@dataclass(frozen=True)
class TidyBatch:
    """One tidy batch, as the fields of its scheduler action print it."""
    epic: str
    number: int
    worktree: Path
    scratch: Path
    base: str
    head: str
    files: list[str]

    @staticmethod
    def of_action(action: object) -> TidyBatch:
        if not (isinstance(action, dict) and all(rules.is_text(action.get(key)) for key in (
                "epic", "worktree", "scratch", "base", "head")) and isinstance(action.get("batch"), int)
                and isinstance(action.get("files"), list) and action["files"]
                and all(isinstance(each, str) for each in action["files"])):
            raise TidyChildError("the batch's action does not hold an epic, a batch, a worktree, a scratch folder, a "
                                 "base, a head and files")
        return TidyBatch(action["epic"], action["batch"], Path(action["worktree"]), Path(action["scratch"]),
                         action["base"], action["head"], action["files"])


def batch_outcome(scratch: Path) -> str | None:
    """The outcome that `finish` recorded for the batch, or None when it recorded none: a batch with no result never
    ran as a child, or failed before `finish`, and so fell back."""
    try:
        result = json.loads(result_path(scratch).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    outcome = result.get("outcome") if isinstance(result, dict) else None
    return outcome if isinstance(outcome, str) else None


def opencode_route(home: Path) -> dict:
    route = routes.recorded_route(TIER, home)
    if not routes.is_opencode_route(route):
        raise TidyChildError(f"the {TIER} tier's route is not a {T3} {routes.OPENCODE_DRIVER} route")
    missing = [field for field in ROUTE_FIELDS if not rules.is_text(route.get(field))]
    if missing:
        raise TidyChildError(f"the {TIER} tier's {T3} route lacks a {' and a '.join(missing)}")
    return route


def prompt_of(batch: TidyBatch, docs: list[str], diff: str, plugin: Path) -> str:
    """The task the child gets. It may run no shell command, so the diff is in the prompt, the files are named by
    absolute path, and the skills are read with the read tool."""
    listed = "\n".join(f"- {batch.worktree / each}" for each in batch.files)
    paths = "\n".join(f"- {each}" for each in docs) or "- none"
    return "\n".join([
        f"You are a tidy worker for the epic {batch.epic}, batch {batch.number}. The run is unattended: ask nothing. "
        "Run no shell command and no test: a command asks for an approval that no one gives, and ends your task. "
        "Change files with the edit tool only, change no file but the ones below and the discovered-work report, "
        "and commit nothing.",
        "",
        f"The files are in the worktree {batch.worktree}. Your own working folder is not that worktree, so read and "
        "edit each file by the absolute path below. These are the only files you may change:",
        listed,
        "",
        f"The epic changed them as follows, from {batch.base} to {batch.head}:",
        "```diff",
        diff.rstrip("\n"),
        "```",
        "",
        "The house rules and the glossary are at these paths:",
        paths,
        "",
        f"Read {plugin / NO_COMMENTS_SKILL} and follow its Unattended section, then read {plugin / UNSLOP_SKILL} and "
        "follow its Unattended section, over those files, reading every one of them whole. Leave line wrapping alone: "
        "never re-wrap a line or a paragraph, and change a line only to delete a comment or to reword prose that the "
        "skills call for.",
        "",
        f"List the work you find outside those files in {batch.scratch / 'discovered.json'}, a JSON list of objects "
        "with \"title\", \"description\" and \"placement\", where placement is \"epic\" when acceptance would reject "
        "the epic without the work and \"outside\" otherwise. File no bead.",
        "",
        "End your reply with {\"outcome\": \"done\"}, or {\"outcome\": \"failed\", \"why\": \"<one line>\"}, and "
        "nothing after it."])


def delegate_task_of(prompt: str, route: dict, wall_seconds: int) -> dict:
    """The arguments of T3's `delegate_task` call for the child: an implementation task in the shared checkout, waited
    on for the stage's wall clock, on the OpenCode provider. T3 takes only `variant` as an OpenCode option, so the
    route's effort is the variant and no agent is named. The auto-accept-edits runtime mode lets the child's edits
    through and holds any shell command for approval, which no one gives. T3 ends a wait when the child asks for an
    approval, so the batch ends at the request and falls back instead of holding its slot. The lap mod does not guard a
    T3 child, so ADR 0005 does not reach it by that route."""
    return {"task": prompt, "role": "implementation", "isolation": "shared", "mode": "wait",
            "timeoutMs": wall_seconds * 1000, "runtimeMode": RUNTIME_MODE,
            "target": {"providerInstanceId": route["provider"], "driverKind": routes.OPENCODE_DRIVER,
                       "model": route["model"], "options": {"variant": route["effort"]}}}


def start(batch: TidyBatch, docs: list[str], wall_seconds: int, home: Path, main_tree: Path) -> dict:
    route = opencode_route(home)
    plugin = Path(__file__).resolve().parent.parent
    diff = tidy.diff_of(batch.base, batch.head, batch.files, main_tree)
    prompt = prompt_of(batch, docs, diff, plugin)
    result_path(batch.scratch).unlink(missing_ok=True)
    own_fields = {"batch": batch.number, "worktree": str(batch.worktree), "head": batch.head, "files": batch.files}
    return record_start(state_path(batch.scratch), reply_path(batch.scratch), batch.epic, route, wall_seconds,
                        main_tree, own_fields, delegate_task_of(prompt, route, wall_seconds))


def ending_of(reply: str) -> dict:
    """The JSON object that ends the child's reply, with its `outcome`."""
    text = reply.strip().rstrip("`").strip()
    for at in reversed([index for index, character in enumerate(text) if character == "{"]):
        try:
            ended = json.loads(text[at:])
        except ValueError:
            continue
        if isinstance(ended, dict) and isinstance(ended.get("outcome"), str):
            return ended
    raise TidyChildError(f"{CHILD}'s reply does not end with an outcome")


def restore_files(state: dict) -> None:
    """Puts the batch's files back as the head holds them, so a rerun starts from them. A restore that fails leaves
    the files as the child left them and says so on stderr, and the failure that called it is the one reported."""
    if not state["files"]:
        return
    try:
        run(["git", "-C", state["worktree"], "--literal-pathspecs", "checkout", state["head"], "--",
             *state["files"]], Path(state["worktree"]), None)
    except CommandError as error:
        print(f"t3_tidy: the batch's files were not put back: {error}", file=sys.stderr)


def record(home: Path, main_tree: Path, state: dict, seconds: int, outcome: str) -> None:
    route = state["route"]
    ran = ledger.Ran(Tokens(0, 0, 0, 0), T3, ledger.text_or_none(route.get("model")),
                     ledger.text_or_none(route.get("effort")))
    where = replace(ledger.Where.of_pass(tidy.STAGE.name), wall_seconds=seconds)
    ledger.record_ran_or_say(home, main_tree, state["epic"], where, ledger.Worker(None, TIER, False), ran, outcome,
                             clock.now())


def settle_up(scratch: Path, state: dict, home: Path, main_tree: Path, seconds: int, outcome: str) -> None:
    """What every run leaves, whatever its outcome: a failed run's files put back, the one ledger row, the result file
    and no start record. A failure of the restore never keeps the row from being written."""
    if outcome != DONE:
        restore_files(state)
    record(home, main_tree, state, seconds, outcome)
    result_path(scratch).write_text(json.dumps({"outcome": outcome}), encoding="utf-8")
    state_path(scratch).unlink(missing_ok=True)


def finish(scratch: Path, home: Path, main_tree: Path, asked_for_approval: bool) -> None:
    """Records the row. Raises TidyChildError for a failed run, after putting the batch's files back."""
    try:
        state = started_state(state_path(scratch), OWN_START_FIELDS, "batch")
    except ChildError as error:
        raise TidyChildError(str(error)) from error
    seconds = max(0, clock.now() - state["started"])
    outcome = FAILED
    try:
        if asked_for_approval:
            raise TidyChildError(f"{CHILD} asked for an approval")
        text = check_child_run(state, seconds, main_tree, "the tidy changes the tidy worktree alone")
        ended = ending_of(text)
        if ended["outcome"] != DONE:
            raise TidyChildError(f"{CHILD} ended {ended['outcome']}: {ended.get('why') or 'no reason given'}")
        outcome = DONE
    except WallClockExceeded as error:
        outcome = CUT_OFF
        raise TidyChildError(str(error)) from error
    except (CommandError, ChildError) as error:
        raise TidyChildError(str(error)) from error
    finally:
        settle_up(scratch, state, home, main_tree, seconds, outcome)


def batch_of_file(path: Path) -> TidyBatch:
    try:
        return TidyBatch.of_action(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        raise TidyChildError(f"the batch's action {path} was not read as JSON: {error}") from error


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="t3_tidy.py", description="Run one tidy batch as a T3 child task.")
    modes = parser.add_subparsers(dest="mode", required=True)
    starting = modes.add_parser("start", help="read the batch's action, record the start and print the arguments of "
                                              "the delegate_task call")
    starting.add_argument("--action", required=True, help="a file that holds the batch's action as the scheduler "
                                                          "printed it, a JSON object")
    starting.add_argument("--doc", action="append", help="the path of the glossary or a house rules file; once each")
    starting.add_argument("--wall-seconds", type=int, default=lap_record.wall_clock_seconds(tidy.STAGE.name),
                          help="the wall clock of the stage, after which the manager cancels the child")
    starting.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    finishing = modes.add_parser("finish", help="record the child's run")
    finishing.add_argument("--scratch", required=True, help="the batch's scratch folder, as given to start")
    finishing.add_argument("--asked-for-approval", action="store_true",
                           help="T3 ended the wait because the child asked for an approval, and the manager "
                                "cancelled it")
    finishing.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = settings_reader.jidoka_home(args.jidoka_home)
        if args.mode == "start":
            print(json.dumps(start(batch_of_file(Path(args.action)), args.doc or [], args.wall_seconds, home, main_tree)))
        else:
            finish(Path(args.scratch), home, main_tree, args.asked_for_approval)
            print(json.dumps({"scratch": args.scratch, "outcome": DONE}))
    except (TidyChildError, CommandError, routes.RouteError, settings_reader.SettingsError, OSError) as error:
        print(f"t3_tidy: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
