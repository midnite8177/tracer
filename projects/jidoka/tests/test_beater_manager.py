import json
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import t3_state  # noqa: E402
from test_beater import OTHER_THREAD, THREAD  # noqa: E402
from test_beater_wake import SETTLE_SECONDS, WakeBeaterCase  # noqa: E402
from test_scheduler import SAVED_PRICE_PAGES  # noqa: E402
from test_stop import PLUGIN  # noqa: E402

import beater  # noqa: E402
import processes  # noqa: E402

LEDGER = PLUGIN / "scripts" / "ledger.py"
NEON = "gemini-4-neon"
HYDROGEN = "gemini-4-hydrogen"


class ManagerBeaterCase(WakeBeaterCase):
    """The beater of THREAD runs against a fixture of T3's state db that holds the runtime requests, the runs, the run
    attempts and the provider turns of the threads, with Pushover and the ledger as the epic's owner sees them."""

    def setUp(self):
        super().setUp()
        t3_state.create(self.state, (t3_state.REQUESTS_TABLE, t3_state.ATTEMPTS_TABLE, t3_state.TURNS_TABLE))
        self.variables = {**self.variables, "JIDOKA_PRICE_PAGES": str(SAVED_PRICE_PAGES)}

    def run_of(self, run_id: str, status: str, thread: str, model: str) -> None:
        """The thread's next run, with its one attempt, whose model selection names the model."""
        t3_state.add_next_run(self.state, run_id, thread, model, status, "completed")

    def turn(self, thread: str, run_id: str, input_tokens: int, cached: int, creation: int, output: int) -> None:
        """A provider turn of the thread that ran under the attempt of the run."""
        t3_state.add_next_turn(self.state, thread, run_id, t3_state.usage(input_tokens, cached, creation, output, 0))

    def notices(self) -> list[dict[str, str]]:
        return self.pushover.received

    def rows(self) -> list[dict]:
        done = self.call(self.variables, LEDGER, "list", self.epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)["rows"]

    def wait_for_rows(self, count: int) -> list[dict]:
        self.wait_until(lambda: len(self.rows()) >= count, f"the ledger held {count} rows")
        return self.rows()

    def wait_for_notices(self, count: int) -> None:
        self.wait_until(lambda: len(self.notices()) >= count, f"{count} notices were sent")

    def restart_the_beater(self) -> None:
        pid = beater.running_beater(self.home, THREAD)
        self.assertIsNotNone(pid)
        processes.end_process(pid)
        self.wait_for_the_beater_to_end(THREAD)
        self.claim_and_let_the_beater_take_its_first_read()


class TheApprovalNoticeTests(ManagerBeaterCase):
    def test_a_pending_request_sends_one_notice_and_the_same_request_sends_no_second(self):
        t3_state.add_request(self.state, "request-1", THREAD, "pending")

        self.claim_and_let_the_beater_take_its_first_read()

        self.wait_for_notices(1)
        time.sleep(SETTLE_SECONDS)
        [notice] = self.notices()
        self.assertEqual("Permission prompt: Take card payments", notice["title"])

    def test_a_second_request_sends_its_own_notice(self):
        t3_state.add_request(self.state, "request-1", THREAD, "pending")
        self.claim_and_let_the_beater_take_its_first_read()
        self.wait_for_notices(1)

        t3_state.add_request(self.state, "request-2", THREAD, "pending")

        self.wait_for_notices(2)
        time.sleep(SETTLE_SECONDS)
        self.assertEqual(2, len(self.notices()))

    def test_a_request_that_is_answered_sends_nothing(self):
        t3_state.add_request(self.state, "request-1", THREAD, "resolved")

        self.claim_and_let_the_beater_take_its_first_read()

        time.sleep(SETTLE_SECONDS)
        self.assertEqual([], self.notices())

    def test_a_request_of_another_thread_sends_nothing(self):
        t3_state.add_request(self.state, "request-1", OTHER_THREAD, "pending")

        self.claim_and_let_the_beater_take_its_first_read()

        time.sleep(SETTLE_SECONDS)
        self.assertEqual([], self.notices())

    def test_a_restarted_beater_sends_no_second_notice_for_a_request_it_announced(self):
        t3_state.add_request(self.state, "request-1", THREAD, "pending")
        self.claim_and_let_the_beater_take_its_first_read()
        self.wait_for_notices(1)

        self.restart_the_beater()

        time.sleep(SETTLE_SECONDS)
        self.assertEqual(1, len(self.notices()))

    def test_a_state_db_that_cannot_be_read_sends_nothing_and_leaves_the_beater_running(self):
        self.state.unlink()

        self.claim_and_let_the_beater_take_its_first_read()

        time.sleep(SETTLE_SECONDS)
        self.assertEqual([], self.notices())
        self.assertIsNotNone(beater.running_beater(self.home, THREAD))


class TheManagersOwnTurnsAreSpendTests(ManagerBeaterCase):
    def test_a_completed_run_writes_one_manager_row_priced_from_its_turns(self):
        self.run_of("run-1", "completed", THREAD, NEON)
        self.turn(THREAD, "run-1", 10_000, 6_000, 0, 700)
        self.turn(THREAD, "run-1", 20_000, 15_000, 0, 300)
        self.run_of("run-2", "running", THREAD, NEON)
        self.turn(THREAD, "run-2", 999_999, 0, 0, 999_999)

        self.claim_and_let_the_beater_take_its_first_read()

        [row] = self.wait_for_rows(1)
        self.assertEqual(("manager", "request", NEON, None, 90),
                         (row["stage"], row["outcome"], row["model"], row["task"], row["wall_seconds"]))
        self.assertEqual((9_000, 21_000, 0, 1_000),
                         (row["input_tokens"], row["cache_read_tokens"], row["cache_write_tokens"],
                          row["output_tokens"]))
        self.assertGreater(row["dollars"], 0)

    def test_two_completed_runs_on_two_models_write_a_row_for_each(self):
        self.run_of("run-1", "completed", THREAD, NEON)
        self.turn(THREAD, "run-1", 1_000, 0, 0, 10)
        self.run_of("run-2", "completed", THREAD, HYDROGEN)
        self.turn(THREAD, "run-2", 2_000, 0, 0, 20)

        self.claim_and_let_the_beater_take_its_first_read()

        rows = self.wait_for_rows(2)
        self.assertEqual({NEON, HYDROGEN}, {row["model"] for row in rows})

    def test_no_row_is_written_twice_for_one_run_across_beats_and_a_restart(self):
        self.run_of("run-1", "completed", THREAD, NEON)
        self.turn(THREAD, "run-1", 1_000, 0, 0, 10)
        self.claim_and_let_the_beater_take_its_first_read()
        self.wait_for_rows(1)

        time.sleep(SETTLE_SECONDS)
        self.restart_the_beater()
        time.sleep(SETTLE_SECONDS)

        self.assertEqual(1, len(self.rows()))

    def test_a_later_run_writes_its_own_row(self):
        self.run_of("run-1", "completed", THREAD, NEON)
        self.turn(THREAD, "run-1", 1_000, 0, 0, 10)
        self.claim_and_let_the_beater_take_its_first_read()
        self.wait_for_rows(1)

        self.run_of("run-2", "completed", THREAD, NEON)
        self.turn(THREAD, "run-2", 2_000, 0, 0, 20)

        rows = self.wait_for_rows(2)
        self.assertEqual([1_000, 2_000], [row["input_tokens"] for row in rows])

    def test_a_run_still_in_progress_writes_no_row(self):
        self.run_of("run-1", "running", THREAD, NEON)
        self.turn(THREAD, "run-1", 1_000, 0, 0, 10)

        self.claim_and_let_the_beater_take_its_first_read()

        time.sleep(SETTLE_SECONDS)
        self.assertEqual([], self.rows())

    def test_a_run_of_another_thread_writes_no_row(self):
        self.run_of("run-1", "completed", OTHER_THREAD, NEON)
        self.turn(OTHER_THREAD, "run-1", 1_000, 0, 0, 10)

        self.claim_and_let_the_beater_take_its_first_read()

        time.sleep(SETTLE_SECONDS)
        self.assertEqual([], self.rows())

    def test_a_completed_run_whose_turns_are_not_there_yet_writes_its_row_once_they_are(self):
        self.run_of("run-1", "completed", THREAD, NEON)
        self.claim_and_let_the_beater_take_its_first_read()
        time.sleep(SETTLE_SECONDS)
        self.assertEqual([], self.rows())

        self.turn(THREAD, "run-1", 1_000, 0, 0, 10)

        self.assertEqual(1, len(self.wait_for_rows(1)))


if __name__ == "__main__":
    unittest.main()
