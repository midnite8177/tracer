import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture
import test_status

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
sys.path.insert(0, str(PLUGIN / "scripts"))

import processes  # noqa: E402
import watcher_record  # noqa: E402

FACTORY_STATE = PLUGIN / "scripts" / "factory_state.py"

MINUTE = 60
FRESH_SECONDS = 90
QUESTION = "Should the receipt round to five cents?"
GATE_COMMAND = "/jidoka:accept"
RESTART = "/jidoka:factory"
FACTORY_ACTOR = "jidoka"


class FactoryStateCase(test_status.StatusCase):
    def post_as_factory(self, bead: str, text: str) -> None:
        fixture.run_with_env([self.fake_bd, "comment", bead, text], self.repo,
                             {**os.environ, "BEADS_ACTOR": FACTORY_ACTOR})

    def park_on_question(self, bead: str, question: str = QUESTION) -> None:
        self.post_as_factory(bead, f"Question: {question}\n\nThe receipt shows 3.14159.")
        self.bd("label", "add", bead, "human")

    def start_watcher(self, epic: str, parked: list[str]) -> None:
        pid = os.getpid()
        watcher_record.write_record(self.home, watcher_record.WatcherRecord(
            epic, pid, processes.started_at(pid), None, int(time.time()),
            watcher_record.WaitsFor(frozenset(parked))))

    def leave_record_of_a_gone_watcher(self, epic: str, parked: list[str]) -> None:
        watcher_record.write_record(self.home, watcher_record.WatcherRecord(
            epic, 2 ** 22 + 12345, "Thu Jan  1 00:00:00 1970", None, int(time.time()),
            watcher_record.WaitsFor(frozenset(parked))))

    def states(self, *args: str) -> list[dict]:
        done = self.script(FACTORY_STATE, "--json", *args)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)["epics"]

    def state_of(self, epic: str) -> dict:
        return next(item for item in self.states() if item["epic"] == epic)

    def lines(self) -> str:
        done = self.script(FACTORY_STATE)
        self.assertEqual(0, done.returncode, done.stderr)
        return done.stdout


class ParkedEpicTests(FactoryStateCase):
    def setUp(self):
        super().setUp()
        self.epic = self.new_epic("Take card payments", "factory")
        self.park_on_question(self.epic)
        self.write_beat(self.epic, 10, test_status.MANAGER_SESSION)

    def test_a_parked_epic_with_a_live_watcher_says_that_answering_wakes_it(self):
        self.start_watcher(self.epic, [self.epic])

        shown = self.state_of(self.epic)

        self.assertEqual("waiting-on-you", shown["state"])
        self.assertEqual("answer", shown["next_step"]["action"])
        self.assertTrue(shown["next_step"]["wakes_on_answer"])
        self.assertIn(QUESTION, shown["next_step"]["text"])
        self.assertIn("wakes", shown["next_step"]["text"])
        self.assertNotIn(RESTART, shown["next_step"]["text"])

    def test_the_same_epic_with_no_watcher_says_to_answer_and_then_run_the_factory(self):
        shown = self.state_of(self.epic)

        self.assertEqual("waiting-on-you", shown["state"])
        self.assertFalse(shown["next_step"]["wakes_on_answer"])
        self.assertEqual(RESTART, shown["next_step"]["command"])
        self.assertIn(QUESTION, shown["next_step"]["text"])
        self.assertIn(f"then run {RESTART}", shown["next_step"]["text"])

    def test_a_record_whose_process_is_gone_counts_as_no_watcher(self):
        self.leave_record_of_a_gone_watcher(self.epic, [self.epic])

        shown = self.state_of(self.epic)

        self.assertFalse(shown["watcher"])
        self.assertFalse(shown["next_step"]["wakes_on_answer"])

    def test_a_record_whose_parked_list_is_malformed_counts_as_no_watcher(self):
        self.start_watcher(self.epic, [self.epic])
        path = watcher_record.record_path(self.home, self.epic)
        held = json.loads(path.read_text(encoding="utf-8"))
        held["waits_for"]["parked"] = "not a list"
        path.write_text(json.dumps(held), encoding="utf-8")

        shown = self.state_of(self.epic)

        self.assertFalse(shown["watcher"])
        self.assertFalse(shown["next_step"]["wakes_on_answer"])

    def test_a_watcher_that_began_before_the_epic_was_parked_is_not_woken_by_the_answer(self):
        self.start_watcher(self.epic, [])

        shown = self.state_of(self.epic)

        self.assertTrue(shown["watcher"])
        self.assertFalse(shown["next_step"]["wakes_on_answer"])

    def test_a_fresh_heartbeat_makes_the_run_wait_until_it_would_be_stale(self):
        now = int(time.time())
        self.write_beat(self.epic, 30, test_status.MANAGER_SESSION)

        shown = self.state_of(self.epic)

        step = shown["next_step"]
        self.assertAlmostEqual(now - 30 + FRESH_SECONDS + 1, step["run_after"], delta=5)
        self.assertRegex(step["text"], rf"then run {RESTART} after \d\d:\d\d:\d\d")

    def test_a_stale_heartbeat_leaves_the_run_with_no_wait(self):
        self.write_beat(self.epic, 10 * MINUTE, test_status.MANAGER_SESSION)

        step = self.state_of(self.epic)["next_step"]

        self.assertIsNone(step["run_after"])
        self.assertNotIn(" after ", step["text"])

    def test_the_wait_is_printed_in_the_clock_the_machine_keeps(self):
        self.write_beat(self.epic, 30, test_status.MANAGER_SESSION)
        beat = json.loads(self.beat_file(self.epic).read_text(encoding="utf-8"))["time"]
        expected = beat + FRESH_SECONDS + 1

        done = self.script(FACTORY_STATE)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(time.strftime("%H:%M:%S", time.localtime(expected)), done.stdout)

    def test_the_reason_is_the_question_the_factory_posted(self):
        shown = self.state_of(self.epic)

        self.assertEqual([{"bead": self.epic, "kind": "question", "text": QUESTION, "wakes": False}],
                         shown["waiting_on"])

    def test_an_epic_labeled_by_hand_says_so(self):
        by_hand = self.new_epic("Print receipts", "factory", "human")

        shown = self.state_of(by_hand)

        self.assertEqual("human", shown["waiting_on"][0]["kind"])
        self.assertEqual("waiting-on-you", shown["state"])


class GateAndBudgetTests(FactoryStateCase):
    def test_an_epic_at_the_acceptance_gate_says_to_decide_there(self):
        epic = self.new_epic("Take card payments", "factory", "human")
        self.set_metadata(epic, gate_state="waiting")
        self.start_watcher(epic, [epic])

        shown = self.state_of(epic)

        self.assertEqual("waiting-on-you", shown["state"])
        self.assertEqual("acceptance-gate", shown["waiting_on"][0]["kind"])
        self.assertIn(f"{GATE_COMMAND} {epic}", shown["next_step"]["text"])

    def test_an_epic_the_factory_parked_without_a_question_gives_the_factorys_words(self):
        epic = self.new_epic("Take card payments", "factory")
        self.post_as_factory(epic, "Parked: the epic spent $12.00 at list price, and its budget is $10.00.")
        self.bd("label", "add", epic, "human")

        waiting = self.state_of(epic)["waiting_on"][0]

        self.assertEqual("parked", waiting["kind"])
        self.assertEqual("the epic spent $12.00 at list price, and its budget is $10.00.", waiting["text"])


class ManagedEpicTests(FactoryStateCase):
    def setUp(self):
        super().setUp()
        self.epic = self.new_epic("Take card payments", "factory")
        self.task = self.new_task(self.epic, "Read the card")
        self.write_beat(self.epic, 10, test_status.MANAGER_SESSION)

    def test_an_epic_with_a_fresh_heartbeat_and_no_watcher_is_running_and_asks_nothing_of_the_human(self):
        shown = self.state_of(self.epic)

        self.assertEqual("running", shown["state"])
        self.assertEqual("none", shown["next_step"]["action"])
        self.assertIn("Nothing to do", shown["next_step"]["text"])
        self.assertEqual([], shown["waiting_on"])

    def test_an_epic_with_a_live_watcher_and_nothing_parked_wakes_by_itself(self):
        self.start_watcher(self.epic, [])

        shown = self.state_of(self.epic)

        self.assertEqual("waiting", shown["state"])
        self.assertEqual("wait", shown["next_step"]["action"])
        self.assertIn("Nothing to do", shown["next_step"]["text"])
        self.assertIn("new task", shown["next_step"]["text"])
        self.assertIn("merged task", shown["next_step"]["text"])
        self.assertIn("room", shown["next_step"]["text"])

    def test_a_pause_names_the_time_the_factory_carries_on(self):
        until = int(time.time()) + 20 * MINUTE
        self.bd("update", self.epic, "--set-metadata",
                "pause=" + json.dumps({"cause": "usage-limit", "since": until - 600, "until": until, "retries": 0}))
        self.start_watcher(self.epic, [])

        shown = self.state_of(self.epic)

        self.assertEqual("waiting", shown["state"])
        self.assertEqual(until, shown["next_step"]["wakes_at"])
        self.assertIn(time.strftime("%H:%M", time.localtime(until)), shown["next_step"]["text"])

    def test_an_epic_with_a_stale_heartbeat_is_stopped_and_says_to_run_the_factory(self):
        self.write_beat(self.epic, 10 * MINUTE, test_status.MANAGER_SESSION)

        shown = self.state_of(self.epic)

        self.assertEqual("stopped", shown["state"])
        self.assertEqual("restart", shown["next_step"]["action"])
        self.assertEqual(RESTART, shown["next_step"]["command"])
        self.assertIn(f"Run {RESTART}", shown["next_step"]["text"])

    def stop_in_session(self, session: str, epic: str) -> subprocess.CompletedProcess:
        return self.stop_in_session_from(session, epic, self.repo)

    def stop_in_session_from(self, session: str, epic: str, folder: Path) -> subprocess.CompletedProcess:
        return fixture.run_launcher(test_status.LAUNCHER, [str(FACTORY_STATE), "--json", "--stopping", epic], None,
                                    {**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
                                     "JIDOKA_SESSION_ID": session}, folder, test_status.RUN_TIMEOUT_SECONDS)

    def held_beat(self, epic: str) -> dict:
        return json.loads(self.beat_file(epic).read_text(encoding="utf-8"))

    def test_the_closing_line_of_a_manager_that_stops_already_reads_stopped(self):
        stopped = self.stop_in_session(test_status.MANAGER_SESSION, self.epic)

        self.assertEqual(0, stopped.returncode, stopped.stderr)
        shown = json.loads(stopped.stdout)["epics"][0]
        self.assertEqual("stopped", shown["state"])
        self.assertEqual(RESTART, shown["next_step"]["command"])

    def test_a_stop_is_recorded_though_the_states_cannot_be_read(self):
        outside = self.root / "elsewhere"
        outside.mkdir()

        stopped = self.stop_in_session_from(test_status.MANAGER_SESSION, self.epic, outside)

        self.assertEqual(1, stopped.returncode)
        self.assertEqual("stopped", self.state_of(self.epic)["state"])

    def test_a_stopped_field_that_is_not_true_records_no_stop(self):
        held = self.held_beat(self.epic)
        self.beat_file(self.epic).write_text(json.dumps({**held, "stopped": "yes"}), encoding="utf-8")

        self.assertEqual("running", self.state_of(self.epic)["state"])

    def test_the_call_that_names_no_stop_changes_no_heartbeat(self):
        before = self.beat_file(self.epic).read_text(encoding="utf-8")

        self.states()

        self.assertEqual(before, self.beat_file(self.epic).read_text(encoding="utf-8"))

    def test_a_manager_that_stops_leaves_the_epic_stopped_while_its_host_keeps_beating(self):
        stopped = self.stop_in_session(test_status.MANAGER_SESSION, self.epic)
        self.assertEqual(0, stopped.returncode, stopped.stderr)
        beaten = self.script(test_status.HEARTBEAT, "beat", "--session", test_status.MANAGER_SESSION)
        self.assertEqual(0, beaten.returncode, beaten.stderr)

        shown = self.state_of(self.epic)

        self.assertEqual("stopped", shown["state"])
        self.assertEqual("restart", shown["next_step"]["action"])
        self.assertNotIn("is running", shown["next_step"]["text"])

    def test_stopping_an_epic_no_manager_claimed_writes_no_heartbeat(self):
        self.beat_file(self.epic).unlink()

        stopped = self.stop_in_session(test_status.MANAGER_SESSION, self.epic)

        self.assertEqual(0, stopped.returncode, stopped.stderr)
        self.assertFalse(self.beat_file(self.epic).exists())

    def test_a_session_that_did_not_claim_the_epic_cannot_stop_its_manager(self):
        stopped = self.stop_in_session(test_status.OTHER_SESSION, self.epic)

        self.assertEqual(0, stopped.returncode, stopped.stderr)
        self.assertEqual("running", self.state_of(self.epic)["state"])

    def test_an_epic_no_manager_claimed_is_stopped(self):
        self.beat_file(self.epic).unlink()

        shown = self.state_of(self.epic)

        self.assertEqual("stopped", shown["state"])
        self.assertIsNone(shown["heartbeat_age_seconds"])

    def test_a_stopped_epic_names_the_question_that_waits_on_a_task(self):
        self.write_beat(self.epic, 10 * MINUTE, test_status.MANAGER_SESSION)
        self.park_on_question(self.task)

        shown = self.state_of(self.epic)

        self.assertEqual("stopped", shown["state"])
        self.assertEqual([{"bead": self.task, "kind": "question", "text": QUESTION, "wakes": False}],
                         shown["waiting_on"])
        self.assertIn(QUESTION, shown["next_step"]["text"])

    def test_a_question_on_a_task_names_the_task_in_the_request(self):
        self.park_on_question(self.task)
        self.start_watcher(self.epic, [self.task])

        shown = self.state_of(self.epic)

        self.assertIn(f"Answer {self.task}: {QUESTION}", shown["next_step"]["text"])

    def test_a_live_watcher_with_only_a_parked_task_left_says_that_answering_wakes_it(self):
        self.park_on_question(self.task)
        self.start_watcher(self.epic, [self.task])

        shown = self.state_of(self.epic)

        self.assertEqual("waiting-on-you", shown["state"])
        self.assertTrue(shown["next_step"]["wakes_on_answer"])
        self.assertEqual([{"bead": self.task, "kind": "question", "text": QUESTION, "wakes": True}],
                         shown["waiting_on"])

    def test_a_parked_task_beside_a_running_epic_does_not_make_it_wait_on_the_human(self):
        self.park_on_question(self.task)

        shown = self.state_of(self.epic)

        self.assertEqual("running", shown["state"])
        self.assertEqual(self.task, shown["waiting_on"][0]["bead"])

    def test_an_epic_that_is_not_handed_off_or_is_closed_is_left_out(self):
        self.new_epic("Not handed off")
        closed = self.new_epic("Done", "factory")
        self.bd("close", closed)

        self.assertEqual([self.epic], [item["epic"] for item in self.states()])


class PrintedFormTests(FactoryStateCase):
    def test_the_lines_for_a_person_hold_the_epic_its_state_and_the_next_step(self):
        epic = self.new_epic("Take card payments", "factory")
        self.park_on_question(epic)
        self.start_watcher(epic, [epic])
        self.write_beat(epic, 10, test_status.MANAGER_SESSION)

        output = self.lines()

        self.assertIn(f"{epic}  Take card payments [waiting on you]", output)
        self.assertIn(f"  next: Answer: {QUESTION}", output)

    def test_it_prints_the_heartbeat_age_and_the_watcher_in_json(self):
        epic = self.new_epic("Take card payments", "factory")
        self.write_beat(epic, 25, test_status.MANAGER_SESSION)

        shown = self.state_of(epic)

        self.assertEqual("Take card payments", shown["title"])
        self.assertIn(shown["heartbeat_age_seconds"], range(25, 35))
        self.assertFalse(shown["watcher"])

    def test_it_says_so_when_the_factory_holds_no_epic(self):
        self.new_epic("Not handed off")

        self.assertEqual([], self.states())
        self.assertIn("no epic is in the factory", self.lines())

    def test_it_changes_no_bead(self):
        epic = self.new_epic("Take card payments", "factory")
        self.park_on_question(epic)
        before = self.bd("show", epic, "--json")

        self.states()

        self.assertEqual(before, self.bd("show", epic, "--json"))

    def test_it_lists_the_beads_once_and_shows_none_however_many_epics_the_factory_holds(self):
        epics = [self.new_epic(f"Epic {number}", "factory") for number in range(3)]
        tasks = [self.new_task(epic, f"Task of {epic}") for epic in epics]
        self.park_on_question(tasks[1])
        self.new_epic("Not handed off")
        before = len(fixture.fake_beads_calls(self.repo))

        shown = self.states()
        made = fixture.fake_beads_calls(self.repo)[before:]

        self.assertEqual(epics, [item["epic"] for item in shown])
        self.assertEqual([tasks[1]], [waiting["bead"] for item in shown for waiting in item["waiting_on"]])
        self.assertEqual([["list", "--all", "--limit", "0", "--json"], ["comments", tasks[1], "--json"]], made)

    def test_it_exits_with_a_reason_outside_a_repo(self):
        outside = self.root / "elsewhere"
        outside.mkdir()

        done = fixture.run_launcher(test_status.LAUNCHER, [str(FACTORY_STATE), "--json"], None,
                                    {**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home)},
                                    outside, test_status.RUN_TIMEOUT_SECONDS)

        self.assertEqual(1, done.returncode)
        self.assertIn("not inside a git repo", done.stderr)


if __name__ == "__main__":
    unittest.main()
