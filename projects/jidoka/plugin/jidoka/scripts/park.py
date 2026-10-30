#!/usr/bin/env python3
"""Parks a lap's task on the human, and posts a worker's question when that is why.

The scheduler imports it. A parked task is open and
unassigned, carries the `human` label, and rests at the parked stage. Its
worktree and branch stay, and its lap holds no slot and no area, so the
scheduler opens the next ready task's lap in the freed slot.

A worker never asks live. A stage that needs a decision ends with a question
report, the JSON file `question.json` in the lap's scratch folder:
  question     the question in one sentence, which the page shows as its
               heading and the comment shows first. A report without it is
               refused.
  found        what the worker found, in plain words.
  options      two or more, each with a `name` and a `confidence`, the whole
               number of percent, from 0 to 100, that it is the right answer.
  recommended  the `name` of the one option the worker recommends.
Three keys are optional, and the page and the comment show them when present:
  shown        what the app shows the user today.
  why          a list of short steps that explain why, in order.
  next         on an option, what happens next if the human picks it.
Posting the question writes its page (question_page.py) in the jidoka home,
then comments on the task the question, what was found, the optional words, every option with
its confidence, the recommendation and the page's link, and sets the task's
metadata `question.options` to the options as JSON and `question.recommended` to
the recommended name. The comment holds the whole question without the page.
The report file is removed once posted.

The human answers by taking the `human` label off. answer_of gives the answer
to the lap that follows: the comments posted since the question, or the
recommendation when there are none. A comment that asks back is answered the
same way as any other: the lap's worker replies with a new question report.

A permission question is a question about a call the lap mod denied. Its
report adds two keys:
  call     the call the lap mod denied, as the denial printed it.
  pattern  the command prefix that would allow it: one simple command whose
           words appear in the call.
Jidoka writes its question itself from the pattern, "May lap workers run
<pattern>?", so its report needs no `question`. Its options are exactly the
three lists, `epic` (the epic's factory rules), `repo` (the repo settings'
worker commands) and `built-in` (the built-in list's additions on this
machine). Jidoka writes each option's card itself, on the page and in the
comment: the change the list makes in plain words, what the next lap does,
and the list's name as the answer word to type. The worker's `next` on such
an option is not shown. The task's metadata gets `question.call`
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

import lap_record
import question_page
import repo_settings
import rules
from commands import (COMMAND_TIMEOUT_SECONDS, FACTORY_ACTOR, HUMAN_LABEL, CommandError, bd_comments, env_as_factory,
                      metadata_of, parent_of, read_bead, run, set_metadata)
from discovered import BLOCKED_PREFIX
from report_text import parsed_report

QUESTION_PREFIX = "Question: "
PARKED_PREFIX = "Parked: "
PARK_PREFIXES = (QUESTION_PREFIX, PARKED_PREFIX, BLOCKED_PREFIX)
COMMENT = "comment"
RECOMMENDATION = "recommendation"
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
    """One answer a question offers, the worker's confidence in percent that it is the right one and what happens
    next if the human picks it ("" when the worker gave none). A permission option also holds `change`, the change
    its list makes in plain words, and its name is then the answer word the human types ("" for any other option)."""
    name: str
    confidence: int
    next_step: str
    change: str


@dataclass(frozen=True)
class Denial:
    """The call the lap mod denied, and the command prefix whose entry on a list would allow it."""
    call: str
    pattern: str


@dataclass(frozen=True)
class Question:
    """The question in one sentence, what a worker found, the options it offers and the name of the one it recommends.

    `shown` is what the app shows and `why` the steps that explain it, "" and empty when the worker gave none. A
    permission question also holds the denial it is about, and its sentence is written from that denial.
    """
    question: str
    found: str
    shown: str
    why: tuple[str, ...]
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
    return Option(text_of(value.get("name"), "the name of an option"), confidence,
                  optional_text(value, "next", "next of an option"), "")


def optional_text(report: dict, key: str, what: str) -> str:
    """The text under the key, or "" when the report has no such key."""
    return text_of(report[key], what) if key in report else ""


def steps_of(report: dict) -> tuple[str, ...]:
    """The steps under `why`, or none when the report has no such key."""
    if "why" not in report:
        return ()
    steps = report["why"]
    if not isinstance(steps, list) or not steps or not all(isinstance(step, str) and step.strip() for step in steps):
        raise QuestionError("why must be a list of non-empty strings")
    return tuple(step.strip() for step in steps)


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


def permission_sentence(denial: Denial) -> str:
    return f"May lap workers run {denial.pattern}?"


def permission_option(option: Option, denial: Denial) -> Option:
    """The option with the change its list makes and what the next lap does, both written here from the pattern; the
    worker's own `next` is dropped, for it cannot know what the list does."""
    pattern = denial.pattern
    changes = {
        EPIC_LIST: (f"Only this epic's laps may run {pattern}",
                    f"The next lap starts with {pattern} allowed for this epic's laps. Laps of other epics are still "
                    "denied it."),
        REPO_LIST: (f"Every lap in this repo may run {pattern}",
                    f"The next lap starts with {pattern} on this repo's list, and so does every later lap in this "
                    "repo, whatever its epic."),
        BUILT_IN_LIST: (f"Every lap in every repo on this machine may run {pattern}",
                        f"The next lap starts with {pattern} on the built-in list, and so does every later lap in "
                        "every repo on this machine."),
    }
    change, next_step = changes[option.name]
    return Option(option.name, option.confidence, next_step, change)


def read_question(scratch: Path) -> Question:
    """The question report in the lap's scratch folder; raises QuestionError when it is missing or unusable."""
    path = scratch / QUESTION_REPORT
    report = parsed_report(path, f"the question report {path}", QuestionError)
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
    denial = denial_of(report, names)
    if denial is None:
        sentence = text_of(report.get("question"), "question")
    else:
        sentence = permission_sentence(denial)
        options = tuple(permission_option(option, denial) for option in options)
    return Question(sentence, text_of(report.get("found"), "found"), optional_text(report, "shown", "shown"),
                    steps_of(report), options, recommended, denial)


def denial_paragraph(denial: Denial) -> str:
    return (f"The lap mod denied the call `{denial.call}`. Answer with the answer word of the one list that should "
            f"allow `{denial.pattern}` from now on.\n\n")


def option_line(option: Option) -> str:
    if option.change:
        return f"- {option.change} ({option.confidence}%). Answer word: {option.name}. {option.next_step}"
    line = f"- {option.name} ({option.confidence}%)"
    return f"{line}: {option.next_step}" if option.next_step else line


def question_comment(question: Question, page: Path, worktree: Path, branch: str) -> str:
    """The whole question in plain text; the page adds pictures and no fact."""
    denial = denial_paragraph(question.denial) if question.denial is not None else ""
    shown = f"What the app shows: {question.shown}\n\n" if question.shown else ""
    why = f"Why: {' -> '.join(question.why)}\n\n" if question.why else ""
    options = "\n".join(option_line(option) for option in question.options)
    recommendation = question.recommendation
    return (f"{QUESTION_PREFIX}{question.question}\n\n{question.found}\n\n{shown}{why}{denial}"
            f"Options, each with the worker's confidence in percent that it is the right answer:\n{options}\n\n"
            f"Recommended: {recommendation.name} ({recommendation.confidence}%).\n\n"
            f"Page: {page.as_uri()}\n\n"
            f"The worktree {worktree} and the branch {branch} keep the work. Take the {HUMAN_LABEL} label off to "
            "give the task a new lap.")


@dataclass(frozen=True)
class Answer:
    """What a parked question got: the human's comments since it, or else the recommended option."""
    source: str
    text: str

    def fields(self) -> dict:
        return {"source": self.source, "text": self.text}


@dataclass(frozen=True)
class ParkComment:
    """The factory's comment that parked a bead: its id and time as bd printed them, its whole text and the prefix the
    text opens with."""
    id: str
    created_at: str
    text: str
    prefix: str

    @property
    def body(self) -> str:
        """The text after the prefix, without the whitespace around it."""
        return self.text[len(self.prefix):].strip()


def park_prefix_of(comment: dict) -> str | None:
    """The prefix the comment opens with when the factory posted it to park a bead, else None."""
    if comment.get("author") != FACTORY_ACTOR:
        return None
    text = str(comment.get("text") or "")
    return next((prefix for prefix in PARK_PREFIXES if text.startswith(prefix)), None)


def latest_park_index(comments: list[dict]) -> int | None:
    """The place in the comments of the latest one that parked the bead, or None when none did."""
    parks = [index for index, comment in enumerate(comments) if park_prefix_of(comment) is not None]
    return parks[-1] if parks else None


def latest_park(bead: str, main_tree: Path) -> ParkComment | None:
    """The factory's latest `Question:`, `Parked:` or `Blocked:` comment on the bead, or None when the factory never
    parked it, as when the human did."""
    comments = bd_comments(bead, main_tree)
    index = latest_park_index(comments)
    if index is None:
        return None
    comment = comments[index]
    return ParkComment(str(comment.get("id") or ""), str(comment.get("created_at") or ""),
                       str(comment.get("text") or ""), park_prefix_of(comment) or "")


def answer_of(task: str, recommended: str, main_tree: Path) -> Answer | None:
    """The answer a task's question has, or None when the task's last park was not for a question.

    The park is the factory's latest `Question:`, `Parked:` or `Blocked:` comment. The answer is every comment by anyone
    else since a question, joined in order, or the recommended option when there are none. The comment of a
    failed build try is no park, so the answer survives a retry and a restart.
    """
    comments = bd_comments(task, main_tree)
    parked = latest_park_index(comments)
    if parked is None or park_prefix_of(comments[parked]) != QUESTION_PREFIX or not recommended:
        return None
    replies = [str(comment.get("text") or "").strip() for comment in comments[parked + 1:]
               if comment.get("author") != FACTORY_ACTOR]
    replies = [reply for reply in replies if reply]
    if replies:
        return Answer(COMMENT, "\n\n".join(replies))
    return Answer(RECOMMENDATION, recommended)


def park(task: str, tries: int, comment: str, metadata: list[tuple[str, str]], main_tree: Path) -> None:
    """Comments on the task and ends its lap parked, under the actor jidoka."""
    env = env_as_factory()
    run(["bd", "comment", task, comment], main_tree, env)
    run(["bd", "update", task, f"--add-label={HUMAN_LABEL}", *lap_record.resting_with_tries(lap_record.PARKED, tries),
         *set_metadata(*metadata)], main_tree, env)


def write_page(task: str, question: Question, home: Path, main_tree: Path) -> Path:
    """Writes the question's page; raises QuestionError when the file cannot be written."""
    cards = tuple(question_page.Card(option.change or option.name, option.name if option.change else "",
                                     option.confidence, option.next_step, option.name == question.recommended)
                  for option in question.options)
    page = question_page.QuestionPage(task, question.question, question.found, question.shown, question.why, cards)
    try:
        return question_page.write(page, home, main_tree)
    except OSError as error:
        raise QuestionError(f"the question page could not be written: {error}") from error


@dataclass(frozen=True)
class AskingLap:
    """The part of a lap that a question needs: the task, the tries it has used, its scratch folder that holds the
    question report, and the worktree and branch that keep its work."""
    task: str
    tries: int
    scratch: Path
    worktree: Path
    branch: str


def park_on_question(lap: AskingLap, home: Path, main_tree: Path) -> None:
    """Writes the lap's question page, posts its question report on the task and parks the task; raises
    QuestionError for a bad report or a page that cannot be written."""
    question = read_question(lap.scratch)
    page = write_page(lap.task, question, home, main_tree)
    options = json.dumps([{"name": option.name, "confidence": option.confidence} for option in question.options])
    denial = question.denial or Denial("", "")
    park(lap.task, lap.tries, question_comment(question, page, lap.worktree, lap.branch),
         [(OPTIONS_KEY, options), (RECOMMENDED_KEY, question.recommended), (CALL_KEY, denial.call),
          (PATTERN_KEY, denial.pattern)], main_tree)
    (lap.scratch / QUESTION_REPORT).unlink(missing_ok=True)


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
    shown = read_bead(task, main_tree)
    metadata = metadata_of(shown)
    denial = denial_in(metadata)
    if denial is None:
        raise QuestionError(f"the last question on {task} was no permission question")
    answer = answer_of(task, str(metadata.get(RECOMMENDED_KEY) or ""), main_tree)
    if answer is None:
        raise QuestionError(f"{task} holds no answered question")
    return allow_answered(denial, answer, parent_of(shown), home, main_tree)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="park.py", description="Post a worker's question or apply its answer.")
    modes = parser.add_subparsers(dest="mode", required=True)
    asking = modes.add_parser("question", help="post the question report in a scratch folder and park the task")
    asking.add_argument("task")
    asking.add_argument("--scratch", required=True, type=Path)
    asking.add_argument("--worktree", required=True, type=Path)
    asking.add_argument("--branch", required=True)
    asking.add_argument("--tries", required=True, type=int)
    asking.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    answering = modes.add_parser("answer", help="add the answered permission question's pattern to the list it names")
    answering.add_argument("task")
    answering.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        if args.mode == "question":
            asked = AskingLap(args.task, args.tries, args.scratch, args.worktree, args.branch)
            park_on_question(asked, repo_settings.jidoka_home(args.jidoka_home), main_tree)
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
