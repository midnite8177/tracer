#!/usr/bin/env python3
"""Runs an app's acceptance specs on a checkout and prints pass or fail for each.

`run_specs.py <app> --checkout <folder> [SPEC ...]` finds the app in the repo settings of the checkout's repo and
runs its specs in the checkout, so a lap can run them on its own worktree, red before it builds and green before it
merges. The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

A SPEC is the name of one spec, in the words the human approved. Each one runs alone: the app's spec_command
followed by its spec_target, with the target's one <...> placeholder replaced by the name, quoted for the shell. A
name given twice runs once, and the specs print in the order given. With no SPEC, the app's spec_command runs once
for all of the app's specs. The script cannot list them, so it prints one line for the run, named "all specs".

A line is `pass <name>` or `fail <name>`, on stdout. The output of each run that failed goes to stderr after the
run. A run that executed no specs fails, because a name that selects nothing would otherwise pass. The script
reads that from the output the way runner_summary.py does, and judges output in no known shape by its exit code.

`run_specs.py <app> --checkout <folder> --record red|green --task <task>` runs the specs the task makes pass, which
specs.py records, and records the run on the task as spec_runs.py describes. It takes no SPEC. A red run is a build
worker's, made before it writes code: `--expect "<spec>=<the failure you expect>"` gives the failure expected of each
spec, a spec that fails without one records nothing, a spec that passes is recorded as already passing, and a task
that holds a red run takes no second one. A green run needs a checkout with no uncommitted change to a tracked file,
and records the checkout's head.

Exit codes:
  0  every run passed, or a red run was recorded.
  1  it refused, with the reason on stderr and nothing recorded: the repo has no settings, the app is unknown or
     incomplete, has no acceptance folder or no spec command, the spec target lacks one placeholder, a spec name
     has no letter or digit, the checkout is no folder of a git repo, or a recording is refused (the task makes no
     spec pass, holds a red run already, or a failing spec has no expected failure).
  2  a usage error.
  3  at least one run failed, and a green run was recorded.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import runner_summary
import settings_reader
import spec_commands
import spec_runs
import specs
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, read_bead, run, run_test_command
from spec_runs import GREEN_KEY, RED_KEY, RecordedRun, SpecResult

SPECS_FAILED_EXIT_CODE = 3
ALL_SPECS = "all specs"
RED = "red"
GREEN = "green"
RECORD_KEYS = {RED: RED_KEY, GREEN: GREEN_KEY}


class RunSpecsError(spec_commands.SpecCommandError):
    """A reason the script runs no spec, worded for the person who reads stderr."""


@dataclass(frozen=True)
class SpecRun:
    """The result of one run of the spec command: the name printed for it, whether it passed and its output."""
    name: str
    passed: bool
    output: str

    @property
    def line(self) -> str:
        return f"{'pass' if self.passed else 'fail'} {self.name}"


@dataclass(frozen=True)
class Recording:
    """A run to record on a task: which one, the task, the specs it owes, the commit the run is made on and the
    failure expected of each spec."""
    mode: str
    task: str
    names: list[str]
    head: str
    expected: dict[str, str]


def run_command(name: str, command: str, checkout: Path) -> SpecRun:
    done = run_test_command(command, checkout)
    output = f"{done.stdout}{done.stderr}"
    finished = runner_summary.Finished(done.returncode, output)
    tally = finished.tally
    if tally is not None and tally.executed == 0:
        return SpecRun(name, False, f"{output}\nThe command ran no specs: {command}\n")
    return SpecRun(name, finished.passed, output)


def runs_of(app: settings_reader.App, given: list[str], checkout: Path) -> list[SpecRun]:
    command, target = spec_commands.spec_commands(app)
    try:
        names = specs.named_specs(given)
    except specs.SpecsError as error:
        raise RunSpecsError(str(error)) from error
    if not names:
        return [run_command(ALL_SPECS, command, checkout)]
    commands = [(name, spec_commands.command_for_one(app, command, target, name)) for name in names]
    return [run_command(name, one, checkout) for name, one in commands]


def app_of(home: Path, checkout: Path, name: str) -> tuple[settings_reader.App, Path]:
    """The app the repo settings name, and the repo's main worktree."""
    if not checkout.is_dir():
        raise RunSpecsError(f"{checkout} is not a folder")
    try:
        main_tree = settings_reader.main_worktree(checkout, COMMAND_TIMEOUT_SECONDS)
        return settings_reader.app_named(settings_reader.require_settings(home, main_tree), name), main_tree
    except settings_reader.SettingsError as error:
        raise RunSpecsError(str(error)) from error


def expectations_of(names: list[str], given: list[str]) -> dict[str, str]:
    """The failure expected of each spec, from `<spec>=<failure>` arguments; a spec's name may hold an equals sign, so
    each argument is matched against the task's spec names."""
    expected: dict[str, str] = {}
    for text in given:
        matching = [name for name in names if text.startswith(f"{name}=")]
        if not matching:
            raise RunSpecsError(f"--expect {text!r} does not start with the name of one of the task's specs and an "
                                f"equals sign. The task's specs: {spec_runs.listed(names)}")
        name = max(matching, key=len)
        expected[name] = text[len(name) + 1:].strip()
    return expected


def head_of(checkout: Path, must_be_clean: bool) -> str:
    head = run(["git", "rev-parse", "HEAD"], checkout, None).strip()
    if must_be_clean and run(["git", "status", "--porcelain", "--untracked-files=no"], checkout, None).strip():
        raise RunSpecsError(f"{checkout} has uncommitted changes to tracked files, so a run there is not a run of its "
                            f"head {head}. Commit them first")
    return head


def plan_recording(mode: str, task: str, given: list[str], checkout: Path, main_tree: Path) -> Recording:
    """What a recorded run owes, checked before any spec runs; raises RunSpecsError for a task that makes no spec
    pass, a second red run and an expectation that names no spec of the task."""
    shown = read_bead(task, main_tree)
    try:
        names = specs.specs_of(shown)
        held = spec_runs.red_run_of(shown)
    except (specs.SpecsError, spec_runs.SpecRunsError) as error:
        raise RunSpecsError(str(error)) from error
    if not names:
        raise RunSpecsError(f"{task} makes no acceptance spec pass, so it has no specs to run and record. Record "
                            "them with specs.py makes-pass")
    if mode == RED and held is not None:
        raise RunSpecsError(f"{task} holds a red run already, made at {held.head}. A second one would run specs "
                            "the build has changed the app for, so the first stands")
    return Recording(mode, task, names, head_of(checkout, mode == GREEN), expectations_of(names, given))


def record(plan: Recording, runs: list[SpecRun], main_tree: Path) -> None:
    """Records the runs on the task; raises RunSpecsError, recording nothing, for a red run with a failing spec whose
    failure was not expected."""
    unexplained = [each.name for each in runs if not each.passed and not plan.expected.get(each.name)]
    if plan.mode == RED and unexplained:
        raise RunSpecsError("no expected failure was given for " + spec_runs.listed(unexplained) + ". Nothing was "
                            "recorded. Run again with --expect '<spec>=<the failure you expect>' for each")
    results = [SpecResult(each.name, each.passed, "" if each.passed else plan.expected.get(each.name, ""))
               for each in runs]
    spec_runs.record(RECORD_KEYS[plan.mode], plan.task, RecordedRun(plan.head, results), main_tree)


def runs_to_record(app: settings_reader.App, mode: str, task: str, expect: list[str], checkout: Path,
                   main_tree: Path) -> tuple[Recording, list[SpecRun]]:
    """Runs the specs the task makes pass in the checkout, and returns the runs with the recording they await. The
    caller can show the runs before `record` refuses them."""
    plan = plan_recording(mode, task, expect, checkout, main_tree)
    return plan, runs_of(app, plan.names, checkout)


def recorded_runs(app: settings_reader.App, mode: str, task: str, expect: list[str], checkout: Path,
                  main_tree: Path) -> list[SpecRun]:
    """Runs the specs the task makes pass in the checkout and records the run on the task; the runs, passed or not,
    once recorded."""
    plan, runs = runs_to_record(app, mode, task, expect, checkout, main_tree)
    record(plan, runs, main_tree)
    return runs


def print_runs(runs: list[SpecRun]) -> None:
    for finished in runs:
        print(finished.line)
        if not finished.passed:
            print(finished.output, end="" if finished.output.endswith("\n") else "\n", file=sys.stderr)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_specs.py", description="Run an app's acceptance specs on a checkout "
                                                                     "and print pass or fail for each.")
    parser.add_argument("app")
    parser.add_argument("--checkout", required=True, help="the folder the specs run in")
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    parser.add_argument("--record", choices=[RED, GREEN], help="run the task's specs and record the run on the task")
    parser.add_argument("--task", help="the task whose specs a recorded run runs")
    parser.add_argument("--expect", action="append", default=[], metavar="SPEC=FAILURE",
                        help="the failure expected of a spec in a red run")
    parser.add_argument("specs", nargs="*", metavar="SPEC", help="a spec to run by name; none runs all of them")
    args = parser.parse_args(argv)
    if args.record is None and (args.task is not None or args.expect):
        parser.error("--task and --expect belong to a recorded run, with --record")
    if args.record is not None and (args.task is None or args.specs):
        parser.error("--record takes --task and no SPEC, because it runs the specs the task makes pass")
    if args.expect and args.record != RED:
        parser.error("--expect belongs to a red run")

    checkout = Path(args.checkout).resolve()
    try:
        app, main_tree = app_of(settings_reader.jidoka_home(args.jidoka_home), checkout, args.app)
        if args.record is None:
            runs = runs_of(app, args.specs, checkout)
            print_runs(runs)
        else:
            plan, runs = runs_to_record(app, args.record, args.task, args.expect, checkout, main_tree)
            print_runs(runs)
            record(plan, runs, main_tree)
    except (spec_commands.SpecCommandError, CommandError, OSError) as error:
        print(f"run_specs: {error}", file=sys.stderr)
        return 1
    return 0 if args.record == RED or all(finished.passed for finished in runs) else SPECS_FAILED_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
