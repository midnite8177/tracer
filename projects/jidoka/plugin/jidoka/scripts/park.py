#!/usr/bin/env python3
"""Parks a lap's task on the human, and posts a worker's question when that is why.

The scheduler imports it. A parked task is open and
unassigned, carries the `human` label, and has `lap.stage` parked. Its
worktree and branch stay, and its lap holds no slot and no area, so the
scheduler opens the next ready task's lap in the freed slot.

A worker never asks live. A stage that needs a decision ends with a question
report, the JSON file `question.json` in the lap's scratch folder:
  found        what the worker found, in plain words.
  options      two or more, each with a `name` and a `confidence`, the whole
               number of percent, from 0 to 100, that it is the right answer.
  recommended  the `name` of the one option the worker recommends.
Posting the question comments on the task what was found, every option with
its confidence, and the recommendation, and sets the task's metadata
`question.options` to the options as JSON and `question.recommended` to the
recommended name. The report file is removed once posted.

The human answers by taking the `human` label off. answer_of gives the answer
to the lap that follows: the comments posted since the question, or the
recommendation when there are none. A comment that asks back is answered the
same way as any other: the lap's worker replies with a new question report.

A permission question is a question about a call the lap mod denied. Its
report adds two keys:
  call     the call the lap mod denied, as the denial printed it.
  pattern  the command prefix that would allow it: one simple command whose
           words appear in the call.
Its options are exactly the three lists, `epic` (the epic's factory rules),
`repo` (the repo settings' worker commands) and `built-in` (the built-in
list's additions on this machine). The task's metadata gets `question.call`
and `question.pattern`, both empty after any other question. The answer
names one list, and the pattern goes onto it, so the next lap's mod allows
the call. The scheduler adds the pattern when it opens the lap that follows
the answer, and `answer` does the same from a command line.

`question <task> --scratch <folder> --worktree <path> --branch <name> --tries <n>`
posts the question report in the scratch folder and parks the task.
`answer <task>` adds the pattern of the task's answered permission question to
the list the answer names, and prints the task, the list, the pattern and
whether the list changed. The home is --jidoka-home, else $JIDOKA_HOME, else
~/.jidoka.

Exit codes:
  0  success.
  1  it refused, or a bd command failed, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

import repo_settings
import rules
from commands import COMMAND_TIMEOUT_SECONDS, FACTORY_ACTOR, CommandError, bd_show, env_as_factory, run
from discovered import BLOCKED_PREFIX

QUESTION_PREFIX = "Question: "
PARKED_PREFIX = "Parked: "
COMMENT = "comment"
RECOMMENDATION = "recommendation"
HUMAN_LABEL = "human"
PARKED = "parked"
QUESTION_REPORT = "question.json"
OPTIONS_KEY = "question.options"
RECOMMENDED_KEY = "question.recommended"
CALL_KEY = "question.call"
PATTERN_KEY = "question.pattern"
EPIC_LIST, REPO_LIST, BUILT_IN_LIST = "epic", "repo", "built-in"
PERMISSION_LISTS = (EPIC_LIST, REPO_LIST, BUILT_IN_LIST)
SHELL_SYNTAX = re.compile(r"[;&|<>`\n]|\$\(")
LEAST_OPTIONS = 2
LEAST_CONFIDENCE = 0
MOST_CONFIDENCE = 100


class QuestionError(Exception):
    """A reason a question report cannot be posted, worded for the worker that writes the next one."""


@dataclass(frozen=True)
class Option:
    """One answer a question offers, and the worker's confidence in percent that it is the right one."""
    name: str
    confidence: int


@dataclass(frozen=True)
class Denial:
    """The call the lap mod denied, and the command prefix whose entry on a list would allow it."""
    call: str
    pattern: str


@dataclass(frozen=True)
class Question:
    """What a worker found, the options it offers and the name of the one it recommends.

    A permission question also holds the denial it is about.
    """
    found: str
    options: tuple[Option, ...]
    recommended: str
    denial: Denial | None

    @property
    def recommendation(self) -> Option:
        return next(option for option in self.options if option.name == self.recommended)


def text_of(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QuestionError(f"{what} must be a non-empty string")
    return value.strip()


def option_of(value: object) -> Option:
    if not isinstance(value, dict):
        raise QuestionError("each option must be an object with a name and a confidence")
    confidence = value.get("confidence")
    if (not isinstance(confidence, int) or isinstance(confidence, bool)
            or not LEAST_CONFIDENCE <= confidence <= MOST_CONFIDENCE):
        raise QuestionError(f"the confidence of an option must be a whole number of percent from "
                            f"{LEAST_CONFIDENCE} to {MOST_CONFIDENCE}, not {confidence!r}")
    return Option(text_of(value.get("name"), "the name of an option"), confidence)


def words_of(command: str, what: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError as error:
        raise QuestionError(f"{what} {command!r} is not a command: {error}") from error


def denial_of(report: dict, option_names: list[str]) -> Denial | None:
    """The denial a permission question report holds, or None when it holds neither call nor pattern."""
    if "call" not in report and "pattern" not in report:
        return None
    call = text_of(report.get("call"), "call")
    pattern = text_of(report.get("pattern"), "pattern")
    if sorted(option_names) != sorted(PERMISSION_LISTS):
        raise QuestionError(f"the options of a permission question must be the three lists, one each: "
                            f"{', '.join(PERMISSION_LISTS)}")
    if SHELL_SYNTAX.search(pattern):
        raise QuestionError("pattern must be one simple command, with no separator, redirect or substitution")
    wanted, spoken = words_of(pattern, "pattern"), words_of(call, "call")
    if not any(spoken[start:start + len(wanted)] == wanted for start in range(len(spoken))):
        raise QuestionError("the words of pattern must appear in call, one after the other")
    return Denial(call, pattern)


def read_question(scratch: Path) -> Question:
    """The question report in the lap's scratch folder; raises QuestionError when it is missing or unusable."""
    path = scratch / QUESTION_REPORT
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise QuestionError(f"the question report {path} cannot be read: {error}") from error
    except ValueError as error:
        raise QuestionError(f"the question report {path} is not JSON: {error}") from error
    if not isinstance(report, dict):
        raise QuestionError(f"the question report {path} must be a JSON object")
    raw_options = report.get("options")
    if not isinstance(raw_options, list) or len(raw_options) < LEAST_OPTIONS:
        raise QuestionError(f"the question report {path} must hold at least {LEAST_OPTIONS} options")
    options = tuple(option_of(raw) for raw in raw_options)
    names = [option.name for option in options]
    if len(set(names)) != len(names):
        raise QuestionError("the options of a question must have different names")
    recommended = text_of(report.get("recommended"), "recommended")
    if recommended not in names:
        raise QuestionError(f"recommended must be the name of one option: {', '.join(names)}")
    return Question(text_of(report.get("found"), "found"), options, recommended, denial_of(report, names))


def denial_paragraph(denial: Denial) -> str:
    return (f"The lap mod denied the call `{denial.call}`. Answer with the one list that should allow "
            f"`{denial.pattern}` from now on:\n"
            f"- {EPIC_LIST}: this epic's factory rules, so only this epic's laps may run it\n"
            f"- {REPO_LIST}: the repo's list, so every lap in this repo may run it\n"
            f"- {BUILT_IN_LIST}: the built-in list, so every lap in every repo on this machine may run it\n\n")


def question_comment(question: Question, worktree: Path, branch: str) -> str:
    options = "\n".join(f"- {option.name} ({option.confidence}%)" for option in question.options)
    recommendation = question.recommendation
    denial = denial_paragraph(question.denial) if question.denial is not None else ""
    return (f"{QUESTION_PREFIX}{question.found}\n\n{denial}"
            f"Options, each with the worker's confidence in percent that it is the right answer:\n{options}\n\n"
            f"Recommended: {recommendation.name} ({recommendation.confidence}%).\n\n"
            f"The worktree {worktree} and the branch {branch} keep the work. Take the {HUMAN_LABEL} label off to "
            "give the task a new lap.")


@dataclass(frozen=True)
class Answer:
    """What a parked question got: the human's comments since it, or else the recommended option."""
    source: str
    text: str

    def fields(self) -> dict:
        return {"source": self.source, "text": self.text}


def posted_comments(task: str, main_tree: Path) -> list[dict]:
    output = run(["bd", "comments", task, "--json"], main_tree, None)
    try:
        comments = json.loads(output or "[]") or []
    except ValueError as error:
        raise CommandError(f"bd comments did not print JSON: {output.strip()[:200]!r}") from error
    return [comment for comment in comments if isinstance(comment, dict)]


def answer_of(task: str, recommended: str, main_tree: Path) -> Answer | None:
    """The answer a task's question has, or None when the task's last park was not for a question.

    The park is the factory's latest `Question:`, `Parked:` or `Blocked:` comment. The answer is every comment by anyone
    else since a question, joined in order, or the recommended option when there are none. The comment of a
    failed build try is no park, so the answer survives a retry and a restart.
    """
    comments = posted_comments(task, main_tree)
    parks = [index for index, comment in enumerate(comments)
             if comment.get("author") == FACTORY_ACTOR
             and str(comment.get("text") or "").startswith((QUESTION_PREFIX, PARKED_PREFIX, BLOCKED_PREFIX))]
    if not parks or not str(comments[parks[-1]].get("text")).startswith(QUESTION_PREFIX) or not recommended:
        return None
    replies = [str(comment.get("text") or "").strip() for comment in comments[parks[-1] + 1:]
               if comment.get("author") != FACTORY_ACTOR]
    replies = [reply for reply in replies if reply]
    if replies:
        return Answer(COMMENT, "\n\n".join(replies))
    return Answer(RECOMMENDATION, recommended)


def park(task: str, tries: int, comment: str, metadata: list[tuple[str, str]], main_tree: Path) -> None:
    """Comments on the task and ends its lap parked, under the actor jidoka."""
    env = env_as_factory()
    run(["bd", "comment", task, comment], main_tree, env)
    written = [argument for key, value in metadata for argument in ("--set-metadata", f"{key}={value}")]
    run(["bd", "update", task, "--status=open", "--assignee=", f"--add-label={HUMAN_LABEL}",
         "--set-metadata", f"lap.stage={PARKED}", "--set-metadata", f"lap.tries={tries}", *written], main_tree, env)


def park_on_question(task: str, tries: int, scratch: Path, worktree: Path, branch: str, main_tree: Path) -> None:
    """Posts the lap's question report on its task and parks the task; raises QuestionError for a bad report."""
    question = read_question(scratch)
    options = json.dumps([{"name": option.name, "confidence": option.confidence} for option in question.options])
    denial = question.denial or Denial("", "")
    park(task, tries, question_comment(question, worktree, branch),
         [(OPTIONS_KEY, options), (RECOMMENDED_KEY, question.recommended), (CALL_KEY, denial.call),
          (PATTERN_KEY, denial.pattern)], main_tree)
    (scratch / QUESTION_REPORT).unlink(missing_ok=True)


def denial_in(metadata: dict) -> Denial | None:
    """The denial a task's metadata holds, or None when its last question was no permission question."""
    call, pattern = str(metadata.get(CALL_KEY) or ""), str(metadata.get(PATTERN_KEY) or "")
    return Denial(call, pattern) if pattern else None


def list_named(answer: Answer) -> str:
    """The one list an answer names; raises QuestionError when it names none or more than one."""
    named = {match.group(1) for match in re.finditer(r"(?<![\w-])(epic|repo|built-in)(?![\w-])", answer.text.lower())}
    if len(named) != 1:
        raise QuestionError(f"the answer must name exactly one list of {', '.join(PERMISSION_LISTS)}, and "
                            f"{answer.text!r} names {len(named)}")
    return named.pop()


@dataclass(frozen=True)
class Allowed:
    """The list a permission answer chose, the pattern, and whether the list changed."""
    chosen: str
    pattern: str
    changed: bool


def allow(chosen: str, pattern: str, epic: str, home: Path, main_tree: Path) -> bool:
    """Adds the pattern to the chosen list; False when the list already holds it."""
    if chosen == EPIC_LIST:
        return rules.allow_extra_command(epic, pattern, home, main_tree)
    if chosen == REPO_LIST:
        return repo_settings.add_worker_command(home, main_tree, pattern)
    return repo_settings.add_built_in_command(home, pattern)


def allow_answered(denial: Denial, answer: Answer, epic: str, home: Path, main_tree: Path) -> Allowed:
    """Puts the denial's pattern on the list the answer names, so the next lap's mod allows the call."""
    chosen = list_named(answer)
    return Allowed(chosen, denial.pattern, allow(chosen, denial.pattern, epic, home, main_tree))


def answered_permission(task: str, home: Path, main_tree: Path) -> Allowed:
    """Applies the answer of the task's permission question; raises QuestionError when there is none to apply."""
    shown = bd_show(task, main_tree)
    if shown is None:
        raise QuestionError(f"bd show printed nothing usable for {task}")
    metadata = shown.get("metadata") or {}
    denial = denial_in(metadata)
    if denial is None:
        raise QuestionError(f"the last question on {task} was no permission question")
    answer = answer_of(task, str(metadata.get(RECOMMENDED_KEY) or ""), main_tree)
    if answer is None:
        raise QuestionError(f"{task} holds no answered question")
    return allow_answered(denial, answer, str(shown.get("parent") or ""), home, main_tree)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="park.py", description="Post a worker's question or apply its answer.")
    modes = parser.add_subparsers(dest="mode", required=True)
    asking = modes.add_parser("question", help="post the question report in a scratch folder and park the task")
    asking.add_argument("task")
    asking.add_argument("--scratch", required=True, type=Path)
    asking.add_argument("--worktree", required=True, type=Path)
    asking.add_argument("--branch", required=True)
    asking.add_argument("--tries", required=True, type=int)
    answering = modes.add_parser("answer", help="add the answered permission question's pattern to the list it names")
    answering.add_argument("task")
    answering.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        if args.mode == "question":
            park_on_question(args.task, args.tries, args.scratch, args.worktree, args.branch, main_tree)
            printed = {"task": args.task, "parked": True}
        else:
            allowed = answered_permission(args.task, repo_settings.jidoka_home(args.jidoka_home), main_tree)
            printed = {"task": args.task, "list": allowed.chosen, "pattern": allowed.pattern,
                       "changed": allowed.changed}
    except (QuestionError, rules.RulesError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"park: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
