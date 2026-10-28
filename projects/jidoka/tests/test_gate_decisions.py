import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_gate  # noqa: E402
import test_scheduler  # noqa: E402
from test_gate import GATE, git  # noqa: E402

ASSUMPTION = "the total rounds half up, as the till's paper receipts do"
API_CHANGE = "Till.total now returns a Decimal where it returned a float"
THREE_TESTS = ("def test_total():\n    pass\n\n\ndef test_total_again():\n    assert True\n\n\n"
               "def test_total_once_more():\n    pass\n")
ONE_TEST = "def test_total():\n    pass\n"


class GateDecisionsCase(test_gate.GateCase):
    """The gate tests' shop repo, with an epic whose task leaves comments and beads behind before it reaches the
    gate."""

    def handed_off(self) -> tuple[str, str, dict]:
        """An epic handed off with one task whose lap is open; returns the epic, the task and the lap's action."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), self.work_file(task), "built\n")
        return epic, task, action

    def comment(self, bead: str, text: str) -> None:
        test_scheduler.fixture.run([self.bd, "comment", bead, text], self.repo)

    def gate_comment(self, epic: str) -> str:
        [comment] = self.gate_comments(epic)
        return comment

    def decide(self, *args: str):
        return self.launch(GATE, *args)


class TheGateCommentListsTheItemsTests(GateDecisionsCase):
    def test_the_gate_comment_numbers_each_assumption_under_the_task_whose_worker_made_it(self):
        epic, task, _ = self.handed_off()
        self.comment(task, f"assumption: {ASSUMPTION}")
        self.comment(task, "research brief: nothing to say")

        self.build_done(epic, task)

        comment = self.gate_comment(epic)
        self.assertIn(f"Assumptions:\n1. {task} {self.shown(task)['title']}: {ASSUMPTION}", comment)
        self.assertNotIn("nothing to say", comment)

    def test_the_gate_comment_lists_each_public_api_change_a_task_records(self):
        epic, task, _ = self.handed_off()
        self.comment(task, f"public API change: {API_CHANGE}")

        self.build_done(epic, task)

        self.assertIn(f"Public API changes:\n- {task} {self.shown(task)['title']}: {API_CHANGE}",
                      self.gate_comment(epic))

    def test_the_gate_comment_lists_each_open_bead_found_outside_the_epic_from_the_epic_or_its_tasks(self):
        epic, task, _ = self.handed_off()
        from_task = self.create("Round the tax the same way", "--type=task", "--deps", f"discovered-from:{task}")
        from_epic = self.create("Split the till module", "--type=task", "--deps", f"discovered-from:{epic}")
        closed = self.create("Rename the till", "--type=task", "--deps", f"discovered-from:{task}")
        test_scheduler.fixture.run([self.bd, "close", closed, "--reason", "done"], self.repo)
        elsewhere = self.create("Paint the shop", "--type=task")

        self.build_done(epic, task)

        comment = self.gate_comment(epic)
        self.assertIn("Found outside the epic, still open:", comment)
        self.assertIn(f"- {from_task} Round the tax the same way, found in {task}", comment)
        self.assertIn(f"- {from_epic} Split the till module, found in {epic}", comment)
        self.assertNotIn(closed, comment)
        self.assertNotIn(elsewhere, comment)

    def test_a_gate_comment_with_no_assumption_api_change_or_bead_outside_has_none_of_their_headings(self):
        epic, task, _ = self.handed_off()

        self.build_done(epic, task)

        comment = self.gate_comment(epic)
        for heading in ("Assumptions:", "Public API changes:", "Found outside the epic"):
            self.assertNotIn(heading, comment)


class MarkingAnAssumptionWrongTests(GateDecisionsCase):
    WHY = "receipts round half to even"

    def at_the_gate_with_assumptions(self) -> tuple[str, str]:
        epic, task, _ = self.handed_off()
        self.comment(epic, "assumption: the epic's own")
        self.comment(task, f"assumption: {ASSUMPTION}")
        self.build_done(epic, task)
        return epic, task

    def test_marking_an_assumption_wrong_by_its_number_posts_the_human_s_reason_on_the_task_that_made_it(self):
        epic, task = self.at_the_gate_with_assumptions()

        done = self.decide("wrong", epic, "2", "--why", self.WHY)

        self.assertEqual(0, done.returncode, done.stderr)
        [marked] = [text for text in self.texts(task) if text.startswith("Assumption marked wrong")]
        self.assertIn(ASSUMPTION, marked)
        self.assertIn(self.WHY, marked)
        self.assertEqual("Jeff Scheduler", self.comments(task)[-1]["author"])
        self.assertEqual(("open", "waiting"), (self.shown(epic)["status"], self.metadata(epic)["gate.state"]))

    def test_a_number_the_gate_did_not_list_is_refused_and_nothing_is_posted(self):
        epic, task = self.at_the_gate_with_assumptions()
        before = self.texts(task)

        done = self.decide("wrong", epic, "3", "--why", self.WHY)

        self.assertEqual(1, done.returncode)
        self.assertIn("2 assumptions", done.stderr)
        self.assertEqual(before, self.texts(task))

    def test_an_epic_that_does_not_wait_at_the_gate_is_refused(self):
        epic, task, _ = self.handed_off()
        self.comment(task, f"assumption: {ASSUMPTION}")

        done = self.decide("wrong", epic, "1", "--why", self.WHY)

        self.assertEqual(1, done.returncode)
        self.assertIn("acceptance gate", done.stderr)
        self.assertEqual([], [text for text in self.texts(task) if text.startswith("Assumption marked wrong")])


class KeepingOrClosingAFindingTests(GateDecisionsCase):
    def at_the_gate_with_a_finding(self) -> tuple[str, str]:
        epic, task, _ = self.handed_off()
        finding = self.create("Split the till module", "--type=task", "--labels", "design", "--deps",
                              f"discovered-from:{epic}")
        self.build_done(epic, task)
        return epic, finding

    def test_keeping_a_finding_leaves_it_open_with_a_comment_that_names_the_epic(self):
        epic, finding = self.at_the_gate_with_a_finding()

        done = self.decide("keep-finding", epic, finding)

        shown = self.shown(finding)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(("open", ["design"]), (shown["status"], shown["labels"]))
        self.assertIn(epic, self.texts(finding)[-1])

    def test_closing_a_finding_closes_its_bead_with_a_reason_that_names_the_epic_and_keeps_its_labels(self):
        epic, finding = self.at_the_gate_with_a_finding()

        done = self.decide("close-finding", epic, finding)

        shown = self.shown(finding)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(("closed", ["design"]), (shown["status"], shown["labels"]))
        self.assertIn(epic, shown["close_reason"])
        self.assertEqual(("open", "waiting"), (self.shown(epic)["status"], self.metadata(epic)["gate.state"]))

    def test_a_bead_the_epic_did_not_find_is_refused_and_stays_open(self):
        epic, _ = self.at_the_gate_with_a_finding()
        elsewhere = self.create("Paint the shop", "--type=task")

        done = self.decide("close-finding", epic, elsewhere)

        self.assertEqual(1, done.returncode)
        self.assertIn(elsewhere, done.stderr)
        self.assertEqual("open", self.shown(elsewhere)["status"])


class RestoringARemovedTestTests(GateDecisionsCase):
    def file_of_tests(self, task: str) -> str:
        return f"tests/test_{task.replace('.', '_').replace('-', '_')}.py"

    def removal(self, test: str, file: str) -> dict:
        return {"test": test, "file": file, "covered_by": "test_total"}

    def at_the_gate_after_a_cleanup(self) -> tuple[str, str, str]:
        """An epic at the gate whose test cleanup removed two of the three tests its task added to one file; returns
        the epic, its epic branch and the test file."""
        return self.at_the_gate_after_cleaning(ONE_TEST, ["test_total_again", "test_total_once_more"], "test_total")

    def at_the_gate_after_a_cleanup_that_deleted_the_file(self) -> tuple[str, str, str]:
        """An epic at the gate whose test cleanup deleted the test file its task added, all three tests of it."""
        return self.at_the_gate_after_cleaning(None, ["test_total", "test_total_again", "test_total_once_more"],
                                               "specs/acceptance/till.feature")

    def at_the_gate_after_cleaning(self, left: str | None, removed: list[str],
                                   covered_by: str) -> tuple[str, str, str]:
        epic, task, action = self.handed_off()
        file = self.file_of_tests(task)
        self.leave_in(Path(action["worktree"]), file, THREE_TESTS)
        printed = self.report_printed(epic, task, "done", "--app", "shop", "--filter", "test_card")
        [cleaning] = [each for each in printed["actions"] if each["action"] == "test-cleanup"]
        if left is None:
            (Path(cleaning["worktree"]) / file).unlink()
        else:
            self.leave_in(Path(cleaning["worktree"]), file, left)
        Path(cleaning["report"]).write_text(json.dumps([{"test": test, "file": file, "covered_by": covered_by}
                                                        for test in removed]), encoding="utf-8")
        done = self.launch(test_scheduler.SCHEDULER, "report-cleanup", epic)
        self.assertEqual(0, done.returncode, done.stderr)
        self.settle_tidy_and_review(json.loads(done.stdout))
        self.assertEqual("waiting", self.metadata(epic).get("gate.state"))
        return epic, self.metadata(epic)["factory.branch"], file

    def test_restoring_a_removed_test_puts_only_that_test_back_on_the_epic_branch_as_a_commit_of_its_own(self):
        epic, branch, file = self.at_the_gate_after_a_cleanup()
        before = git(self.repo, "rev-parse", branch)

        done = self.decide("restore", epic, "test_total_again")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(before, git(self.repo, "rev-parse", f"{branch}^"))
        self.assertEqual("Restore test_total_again", git(self.repo, "log", "-1", "--format=%s", branch))
        self.assertEqual("def test_total():\n    pass\n\n\ndef test_total_again():\n    assert True",
                         git(self.repo, "show", f"{branch}:{file}"))
        self.assertEqual([file], git(self.repo, "diff", "--name-only", before, branch).splitlines())

    def test_restoring_a_test_from_a_file_the_cleanup_deleted_brings_the_file_back_with_only_that_test(self):
        epic, branch, file = self.at_the_gate_after_a_cleanup_that_deleted_the_file()

        done = self.decide("restore", epic, "test_total_again")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("def test_total_again():\n    assert True", git(self.repo, "show", f"{branch}:{file}"))
        self.assertEqual(["test_total", "test_total_once_more"],
                         [each["test"] for each in json.loads(self.metadata(epic)["cleanup.removed"])])

    def test_a_restored_test_leaves_the_removed_list_and_the_epic_records_the_restore_and_waits_at_the_gate(self):
        epic, branch, file = self.at_the_gate_after_a_cleanup()

        self.decide("restore", epic, "test_total_again")

        metadata = self.metadata(epic)
        self.assertEqual([self.removal("test_total_once_more", file)], json.loads(metadata["cleanup.removed"]))
        self.assertEqual("waiting", metadata["gate.state"])
        [restored] = [text for text in self.texts(epic) if text.startswith("Restored at the acceptance gate")]
        self.assertIn("test_total_again", restored)
        self.assertIn(git(self.repo, "rev-parse", branch), restored)

    def test_the_merge_runs_the_full_suite_again_after_a_restore_and_lands_the_restored_test(self):
        epic, _, file = self.at_the_gate_after_a_cleanup()
        self.decide("restore", epic, "test_total_again")

        done = self.merge(epic)

        landed = git(self.repo, "rev-parse", "main")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([f"{test_gate.test_validation.SKIP_HAND_RUN} {landed}"], self.landing_runs_of(epic))
        self.assertIn("def test_total_again():", git(self.repo, "show", f"{landed}:{file}"))
        self.assertNotIn("test_total_once_more", git(self.repo, "show", f"{landed}:{file}"))

    def test_a_test_the_cleanup_did_not_remove_is_refused_and_the_epic_branch_stays(self):
        epic, branch, _ = self.at_the_gate_after_a_cleanup()
        before = git(self.repo, "rev-parse", branch)

        done = self.decide("restore", epic, "test_total")

        self.assertEqual(1, done.returncode)
        self.assertIn("test_total", done.stderr)
        self.assertEqual(before, git(self.repo, "rev-parse", branch))
        self.assertEqual(2, len(json.loads(self.metadata(epic)["cleanup.removed"])))


if __name__ == "__main__":
    unittest.main()
