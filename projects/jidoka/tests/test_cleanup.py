import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_scheduler  # noqa: E402
import test_validation  # noqa: E402

TEST_FILE = "tests/test_till.py"
TWO_TESTS = "def test_total():\n    pass\n\n\ndef test_total_again():\n    pass\n"
ONE_TEST = "def test_total():\n    pass\n"
REMOVAL = {"test": "test_total_again", "file": TEST_FILE, "covered_by": "tests/test_till.py::test_total"}


class CleanupCase(test_validation.ValidationCase):
    def finish_epic_whose_task_added_tests(self) -> tuple[str, str, dict]:
        """An epic with one task whose build adds a test file; returns the epic, the task and the moves printed when
        the task merged, which end with the test cleanup."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), "till.txt", "built\n")
        self.leave_in(Path(action["worktree"]), TEST_FILE, TWO_TESTS)
        return epic, task, self.build_done(epic, task)

    def cleanup_action_of(self, printed: dict) -> dict:
        [action] = [each for each in printed["actions"] if each["action"] == "test-cleanup"]
        return action

    def write_report(self, action: dict, entries: list[dict]) -> None:
        Path(action["report"]).write_text(json.dumps(entries), encoding="utf-8")

    def report_cleanup(self, epic: str):
        return self.launch(test_scheduler.SCHEDULER, "report-cleanup", epic)


class TestCleanupStartsThePassTests(CleanupCase):
    def test_the_pass_starts_with_a_cleanup_action_on_the_tests_the_epic_added_and_runs_no_validation_yet(self):
        epic, _, printed = self.finish_epic_whose_task_added_tests()

        action = self.cleanup_action_of(printed)

        self.assertEqual([TEST_FILE], action["tests"])
        self.assertIsNone(printed["validation"])
        self.assertNotIn("gate.state", self.metadata(epic))
        self.assertEqual([], self.validation_runs_of(epic))
        self.assertTrue(Path(action["worktree"]).is_dir())

    def test_no_cleanup_starts_while_a_task_of_the_epic_is_still_open(self):
        epic = self.new_epic()
        first = self.new_task_under(epic)
        second = self.new_task_under(epic)
        self.hand_off(epic, {first: "till", second: "reader"})
        laps = {each["task"]: each for each in self.next_printed(epic)["actions"]}
        self.leave_in(Path(laps[first]["worktree"]), TEST_FILE, TWO_TESTS)

        printed = self.build_done(epic, first)

        self.assertEqual([], [each for each in printed["actions"] if each["action"] == "test-cleanup"])

    def test_an_epic_that_added_no_test_goes_straight_to_validation(self):
        epic, task, _ = self.finish_epic_but_for_the_last_report()

        printed = self.build_done(epic, task)

        self.assertEqual(([], "pass"), (printed["actions"], printed["validation"]["result"]))

    def test_a_cleanup_action_repeats_on_every_call_until_its_report_is_taken(self):
        epic, _, printed = self.finish_epic_whose_task_added_tests()

        again = self.next_printed(epic)

        self.assertEqual(self.cleanup_action_of(printed)["head"], self.cleanup_action_of(again)["head"])


class TestCleanupDeletesTests(CleanupCase):
    def delete_one_test(self, action: dict) -> None:
        self.leave_in(Path(action["worktree"]), TEST_FILE, ONE_TEST)
        self.write_report(action, [REMOVAL])

    def test_the_deletions_commit_on_their_own_and_touch_only_the_tests_the_epic_added(self):
        epic, _, printed = self.finish_epic_whose_task_added_tests()
        branch = self.metadata(epic)["factory.branch"]
        self.delete_one_test(self.cleanup_action_of(printed))

        done = self.report_cleanup(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["Test cleanup"], test_validation.git(self.repo, "log", "-1", "--format=%s", branch).splitlines())
        self.assertEqual([TEST_FILE], self.files_of(branch))
        self.assertNotIn("test_total_again",
                         test_validation.git(self.repo, "show", f"{branch}:{TEST_FILE}"))

    def test_the_epic_goes_to_the_gate_after_the_cleanup_and_its_comment_lists_each_removed_test_with_what_covers_it(
            self):
        epic, _, printed = self.finish_epic_whose_task_added_tests()
        self.delete_one_test(self.cleanup_action_of(printed))

        done = self.report_cleanup(epic)

        self.assertEqual([REMOVAL], json.loads(done.stdout)["cleanup"]["removed"])
        moved = self.settle_tidy_and_review(json.loads(done.stdout))
        [gate] = self.gate_comments(epic)
        self.assertEqual("pass", moved["validation"]["result"])
        self.assertIn("Tests removed:", gate)
        self.assertIn("| test_total_again | tests/test_till.py | tests/test_till.py::test_total |", gate)

    def test_a_cleanup_that_removes_nothing_makes_no_commit_and_the_pass_goes_on(self):
        epic, _, printed = self.finish_epic_whose_task_added_tests()
        branch = self.metadata(epic)["factory.branch"]
        head = test_validation.git(self.repo, "rev-parse", branch)
        self.write_report(self.cleanup_action_of(printed), [])

        done = self.report_cleanup(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("pass", self.settle_tidy_and_review(json.loads(done.stdout))["validation"]["result"])
        self.assertNotIn("Test cleanup",
                         test_validation.git(self.repo, "log", "--format=%s", f"{head}..{branch}"))
        self.assertNotIn("Tests removed:", self.gate_comments(epic)[0])

    def test_a_change_to_a_file_that_is_no_test_of_the_epic_is_refused_and_nothing_is_committed(self):
        epic, _, printed = self.finish_epic_whose_task_added_tests()
        branch = self.metadata(epic)["factory.branch"]
        head = test_validation.git(self.repo, "rev-parse", branch)
        action = self.cleanup_action_of(printed)
        self.delete_one_test(action)
        self.leave_in(Path(action["worktree"]), "till.txt", "changed\n")

        done = self.report_cleanup(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("till.txt", done.stderr)
        self.assertEqual(head, test_validation.git(self.repo, "rev-parse", branch))
        self.assertNotIn("gate.state", self.metadata(epic))

    def test_a_deletion_that_names_no_covering_test_is_refused(self):
        epic, _, printed = self.finish_epic_whose_task_added_tests()
        action = self.cleanup_action_of(printed)
        self.leave_in(Path(action["worktree"]), TEST_FILE, ONE_TEST)
        self.write_report(action, [{**REMOVAL, "covered_by": " "}])

        done = self.report_cleanup(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("covered_by", done.stderr)

    def test_a_missing_report_is_refused_and_the_action_repeats(self):
        epic, _, printed = self.finish_epic_whose_task_added_tests()

        done = self.report_cleanup(epic)

        self.assertEqual(1, done.returncode)
        self.assertEqual(1, len([each for each in self.next_printed(epic)["actions"]
                                 if each["action"] == "test-cleanup"]))
        self.assertTrue(self.cleanup_action_of(printed))

    def test_a_red_validation_makes_the_next_pass_start_with_a_cleanup_again(self):
        epic, task, printed = self.finish_epic_whose_task_added_tests()
        self.delete_one_test(self.cleanup_action_of(printed))
        self.queue_validation_exit_codes(epic, 1)

        done = self.report_cleanup(epic)

        self.assertEqual("fail", self.settle_tidy_and_review(json.loads(done.stdout))["validation"]["result"])
        self.assertNotIn("cleanup.state", self.metadata(epic))


if __name__ == "__main__":
    unittest.main()
