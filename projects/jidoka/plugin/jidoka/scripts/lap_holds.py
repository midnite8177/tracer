"""What holds the laps of an epic in one call of the scheduler: the human label, a pause that waits, a budget or a
seven-day reserve that parks the epic, and the brake.

`apply_holds` is the one entry point. `decision_of` works out, from the epic and its laps and with no side effect, which
laps stop, start again or stay open and whether the epic parks, and `apply_holds` carries the decision out: it prints,
interrupts laps, restarts wall clocks, reads the brake and parks the epic. The human label on the epic or on a task
keeps a lap from starting again. A pause that waits, a reached budget and a seven-day window past its reserve end the
laps that would start again interrupted, and the epic parks once none of its stages runs.
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import budget
import caps
import lap_record
import notify
import pause
import reserves
from commands import HUMAN_LABEL, env_as_factory, run
from epic_reader import Epic
from epics import state_of
from lap_record import Lap
from lap_stages import interrupt_lap

SCRIPT = "scheduler"


@dataclass(frozen=True)
class Parking:
    """Why the epic starts no new stage and parks once none runs: what it reached, in words that follow the epic's id,
    when its laps start again, and how it parks."""
    reason: str
    resumes_when: str
    park: Callable[[], None]


@dataclass(frozen=True)
class Standstill:
    """What keeps the epic from starting a stage in this call: a pause that waits, or a reached budget or a passed
    seven-day reserve that parks it once no stage runs."""
    waiting: pause.Pause | None
    parking: Parking | None

    @property
    def is_on(self) -> bool:
        return self.waiting is not None or self.parking is not None


@dataclass(frozen=True)
class Holds:
    """What holds the epic's laps in this call: the laps that start again, the laps still open, the standstill, the
    brake, and whether the epic carries the human label."""
    rebuilds: list[Lap]
    held: list[Lap]
    standstill: Standstill
    brake: caps.Brake
    epic_parked: bool

    @property
    def waiting(self) -> pause.Pause | None:
        return self.standstill.waiting

    def lets_open(self, task: str, resumed: set[str]) -> bool:
        """Whether a ready task may get a lap: not while the epic is parked or at a standstill, and with the brake on
        only a task whose lap this call ended, named in `resumed`."""
        if self.epic_parked or self.standstill.is_on:
            return False
        return not self.brake.is_on or task in resumed


@dataclass(frozen=True)
class Decision:
    """What the holds do to the laps, worked out with no side effect: the laps the human label keeps from starting,
    the laps that start again, the laps a standstill ends instead, the laps that stay open, and whether the epic parks
    now, which it does at a standstill that parks it once no lap stays open."""
    epic_parked: bool
    stopped: list[Lap]
    starting: list[Lap]
    interrupted: list[Lap]
    held: list[Lap]
    parks: bool


def is_parked(epic: Epic) -> bool:
    """The epic carries the human label, the human's brake, so no stage starts and no lap opens."""
    return state_of(epic.shown).labeled_for_human


def parking_of(epic: Epic, reading: reserves.Reading | None, now: int, home: Path,
               main_tree: Path) -> Parking | None:
    """The parking that holds the epic: its budget when reached, else its seven-day reserve when passed."""
    reached = budget.reached_by(epic.shown, home)
    if reached is not None:
        return Parking(reached.reason, budget.RESUMES_WHEN, lambda: park_at_the_budget(epic, reached, home, main_tree))
    window = reserves.seven_day_past_reserve(epic.shown, reading, now)
    if window is not None:
        return Parking(window.reason, reserves.RESUMES_WHEN,
                       lambda: park_at_the_reserve(epic, window, now, home, main_tree))
    return None


def restart_clock(lap: Lap, now: int, main_tree: Path) -> Lap:
    """A stage that reruns starts its wall clock again."""
    restarted, arguments = lap_record.restarting_clock(lap, now)
    run(["bd", "update", lap.task, *arguments], main_tree, env_as_factory())
    return restarted


def decision_of(epic: Epic, held: list[Lap], rebuilds: list[Lap], standstill: Standstill) -> Decision:
    """Which of the laps that would start again are stopped by the human label, start, or are ended by a standstill,
    which laps stay open, and whether the epic parks. The human label, on the epic or on a task, keeps a lap from
    starting again, and a standstill ends the laps that would start again interrupted."""
    labeled = epic.labeled_task_ids
    epic_parked = is_parked(epic)
    stopped = [lap for lap in rebuilds if epic_parked or lap.task in labeled]
    starting = [lap for lap in rebuilds if lap not in stopped]
    interrupted = starting if standstill.is_on else []
    starting = [] if standstill.is_on else starting
    staying = [lap for lap in held if lap not in interrupted]
    parks = standstill.parking is not None and not staying
    return Decision(epic_parked, stopped, starting, interrupted, staying, parks)


def apply_holds(epic: Epic, held: list[Lap], rebuilds: list[Lap], standstill: Standstill, now: int,
                home: Path, main_tree: Path) -> Holds:
    """Carries out what holds the epic's laps: says why, interrupts the laps a standstill ends, starts the wall clock
    again of the laps that go on, reads the brake, and parks the epic when the decision says it parks. The brake holds
    only the laps that have not opened."""
    decision = decision_of(epic, held, rebuilds, standstill)
    if decision.epic_parked:
        print(f"scheduler: {epic.id} carries the {HUMAN_LABEL} label, so no stage starts and no lap opens until it "
              "is taken off. The stages already running finish", file=sys.stderr)
    for lap in decision.stopped:
        print(f"scheduler: {lap.task} waits at the {lap.stage} for the {HUMAN_LABEL} label to come off, so no stage "
              "starts on it", file=sys.stderr)
    waiting, parking = standstill.waiting, standstill.parking
    interruption = None
    if waiting is not None:
        print(f"scheduler: {epic.id} is paused on {pause.WORDS[waiting.cause]} for {waiting.until - now} more "
              "seconds, so no stage starts and no lap opens until then", file=sys.stderr)
        interruption = (f"the factory paused on {pause.WORDS[waiting.cause]}", "the factory goes on after the pause")
    elif parking is not None:
        interruption = (f"{epic.id} {parking.reason}", parking.resumes_when)
    if interruption is not None:
        because, resumes_when = interruption
        for lap in decision.interrupted:
            interrupt_lap(lap, f"{because} before the {lap.stage} could start again", resumes_when, main_tree)
    if waiting is not None:
        notify.announce(notify.FACTORY_PAUSED, epic.id, home, main_tree, SCRIPT)
    starting = [restart_clock(lap, now, main_tree) for lap in decision.starting]
    brake = caps.brake_after_new_beads(epic.shown, [str(child["id"]) for child in epic.children], main_tree)
    if brake.is_on:
        print(f"scheduler: {brake.laps} laps in a row parked at the {brake.stage} with no merge between, so no new "
              f"lap opens until a fix task is filed in {epic.id}. The laps already open run on", file=sys.stderr)
    if decision.parks and parking is not None:
        parking.park()
    return Holds(starting, decision.held, standstill, brake, decision.epic_parked)


def park_at_the_budget(epic: Epic, reached: budget.Reached, home: Path, main_tree: Path) -> None:
    """Parks the epic whose budget is reached, now that no stage of it runs, and tells the human."""
    print(f"scheduler: {epic.id} spent ${reached.spent:.2f} of its budget of ${reached.budget:.2f}, so no stage "
          "starts and it is parked", file=sys.stderr)
    budget.park_epic_at(epic.id, reached, main_tree)
    notify.announce(notify.EPIC_PARKED, epic.id, home, main_tree, SCRIPT)


def park_at_the_reserve(epic: Epic, window: reserves.Window, now: int, home: Path, main_tree: Path) -> None:
    """Parks the epic whose seven-day window is past its reserve, now that no stage of it runs, asks the human, and
    tells the human."""
    print(f"scheduler: {epic.id} is on an account whose {window.name} window is {window.used_percent:g}% used, past "
          "its reserve, so no stage starts and it is parked with a question", file=sys.stderr)
    reserves.park_epic_at(epic.id, window, now, home, main_tree)
    notify.announce(notify.EPIC_PARKED, epic.id, home, main_tree, SCRIPT)
