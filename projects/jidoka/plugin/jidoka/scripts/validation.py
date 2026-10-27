"""Validation, the stage that takes a finished epic to the acceptance gate, or back to the build.

The scheduler calls it once every task of an epic is closed. It cuts a
detached worktree at .worktrees/validation-<epic> from the epic branch's
head, merges main into it, and runs every command of the repo settings' full
suite there, one after another, whatever an earlier command did. The full
suite leaves out the hand-run tests, which validation never runs. The output
of the commands goes to stderr. A merge that conflicts with main is aborted,
and validation stops with the conflicting files and writes nothing.

Under the merge lock, the one land.py and the merge gate take, validation
then fast-forwards the epic branch to the merged head, so the next pass
builds on main's work, red or green. It refuses while the main checkout has
the epic branch checked out with uncommitted edits, and when the epic branch
moved while the suite ran. With BEADS_ACTOR set to jidoka it records on the
epic `validation.result` (pass or fail), `validation.head` (the commit it
validated), `validation.seconds`, `validation.tests` and `validation.skipped`,
the figures summed over the commands, and posts a comment that gives them for
each command. A command's figures come from its output, as the targeted
tests read it: dotnet test's summary lines and unittest's "Ran N tests" and
"skipped=N". Output in neither shape counts no tests and no skips.

Green puts the epic at the acceptance gate with one comment that starts with
"Acceptance gate:" and lists the commits the epic branch holds that main
lacks, the figures, the Tests removed table from the epic's `cleanup.removed`
metadata when a test cleanup removed any test, the review's findings of low confidence from `review.low`, which
were never fixed, and each hand-run group with the command that runs it.
Then it sets the epic's `gate.state` to waiting and adds the human label,
last, so a labeled epic always has its comment.

A red result takes `cleanup.state` and `tidy.state` off the epic, so the next
pass starts with a test cleanup and a tidy again. Red files one task in the epic, with the failing commands and the end of
their output, the track simple and the area of the first failing command's
app. The scheduler then opens its lap, and the next pass begins.

An epic that holds holdouts is not at the gate when its suite is green. It
sets `validation.holdouts` and `validation.result` to pending, keeps the
validation worktree, and hands the scheduler the run of its holdouts, which a
worker of the validation agent type makes against the app built from that
worktree. The worker lists, in `.scratch/holdouts-report.json` of the
worktree, one entry for every holdout, numbered from 1 in the order
`holdouts.py read` prints them: {"holdout", "verdict" (pass or fail), "saw"}.
`saw` says what a user saw, never the holdout's scenario or steps, and a
report whose `saw` holds a scenario is refused. A report with every holdout
green goes to the gate as above. A red holdout files one task in the epic, for
each one, with what a user saw, the track simple and the area of the
holdout's app, and the epic stays out of the gate for the next pass. A red
suite runs no holdouts, because the pass goes back to the build anyway.
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import git_exclude
import holdouts
import park
import private_docs
import targeted_tests
from bench import WORKTREE_FOLDER, hide_worktrees
from commands import bd_show, capture, env_as_factory, head_of, run, run_test_command
from handoff import TRACK
from land import acquire_lock, edited_paths, merge_lock, release_lock
from merge_gate import checked_out_branch
from repo_settings import full_suite_command

GATE_STATE_KEY = "gate.state"
WAITING = "waiting"
HUMAN_LABEL = park.HUMAN_LABEL
GATE_COMMENT_HEADING = "Acceptance gate:"
WORKTREE_PREFIX = "validation-"
MAIN_BRANCH = "main"
OUTPUT_TAIL_LINES = 40
DOTNET_SKIPPED = re.compile(r"[A-Za-z]+!\s+-\s+Failed:\s*\d+,\s*Passed:\s*\d+,\s*Skipped:\s*(\d+),\s*Total:\s*\d+")
UNITTEST_SKIPPED = re.compile(r"^(?:OK|FAILED) \([^)]*\bskipped=(\d+)", re.MULTILINE)
HAND_RUN_FIELDS = ("app", "name", "reason", "command")
UNKNOWN_FIGURES = "no test count in its output"
CLEANUP_STATE_KEY = "cleanup.state"
TIDY_STATE_KEY = "tidy.state"
REMOVED_KEY = "cleanup.removed"
LOW_KEY = "review.low"
RESULT_KEY = "validation.result"
HEAD_KEY = "validation.head"
RUNS_KEY = "validation.runs"
HOLDOUTS_KEY = "validation.holdouts"
PENDING = "pending"
PASS = "pass"
FAIL = "fail"
SCRATCH_FOLDER = ".scratch"
HOLDOUTS_REPORT = "holdouts-report.json"
TITLE_LIMIT = 80


class ValidationError(Exception):
    """A reason validation writes nothing more, worded for the person who reads stderr."""


@dataclass(frozen=True)
class SuiteCommand:
    """One command of the full suite, and the app whose tests it runs."""
    app: str
    command: str


@dataclass(frozen=True)
class HandRunGroup:
    """A group of an app's tests that the full suite leaves out, and the command the human runs it with."""
    app: str
    name: str
    reason: str
    command: str


@dataclass(frozen=True)
class CommandRun:
    """One run of a full-suite command: how it exited, how long it took, and what its output counted."""
    suite: SuiteCommand
    exit_code: int
    seconds: float
    tests: int | None
    skipped: int
    output: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0

    def figures(self) -> str:
        if self.tests is None:
            return f"exit code {self.exit_code}, {UNKNOWN_FIGURES}, {self.seconds:.1f} s"
        return f"exit code {self.exit_code}, {self.tests} tests, {self.skipped} skipped, {self.seconds:.1f} s"


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
class Validated:
    """What a validation did: the commit it validated, each command's run, the tasks it filed when red, the holdouts
    it waits on when the suite is green and the epic holds some, and how many holdouts ended red."""
    head: str
    runs: list[CommandRun]
    filed: list[str]
    waiting: HoldoutsToRun | None
    red_holdouts: int

    @property
    def green(self) -> bool:
        return all(each.passed for each in self.runs)

    @property
    def result(self) -> str:
        if not self.green or self.red_holdouts:
            return FAIL
        return PENDING if self.waiting is not None else PASS

    @property
    def headline(self) -> str:
        return {FAIL: "Validation failed.", PASS: "Validation passed.",
                PENDING: "Validation passed the full suite, and its holdouts run next."}[self.result]

    @property
    def tests(self) -> int:
        return sum(each.tests or 0 for each in self.runs)

    @property
    def skipped(self) -> int:
        return sum(each.skipped for each in self.runs)

    @property
    def seconds(self) -> float:
        return round(sum(each.seconds for each in self.runs), 3)

    def fields(self) -> dict:
        return {"result": self.result, "head": self.head, "tests": self.tests, "skipped": self.skipped,
                "seconds": self.seconds, "filed": self.filed[0] if self.filed else None, "filed_all": self.filed}


def suite_commands(settings: dict) -> list[SuiteCommand]:
    """The full-suite command of every app that has a test command, in the order of the repo settings."""
    return [SuiteCommand(str(app["name"]), full_suite_command(app)) for app in settings.get("apps") or []
            if isinstance(app, dict) and app.get("test") is not None]


def hand_run_groups(settings: dict) -> list[HandRunGroup]:
    listed = settings.get("hand_run")
    if not (isinstance(listed, list) and all(isinstance(group, dict) and all(
            isinstance(group.get(key), str) for key in HAND_RUN_FIELDS) for group in listed)):
        raise ValidationError("the repo settings hold no hand_run list of the tests validation leaves out. "
                              "Run /jidoka:onboard again to record it")
    return [HandRunGroup(*(group[key] for key in HAND_RUN_FIELDS)) for group in listed]


def skipped_in(output: str) -> int:
    return sum(int(count) for count in DOTNET_SKIPPED.findall(output) + UNITTEST_SKIPPED.findall(output))


def run_command(suite: SuiteCommand, worktree: Path) -> CommandRun:
    print(f"running: {suite.command}", file=sys.stderr, flush=True)
    started = time.monotonic()
    done = run_test_command(suite.command, worktree)
    seconds = time.monotonic() - started
    output = f"{done.stdout}{done.stderr}"
    sys.stderr.write(output)
    sys.stderr.flush()
    return CommandRun(suite, done.returncode, seconds, targeted_tests.tests_executed(output), skipped_in(output),
                      output)


def merged_worktree(epic: str, epic_head: str, home: Path, main_tree: Path) -> tuple[Path, str]:
    """Cuts the validation worktree from the epic branch's head and merges main into it; returns it and its head."""
    path = main_tree / WORKTREE_FOLDER / f"{WORKTREE_PREFIX}{epic}"
    if path.exists():
        run(["git", "worktree", "remove", "--force", str(path)], main_tree, None)
    hide_worktrees(main_tree)
    run(["git", "worktree", "add", "-q", "--detach", str(path), epic_head], main_tree, None)
    try:
        private_docs.share(main_tree, path.resolve(), home)
        targeted_tests.bring_in_base_branch(MAIN_BRANCH, path, targeted_tests.Integration.MERGE)
    except targeted_tests.MergeConflict as conflict:
        remove_worktree(path, main_tree)
        raise ValidationError(f"merging {MAIN_BRANCH} into the epic branch conflicts in "
                              f"{', '.join(conflict.files)}, so validation ran no tests and wrote nothing. Merge "
                              f"{MAIN_BRANCH} into the epic branch by hand, then run the scheduler again") from conflict
    except (targeted_tests.TestRunError, private_docs.ClashError) as error:
        remove_worktree(path, main_tree)
        raise ValidationError(str(error)) from error
    head = head_of("HEAD", path)
    if head is None:
        remove_worktree(path, main_tree)
        raise ValidationError(f"{path} has no commit after the merge of {MAIN_BRANCH}")
    return path, head


def remove_worktree(path: Path, main_tree: Path) -> None:
    capture(["git", "worktree", "remove", "--force", str(path)], main_tree, None)


def move_epic_branch(branch: str, old: str, new: str, home: Path, main_tree: Path) -> None:
    """Fast-forwards the epic branch from old to new under the merge lock, bringing the main checkout along."""
    if old == new:
        return
    lock = merge_lock(home)
    acquire_lock(lock)
    try:
        checked_out = checked_out_branch(main_tree) == branch
        if checked_out:
            edited = sorted(edited_paths(main_tree))
            if edited:
                raise ValidationError(f"the main checkout {main_tree} has {branch} checked out with uncommitted "
                                      f"edits: {', '.join(edited)}. Commit or discard them, then run the "
                                      "scheduler again")
        done = capture(["git", "update-ref", f"refs/heads/{branch}", new, old], main_tree, None)
        if done.returncode != 0:
            raise ValidationError(f"{branch} moved from {old} while the suite ran, so validation changed "
                                  f"nothing. Run the scheduler again: {done.stderr.strip()}")
        if checked_out:
            run(["git", "read-tree", "-m", "-u", old, new], main_tree, None)
    finally:
        release_lock(lock)


def merged_commits(branch_head: str, main_tree: Path) -> list[str]:
    """One line for each commit the epic branch holds that main lacks, merge commits left out, oldest first."""
    listed = run(["git", "log", "--no-merges", "--reverse", "--format=%h %s", f"{MAIN_BRANCH}..{branch_head}"],
                 main_tree, None)
    return listed.splitlines()


def figures_lines(validated: Validated) -> list[str]:
    return [f"Validation of {validated.head}: {validated.tests} tests, {validated.skipped} skipped, "
            f"{validated.seconds} s.",
            *(f"- {each.suite.app}: {each.suite.command}, {each.figures()}" for each in validated.runs)]


def tests_removed_lines(shown: dict) -> list[str]:
    """The gate comment's Tests removed table from the deletions the epic records, or no line when none."""
    metadata = shown.get("metadata") if isinstance(shown.get("metadata"), dict) else {}
    value = metadata.get(REMOVED_KEY)
    if value in (None, ""):
        return []
    try:
        listed = json.loads(value) if isinstance(value, str) else value
        rows = [f"| {each['test']} | {each['file']} | {each['covered_by']} |" for each in listed]
    except (ValueError, KeyError, TypeError) as error:
        raise ValidationError(f"the {REMOVED_KEY} metadata of the epic cannot be read: {error!r}") from error
    if not rows:
        return []
    return ["", "Tests removed:", "| Test | File | Covered by |", "| --- | --- | --- |", *rows]


def low_confidence_lines(shown: dict) -> list[str]:
    """The gate comment's list of the review findings of low confidence, which no fix touched, or no line when
    none."""
    metadata = shown.get("metadata") if isinstance(shown.get("metadata"), dict) else {}
    value = metadata.get(LOW_KEY)
    if value in (None, ""):
        return []
    try:
        listed = json.loads(value) if isinstance(value, str) else value
        rows = [f"- {each['lane']}, {each['file']}:{each['line']}: {each['title']}. {each['note']}" for each in listed]
    except (ValueError, KeyError, TypeError) as error:
        raise ValidationError(f"the {LOW_KEY} metadata of the epic cannot be read: {error!r}") from error
    if not rows:
        return []
    return ["", "Review findings of low confidence, which were never fixed:", *rows]


def gate_comment(epic: str, branch: str, validated: Validated, hand_run: list[HandRunGroup], removed: list[str],
                 main_tree: Path) -> str:
    commits = merged_commits(validated.head, main_tree)
    lines = [f"{GATE_COMMENT_HEADING} {epic} waits for the human, on the epic branch {branch} at {validated.head}.",
             "", "Merged into the epic branch:", *(f"- {commit}" for commit in commits), "",
             *figures_lines(validated), *removed]
    if hand_run:
        lines += ["", "Hand-run tests, which validation never runs. Run each one yourself before you trust the "
                      "branch:"]
        for group in hand_run:
            lines += [f"- {group.app}, {group.name}: {group.reason}", f"  {group.command}"]
    return "\n".join(lines)


def runs_as_text(runs: list[CommandRun]) -> str:
    return json.dumps([{"app": each.suite.app, "command": each.suite.command, "exit_code": each.exit_code,
                        "seconds": each.seconds, "tests": each.tests, "skipped": each.skipped} for each in runs])


def runs_of(value: object) -> list[CommandRun]:
    """The runs a validation recorded on the epic, without their output."""
    try:
        listed = json.loads(value) if isinstance(value, str) else value
        return [CommandRun(SuiteCommand(str(each["app"]), str(each["command"])), int(each["exit_code"]),
                           float(each["seconds"]), None if each["tests"] is None else int(each["tests"]),
                           int(each["skipped"]), "") for each in listed]
    except (ValueError, KeyError, TypeError) as error:
        raise ValidationError(f"the {RUNS_KEY} metadata of the epic cannot be read: {error!r}") from error


def record(epic: str, validated: Validated, main_tree: Path) -> None:
    env = env_as_factory()
    run(["bd", "comment", epic, "\n".join([validated.headline, *figures_lines(validated)])], main_tree, env)
    waiting = ["--set-metadata", f"{HOLDOUTS_KEY}={PENDING}"] if validated.waiting is not None else []
    again = (["--unset-metadata", CLEANUP_STATE_KEY, "--unset-metadata", TIDY_STATE_KEY]
             if validated.result == FAIL else [])
    run(["bd", "update", epic, "--set-metadata", f"{RESULT_KEY}={validated.result}",
         "--set-metadata", f"{HEAD_KEY}={validated.head}",
         "--set-metadata", f"validation.seconds={validated.seconds}",
         "--set-metadata", f"validation.tests={validated.tests}",
         "--set-metadata", f"validation.skipped={validated.skipped}",
         "--set-metadata", f"{RUNS_KEY}={runs_as_text(validated.runs)}", *waiting, *again], main_tree, env)


def reach_the_gate(epic: str, branch: str, validated: Validated, hand_run: list[HandRunGroup],
                   main_tree: Path) -> None:
    env = env_as_factory()
    shown = bd_show(epic, main_tree)
    removed = [*tests_removed_lines(shown), *low_confidence_lines(shown)] if shown is not None else []
    run(["bd", "comment", epic, gate_comment(epic, branch, validated, hand_run, removed, main_tree)], main_tree, env)
    run(["bd", "update", epic, "--set-metadata", f"{GATE_STATE_KEY}={WAITING}", f"--add-label={HUMAN_LABEL}"],
        main_tree, env)


def tail_of(output: str) -> str:
    return "\n".join(output.strip().splitlines()[-OUTPUT_TAIL_LINES:])


def failure_description(failed: list[CommandRun]) -> str:
    sections = ["## What", "",
                f"Validation ran the full suite on the epic branch after it merged {MAIN_BRANCH}, and "
                f"{'this command' if len(failed) == 1 else 'these commands'} failed:"]
    for failure in failed:
        sections += ["", f"`{failure.suite.command}` exited {failure.exit_code}. The end of its output:", "",
                     "```", tail_of(failure.output), "```"]
    sections += ["", "## Demo", "",
                 f"{'The command' if len(failed) == 1 else 'Each command'} above exits 0 on the epic branch.", "",
                 "## Seams", "", "The failing full-suite commands, run as processes from the repo root."]
    return "\n".join(sections)


def file_failure(epic: str, failed: list[CommandRun], main_tree: Path) -> str:
    """Files the task that says what failed, with the track and area the scheduler needs to open its lap."""
    app = failed[0].suite.app
    return file_task(epic, f"Make the {app} full suite pass on the epic branch", failure_description(failed), app,
                     main_tree)


def file_task(epic: str, title: str, description: str, area: str, main_tree: Path) -> str:
    env = env_as_factory()
    created = run(["bd", "create", "--title", title, "--type", "task", "--parent", epic, "--description",
                   description, "--json"], main_tree, env)
    try:
        task = str(json.loads(created)["id"])
    except (ValueError, KeyError, TypeError) as error:
        raise ValidationError(f"bd create did not print the id of the task it made: {created.strip()[:200]!r}") \
            from error
    run(["bd", "update", task, "--set-metadata", f"lap.track={TRACK}", "--set-metadata", f"lap.area={area}"],
        main_tree, env)
    return task


def awaits_holdouts(shown: dict) -> bool:
    """True when the epic's suite passed and the run of its holdouts has not been settled."""
    metadata = shown.get("metadata")
    return isinstance(metadata, dict) and metadata.get(HOLDOUTS_KEY) == PENDING


def worktree_of(epic: str, main_tree: Path) -> Path:
    return main_tree / WORKTREE_FOLDER / f"{WORKTREE_PREFIX}{epic}"


def keep_scratch_folder(worktree: Path, main_tree: Path) -> None:
    """Makes the worktree's scratch folder, which the repo's git exclude file hides from every git status."""
    git_exclude.add(git_exclude.exclude_file(main_tree), [git_exclude.exclude_line(SCRATCH_FOLDER, True)])
    (worktree / SCRATCH_FOLDER).mkdir(exist_ok=True)


def holdouts_to_run(epic: str, shown: dict, home: Path, main_tree: Path) -> HoldoutsToRun:
    """The run of the epic's holdouts that its validation waits on, in a worktree cut again from the validated
    head when the folder is gone."""
    metadata = shown.get("metadata") if isinstance(shown.get("metadata"), dict) else {}
    head = str(metadata.get(HEAD_KEY) or "")
    path = worktree_of(epic, main_tree)
    if not path.is_dir():
        if not head:
            raise ValidationError(f"{epic} waits on its holdouts but records no {HEAD_KEY} to test. Run its "
                                  "validation again by taking the validation metadata off the epic")
        capture(["git", "worktree", "prune"], main_tree, None)
        hide_worktrees(main_tree)
        run(["git", "worktree", "add", "-q", "--detach", str(path), head], main_tree, None)
        try:
            private_docs.share(main_tree, path.resolve(), home)
        except private_docs.ClashError as error:
            remove_worktree(path, main_tree)
            raise ValidationError(str(error)) from error
    keep_scratch_folder(path, main_tree)
    return HoldoutsToRun(epic, head, path, len(holdouts.of_epic(shown)))


def validate(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Validated:
    """Validates the epic branch merged with main, moves the branch there, and records the verdict on the epic.

    An epic with holdouts whose suite is green keeps its worktree and waits for the holdouts to run.
    """
    commands = suite_commands(settings)
    hand_run = hand_run_groups(settings)
    epic_holdouts = holdouts.read(epic, main_tree)
    epic_head = head_of(f"refs/heads/{branch}", main_tree)
    if epic_head is None:
        raise ValidationError(f"the epic branch {branch} does not exist")
    worktree, merged_head = merged_worktree(epic, epic_head, home, main_tree)
    try:
        runs = [run_command(suite, worktree) for suite in commands]
        move_epic_branch(branch, epic_head, merged_head, home, main_tree)
    except BaseException:
        remove_worktree(worktree, main_tree)
        raise
    waiting = None
    if epic_holdouts and all(each.passed for each in runs):
        keep_scratch_folder(worktree, main_tree)
        waiting = HoldoutsToRun(epic, merged_head, worktree, len(epic_holdouts))
    else:
        remove_worktree(worktree, main_tree)
    validated = Validated(merged_head, runs, [], waiting, 0)
    record(epic, validated, main_tree)
    if waiting is not None:
        return validated
    if validated.green:
        reach_the_gate(epic, branch, validated, hand_run, main_tree)
        return validated
    return Validated(merged_head, runs, [file_failure(epic, [each for each in runs if not each.passed], main_tree)],
                     None, 0)


@dataclass(frozen=True)
class Verdict:
    """What the validation worker reported of one holdout: whether it passed, and what a user saw when it did not."""
    holdout: holdouts.Holdout
    passed: bool
    saw: str


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
    summary = saw.splitlines()[0]
    if len(summary) > TITLE_LIMIT:
        summary = f"{summary[:TITLE_LIMIT - 3].rstrip()}..."
    return f"Fix what a user of {app} saw: {summary}"


def file_holdout_failure(epic: str, verdict: Verdict, settings: dict, main_tree: Path) -> str:
    """Files the task that says what a user saw, with neither the holdout's scenario nor its steps."""
    app = verdict.holdout.app
    way_in = next((str(each.get("way_in")) for each in settings.get("apps") or []
                   if isinstance(each, dict) and each.get("name") == app and each.get("way_in")), "its way in")
    return file_task(epic, holdout_title(app, verdict.saw), holdout_description(app, way_in, verdict.saw), app,
                     main_tree)


def settle_holdouts(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Validated:
    """Takes the validation worker's report on the epic's holdouts: the gate when all are green, and one task in
    the epic for each red one."""
    shown = bd_show(epic, main_tree)
    if shown is None:
        raise ValidationError(f"bd show printed nothing usable for {epic}")
    if not awaits_holdouts(shown):
        raise ValidationError(f"{epic} waits on no run of its holdouts, so nothing was written")
    hand_run = hand_run_groups(settings)
    to_run = holdouts_to_run(epic, shown, home, main_tree)
    verdicts = verdicts_of(to_run.report, holdouts.of_epic(shown))
    red = [verdict for verdict in verdicts if not verdict.passed]
    filed = [file_holdout_failure(epic, verdict, settings, main_tree) for verdict in red]
    metadata = shown["metadata"]
    validated = Validated(to_run.head, runs_of(metadata.get(RUNS_KEY)), filed, None, len(red))
    env = env_as_factory()
    run(["bd", "comment", epic, f"Holdouts: {len(verdicts) - len(red)} of {len(verdicts)} passed on {to_run.head}."
         + (f" The red ones are filed as {', '.join(filed)}." if filed else "")], main_tree, env)
    run(["bd", "update", epic, "--set-metadata", f"{RESULT_KEY}={validated.result}",
         "--unset-metadata", HOLDOUTS_KEY, *(["--unset-metadata", CLEANUP_STATE_KEY, "--unset-metadata", TIDY_STATE_KEY] if red else [])],
        main_tree, env)
    remove_worktree(to_run.worktree, main_tree)
    if not red:
        reach_the_gate(epic, branch, validated, hand_run, main_tree)
    return validated
