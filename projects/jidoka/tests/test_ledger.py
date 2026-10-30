import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_cleanup  # noqa: E402
import test_review  # noqa: E402
import test_scheduler  # noqa: E402
import test_tidy  # noqa: E402
import test_validation  # noqa: E402
from test_scheduler import LAUNCHER, PLUGIN, RUN_TIMEOUT_SECONDS, SAVED_PRICE_PAGES, SchedulerCase  # noqa: E402

LEDGER = PLUGIN / "scripts" / "ledger.py"
PRICE_PAGES = PLUGIN / "scripts" / "price_pages.py"
SONNET = "claude-sonnet-5-5"
OPUS = "claude-opus-5-5"
FABLE = "claude-fable-5-1"
OLD_SONNET = "claude-sonnet-4-6"
HAIKU_3_5 = "claude-haiku-3-5"
DAY = 86400
ROUTES = {"routes": {"standard": {"harness": "claude", "model": "sonnet", "version": "5.5", "effort": "high"},
                     "deep": {"harness": "claude", "model": "opus", "version": "5.5", "effort": "max"},
                     "second": {"harness": "codex", "model": None, "version": None, "effort": None}}}
SESSION = "session-of-the-manager"


def tokens(model: str, input_tokens: int, output_tokens: int, cache_read: int, cache_creation: int) -> dict:
    """What the lap mod writes for one agent id, the sums of its steps."""
    return {"model": model, "steps": 3, "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read, "cache_creation_input_tokens": cache_creation}


def price(input_price: float, output_price: float, cache_read: float | None, cache_write: float | None) -> dict:
    """A list price as the lookup prints it and the cache holds it, in dollars for a million tokens of each kind."""
    return {"input": input_price, "output": output_price, "cache_read": cache_read, "cache_write": cache_write}


class LedgerBooks:
    """What a test needs to put tokens and routes in a home and read the ledger back. A test case class names it
    before the scheduler case it builds on."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.home / "settings.json").write_text(json.dumps(ROUTES), encoding="utf-8")

    def leave_tokens(self, agent: str, written: dict) -> None:
        folder = self.home / "tokens"
        folder.mkdir(exist_ok=True)
        (folder / f"{agent}.json").write_text(json.dumps(written), encoding="utf-8")

    def listed(self, epic: str) -> dict:
        done = self.launch(LEDGER, "list", epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def passes_of(self, epic: str) -> list[dict]:
        """The rows of the epic's pass workers, which belong to no task."""
        return [row for row in self.listed(epic)["rows"] if row["task"] is None]


class LedgerCase(LedgerBooks, SchedulerCase):
    def launch_at(self, now: int, *scheduler_args: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(PLUGIN / "scripts" / "scheduler.py"), *scheduler_args], None,
                                    {**self.caller_env(self.home), "JIDOKA_NOW": str(now)}, self.repo,
                                    RUN_TIMEOUT_SECONDS)

    def report_at(self, lap, outcome: str, seconds_after_start: int, *flags: str) -> dict:
        started = int(self.metadata(lap.task)["lap.started"])
        done = self.launch_at(started + seconds_after_start, "report", lap.epic, lap.task, outcome, *flags)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)


class TheLedgerPricesEveryWorkerRunTests(LedgerCase):
    def test_a_reported_build_writes_one_row_that_names_its_lap_and_prices_its_tokens_at_list_price(self):
        lap = self.open_one_lap()
        self.leave_tokens("agent-1", tokens(SONNET, 1_000_000, 100_000, 2_000_000, 100_000))

        self.report_at(lap, "failed", 95, "--agent", "agent-1", "--tier", "standard", "--why", "red")

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual(
            {"repo": str(self.repo), "epic": lap.epic, "task": lap.task, "lap": 1, "stage": "build", "try": 1,
             "track": "simple", "tier": "standard", "harness": "claude", "model": SONNET, "effort": "high",
             "agent": "agent-1", "input_tokens": 1_000_000, "output_tokens": 100_000,
             "cache_read_tokens": 2_000_000, "cache_write_tokens": 100_000, "wall_seconds": 95,
             "outcome": "failed"},
            {key: row[key] for key in ("repo", "epic", "task", "lap", "stage", "try", "track", "tier", "harness",
                                       "model", "effort", "agent", "input_tokens", "output_tokens",
                                       "cache_read_tokens", "cache_write_tokens", "wall_seconds", "outcome")})
        self.assertAlmostEqual(3.45, row["dollars"], places=6)

    def test_a_report_that_names_no_agent_still_writes_a_row_with_no_tokens(self):
        lap = self.open_one_lap()

        self.report_at(lap, "failed", 10, "--why", "red")

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((lap.task, "build", None, 0, 0.0, "failed"),
                         (row["task"], row["stage"], row["agent"], row["input_tokens"], row["dollars"],
                          row["outcome"]))

    def test_each_agent_id_keeps_its_own_token_sums(self):
        lap = self.open_one_lap()
        self.leave_tokens("agent-a", tokens(SONNET, 1_000_000, 0, 0, 0))
        self.leave_tokens("agent-b", tokens(OPUS, 0, 1_000_000, 0, 0))

        self.report_at(lap, "failed", 5, "--agent", "agent-a", "--tier", "standard", "--why", "red")
        self.report_at(lap, "failed", 5, "--agent", "agent-b", "--tier", "deep", "--why", "red")

        rows = self.listed(lap.epic)["rows"]
        self.assertEqual([("agent-a", SONNET, 1_000_000, 0, 2.0), ("agent-b", OPUS, 0, 1_000_000, 20.0)],
                         [(row["agent"], row["model"], row["input_tokens"], row["output_tokens"], row["dollars"])
                          for row in rows])
        self.assertEqual([1, 2], [row["try"] for row in rows])

    def test_a_stage_that_reran_on_the_native_route_is_priced_as_the_model_it_ran_on_not_as_the_failed_route(self):
        lap = self.open_one_lap()
        self.leave_tokens("agent-1", tokens(OPUS, 0, 1_000_000, 0, 0))

        self.report_at(lap, "failed", 5, "--agent", "agent-1", "--tier", "second", "--route", "native",
                       "--why", "red")

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual(("second", "claude", OPUS, "high"),
                         (row["tier"], row["harness"], row["model"], row["effort"]))
        self.assertAlmostEqual(20.0, row["dollars"], places=6)

    def test_a_stage_that_ran_on_its_tiers_own_route_keeps_that_routes_harness(self):
        lap = self.open_one_lap()
        self.leave_tokens("agent-1", tokens(OPUS, 0, 1_000_000, 0, 0))

        self.report_at(lap, "failed", 5, "--agent", "agent-1", "--tier", "second", "--why", "red")

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual(("second", "codex", OPUS), (row["tier"], row["harness"], row["model"]))

    def test_a_route_other_than_native_is_refused_and_writes_no_row(self):
        lap = self.open_one_lap()

        done = self.launch(test_scheduler.SCHEDULER, "report", lap.epic, lap.task, "failed", "--tier", "second",
                           "--route", "codex")

        self.assertEqual(2, done.returncode)
        self.assertEqual([], self.listed(lap.epic)["rows"])

    def test_a_stage_that_ran_past_its_wall_clock_is_priced_as_cut_off_whatever_the_worker_reported(self):
        lap = self.open_one_lap()

        self.report_at(lap, "failed", 60 * 60 + 1, "--why", "red")

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual(("cut off", 60 * 60 + 1), (row["outcome"], row["wall_seconds"]))

    def test_a_ledger_that_cannot_take_the_row_leaves_the_report_settled_and_says_so_on_stderr(self):
        lap = self.open_one_lap()
        ledger_file = self.home / "ledger.sqlite"
        ledger_file.mkdir()
        self.addCleanup(ledger_file.rmdir)
        started = int(self.metadata(lap.task)["lap.started"])

        done = self.launch_at(started + 5, "report", lap.epic, lap.task, "failed", "--why", "red")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("took no row for the build", done.stderr)
        self.assertEqual(1, self.metadata(lap.task)["lap.tries"])

    def test_a_model_with_no_price_leaves_the_row_unpriced(self):
        lap = self.open_one_lap()
        self.leave_tokens("agent-x", tokens("claude-mystery-9", 1000, 1000, 0, 0))

        self.report_at(lap, "failed", 5, "--agent", "agent-x", "--why", "red")

        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual((1000, None), (row["input_tokens"], row["dollars"]))


class EachModelIsPricedByItsOwnListPriceTests(LedgerCase):
    def dollars_of(self, model: str, input_tokens: int, output_tokens: int, cache_read: int,
                   cache_creation: int) -> float | None:
        lap = self.open_one_lap()
        self.leave_tokens("agent-1", tokens(model, input_tokens, output_tokens, cache_read, cache_creation))
        self.report_at(lap, "failed", 5, "--agent", "agent-1", "--why", "red")
        [row] = self.listed(lap.epic)["rows"]
        return row["dollars"]

    def test_a_fable_5_1_run_is_priced_with_its_cheap_cache_reads(self):
        self.assertAlmostEqual(10.0 + 50.0 + 0.25 + 12.5,
                               self.dollars_of(FABLE, 1_000_000, 1_000_000, 1_000_000, 1_000_000), places=6)

    def test_two_models_of_one_family_cost_what_each_lists(self):
        newer = self.dollars_of(SONNET, 1_000_000, 1_000_000, 1_000_000, 1_000_000)
        older = self.dollars_of(OLD_SONNET, 1_000_000, 1_000_000, 1_000_000, 1_000_000)

        self.assertAlmostEqual(2.0 + 10.0 + 0.10 + 2.5, newer, places=6)
        self.assertAlmostEqual(3.0 + 15.0 + 0.30 + 3.75, older, places=6)

    def test_a_model_id_that_names_only_a_family_has_no_price(self):
        self.assertIsNone(self.dollars_of("claude-sonnet", 1000, 0, 0, 0))

    def test_a_model_id_with_a_snapshot_date_is_priced_as_the_model(self):
        self.assertAlmostEqual(1.0, self.dollars_of("claude-haiku-4-5-20251001", 1_000_000, 0, 0, 0), places=6)


class TheProvidersPagesGiveTheStandardPricesTests(LedgerCase):
    def list_prices(self) -> dict:
        """The prices the lookup prints from a home with no cache, which makes it read both saved pages."""
        (self.home / "prices.json").unlink(missing_ok=True)
        done = self.launch(PRICE_PAGES, "list")
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)["prices"]

    def test_a_claude_model_is_keyed_by_the_model_id_its_display_name_makes(self):
        listed = self.list_prices()

        self.assertEqual(price(2.0, 10.0, 0.10, 2.5), listed["claude-sonnet-5-5"])
        self.assertEqual(price(10.0, 50.0, 0.25, 12.5), listed["claude-mythos-5-1"])

    def test_a_claude_model_whose_name_carries_a_note_and_a_link_is_keyed_by_the_name_alone(self):
        self.assertEqual(price(15.0, 75.0, 1.5, 18.75), self.list_prices()["claude-opus-4-1"])

    def test_a_claude_price_with_a_footnote_mark_is_the_number_before_it(self):
        self.assertEqual(price(2.0, 10.0, 0.20, 2.5), self.list_prices()["claude-sonnet-5"])

    def test_haiku_5_5_is_priced_at_its_rate_for_prompts_up_to_100000_tokens(self):
        self.assertEqual(price(0.10, 0.50, 0.01, 0.125), self.list_prices()["claude-haiku-5-5"])

    def test_the_batch_and_fast_tables_of_the_claude_page_price_nothing(self):
        listed = self.list_prices()

        self.assertEqual(4.0, listed["claude-opus-5-5"]["input"])
        self.assertEqual(0.80, listed["claude-haiku-3-5"]["input"])

    def test_an_openai_model_is_priced_at_its_standard_short_context_rates(self):
        self.assertEqual(price(4.0, 20.0, 0.40, 5.0), self.list_prices()["gpt-5.6-sol"])

    def test_an_openai_model_split_by_context_length_is_keyed_without_the_split(self):
        listed = self.list_prices()

        self.assertEqual(price(5.0, 30.0, 0.50, None), listed["gpt-5.5"])
        self.assertNotIn("gpt-5.5 (<272k context length)", listed)

    def test_a_dash_on_the_openai_page_is_no_price_rather_than_a_free_one(self):
        self.assertEqual(price(30.0, 180.0, None, None), self.list_prices()["gpt-5.5-pro"])

    def test_the_openai_table_of_older_models_and_the_cyber_models_are_priced_too(self):
        listed = self.list_prices()

        self.assertEqual(price(2.0, 8.0, 0.50, None), listed["gpt-4.1"])
        self.assertEqual(price(12.5, 75.0, 1.25, 15.625), listed["gpt-5.6-cyber"])


class TheLedgerPricesWithTheCachedListPricesTests(LedgerCase):
    def write_cache(self, fetched_at: int, listed: dict) -> None:
        (self.home / "prices.json").write_text(json.dumps({"fetched_at": fetched_at, "prices": listed}),
                                               encoding="utf-8")

    def cached(self) -> dict:
        return json.loads((self.home / "prices.json").read_text(encoding="utf-8"))

    def opened(self) -> tuple:
        """A new lap, and the second its report comes in."""
        lap = self.open_one_lap()
        return lap, int(self.metadata(lap.task)["lap.started"]) + 5

    def pages_folder(self, name: str, anthropic: str | None, openai: str | None) -> Path:
        """A folder of page copies that holds the given texts, and no page for a text that is None."""
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        for file, text in (("anthropic-pricing.md", anthropic), ("openai-pricing.md", openai)):
            (folder / file).unlink(missing_ok=True)
            if text is not None:
                (folder / file).write_text(text, encoding="utf-8")
        return folder

    def report_priced(self, lap, now: int, model: str, pages: Path) -> tuple[float | None, str]:
        """Reports the lap's build with a worker that used a million input tokens of the model, with the pages read
        from the folder, and returns the dollars of its row and what the report said on stderr."""
        self.leave_tokens("agent-1", tokens(model, 1_000_000, 0, 0, 0))
        done = fixture.run_launcher(LAUNCHER, [str(PLUGIN / "scripts" / "scheduler.py"), "report", lap.epic,
                                               lap.task, "failed", "--agent", "agent-1", "--why", "red"], None,
                                    {**self.caller_env(self.home), "JIDOKA_NOW": str(now),
                                     "JIDOKA_PRICE_PAGES": str(pages)}, self.repo, RUN_TIMEOUT_SECONDS)
        self.assertEqual(0, done.returncode, done.stderr)
        [row] = self.listed(lap.epic)["rows"]
        return row["dollars"], done.stderr

    def test_a_cache_older_than_seven_days_is_fetched_again_and_prices_a_model_the_hand_written_table_lacks(self):
        lap, now = self.opened()
        self.write_cache(now - 8 * DAY, {SONNET: price(9.0, 9.0, 9.0, 9.0)})

        dollars, _ = self.report_priced(lap, now, HAIKU_3_5, SAVED_PRICE_PAGES)

        self.assertAlmostEqual(0.80, dollars, places=6)
        self.assertEqual(now, self.cached()["fetched_at"])
        self.assertEqual(price(2.0, 10.0, 0.10, 2.5), self.cached()["prices"][SONNET])

    def test_with_the_network_off_a_stale_cache_prices_the_run_stays_as_it_was_and_the_report_says_so(self):
        lap, now = self.opened()
        self.write_cache(now - 8 * DAY, {HAIKU_3_5: price(7.0, 7.0, 7.0, 7.0)})
        before = self.cached()

        dollars, stderr = self.report_priced(lap, now, HAIKU_3_5, self.root / "no-network")

        self.assertAlmostEqual(7.0, dollars, places=6)
        self.assertEqual(before, self.cached())
        self.assertIn("pricing with the prices fetched at", stderr)

    def test_a_cache_younger_than_seven_days_prices_the_run_without_fetching(self):
        lap, now = self.opened()
        self.write_cache(now - 6 * DAY, {HAIKU_3_5: price(0.5, 0.5, 0.5, 0.5)})

        dollars, _ = self.report_priced(lap, now, HAIKU_3_5, SAVED_PRICE_PAGES)

        self.assertAlmostEqual(0.5, dollars, places=6)
        self.assertEqual(now - 6 * DAY, self.cached()["fetched_at"])

    def test_with_no_cache_and_the_network_off_the_hand_written_table_prices_the_run(self):
        lap, now = self.opened()
        (self.home / "prices.json").unlink(missing_ok=True)

        dollars, stderr = self.report_priced(lap, now, SONNET, self.root / "no-network")

        self.assertAlmostEqual(2.0, dollars, places=6)
        self.assertIn("pricing with the hand-written table", stderr)
        self.assertFalse((self.home / "prices.json").exists())

    def test_with_no_cache_and_the_network_off_a_model_the_hand_written_table_lacks_has_no_price(self):
        lap, now = self.opened()
        (self.home / "prices.json").unlink(missing_ok=True)

        dollars, _ = self.report_priced(lap, now, HAIKU_3_5, self.root / "no-network")

        self.assertIsNone(dollars)

    def test_one_page_fetched_without_the_other_leaves_the_cache_as_it_was(self):
        lap, now = self.opened()
        self.write_cache(now - 8 * DAY, {HAIKU_3_5: price(7.0, 7.0, 7.0, 7.0)})
        before = self.cached()
        anthropic = (SAVED_PRICE_PAGES / "anthropic-pricing.md").read_text(encoding="utf-8")

        dollars, stderr = self.report_priced(lap, now, HAIKU_3_5, self.pages_folder("anthropic-only", anthropic, None))

        self.assertAlmostEqual(7.0, dollars, places=6)
        self.assertEqual(before, self.cached())
        self.assertIn("openai-pricing.md", stderr)

    def test_a_page_with_no_price_table_leaves_the_cache_as_it_was(self):
        lap, now = self.opened()
        self.write_cache(now - 8 * DAY, {HAIKU_3_5: price(7.0, 7.0, 7.0, 7.0)})
        before = self.cached()
        openai = (SAVED_PRICE_PAGES / "openai-pricing.md").read_text(encoding="utf-8")
        pages = self.pages_folder("moved-table", "# Pricing\n\nThe prices moved.\n", openai)

        dollars, stderr = self.report_priced(lap, now, HAIKU_3_5, pages)

        self.assertAlmostEqual(7.0, dollars, places=6)
        self.assertEqual(before, self.cached())
        self.assertIn("holds no price table", stderr)

    def test_a_cache_that_cannot_be_read_counts_as_none_and_the_pages_are_fetched(self):
        lap, now = self.opened()
        (self.home / "prices.json").write_text("{not json", encoding="utf-8")

        dollars, _ = self.report_priced(lap, now, HAIKU_3_5, SAVED_PRICE_PAGES)

        self.assertAlmostEqual(0.80, dollars, places=6)
        self.assertEqual(now, self.cached()["fetched_at"])

    def test_the_hand_written_table_prices_a_model_the_cache_does_not_list(self):
        lap, now = self.opened()
        self.write_cache(now - DAY, {HAIKU_3_5: price(0.80, 4.0, 0.08, 1.0)})

        dollars, _ = self.report_priced(lap, now, SONNET, SAVED_PRICE_PAGES)

        self.assertAlmostEqual(2.0, dollars, places=6)

    def test_a_row_keeps_the_dollars_it_was_written_with_when_the_prices_change(self):
        lap, now = self.opened()
        self.write_cache(now - DAY, {HAIKU_3_5: price(7.0, 7.0, 7.0, 7.0)})
        self.report_priced(lap, now, HAIKU_3_5, SAVED_PRICE_PAGES)

        self.write_cache(now - DAY, {HAIKU_3_5: price(9.0, 9.0, 9.0, 9.0)})

        [row] = self.listed(lap.epic)["rows"]
        self.assertAlmostEqual(7.0, row["dollars"], places=6)


class TheEpicsRunningTotalTests(LedgerCase):
    def test_the_epics_metadata_holds_the_sum_of_its_rows_after_each_report(self):
        lap = self.open_one_lap()
        self.leave_tokens("agent-a", tokens(SONNET, 1_000_000, 0, 0, 0))
        self.leave_tokens("agent-b", tokens(OPUS, 0, 1_000_000, 0, 0))

        self.report_at(lap, "failed", 5, "--agent", "agent-a", "--tier", "standard", "--why", "red")
        after_one = self.metadata(lap.epic)["spend.dollars"]
        self.report_at(lap, "failed", 5, "--agent", "agent-b", "--tier", "deep", "--why", "red")

        listed = self.listed(lap.epic)
        self.assertAlmostEqual(2.0, float(after_one), places=6)
        self.assertAlmostEqual(22.0, float(self.metadata(lap.epic)["spend.dollars"]), places=6)
        self.assertAlmostEqual(sum(row["dollars"] for row in listed["rows"]), listed["dollars"], places=6)
        self.assertAlmostEqual(22.0, listed["dollars"], places=6)

    def test_another_epics_rows_stay_out_of_the_total(self):
        first = self.open_one_lap()
        second = self.open_one_lap()
        self.leave_tokens("agent-a", tokens(SONNET, 1_000_000, 0, 0, 0))
        self.leave_tokens("agent-b", tokens(SONNET, 2_000_000, 0, 0, 0))

        self.report_at(first, "failed", 5, "--agent", "agent-a", "--why", "red")
        self.report_at(second, "failed", 5, "--agent", "agent-b", "--why", "red")

        self.assertAlmostEqual(2.0, self.listed(first.epic)["dollars"], places=6)
        self.assertAlmostEqual(4.0, self.listed(second.epic)["dollars"], places=6)

    def test_an_epic_with_no_rows_lists_none_and_totals_nothing(self):
        epic = self.new_epic()

        self.assertEqual({"epic": epic, "dollars": 0.0, "rows": []}, self.listed(epic))


class TheManagersRequestsTests(LedgerCase):
    def request(self, *flags: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(LEDGER), "request", "--session", SESSION, *flags], None,
                                    self.caller_env(self.home), self.repo, RUN_TIMEOUT_SECONDS)

    def test_a_request_of_the_session_that_manages_an_epic_writes_a_row_on_that_epic(self):
        lap = self.open_one_lap()
        (self.home / "heartbeat" / f"{lap.epic}.json").unlink(missing_ok=True)
        claimed = fixture.run_launcher(LAUNCHER, [str(PLUGIN / "scripts" / "scheduler.py"), "next", lap.epic], None,
                                       {**self.caller_env(self.home), "JIDOKA_SESSION_ID": SESSION}, self.repo,
                                       RUN_TIMEOUT_SECONDS)
        self.assertEqual(0, claimed.returncode, claimed.stderr)

        done = self.request("--model", OPUS, "--input", "0", "--output", "200000", "--cache-read", "0",
                            "--cache-write", "0", "--seconds", "42")

        self.assertEqual(0, done.returncode, done.stderr)
        [row] = self.listed(lap.epic)["rows"]
        self.assertEqual(("manager", None, OPUS, 200_000, 42), (row["stage"], row["task"], row["model"],
                                                               row["output_tokens"], row["wall_seconds"]))
        self.assertAlmostEqual(4.0, row["dollars"], places=6)
        self.assertAlmostEqual(4.0, float(self.metadata(lap.epic)["spend.dollars"]), places=6)

    def test_a_request_of_a_session_that_manages_no_epic_writes_nothing(self):
        lap = self.open_one_lap()

        done = self.request("--model", OPUS, "--input", "10", "--output", "10", "--cache-read", "0",
                            "--cache-write", "0", "--seconds", "1")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], self.listed(lap.epic)["rows"])


def worker(agent: str, tier: str) -> list[str]:
    return ["--worker", agent, tier]


class PassRowsAre:
    """The checks every pass stage's row has to pass."""

    def assert_row_of(self, row: dict, stage: str, agent: str, tier: str, model: str, outcome: str,
                      dollars: float) -> None:
        self.assertEqual({"task": None, "lap": None, "try": None, "track": None, "stage": stage, "agent": agent,
                          "tier": tier, "harness": "claude", "model": model, "outcome": outcome, "wall_seconds": 0},
                         {key: row[key] for key in ("task", "lap", "try", "track", "stage", "agent", "tier", "harness",
                                                    "model", "outcome", "wall_seconds")})
        self.assertAlmostEqual(dollars, row["dollars"], places=6)


class TheTestCleanupWorkerIsPricedTests(PassRowsAre, LedgerBooks, test_cleanup.CleanupCase):
    def report_removing_nothing(self, epic: str, printed: dict, *flags: str):
        self.write_report(self.cleanup_action_of(printed), [])
        return self.launch(test_scheduler.SCHEDULER, "report-cleanup", epic, *flags)

    def test_a_reported_test_cleanup_writes_a_row_with_no_task_priced_at_list_price(self):
        epic, _, printed = self.finish_epic_whose_task_added_tests()
        self.leave_tokens("cleaner", tokens(OPUS, 0, 100_000, 0, 0))

        done = self.report_removing_nothing(epic, printed, *worker("cleaner", "deep"))

        self.assertEqual(0, done.returncode, done.stderr)
        [row] = self.passes_of(epic)
        self.assert_row_of(row, "test-cleanup", "cleaner", "deep", OPUS, "done", 2.0)
        self.assertEqual((100_000, "max"), (row["output_tokens"], row["effort"]))
        self.assertAlmostEqual(2.0, float(self.metadata(epic)["spend.dollars"]), places=6)

    def test_a_report_that_names_no_worker_writes_no_row(self):
        epic, _, printed = self.finish_epic_whose_task_added_tests()

        done = self.report_removing_nothing(epic, printed)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], self.passes_of(epic))

    def test_a_refused_report_still_prices_the_run_that_made_it(self):
        epic, _, _ = self.finish_epic_whose_task_added_tests()
        self.leave_tokens("cleaner", tokens(OPUS, 0, 100_000, 0, 0))

        done = self.launch(test_scheduler.SCHEDULER, "report-cleanup", epic, *worker("cleaner", "deep"))

        self.assertEqual(1, done.returncode)
        [row] = self.passes_of(epic)
        self.assertEqual(("test-cleanup", "cleaner"), (row["stage"], row["agent"]))

    def test_a_ledger_that_cannot_take_the_row_leaves_the_report_settled_and_says_so_on_stderr(self):
        epic, _, printed = self.finish_epic_whose_task_added_tests()
        ledger_file = self.home / "ledger.sqlite"
        ledger_file.unlink(missing_ok=True)
        ledger_file.mkdir()
        self.addCleanup(ledger_file.rmdir)

        done = self.report_removing_nothing(epic, printed, *worker("cleaner", "deep"))

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("took no row for the test-cleanup", done.stderr)
        self.assertEqual("done", self.metadata(epic)["cleanup.state"])


class TheTidyWorkerIsPricedTests(PassRowsAre, LedgerBooks, test_tidy.TidyCase):
    def test_a_reported_tidy_writes_a_row_that_joins_the_epics_running_total(self):
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        self.tidy_by_hand(self.tidy_action_of(printed), "total = 1\n")
        self.leave_tokens("tidier", tokens(SONNET, 1_000_000, 0, 0, 0))

        done = self.launch(test_scheduler.SCHEDULER, "report-tidy", epic, *worker("tidier", "standard"))

        self.assertEqual(0, done.returncode, done.stderr)
        [row] = self.passes_of(epic)
        self.assert_row_of(row, "tidy", "tidier", "standard", SONNET, "done", 2.0)
        self.assertAlmostEqual(2.0, float(self.metadata(epic)["spend.dollars"]), places=6)


class TheReviewAndFixWorkersArePricedTests(PassRowsAre, LedgerBooks, test_review.ReviewCase):
    def test_each_lane_of_a_reported_review_writes_a_row_of_its_own_agent(self):
        epic, printed = self.finish_epic_at_the_review()
        self.write_lanes(printed, {})
        self.leave_tokens("comments-agent", tokens(SONNET, 1_000_000, 0, 0, 0))
        self.leave_tokens("design-agent", tokens(OPUS, 0, 100_000, 0, 0))

        done = self.launch(test_scheduler.SCHEDULER, "report-review", epic, *worker("comments-agent", "standard"),
                           *worker("standards-agent", "standard"), *worker("spec-agent", "standard"),
                           *worker("design-agent", "deep"))

        self.assertEqual(0, done.returncode, done.stderr)
        rows = self.passes_of(epic)
        self.assertEqual(["comments-agent", "standards-agent", "spec-agent", "design-agent"],
                         [row["agent"] for row in rows])
        self.assertEqual({"review"}, {row["stage"] for row in rows})
        self.assert_row_of(rows[0], "review", "comments-agent", "standard", SONNET, "done", 2.0)
        self.assert_row_of(rows[3], "review", "design-agent", "deep", OPUS, "done", 2.0)
        self.assertAlmostEqual(4.0, float(self.metadata(epic)["spend.dollars"]), places=6)

    def test_a_reported_fix_writes_a_row_after_the_reviews(self):
        epic, printed = self.finish_epic_at_the_review()
        self.write_lanes(printed, {"comments": [test_review.finding("Echo", "small", "high")]})
        reviewed = self.launch(test_scheduler.SCHEDULER, "report-review", epic, *worker("comments-agent", "standard"))
        self.assertEqual(0, reviewed.returncode, reviewed.stderr)
        self.leave_tokens("fixer", tokens(SONNET, 0, 1_000_000, 0, 0))

        done = self.launch(test_scheduler.SCHEDULER, "report-fix", epic, *worker("fixer", "standard"))

        self.assertEqual(0, done.returncode, done.stderr)
        rows = self.passes_of(epic)
        self.assertEqual([("review", "comments-agent"), ("fix", "fixer")],
                         [(row["stage"], row["agent"]) for row in rows])
        self.assert_row_of(rows[1], "fix", "fixer", "standard", SONNET, "done", 10.0)

    def test_a_fix_worker_cut_off_at_its_wall_clock_leaves_a_row_that_the_epics_spend_includes(self):
        epic, printed = self.finish_epic_at_the_review()
        self.write_lanes(printed, {"comments": [test_review.finding("Echo", "small", "high")]})
        reviewed = self.launch(test_scheduler.SCHEDULER, "report-review", epic, *worker("comments-agent", "standard"))
        self.assertEqual(0, reviewed.returncode, reviewed.stderr)
        self.leave_tokens("fixer", tokens(SONNET, 0, 1_000_000, 0, 0))

        ended = self.launch(test_scheduler.SCHEDULER, "report-fix", epic, "--ended", "cut-off",
                            *worker("fixer", "standard"))

        self.assertEqual(0, ended.returncode, ended.stderr)
        rows = self.passes_of(epic)
        self.assertEqual([("review", "done"), ("fix", "cut off")], [(row["stage"], row["outcome"]) for row in rows])
        self.assert_row_of(rows[1], "fix", "fixer", "standard", SONNET, "cut off", 10.0)
        self.assertAlmostEqual(10.0, float(self.metadata(epic)["spend.dollars"]), places=6)
        self.assertEqual(["fix"], [action["action"] for action in json.loads(ended.stdout)["actions"]])

    def test_a_review_whose_lane_failed_prices_every_lane_it_started_as_failed(self):
        epic, printed = self.finish_epic_at_the_review()
        self.write_lanes(printed, {})
        self.leave_tokens("comments-agent", tokens(SONNET, 1_000_000, 0, 0, 0))

        ended = self.launch(test_scheduler.SCHEDULER, "report-review", epic, "--ended", "failed",
                            *worker("comments-agent", "standard"), *worker("spec-agent", "standard"))

        self.assertEqual(0, ended.returncode, ended.stderr)
        rows = self.passes_of(epic)
        self.assertEqual([("review", "failed"), ("review", "failed")], [(row["stage"], row["outcome"]) for row in rows])
        self.assertNotIn("review.head", self.metadata(epic))
        self.assertAlmostEqual(2.0, float(self.metadata(epic)["spend.dollars"]), places=6)

    def test_a_worker_reported_with_its_own_ending_is_priced_with_it_beside_the_lane_that_failed(self):
        epic, printed = self.finish_epic_at_the_review()
        self.write_lanes(printed, {})

        ended = self.launch(test_scheduler.SCHEDULER, "report-review", epic, "--ended", "failed",
                            *worker("comments-agent", "standard"), "done",
                            *worker("spec-agent", "standard"), "cut-off",
                            *worker("standards-agent", "standard"))

        self.assertEqual(0, ended.returncode, ended.stderr)
        self.assertEqual([("comments-agent", "done"), ("spec-agent", "cut off"), ("standards-agent", "failed")],
                         [(row["agent"], row["outcome"]) for row in self.passes_of(epic)])
        self.assertNotIn("review.head", self.metadata(epic))

    def test_a_worker_ending_that_is_not_done_failed_or_cut_off_is_refused_and_writes_no_row(self):
        epic, printed = self.finish_epic_at_the_review()
        self.write_lanes(printed, {})

        refused = self.launch(test_scheduler.SCHEDULER, "report-review", epic, "--ended", "failed",
                              *worker("comments-agent", "standard"), "sideways")

        self.assertEqual(1, refused.returncode)
        self.assertIn("sideways", refused.stderr)
        self.assertEqual([], self.passes_of(epic))


class ASpecLaneThatRanOnTheNativeRouteIsPricedTests(PassRowsAre, LedgerBooks, test_review.ReviewCase):
    def row_of(self, epic: str, agent: str) -> dict:
        [row] = [row for row in self.passes_of(epic) if row["agent"] == agent]
        return row

    def test_a_spec_lane_that_reran_on_the_native_route_is_priced_as_the_model_it_ran_on(self):
        epic, printed = self.finish_epic_at_the_review()
        self.write_lanes(printed, {})
        self.leave_tokens("native-spec-agent", tokens(OPUS, 0, 1_000_000, 0, 0))

        done = self.launch(test_scheduler.SCHEDULER, "report-review", epic,
                           *worker("native-spec-agent", "second"), "native")

        self.assertEqual(0, done.returncode, done.stderr)
        row = self.row_of(epic, "native-spec-agent")
        self.assertEqual(("second", "claude", OPUS, "high", "done"),
                         (row["tier"], row["harness"], row["model"], row["effort"], row["outcome"]))
        self.assertAlmostEqual(20.0, row["dollars"], places=6)

    def test_a_native_lane_can_carry_its_own_ending_after_the_route(self):
        epic, printed = self.finish_epic_at_the_review()
        self.write_lanes(printed, {})

        done = self.launch(test_scheduler.SCHEDULER, "report-review", epic, "--ended", "failed",
                           *worker("ended-spec-agent", "second"), "native", "cut-off")

        self.assertEqual(0, done.returncode, done.stderr)
        row = self.row_of(epic, "ended-spec-agent")
        self.assertEqual(("claude", "cut off"), (row["harness"], row["outcome"]))


class TheValidationWorkerIsPricedTests(PassRowsAre, LedgerBooks, test_validation.ValidationHoldoutsCase):
    def test_a_reported_holdouts_run_writes_a_row_that_ends_done(self):
        epic, _, printed = self.finish_epic_with_holdouts([test_validation.SCENARIO])
        self.write_report(self.holdouts_action_of(printed), [{"holdout": 1, "verdict": "pass", "saw": ""}])
        self.leave_tokens("validator", tokens(SONNET, 1_000_000, 0, 0, 0))

        done = self.launch(test_scheduler.SCHEDULER, "report-holdouts", epic, *worker("validator", "standard"))

        self.assertEqual(0, done.returncode, done.stderr)
        [row] = self.passes_of(epic)
        self.assert_row_of(row, "holdouts", "validator", "standard", SONNET, "done", 2.0)

    def test_a_validation_worker_that_failed_or_was_cut_off_is_priced_with_that_ending(self):
        epic, _, _ = self.finish_epic_with_holdouts([test_validation.SCENARIO])
        self.leave_tokens("validator", tokens(SONNET, 1_000_000, 0, 0, 0))

        self.launch(test_scheduler.SCHEDULER, "report-holdouts", epic, "--ended", "failed", "--why", "no start",
                    *worker("validator", "standard"))
        self.launch(test_scheduler.SCHEDULER, "report-holdouts", epic, "--ended", "cut-off",
                    *worker("validator", "standard"))

        self.assertEqual([("holdouts", "failed"), ("holdouts", "cut off")],
                         [(row["stage"], row["outcome"]) for row in self.passes_of(epic)])


if __name__ == "__main__":
    unittest.main()
