import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture
import test_gate
import test_scheduler
import test_validation

NOTIFY = test_scheduler.PLUGIN / "scripts" / "notify.py"
git = test_gate.git


class BackToValidationCase(test_gate.GateCase):
    """An epic at the gate that another epic's landing moved main under, and the manager that carries it on."""

    def epic_at_the_gate_with_a_clash_on_main(self) -> tuple[str, str]:
        """An epic at the gate whose task wrote a file that main wrote too; returns the epic and the file."""
        epic, task, _, worktree = self.epic_building_in_its_lap()
        clash = f"clash-{task}.txt"
        self.leave_in(worktree, clash, f"the epic's {epic}\n")
        self.build_done(epic, task)
        self.commit_in(self.repo, clash, f"main's {epic}\n")
        return epic, clash

    def epic_at_the_gate_with_main_moved(self) -> tuple[str, str]:
        """An epic at the gate whose rebuild on main merges cleanly and whose full suite fails on the rebuild; returns
        the epic and its task."""
        epic, task, _ = self.epic_at_the_gate()
        self.commit_in(self.repo, f"moved-{task}.txt", "main moved\n")
        self.queue_landing_exit_codes(epic, 1)
        return epic, task

    def carry_on(self, epic: str) -> dict:
        done = self.launch(test_scheduler.SCHEDULER, "carry-on", epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def announce(self, epic: str) -> subprocess.CompletedProcess:
        return self.launch(NOTIFY, "acceptance-gate", epic)

    def announced(self, epic: str) -> str:
        return json.loads(self.metadata(epic)["notification"])[f"acceptance-gate:{epic}"]["fingerprint"]

    def refusal_comments(self, epic: str) -> list[str]:
        return [text for text in self.texts(epic) if text.startswith("Landing")]

    def assert_off_the_gate(self, epic: str) -> None:
        shown = self.shown(epic)
        self.assertEqual("open", shown["status"])
        self.assertNotIn("gate.state", shown.get("metadata") or {})
        self.assertNotIn("human", shown.get("labels") or [])
        self.assertIn("factory", shown["labels"])


class AMergeThatConflictsWithMainTests(BackToValidationCase):
    def test_the_merge_posts_the_conflicting_files_takes_the_epic_off_the_gate_and_leaves_main_alone(self):
        epic, clash = self.epic_at_the_gate_with_a_clash_on_main()
        main_before = git(self.repo, "rev-parse", "main")

        done = self.merge(epic)

        self.assertEqual(test_gate.FULL_SUITE_FAILED_EXIT_CODE, done.returncode)
        self.assertEqual(main_before, git(self.repo, "rev-parse", "main"))
        self.assert_off_the_gate(epic)
        [comment] = self.refusal_comments(epic)
        self.assertIn(clash, comment)
        self.assertIn("validation again", comment)
        self.assertFalse((self.repo / ".worktrees" / f"landing-{epic}").exists())

    def test_an_epic_parked_at_its_pass_cap_stays_parked_with_a_comment_that_says_to_merge_main_by_hand(self):
        epic, clash = self.epic_at_the_gate_with_a_clash_on_main()
        fixture.run([self.bd, "update", epic, "--unset-metadata", "gate.state", "--set-metadata", "review.passes=3",
                     "--set-metadata", "pass.asked=3"], self.repo)
        self.new_task_under(epic)
        main_before = git(self.repo, "rev-parse", "main")

        done = self.merge(epic)

        shown = self.shown(epic)
        self.assertEqual(test_gate.FULL_SUITE_FAILED_EXIT_CODE, done.returncode)
        self.assertEqual(main_before, git(self.repo, "rev-parse", "main"))
        self.assertIn("human", shown["labels"])
        [comment] = self.refusal_comments(epic)
        self.assertIn(clash, comment)
        self.assertIn("stays parked. Merge main into the epic branch by hand", comment)

    def test_the_next_scheduler_call_prints_a_merge_action_for_validation_and_nothing_else(self):
        epic, clash = self.epic_at_the_gate_with_a_clash_on_main()
        self.merge(epic)

        printed = self.carry_on(epic)

        [action] = printed["actions"]
        self.assertEqual(("merge", [clash]), (action["action"], action["files"]))
        self.assertEqual(self.repo / ".worktrees" / f"validation-{epic}", Path(action["worktree"]))
        self.assert_off_the_gate(epic)

    def test_the_epic_comes_back_to_the_gate_with_a_new_notification_once_the_merge_worker_has_merged_main(self):
        epic, clash = self.epic_at_the_gate_with_a_clash_on_main()
        self.announce(epic)
        announced_before = self.announced(epic)
        gate_head_before = self.metadata(epic)["validation.head"]
        self.merge(epic)
        [action] = self.carry_on(epic)["actions"]
        self.reconcile(Path(action["worktree"]), clash)

        reported = self.launch(test_scheduler.SCHEDULER, "report-merge", epic)
        self.announce(epic)

        shown = self.shown(epic)
        self.assertEqual(0, reported.returncode, reported.stderr)
        self.assertEqual("waiting", shown["metadata"]["gate.state"])
        self.assertIn("human", shown["labels"])
        self.assertNotEqual(gate_head_before, shown["metadata"]["validation.head"])
        self.assertEqual(2, len(self.gate_comments(epic)))
        self.assertNotEqual(announced_before, self.announced(epic))

    def test_the_epic_lands_on_the_second_merge_without_running_the_full_suite_again(self):
        epic, clash = self.epic_at_the_gate_with_a_clash_on_main()
        self.merge(epic)
        [action] = self.carry_on(epic)["actions"]
        self.reconcile(Path(action["worktree"]), clash)
        self.launch(test_scheduler.SCHEDULER, "report-merge", epic)

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("closed", self.shown(epic)["status"])
        self.assertEqual([], self.landing_runs_of(epic))


class AMergeWhoseFullSuiteFailsTests(BackToValidationCase):
    def test_the_merge_posts_the_failing_commands_takes_the_epic_off_the_gate_and_leaves_main_alone(self):
        epic, _ = self.epic_at_the_gate_with_main_moved()
        main_before = git(self.repo, "rev-parse", "main")

        done = self.merge(epic)

        self.assertEqual(test_gate.FULL_SUITE_FAILED_EXIT_CODE, done.returncode)
        self.assertEqual(main_before, git(self.repo, "rev-parse", "main"))
        self.assert_off_the_gate(epic)
        [comment] = self.refusal_comments(epic)
        self.assertIn("FAIL: test_till_total", comment)
        self.assertIn(test_validation.SKIP_HAND_RUN, comment)
        self.assertIn("validation again", comment)
        self.assertFalse((self.repo / ".worktrees" / f"landing-{epic}").exists())

    def test_the_next_scheduler_call_validates_the_epic_with_main_merged_and_puts_it_back_at_the_gate(self):
        epic, _ = self.epic_at_the_gate_with_main_moved()
        self.announce(epic)
        announced_before = self.announced(epic)
        self.merge(epic)

        printed = self.carry_on(epic)
        self.announce(epic)

        shown = self.shown(epic)
        head = printed["validation"]["head"]
        self.assertEqual(([], "pass"), (printed["actions"], printed["validation"]["result"]))
        self.assertTrue(self.is_on(git(self.repo, "rev-parse", "main"), head))
        self.assertEqual(head, shown["metadata"]["validation.head"])
        self.assertEqual("waiting", shown["metadata"]["gate.state"])
        self.assertIn("human", shown["labels"])
        self.assertEqual(f"{test_validation.SKIP_HAND_RUN} {head}", self.validation_runs_of(epic)[-1])
        self.assertEqual(2, len(self.validation_runs_of(epic)))
        self.assertNotEqual(announced_before, self.announced(epic))

    def test_the_holdouts_run_again_on_the_epic_merged_with_main(self):
        epic, task = self.epic_at_the_gate_with_main_moved()
        written = fixture.run_launcher(test_scheduler.LAUNCHER, [str(test_validation.HOLDOUTS), "write", epic],
                                       json.dumps([{"app": "shop", "tasks": [task],
                                                    "scenario": test_validation.SCENARIO}]),
                                       self.caller_env(self.home), self.repo, None)
        self.assertEqual(0, written.returncode, written.stderr)
        self.merge(epic)

        printed = self.carry_on(epic)

        [action] = printed["actions"]
        self.assertEqual(("holdouts", "pending"), (action["action"], printed["validation"]["result"]))
        self.assertTrue(self.is_on(git(self.repo, "rev-parse", "main"), action["head"]))
        self.assertNotIn("gate.state", self.metadata(epic))


if __name__ == "__main__":
    unittest.main()
