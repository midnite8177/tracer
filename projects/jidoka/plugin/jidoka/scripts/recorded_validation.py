"""The record a validation leaves on its epic, with the one writer and the one reader of it.

A `RecordedValidation` is the result, the validated head, each command's run, the figures of the acceptance specs and
the specs that ran over their app's time limit. `metadata` and `comment_lines` write it, `read` reads it back from the
epic's metadata, `validated_head` reads the head alone, and `result_metadata` writes the result alone, as settling the holdouts does. A figure added to the
record is added here.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import spec_time_limit
from commands import set_metadata, unset_metadata
from full_suite import CommandRun
from pass_support import PassError
from settings_reader import SuiteCommand
from spec_time_limit import OverTheLimit
from validation_specs import SpecFigures

RESULT_KEY = "validation.result"
VALIDATED_HEAD_KEY = "validation.head"
RUNS_KEY = "validation.runs"
SPECS_KEY = "validation.specs"
SPEC_SECONDS_KEY = "validation.spec_seconds"
SLOW_SPECS_KEY = "validation.slow_specs"


class RecordError(PassError):
    """A reason the validation an epic records cannot be read, worded for the person who reads stderr."""


def runs_of(value: object) -> list[CommandRun]:
    """The runs a validation recorded on the epic, without their output."""
    try:
        listed = json.loads(value) if isinstance(value, str) else value
        return [CommandRun(SuiteCommand(str(each["app"]), str(each["command"])), int(each["exit_code"]),
                           float(each["seconds"]), None if each["tests"] is None else int(each["tests"]),
                           int(each["skipped"]), "") for each in listed]
    except (ValueError, KeyError, TypeError) as error:
        raise RecordError(f"the {RUNS_KEY} metadata of the epic cannot be read: {error!r}") from error


def run_fields(run: CommandRun) -> dict:
    """The entry that the record keeps for a run; `runs_of` reads it back by the same keys."""
    return {"app": run.suite.app, "command": run.suite.command, "exit_code": run.exit_code, "seconds": run.seconds,
            "tests": run.tests, "skipped": run.skipped}


def spec_figures_of(metadata: dict) -> SpecFigures:
    """The figures of the spec run a validation recorded on the epic; none when it recorded no spec run."""
    try:
        return SpecFigures(int(metadata.get(SPECS_KEY) or 0), float(metadata.get(SPEC_SECONDS_KEY) or 0))
    except (ValueError, TypeError) as error:
        raise RecordError(f"the {SPECS_KEY} and {SPEC_SECONDS_KEY} metadata of the epic cannot be read: "
                          f"{error!r}") from error


def slow_specs_of(value: object) -> list[OverTheLimit]:
    """The overruns a validation recorded on the epic; none when it recorded none."""
    if value is None:
        return []
    try:
        listed = json.loads(value) if isinstance(value, str) else value
        return [OverTheLimit.from_fields(each) for each in listed]
    except (ValueError, KeyError, TypeError) as error:
        raise RecordError(f"the {SLOW_SPECS_KEY} metadata of the epic cannot be read: {error!r}") from error


@dataclass(frozen=True)
class RecordedValidation:
    """What a validation records on its epic: its result, the commit it validated, each command's run, the figures of
    the acceptance specs and the apps whose specs ran over their time limit. The totals of the runs are derived from
    them, so no total is stored apart from the runs it sums."""
    result: str
    head: str
    runs: list[CommandRun]
    specs: SpecFigures
    slow: list[OverTheLimit]

    @property
    def tests(self) -> int:
        return sum(each.tests or 0 for each in self.runs)

    @property
    def skipped(self) -> int:
        return sum(each.skipped for each in self.runs)

    @property
    def seconds(self) -> float:
        return round(sum(each.seconds for each in self.runs), 3)

    def fields(self, filed: list[str]) -> dict:
        """The fields the scheduler prints for a validation, with the tasks it filed."""
        return {"result": self.result, "head": self.head, "tests": self.tests, "skipped": self.skipped,
                "seconds": self.seconds, "specs": self.specs.count, "spec_seconds": self.specs.seconds,
                "filed": filed[0] if filed else None, "filed_all": filed}

    def figures_lines(self) -> list[str]:
        """The validation's figures: the totals, a line for each command and one for the spec run when it ran."""
        spec_line = ([f"Run side by side, {self.specs.count} acceptance specs took {self.specs.seconds} s."]
                     if self.specs.count else [])
        return [f"Validation of {self.head}: {self.tests} tests, {self.skipped} skipped, {self.seconds} s.",
                *(f"- {each.suite.app}: {each.suite.command}, {each.figures()}" for each in self.runs), *spec_line]

    def evidence_lines(self) -> list[str]:
        """What the gate page shows as the evidence of the validation."""
        return [f"Validation of {self.head} ended {self.result}: {self.tests} tests in {self.seconds} s.",
                *(f"{each.suite.app}: {each.suite.command}, {each.figures()}" for each in self.runs)]

    def slow_lines(self) -> list[str]:
        """What acceptance shows for the specs that ran over the limit."""
        return spec_time_limit.lines_of(self.slow)

    def comment_lines(self, headline: str) -> list[str]:
        return [headline, *self.figures_lines(), *self.slow_lines()]

    def metadata(self) -> list[str]:
        """The `bd update` arguments that write the record, and take the slow specs off when there are none."""
        slow = (set_metadata((SLOW_SPECS_KEY, json.dumps([each.fields() for each in self.slow]))) if self.slow
                else unset_metadata(SLOW_SPECS_KEY))
        return [*set_metadata((RESULT_KEY, self.result), (VALIDATED_HEAD_KEY, self.head),
                              (SPECS_KEY, self.specs.count), (SPEC_SECONDS_KEY, self.specs.seconds),
                              (RUNS_KEY, json.dumps([run_fields(each) for each in self.runs]))), *slow]


def result_metadata(result: str) -> list[str]:
    """The `bd update` arguments that replace the result of a recorded validation and nothing else."""
    return set_metadata((RESULT_KEY, result))


def validated_head(metadata: dict) -> str:
    """The commit of the epic branch that validation checked, or an empty string when the epic records none."""
    return str(metadata.get(VALIDATED_HEAD_KEY) or "")


def read(metadata: dict) -> RecordedValidation | None:
    """The validation the epic's metadata records; none when it records no runs, as for an epic never validated."""
    runs = metadata.get(RUNS_KEY)
    if not runs:
        return None
    return RecordedValidation(str(metadata.get(RESULT_KEY) or "unknown"), validated_head(metadata),
                              runs_of(runs), spec_figures_of(metadata), slow_specs_of(metadata.get(SLOW_SPECS_KEY)))
