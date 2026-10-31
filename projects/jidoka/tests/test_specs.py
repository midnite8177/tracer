import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_handoff as handoff  # noqa: E402
import test_handoff_page as handoff_page  # noqa: E402

SPECS = handoff.PLUGIN / "scripts" / "specs.py"
PAYS = "A shopper pays by card and the till prints a receipt"
REFUNDS = "A shopper refunds a card payment"
FULL_FOR_SPEC_TASK = "it is the spec task, whose lap alone changes the code beneath the acceptance specs"


class SpecsCase(handoff_page.HandoffPageCase):
    """The handoff tests' fixture, with a runner for the specs script."""

    def specs(self, *args: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(handoff.LAUNCHER, [str(SPECS), *args], None, self.caller_env(self.home),
                                    self.repo, handoff.RUN_TIMEOUT_SECONDS)

    def printed(self, *args: str) -> dict:
        done = self.specs(*args)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def epic_with_two_tasks(self) -> tuple[str, str, str]:
        epic, _ = self.new_epic()
        return epic, self.new_task_under(epic), self.new_task_under(epic)

    def checked(self, epic: str) -> dict:
        done = self.handoff("check", epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)


class SpecsRecordingTests(SpecsCase):
    def test_an_epic_with_no_spec_task_and_no_specs_shows_neither(self):
        epic, _, _ = self.epic_with_two_tasks()

        self.assertEqual({"epic": epic, "spec_task": "", "tasks": []}, self.printed("show", epic))

    def test_the_spec_task_and_the_specs_each_task_makes_pass_print_back(self):
        epic, first, second = self.epic_with_two_tasks()

        self.printed("spec-task", epic, first)
        self.printed("makes-pass", epic, first, PAYS)
        shown = self.printed("makes-pass", epic, second, PAYS, REFUNDS)

        self.assertEqual({"epic": epic, "spec_task": first,
                          "tasks": [{"id": first, "specs": [PAYS]}, {"id": second, "specs": [PAYS, REFUNDS]}]},
                         shown)
        self.assertEqual(shown, self.printed("show", epic))

    def test_recording_the_specs_of_a_task_again_replaces_them(self):
        epic, first, _ = self.epic_with_two_tasks()
        self.printed("makes-pass", epic, first, PAYS, REFUNDS)

        shown = self.printed("makes-pass", epic, first, REFUNDS, REFUNDS)

        self.assertEqual([{"id": first, "specs": [REFUNDS]}], shown["tasks"])

    def test_naming_another_spec_task_replaces_the_first(self):
        epic, first, second = self.epic_with_two_tasks()
        self.printed("spec-task", epic, first)

        self.assertEqual(second, self.printed("spec-task", epic, second)["spec_task"])

    def test_the_records_are_the_metadata_of_the_epic_and_of_the_task(self):
        epic, first, _ = self.epic_with_two_tasks()

        self.printed("spec-task", epic, first)
        self.printed("makes-pass", epic, first, PAYS)

        self.assertEqual(first, self.shown(epic)["metadata"]["acceptance.spec_task"])
        self.assertEqual([PAYS], json.loads(self.shown(first)["metadata"]["acceptance.specs"]))

    def test_the_specs_planning_marked_as_already_true_are_the_tasks_own_record_and_stay_out_of_show(self):
        epic, first, _ = self.epic_with_two_tasks()
        self.printed("already-true", epic, first, PAYS, REFUNDS)

        shown = self.printed("already-true", epic, first, REFUNDS)

        self.assertEqual({"epic": epic, "spec_task": "", "tasks": []}, shown)
        self.assertEqual([REFUNDS], json.loads(self.shown(first)["metadata"]["acceptance.already_true"]))
        self.assertNotIn("acceptance.specs", self.shown(first)["metadata"])

    def test_a_task_that_the_epic_does_not_hold_is_refused_for_both_records_and_nothing_is_written(self):
        epic, _, _ = self.epic_with_two_tasks()
        other_epic, _ = self.new_epic()
        stranger = self.new_task_under(other_epic)

        named = self.specs("spec-task", epic, stranger)
        passing = self.specs("makes-pass", epic, stranger, PAYS)

        for done in (named, passing):
            self.assertEqual(1, done.returncode)
            self.assertIn(f"{stranger} is not a task of {epic}", done.stderr)
        self.assertEqual({"epic": epic, "spec_task": "", "tasks": []}, self.printed("show", epic))
        self.assertNotIn("acceptance.specs", self.shown(stranger).get("metadata") or {})
        self.assertNotIn("acceptance.spec_task", self.shown(epic).get("metadata") or {})

    def test_a_spec_name_with_no_letter_or_digit_is_refused_and_nothing_is_written(self):
        epic, first, _ = self.epic_with_two_tasks()

        done = self.specs("makes-pass", epic, first, PAYS, "  --  ")

        self.assertEqual(1, done.returncode)
        self.assertIn("needs a letter or a digit", done.stderr)
        self.assertNotIn("acceptance.specs", self.shown(first).get("metadata") or {})

    def test_a_bead_that_is_not_an_epic_is_refused(self):
        _, first, _ = self.epic_with_two_tasks()

        done = self.specs("show", first)

        self.assertEqual(1, done.returncode)
        self.assertIn("not an epic", done.stderr)

    def test_metadata_that_is_not_a_list_of_names_cannot_be_read_and_is_named(self):
        epic, first, _ = self.epic_with_two_tasks()
        fixture.run([self.bd, "update", first, "--set-metadata", "acceptance.specs=not a list"], self.repo)

        done = self.specs("show", epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"acceptance.specs of {first} is not a list of spec names", done.stderr)


class HandoffShowsTheSpecsTests(SpecsCase):
    def test_check_prints_the_specs_of_each_task_and_the_spec_task(self):
        epic, first, second = self.epic_with_two_tasks()
        self.printed("spec-task", epic, first)
        self.printed("makes-pass", epic, second, PAYS, REFUNDS)

        checked = self.checked(epic)

        self.assertEqual(first, checked["spec_task"])
        self.assertEqual({first: [], second: [PAYS, REFUNDS]}, {row["id"]: row["specs"] for row in checked["tasks"]})

    def test_check_proposes_the_full_track_for_the_spec_task_and_the_simple_track_for_the_other(self):
        epic, first, second = self.epic_with_two_tasks()
        self.printed("spec-task", epic, first)

        rows = {row["id"]: row for row in self.checked(epic)["tasks"]}

        self.assertEqual(("full", FULL_FOR_SPEC_TASK), (rows[first]["track"], rows[first]["why"]))
        self.assertEqual("simple", rows[second]["track"])

    def test_the_reason_for_the_spec_task_joins_the_other_reasons_for_the_full_track(self):
        epic, first, _ = self.epic_with_two_tasks()
        self.printed("spec-task", epic, first)
        self.write_holdouts(epic, [{"app": "shop", "tasks": [first], "scenario": handoff.SCENARIO}])

        row = self.checked(epic)["tasks"][0]

        self.assertEqual(f"{FULL_FOR_SPEC_TASK}; named by 1 holdout", row["why"])

    def test_taking_the_epic_shows_the_specs_in_the_comment_and_the_page_and_puts_the_spec_task_on_the_full_track(self):
        epic, first, second = self.epic_with_two_tasks()
        self.printed("spec-task", epic, first)
        self.printed("makes-pass", epic, second, PAYS, REFUNDS)

        done = self.handoff("take", epic, "--area", f"{first}=driver", "--area", f"{second}=till")

        self.assertEqual(0, done.returncode, done.stderr)
        table = self.table_comment(epic)
        self.assertIn(f"| {first} Read the card {self.count - 1} | full | {FULL_FOR_SPEC_TASK} | driver | 0 |  | open |",
                      table)
        self.assertIn(f"| till | 0 | {PAYS}, {REFUNDS} | open |", table)
        self.assertEqual("full", self.shown(first)["metadata"]["lap.track"])
        rows = re.findall(r"(?s)<tr>(.*?)</tr>", self.page_of(epic).read_text(encoding="utf-8").split(
            "The factory rules")[0])
        cells = [re.findall(r"<t[dh]>(.*?)</t[dh]>", row) for row in rows]
        self.assertEqual(["", f"{PAYS}, {REFUNDS}"], [cells[1][5], cells[2][5]])
        self.assertEqual({first: [], second: [PAYS, REFUNDS]},
                         {row["id"]: row["specs"] for row in json.loads(done.stdout)["tasks"]})

    def test_the_human_may_still_flip_the_spec_task_to_the_simple_track(self):
        epic, first, second = self.epic_with_two_tasks()
        self.printed("spec-task", epic, first)

        done = self.handoff("take", epic, "--area", f"{first}=driver", "--area", f"{second}=till", "--track",
                            f"{first}=simple")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("simple", self.shown(first)["metadata"]["lap.track"])

    def test_a_task_that_is_closed_shows_no_row_and_its_specs_are_left_out(self):
        epic, first, second = self.epic_with_two_tasks()
        self.printed("makes-pass", epic, first, PAYS)
        fixture.run([self.bd, "close", first], self.repo)

        checked = self.checked(epic)

        self.assertEqual([second], [row["id"] for row in checked["tasks"]])


if __name__ == "__main__":
    unittest.main()
