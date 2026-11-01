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
  options      two or more, each with a `name`, a `confidence`, the whole
               number of percent, from 0 to 100, that it is the right answer,
               and a `next`, what happens next if the human picks it. A
               report where any option lacks `next` is refused.
  recommended  the `name` of the one option the worker recommends.
Two keys are optional, and the page and the comment show them when present:
  shown        what the app shows the user today.
  why          a list of short steps that explain why, in order.
Posting the question writes its page (question_page.py) in the jidoka home,
then comments on the task with the question, what was found, the optional
words, every option with its confidence, the recommendation and the page's
link, and sets the task's metadata `question.options` to the options as JSON
and `question.recommended` to the recommended name. The comment holds the
whole question without the page. The report file is removed once posted.

The human answers by taking the `human` label off. answer_of gives the answer
to the lap that follows: the comments posted since the question, or the
recommendation when there are none. A comment that asks back is answered the
same way as any other: the lap's worker replies with a new question report.

A permission question is a question about a call the lap mod denied. Its
report adds three keys:
  call     the call the lap mod denied, as the denial printed it.
  pattern  the command prefix that would allow it: one simple command whose
           words appear in the call.
  cause    why the lap mod denied it, as the denial says: `off-lists` when
           the call is off the lists, `outside-worktree` when a delete lands
           outside the worktree, `unreadable-delete` when a delete's paths
           cannot be told.
Its options are exactly the three lists, `epic` (the epic's factory rules),
`repo` (the repo settings' worker commands) and `built-in` (the built-in
list's additions on this machine), and `none`, which changes no list.

permission_question.py writes everything else of a permission question from
the denial, so the report needs no `question`, and reads which list the
answer names. The worker's `shown` and its options' `next` are dropped. Its
`why` is its reasoning for its pick, which goes on the recommended option's
card. The task's metadata gets `question.call` and `question.pattern`, both
empty after any other question. The scheduler adds the pattern to the list
the answer names when it opens the lap that follows the answer, and `answer`
does the same from a command line.

`Question` is the one format of every question, a task's and an epic's: one sentence, what was found, and options that
each say what happens next.

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
import sys
from dataclasses import dataclass
from pathlib import Path

import lap_record
import permission_question
import question_page
import settings_reader
import rules
from commands import (COMMAND_TIMEOUT_SECONDS, FACTORY_ACTOR, HUMAN_LABEL, CommandError, bd_comments, env_as_factory,
                      metadata_of, parent_of, read_bead, run, set_metadata, unset_metadata)
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
SHOWN_LABEL = "What the app shows"
LEAST_OPTIONS = 2
LEAST_CONFIDENCE = 0
MOST_CONFIDENCE = 100


class QuestionError(Exception):
    """A reason a question report cannot be posted, worded for the worker that writes the next one."""


@dataclass(frozen=True)
class ReportedOption:
    """One option as the worker's report gave it: its name, its confidence in percent and its `next`, None when it
    gave none."""
    name: str
    confidence: int
    next_step: str | None


@dataclass(frozen=True)
class Option:
    """One answer a question offers, the worker's confidence in percent that it is the right one and what happens
    next if the human picks it."""
    name: str
    confidence: int
    next_step: str

    def line(self) -> str:
        """The option as one line of the question's comment."""
        return f"- {self.name} ({self.confidence}%): {self.next_step}"

    def card(self, recommended: bool) -> question_page.Card:
        """The option as a card of the question's page."""
        return question_page.Card(self.name, None, self.confidence, self.next_step, None, recommended)


AnyOption = Option | permission_question.PermissionOption


@dataclass(frozen=True)
class Report:
    """What a worker's question report says, read and checked as far as its keys go and not yet turned into a
    question. `question` and `shown` are None when the report has none, and `denied` is None unless it is a permission
    question's report."""
    question: str | None
    found: str
    shown: str | None
    why: tuple[str, ...]
    options: tuple[ReportedOption, ...]
    recommended: str
    denied: permission_question.Denied | None


@dataclass(frozen=True)
class Question:
    """The question in one sentence, what a worker found, the options it offers and the name of the one it recommends.

    `shown` is what the app shows, or what happened on a permission question, and `shown_label` names which; it is
    None when there is none. `why` is the steps that explain it, empty when there are none. A permission question
    also holds the denial it is about.
    """
    question: str
    found: str
    shown_label: str
    shown: str | None
    why: tuple[str, ...]
    options: tuple[AnyOption, ...]
    recommended: str
    denial: permission_question.Denial | None

    @property
    def recommendation(self) -> AnyOption:
        return next(option for option in self.options if option.name == self.recommended)


def plain_question(sentence: str, found: str, options: tuple[Option, ...], recommended: str) -> Question:
    """A question that has no `shown`, no steps and no denial, as an epic asks."""
    return Question(sentence, found, SHOWN_LABEL, None, (), options, recommended, None)


def text_of(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QuestionError(f"{what} must be a non-empty string")
    return value.strip()


def optional_text(report: dict, key: str, what: str) -> str | None:
    """The text under the key, or None when the report has no such key."""
    return text_of(report[key], what) if key in report else None


def option_of(value: object) -> ReportedOption:
    if not isinstance(value, dict):
        raise QuestionError("each option must be an object with a name and a confidence")
    confidence = value.get("confidence")
    if (not isinstance(confidence, int) or isinstance(confidence, bool)
            or not LEAST_CONFIDENCE <= confidence <= MOST_CONFIDENCE):
        raise QuestionError(f"the confidence of an option must be a whole number of percent from "
                            f"{LEAST_CONFIDENCE} to {MOST_CONFIDENCE}, not {confidence!r}")
    return ReportedOption(text_of(value.get("name"), "the name of an option"), confidence,
                          optional_text(value, "next", "next of an option"))


def steps_of(report: dict) -> tuple[str, ...]:
    """The steps under `why`, or none when the report has no such key."""
    if "why" not in report:
        return ()
    steps = report["why"]
    if not isinstance(steps, list) or not steps or not all(isinstance(step, str) and step.strip() for step in steps):
        raise QuestionError("why must be a list of non-empty strings")
    return tuple(step.strip() for step in steps)


def denied_of(report: dict, option_names: list[str]) -> permission_question.Denied | None:
    """The denial a permission question report holds, or None when it is no permission question's report, one with
    neither call nor pattern."""
    if "call" not in report and "pattern" not in report:
        return None
    call = text_of(report.get("call"), "call")
    pattern = text_of(report.get("pattern"), "pattern")
    cause = text_of(report.get("cause"), "cause")
    try:
        return permission_question.denied_in(call, pattern, cause, option_names)
    except permission_question.DenialError as error:
        raise QuestionError(str(error)) from error


def read_report(scratch: Path) -> Report:
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
    denied = denied_of(report, names)
    return Report(optional_text(report, "question", "question"), text_of(report.get("found"), "found"),
                  optional_text(report, "shown", "shown"), steps_of(report), options, recommended, denied)


def ordinary_question(report: Report) -> Question:
    """The question of a report that is no permission question, in the worker's own words; raises QuestionError when
    the report lacks its question or the `next` of an option."""
    if report.question is None:
        raise QuestionError("question must be a non-empty string")
    options = []
    for option in report.options:
        if option.next_step is None:
            raise QuestionError(f"next of the option {option.name} is missing; every option must say what "
                                "happens next if the human picks it")
        options.append(Option(option.name, option.confidence, option.next_step))
    return Question(report.question, report.found, SHOWN_LABEL, report.shown, report.why, tuple(options),
                    report.recommended, None)


def asked_permission(report: Report, denied: permission_question.Denied, task: str) -> Question:
    """The question of a permission question's report, which jidoka writes from the denial: its sentence, its
    situation line, its diagram and its option cards. The worker's `shown` and `next` are dropped."""
    reason = " ".join(report.why) if report.why else None
    options = tuple(permission_question.permission_option(option.name, option.confidence, denied.denial,
                                                          reason if option.name == report.recommended else None)
                    for option in report.options)
    return Question(permission_question.sentence_of(denied.denial), report.found,
                    permission_question.SITUATION_LABEL, permission_question.situation_of(denied),
                    permission_question.steps_of_denial(task, denied), options, report.recommended, denied.denial)


def read_question(scratch: Path, task: str) -> Question:
    """The question report in the lap's scratch folder as a question; raises QuestionError when it is missing or
    unusable."""
    report = read_report(scratch)
    return ordinary_question(report) if report.denied is None else asked_permission(report, report.denied, task)


def question_comment(question: Question, page: Path, closing: str) -> str:
    """The whole question in plain text, ending with the closing sentence; the page adds pictures and no fact."""
    denial = permission_question.denial_paragraph(question.denial) if question.denial is not None else ""
    shown = f"{question.shown_label}: {question.shown}\n\n" if question.shown is not None else ""
    why = f"Why: {' -> '.join(question.why)}\n\n" if question.why else ""
    options = "\n".join(option.line() for option in question.options)
    recommendation = question.recommendation
    return (f"{QUESTION_PREFIX}{question.question}\n\n{question.found}\n\n{shown}{why}{denial}"
            f"Options, each with the worker's confidence in percent that it is the right answer:\n{options}\n\n"
            f"Recommended: {recommendation.name} ({recommendation.confidence}%).\n\n"
            f"Page: {page.as_uri()}\n\n{closing}")


@dataclass(frozen=True)
class Answer:
    """What a parked question got: the human's comments since it, or else the recommended option. `text` joins the
    comments; `replies` holds each of them apart."""
    source: str
    text: str
    replies: tuple[str, ...]

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
        return Answer(COMMENT, "\n\n".join(replies), tuple(replies))
    return Answer(RECOMMENDATION, recommended, (recommended,))


def park(task: str, tries: int, comment: str, metadata: list[tuple[str, str]], main_tree: Path) -> None:
    """Comments on the task and ends its lap parked, under the actor jidoka. The options and the recommendation of an
    earlier question come off, so the task does not show that question again."""
    env = env_as_factory()
    run(["bd", "comment", task, comment], main_tree, env)
    run(["bd", "update", task, f"--add-label={HUMAN_LABEL}", *lap_record.resting_with_tries(lap_record.PARKED, tries),
         *set_metadata(*metadata), *unset_metadata(*question_keys_unset_by(dict(metadata)))], main_tree, env)


def question_keys_unset_by(metadata: dict[str, str]) -> list[str]:
    """The question keys, options and recommendation, that a park setting `metadata` removes. A key the park sets
    itself stays."""
    return [key for key in (OPTIONS_KEY, RECOMMENDED_KEY) if key not in metadata]


def options_json_of(named: list[tuple[str, int | None]]) -> str:
    """The JSON that the `question.options` metadata of a bead holds for options given as a name and a confidence,
    which an answer with no confidence leaves out."""
    return json.dumps([{"name": name} if confidence is None else {"name": name, "confidence": confidence}
                       for name, confidence in named])


def options_json(options: tuple[AnyOption, ...]) -> str:
    """The options of a question as the JSON that the `question.options` metadata of a bead holds."""
    return options_json_of([(option.name, option.confidence) for option in options])


def write_page(task: str, question: Question, home: Path, main_tree: Path) -> Path:
    """Writes the question's page; raises QuestionError when the file cannot be written."""
    cards = tuple(option.card(option.name == question.recommended) for option in question.options)
    page = question_page.QuestionPage(task, question.question, question.found, question.shown_label, question.shown,
                                      question.why, cards)
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


def post_question(bead: str, question: Question, closing: str, extra: list[tuple[str, str]], resting: list[str],
                  home: Path, main_tree: Path) -> None:
    """Writes the question's page, comments the whole question on the bead with the closing sentence, and sets the
    options and the recommendation in its metadata beside `extra`. The bead gets the human label and `resting`, the
    arguments that put it at rest. Raises QuestionError when the page cannot be written."""
    page = write_page(bead, question, home, main_tree)
    env = env_as_factory()
    run(["bd", "comment", bead, question_comment(question, page, closing)], main_tree, env)
    run(["bd", "update", bead, f"--add-label={HUMAN_LABEL}", *resting,
         *set_metadata((OPTIONS_KEY, options_json(question.options)), (RECOMMENDED_KEY, question.recommended), *extra)],
        main_tree, env)


def park_epic_on_question(epic: str, question: Question, metadata: dict[str, str], home: Path,
                          main_tree: Path) -> None:
    """Parks the epic on the human with the question, and sets `metadata` beside the question's own."""
    closing = f"The epic stays parked while it carries the {HUMAN_LABEL} label."
    post_question(epic, question, closing, list(metadata.items()), [], home, main_tree)


def park_on_question(lap: AskingLap, home: Path, main_tree: Path) -> None:
    """Writes the lap's question page, posts its question report on the task and parks the task; raises
    QuestionError for a bad report or a page that cannot be written."""
    question = read_question(lap.scratch, lap.task)
    denial = question.denial or permission_question.Denial("", "")
    closing = (f"The worktree {lap.worktree} and the branch {lap.branch} keep the work. Take the {HUMAN_LABEL} label "
               "off to give the task a new lap.")
    post_question(lap.task, question, closing, [(CALL_KEY, denial.call), (PATTERN_KEY, denial.pattern)],
                  lap_record.resting_with_tries(lap_record.PARKED, lap.tries), home, main_tree)
    (lap.scratch / QUESTION_REPORT).unlink(missing_ok=True)


def denial_in(metadata: dict) -> permission_question.Denial | None:
    """The denial a task's metadata holds, or None when its last question was no permission question."""
    call, pattern = str(metadata.get(CALL_KEY) or ""), str(metadata.get(PATTERN_KEY) or "")
    return permission_question.Denial(call, pattern) if pattern else None


def answered_permission(task: str, home: Path, main_tree: Path) -> permission_question.Allowed:
    """Applies the answer of the task's permission question; raises QuestionError when there is none to apply."""
    shown = read_bead(task, main_tree)
    metadata = metadata_of(shown)
    denial = denial_in(metadata)
    if denial is None:
        raise QuestionError(f"the last question on {task} was no permission question")
    answer = answer_of(task, str(metadata.get(RECOMMENDED_KEY) or ""), main_tree)
    if answer is None:
        raise QuestionError(f"{task} holds no answered question")
    return permission_question.allow_answered(denial, answer.replies, parent_of(shown), home, main_tree)


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
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        if args.mode == "question":
            asked = AskingLap(args.task, args.tries, args.scratch, args.worktree, args.branch)
            park_on_question(asked, settings_reader.jidoka_home(args.jidoka_home), main_tree)
            printed = {"task": args.task, "parked": True}
        else:
            allowed = answered_permission(args.task, settings_reader.jidoka_home(args.jidoka_home), main_tree)
            printed = {"task": args.task, "list": allowed.chosen, "pattern": allowed.pattern,
                       "changed": allowed.changed}
    except (QuestionError, permission_question.AnswerError, rules.RulesError, CommandError,
            settings_reader.SettingsError, OSError) as error:
        print(f"park: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
