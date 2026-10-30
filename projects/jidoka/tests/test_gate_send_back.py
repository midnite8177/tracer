import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_gate  # noqa: E402
import test_scheduler  # noqa: E402
from test_gate import GATE  # noqa: E402

TEST_FILE = "tests/test_till.py"
TWO_TESTS = "def test_total():\n    pass\n\n\ndef test_total_again():\n    pass\n"
ONE_TEST = "def test_total():\n    pass\n"
REMOVAL = {"test": "test_total_again", "file": TEST_FILE, "covered_by": "tests/test_till.py::test_total"}
ROUNDING = "The till rounds 2.675 down to 2.67 where the paper receipt says 2.68."
PINNED = "The total is read before the tax is added."
PINNED_NOTE = f"till.py:12: {PINNED}"


def proposal(note: int, title: str, area: str, track: str) -> dict:
    return {"note": note, "title": title, "demo": f"Demo line for {title}.", "seams": f"Seams line for {title}.",
            "area": area, "track": track}


TWO_PROPOSALS = [proposal(1, "Round half up on the till", "till", "simple"),
                 proposal(2, "Add the tax before the total is read", "receipt", "full")]


class SendBackCase(test_gate.GateCase):
    def proposals_file(self, proposals: list) -> Path:
        type(self).count += 1
        path = self.root / f"send-back-{self.count}.json"
        path.write_text(json.dumps(proposals), encoding="utf-8")
        return path

    def send_back(self, epic: str, notes: list[str], proposals: list) -> subprocess.CompletedProcess:
        flags = [flag for note in notes for flag in ("--note", note)]
        return self.launch(GATE, "send-back", epic, *flags, "--proposals", str(self.proposals_file(proposals)))

    def sent_back_with_two_notes(self) -> tuple[str, dict[str, str]]:
        """An epic sent back with a free note and a pinned note; returns the epic and its new tasks by title."""
        epic, task, _ = self.epic_at_the_gate()
        before = set(self.children_of(epic).values())
        done = self.send_back(epic, [ROUNDING, PINNED_NOTE], TWO_PROPOSALS)
        self.assertEqual(0, done.returncode, done.stderr)
        return epic, {title: bead for title, bead in self.children_of(epic).items() if bead not in before}


    def epic_at_the_gate_after_a_cleanup_and_a_tidy(self) -> str:
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), self.work_file(task), "built\n")
        self.leave_in(Path(action["worktree"]), TEST_FILE, TWO_TESTS)
        printed = self.build_done(epic, task)
        [cleanup] = [each for each in printed["actions"] if each["action"] == "test-cleanup"]
        self.leave_in(Path(cleanup["worktree"]), TEST_FILE, ONE_TEST)
        Path(cleanup["report"]).write_text(json.dumps([REMOVAL]), encoding="utf-8")
        done = self.launch(test_scheduler.SCHEDULER, "report-cleanup", epic)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("pass", self.settle_tidy_and_review(json.loads(done.stdout))["validation"]["result"])
        self.assertEqual("done", self.metadata(epic)["cleanup.state"])
        self.assertEqual("done", self.metadata(epic)["tidy.state"])
        return epic


class EachNoteBecomesATaskTests(SendBackCase):
    def test_each_note_becomes_an_open_task_in_the_epic_with_the_proposed_demo_and_seams_lines(self):
        epic, filed = self.sent_back_with_two_notes()

        self.assertEqual({"Round half up on the till", "Add the tax before the total is read"}, set(filed))
        description = self.shown(filed["Round half up on the till"])["description"]
        self.assertIn(f"## What\n\n{ROUNDING}", description)
        self.assertIn("## Demo\n\nDemo line for Round half up on the till.", description)
        self.assertIn("## Seams\n\nSeams line for Round half up on the till.", description)
        for bead in filed.values():
            self.assertEqual("open", self.shown(bead)["status"])

    def test_a_task_gets_the_area_and_the_track_its_proposal_names(self):
        _, filed = self.sent_back_with_two_notes()

        simple = self.metadata(filed["Round half up on the till"])
        full = self.metadata(filed["Add the tax before the total is read"])
        self.assertEqual(("till", "simple"), (simple["lap.area"], simple["lap.track"]))
        self.assertEqual(("receipt", "full"), (full["lap.area"], full["lap.track"]))

    def test_a_new_task_carries_none_of_the_labels_the_epic_held_at_the_gate(self):
        _, filed = self.sent_back_with_two_notes()

        for bead in filed.values():
            self.assertNotIn("labels", self.shown(bead))

    def test_a_note_pinned_to_a_diff_line_names_the_file_and_the_line_in_its_task(self):
        _, filed = self.sent_back_with_two_notes()

        description = self.shown(filed["Add the tax before the total is read"])["description"]
        self.assertIn(PINNED, description)
        self.assertIn("till.py, line 12", description)
        self.assertNotIn("till.py", self.shown(filed["Round half up on the till"])["description"])

    def test_the_epic_records_the_decision_and_a_comment_that_pairs_each_note_with_its_task(self):
        epic, filed = self.sent_back_with_two_notes()

        [comment] = [text for text in self.texts(epic) if text.startswith("Sent back at the acceptance gate")]
        self.assertEqual("send-back", self.metadata(epic)["gate.decision"])
        for title, bead in filed.items():
            self.assertIn(f"{bead} {title}", comment)
        self.assertIn(ROUNDING, comment)
        self.assertEqual("Jeff Scheduler", self.comments(epic)[-1]["author"])

    def test_the_script_prints_the_new_tasks_in_the_order_of_the_notes(self):
        epic, task, _ = self.epic_at_the_gate()

        done = self.send_back(epic, [ROUNDING, PINNED_NOTE], TWO_PROPOSALS)

        filed = self.children_of(epic)
        self.assertIn(f"1. {filed['Round half up on the till']} Round half up on the till\n"
                      f"2. {filed['Add the tax before the total is read']} Add the tax before the total is read\n",
                      done.stdout)


class ASentBackEpicRunsAgainTests(SendBackCase):
    def test_the_epic_leaves_the_gate_and_the_next_call_of_the_scheduler_opens_a_lap_for_each_new_task(self):
        epic, filed = self.sent_back_with_two_notes()

        shown = self.shown(epic)
        printed = self.next_printed(epic)

        self.assertNotIn("human", shown["labels"])
        self.assertIn("factory", shown["labels"])
        self.assertNotIn("gate.state", shown["metadata"])
        self.assertEqual("open", shown["status"])
        self.assertEqual(sorted(filed.values()), sorted(action["task"] for action in self.lap_actions(printed)))
        self.assertEqual({"build", "research"}, {action["action"] for action in self.lap_actions(printed)})

    def test_the_pass_count_restarts_so_an_epic_past_the_cap_runs_its_next_pass_instead_of_asking(self):
        epic, task, _ = self.epic_at_the_gate()
        self.assertEqual(1, int(self.metadata(epic)["review.passes"]))
        fixture.run([self.bd, "update", epic, "--set-metadata", "review.passes=3", "--set-metadata",
                     "pass.asked=3"], self.repo)

        done = self.send_back(epic, [ROUNDING], [proposal(1, "Round half up on the till", "till", "simple")])
        printed = self.next_printed(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        shown = self.shown(epic)
        self.assertNotIn("review.passes", shown["metadata"])
        self.assertNotIn("pass.asked", shown["metadata"])
        self.assertNotIn("human", shown["labels"])
        self.assertEqual(1, len(self.lap_actions(printed)))

    def test_the_next_pass_of_a_sent_back_epic_runs_the_test_cleanup_and_the_tidy_again(self):
        epic = self.epic_at_the_gate_after_a_cleanup_and_a_tidy()
        done = self.send_back(epic, [ROUNDING], [proposal(1, "Round half up on the till", "till", "simple")])
        self.assertEqual(0, done.returncode, done.stderr)
        [lap] = self.lap_actions(self.next_printed(epic))
        self.leave_in(Path(lap["worktree"]), self.work_file(lap["task"]), "rounded\n")

        merged = test_scheduler.SchedulerCase.build_done(self, epic, lap["task"])

        [cleanup] = merged["actions"]
        self.assertEqual("test-cleanup", cleanup["action"])
        Path(cleanup["report"]).write_text("[]", encoding="utf-8")
        reported = self.launch(test_scheduler.SCHEDULER, "report-cleanup", epic)
        self.assertEqual(0, reported.returncode, reported.stderr)
        self.assertIn("tidy", [each["action"] for each in json.loads(reported.stdout)["actions"]])


class ASendBackThatCannotGoThroughTests(SendBackCase):
    def assert_nothing_changed(self, epic: str, children: dict[str, str], done) -> None:
        self.assertEqual(1, done.returncode)
        self.assertEqual(children, self.children_of(epic))
        shown = self.shown(epic)
        self.assertEqual("waiting", shown["metadata"]["gate.state"])
        self.assertIn("human", shown["labels"])
        self.assertEqual([], [text for text in self.texts(epic) if text.startswith("Sent back")])

    def test_a_note_with_no_proposal_is_refused_and_nothing_is_filed(self):
        epic, _, _ = self.epic_at_the_gate()
        children = self.children_of(epic)

        done = self.send_back(epic, [ROUNDING, PINNED_NOTE], TWO_PROPOSALS[:1])

        self.assert_nothing_changed(epic, children, done)
        self.assertIn("note 2", done.stderr)

    def test_a_proposal_for_a_note_that_does_not_exist_is_refused(self):
        epic, _, _ = self.epic_at_the_gate()
        children = self.children_of(epic)

        done = self.send_back(epic, [ROUNDING], [proposal(1, "Round", "till", "simple"),
                                                 proposal(2, "Tax", "till", "simple")])

        self.assert_nothing_changed(epic, children, done)
        self.assertIn("note 2", done.stderr)

    def test_a_proposal_with_a_track_that_is_neither_simple_nor_full_is_refused(self):
        epic, _, _ = self.epic_at_the_gate()
        children = self.children_of(epic)

        done = self.send_back(epic, [ROUNDING], [proposal(1, "Round", "till", "medium")])

        self.assert_nothing_changed(epic, children, done)
        self.assertIn("medium", done.stderr)

    def test_a_proposal_with_an_empty_demo_line_is_refused(self):
        epic, _, _ = self.epic_at_the_gate()
        children = self.children_of(epic)

        done = self.send_back(epic, [ROUNDING], [{**proposal(1, "Round", "till", "simple"), "demo": " "}])

        self.assert_nothing_changed(epic, children, done)
        self.assertIn("demo", done.stderr)

    def test_a_report_that_is_not_there_is_refused(self):
        epic, _, _ = self.epic_at_the_gate()
        children = self.children_of(epic)

        done = self.launch(GATE, "send-back", epic, "--note", ROUNDING, "--proposals", str(self.root / "gone.json"))

        self.assert_nothing_changed(epic, children, done)

    def test_a_send_back_with_no_note_is_refused(self):
        epic, _, _ = self.epic_at_the_gate()
        children = self.children_of(epic)

        done = self.launch(GATE, "send-back", epic, "--proposals", str(self.proposals_file([])))

        self.assert_nothing_changed(epic, children, done)
        self.assertIn("note", done.stderr)

    def test_an_epic_that_does_not_wait_at_the_gate_is_refused(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)

        done = self.send_back(epic, [ROUNDING], [proposal(1, "Round", "till", "simple")])

        self.assertEqual(1, done.returncode)
        self.assertIn("acceptance gate", done.stderr)
        self.assertEqual({self.shown(task)["title"]: task}, self.children_of(epic))


if __name__ == "__main__":
    unittest.main()
