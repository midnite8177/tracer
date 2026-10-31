"""Reads what a test runner prints, dotnet test's and unittest's, and judges one run of it.

A summary counts the tests a run executed, the ones that failed a check and the ones that ended in an error. The
reading is the same for the targeted tests, which only need to know that tests ran, and for the acceptance specs, which
must tell a failed check from a build or driver error.

dotnet test counts every failed result in one number, so the output tells the two apart: a failed test whose error
message is an assertion's (xUnit's `Assert.`, NUnit's `Expected:`, MSTest's AssertFailedException) failed a check, and
any other failed test, one whose message is an exception from the driver or whose message cannot be read, counts as an
error. unittest counts failures and errors apart.
"""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass

DOTNET_SUMMARY = re.compile(r"[A-Za-z]+!\s+-\s+Failed:\s*(\d+),\s*Passed:\s*\d+,\s*Skipped:\s*\d+,\s*Total:\s*(\d+)")
DOTNET_NO_MATCH = "No test matches the given testcase filter"
DOTNET_FAILED_TEST = re.compile(r"^[ \t]*Failed [^\n]+\[[^\]\n]*\][ \t]*\r?\n[ \t]*Error Message:[ \t]*\r?\n"
                                r"(?P<message>(?s:.*?))(?=^[ \t]*Stack Trace:|^[ \t]*Standard Output|\Z)",
                                re.MULTILINE)
ASSERTION_MESSAGE = re.compile(r"\A\s*(?:Assert\.|Expected:|Xunit\.Sdk\.|[\w.]*(?:Assertion|AssertFailed)Exception)")
UNITTEST_RAN = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)
UNITTEST_FAILURES = re.compile(r"^FAILED \(.*?\bfailures=(\d+)", re.MULTILINE)
UNITTEST_ERRORS = re.compile(r"^FAILED \(.*?\berrors=(\d+)", re.MULTILINE)


class Verdict(enum.Enum):
    PASSED = "passed"
    FAILED_AS_A_CHECK = "failed as a check"
    ERRORED = "ended in a build or driver error"


@dataclass(frozen=True)
class Tally:
    """What a run's summary counts: the tests it executed, the ones that failed a check and the ones that errored."""
    executed: int
    failed: int
    errored: int


def tests_executed(output: str) -> int | None:
    """Returns how many tests a run's output says it executed, or None for output in no known shape.

    A dotnet run prints one summary line per test assembly, and an assembly the filter matches nothing in
    prints no summary, so the count is the sum of the summaries' totals. Python's unittest prints one
    "Ran N tests" line.
    """
    counts = [int(total) for _, total in DOTNET_SUMMARY.findall(output)]
    counts += [int(ran) for ran in UNITTEST_RAN.findall(output)]
    if counts:
        return sum(counts)
    if DOTNET_NO_MATCH in output:
        return 0
    return None


def tally_of(output: str) -> Tally | None:
    """The summary's counts, or None for output in no known shape."""
    executed = tests_executed(output)
    if executed is None:
        return None
    dotnet_failed = sum(int(failed) for failed, _ in DOTNET_SUMMARY.findall(output))
    asserted = sum(1 for each in DOTNET_FAILED_TEST.finditer(output) if ASSERTION_MESSAGE.match(each["message"]))
    checks = min(asserted, dotnet_failed)
    failed = checks + sum(int(each) for each in UNITTEST_FAILURES.findall(output))
    errored = dotnet_failed - checks + sum(int(each) for each in UNITTEST_ERRORS.findall(output))
    return Tally(executed, failed, errored)


@dataclass(frozen=True)
class Finished:
    """One run of a test command: how it exited and what it printed."""
    exit_code: int
    output: str

    @property
    def tally(self) -> Tally | None:
        return tally_of(self.output)

    @property
    def verdict(self) -> Verdict:
        """A run that executed no test, or exited with a failure that did not fail a check, ended in an error. Output
        in no known shape is judged by the exit code alone, and an exit with a failure is then an error, because the
        output does not show a failed check."""
        tally = self.tally
        if tally is not None and tally.executed == 0:
            return Verdict.ERRORED
        if self.exit_code == 0:
            return Verdict.PASSED
        if tally is None or tally.errored > 0 or tally.failed == 0:
            return Verdict.ERRORED
        return Verdict.FAILED_AS_A_CHECK

    @property
    def passed(self) -> bool:
        return self.verdict is Verdict.PASSED
