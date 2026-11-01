"""The acceptance specs of a validation: which specs an epic's validation runs, and the run of them side by side.

The specs are the ones the epic's tasks record, those they make pass and those planning marked as already true, each
under the app that the task records beside them, because the spec command cannot list the specs it holds. A spec that two
tasks record runs once. Each spec runs alone, as run_specs.py runs a named spec, in the validation worktree.

`specs_to_run` plans the run from the epic's beads and the repo settings, and refuses what cannot run, so that
validation asks for it before its suite and not after. `run_all` runs a plan.

The specs run on the slots that no other running epic holds, at least one, as slots.py says, and never more at once
than those slots. Each running spec has a slot of its own, which it learns from the environment variable JIDOKA_SLOT,
so that the protocol driver turns it into what the repo settings' `slot_use` says, such as a port, and two specs side
by side never clash. The run holds the slots and gives them back after it, even when a run raises.
"""
from __future__ import annotations

import queue
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import clock
import epic_reader
import rules
import run_specs
import settings_reader
import slots
import spec_commands
import specs
from commands import read_bead
from pass_support import PassError

SLOT_VARIABLE = "JIDOKA_SLOT"

class SpecsRunError(PassError):
    """A reason the specs of a validation cannot be run, worded for the person who reads stderr."""


@dataclass(frozen=True)
class SpecToRun:
    """One spec, the app it belongs to and the command line that runs it alone."""
    app: str
    name: str
    command: str


@dataclass(frozen=True)
class TimedSpecRun:
    """The result of running one spec: its app and name, whether it passed, what it printed, and the moments it started
    and ended on the monotonic clock, which place it in the run beside the other specs."""
    app: str
    name: str
    passed: bool
    output: str
    started: float
    ended: float

    @property
    def seconds(self) -> float:
        return round(self.ended - self.started, 3)


@dataclass(frozen=True)
class SpecFigures:
    """What a run of the specs counted and how long it took from its first spec starting to its last one ending."""
    count: int
    seconds: float


def elapsed(runs: list[TimedSpecRun]) -> float:
    """The seconds from the first of the runs starting to the last one ending; none for no runs."""
    return max(each.ended for each in runs) - min(each.started for each in runs) if runs else 0.0


@dataclass(frozen=True)
class SpecsRun:
    """The run of an epic's acceptance specs: each spec's result. The run's time, and each app's own part of it, run
    from the first of the specs starting to the last one ending."""
    runs: list[TimedSpecRun]

    @property
    def passed(self) -> bool:
        return all(each.passed for each in self.runs)

    @property
    def failed(self) -> list[TimedSpecRun]:
        return [each for each in self.runs if not each.passed]

    @property
    def seconds(self) -> float:
        return elapsed(self.runs)

    def seconds_of(self, app: str) -> float:
        """How long the app's part of the run took, whatever the other apps' specs ran beside it."""
        return elapsed([each for each in self.runs if each.app == app])

    def slowest_of(self, app: str, count: int) -> list[TimedSpecRun]:
        """The app's specs that took longest, the slowest first, at most `count` of them."""
        mine = [each for each in self.runs if each.app == app]
        return sorted(mine, key=lambda each: each.seconds, reverse=True)[:count]

    @property
    def figures(self) -> SpecFigures:
        return SpecFigures(len(self.runs), round(self.seconds, 3))


NO_SPECS = SpecsRun([])


def recorded_specs(epic: str, main_tree: Path) -> dict[str, list[str]]:
    """The spec names the epic's tasks record, by the name of the app they are recorded under, in the order the tasks
    are read."""
    try:
        found = epic_reader.read_epic(read_bead(epic, main_tree), main_tree)
        by_app: dict[str, list[str]] = {}
        for task in found.task_beads:
            names = [*specs.specs_of(task), *specs.already_true_of(task)]
            app = specs.app_of(task)
            if names:
                by_app.setdefault(app, []).extend(names)
        return {app: specs.named_specs(names) for app, names in by_app.items()}
    except specs.SpecsError as error:
        raise SpecsRunError(str(error)) from error


def specs_to_run(epic: str, settings: settings_reader.Settings, main_tree: Path) -> list[SpecToRun]:
    """Every spec the epic records, with the command that runs it; raises SpecsRunError for a spec of an app that the
    repo settings do not list or that has no way to run one spec."""
    jobs = []
    for name, listed in recorded_specs(epic, main_tree).items():
        try:
            app = settings.app_named(name)
            jobs += [SpecToRun(name, spec, spec_commands.command_for_one(app, spec))
                     for spec in listed]
        except (settings_reader.SettingsError, spec_commands.SpecCommandError) as error:
            raise SpecsRunError(str(error)) from error
    return jobs


def run_one(job: SpecToRun, slot: int, worktree: Path) -> TimedSpecRun:
    print(f"running spec: {job.name}", file=sys.stderr, flush=True)
    started = time.monotonic()
    done = run_specs.run_command(job.name, f"export {SLOT_VARIABLE}={slot}; {job.command}", worktree)
    return TimedSpecRun(job.app, job.name, done.passed, done.output, started, time.monotonic())


def run_on_a_free_slot(job: SpecToRun, free: queue.SimpleQueue[int], worktree: Path) -> TimedSpecRun:
    """Runs the spec on a slot taken from `free`, and puts the slot back when the spec is done."""
    slot = free.get()
    try:
        return run_one(job, slot, worktree)
    finally:
        free.put(slot)


def run_all(jobs: list[SpecToRun], epic: str, worktree: Path, home: Path, main_tree: Path) -> SpecsRun:
    """Runs the jobs in the worktree, side by side on the slots the machine has free, one spec to a slot, and prints the
    output of each failed spec to stderr."""
    if not jobs:
        return NO_SPECS
    held = slots.hold_free(slots.Standing(home, epic, main_tree, rules.machine_lap_limit(home), clock.now()))
    try:
        free: queue.SimpleQueue[int] = queue.SimpleQueue()
        for slot in held:
            free.put(slot)
        with ThreadPoolExecutor(max_workers=len(held)) as pool:
            finished = SpecsRun(list(pool.map(lambda job: run_on_a_free_slot(job, free, worktree), jobs)))
    finally:
        slots.release(home, epic)
    for each in finished.failed:
        print(f"failed spec: {each.name}\n{each.output}", file=sys.stderr, flush=True)
    return finished
