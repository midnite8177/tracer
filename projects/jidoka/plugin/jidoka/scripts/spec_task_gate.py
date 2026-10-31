"""What the merge gate asks of the spec task's lap: its new specs fail as checks and every other spec passes.

The gate picks the one app that the specs record, those of the spec task and those of the epic's other open tasks, then
runs that app's specs in the lap's worktree,
with the app's spec_command and spec_target as run_specs.py does, and judges each run by its exit code and the summary
a test runner prints (runner_summary.py reads unittest's and dotnet test's):

  a new spec, one that another open task of the epic makes pass, must fail as a check: the run exits with a failure
    and its summary counts at least one failed check and no errors. A run that passes, that prints no summary, as a
    build failure does, or that counts an error, as a driver exception does, is refused. dotnet test counts every
    failed result alike, so runner_summary.py counts a failed test as a check only when its error message is an
    assertion's, and refuses the rest as errors;
  a spec planning marked as already true, one that the spec task's `acceptance.already_true` lists, must pass;
  every other spec, an old one, must pass. The spec command cannot list the specs it holds, so the gate runs all of
    them once and refuses when that run counts more failed specs than the named runs of the new ones did.

`refusal` says why the lap does not support the merge, or gives nothing. It records nothing.
"""
from __future__ import annotations

from pathlib import Path

import epic_reader
import settings_reader
import spec_commands
import specs
from commands import run_test_command
from runner_summary import Finished, Verdict


class OneAppExpected(Exception):
    """Specs recorded under no app or under several, worded for the gate's refusal."""


def finished(command: str, checkout: Path) -> Finished:
    done = run_test_command(command, checkout)
    return Finished(done.returncode, f"{done.stdout}\n{done.stderr}")


def other_open_tasks(task: dict, epic: dict, main_tree: Path) -> list[dict]:
    task_id = str(task.get("id") or "")
    return [bead for bead in epic_reader.read_epic(epic, main_tree).open_task_beads if str(bead["id"]) != task_id]


def app_the_specs_belong_to(settings: settings_reader.Settings, beads: list[dict]) -> settings_reader.App:
    """The one app that the beads record for their specs; raises OneAppExpected when they record none or several, and
    SettingsError for an app the repo settings do not list."""
    named = sorted({app for bead in beads if (app := specs.app_of(bead))})
    if len(named) != 1:
        raise OneAppExpected(f"the specs of the spec task and of the epic's other open tasks belong to "
                             f"{', '.join(named) or 'no app'}, and the gate judges the specs of exactly one app")
    return settings.app_named(named[0])


def new_specs(task: dict, others: list[dict]) -> list[str]:
    """The specs another open task of the epic makes pass, less those planning marked as already true."""
    already_true = specs.already_true_of(task)
    return [name for name in dict.fromkeys(name for bead in others for name in specs.specs_of(bead))
            if name not in already_true]


def new_spec_problem(name: str, made: Finished) -> str | None:
    if made.verdict is Verdict.FAILED_AS_A_CHECK:
        return None
    if made.verdict is Verdict.PASSED:
        return f"the new spec {name!r} passes, and a new spec fails until the app does what it asks"
    return f"the new spec {name!r} ended in a build or driver error, not a failed check"


def already_true_problem(name: str, made: Finished) -> str | None:
    if made.verdict is Verdict.PASSED:
        return None
    return f"the spec {name!r}, which planning marked as already true, does not pass: it {made.verdict.value}"


def old_specs_problem(everything: Finished, failing_by_name: int) -> str | None:
    """Why the run of all specs shows a failing old spec, or None. The named specs account for failing_by_name of the
    failures it counts."""
    tally = everything.tally
    if everything.verdict is Verdict.PASSED:
        return None
    if everything.verdict is Verdict.ERRORED or tally is None:
        return "the run of all of the app's specs ended in a build or driver error, so an old spec cannot be judged"
    beyond = tally.failed - failing_by_name
    if beyond > 0:
        return (f"{beyond} more spec{'s' if beyond > 1 else ''} fail in the run of all of the app's specs than the "
                "new specs account for, so an old spec fails")
    return None


def refusal(task: dict, epic: dict, settings: settings_reader.Settings, worktree: Path, main_tree: Path) -> str | None:
    """Why the spec task's lap, checked out in the worktree, does not support the merge, or None when it does. The task
    and its epic beads say which specs are new and which are already true, and the app they record for their specs
    says which app's specs to run."""
    try:
        others = other_open_tasks(task, epic, main_tree)
        app = app_the_specs_belong_to(settings, [task, *others])
        new = new_specs(task, others)
        already_true = specs.already_true_of(task)
        command, target = spec_commands.spec_commands(app)
        named = {name: finished(spec_commands.command_for_one(app, command, target, name), worktree)
                 for name in [*new, *already_true]}
    except (OneAppExpected, specs.SpecsError, settings_reader.SettingsError, spec_commands.SpecCommandError) as error:
        return str(error)
    problems = [new_spec_problem(name, named[name]) for name in new]
    problems += [already_true_problem(name, named[name]) for name in already_true]
    failing_by_name = sum(tally.failed for each in named.values() if (tally := each.tally) is not None)
    problems.append(old_specs_problem(finished(command, worktree), failing_by_name))
    return "; ".join(problem for problem in problems if problem) or None
