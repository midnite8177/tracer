"""Reads the report of an app check worker from the lap's scratch folder.

The scheduler imports it; no command line runs it. An app check worker runs
the app on the lap's slot against the holdouts that name the lap's task, and
writes `app-check.json` in the lap's scratch folder: one JSON list with an
entry for each of those holdouts, `{"holdout", "verdict", "saw"}`. The
`holdout` is the number `holdouts.py read <epic> --task <task>` prints, the
verdict is `pass` or `fail`, and `saw` says what a user saw and is empty for
a pass. Nothing else in an entry is read, so a builder never gets a step.

A failed holdout reaches the builder as its number, its verdict and `saw`. A
report whose `saw` holds the text of any holdout's scenario is refused.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import holdouts

APP_CHECK_REPORT = "app-check.json"
PASS = "pass"
FAIL = "fail"


class AppCheckError(Exception):
    """A reason the report cannot be used, worded for the worker that writes the next one."""


@dataclass(frozen=True)
class Verdict:
    """What the app check saw of one holdout that names the task: its number, whether it passed, and what a user saw
    when it did not."""
    holdout: int
    verdict: str
    saw: str

    @property
    def passed(self) -> bool:
        return self.verdict == PASS


def read_verdicts(scratch: Path, task: str, epic_holdouts: list[holdouts.Holdout]) -> list[Verdict]:
    """The verdicts in the scratch folder, one for each holdout that names the task and none for any other."""
    path = scratch / APP_CHECK_REPORT
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise AppCheckError(f"the app check's report {path} cannot be read: {error}") from error
    except ValueError as error:
        raise AppCheckError(f"the app check's report {path} is not JSON: {error}") from error
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise AppCheckError(f"the app check's report {path} must be a JSON list of objects")
    wanted = [number for number, _ in holdouts.numbered_naming(task, epic_holdouts)]
    numbers = [entry.get("holdout") for entry in entries]
    for number in wanted:
        if numbers.count(number) != 1:
            raise AppCheckError(f"the report must give holdout {number} one verdict, and gives it "
                                f"{numbers.count(number)}")
    if len(entries) != len(wanted):
        raise AppCheckError(f"the report holds {len(entries)} verdicts for the {len(wanted)} holdouts that name "
                            f"{task}")
    verdicts = []
    for entry in sorted(entries, key=lambda entry: entry["holdout"]):
        number = entry["holdout"]
        saw = str(entry.get("saw") or "").strip()
        if entry.get("verdict") not in (PASS, FAIL):
            raise AppCheckError(f"holdout {number} has the verdict {entry.get('verdict')!r}, and a verdict is "
                                f"{PASS} or {FAIL}")
        if entry["verdict"] == FAIL and not saw:
            raise AppCheckError(f"holdout {number} failed with no word on what a user saw")
        if any(each.scenario.strip() in saw for each in epic_holdouts):
            raise AppCheckError(f"the saw of holdout {number} holds the text of a scenario. Say what a user saw, "
                                "never the steps")
        verdicts.append(Verdict(number, entry["verdict"], saw))
    return verdicts


def clear_report(scratch: Path) -> None:
    (scratch / APP_CHECK_REPORT).unlink(missing_ok=True)


def as_json(failed: list[Verdict]) -> str:
    return json.dumps([asdict(verdict) for verdict in failed])


def describe(failed: list[Verdict]) -> str:
    return "\n".join(f"- holdout {verdict.holdout}, {verdict.verdict}: {verdict.saw}" for verdict in failed)
