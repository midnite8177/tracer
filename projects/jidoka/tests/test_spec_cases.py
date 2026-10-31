import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_handoff as handoff  # noqa: E402
import test_specs as specs_tests  # noqa: E402

SPEC_CASES = handoff.PLUGIN / "scripts" / "spec_cases.py"
PAYS = "A shopper pays by card and the till prints a receipt"
REFUNDS = "A shopper refunds a card payment and gets the money back"
CASES = [
    {"name": PAYS, "reading": "Pay 5.00 by card and the till prints receipt 1.",
     "deletion": "No. Without card payment there is no receipt, so the spec fails."},
    {"name": REFUNDS, "reading": "Refund the card payment and the till shows 0.00 owed.",
     "deletion": "No. Without refunds the till still shows 5.00, so the spec fails."},
]
INTERFACE = [{"interface": "Pay by card", "shape": "`till pay --card <amount>`", "cases": [1, 2]},
             {"interface": "Refund a payment", "shape": "`till refund <receipt>`", "cases": [2]}]
APPROVED = {"cases": CASES, "interface": INTERFACE}
SECTION_HEAD = "## Acceptance specs"


class SpecCasesCase(specs_tests.SpecsCase):
    """The specs tests' fixture, with a runner for the spec cases script and an epic whose spec task is recorded."""

    def spec_cases(self, mode: str, epic: str, stdin: str = "") -> subprocess.CompletedProcess:
        return fixture.run_launcher(handoff.LAUNCHER, [str(SPEC_CASES), mode, epic], stdin,
                                    self.caller_env(self.home), self.repo, handoff.RUN_TIMEOUT_SECONDS)

    def written(self, epic: str, approved: object) -> str:
        done = self.spec_cases("write", epic, json.dumps(approved))
        self.assertEqual(0, done.returncode, done.stderr)
        return done.stdout

    def epic_with_a_spec_task(self) -> tuple[str, str, str]:
        epic, spec_task, other = self.epic_with_two_tasks()
        self.printed("spec-task", epic, spec_task)
        return epic, spec_task, other

    def description(self, task: str) -> str:
        return str(self.shown(task).get("description") or "")


class SpecCasesWriteTests(SpecCasesCase):
    def test_the_approved_cases_land_on_the_spec_task_with_their_readings_and_deletion_answers(self):
        epic, spec_task, _ = self.epic_with_a_spec_task()

        self.written(epic, APPROVED)

        description = self.description(spec_task)
        self.assertIn(f"1. {PAYS}\n   - Plain reading: Pay 5.00 by card and the till prints receipt 1.\n"
                      "   - If this feature were deleted: No. Without card payment there is no receipt, so the "
                      "spec fails.\n", description)
        self.assertIn(f"2. {REFUNDS}\n   - Plain reading: Refund the card payment and the till shows 0.00 owed.\n"
                      "   - If this feature were deleted: No. Without refunds the till still shows 5.00, so the "
                      "spec fails.", description)

    def test_the_interface_table_lists_each_interface_the_driver_lacks_with_its_shape_and_the_cases_that_need_it(self):
        epic, spec_task, _ = self.epic_with_a_spec_task()

        self.written(epic, APPROVED)

        self.assertIn("| Interface | Shape | Cases |\n| --- | --- | --- |\n"
                      "| Pay by card | `till pay --card <amount>` | 1, 2 |\n"
                      "| Refund a payment | `till refund <receipt>` | 2 |", self.description(spec_task))

    def test_an_empty_interface_table_says_the_driver_offers_everything_the_cases_need(self):
        epic, spec_task, _ = self.epic_with_a_spec_task()

        self.written(epic, {"cases": CASES, "interface": []})

        description = self.description(spec_task)
        self.assertIn("The protocol driver already offers everything the test cases need.", description)
        self.assertNotIn("| Interface |", description)

    def test_the_description_the_task_already_held_stays_before_the_cases(self):
        epic, spec_task, _ = self.epic_with_a_spec_task()

        self.written(epic, APPROVED)

        self.assertTrue(self.description(spec_task).startswith(handoff.SEAMS.rstrip("\n") + "\n\n" + SECTION_HEAD),
                        self.description(spec_task))

    def test_writing_again_replaces_the_cases_and_keeps_the_text_after_them(self):
        epic, spec_task, _ = self.epic_with_a_spec_task()
        self.written(epic, APPROVED)
        fixture.run([self.bd, "update", spec_task, f"--description={self.description(spec_task)}\n\n## Notes\nKeep."],
                    self.repo)

        self.written(epic, {"cases": CASES[:1], "interface": []})

        description = self.description(spec_task)
        self.assertEqual(1, description.count(SECTION_HEAD))
        self.assertNotIn(REFUNDS, description)
        self.assertTrue(description.endswith("offers everything the test cases need.\n\n## Notes\nKeep."),
                        description)

    def test_the_other_tasks_and_the_epic_keep_their_descriptions(self):
        epic, _, other = self.epic_with_a_spec_task()
        before = (self.description(epic), self.description(other))

        self.written(epic, APPROVED)

        self.assertEqual(before, (self.description(epic), self.description(other)))

    def test_a_bar_in_a_table_cell_does_not_split_the_cell(self):
        epic, spec_task, _ = self.epic_with_a_spec_task()
        row = {"interface": "Choose cash | card", "shape": "`till pay`", "cases": [1]}

        self.written(epic, {"cases": CASES, "interface": [row]})

        self.assertIn("| Choose cash \\| card | `till pay` | 1 |", self.description(spec_task))

    def test_write_prints_the_section_that_read_prints_back(self):
        epic, _, _ = self.epic_with_a_spec_task()

        printed = self.written(epic, APPROVED)

        read = self.spec_cases("read", epic)
        self.assertEqual(0, read.returncode, read.stderr)
        self.assertEqual(printed, read.stdout)
        self.assertTrue(read.stdout.startswith(SECTION_HEAD))


class SpecCasesRefusalTests(SpecCasesCase):
    def refused(self, epic: str, spec_task: str, approved: object, reason: str) -> None:
        before = self.description(spec_task)

        done = self.spec_cases("write", epic, json.dumps(approved))

        self.assertEqual(1, done.returncode)
        self.assertIn(reason, done.stderr)
        self.assertEqual(before, self.description(spec_task))

    def test_an_epic_with_no_spec_task_is_refused_and_nothing_is_written(self):
        epic, first, second = self.epic_with_two_tasks()

        done = self.spec_cases("write", epic, json.dumps(APPROVED))

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{epic} records no spec task", done.stderr)
        self.assertEqual(handoff.SEAMS, self.description(first))
        self.assertEqual(handoff.SEAMS, self.description(second))

    def test_a_case_with_no_deletion_answer_is_refused(self):
        epic, spec_task, _ = self.epic_with_a_spec_task()
        unanswered = [{**CASES[0], "deletion": "  "}]

        self.refused(epic, spec_task, {"cases": unanswered, "interface": []}, "case 1 is not an object with a name")

    def test_no_case_at_all_is_refused(self):
        epic, spec_task, _ = self.epic_with_a_spec_task()

        self.refused(epic, spec_task, {"cases": [], "interface": []}, "at least one test case")

    def test_two_cases_with_one_name_are_refused(self):
        epic, spec_task, _ = self.epic_with_a_spec_task()

        self.refused(epic, spec_task, {"cases": [CASES[0], CASES[0]], "interface": []}, "two cases are named")

    def test_an_interface_row_that_names_a_case_that_does_not_exist_is_refused(self):
        epic, spec_task, _ = self.epic_with_a_spec_task()
        row = {"interface": "Pay by card", "shape": "`till pay`", "cases": [3]}

        self.refused(epic, spec_task, {"cases": CASES, "interface": [row]}, "the cases are numbered 1 to 2")

    def test_input_without_an_interface_list_is_refused(self):
        epic, spec_task, _ = self.epic_with_a_spec_task()

        self.refused(epic, spec_task, {"cases": CASES}, 'an object with "cases" and "interface"')

    def test_input_that_is_not_json_is_refused(self):
        epic, spec_task, _ = self.epic_with_a_spec_task()
        before = self.description(spec_task)

        done = self.spec_cases("write", epic, "not json")

        self.assertEqual(1, done.returncode)
        self.assertIn("not valid JSON", done.stderr)
        self.assertEqual(before, self.description(spec_task))

    def test_a_bead_that_is_not_an_epic_is_refused(self):
        _, first, _ = self.epic_with_a_spec_task()

        done = self.spec_cases("write", first, json.dumps(APPROVED))

        self.assertEqual(1, done.returncode)
        self.assertIn("not an epic", done.stderr)


class SpecCasesReadTests(SpecCasesCase):
    def test_read_prints_nothing_for_a_spec_task_that_holds_no_cases(self):
        epic, _, _ = self.epic_with_a_spec_task()

        done = self.spec_cases("read", epic)

        self.assertEqual((0, ""), (done.returncode, done.stdout))


if __name__ == "__main__":
    unittest.main()
