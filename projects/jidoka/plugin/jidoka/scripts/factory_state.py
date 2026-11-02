#!/usr/bin/env python3
"""Prints each epic the factory holds with its one factory state and the one next step the human can act on.

Run it from inside any checkout of the repo. It needs no host: it reads the beads through bd, the heartbeat
(heartbeat.py) and the watcher record (watcher_record.py) in the jidoka home, and changes nothing. One bd list gives
every epic and task with the labels and metadata that the states read, so the number of bd calls does not grow with
the epics. Only a bead that carries the human label costs one more call, for its comments. For each open epic with the
`factory` label it works out one of four states:
  running         the heartbeat is fresh and no watcher waits: a manager works the epic. Nothing to do.
  waiting         the heartbeat is fresh, a live watcher waits, and no bead waits on the human: the factory carries
                  on by itself at the end of its pause, on a new task, on a merged task or on room that frees.
  waiting-on-you  the epic carries the human label, as at the acceptance gate or after a question or a budget park,
                  or the heartbeat is fresh, a live watcher waits and a task carries it. Whether the factory goes on
                  by itself when the human answers is in the next step.
  stopped         the heartbeat is stale or missing and the epic waits on no label of its own: no manager runs it,
                  and only the human starts it again.
`waiting_on` lists each bead of the epic that carries the human label, the epic first and then its open tasks by id,
with `kind` and `text`, the reason it was put there:
  acceptance-gate  the epic waits at the acceptance gate.
  question         the factory's latest comment on the bead is a `Question:`; `text` is its sentence.
  parked           it is a `Parked:` comment, such as the budget's; `text` is the comment's first line.
  human            the label is on the bead and the factory posted no reason.
`wakes` is true when the epic has a live watcher whose record lists the bead among those it waits on, so that taking
the label off ends the watch and the manager goes on; a bead that was labeled after the watch began is not in the
record, and the watcher does not end on it. Nothing wakes a stopped epic.

`next_step` is {"action", "text", "command", "run_after", "wakes_at", "wakes_on_answer"}:
  action           `none` for a running epic, `wait` for a waiting one, `answer` for one that waits on you and
                   `restart` for a stopped one.
  text             the step in words.
  command          `/jidoka:factory` when the step ends with running it, else null.
  run_after        the second since the epoch before which a run of /jidoka:factory would only wait out the fresh
                   heartbeat, or null when the heartbeat is not fresh or the step runs nothing.
  wakes_at         the second the epic's pause ends when the epic is waiting on it, else null.
  wakes_on_answer  true when every bead that waits on the human wakes the factory when it is answered.

The JSON printed with --json is {"epics": [{"epic", "title", "state", "heartbeat_age_seconds", "watcher",
"waiting_on", "next_step"}]}, in epic-id order. Without --json it prints lines for a person. JIDOKA_NOW stands in for
the clock, as clock.py says. The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  success, including when the factory holds no epic.
  1  it could not read the beads, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

import clock
import heartbeat
import pause
import park
import settings_reader
import watcher_record
from commands import (COMMAND_TIMEOUT_SECONDS, FACTORY_LABEL, CommandError, NotAWholeNumber, bd_list,
                      is_labeled_for_human, labels_of, parent_of)
from epic_reader import EPIC_TYPE
from epics import at_the_gate, is_closed
from lap_outcomes import SchedulerError

class State(Enum):
    RUNNING = "running"
    WAITING = "waiting"
    WAITING_ON_YOU = "waiting-on-you"
    STOPPED = "stopped"

    @property
    def words(self) -> str:
        return self.value.replace("-on-", " on ")


class Action(Enum):
    NONE = "none"
    WAIT = "wait"
    ANSWER = "answer"
    RESTART = "restart"


class Kind(Enum):
    ACCEPTANCE_GATE = "acceptance-gate"
    QUESTION = "question"
    PARKED = "parked"
    HUMAN = "human"


RESTART_COMMAND = "/jidoka:factory"
ACCEPT_COMMAND = "/jidoka:accept"
CLOCK_FORMAT = "%H:%M:%S"
NO_REASON = "it carries the human label, and the factory posted no reason"
GATE_REASON = "the epic waits at the acceptance gate"


@dataclass(frozen=True)
class Waiting:
    """A bead that carries the human label, with why in the factory's words and whether taking the label off wakes
    the factory."""
    bead: str
    kind: Kind
    text: str
    wakes: bool


@dataclass(frozen=True)
class NextStep:
    """The one thing the human does for an epic, built by the constructor that names its action."""
    action: Action
    text: str
    command: str | None
    run_after: int | None
    wakes_at: int | None
    wakes_on_answer: bool

    @staticmethod
    def none(text: str) -> NextStep:
        return NextStep(action=Action.NONE, text=text, command=None, run_after=None, wakes_at=None,
                        wakes_on_answer=False)

    @staticmethod
    def wait(text: str, wakes_at: int | None) -> NextStep:
        return NextStep(action=Action.WAIT, text=text, command=None, run_after=None, wakes_at=wakes_at,
                        wakes_on_answer=False)

    @staticmethod
    def answer(text: str, wakes_on_answer: bool) -> NextStep:
        """An answer after which the human runs no command."""
        return NextStep(action=Action.ANSWER, text=text, command=None, run_after=None, wakes_at=None,
                        wakes_on_answer=wakes_on_answer)

    @staticmethod
    def answer_then_run(text: str, run_after: int | None) -> NextStep:
        """An answer that the human follows by running /jidoka:factory, after `run_after` when the heartbeat is
        fresh."""
        return NextStep(action=Action.ANSWER, text=text, command=RESTART_COMMAND, run_after=run_after,
                        wakes_at=None, wakes_on_answer=False)

    @staticmethod
    def restart(text: str) -> NextStep:
        return NextStep(action=Action.RESTART, text=text, command=RESTART_COMMAND, run_after=None, wakes_at=None,
                        wakes_on_answer=False)


@dataclass(frozen=True)
class EpicState:
    epic: str
    title: str
    state: State
    heartbeat_age_seconds: int | None
    watcher: bool
    waiting_on: tuple[Waiting, ...]
    next_step: NextStep


def seconds_until_stale(age_seconds: int) -> int:
    """How many seconds from now a heartbeat of this age is stale: the one past the last second it counts as fresh."""
    return heartbeat.FRESH_SECONDS - age_seconds + 1


def clock_time(seconds: int) -> str:
    return time.strftime(CLOCK_FORMAT, time.localtime(seconds))


def first_line(text: str) -> str:
    lines = text.splitlines()
    return lines[0].strip() if lines else ""


def reason_of(bead: str, main_tree: Path) -> tuple[Kind, str]:
    """The kind and the words of why the bead carries the human label, from the factory's latest park comment."""
    parked = park.latest_park(bead, main_tree)
    if parked is None:
        return Kind.HUMAN, NO_REASON
    return (Kind.QUESTION if parked.prefix == park.QUESTION_PREFIX else Kind.PARKED), first_line(parked.body)


def waiting_on(epic_shown: dict, tasks: list[dict], watched: frozenset[str], main_tree: Path) -> tuple[Waiting, ...]:
    """The epic, if it carries the human label, then each open task that does, by id."""
    epic = str(epic_shown["id"])
    held: list[Waiting] = []
    if is_labeled_for_human(epic_shown):
        if at_the_gate(epic_shown):
            kind, text = Kind.ACCEPTANCE_GATE, GATE_REASON
        else:
            kind, text = reason_of(epic, main_tree)
        held.append(Waiting(epic, kind, text, epic in watched))
    for task in sorted(tasks, key=lambda task: str(task["id"])):
        if is_labeled_for_human(task):
            kind, text = reason_of(str(task["id"]), main_tree)
            held.append(Waiting(str(task["id"]), kind, text, str(task["id"]) in watched))
    return tuple(held)


def request_of(item: Waiting, epic: str) -> str:
    if item.kind is Kind.ACCEPTANCE_GATE:
        return f"Decide at the acceptance gate: run {ACCEPT_COMMAND} {epic} to merge, send back or drop the epic"
    if item.kind is Kind.QUESTION:
        return f"Answer: {item.text}" if item.bead == epic else f"Answer {item.bead}: {item.text}"
    return f"Take the human label off {item.bead} once you have settled it: {item.text}"


def step_for_you(epic: str, held: tuple[Waiting, ...], fresh_age: int | None, now: int) -> NextStep:
    """What the human does for the beads that wait on them. The step lists the requests, then ends in one of three
    ways. Beads that all wait at the acceptance gate end it with the request, which names its own command. Beads
    whose answer wakes the factory say that it does. Any other bead tells the human to run /jidoka:factory after the
    answer, once the heartbeat goes stale if it is fresh."""
    requests = "; ".join(request_of(item, epic) for item in held)
    wakes = all(item.wakes for item in held)
    if all(item.kind is Kind.ACCEPTANCE_GATE for item in held):
        return NextStep.answer(f"{requests}.", wakes)
    if wakes:
        return NextStep.answer(f"{requests}. Answering wakes the factory by itself.", True)
    run_after = None if fresh_age is None else now + seconds_until_stale(fresh_age)
    after = "" if run_after is None else f" after {clock_time(run_after)}"
    return NextStep.answer_then_run(f"{requests}, then run {RESTART_COMMAND}{after}.", run_after)


def step_for_a_stopped_epic(held: tuple[Waiting, ...]) -> NextStep:
    kept = "".join(f" {item.bead} stays parked until you answer: {item.text}." for item in held)
    return NextStep.restart(f"Run {RESTART_COMMAND} to start the manager again.{kept}")


def step_for_a_waiting_epic(shown: dict, now: int) -> NextStep:
    held_pause = pause.waiting_at(shown, now)
    sooner = "on a new task, a merged task or room freed by another epic"
    if held_pause is None:
        return NextStep.wait(f"Nothing to do. The factory wakes by itself {sooner}.", None)
    return NextStep.wait(f"Nothing to do. The factory wakes by itself at {clock_time(held_pause.until)} when its "
                         f"pause ends, and sooner {sooner}.", held_pause.until)


def state_of_epic(shown: dict, tasks: list[dict], home: Path, main_tree: Path, now: int) -> EpicState:
    """The state of the epic, from the epic and its open tasks as bd lists them."""
    epic = str(shown["id"])
    fresh_age = heartbeat.fresh_age_seconds(home, epic, now)
    record = watcher_record.live_watcher(home, epic)
    listed = record.waits_for.parked if record is not None else frozenset()
    has_manager = fresh_age is not None
    stopped = not has_manager and not is_labeled_for_human(shown)
    held = waiting_on(shown, tasks, frozenset() if stopped else listed, main_tree)
    task_waits = record is not None and has_manager and any(is_labeled_for_human(task) for task in tasks)
    if is_labeled_for_human(shown) or task_waits:
        state, step = State.WAITING_ON_YOU, step_for_you(epic, held, fresh_age, now)
    elif stopped:
        state, step = State.STOPPED, step_for_a_stopped_epic(held)
    elif record is not None:
        state, step = State.WAITING, step_for_a_waiting_epic(shown, now)
    else:
        state, step = State.RUNNING, NextStep.none("Nothing to do. The factory is running.")
    return EpicState(epic, str(shown.get("title") or ""), state, heartbeat.beat_age_seconds(home, epic, now),
                     record is not None, held, step)


def states(home: Path, main_tree: Path, now: int) -> list[EpicState]:
    listed = [item for item in bd_list(["--all", "--limit", "0"], main_tree) if item.get("id") and not is_closed(item)]
    held = sorted((item for item in listed if item.get("issue_type") == EPIC_TYPE and FACTORY_LABEL in labels_of(item)),
                  key=lambda epic: str(epic["id"]))
    open_tasks: dict[str, list[dict]] = {}
    for item in listed:
        if item.get("issue_type") != EPIC_TYPE:
            open_tasks.setdefault(parent_of(item), []).append(item)
    return [state_of_epic(epic, open_tasks.get(str(epic["id"]), []), home, main_tree, now) for epic in held]


def lines_of(held: list[EpicState]) -> str:
    if not held:
        return "no epic is in the factory"
    sections = []
    for item in held:
        beat = "no heartbeat" if item.heartbeat_age_seconds is None else f"heartbeat {item.heartbeat_age_seconds}s ago"
        lines = [f"{item.epic}  {item.title} [{item.state.words}]",
                 f"  {beat}, {'a watcher waits' if item.watcher else 'no watcher'}"]
        lines += [f"  waits on you: {waiting.bead} ({waiting.kind.value}): {waiting.text}" for waiting in item.waiting_on]
        lines.append(f"  next: {item.next_step.text}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="factory_state.py", description="Print each epic's factory state and the "
                                                                           "next step.")
    parser.add_argument("--json", action="store_true", help="print JSON instead of lines for a person")
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        held = states(settings_reader.jidoka_home(args.jidoka_home), main_tree, clock.now())
    except (SchedulerError, NotAWholeNumber, CommandError,
            settings_reader.SettingsError, OSError) as error:
        print(f"factory_state: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"epics": [asdict(item) for item in held]}, default=lambda value: value.value)
          if args.json else lines_of(held))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
