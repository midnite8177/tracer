import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_scheduler  # noqa: E402
import test_validation  # noqa: E402

BUILT_FILE = "till.txt"
LANES = ["comments", "standards", "spec", "design"]
DIFF_LANES = ["comments", "standards", "spec"]
FIX_SUBJECT = "Review fixes"


def finding(title: str, size: str, confidence: str, file: str = BUILT_FILE) -> dict:
    return {"file": file, "line": 1, "title": title, "note": f"{title}, as the lane reads it", "size": size,
            "confidence": confidence}


class ReviewCase(test_validation.ValidationCase):
    def finish_epic_at_the_review(self) -> tuple[str, dict]:
        """An epic whose one task built a file and whose tidy changed nothing; returns the epic and the moves that
        hold the review's lanes."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), BUILT_FILE, "total = 1\n")
        return epic, self.tidied(test_scheduler.SchedulerCase.build_done(self, epic, action["task"]))

    def tidied(self, printed: dict) -> dict:
        """Reports the tidy done with nothing changed, as often as the moves hold one."""
        while any(each["action"] == "tidy" for each in printed["actions"]):
            done = self.launch(test_scheduler.SCHEDULER, "report-tidy", printed["epic"])
            self.assertEqual(0, done.returncode, done.stderr)
            printed = json.loads(done.stdout)
        return printed

    def review_actions_of(self, printed: dict) -> list[dict]:
        return [each for each in printed["actions"] if each["action"] == "review"]

    def write_lanes(self, printed: dict, findings: dict[str, list[dict]]) -> None:
        for action in self.review_actions_of(printed):
            Path(action["report"]).write_text(json.dumps(findings.get(action["lane"], [])), encoding="utf-8")

    def report_review(self, epic: str) -> subprocess.CompletedProcess:
        return self.launch(test_scheduler.SCHEDULER, "report-review", epic)

    def reviewed(self, printed: dict, findings: dict[str, list[dict]]) -> dict:
        self.write_lanes(printed, findings)
        done = self.report_review(printed["epic"])
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def report_fix(self, epic: str) -> subprocess.CompletedProcess:
        return self.launch(test_scheduler.SCHEDULER, "report-fix", epic)

    def fix_action_of(self, printed: dict) -> dict:
        [action] = [each for each in printed["actions"] if each["action"] == "fix"]
        return action

    def epic_log(self, epic: str) -> list[str]:
        branch = self.metadata(epic)["factory.branch"]
        return test_validation.git(self.repo, "log", "--format=%s", f"main..{branch}").splitlines()

    def red_validation(self, printed: dict) -> tuple[dict, str]:
        """Settles the review with no finding and a red full suite; returns the moves and the task validation filed
        in the epic."""
        self.queue_validation_exit_codes(printed["epic"], 1)
        moved = self.reviewed(printed, {})
        self.assertEqual("fail", moved["validation"]["result"])
        return moved, moved["validation"]["filed"]

    def next_pass_review(self, printed: dict, task: str, new_file: str) -> dict:
        """Builds the filed task with a file of its own, merges it, and tidies; returns the moves that hold the
        next pass's review."""
        [lap] = [each for each in printed["actions"] if each.get("task") == task]
        self.leave_in(Path(lap["worktree"]), new_file, "more = 2\n")
        return self.tidied(test_scheduler.SchedulerCase.build_done(self, printed["epic"], task))


class ReviewLanesTests(ReviewCase):
    def test_the_four_lanes_are_printed_together_on_one_head_each_with_its_own_report_and_no_validation_runs(self):
        epic, printed = self.finish_epic_at_the_review()

        lanes = self.review_actions_of(printed)

        self.assertEqual(LANES, [each["lane"] for each in lanes])
        self.assertEqual(1, len({each["head"] for each in lanes}))
        self.assertEqual(4, len({each["report"] for each in lanes}))
        self.assertEqual([[BUILT_FILE]] * 4, [each["files"] for each in lanes])
        self.assertTrue(Path(lanes[0]["worktree"]).is_dir())
        self.assertIsNone(printed["validation"])
        self.assertEqual([], self.validation_runs_of(epic))

    def test_the_lanes_repeat_on_every_call_until_they_are_reported(self):
        epic, printed = self.finish_epic_at_the_review()

        again = self.next_printed(epic)

        self.assertEqual(self.review_actions_of(printed), self.review_actions_of(again))

    def test_a_finding_without_a_size_is_refused_and_nothing_is_written(self):
        epic, printed = self.finish_epic_at_the_review()
        unsized = finding("Long function", "small", "high")
        del unsized["size"]
        self.write_lanes(printed, {"standards": [unsized]})

        done = self.report_review(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("size", done.stderr)
        self.assertNotIn("review.head", self.metadata(epic))
        self.assertEqual(4, len(self.review_actions_of(self.next_printed(epic))))

    def test_a_finding_with_a_confidence_outside_high_medium_and_low_is_refused(self):
        epic, printed = self.finish_epic_at_the_review()
        self.write_lanes(printed, {"comments": [finding("Echo", "small", "90")]})

        done = self.report_review(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("confidence", done.stderr)

    def test_a_lane_that_wrote_no_report_is_refused(self):
        epic, printed = self.finish_epic_at_the_review()
        self.write_lanes(printed, {})
        Path(self.review_actions_of(printed)[2]["report"]).unlink()

        done = self.report_review(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("spec", done.stderr)

    def test_lanes_with_no_finding_send_the_epic_on_to_validation(self):
        epic, printed = self.finish_epic_at_the_review()

        moved = self.reviewed(printed, {})

        self.assertEqual("pass", moved["validation"]["result"])
        self.assertIn("human", self.shown(epic)["labels"])


class FixWorkerTests(ReviewCase):
    FINDINGS = {"comments": [finding("Echo", "small", "high")],
                "standards": [finding("Long function", "medium", "medium")],
                "spec": [finding("Unasked flag", "small", "low"), finding("Split the module", "large", "low")]}

    def test_small_and_medium_findings_of_high_or_medium_confidence_go_to_one_fix_worker(self):
        epic, printed = self.finish_epic_at_the_review()

        moved = self.reviewed(printed, self.FINDINGS)

        action = self.fix_action_of(moved)
        self.assertEqual(["Echo", "Long function"], [each["title"] for each in action["findings"]])
        self.assertEqual([BUILT_FILE], action["files"])
        self.assertEqual(["fix"], [each["action"] for each in moved["actions"]])
        self.assertIsNone(moved["validation"])

    def test_low_confidence_findings_are_never_fixed_nor_filed_and_the_gate_lists_them(self):
        epic, printed = self.finish_epic_at_the_review()
        moved = self.reviewed(printed, self.FINDINGS)

        done = self.report_fix(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        fixed = json.loads(done.stdout)
        self.assertEqual(([], []), (moved["review"]["filed"], self.lap_actions(fixed)))
        [gate] = self.gate_comments(epic)
        self.assertIn("Unasked flag", gate)
        self.assertIn("Split the module", gate)
        self.assertNotIn("Echo", gate)

    def test_what_the_fix_worker_changed_lands_in_one_commit_and_validation_runs(self):
        epic, printed = self.finish_epic_at_the_review()
        branch = self.metadata(epic)["factory.branch"]
        moved = self.reviewed(printed, self.FINDINGS)
        self.leave_in(Path(self.fix_action_of(moved)["worktree"]), BUILT_FILE, "total = 2\n")

        done = self.report_fix(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        fixed = json.loads(done.stdout)
        self.assertEqual(FIX_SUBJECT, self.epic_log(epic)[0])
        self.assertEqual("total = 2", test_validation.git(self.repo, "show", f"{branch}:{BUILT_FILE}"))
        self.assertEqual([BUILT_FILE], fixed["fix"]["changed"])
        self.assertEqual("pass", fixed["validation"]["result"])

    def test_a_fix_that_changes_a_file_outside_the_epics_files_is_refused_and_nothing_is_committed(self):
        epic, printed = self.finish_epic_at_the_review()
        branch = self.metadata(epic)["factory.branch"]
        head = test_validation.git(self.repo, "rev-parse", branch)
        moved = self.reviewed(printed, self.FINDINGS)
        self.leave_in(Path(self.fix_action_of(moved)["worktree"]), "reader.txt", "stray\n")

        done = self.report_fix(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("reader.txt", done.stderr)
        self.assertEqual(head, test_validation.git(self.repo, "rev-parse", branch))
        self.assertEqual(["fix"], [each["action"] for each in self.next_printed(epic)["actions"]])

    def test_a_fix_whose_worktree_is_gone_is_refused_instead_of_settled_as_a_fix_that_changed_nothing(self):
        epic, printed = self.finish_epic_at_the_review()
        branch = self.metadata(epic)["factory.branch"]
        head = test_validation.git(self.repo, "rev-parse", branch)
        worktree = Path(self.fix_action_of(self.reviewed(printed, self.FINDINGS))["worktree"])
        self.leave_in(worktree, BUILT_FILE, "total = 2\n")
        test_validation.git(self.repo, "worktree", "remove", "--force", str(worktree))

        done = self.report_fix(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(str(worktree), done.stderr)
        self.assertEqual(head, test_validation.git(self.repo, "rev-parse", branch))
        self.assertEqual(["fix"], [each["action"] for each in self.next_printed(epic)["actions"]])

    def test_a_fix_whose_worktree_moved_to_another_head_is_refused_and_nothing_is_committed(self):
        epic, printed = self.finish_epic_at_the_review()
        branch = self.metadata(epic)["factory.branch"]
        head = test_validation.git(self.repo, "rev-parse", branch)
        worktree = Path(self.fix_action_of(self.reviewed(printed, self.FINDINGS))["worktree"])
        test_validation.git(worktree, "commit", "--allow-empty", "--message", "Moved by hand")

        done = self.report_fix(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(str(worktree), done.stderr)
        self.assertEqual(head, test_validation.git(self.repo, "rev-parse", branch))


class LargeFindingTests(ReviewCase):
    LARGE = {"spec": [finding("Split the till module", "large", "high")]}

    def assert_filed_outside(self, epic: str, task: str) -> None:
        self.assertEqual((None, {("discovered-from", epic)}), (self.shown(task).get("parent"), self.links_of(task)))
        self.assertNotIn(task, self.children_of(epic).values())
        self.assertNotIn("lap.area", self.metadata(task))

    def test_a_large_finding_is_filed_outside_the_epic_linked_discovered_from_it_and_validation_runs(self):
        epic, printed = self.finish_epic_at_the_review()

        moved = self.reviewed(printed, self.LARGE)

        [task] = moved["review"]["filed"]
        self.assert_filed_outside(epic, task)
        self.assertIn("Split the till module", self.shown(task)["title"])
        self.assertIn(epic, self.shown(task)["description"])
        self.assertEqual([], self.lap_actions(moved))
        self.assertEqual("pass", moved["validation"]["result"])

    def test_an_epic_whose_first_review_sizes_a_finding_large_goes_on_to_validation_after_the_fix(self):
        epic, printed = self.finish_epic_at_the_review()
        moved = self.reviewed(printed, {"comments": [finding("Echo", "small", "high")], **self.LARGE})
        [task] = moved["review"]["filed"]
        self.leave_in(Path(self.fix_action_of(moved)["worktree"]), BUILT_FILE, "total = 2\n")

        done = self.report_fix(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        fixed = json.loads(done.stdout)
        self.assertEqual(FIX_SUBJECT, self.epic_log(epic)[0])
        self.assertEqual("pass", fixed["validation"]["result"])
        self.assertEqual([], fixed["actions"])
        self.assert_filed_outside(epic, task)
        self.assertEqual("open", self.shown(task)["status"])


class LaterReviewTests(ReviewCase):
    def test_a_later_review_runs_only_the_diff_lanes_over_the_diff_since_the_last_review(self):
        epic, printed = self.finish_epic_at_the_review()
        first_head = self.review_actions_of(printed)[0]["head"]
        moved, task = self.red_validation(printed)

        second = self.next_pass_review(moved, task, "reader.txt")

        lanes = self.review_actions_of(second)
        self.assertEqual(DIFF_LANES, [each["lane"] for each in lanes])
        self.assertEqual([first_head] * 3, [each["base"] for each in lanes])
        self.assertEqual([["reader.txt"]] * 3, [each["files"] for each in lanes])

    def test_a_later_review_settles_on_the_reports_of_the_three_diff_lanes_and_validation_runs(self):
        epic, printed = self.finish_epic_at_the_review()
        moved, task = self.red_validation(printed)
        second = self.next_pass_review(moved, task, "reader.txt")

        again = self.reviewed(second, {})

        self.assertEqual("pass", again["validation"]["result"])
        self.assertIn("human", self.shown(epic)["labels"])

    def test_a_later_review_diff_holds_none_of_the_hunks_main_brought_in_by_a_merge(self):
        shared = "".join(f"line {number}\n" for number in range(1, 9))
        self.commit_in(self.repo, "shared.txt", shared)
        epic, printed = self.finish_epic_at_the_review()
        branch = self.metadata(epic)["factory.branch"]
        moved, task = self.red_validation(printed)
        [lap] = [each for each in moved["actions"] if each.get("task") == task]
        self.leave_in(Path(lap["worktree"]), "shared.txt", shared.replace("line 1\n", "the epic's line\n"))
        self.tidied(test_scheduler.SchedulerCase.build_done(self, epic, task))
        self.commit_in(self.repo, "shared.txt", shared.replace("line 8\n", "main's line\n"))
        self.merge_main_into(branch)

        lanes = self.review_actions_of(self.next_printed(epic))

        diff = test_validation.git(self.repo, "diff", lanes[0]["base"], lanes[0]["head"], "--", "shared.txt")
        changed = [each for each in diff.splitlines() if each[:1] in "+-" and each[:3] not in ("+++", "---")]
        self.assertEqual(["-line 1", "+the epic's line"], changed)

    def merge_main_into(self, branch: str) -> None:
        """Merges main into the epic branch in a throwaway worktree, as validation does."""
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        tree = scratch / "merge"
        test_validation.git(self.repo, "worktree", "add", "--quiet", "--detach", str(tree), branch)
        test_validation.git(tree, "merge", "--quiet", "--no-edit", "main")
        merged = test_validation.git(tree, "rev-parse", "HEAD")
        test_validation.git(self.repo, "worktree", "remove", "--force", str(tree))
        test_validation.git(self.repo, "update-ref", f"refs/heads/{branch}", merged)


class PassCapTests(ReviewCase):
    def three_passes_each_with_a_red_validation(self) -> tuple[str, dict]:
        epic, printed = self.finish_epic_at_the_review()
        for number in range(2):
            moved, task = self.red_validation(printed)
            printed = self.next_pass_review(moved, task, f"pass-{number}.txt")
        moved, _ = self.red_validation(printed)
        return epic, moved

    def test_the_fourth_pass_parks_the_epic_with_a_question_and_opens_no_lap(self):
        epic, moved = self.three_passes_each_with_a_red_validation()

        self.assertEqual([], self.lap_actions(moved))
        self.assertIn("human", self.shown(epic)["labels"])
        self.assertTrue(any(text.startswith("Question: ") and "3 passes" in text for text in self.texts(epic)))
        self.assertNotIn("gate.state", self.metadata(epic))

    def test_taking_the_human_label_off_runs_the_fourth_pass(self):
        epic, moved = self.three_passes_each_with_a_red_validation()
        task = moved["validation"]["filed"]

        fixture.run([self.bd, "label", "remove", epic, "human"], self.repo)
        again = self.next_printed(epic)

        self.assertEqual([task], [each["task"] for each in self.lap_actions(again)])
        self.assertNotIn("human", self.shown(epic).get("labels") or [])


class EndOfPassTests(ReviewCase):
    def test_a_reviewed_pass_that_ends_in_a_red_validation_is_counted_once_and_starts_the_next_pass_over(self):
        epic, printed = self.finish_epic_at_the_review()
        self.assertEqual("done", self.metadata(epic)["tidy.state"])
        self.queue_validation_exit_codes(epic, 1)

        moved = self.reviewed(printed, {})

        self.assertEqual("fail", moved["validation"]["result"])
        metadata = self.metadata(epic)
        self.assertEqual("1", str(metadata["review.passes"]))
        for key in ("tidy.state", "cleanup.state", "review.reviewed"):
            self.assertNotIn(key, metadata)

    def test_a_reviewed_pass_that_reaches_the_gate_is_counted_once_and_leaves_no_review_flag(self):
        epic, printed = self.finish_epic_at_the_review()

        moved = self.reviewed(printed, {})

        self.assertEqual("pass", moved["validation"]["result"])
        metadata = self.metadata(epic)
        self.assertEqual("1", str(metadata["review.passes"]))
        self.assertNotIn("review.reviewed", metadata)
        self.assertEqual("done", metadata["tidy.state"])


class PassCapWithoutReviewTests(ReviewCase):
    def merge_the_open_task(self, epic: str, printed: dict, removed: str) -> dict:
        """Merges the one task the moves open, which only deletes a file, so no file is left for a review to read."""
        [lap] = [each for each in printed["actions"] if each["action"] == "build"]
        (Path(lap["worktree"]) / removed).unlink()
        return self.tidied(test_scheduler.SchedulerCase.build_done(self, epic, lap["task"]))

    def test_an_epic_with_no_reviewable_file_and_a_red_validation_parks_at_the_third_pass(self):
        for name in ("one.txt", "two.txt", "three.txt"):
            self.commit_in(self.repo, name, "old\n")
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        self.queue_validation_exit_codes(epic, 1, 1, 1, 1)
        printed = self.next_printed(epic)
        for name in ("one.txt", "two.txt"):
            printed = self.merge_the_open_task(epic, printed, name)
            self.assertNotIn("human", self.shown(epic).get("labels") or [])

        printed = self.merge_the_open_task(epic, printed, "three.txt")

        self.assertEqual([], self.lap_actions(printed))
        self.assertIn("human", self.shown(epic)["labels"])
        self.assertTrue(any(text.startswith("Question: ") and "3 passes" in text for text in self.texts(epic)))

    def test_a_pass_with_no_reviewable_file_that_reaches_the_gate_is_counted(self):
        self.commit_in(self.repo, "gone.txt", "old\n")
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})

        printed = self.merge_the_open_task(epic, self.next_printed(epic), "gone.txt")

        self.assertEqual("pass", printed["validation"]["result"])
        self.assertEqual("1", str(self.metadata(epic)["review.passes"]))


if __name__ == "__main__":
    unittest.main()
