import sqlite3
import sys
import time
import unittest
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import t3_state  # noqa: E402
from test_beater import BeaterCase, THREAD  # noqa: E402
from test_stop import PLUGIN, SCHEDULER  # noqa: E402

import beater  # noqa: E402

FACTORY_SKILL = PLUGIN / "skills" / "factory" / "SKILL.md"
SETTLE_SECONDS = 4


class WakeBeaterCase(BeaterCase):
    """The beater of THREAD runs against a fake t3 that records what it is sent and a fixture of T3's state db whose
    one run of the thread a test sets to running or completed."""

    def setUp(self):
        super().setUp()
        self.sent = self.root / "sent.txt"
        fake = fixture.write_executable(
            self.bin / "t3", f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "{self.sent.as_posix()}"\n')
        self.state = self.root / "statev2.sqlite"
        t3_state.create(self.state, (t3_state.RUNS_TABLE,))
        self.variables = {"T3CODE_THREAD_ID": THREAD, "T3CODE_CLI_PATH": str(fake),
                          "JIDOKA_T3_STATE_DB": str(self.state)}

    def the_latest_run_is(self, status: str) -> None:
        with closing(sqlite3.connect(self.state)) as db, db:
            db.execute("DELETE FROM orchestration_v2_projection_runs")
        t3_state.add_run_in_status(self.state, "run-1", THREAD, 1, status)

    def claim_and_let_the_beater_take_its_first_read(self) -> None:
        done = self.call(self.variables, SCHEDULER, "next", self.epic)
        self.assertEqual(0, done.returncode, done.stderr)
        first = self.held_beat().time
        self.wait_until(lambda: self.held_beat().time > first, "the heartbeat was renewed")
        renewed = self.held_beat().time
        self.wait_until(lambda: self.held_beat().time > renewed, "the heartbeat was renewed again")

    def let_the_beater_beat_twice(self) -> None:
        for _ in range(2):
            seen = self.held_beat().time
            self.wait_until(lambda: self.held_beat().time > seen, "the heartbeat was renewed")

    def sent_lines(self) -> list[str]:
        return self.sent.read_text(encoding="utf-8").splitlines() if self.sent.exists() else []

    def wait_for_one_send(self) -> list[str]:
        self.wait_until(lambda: bool(self.sent_lines()), "the thread was sent a prompt")
        return self.sent_lines()

    def assert_nothing_sent_for(self, seconds: float) -> None:
        time.sleep(seconds)
        self.assertEqual([], self.sent_lines())

    def add_a_task(self) -> str:
        return self.create("Read the card 9", "--type=task", "--parent", self.epic)


class AnIdleManagerIsWokenTests(WakeBeaterCase):
    def test_a_new_task_on_an_idle_thread_sends_one_carry_on_prompt_and_no_second(self):
        self.the_latest_run_is("completed")
        self.claim_and_let_the_beater_take_its_first_read()

        self.add_a_task()

        [line] = self.wait_for_one_send()
        self.assertTrue(line.startswith(f"thread send {THREAD} "), line)
        self.assertIn(f"scheduler.py carry-on {self.epic}", line)
        time.sleep(SETTLE_SECONDS)
        self.assertEqual([line], self.sent_lines())

    def test_an_unparked_task_on_an_idle_thread_sends_a_carry_on_prompt(self):
        self.the_latest_run_is("completed")
        self.bd("label", "add", self.tasks[2], "human")
        self.claim_and_let_the_beater_take_its_first_read()

        self.bd("label", "remove", self.tasks[2], "human")

        [line] = self.wait_for_one_send()
        self.assertIn("unparked", line)

    def test_a_task_labeled_human_after_the_first_read_sends_no_prompt_and_one_when_unlabeled(self):
        self.the_latest_run_is("completed")
        self.claim_and_let_the_beater_take_its_first_read()

        self.bd("label", "add", self.tasks[2], "human")
        self.let_the_beater_beat_twice()
        self.assertEqual([], self.sent_lines())
        self.bd("label", "remove", self.tasks[2], "human")

        [line] = self.wait_for_one_send()
        self.assertIn("unparked", line)
        time.sleep(SETTLE_SECONDS)
        self.assertEqual([line], self.sent_lines())

    def test_a_thread_with_no_run_in_t3_counts_as_idle(self):
        self.claim_and_let_the_beater_take_its_first_read()

        self.add_a_task()

        self.assertEqual(1, len(self.wait_for_one_send()))

    def test_nothing_is_sent_while_nothing_changes(self):
        self.the_latest_run_is("completed")
        self.claim_and_let_the_beater_take_its_first_read()

        self.assert_nothing_sent_for(SETTLE_SECONDS)


class ARunningManagerIsLeftAloneTests(WakeBeaterCase):
    def test_a_thread_with_a_run_in_progress_gets_no_prompt_until_the_run_ends(self):
        self.the_latest_run_is("running")
        self.claim_and_let_the_beater_take_its_first_read()

        self.add_a_task()
        self.assert_nothing_sent_for(SETTLE_SECONDS)
        self.the_latest_run_is("completed")

        [line] = self.wait_for_one_send()
        self.assertIn(f"scheduler.py carry-on {self.epic}", line)

    def test_a_state_db_that_cannot_be_read_sends_nothing_and_leaves_the_beater_running(self):
        self.state.unlink()
        self.claim_and_let_the_beater_take_its_first_read()

        self.add_a_task()

        self.assert_nothing_sent_for(SETTLE_SECONDS)
        self.assertIsNotNone(beater.running_beater(self.home, THREAD))


class TheFactorySkillOnAntigravityTests(unittest.TestCase):
    def test_the_wait_or_end_step_starts_no_watcher_on_an_antigravity_host(self):
        text = " ".join(FACTORY_SKILL.read_text(encoding="utf-8").split())
        step = text.split("6. **Wait or end.**")[1].split("## When the human")[0]

        self.assertIn("On an Antigravity host, start no watcher", step)
        self.assertIn("The beater wakes you with the carry-on prompt", step)


if __name__ == "__main__":
    unittest.main()
