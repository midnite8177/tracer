import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_scheduler  # noqa: E402
import test_validation  # noqa: E402

BUILT_FILE = "till.txt"
OTHER_FILE = "README.md"
COMMENTED = "total = 1  # add one\n"
CLEAN = "total = 1\n"
TIDY_SUBJECT = "No comments and unslop"


class TidyCase(test_validation.ValidationCase):
    def finish_epic_whose_task_built_a_commented_file(self) -> tuple[str, str, dict]:
        """An epic with one task whose build leaves a commented file; returns the epic, the
        task and the moves printed when the task merged, which end with the tidy."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), BUILT_FILE, COMMENTED)
        return epic, task, test_scheduler.SchedulerCase.build_done(self, epic, task)

    def finish_epic_whose_task_built(self, files: dict[str, str]) -> tuple[str, dict]:
        """An epic with one task whose build leaves the files; returns the epic and the moves printed when the task
        merged, which end with the tidy."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        for name, text in files.items():
            self.leave_in(Path(action["worktree"]), name, text)
        return epic, test_scheduler.SchedulerCase.build_done(self, epic, task)

    def tidy_actions_of(self, printed: dict) -> list[dict]:
        return [each for each in printed["actions"] if each["action"] == "tidy"]

    def tidy_action_of(self, printed: dict) -> dict:
        [action] = self.tidy_actions_of(printed)
        return action

    def report_tidy(self, epic: str) -> subprocess.CompletedProcess:
        return self.launch(test_scheduler.SCHEDULER, "report-tidy", epic)

    def epic_log(self, epic: str) -> list[str]:
        branch = self.metadata(epic)["factory.branch"]
        return test_validation.git(self.repo, "log", "--format=%s", f"main..{branch}").splitlines()

    def tidy_by_hand(self, action: dict, text: str) -> None:
        self.leave_in(Path(action["worktree"]), BUILT_FILE, text)


class TidyStartsAfterTheTestCleanupTests(TidyCase):
    def test_the_pass_prints_one_tidy_action_over_the_files_of_the_epic_and_runs_no_validation(
            self):
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()

        action = self.tidy_action_of(printed)

        self.assertEqual([BUILT_FILE], action["files"])
        self.assertIsNone(printed["validation"])
        self.assertNotIn("gate.state", self.metadata(epic))
        self.assertEqual([], self.validation_runs_of(epic))
        self.assertTrue(Path(action["worktree"]).is_dir())

    def test_each_tidy_action_carries_the_epics_base_and_no_diff(self):
        files = {f"till_{number}.txt": f"total = {number}  # add one\n" for number in range(1, 6)}
        _, printed = self.finish_epic_whose_task_built(files)

        actions = self.tidy_actions_of(printed)

        self.assertEqual(2, len(actions))
        for action in actions:
            self.assertEqual(test_validation.git(self.repo, "rev-parse", "main"), action["base"])
            self.assertNotIn("diff", action)

    def test_no_tidy_starts_while_a_task_of_the_epic_is_still_open(self):
        epic = self.new_epic()
        first = self.new_task_under(epic)
        second = self.new_task_under(epic)
        self.hand_off(epic, {first: "till", second: "reader"})
        laps = {each["task"]: each for each in self.next_printed(epic)["actions"]}
        self.leave_in(Path(laps[first]["worktree"]), BUILT_FILE, COMMENTED)

        printed = test_scheduler.SchedulerCase.build_done(self, epic, first)

        self.assertEqual([], [each for each in printed["actions"] if each["action"] == "tidy"])


class TidyCommitsTests(TidyCase):
    def test_what_the_worker_changed_lands_in_one_commit_of_its_own_and_the_epic_goes_on_to_the_review(self):
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        branch = self.metadata(epic)["factory.branch"]
        self.tidy_by_hand(self.tidy_action_of(printed), CLEAN)

        done = self.report_tidy(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        moved = json.loads(done.stdout)
        self.assertEqual(TIDY_SUBJECT, self.epic_log(epic)[0])
        self.assertEqual([BUILT_FILE], self.files_of(branch))
        self.assertEqual(CLEAN.strip(), test_validation.git(self.repo, "show", f"{branch}:{BUILT_FILE}"))
        self.assertEqual([BUILT_FILE], moved["tidy"]["changed"])
        self.assertEqual(["review"] * 4, [each["action"] for each in moved["actions"]])
        self.assertEqual("pass", self.settle_tidy_and_review(moved)["validation"]["result"])
        self.assertEqual("done", self.metadata(epic)["tidy.state"])

    def test_a_tidy_that_changes_nothing_makes_no_commit_and_the_pass_goes_on(self):
        epic, _, _ = self.finish_epic_whose_task_built_a_commented_file()
        before = self.epic_log(epic)

        done = self.report_tidy(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(before, self.epic_log(epic))
        self.assertEqual("pass", self.settle_tidy_and_review(json.loads(done.stdout))["validation"]["result"])

    def test_the_tidy_runs_once_per_pass_so_the_next_call_prints_no_tidy_action(self):
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        self.tidy_by_hand(self.tidy_action_of(printed), CLEAN)
        self.assertEqual(0, self.report_tidy(epic).returncode)

        again = self.next_printed(epic)

        self.assertEqual([], [each for each in again["actions"] if each["action"] == "tidy"])
        self.assertEqual(1, self.epic_log(epic).count(TIDY_SUBJECT))

    def test_a_tidy_that_adds_a_new_file_commits_it_with_the_epic_files(self):
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        branch = self.metadata(epic)["factory.branch"]
        action = self.tidy_action_of(printed)
        self.tidy_by_hand(action, CLEAN)
        self.leave_in(Path(action["worktree"]), "till_totals.txt", CLEAN)

        done = self.report_tidy(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(CLEAN.strip(), test_validation.git(self.repo, "show", f"{branch}:till_totals.txt"))

    def test_a_tidy_that_adds_a_file_in_an_acceptance_folder_is_refused_and_nothing_is_committed(self):
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        branch = self.metadata(epic)["factory.branch"]
        head = test_validation.git(self.repo, "rev-parse", branch)
        action = self.tidy_action_of(printed)
        self.tidy_by_hand(action, CLEAN)
        spec = f"{test_scheduler.ACCEPTANCE}/till.feature"
        self.leave_in(Path(action["worktree"]), spec, CLEAN)

        done = self.report_tidy(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(spec, done.stderr)
        self.assertEqual(head, test_validation.git(self.repo, "rev-parse", branch))
        self.assertNotIn("tidy.state", self.metadata(epic))

    def test_a_change_to_a_file_outside_the_epics_files_is_refused_and_nothing_is_committed(self):
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        branch = self.metadata(epic)["factory.branch"]
        head = test_validation.git(self.repo, "rev-parse", branch)
        action = self.tidy_action_of(printed)
        self.tidy_by_hand(action, CLEAN)
        self.leave_in(Path(action["worktree"]), OTHER_FILE, CLEAN)

        done = self.report_tidy(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(OTHER_FILE, done.stderr)
        self.assertEqual(head, test_validation.git(self.repo, "rev-parse", branch))
        self.assertNotIn("tidy.state", self.metadata(epic))

    def test_a_report_for_an_epic_that_waits_on_no_tidy_is_refused(self):
        epic = self.new_epic()

        done = self.report_tidy(epic)

        self.assertEqual(1, done.returncode)

    def test_a_red_validation_makes_the_next_pass_tidy_again(self):
        epic, _, _ = self.finish_epic_whose_task_built_a_commented_file()
        self.queue_validation_exit_codes(epic, 1)

        done = self.report_tidy(epic)

        self.assertEqual("fail", self.settle_tidy_and_review(json.loads(done.stdout))["validation"]["result"])
        self.assertNotIn("tidy.state", self.metadata(epic))


class TidyBatchesTests(TidyCase):
    def test_an_epic_that_changed_twenty_seven_files_gets_batches_of_at_most_four_files_that_hold_each_file_once(
            self):
        files = {f"till_{number:02}.txt": COMMENTED for number in range(1, 28)}
        _, printed = self.finish_epic_whose_task_built(files)

        batches = [each["files"] for each in self.tidy_actions_of(printed)]

        self.assertEqual(sorted(files), sorted(path for batch in batches for path in batch))
        self.assertEqual(27, len({path for batch in batches for path in batch}))
        self.assertEqual([], [batch for batch in batches if not 1 <= len(batch) <= 4])

    def test_the_batches_share_one_worktree_and_one_head_and_each_has_a_scratch_folder_of_its_own(self):
        _, printed = self.finish_epic_whose_task_built({f"till_{number}.txt": COMMENTED for number in range(1, 10)})

        actions = self.tidy_actions_of(printed)

        self.assertEqual(1, len({(each["worktree"], each["head"]) for each in actions}))
        self.assertEqual(len(actions), len({each["scratch"] for each in actions}))
        self.assertTrue(all(Path(each["scratch"]).is_dir() for each in actions))
        self.assertIsNone(printed["validation"])

    def test_a_file_too_large_to_share_a_batch_gets_a_batch_of_its_own(self):
        _, printed = self.finish_epic_whose_task_built(
            {"till_a.txt": COMMENTED, "till_b.txt": "total = 1\n" * 10_000, "till_c.txt": COMMENTED})

        batches = [each["files"] for each in self.tidy_actions_of(printed)]

        self.assertIn(["till_b.txt"], batches)

    def test_the_batches_are_the_same_on_every_call_until_the_tidy_is_reported(self):
        epic, printed = self.finish_epic_whose_task_built({f"till_{number}.txt": COMMENTED for number in range(1, 10)})

        again = self.next_printed(epic)

        self.assertEqual(self.tidy_actions_of(printed), self.tidy_actions_of(again))

    def test_one_report_commits_what_every_batch_changed_in_one_commit(self):
        files = {f"till_{number}.txt": COMMENTED for number in range(1, 10)}
        epic, printed = self.finish_epic_whose_task_built(files)
        branch = self.metadata(epic)["factory.branch"]
        actions = self.tidy_actions_of(printed)
        cleaned = [actions[0]["files"][0], actions[-1]["files"][-1]]
        for name in cleaned:
            self.leave_in(Path(actions[0]["worktree"]), name, CLEAN)

        done = self.report_tidy(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(sorted(cleaned), sorted(json.loads(done.stdout)["tidy"]["changed"]))
        self.assertEqual(1, self.epic_log(epic).count(TIDY_SUBJECT))
        self.assertEqual(sorted(cleaned), self.files_of(branch))
        self.assertEqual([], self.tidy_actions_of(json.loads(done.stdout)))

    def test_the_work_each_batch_discovered_is_filed_and_work_two_batches_found_is_filed_once(self):
        epic, printed = self.finish_epic_whose_task_built({f"till_{number}.txt": COMMENTED for number in range(1, 10)})
        first, *_, last = self.tidy_actions_of(printed)
        shared = {"title": "Round the receipt total", "description": "The till rounds down.", "placement": "outside"}
        own = {"title": "Sweep the till", "description": "The till keeps old totals.", "placement": "outside"}
        self.leave_in(Path(first["scratch"]), "discovered.json", json.dumps([shared]))
        self.leave_in(Path(last["scratch"]), "discovered.json", json.dumps([shared, own]))

        done = self.report_tidy(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({("discovered-from", epic)}, self.links_of(self.bead_titled("Sweep the till")))
        self.assertEqual({("discovered-from", epic)}, self.links_of(self.bead_titled("Round the receipt total")))


class TidyDiscoveredWorkTests(TidyCase):
    def finding(self, title: str, placement: str) -> dict:
        return {"title": title, "description": f"Seen while tidying the till: {title}", "placement": placement}

    def epic_tidied_with_findings(self, *findings: dict) -> tuple[str, dict]:
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        action = self.tidy_action_of(printed)
        self.tidy_by_hand(action, CLEAN)
        self.leave_in(Path(action["scratch"]), "discovered.json", json.dumps(list(findings)))
        return epic, action

    def test_a_finding_the_epic_cannot_be_accepted_without_becomes_a_task_of_the_epic_with_no_other_link(self):
        epic, _ = self.epic_tidied_with_findings(self.finding("Round the receipt total", "epic"))

        done = self.report_tidy(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        filed = self.children_of(epic)["Round the receipt total"]
        self.assertEqual({("parent-child", epic)}, self.links_of(filed))
        metadata = self.metadata(filed)
        self.assertEqual(("tidy", "simple"), (metadata["lap.area"], metadata["lap.track"]))
        self.assertEqual([filed], [action["task"] for action in self.lap_actions(json.loads(done.stdout))])

    def test_a_finding_that_acceptance_does_not_need_is_filed_outside_the_epic_linked_discovered_from_it(self):
        epic, _ = self.epic_tidied_with_findings(self.finding("Sweep the till", "outside"))

        done = self.report_tidy(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        outside = self.bead_titled("Sweep the till")
        self.assertEqual((None, {("discovered-from", epic)}),
                         (self.shown(outside).get("parent"), self.links_of(outside)))
        self.assertNotIn("Sweep the till", self.children_of(epic))
        self.assertNotIn("lap.area", self.metadata(outside))

    def test_the_tidy_commit_lands_on_the_epic_branch_when_the_tidy_found_work(self):
        epic, _ = self.epic_tidied_with_findings(self.finding("Round the receipt total", "epic"),
                                    self.finding("Sweep the till", "outside"))
        branch = self.metadata(epic)["factory.branch"]

        done = self.report_tidy(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(TIDY_SUBJECT, self.epic_log(epic)[0])
        self.assertEqual(CLEAN.strip(), test_validation.git(self.repo, "show", f"{branch}:{BUILT_FILE}"))
        self.assertEqual("done", self.metadata(epic)["tidy.state"])

    def test_a_finding_the_tidy_cannot_place_is_refused_and_nothing_is_filed_or_committed(self):
        epic, action = self.epic_tidied_with_findings(self.finding("Round the receipt total", "blocks"))
        branch = self.metadata(epic)["factory.branch"]
        head = test_validation.git(self.repo, "rev-parse", branch)
        children = self.children_of(epic)

        done = self.report_tidy(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("blocks", done.stderr)
        self.assertEqual(children, self.children_of(epic))
        self.assertEqual(head, test_validation.git(self.repo, "rev-parse", branch))
        self.assertNotIn("tidy.state", self.metadata(epic))
        self.assertTrue(Path(action["worktree"]).is_dir())

    def test_an_unusable_discovered_work_report_is_refused_and_nothing_is_committed(self):
        epic, action = self.epic_tidied_with_findings()
        self.leave_in(Path(action["scratch"]), "discovered.json", "Round the receipt total")
        branch = self.metadata(epic)["factory.branch"]
        head = test_validation.git(self.repo, "rev-parse", branch)

        done = self.report_tidy(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("discovered.json", done.stderr)
        self.assertEqual(head, test_validation.git(self.repo, "rev-parse", branch))
        self.assertNotIn("tidy.state", self.metadata(epic))


if __name__ == "__main__":
    unittest.main()
