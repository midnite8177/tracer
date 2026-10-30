#!/usr/bin/env python3
"""Runs the test modules beside this script, one test class at a time in each of several worker processes.

It discovers test*.py in its own folder as `python3 -m unittest discover` does,
keeps the tests that a -k pattern selects with unittest's meaning, and sends
each test class whole to one worker, so a class's setUpClass and
tearDownClass still run once around all of its tests. The classes with the
most tests start first. A test that discovery could not load, such as a
module that fails to import, runs in this process.

It prints what unittest prints, on stderr: a status character per test,
then each error and failure with its traceback and buffered output, then
"Ran N tests in X.XXXs" and OK, FAILED (...) or NO TESTS RAN. It exits
0 when every test passed, 1 when one did not, and 5 when no test ran and
none was skipped.

Every worker sees the same folder in JIDOKA_SUITE_SHARED_FOLDER, for
fixtures that one run makes once and every worker reuses. The run removes
the folder when it ends.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import time
import unittest
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

SHARED_FOLDER = "JIDOKA_SUITE_SHARED_FOLDER"
SUITE = Path(__file__).resolve().parent
NO_TESTS_EXIT_CODE = 5
WINDOWS_WORKER_LIMIT = 61
SEPARATOR_1 = "=" * 70
SEPARATOR_2 = "-" * 70


@dataclass(frozen=True)
class Problem:
    """One error or failure: its kind as unittest names it, the test's description and the traceback."""
    kind: str
    description: str
    text: str


@dataclass(frozen=True)
class ClassOutcome:
    """What running one group of tests produced, in a form that crosses a process boundary."""
    statuses: str
    tests_run: int
    errors: list[Problem]
    failures: list[Problem]
    skipped: int
    expected_failures: int
    unexpected_successes: list[str]

    def successful(self) -> bool:
        return not self.errors and not self.failures and not self.unexpected_successes


def worker_count(class_count: int, cpu_count: int | None, windows: bool) -> int:
    """How many worker processes a run starts: one per class up to one per CPU, and on Windows at most 61.

    ProcessPoolExecutor refuses more than 61 workers there, whatever the machine has.
    """
    limit = min(class_count, cpu_count or 1)
    return min(limit, WINDOWS_WORKER_LIMIT) if windows else limit


def select_pattern(pattern: str) -> str:
    """unittest's reading of a -k value: a value without * matches any name that holds it."""
    return pattern if "*" in pattern else f"*{pattern}*"


def loader_for(patterns: list[str]) -> unittest.TestLoader:
    loader = unittest.TestLoader()
    if patterns:
        loader.testNamePatterns = [select_pattern(pattern) for pattern in patterns]
    return loader


def flatten(suite: unittest.TestSuite) -> list[unittest.TestCase]:
    tests = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            tests.extend(flatten(item))
        else:
            tests.append(item)
    return tests


def loaded_by_name(test: unittest.TestCase) -> bool:
    """Whether a worker can load the test again from its id; the stand-ins for load failures live in unittest."""
    return not type(test).__module__.startswith("unittest")


def class_key(test: unittest.TestCase) -> str:
    return f"{type(test).__module__}.{type(test).__qualname__}"


def run_tests(suite: unittest.TestSuite) -> ClassOutcome:
    stream = io.StringIO()
    result = unittest.TextTestResult(stream, True, 1)
    result.buffer = True
    suite(result)
    return ClassOutcome(
        statuses=stream.getvalue(),
        tests_run=result.testsRun,
        errors=[Problem("ERROR", result.getDescription(test), text) for test, text in result.errors],
        failures=[Problem("FAIL", result.getDescription(test), text) for test, text in result.failures],
        skipped=len(result.skipped),
        expected_failures=len(result.expectedFailures),
        unexpected_successes=[result.getDescription(test) for test in result.unexpectedSuccesses],
    )


def run_class(test_ids: list[str]) -> ClassOutcome:
    """Runs one class's tests, given by id, in a worker; one suite keeps the class fixtures around them all."""
    return run_tests(unittest.TestLoader().loadTestsFromNames(test_ids))


def report_progress(outcome: ClassOutcome) -> None:
    sys.stderr.write(outcome.statuses)
    sys.stderr.flush()


def worker_crash(key: str, count: int, error: BaseException) -> ClassOutcome:
    problem = Problem("ERROR", f"{key} (the worker process running it)", f"{type(error).__name__}: {error}\n")
    return ClassOutcome("E", count, [problem], [], 0, 0, [])


def summary(outcomes: list[ClassOutcome], seconds: float) -> tuple[str, int]:
    """The text unittest prints after its status characters, and the exit code it would end with."""
    text = "\n"
    for kind in ("errors", "failures"):
        for outcome in outcomes:
            for problem in getattr(outcome, kind):
                text += f"{SEPARATOR_1}\n{problem.kind}: {problem.description}\n{SEPARATOR_2}\n{problem.text}\n"
    unexpected = [name for outcome in outcomes for name in outcome.unexpected_successes]
    if unexpected:
        text += SEPARATOR_1 + "\n" + "".join(f"UNEXPECTED SUCCESS: {name}\n" for name in unexpected)
    run = sum(outcome.tests_run for outcome in outcomes)
    skipped = sum(outcome.skipped for outcome in outcomes)
    expected_failures = sum(outcome.expected_failures for outcome in outcomes)
    text += f"{SEPARATOR_2}\nRan {run} test{'s' if run != 1 else ''} in {seconds:.3f}s\n\n"
    infos = []
    if all(outcome.successful() for outcome in outcomes):
        verdict, code = ("NO TESTS RAN", NO_TESTS_EXIT_CODE) if run == 0 and not skipped else ("OK", 0)
    else:
        verdict, code = "FAILED", 1
        failures = sum(len(outcome.failures) for outcome in outcomes)
        errors = sum(len(outcome.errors) for outcome in outcomes)
        if failures:
            infos.append(f"failures={failures}")
        if errors:
            infos.append(f"errors={errors}")
    if skipped:
        infos.append(f"skipped={skipped}")
    if expected_failures:
        infos.append(f"expected failures={expected_failures}")
    if unexpected:
        infos.append(f"unexpected successes={len(unexpected)}")
    return text + (f"{verdict} ({', '.join(infos)})" if infos else verdict) + "\n", code


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Runs the test classes beside this script in parallel.")
    parser.add_argument("-k", dest="patterns", action="append", default=[], metavar="PATTERN",
                        help="only run tests whose dotted name matches the pattern, as unittest's -k does; "
                             "repeat it to run the tests any pattern matches")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    patterns = parse_args(argv).patterns
    started = time.perf_counter()
    discovered = flatten(loader_for(patterns).discover(str(SUITE), pattern="test*.py", top_level_dir=str(SUITE)))
    classes: dict[str, list[str]] = {}
    in_this_process = []
    for test in discovered:
        if loaded_by_name(test):
            classes.setdefault(class_key(test), []).append(test.id())
        else:
            in_this_process.append(test)
    longest_first = sorted(classes, key=lambda key: len(classes[key]), reverse=True)
    outcomes: dict[str, ClassOutcome] = {}
    windows = os.name == "nt"
    with tempfile.TemporaryDirectory(prefix="jidoka-suite-", ignore_cleanup_errors=windows) as shared:
        os.environ[SHARED_FOLDER] = shared
        unloadable = run_tests(unittest.TestSuite(in_this_process))
        report_progress(unloadable)
        if classes:
            with ProcessPoolExecutor(max_workers=worker_count(len(classes), os.cpu_count(), windows)) as pool:
                futures = {pool.submit(run_class, classes[key]): key for key in longest_first}
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        outcomes[key] = future.result()
                    except Exception as error:
                        outcomes[key] = worker_crash(key, len(classes[key]), error)
                    report_progress(outcomes[key])
    text, code = summary([unloadable, *(outcomes[key] for key in classes)], time.perf_counter() - started)
    sys.stderr.write(text)
    sys.stderr.flush()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
