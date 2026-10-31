"""A validation's run of the acceptance specs against the time limit of the app's settings.

An app's `spec_seconds_limit` is how long a validation may take to run the app's specs side by side. A run that took
longer is over the limit: acceptance shows the slowest specs of the app with their times, and a design finding names the
app's protocol driver, because the driver is what every spec waits on. The design finding is the one design_findings.py
keeps for the problem, so an epic that meets it again adds a sighting to the open finding instead of a second one. An
app's limit judges its own part of the run, from its first spec starting to its last one ending, whatever the specs of
the other apps took beside them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import design_findings
import settings_reader
from validation_specs import SpecsRun

SLOWEST_COUNT = 5


@dataclass(frozen=True)
class SlowSpec:
    """One spec of a run that was over the limit, with how long it took."""
    name: str
    seconds: float


@dataclass(frozen=True)
class OverTheLimit:
    """An app whose specs ran over its time limit: where its protocol driver sits, the limit, how long the app's part
    of the run took, how many of the app's specs it ran and the app's slowest specs."""
    app: str
    acceptance: str
    limit: float
    seconds: float
    count: int
    slowest: tuple[SlowSpec, ...]

    def overrun_sentence(self) -> str:
        return (f"The {self.count} acceptance specs of the {self.app} app took {self.seconds:.1f} s side by side, over "
                f"the {self.limit:g} s limit. The slowest:")

    def lines(self) -> list[str]:
        """What acceptance shows: the overrun, then each of the slowest specs with its time."""
        return [self.overrun_sentence(), *(f"{each.name}: {each.seconds:.1f} s" for each in self.slowest)]

    def fields(self) -> dict:
        return {"app": self.app, "acceptance": self.acceptance, "limit": self.limit, "seconds": self.seconds,
                "count": self.count, "slowest": [{"spec": each.name, "seconds": each.seconds} for each in self.slowest]}

    def problem(self) -> design_findings.Problem:
        """The protocol driver as a problem for design_findings.py, named by the app's acceptance folder."""
        return design_findings.Problem(
            self.acceptance, None, f"The {self.app} protocol driver is slow to run the acceptance specs",
            f"{self.overrun_sentence()} " + ", ".join(f"{each.name} ({each.seconds:.1f} s)"
                                                      for each in self.slowest) + ".")


def over_the_limit(settings: dict, run: SpecsRun) -> list[OverTheLimit]:
    """Each app whose specs the run held and whose limit its own part of the run passed, in the order of the repo
    settings."""
    over = []
    for app in settings_reader.apps_of(settings):
        count = sum(1 for each in run.runs if each.app == app.name)
        if app.spec_seconds_limit is None or app.acceptance is None or not count:
            continue
        seconds = run.seconds_of(app.name)
        if seconds > app.spec_seconds_limit:
            slowest = tuple(SlowSpec(each.name, each.seconds) for each in run.slowest_of(app.name, SLOWEST_COUNT))
            over.append(OverTheLimit(app.name, app.acceptance, app.spec_seconds_limit, round(seconds, 3), count,
                                     slowest))
    return over


def lines_of(over: list[OverTheLimit]) -> list[str]:
    """What acceptance shows for every overrun, one after another."""
    return [line for each in over for line in each.lines()]


def file_design_findings(epic: str, over: list[OverTheLimit], main_tree: Path) -> None:
    """Files the design finding of each overrun, or adds the epic's sighting to the finding that is open."""
    if over:
        design_findings.settle(epic, [each.problem() for each in over], main_tree)
