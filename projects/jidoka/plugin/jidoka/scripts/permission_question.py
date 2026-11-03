"""The words of a permission question and the reading of its answer.

A permission question is a question about a call the lap mod denied. park.py
reads the worker's report and posts the question; this module owns what is
particular to the permission question: the Denial it is about and what makes a
report's call, pattern and cause a denial, the four answers (the three lists
and `none`), the sentence, situation line, diagram steps and option cards that
jidoka writes from the denial in words that need no jidoka vocabulary, and the
reading of the answer that puts the pattern on a list. The page names the
denied call wherever it tells of it; the comment names it once, in its denial
paragraph, and calls it "the call" everywhere else. The wording is plain
functions of a denial, with no repo and no bd. Only `allow` writes, and it
writes through rules.py and repo_settings.py.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

import question_page
import repo_settings
import rules

EPIC_LIST, REPO_LIST, BUILT_IN_LIST = "epic", "repo", "built-in"
NO_LIST = "none"
PERMISSION_LISTS = (EPIC_LIST, REPO_LIST, BUILT_IN_LIST)
PERMISSION_ANSWERS = (*PERMISSION_LISTS, NO_LIST)
LIST_WORD = re.compile(rf"^\W*({'|'.join(re.escape(name) for name in PERMISSION_LISTS)})(?![\w-])", re.IGNORECASE)
OFF_LISTS, OUTSIDE_WORKTREE, UNREADABLE_DELETE = "off-lists", "outside-worktree", "unreadable-delete"
CAUSES = (OFF_LISTS, OUTSIDE_WORKTREE, UNREADABLE_DELETE)
DELETE_CAUSES = (OUTSIDE_WORKTREE, UNREADABLE_DELETE)
SITUATION_LABEL = "What happened"
SHELL_SYNTAX = re.compile(r"[;&|<>`\n]|\$\(")


class AnswerError(Exception):
    """A reason an answer cannot be applied, worded for the human who wrote it."""


class DenialError(Exception):
    """A reason a report's call, pattern and cause are no denial, worded for the worker that writes the next report."""


@dataclass(frozen=True)
class Denial:
    """The call the lap mod denied, and the command prefix whose entry on a list would allow it."""
    call: str
    pattern: str


@dataclass(frozen=True)
class Denied:
    """A denial and its cause, one of CAUSES: the reason the lap mod gave for it."""
    denial: Denial
    cause: str


@dataclass(frozen=True)
class PermissionOption:
    """The option of a permission question that chooses one list. Its name is the answer word the human types.
    `next_step` is what happens next in the comment's words, `page_next_step` the same naming the call, `change` is the
    change the list makes, and `reason` is the worker's reasoning for its pick, held by the recommended option and None
    on any other."""
    name: str
    confidence: int
    next_step: str
    page_next_step: str
    change: str
    reason: str | None

    def line(self) -> str:
        """The option as one line of the question's comment."""
        reason = f" The worker picks it because: {self.reason}" if self.reason is not None else ""
        return f"- {self.change} ({self.confidence}%). Answer word: {self.name}. {self.next_step}{reason}"

    def card(self, recommended: bool) -> question_page.Card:
        """The option as a card of the question's page."""
        return question_page.Card(self.change, self.name, self.confidence, self.page_next_step, self.reason,
                                  recommended)


def pattern_start(wanted: list[str], spoken: list[str]) -> int | None:
    """Where the words of the pattern begin in the words of the call, or None when they do not appear in a row."""
    return next((start for start in range(len(spoken)) if spoken[start:start + len(wanted)] == wanted), None)


def words_of(command: str, what: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError as error:
        raise DenialError(f"{what} {command!r} is not a command: {error}") from error


def denied_in(call: str, pattern: str, cause: str, option_names: list[str]) -> Denied:
    """The denial a permission question's report describes; raises DenialError when the cause is none of CAUSES, the
    options are not exactly the four answers, or the pattern is not one simple command whose words appear in the
    call."""
    if cause not in CAUSES:
        raise DenialError(f"cause must be one of {', '.join(CAUSES)}, not {cause!r}")
    if sorted(option_names) != sorted(PERMISSION_ANSWERS):
        raise DenialError(f"the options of a permission question must be the four answers, one each: "
                          f"{', '.join(PERMISSION_ANSWERS)}")
    if SHELL_SYNTAX.search(pattern):
        raise DenialError("pattern must be one simple command, with no separator, redirect or substitution")
    if pattern_start(words_of(pattern, "pattern"), words_of(call, "call")) is None:
        raise DenialError("the words of pattern must appear in call, one after the other")
    return Denied(Denial(call, pattern), cause)


def sentence_of(denial: Denial) -> str:
    """The question, in one sentence."""
    return f"May lap workers run {denial.pattern}?"


def rule_of(denied: Denied) -> str:
    """The rule that stopped the call, as a clause."""
    rules_by_cause = {
        OFF_LISTS: f"workers may not run {denied.denial.pattern}",
        OUTSIDE_WORKTREE: "workers may delete only inside their worktree",
        UNREADABLE_DELETE: "workers may delete only paths they name one by one inside their worktree",
    }
    return rules_by_cause[denied.cause]


def targets_of(denial: Denial) -> list[str]:
    """The words after the pattern in the call that are no flag, up to the first shell separator, redirect or
    substitution."""
    wanted, spoken = shlex.split(denial.pattern), shlex.split(denial.call)
    start = pattern_start(wanted, spoken)
    if start is None:
        return []
    targets = []
    for word in spoken[start + len(wanted):]:
        syntax = SHELL_SYNTAX.search(word)
        head = word[:syntax.start()] if syntax else word
        if head and not head.startswith("-"):
            targets.append(head)
        if syntax:
            break
    return targets


def situation(denied: Denied, attempt_without_paths: str) -> str:
    """What the worker tried and the rule that stopped it, so the task stopped, in plain words."""
    targets = targets_of(denied.denial) if denied.cause in DELETE_CAUSES else []
    attempt = f"delete {' '.join(targets)} with {denied.denial.pattern}" if targets else attempt_without_paths
    rule = rule_of(denied)
    return f"The worker tried to {attempt}. {rule[0].upper()}{rule[1:]}, so the task stopped."


def situation_on_page(denied: Denied) -> str:
    return situation(denied, f"run `{denied.denial.call}`")


def situation_in_comment(denied: Denied) -> str:
    """The situation line of the comment, which tells the call by its pattern."""
    return situation(denied, f"run {denied.denial.pattern}")


def denial_steps(task: str, denied: Denied, call_step: str) -> tuple[str, ...]:
    return (f"The worker was building {task}",
            call_step,
            f"The call was denied, because {rule_of(denied)}",
            "The task is parked and waits for your answer")


def steps_on_page(task: str, denied: Denied) -> tuple[str, ...]:
    return denial_steps(task, denied, f"It made the call {denied.denial.call}")


def steps_in_comment(task: str, denied: Denied) -> tuple[str, ...]:
    """The steps of the diagram as the comment's Why chain, which tells the call by its pattern."""
    return denial_steps(task, denied, f"It made a call that runs {denied.denial.pattern}")


def permission_option(name: str, confidence: int, denial: Denial, reason: str | None) -> PermissionOption:
    """The option with the change its list makes and what the worker does next with the denied call, both written
    here from the denial; the worker's own `next` is dropped, for it cannot know what the list does. `reason` is the
    worker's reasoning, kept on the option only when it is the recommended one."""
    change, page_next_step = changes_of(denial.pattern, f"`{denial.call}`")[name]
    _, next_step = changes_of(denial.pattern, "the call")[name]
    return PermissionOption(name, confidence, next_step, page_next_step, change, reason)


def changes_of(pattern: str, call: str) -> dict[str, tuple[str, str]]:
    """The change each answer makes, and what the worker does next with the call, which `call` words."""
    return {
        EPIC_LIST: (f"Only the workers on this group of tasks may run {pattern}",
                    f"The worker starts again and runs {call}. Workers on other groups of tasks are still refused "
                    f"{pattern}."),
        REPO_LIST: (f"Every worker in this repo may run {pattern}",
                    f"The worker starts again and runs {call}, and so does every later worker in this repo, whatever "
                    "its group of tasks."),
        BUILT_IN_LIST: (f"Every worker in every repo on this machine may run {pattern}",
                        f"The worker starts again and runs {call}, and so does every later worker in every repo on "
                        "this machine."),
        NO_LIST: (f"Nothing changes, and no worker may run {pattern}",
                  f"The worker starts again with every permission as it was, so {call} is still refused. It reads "
                  "your comment and carries on without it."),
    }


def denial_paragraph(denial: Denial) -> str:
    """The paragraph of the question's comment that tells the human how to answer."""
    return (f"The call `{denial.call}` was denied. Open your comment with the answer word of the one list that "
            f"should allow `{denial.pattern}` from now on, or with none to change no list. Anything after the word "
            "is your comment to the worker.\n\n")


def list_named(replies: tuple[str, ...]) -> str:
    """The one list the replies name, or `none` when they name no list. A reply names a list when it opens with the
    list's name, and what follows is a comment to the worker; raises AnswerError when replies open with the names of
    more than one list."""
    named = {match.group(1).lower() for reply in replies if (match := LIST_WORD.match(reply))}
    if len(named) > 1:
        text = "\n\n".join(replies)
        raise AnswerError(f"the answer must name at most one list of {', '.join(PERMISSION_LISTS)}, and "
                          f"{text!r} names {len(named)}")
    return named.pop() if named else NO_LIST


@dataclass(frozen=True)
class Allowed:
    """The list a permission answer chose, the pattern, and whether the list changed."""
    chosen: str
    pattern: str
    changed: bool


def allow(chosen: str, pattern: str, epic: str, home: Path, main_tree: Path) -> bool:
    """Adds the pattern to the chosen list; False when the list already holds it or the answer chose no list."""
    if chosen == NO_LIST:
        return False
    if chosen == EPIC_LIST:
        return rules.allow_extra_command(epic, pattern, home, main_tree)
    if chosen == REPO_LIST:
        return repo_settings.add_worker_command(home, main_tree, pattern)
    return repo_settings.add_built_in_command(home, pattern)


def allow_answered(denial: Denial, replies: tuple[str, ...], epic: str, home: Path, main_tree: Path) -> Allowed:
    """Puts the denial's pattern on the list the replies name, so the next lap's mod allows the call."""
    chosen = list_named(replies)
    return Allowed(chosen, denial.pattern, allow(chosen, denial.pattern, epic, home, main_tree))
