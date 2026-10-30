import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_gate  # noqa: E402
from test_gate import GATE, git  # noqa: E402

T3_WAKE = test_gate.test_scheduler.PLUGIN / "scripts" / "t3_wake.py"


class DroppingTheEpicTests(test_gate.GateCase):
    def drop(self, epic: str):
        return self.launch(GATE, "drop", epic)

    def test_dropping_closes_the_epic_and_takes_its_factory_and_human_labels_off(self):
        epic, _, _ = self.epic_at_the_gate()

        done = self.drop(epic)

        shown = self.shown(epic)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("closed", shown["status"])
        self.assertIn("Dropped", shown["close_reason"])
        self.assertEqual([], shown.get("labels") or [])
        self.assertEqual("drop", shown["metadata"]["gate.decision"])

    def test_dropping_keeps_the_epic_branch_and_lands_nothing_on_main(self):
        epic, _, branch = self.epic_at_the_gate()
        main_before = git(self.repo, "rev-parse", "main")
        branch_head = git(self.repo, "rev-parse", branch)

        done = self.drop(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(main_before, git(self.repo, "rev-parse", "main"))
        self.assertEqual(branch_head, git(self.repo, "rev-parse", branch))
        self.assertIn(branch, done.stdout)

    def test_dropping_ends_a_lap_still_open_on_one_of_the_epic_s_tasks_and_keeps_its_work(self):
        epic, _, _ = self.epic_at_the_gate()
        running = self.new_task_under(epic)
        worktree = self.root / f"lap-{running}"
        git(self.repo, "worktree", "add", "-q", "-b", f"lap/{running}", str(worktree), "main")
        self.addCleanup(lambda: git(self.repo, "worktree", "prune"))
        fixture.run([self.bd, "update", running, "--claim", "--set-metadata", "lap.stage=build",
                     "--set-metadata", "lap.number=1", "--set-metadata", "lap.slot=1", "--set-metadata",
                     "lap.tries=0", "--set-metadata", f"lap.workspace={worktree}", "--set-metadata",
                     f"lap.branch=lap/{running}"], self.repo)

        done = self.drop(epic)

        shown = self.shown(running)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(("open", "", "interrupted"), (shown["status"], shown.get("assignee") or "",
                                                       shown["metadata"]["lap.stage"]))
        self.assertTrue(worktree.is_dir())
        self.assertIn(f"lap/{running}", git(self.repo, "branch", "--list"))
        self.assertIn(running, done.stdout)

    def test_an_epic_that_does_not_wait_at_the_gate_is_refused_and_stays_open(self):
        epic = self.new_epic()
        self.new_task_under(epic)

        done = self.drop(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("acceptance gate", done.stderr)
        self.assertEqual("open", self.shown(epic)["status"])

    def test_dropping_deletes_the_epic_s_t3_thread_record(self):
        epic, _, _ = self.epic_at_the_gate()
        recorded = self.launch(T3_WAKE, "record", epic, "--thread", "thread-7")
        self.assertEqual(0, recorded.returncode, recorded.stderr)
        self.assertTrue((self.home / "t3-thread" / f"{epic}.json").is_file())

        done = self.drop(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertFalse((self.home / "t3-thread" / f"{epic}.json").exists())

    def test_the_merge_refuses_a_dropped_epic(self):
        epic, _, _ = self.epic_at_the_gate()
        self.drop(epic)
        main_before = git(self.repo, "rev-parse", "main")

        done = self.merge(epic)

        self.assertEqual(1, done.returncode)
        self.assertEqual(main_before, git(self.repo, "rev-parse", "main"))


class TakingTheHumanLabelOffTheGateTests(test_gate.GateCase):
    def take_the_label_off(self, epic: str) -> None:
        fixture.run([self.bd, "label", "remove", epic, "human"], self.repo)

    def test_the_epic_is_parked_again_with_a_comment_when_its_label_comes_off_with_no_decision(self):
        epic, _, _ = self.epic_at_the_gate()
        self.take_the_label_off(epic)

        printed = self.next_printed(epic)

        shown = self.shown(epic)
        self.assertIn("human", shown["labels"])
        self.assertEqual("waiting", shown["metadata"]["gate.state"])
        self.assertEqual([], printed["actions"])
        self.assertIn("still waits at the acceptance gate", self.texts(epic)[-1])

    def test_a_parked_again_epic_can_still_be_merged(self):
        epic, _, _ = self.epic_at_the_gate()
        self.take_the_label_off(epic)
        self.next_printed(epic)

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("closed", self.shown(epic)["status"])

    def test_an_epic_that_keeps_its_label_at_the_gate_gets_no_new_comment(self):
        epic, _, _ = self.epic_at_the_gate()
        before = self.texts(epic)

        self.next_printed(epic)

        self.assertEqual(before, self.texts(epic))


if __name__ == "__main__":
    unittest.main()
