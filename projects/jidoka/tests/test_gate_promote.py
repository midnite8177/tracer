import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_gate  # noqa: E402
import test_scheduler  # noqa: E402
from test_gate import GATE, HOLDOUTS  # noqa: E402

FIRST = "Pay 5.00 with a card and see the receipt say CARD 5.00."
SECOND = "Pay 5.00 in cash and see the drawer open."


class PromotingAHoldoutCase(test_gate.GateCase):
    """The shop repo with an epic at the gate that holds two holdouts."""

    def epic_with_two_holdouts(self) -> str:
        epic, task, _ = self.epic_at_the_gate()
        holdouts = [{"app": "shop", "tasks": [task], "scenario": FIRST},
                    {"app": "shop", "tasks": [task], "scenario": SECOND}]
        written = fixture.run_launcher(test_scheduler.LAUNCHER, [str(HOLDOUTS), "write", epic], json.dumps(holdouts),
                                       self.caller_env(self.home), self.repo, test_scheduler.RUN_TIMEOUT_SECONDS)
        self.assertEqual(0, written.returncode, written.stderr)
        return epic

    def promote(self, epic: str, number: int):
        return self.launch(GATE, "promote", epic, str(number))

    def promoted_beads(self, epic: str) -> list[dict]:
        return json.loads(self.metadata(epic)["gate.promoted"])


class TheGateOffersPromoteOnEachHoldoutTests(PromotingAHoldoutCase):
    def test_items_list_each_holdout_with_its_number_its_app_and_its_scenario(self):
        epic = self.epic_with_two_holdouts()

        done = self.launch(GATE, "items", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([{"number": 1, "app": "shop", "scenario": FIRST, "promoted": False},
                          {"number": 2, "app": "shop", "scenario": SECOND, "promoted": False}],
                         json.loads(done.stdout)["holdouts"])

    def test_items_list_no_holdout_for_an_epic_that_holds_none(self):
        epic, _, _ = self.epic_at_the_gate()

        done = self.launch(GATE, "items", epic)

        self.assertEqual([], json.loads(done.stdout)["holdouts"])

    def test_promote_marks_the_holdout_promoted_in_the_items_and_leaves_the_epic_at_the_gate(self):
        epic = self.epic_with_two_holdouts()

        done = self.promote(epic, 2)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([False, True],
                         [each["promoted"] for each in json.loads(self.launch(GATE, "items", epic).stdout)["holdouts"]])
        self.assertEqual("waiting", self.metadata(epic)["gate.state"])

    def test_promoting_a_holdout_twice_records_it_once(self):
        epic = self.epic_with_two_holdouts()

        self.promote(epic, 1)
        again = self.promote(epic, 1)

        self.assertEqual(0, again.returncode, again.stderr)
        self.assertEqual([{"holdout": 1, "bead": None}], self.promoted_beads(epic))

    def test_promote_refuses_a_number_the_epic_has_no_holdout_for_and_writes_nothing(self):
        epic = self.epic_with_two_holdouts()

        done = self.promote(epic, 3)

        self.assertEqual(1, done.returncode)
        self.assertIn("no holdout 3", done.stderr)
        self.assertNotIn("gate.promoted", self.metadata(epic))

    def test_promote_refuses_an_epic_that_does_not_wait_at_the_gate(self):
        epic = self.new_epic()

        done = self.promote(epic, 1)

        self.assertEqual(1, done.returncode)
        self.assertIn("acceptance gate", done.stderr)


class LandingFilesAPlanningBeadForEachPromotedHoldoutTests(PromotingAHoldoutCase):
    def planning_bead_of(self, epic: str, number: int) -> dict:
        [entry] = [each for each in self.promoted_beads(epic) if each["holdout"] == number]
        self.assertIsNotNone(entry["bead"])
        return self.shown(entry["bead"])

    def test_landing_files_a_bead_with_the_promoted_scenario_the_human_label_and_no_parent(self):
        epic = self.epic_with_two_holdouts()
        self.promote(epic, 2)

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        filed = self.planning_bead_of(epic, 2)
        self.assertIn(SECOND, filed["description"])
        self.assertNotIn(FIRST, filed["description"])
        self.assertEqual(["human"], filed["labels"])
        self.assertNotIn("parent", filed)
        self.assertEqual("open", filed["status"])

    def test_landing_files_a_bead_for_each_promoted_holdout_and_none_for_the_others(self):
        epic = self.epic_with_two_holdouts()
        self.promote(epic, 1)
        self.promote(epic, 2)

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([1, 2], [each["holdout"] for each in self.promoted_beads(epic)])
        self.assertEqual(2, len({each["bead"] for each in self.promoted_beads(epic)}))

    def test_a_holdout_not_promoted_retires_at_landing(self):
        epic = self.epic_with_two_holdouts()
        self.promote(epic, 1)

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("holdouts", self.metadata(epic))
        self.assertEqual([], json.loads(self.launch(HOLDOUTS, "read", epic).stdout))
        self.assertEqual("closed", self.shown(epic)["status"])

    def test_landing_with_no_promotion_files_no_bead(self):
        epic = self.epic_with_two_holdouts()
        before = self.listed_ids()

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(before, self.listed_ids())
        self.assertNotIn("gate.promoted", self.metadata(epic))

    def test_running_the_merge_again_files_no_second_bead(self):
        epic = self.epic_with_two_holdouts()
        self.promote(epic, 1)
        self.assertEqual(0, self.merge(epic).returncode)
        before = self.listed_ids()

        again = self.merge(epic)

        self.assertEqual(0, again.returncode, again.stderr)
        self.assertEqual(before, self.listed_ids())

    def listed_ids(self) -> list[str]:
        listed = json.loads(fixture.run([self.bd, "list", "--all", "--limit", "0", "--json"], self.repo))
        return sorted(str(each["id"]) for each in listed)


if __name__ == "__main__":
    unittest.main()
