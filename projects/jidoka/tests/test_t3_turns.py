import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import t3_state  # noqa: E402
from t3_state import usage  # noqa: E402
from test_ledger import ROUTES, LedgerCase  # noqa: E402
from test_scheduler import LAUNCHER, PLUGIN, RUN_TIMEOUT_SECONDS  # noqa: E402

sys.path.insert(0, str(PLUGIN / "scripts"))
import t3_turns  # noqa: E402

THREAD = "thread-of-the-build"
OTHER_THREAD = "thread-of-another-stage"
NEON = "gemini-4-neon"
HYDROGEN = "gemini-4-hydrogen"
NEON_ROUTE = {"harness": "t3", "provider": "antigravity", "model": NEON, "version": None, "effort": "high",
              "driver": "antigravity"}
AMBIENT = ("JIDOKA_SESSION_ID", "T3CODE_THREAD_ID", "T3CODE_CLI_PATH", "JIDOKA_T3_STATE_DB")


class ALapWorkersTurnsBecomeLedgerRowsTests(LedgerCase):
    """A lap worker under an Antigravity host is a T3 thread, so its report reads that thread's turns from a
    fixture of T3's state db, which holds T3's own tables for provider turns, run attempts and runs."""

    def setUp(self):
        super().setUp()
        original = (self.home / "settings.json").read_text(encoding="utf-8")
        (self.home / "settings.json").write_text(
            json.dumps({**ROUTES, "antigravity_routes": {"standard": NEON_ROUTE}}), encoding="utf-8")
        self.addCleanup((self.home / "settings.json").write_text, original, encoding="utf-8")
        type(self).count += 1
        self.state = self.root / f"statev2-{self.count}.sqlite"

    def with_tables(self, *tables: str) -> None:
        t3_state.create(self.state, tables or t3_state.TOKEN_TABLES)

    def report_of_thread(self, lap) -> subprocess.CompletedProcess:
        env = {key: value for key, value in self.caller_env(self.home).items() if key not in AMBIENT}
        started = int(self.metadata(lap.task)["lap.started"])
        done = fixture.run_launcher(
            LAUNCHER, [str(PLUGIN / "scripts" / "scheduler.py"), "report", lap.epic, lap.task, "failed", "--agent",
                       THREAD, "--tier", "standard", "--why", "red"], None,
            {**env, "T3CODE_THREAD_ID": "thread-of-the-manager", "JIDOKA_T3_STATE_DB": str(self.state),
             "JIDOKA_NOW": str(started + 30)}, self.repo, RUN_TIMEOUT_SECONDS)
        self.assertEqual(0, done.returncode, done.stderr)
        return done

    def kinds_of(self, row: dict) -> tuple:
        return (row["input_tokens"], row["cache_read_tokens"], row["cache_write_tokens"], row["output_tokens"])

    def test_a_stage_with_two_turns_writes_one_row_that_sums_them_and_prices_above_nothing(self):
        lap = self.open_one_lap()
        self.with_tables()
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", NEON, usage(10_000, 6_000, 0, 500, 0))
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", NEON, usage(20_000, 15_000, 0, 700, 0))
        t3_state.add_turn_of_run(self.state, OTHER_THREAD, "run-2", NEON, usage(999_999, 0, 0, 999_999, 0))

        done = self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((THREAD, "t3", NEON, (9_000, 21_000, 0, 1_200)),
                         (row["agent"], row["harness"], row["model"], self.kinds_of(row)))
        self.assertGreater(row["dollars"], 0, done.stderr)

    def test_cached_input_is_taken_from_fresh_input_and_reasoning_is_not_added_to_output(self):
        lap = self.open_one_lap()
        self.with_tables()
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", NEON, usage(5_000, 4_000, 500, 300, 250))

        self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((500, 4_000, 500, 300), self.kinds_of(row))

    def test_a_turn_that_reports_less_input_than_it_cached_has_no_fresh_input_rather_than_a_negative_one(self):
        lap = self.open_one_lap()
        self.with_tables()
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", NEON, usage(1_000, 900, 400, 10, 0))

        self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((0, 900, 400, 10), self.kinds_of(row))

    def test_the_model_comes_from_the_model_selection_of_the_turns_run_over_the_route(self):
        lap = self.open_one_lap()
        self.with_tables()
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", HYDROGEN, usage(1_000, 0, 0, 10, 0))

        self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((HYDROGEN, "t3", "high"), (row["model"], row["harness"], row["effort"]))

    def test_turns_of_a_run_that_names_no_model_take_the_model_of_the_route(self):
        lap = self.open_one_lap()
        self.with_tables()
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", None, usage(1_000, 0, 0, 10, 0))

        self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((NEON, (1_000, 0, 0, 10)), (row["model"], self.kinds_of(row)))

    def test_a_run_whose_payload_is_not_json_names_no_model(self):
        lap = self.open_one_lap()
        self.with_tables()
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", HYDROGEN, usage(100, 0, 0, 5, 0))
        with closing(sqlite3.connect(self.state)) as db, db:
            db.execute("UPDATE orchestration_v2_projection_runs SET payload_json = 'not json'")

        self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((NEON, (100, 0, 0, 5)), (row["model"], self.kinds_of(row)))

    def test_turns_of_runs_on_two_models_write_a_row_for_each(self):
        lap = self.open_one_lap()
        self.with_tables()
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", NEON, usage(1_000, 0, 0, 10, 0))
        t3_state.add_turn_of_run(self.state, THREAD, "run-2", HYDROGEN, usage(2_000, 500, 0, 20, 0))
        t3_state.add_turn_of_run(self.state, THREAD, "run-3", NEON, usage(3_000, 0, 0, 30, 0))

        self.report_of_thread(lap)

        rows = self.listed(lap.epic)["rows"]
        self.assertEqual([(NEON, (4_000, 0, 0, 40)), (HYDROGEN, (1_500, 500, 0, 20))],
                         [(row["model"], self.kinds_of(row)) for row in rows])

    def test_a_turn_that_ran_under_no_known_attempt_counts_on_the_route_model(self):
        lap = self.open_one_lap()
        self.with_tables()
        t3_state.add_turn(self.state, "turn-1", THREAD, None, usage(700, 0, 0, 7, 0))
        t3_state.add_turn(self.state, "turn-2", THREAD, "attempt-nobody-knows", usage(300, 0, 0, 3, 0))

        self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((NEON, (1_000, 0, 0, 10)), (row["model"], self.kinds_of(row)))

    def test_a_turn_with_no_token_count_adds_nothing_to_the_turns_that_have_one(self):
        lap = self.open_one_lap()
        self.with_tables()
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", NEON, usage(1_000, 0, 0, 10, 0))
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", NEON, {"usageStatus": "unavailable",
                                                                     "usageScope": "main_agent",
                                                                     "hasSubagents": False})
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", NEON, None)

        self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((NEON, (1_000, 0, 0, 10)), (row["model"], self.kinds_of(row)))

    def test_a_context_window_snapshot_is_not_a_turns_tokens_and_the_row_has_none_and_says_why(self):
        lap = self.open_one_lap()
        self.with_tables()
        snapshot = {"id": "turn-1", "runAttemptId": "attempt-1",
                    "tokenUsage": {"usedTokens": 999_999, "inputTokens": 999_999, "outputTokens": 999_999,
                                   "updatedAt": "2026-11-22T10:00:00.000Z"}}
        t3_state.add_run(self.state, "run-1", THREAD, NEON)
        t3_state.add_attempt(self.state, "attempt-1", THREAD, "run-1")
        t3_state.add_turn_payload(self.state, "turn-1", THREAD, "attempt-1", json.dumps(snapshot))

        done = self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((NEON, (0, 0, 0, 0)), (row["model"], self.kinds_of(row)))
        self.assertIn("turnTokenUsage", done.stderr)
        self.assertIn(THREAD, done.stderr)

    def test_a_turn_whose_payload_is_not_json_gives_no_tokens_and_the_row_says_why(self):
        lap = self.open_one_lap()
        self.with_tables()
        t3_state.add_turn_payload(self.state, "turn-1", THREAD, None, "not json")

        done = self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((NEON, (0, 0, 0, 0)), (row["model"], self.kinds_of(row)))
        self.assertIn("payload_json", done.stderr)

    def test_a_schema_the_reader_does_not_know_writes_the_row_with_no_tokens_and_says_why(self):
        lap = self.open_one_lap()
        self.with_tables(t3_state.RUNS_TABLE, t3_state.ATTEMPTS_TABLE,
                         t3_state.TURNS_TABLE.replace("run_attempt_id", "attempt_ref"))

        done = self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((NEON, (0, 0, 0, 0), 0.0), (row["model"], self.kinds_of(row), row["dollars"]))
        self.assertIn("run_attempt_id", done.stderr)
        self.assertIn("ledger", done.stderr)

    def test_a_state_db_without_the_run_attempts_table_is_an_unknown_schema_too(self):
        lap = self.open_one_lap()
        self.with_tables(t3_state.RUNS_TABLE, t3_state.TURNS_TABLE)

        done = self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((NEON, (0, 0, 0, 0)), (row["model"], self.kinds_of(row)))
        self.assertIn("orchestration_v2_projection_run_attempts", done.stderr)

    def test_a_state_db_without_the_turns_table_is_an_unknown_schema_too(self):
        lap = self.open_one_lap()
        self.with_tables("CREATE TABLE something_else (id)")

        done = self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((NEON, (0, 0, 0, 0)), (row["model"], self.kinds_of(row)))
        self.assertIn("orchestration_v2_projection_provider_turns", done.stderr)

    def test_a_missing_state_db_writes_the_row_with_no_tokens_and_does_not_create_the_file(self):
        lap = self.open_one_lap()

        done = self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((NEON, (0, 0, 0, 0)), (row["model"], self.kinds_of(row)))
        self.assertIn(str(self.state), done.stderr)
        self.assertFalse(self.state.exists())

    def test_a_thread_with_no_turns_writes_the_row_with_no_tokens_and_says_so(self):
        lap = self.open_one_lap()
        self.with_tables()
        t3_state.add_turn_of_run(self.state, OTHER_THREAD, "run-1", NEON, usage(1_000, 0, 0, 10, 0))

        done = self.report_of_thread(lap)

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((NEON, (0, 0, 0, 0)), (row["model"], self.kinds_of(row)))
        self.assertIn(THREAD, done.stderr)


class ARunInProgressIsTheLatestRunStillRunningTests(unittest.TestCase):
    """A thread has a run in progress when its latest run, in T3's `orchestration_v2_projection_runs`, has the status
    `running`. The reader is called on a fixture of T3's state db."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.state = Path(self.folder.name) / "statev2.sqlite"
        before = os.environ.get(t3_turns.STATE_VARIABLE)
        os.environ[t3_turns.STATE_VARIABLE] = str(self.state)
        self.addCleanup(self.restore, before)
        t3_state.create(self.state, (t3_state.RUNS_TABLE,))

    @staticmethod
    def restore(before: str | None) -> None:
        if before is None:
            os.environ.pop(t3_turns.STATE_VARIABLE, None)
        else:
            os.environ[t3_turns.STATE_VARIABLE] = before

    def test_a_thread_whose_latest_run_is_running_has_a_run_in_progress(self):
        t3_state.add_run_in_status(self.state, "run-1", THREAD, 1, "completed")
        t3_state.add_run_in_status(self.state, "run-2", THREAD, 2, "running")

        self.assertTrue(t3_turns.has_run_in_progress(THREAD))

    def test_a_thread_whose_latest_run_has_ended_has_none_in_progress(self):
        for ordinal, status in enumerate(("completed", "interrupted", "failed", "cancelled", "rolled_back"), 1):
            with self.subTest(status=status):
                other = f"{THREAD}-{status}"
                t3_state.add_run_in_status(self.state, f"run-of-{status}", other, ordinal, status)

                self.assertFalse(t3_turns.has_run_in_progress(other))

    def test_an_earlier_run_left_running_does_not_count_once_a_later_run_has_ended(self):
        t3_state.add_run_in_status(self.state, "run-1", THREAD, 1, "running")
        t3_state.add_run_in_status(self.state, "run-2", THREAD, 2, "completed")

        self.assertFalse(t3_turns.has_run_in_progress(THREAD))

    def test_the_run_of_another_thread_is_not_the_threads_own(self):
        t3_state.add_run_in_status(self.state, "run-1", OTHER_THREAD, 1, "running")

        self.assertFalse(t3_turns.has_run_in_progress(THREAD))

    def test_a_thread_with_no_run_has_none_in_progress(self):
        self.assertFalse(t3_turns.has_run_in_progress(THREAD))

    def test_a_row_in_the_sessions_table_is_not_where_the_reader_looks(self):
        with closing(sqlite3.connect(self.state)) as db, db:
            db.execute("CREATE TABLE projection_thread_sessions (thread_id TEXT PRIMARY KEY, status TEXT NOT NULL)")
            db.execute("INSERT INTO projection_thread_sessions VALUES (?, 'running')", (THREAD,))

        self.assertFalse(t3_turns.has_run_in_progress(THREAD))

    def test_a_state_db_without_the_runs_table_raises_no_run_state_naming_it(self):
        self.state.unlink()
        t3_state.create(self.state, ("CREATE TABLE something_else (id)",))

        with self.assertRaises(t3_turns.NoRunState) as raised:
            t3_turns.has_run_in_progress(THREAD)

        self.assertIn("orchestration_v2_projection_runs", str(raised.exception))

    def test_a_runs_table_without_the_ordinal_column_raises_no_run_state_naming_it(self):
        self.state.unlink()
        t3_state.create(self.state, (t3_state.RUNS_TABLE.replace("ordinal INTEGER NOT NULL, ", ""),))

        with self.assertRaises(t3_turns.NoRunState) as raised:
            t3_turns.has_run_in_progress(THREAD)

        self.assertIn("ordinal", str(raised.exception))

    def test_a_missing_state_db_raises_no_run_state(self):
        self.state.unlink()

        with self.assertRaises(t3_turns.NoRunState):
            t3_turns.has_run_in_progress(THREAD)


if __name__ == "__main__":
    unittest.main()
