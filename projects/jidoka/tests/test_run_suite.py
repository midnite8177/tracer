import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_suite.py"
RUN_TIMEOUT_SECONDS = 120
NO_TESTS_EXIT_CODE = 5
RAN_LINE = re.compile(r"^Ran (\d+) tests? in \d+\.\d{3}s$", re.MULTILINE)

RECORDING_TESTS = """\
import os
import unittest

LOG = {log!r}


def record(line):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\\n")


class AlphaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        record(f"setup AlphaTests {{os.getpid()}}")

    @classmethod
    def tearDownClass(cls):
        record(f"teardown AlphaTests {{os.getpid()}}")

    def test_one(self):
        record(f"{{self.id()}} {{os.getpid()}}")

    def test_two(self):
        record(f"{{self.id()}} {{os.getpid()}}")


class BetaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        record(f"setup BetaTests {{os.getpid()}}")

    @classmethod
    def tearDownClass(cls):
        record(f"teardown BetaTests {{os.getpid()}}")

    def test_three(self):
        record(f"{{self.id()}} {{os.getpid()}}")

    @unittest.skip("not on this machine")
    def test_skipped(self):
        record(f"{{self.id()}} {{os.getpid()}}")
"""

FAILING_TESTS = """\
import unittest


class BrokenTests(unittest.TestCase):
    def test_a_wrong_sum(self):
        print("printed before the failure")
        self.assertEqual(5, 2 + 2)

    def test_a_raise(self):
        raise RuntimeError("the gadget fell over")

    def test_a_pass(self):
        pass
"""

WAITING_TESTS = """\
import time
import unittest
from pathlib import Path

FOLDER = Path({folder!r})


def meet(mine, theirs):
    (FOLDER / mine).write_text("here", encoding="utf-8")
    deadline = time.monotonic() + 20
    while not (FOLDER / theirs).exists():
        if time.monotonic() > deadline:
            raise AssertionError(f"{{theirs}} never arrived")
        time.sleep(0.05)


class LeftTests(unittest.TestCase):
    def test_left_meets_right(self):
        meet("left", "right")


class RightTests(unittest.TestCase):
    def test_right_meets_left(self):
        meet("right", "left")
"""

SHARED_FOLDER_TESTS = """\
import os
import unittest

LOG = {log!r}


def record_shared_folder():
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(os.environ.get("JIDOKA_SUITE_SHARED_FOLDER", "none") + "\\n")


class FirstTests(unittest.TestCase):
    def test_first(self):
        record_shared_folder()


class SecondTests(unittest.TestCase):
    def test_second(self):
        record_shared_folder()
"""


class SuiteRunnerTests(unittest.TestCase):
    """Runs the suite runner as a process over throwaway test modules that sit beside a copy of it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.suite = self.root / "tests"
        self.suite.mkdir()
        shutil.copy2(RUNNER, self.suite / "run_suite.py")
        self.log = self.root / "log.txt"

    def write_module(self, name: str, text: str) -> None:
        (self.suite / f"{name}.py").write_text(textwrap.dedent(text), encoding="utf-8")

    def write_recording_tests(self) -> None:
        self.write_module("test_recording", RECORDING_TESTS.format(log=str(self.log)))

    def run_suite(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.suite / "run_suite.py"), *args], capture_output=True,
                              text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS, cwd=self.root)

    def logged(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def ran_tests(self) -> list[str]:
        return sorted(line.split()[0] for line in self.logged() if not line.startswith(("setup", "teardown")))

    def ran_count(self, done: subprocess.CompletedProcess) -> int:
        [count] = RAN_LINE.findall(done.stderr)
        return int(count)

    def test_a_run_where_every_test_passes_exits_zero_and_ends_with_the_ran_line_and_ok(self):
        self.write_recording_tests()

        done = self.run_suite()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(4, self.ran_count(done))
        self.assertTrue(done.stderr.endswith("\n\nOK (skipped=1)\n"), done.stderr)
        self.assertEqual(["test_recording.AlphaTests.test_one", "test_recording.AlphaTests.test_two",
                          "test_recording.BetaTests.test_three"], self.ran_tests())

    def test_a_failing_and_an_erroring_test_exit_one_and_print_each_traceback_and_the_failed_line(self):
        self.write_module("test_broken", FAILING_TESTS)

        done = self.run_suite()

        self.assertEqual(1, done.returncode, done.stderr)
        self.assertEqual(3, self.ran_count(done))
        self.assertIn("FAIL: test_a_wrong_sum (test_broken.BrokenTests.test_a_wrong_sum)", done.stderr)
        self.assertIn("AssertionError: 5 != 4", done.stderr)
        self.assertIn("printed before the failure", done.stderr)
        self.assertIn("ERROR: test_a_raise (test_broken.BrokenTests.test_a_raise)", done.stderr)
        self.assertIn("RuntimeError: the gadget fell over", done.stderr)
        self.assertTrue(done.stderr.endswith("\n\nFAILED (failures=1, errors=1)\n"), done.stderr)

    def test_a_k_pattern_runs_only_the_tests_whose_dotted_name_holds_it(self):
        self.write_recording_tests()

        done = self.run_suite("-k", "AlphaTests.test_t")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(1, self.ran_count(done))
        self.assertEqual(["test_recording.AlphaTests.test_two"], self.ran_tests())
        self.assertNotIn("setup BetaTests", " ".join(self.logged()))

    def test_repeated_k_patterns_run_every_test_that_matches_one_of_them(self):
        self.write_recording_tests()

        done = self.run_suite("-k", "test_one", "-k", "test_three")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(2, self.ran_count(done))
        self.assertEqual(["test_recording.AlphaTests.test_one", "test_recording.BetaTests.test_three"],
                         self.ran_tests())

    def test_a_k_pattern_with_a_wildcard_matches_the_whole_dotted_name(self):
        self.write_recording_tests()

        done = self.run_suite("-k", "*Beta*three")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["test_recording.BetaTests.test_three"], self.ran_tests())

    def test_a_pattern_that_matches_no_test_exits_five_and_says_no_tests_ran(self):
        self.write_recording_tests()

        done = self.run_suite("-k", "test_nothing_has_this_name")

        self.assertEqual(NO_TESTS_EXIT_CODE, done.returncode, done.stderr)
        self.assertEqual(0, self.ran_count(done))
        self.assertTrue(done.stderr.endswith("\n\nNO TESTS RAN\n"), done.stderr)
        self.assertEqual([], self.logged())

    def test_a_module_that_fails_to_import_is_an_error_and_the_other_tests_still_run(self):
        self.write_recording_tests()
        self.write_module("test_unimportable", "import a_module_that_does_not_exist\n")

        done = self.run_suite()

        self.assertEqual(1, done.returncode, done.stderr)
        self.assertEqual(5, self.ran_count(done))
        self.assertIn("ERROR: test_unimportable", done.stderr)
        self.assertIn("No module named 'a_module_that_does_not_exist'", done.stderr)
        self.assertTrue(done.stderr.endswith("\n\nFAILED (errors=1, skipped=1)\n"), done.stderr)
        self.assertEqual(3, len(self.ran_tests()))

    def test_each_class_is_set_up_and_torn_down_once_in_the_process_that_runs_all_its_tests(self):
        self.write_recording_tests()

        done = self.run_suite()

        self.assertEqual(0, done.returncode, done.stderr)
        lines = [line.split() for line in self.logged()]
        for name in ("AlphaTests", "BetaTests"):
            setups = [pid for word, cls, pid in (line for line in lines if len(line) == 3) if
                      word == "setup" and cls == name]
            teardowns = [pid for word, cls, pid in (line for line in lines if len(line) == 3) if
                         word == "teardown" and cls == name]
            test_pids = {pid for test, pid in (line for line in lines if len(line) == 2) if f".{name}." in test}
            self.assertEqual(1, len(setups), lines)
            self.assertEqual(setups, teardowns)
            self.assertEqual({setups[0]}, test_pids)
            self.assertNotEqual(str(os.getpid()), setups[0])

    def test_two_classes_run_at_the_same_time(self):
        self.write_module("test_waiting", WAITING_TESTS.format(folder=str(self.root)))

        done = self.run_suite()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(2, self.ran_count(done))

    def test_every_class_sees_one_shared_folder_that_is_gone_after_the_run(self):
        self.write_module("test_shared", SHARED_FOLDER_TESTS.format(log=str(self.log)))

        done = self.run_suite()

        self.assertEqual(0, done.returncode, done.stderr)
        folders = self.logged()
        self.assertEqual(2, len(folders))
        self.assertEqual(1, len(set(folders)), folders)
        self.assertNotEqual("none", folders[0])
        self.assertFalse(Path(folders[0]).exists())


if __name__ == "__main__":
    unittest.main()
