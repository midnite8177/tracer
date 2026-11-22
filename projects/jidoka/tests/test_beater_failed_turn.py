import json
import sqlite3
import sys
import time
import unittest
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fake_t3_server as t3_server  # noqa: E402
import t3_state  # noqa: E402
from test_beater import OTHER_THREAD, THREAD  # noqa: E402
from test_beater_manager import NEON, ManagerBeaterCase  # noqa: E402
from test_beater_wake import SETTLE_SECONDS  # noqa: E402
from test_stop import SCHEDULER  # noqa: E402

import beater  # noqa: E402
import clock  # noqa: E402
import processes  # noqa: E402

TOKEN = "t3-read-token-0123456789abcdef"
PROVIDERS_SIGNED_IN = [t3_server.provider("antigravity", "authenticated")]
PROVIDERS_SIGNED_OUT = [t3_server.provider("antigravity", "unauthenticated")]
MINUTE = 60
FIRST_BACK_OFF = 5 * MINUTE
SECOND_BACK_OFF = 15 * MINUTE
PORT_VARIABLE = "JIDOKA_T3_PORT"


class FailedTurnCase(ManagerBeaterCase):
    """The beater of THREAD runs on a stand-in clock that its own sleeps move, so that a back-off of minutes passes in
    seconds, with beats a minute apart on that clock. T3's provider status is a fake server that a test starts, and
    the token is the one setup saves."""

    def setUp(self):
        super().setUp()
        self.began = int(time.time())
        self.variables = {**self.variables, clock.NOW_VARIABLE: str(self.began),
                          beater.INTERVAL_VARIABLE: str(MINUTE)}
        (self.home / "t3-token").write_text(TOKEN + "\n", encoding="utf-8")

    def t3_reports(self, providers: list[dict]) -> None:
        self.t3_answers(providers, t3_server.ANSWER)

    def t3_answers(self, providers: list[dict], on_request: str) -> None:
        """T3's provider status, as a fake server that does what `on_request` names when the status is asked for."""
        server = t3_server.FakeT3Server(TOKEN, providers, on_request, False)
        server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        self.variables = {**self.variables, PORT_VARIABLE: str(server.port)}

    def a_run_ends(self, run_id: str, status: str) -> None:
        """A run of THREAD that ended with the status, and its one attempt, which ended with the same status."""
        self.a_run_of_the_thread_ends(run_id, status, THREAD, status)

    def a_run_of_the_thread_ends(self, run_id: str, status: str, thread: str, attempt_status: str) -> None:
        """A run of the thread that ended with the status, and its one attempt, which ended with the attempt's."""
        t3_state.add_next_run(self.state, run_id, thread, NEON, status, attempt_status)

    def claim(self) -> None:
        done = self.call(self.variables, SCHEDULER, "next", self.epic)
        self.assertEqual(0, done.returncode, done.stderr)

    def handled_failures(self) -> dict[str, int]:
        return beater.read_handled(self.home, THREAD).failures

    def wait_for_failed_runs_handled(self, count: int) -> dict[str, int]:
        self.wait_until(lambda: len(self.handled_failures()) >= count, f"{count} failed runs were handled")
        return self.handled_failures()

    def pause_held(self) -> str:
        return str(self.metadata(self.epic).get("pause") or "")

    def assert_nothing_happens(self) -> None:
        self.claim()
        self.assert_nothing_sent_for(SETTLE_SECONDS)
        self.assertEqual({}, self.handled_failures())
        self.assertEqual([], self.notices())
        self.assertEqual("", self.pause_held())


class AFailedRunWakesTheManagerAfterTheBackOffTests(FailedTurnCase):
    def test_a_failed_latest_run_gets_one_carry_on_prompt_after_the_first_back_off(self):
        self.t3_reports(PROVIDERS_SIGNED_IN)
        self.a_run_ends("run-1", "failed")

        self.claim()

        [line] = self.wait_for_one_send()
        self.assertTrue(line.startswith(f"thread send {THREAD} "), line)
        self.assertIn(f"scheduler.py carry-on {self.epic}", line)
        self.assertEqual({"run-1": self.began + FIRST_BACK_OFF}, self.wait_for_failed_runs_handled(1))
        time.sleep(SETTLE_SECONDS)
        self.assertEqual([line], self.sent_lines())

    def test_failed_runs_in_a_row_wait_the_longer_back_off_of_their_count(self):
        self.t3_reports(PROVIDERS_SIGNED_IN)
        self.a_run_ends("run-1", "failed")
        self.a_run_ends("run-2", "failed")

        self.claim()

        self.assertEqual(1, len(self.wait_for_one_send()))
        self.assertEqual({"run-2": self.began + SECOND_BACK_OFF}, self.wait_for_failed_runs_handled(1))

    def test_a_completed_run_resets_the_count_of_failed_runs(self):
        self.t3_reports(PROVIDERS_SIGNED_IN)
        self.a_run_ends("run-1", "failed")
        self.a_run_ends("run-2", "failed")
        self.a_run_ends("run-3", "completed")
        self.a_run_ends("run-4", "failed")

        self.claim()

        self.wait_for_one_send()
        self.assertEqual({"run-4": self.began + FIRST_BACK_OFF}, self.wait_for_failed_runs_handled(1))

    def test_a_run_that_fails_after_a_wake_is_woken_again_after_a_longer_back_off(self):
        self.t3_reports(PROVIDERS_SIGNED_IN)
        self.a_run_ends("run-1", "failed")
        self.claim()
        self.wait_for_one_send()
        self.wait_for_failed_runs_handled(1)

        self.a_run_ends("run-2", "failed")

        self.wait_until(lambda: len(self.sent_lines()) == 2, "the thread was sent a second prompt")
        handled = self.wait_for_failed_runs_handled(2)
        self.assertGreaterEqual(handled["run-2"] - handled["run-1"], SECOND_BACK_OFF)

    def test_a_restarted_beater_sends_no_second_prompt_for_a_failed_run_it_woke(self):
        self.t3_reports(PROVIDERS_SIGNED_IN)
        self.a_run_ends("run-1", "failed")
        self.claim()
        self.wait_for_one_send()
        self.wait_for_failed_runs_handled(1)
        pid = beater.running_beater(self.home, THREAD)
        self.assertIsNotNone(pid)
        processes.end_process(pid)
        self.wait_for_the_beater_to_end(THREAD)

        self.claim()

        time.sleep(SETTLE_SECONDS)
        self.assertEqual(1, len(self.sent_lines()))

    def test_a_run_whose_attempt_failed_but_whose_row_says_cancelled_counts_as_failed(self):
        self.t3_reports(PROVIDERS_SIGNED_IN)
        self.a_run_of_the_thread_ends("run-1", "cancelled", THREAD, "failed")

        self.claim()

        self.assertEqual(1, len(self.wait_for_one_send()))

    def test_a_failed_run_with_no_attempt_row_counts_as_failed(self):
        self.t3_reports(PROVIDERS_SIGNED_IN)
        self.a_run_ends("run-1", "failed")
        with closing(sqlite3.connect(self.state)) as db, db:
            db.execute("DELETE FROM orchestration_v2_projection_run_attempts")

        self.claim()

        self.assertEqual(1, len(self.wait_for_one_send()))


class ARunThatDidNotFailWakesNobodyTests(FailedTurnCase):
    def test_a_completed_latest_run_sends_nothing(self):
        self.t3_reports(PROVIDERS_SIGNED_IN)
        self.a_run_ends("run-1", "failed")
        self.a_run_ends("run-2", "completed")

        self.assert_nothing_happens()

    def test_a_run_in_progress_after_a_failed_one_sends_nothing(self):
        self.t3_reports(PROVIDERS_SIGNED_IN)
        self.a_run_ends("run-1", "failed")
        self.a_run_ends("run-2", "running")

        self.assert_nothing_happens()

    def test_an_interrupted_latest_run_sends_nothing(self):
        self.t3_reports(PROVIDERS_SIGNED_IN)
        self.a_run_ends("run-1", "interrupted")

        self.assert_nothing_happens()

    def test_a_failed_run_of_another_thread_sends_nothing(self):
        self.t3_reports(PROVIDERS_SIGNED_IN)
        self.a_run_of_the_thread_ends("run-1", "failed", OTHER_THREAD, "failed")

        self.assert_nothing_happens()


class ASignedOutAccountPausesTheEpicTests(FailedTurnCase):
    def test_a_signed_out_account_pauses_the_epic_on_the_auth_cause_and_sends_factory_paused_once(self):
        self.t3_reports(PROVIDERS_SIGNED_OUT)
        self.a_run_ends("run-1", "failed")

        self.claim()

        self.assertEqual({"run-1": self.began}, self.wait_for_failed_runs_handled(1))
        self.wait_for_notices(1)
        time.sleep(SETTLE_SECONDS)
        [notice] = self.notices()
        self.assertEqual("Factory paused: Take card payments", notice["title"])
        self.assertEqual("auth", json.loads(self.pause_held())["cause"])
        self.assertEqual([], self.sent_lines())

    def test_a_second_failed_run_while_the_account_is_signed_out_sends_no_second_notice(self):
        self.t3_reports(PROVIDERS_SIGNED_OUT)
        self.a_run_ends("run-1", "failed")
        self.claim()
        self.wait_for_notices(1)

        self.a_run_ends("run-2", "failed")

        self.wait_for_failed_runs_handled(2)
        time.sleep(SETTLE_SECONDS)
        self.assertEqual(1, len(self.notices()))
        self.assertEqual([], self.sent_lines())


class AnUnreadableStatusBacksOffAndWakesTests(FailedTurnCase):
    def test_a_t3_that_closes_the_socket_backs_off_and_wakes_and_pauses_nothing(self):
        self.t3_answers(PROVIDERS_SIGNED_OUT, t3_server.CLOSE)
        self.a_run_ends("run-1", "failed")

        self.claim()

        self.assertEqual(1, len(self.wait_for_one_send()))
        self.assertEqual({"run-1": self.began + FIRST_BACK_OFF}, self.wait_for_failed_runs_handled(1))
        self.assertEqual("", self.pause_held())
        self.assertEqual([], self.notices())

    def test_no_token_backs_off_and_wakes(self):
        self.t3_reports(PROVIDERS_SIGNED_OUT)
        (self.home / "t3-token").unlink()
        self.a_run_ends("run-1", "failed")

        self.claim()

        self.assertEqual(1, len(self.wait_for_one_send()))
        self.assertEqual({"run-1": self.began + FIRST_BACK_OFF}, self.wait_for_failed_runs_handled(1))
        self.assertEqual("", self.pause_held())


if __name__ == "__main__":
    unittest.main()
