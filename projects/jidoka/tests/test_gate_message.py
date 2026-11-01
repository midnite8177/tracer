import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_gate_send_back  # noqa: E402
from test_gate import GATE, MESSAGE  # noqa: E402


class GateMessageCase(test_gate_send_back.SendBackCase):
    def save(self, epic: str, message: str) -> subprocess.CompletedProcess:
        return self.launch(GATE, "message", epic, "--message", message)

    def saved(self, epic: str) -> subprocess.CompletedProcess:
        return self.launch(GATE, "message", epic)


class SavingTheMessageTests(GateMessageCase):
    def test_a_saved_message_is_printed_again_by_a_later_run_and_kept_beside_the_gate_page(self):
        epic, _, _ = self.epic_at_the_gate()

        saving = self.save(epic, MESSAGE)
        reading = self.saved(epic)

        self.assertEqual(0, saving.returncode, saving.stderr)
        self.assertEqual((0, f"{MESSAGE}\n"), (reading.returncode, reading.stdout))
        self.assertEqual(MESSAGE, (self.home / "pages" / "shop" / f"gate-{epic}-message.txt").read_text(
            encoding="utf-8"))

    def test_an_epic_with_no_saved_message_prints_nothing(self):
        epic, _, _ = self.epic_at_the_gate()

        reading = self.saved(epic)

        self.assertEqual((0, ""), (reading.returncode, reading.stdout), reading.stderr)

    def test_a_later_message_replaces_the_one_saved_before(self):
        epic, _, _ = self.epic_at_the_gate()
        self.save(epic, "Take cash at the till")

        self.save(epic, MESSAGE)

        self.assertEqual(f"{MESSAGE}\n", self.saved(epic).stdout)


class RefusedMessageTests(GateMessageCase):
    def test_a_message_that_names_a_bead_is_refused_and_the_one_saved_before_stays(self):
        epic, task, _ = self.epic_at_the_gate()
        self.save(epic, MESSAGE)

        refused = self.save(epic, f"Take card payments for {task}")

        self.assertEqual(1, refused.returncode)
        self.assertIn(task, refused.stderr)
        self.assertEqual(f"{MESSAGE}\n", self.saved(epic).stdout)

    def test_an_empty_message_is_refused_and_nothing_is_saved(self):
        epic, _, _ = self.epic_at_the_gate()

        refused = self.save(epic, "  \n")

        self.assertEqual(1, refused.returncode)
        self.assertIn("empty", refused.stderr)
        self.assertEqual("", self.saved(epic).stdout)

    def test_a_message_for_an_epic_that_does_not_wait_at_the_gate_is_refused_and_nothing_is_saved(self):
        epic = self.new_epic()
        self.new_task_under(epic)

        refused = self.save(epic, MESSAGE)

        self.assertEqual(1, refused.returncode)
        self.assertIn("acceptance gate", refused.stderr)
        self.assertEqual("", self.saved(epic).stdout)


class TheDecisionAndTheSavedMessageTests(GateMessageCase):
    def test_a_merge_that_lands_removes_the_saved_message(self):
        epic, _, _ = self.epic_at_the_gate()
        self.save(epic, MESSAGE)

        landed = self.merge(epic)

        self.assertEqual(0, landed.returncode, landed.stderr)
        self.assertFalse((self.home / "pages" / "shop" / f"gate-{epic}-message.txt").exists())

    def test_a_refused_merge_keeps_the_saved_message_for_the_next_try(self):
        epic, task, _ = self.epic_at_the_gate()
        self.save(epic, MESSAGE)

        refused = self.merge(epic, f"Take card payments for {task}")

        self.assertEqual(1, refused.returncode)
        self.assertEqual(f"{MESSAGE}\n", self.saved(epic).stdout)

    def test_a_drop_removes_the_saved_message(self):
        epic, _, _ = self.epic_at_the_gate()
        self.save(epic, MESSAGE)

        dropped = self.launch(GATE, "drop", epic)

        self.assertEqual(0, dropped.returncode, dropped.stderr)
        self.assertFalse((self.home / "pages" / "shop" / f"gate-{epic}-message.txt").exists())

    def test_a_send_back_keeps_the_saved_message_for_when_the_epic_comes_back(self):
        epic, _, _ = self.epic_at_the_gate()
        self.save(epic, MESSAGE)

        sent = self.send_back(epic, [test_gate_send_back.ROUNDING],
                              [test_gate_send_back.proposal(1, "Round half up on the till", "till", "simple")])

        self.assertEqual(0, sent.returncode, sent.stderr)
        self.assertEqual(f"{MESSAGE}\n", self.saved(epic).stdout)


if __name__ == "__main__":
    unittest.main()
