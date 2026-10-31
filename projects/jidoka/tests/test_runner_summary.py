import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture  # noqa: E402,F401
from runner_summary import Finished, Tally, Verdict, tally_of, tests_executed  # noqa: E402

DOTNET_SUMMARY = "Failed!  - Failed:     {failed}, Passed:     {passed}, Skipped:     0, Total:    {total}, Duration: 3 ms"


def dotnet_run(*failures: tuple[str, str], passed: int = 0) -> str:
    """What dotnet test prints for failed tests, each with its name and error message, and a summary line."""
    blocks = "".join(f"  Failed {name} [3 ms]\n  Error Message:\n   {message}\n  Stack Trace:\n     at Spec.Run()\n"
                     for name, message in failures)
    return blocks + DOTNET_SUMMARY.format(failed=len(failures), passed=passed, total=len(failures) + passed) + "\n"


class RunnerSummaryTests(unittest.TestCase):
    def test_counts_the_tests_a_dotnet_summary_and_a_unittest_summary_say_they_executed(self):
        self.assertEqual(4, tests_executed(dotnet_run(("A", "Assert.True() Failure"), passed=3)))
        self.assertEqual(7, tests_executed("Ran 7 tests in 0.1s\n\nOK"))
        self.assertEqual(0, tests_executed("No test matches the given testcase filter `Name~X`"))
        self.assertIsNone(tests_executed("error CS1002: the project does not build"))

    def test_counts_a_dotnet_test_that_fails_an_assertion_as_a_failed_check(self):
        output = dotnet_run(("A shopper pays", "Assert.Equal() Failure: Values differ\n   Expected: 1\n   Actual:   2"))

        self.assertEqual(Tally(1, 1, 0), tally_of(output))
        self.assertIs(Verdict.FAILED_AS_A_CHECK, Finished(1, output).verdict)

    def test_counts_nunit_and_mstest_assertions_as_failed_checks(self):
        output = dotnet_run(("One", "Expected: 1\n  But was:  2"),
                            ("Two", "Assert.AreEqual failed. Expected:<1>. Actual:<2>."),
                            ("Three", "Microsoft.VisualStudio.TestTools.UnitTesting.AssertFailedException: no"))

        self.assertEqual(Tally(3, 3, 0), tally_of(output))

    def test_counts_a_dotnet_test_that_fails_with_a_driver_exception_as_an_error(self):
        output = dotnet_run(("A shopper pays", "OpenQA.Selenium.WebDriverException: the driver stopped"))

        self.assertEqual(Tally(1, 0, 1), tally_of(output))
        self.assertIs(Verdict.ERRORED, Finished(1, output).verdict)

    def test_refuses_a_run_that_mixes_a_failed_check_and_a_driver_exception(self):
        output = dotnet_run(("One", "Assert.True() Failure"), ("Two", "System.InvalidOperationException: no browser"))

        self.assertEqual(Tally(2, 1, 1), tally_of(output))
        self.assertIs(Verdict.ERRORED, Finished(1, output).verdict)

    def test_counts_a_dotnet_failure_with_no_readable_message_as_an_error(self):
        output = DOTNET_SUMMARY.format(failed=1, passed=0, total=1) + "\n"

        self.assertEqual(Tally(1, 0, 1), tally_of(output))

    def test_counts_unittest_failures_and_errors_apart(self):
        self.assertEqual(Tally(3, 2, 1), tally_of("Ran 3 tests in 0.1s\n\nFAILED (failures=2, errors=1)"))

    def test_judges_a_run_that_executed_nothing_as_an_error_whatever_it_exited_with(self):
        output = "No test matches the given testcase filter `Name~X`"

        self.assertIs(Verdict.ERRORED, Finished(0, output).verdict)
        self.assertIs(Verdict.ERRORED, Finished(1, output).verdict)

    def test_judges_output_in_no_known_shape_by_its_exit_code(self):
        self.assertIs(Verdict.PASSED, Finished(0, "done").verdict)
        self.assertIs(Verdict.ERRORED, Finished(1, "error CS1002").verdict)


if __name__ == "__main__":
    unittest.main()
