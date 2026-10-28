"""The run of an epic's holdouts, which follows a green full suite, and the settling of its report.

The scheduler calls it. When validation.py leaves an epic with `validation.holdouts` pending, the epic is not at
the gate. Its validation worktree stays, and the scheduler hands the run of its holdouts to a worker of the
validation agent type, which makes it against the app built from that worktree. The worker lists, in
`.scratch/holdouts-report.json` of the worktree, one entry for every holdout, numbered from 1 in the order
`holdouts.py read` prints them: {"holdout", "verdict" (pass or fail), "saw"}. `saw` says what a user saw, never the
holdout's scenario or steps, and a report whose `saw` holds a scenario is refused.

A report with every holdout green goes to the gate as validation.py does. A red holdout files one task in the epic,
for each one, with what a user saw, the track simple and the area of the holdout's app, and the epic stays out of
the gate for the next pass. A report that is missing or unusable refuses the call and writes nothing.

A run that ends failed or cut off counts toward the try cap of caps.TRY_CAP, in `validation.tries`. Each count
comments on the epic. At the cap the epic parks with the human label, and the count starts again, so a human who
takes the label off gives the worker a new set of tries.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import caps
import holdouts
import park
import pass_ledger
import validation
from commands import (HUMAN_LABEL, NONE_YET, SCRATCH_FOLDER, env_as_factory, metadata_of, read_bead, run, set_metadata,
                      unset_metadata)
from epic_reader import VALIDATED_HEAD_KEY, validated_head
from epic_task import file_task
from epics import HOLDOUTS_PENDING_KEY, awaits_holdouts
from pass_support import MAIN_BRANCH, count_of, park_epic, worktree_at
from report_text import shortened_title
from validation import FAIL, PASS, RESULT_KEY, RUNS_KEY, ValidationError
from worktrees import remove_worktree

TRIES_KEY = "validation.tries"
HOLDOUTS_REPORT = "holdouts-report.json"


@dataclass(frozen=True)
class HoldoutsToRun:
    """The run of an epic's holdouts that a validation worker makes: the commit it tests, the worktree that holds
    that commit, and how many holdouts the epic has."""
    epic: str
    head: str
    worktree: Path
    count: int

    @property
    def report(self) -> Path:
        return self.worktree / SCRATCH_FOLDER / HOLDOUTS_REPORT

    def fields(self) -> dict:
        return {"action": "holdouts", "epic": self.epic, "head": self.head, "worktree": str(self.worktree),
                "scratch": str(self.report.parent), "report": str(self.report), "holdouts": self.count}


@dataclass(frozen=True)
class Verdict:
    """What the validation worker reported of one holdout: whether it passed, and what a user saw when it did not."""
    holdout: holdouts.Holdout
    passed: bool
    saw: str


def waiting_on(epic: str, validated: validation.Validated) -> HoldoutsToRun | None:
    """The run of the holdouts that a validation left waiting, or None when it kept no worktree for one."""
    if validated.kept is None:
        return None
    return HoldoutsToRun(epic, validated.head, validated.kept.path, validated.kept.holdouts)


def holdouts_to_run(epic: str, shown: dict, home: Path, main_tree: Path) -> HoldoutsToRun:
    """The run of the epic's holdouts that its validation waits on, in a worktree cut again from the validated
    head when the folder is gone."""
    head = validated_head(metadata_of(shown))
    path = validation.worktree_of(epic, main_tree)
    if not head:
        raise ValidationError(f"{epic} waits on its holdouts but records no {VALIDATED_HEAD_KEY} to test. Run its "
                              "validation again by taking the validation metadata off the epic")
    worktree_at(path, head, home, main_tree)
    return HoldoutsToRun(epic, head, path, len(holdouts.of_epic(shown)))


def verdicts_of(report: Path, listed: list[holdouts.Holdout]) -> list[Verdict]:
    """Reads the worker's report, which must give every holdout one verdict and never quote a scenario."""
    try:
        entries = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValidationError(f"the holdouts report {report} cannot be read: {error}. The validation worker writes "
                              "it before it ends") from error
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise ValidationError(f"the holdouts report {report} is not a JSON list of objects")
    numbers = [entry.get("holdout") for entry in entries]
    for number in range(1, len(listed) + 1):
        if numbers.count(number) != 1:
            raise ValidationError(f"the holdouts report {report} must give holdout {number} of {len(listed)} one "
                                  f"verdict, and gives it {numbers.count(number)}")
    if len(entries) != len(listed):
        raise ValidationError(f"the holdouts report {report} holds {len(entries)} verdicts for {len(listed)} holdouts")
    verdicts = []
    for entry in sorted(entries, key=lambda entry: entry["holdout"]):
        holdout = listed[entry["holdout"] - 1]
        saw = str(entry.get("saw") or "").strip()
        if entry.get("verdict") not in (PASS, FAIL):
            raise ValidationError(f"holdout {entry['holdout']} has the verdict {entry.get('verdict')!r} in {report}, "
                                  f"and a verdict is {PASS} or {FAIL}")
        if entry["verdict"] == FAIL and not saw:
            raise ValidationError(f"holdout {entry['holdout']} failed in {report} with no word on what a user saw")
        if any(each.scenario.strip() in saw for each in listed):
            raise ValidationError(f"the saw of holdout {entry['holdout']} in {report} holds the text of a scenario. "
                                  "Say what a user saw, never the steps")
        verdicts.append(Verdict(holdout, entry["verdict"] == PASS, saw))
    return verdicts


def holdout_description(app: str, way_in: str, saw: str) -> str:
    return "\n".join(["## What", "",
                      f"A user of the {app} app, reaching it through {way_in}, saw this on the epic branch after "
                      f"validation merged {MAIN_BRANCH} into it:", "", saw, "", "## Demo", "",
                      f"A user of the {app} app no longer sees this, and sees what the epic's spec says instead.", "",
                      "## Seams", "", f"The {app} app, reached as a user reaches it, through {way_in}."])


def holdout_title(app: str, saw: str) -> str:
    return f"Fix what a user of {app} saw: {shortened_title(saw.splitlines()[0])}"


def file_holdout_failure(epic: str, verdict: Verdict, settings: dict, main_tree: Path) -> str:
    """Files the task that says what a user saw, with neither the holdout's scenario nor its steps."""
    app = verdict.holdout.app
    way_in = next((str(each.get("way_in")) for each in settings.get("apps") or []
                   if isinstance(each, dict) and each.get("name") == app and each.get("way_in")), "its way in")
    return file_task(epic, holdout_title(app, verdict.saw), holdout_description(app, way_in, verdict.saw), app,
                     None, main_tree)


def count_failed_run(epic: str, ended: str, why: str, main_tree: Path) -> bool:
    """Counts a run of the holdouts that ended failed or cut off, and parks the epic at the try cap.

    The park comment carries the worker's why. The count starts again at the park, so a human who takes the label off
    gives the worker a new set of tries. Returns True when it parked the epic.
    """
    shown = read_bead(epic, main_tree)
    if not awaits_holdouts(shown):
        raise ValidationError(f"{epic} waits on no run of its holdouts, so nothing was written")
    tries = count_of(shown, TRIES_KEY) + 1
    return caps.count_against_cap(
        epic, tries, caps.TRY_CAP,
        lambda: park_epic(epic, f"{park.PARKED_PREFIX}the try cap of {caps.TRY_CAP} is reached: the holdouts run "
                                f"{ended} {tries} of {caps.TRY_CAP} times, the last time because {why}. Take the "
                                f"{HUMAN_LABEL} label off the epic to run it again.", {TRIES_KEY: str(NONE_YET)},
                          main_tree),
        f"Holdouts run {tries} of {caps.TRY_CAP} {ended}: {why}. The worker starts again.",
        set_metadata((TRIES_KEY, tries)), main_tree)


def settle_holdouts(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> validation.Validated:
    """Takes the validation worker's report on the epic's holdouts: the gate when all are green, and one task in
    the epic for each red one."""
    shown = read_bead(epic, main_tree)
    if not awaits_holdouts(shown):
        raise ValidationError(f"{epic} waits on no run of its holdouts, so nothing was written")
    hand_run = validation.hand_run_groups(settings)
    to_run = holdouts_to_run(epic, shown, home, main_tree)
    verdicts = verdicts_of(to_run.report, holdouts.of_epic(shown))
    red = [verdict for verdict in verdicts if not verdict.passed]
    filed = [file_holdout_failure(epic, verdict, settings, main_tree) for verdict in red]
    validated = validation.Validated(to_run.head, validation.runs_of(metadata_of(shown).get(RUNS_KEY)), filed, None,
                                     len(red))
    env = env_as_factory()
    run(["bd", "comment", epic, f"Holdouts: {len(verdicts) - len(red)} of {len(verdicts)} passed on {to_run.head}."
         + (f" The red ones are filed as {', '.join(filed)}." if filed else "")], main_tree, env)
    run(["bd", "update", epic, *set_metadata((RESULT_KEY, validated.result)),
         *unset_metadata(HOLDOUTS_PENDING_KEY, TRIES_KEY)], main_tree, env)
    remove_worktree(to_run.worktree, main_tree)
    if red:
        pass_ledger.end_pass(epic, main_tree)
    else:
        validation.reach_the_gate(epic, branch, validated, hand_run, main_tree)
    return validated
