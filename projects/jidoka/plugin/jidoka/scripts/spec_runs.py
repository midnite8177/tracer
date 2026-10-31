"""The runs of a task's acceptance specs that a task's metadata records, and what the merge gate asks of them.

A task that makes acceptance specs pass (specs.py records them) owes two runs of exactly those specs. The red run is
the build worker's, made before it writes code: every spec is run, a spec that fails carries the failure the worker
expected, and a spec that already passes is recorded as passing, which the gate comment and the gate page list under
"Acceptance specs that passed before the build" (gate_items.py). The green run is the scheduler's, made on the lap's
head before the merge gate: every spec must pass there. Both are the task's metadata, a JSON object `{"head", "runs"}`
with the commit the run was made on and one `{"spec", "passed", "expected"}` for each spec, under `acceptance.red` and
`acceptance.green`. A task that makes no spec pass owes neither.

`refusal` is what the merge gate asks: it says why a lap's runs do not support the merge, or gives nothing. The module
runs no spec; run_specs.py runs them and writes these records.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import specs
from commands import env_as_factory, metadata_of, run, set_metadata

RED_KEY = "acceptance.red"
GREEN_KEY = "acceptance.green"


class SpecRunsError(Exception):
    """A record of spec runs that cannot be read or written, worded for the person who reads stderr."""


@dataclass(frozen=True)
class SpecResult:
    """One spec's result in a run, and for a red run that failed the failure the build worker expected."""
    spec: str
    passed: bool
    expected: str


@dataclass(frozen=True)
class RecordedRun:
    """A run of a task's specs as the task records it: the commit it was made on and a result for each spec."""
    head: str
    results: list[SpecResult]

    def encoded(self) -> str:
        return json.dumps({"head": self.head, "runs": [{"spec": each.spec, "passed": each.passed,
                                                        "expected": each.expected} for each in self.results]},
                          separators=(",", ":"), ensure_ascii=False)

    def missing(self, names: list[str]) -> list[str]:
        """The names the run holds no result for."""
        held = {each.spec for each in self.results}
        return [name for name in names if name not in held]

    def not_passing(self) -> list[str]:
        return [each.spec for each in self.results if not each.passed]


def parsed(shown: dict, key: str) -> RecordedRun | None:
    """The run the bead records under the key, none when it records none; raises SpecRunsError when the record is not a
    run."""
    stored = metadata_of(shown).get(key)
    if stored is None or stored == "":
        return None
    try:
        record = json.loads(stored) if isinstance(stored, str) else stored
        results = [SpecResult(entry["spec"], entry["passed"], entry["expected"]) for entry in record["runs"]]
        head = record["head"]
        if (isinstance(head, str) and head
                and all(isinstance(each.spec, str) and isinstance(each.passed, bool)
                        and isinstance(each.expected, str) for each in results)):
            return RecordedRun(head, results)
    except (ValueError, KeyError, TypeError):
        pass
    raise SpecRunsError(f"{key} of {shown.get('id')} is not a run of the task's specs. Run the specs again with "
                        f"run_specs.py --record")


def red_run_of(shown: dict) -> RecordedRun | None:
    return parsed(shown, RED_KEY)


def green_run_of(shown: dict) -> RecordedRun | None:
    return parsed(shown, GREEN_KEY)


def passed_before_the_build(shown: dict) -> list[str]:
    """The specs the task's red run found already passing, none when it records no red run or cannot be read."""
    try:
        red = red_run_of(shown)
    except SpecRunsError:
        return []
    return [each.spec for each in red.results if each.passed] if red is not None else []


def record(key: str, task: str, made: RecordedRun, main_tree: Path) -> None:
    """Records the run on the task under the actor jidoka."""
    run(["bd", "update", task, *set_metadata((key, made.encoded()))], main_tree, env_as_factory())


def listed(names: list[str]) -> str:
    return "; ".join(names)


def red_refusal(owed: list[str], red: RecordedRun | None) -> str | None:
    if red is None:
        return (f"no red run of the task's specs is recorded, and the build runs them before it writes code: "
                f"{listed(owed)}")
    unrun = red.missing(owed)
    if unrun:
        return f"the red run records no result for these specs of the task: {listed(unrun)}"
    unexplained = [each.spec for each in red.results if not each.passed and not each.expected.strip()]
    if unexplained:
        return f"the red run records no expected failure for: {listed(unexplained)}"
    return None


def green_refusal(owed: list[str], green: RecordedRun | None, lap_head: str) -> str | None:
    if green is None or green.head != lap_head:
        return (f"the task's specs are not recorded green on the lap's head {lap_head}: "
                f"{listed(owed)}")
    unrun = green.missing(owed)
    if unrun:
        return f"the green run records no result for these specs of the task: {listed(unrun)}"
    failing = green.not_passing()
    if failing:
        return f"the task's specs are not green on the lap's head {lap_head}: {listed(failing)}"
    return None


def refusal(task: dict, lap_head: str) -> str | None:
    """Why the task's recorded runs do not support merging the lap at lap_head, or None when they do or the task makes
    no spec pass."""
    try:
        owed = specs.specs_of(task)
        if not owed:
            return None
        return red_refusal(owed, red_run_of(task)) or green_refusal(owed, green_run_of(task), lap_head)
    except (specs.SpecsError, SpecRunsError) as error:
        return str(error)
