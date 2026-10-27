import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_scheduler  # noqa: E402
import test_validation  # noqa: E402

BUILT_FILE = "till.txt"
LANES = ["comments", "standards", "spec", "design"]
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
        self.reviewed(printed, self.FINDINGS)

        done = self.report_fix(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        fixed = json.loads(done.stdout)
        self.assertEqual(([], []), (fixed["fix"]["filed"], self.lap_actions(fixed)))
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


class LargeFindingTests(ReviewCase):
    LARGE = {"spec": [finding("Split the till module", "large", "high")]}

    def test_a_large_finding_becomes_a_task_in_the_epic_whose_lap_opens_and_no_validation_runs(self):
        epic, printed = self.finish_epic_at_the_review()

        moved = self.reviewed(printed, self.LARGE)

        [task] = moved["review"]["filed"]
        shown = self.shown(task)
        self.assertEqual(epic, shown["parent"])
        self.assertIn("Split the till module", shown["title"])
        self.assertEqual([task], [each["task"] for each in self.lap_actions(moved)])
        self.assertIsNone(moved["validation"])
        self.assertEqual([], self.validation_runs_of(epic))

    def test_the_second_pass_reviews_only_the_diff_since_the_first_review(self):
        epic, printed = self.finish_epic_at_the_review()
        first_head = self.review_actions_of(printed)[0]["head"]
        moved = self.reviewed(printed, self.LARGE)
        [task] = moved["review"]["filed"]

        second = self.next_pass_review(moved, task, "reader.txt")

        lanes = self.review_actions_of(second)
        self.assertEqual(LANES, [each["lane"] for each in lanes])
        self.assertEqual([first_head] * 4, [each["base"] for each in lanes])
        self.assertEqual([["reader.txt"]] * 3 + [["reader.txt", BUILT_FILE]], [each["files"] for each in lanes])

    def test_a_large_finding_waits_for_the_fix_and_is_filed_when_the_fix_settles(self):
        epic, printed = self.finish_epic_at_the_review()
        moved = self.reviewed(printed, {"comments": [finding("Echo", "small", "high")], **self.LARGE})
        self.assertEqual(([], []), (moved["review"]["filed"], self.lap_actions(moved)))

        done = self.report_fix(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        fixed = json.loads(done.stdout)
        [task] = fixed["fix"]["filed"]
        self.assertEqual([task], [each["task"] for each in self.lap_actions(fixed)])
        self.assertIsNone(fixed["validation"])
        self.assertEqual(["fix"], [each["action"] for each in moved["actions"]])


class PassCapTests(ReviewCase):
    LARGE = LargeFindingTests.LARGE

    def three_passes_each_with_a_large_finding(self) -> tuple[str, dict]:
        epic, printed = self.finish_epic_at_the_review()
        for number in range(2):
            moved = self.reviewed(printed, self.LARGE)
            [task] = moved["review"]["filed"]
            printed = self.next_pass_review(moved, task, f"pass-{number}.txt")
        return epic, self.reviewed(printed, self.LARGE)

    def test_the_fourth_pass_parks_the_epic_with_a_question_and_opens_no_lap(self):
        epic, moved = self.three_passes_each_with_a_large_finding()

        self.assertEqual([], self.lap_actions(moved))
        self.assertIn("human", self.shown(epic)["labels"])
        self.assertTrue(any(text.startswith("Question: ") and "3 passes" in text for text in self.texts(epic)))
        self.assertNotIn("gate.state", self.metadata(epic))

    def test_taking_the_human_label_off_runs_the_fourth_pass(self):
        epic, moved = self.three_passes_each_with_a_large_finding()
        [task] = moved["review"]["filed"]

        fixture.run([self.bd, "label", "remove", epic, "human"], self.repo)
        again = self.next_printed(epic)

        self.assertEqual([task], [each["task"] for each in self.lap_actions(again)])
        self.assertNotIn("human", self.shown(epic).get("labels") or [])


if __name__ == "__main__":
    unittest.main()
