import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fake_t3_server as t3_server  # noqa: E402
from test_antigravity_usage import MINUTE, THREAD, TOKEN, UsageCase, closed_port, from_now, iso  # noqa: E402
from test_beater import SCHEDULER  # noqa: E402

HOUR = timedelta(hours=1)
NEON = {"harness": "t3", "model": "gemini-4-neon", "version": None, "effort": "high", "provider": "antigravity-main",
        "driver": "antigravity"}
CARBON = {**NEON, "model": "gemini-4-carbon"}
ARGON = {**NEON, "model": "gemini-4-argon"}
OPUS = {"harness": "claude", "model": "opus", "version": "5.5", "effort": "high"}


def buckets(gemini: tuple[float, float], argon: tuple[float, float] = (0, 0),
            carbon: tuple[float, float] = (0, 0)) -> list[dict]:
    """The Antigravity provider T3 lists, checked a minute ago, with a five-hour and a weekly window for the Gemini,
    Gemini Argon and Gemini Carbon buckets, each given as (five-hour used, weekly used)."""
    resets, weekly_resets = iso(from_now(2 * HOUR)), iso(from_now(timedelta(days=3)))
    windows = []
    for name, (five_hour, weekly) in (("gemini", gemini), ("gemini-argon", argon), ("gemini-carbon", carbon)):
        windows += [t3_server.usage_window(f"{name}-5h", "session", five_hour, resets, 300),
                    t3_server.usage_window(f"{name}-weekly", "weekly", weekly, weekly_resets, 10080)]
    return [t3_server.antigravity_with_usage(iso(from_now(-MINUTE)), windows)]


class ReserveCase(UsageCase):
    def use_routes(self, routes: dict) -> None:
        self.settings_path.write_text(json.dumps({**self.machine_settings(), "antigravity_routes": routes}),
                                      encoding="utf-8")

    @property
    def settings_path(self) -> Path:
        return self.home / "settings.json"

    def machine_settings(self) -> dict:
        return json.loads(self.settings_path.read_text(encoding="utf-8")) if self.settings_path.exists() else {}

    def use_reserve(self, share: float) -> None:
        self.settings_path.write_text(json.dumps({**self.machine_settings(), "reserves": {"antigravity": share}}),
                                      encoding="utf-8")

    def printed_with(self, providers: list[dict]) -> dict:
        with self.server(providers) as server:
            return json.loads(self.schedule(server.port).stdout)

    def epic_comments(self) -> list[str]:
        return [str(comment["text"]) for comment in self.comments(self.epic)]

    def usage_notices(self) -> list[str]:
        return [text for text in self.epic_comments() if "Antigravity usage" in text]


class TheFiveHourReserveOfABucketTests(ReserveCase):
    def setUp(self):
        super().setUp()
        self.use_routes({"standard": NEON, "deep": CARBON})

    def test_a_stage_whose_models_bucket_is_past_its_five_hour_reserve_pauses_the_epic(self):
        printed = self.printed_with(buckets(gemini=(95, 10)))

        self.assertEqual([], printed["actions"])
        self.assertEqual("reserve", printed["paused"]["cause"])
        [comment] = [text for text in self.epic_comments() if text.startswith("Paused: ")]
        self.assertIn("Gemini five-hour window is 95% used", comment)

    def test_a_stage_whose_models_bucket_is_under_its_five_hour_reserve_runs(self):
        printed = self.printed_with(buckets(gemini=(90, 10)))

        self.assertNotEqual([], printed["actions"])
        self.assertIsNone(printed["paused"])

    def test_the_bucket_of_a_carbon_stage_pauses_the_epic_when_it_is_the_one_past_its_reserve(self):
        self.use_routes({"standard": CARBON})

        printed = self.printed_with(buckets(gemini=(10, 10), carbon=(95, 10)))

        self.assertEqual([], printed["actions"])
        self.assertEqual("reserve", printed["paused"]["cause"])

    def test_the_bucket_of_an_argon_stage_is_the_argon_one(self):
        self.use_routes({"standard": ARGON})

        printed = self.printed_with(buckets(gemini=(99, 10), argon=(50, 10)))

        self.assertNotEqual([], printed["actions"])

    def test_a_stage_on_a_model_that_is_not_gemini_has_no_bucket_to_watch(self):
        self.use_routes({"standard": OPUS})

        printed = self.printed_with(buckets(gemini=(99, 99)))

        self.assertNotEqual([], printed["actions"])

    def test_the_pause_ends_when_the_next_reading_shows_the_bucket_under_its_reserve(self):
        self.printed_with(buckets(gemini=(95, 10)))

        printed = self.printed_with(buckets(gemini=(20, 10)))

        self.assertIsNone(printed["paused"])
        self.assertNotEqual([], printed["actions"])

    def test_the_machines_reserve_for_the_antigravity_account_sets_the_share_of_both_windows(self):
        self.use_reserve(0.5)

        printed = self.printed_with(buckets(gemini=(60, 10)))

        self.assertEqual("reserve", printed["paused"]["cause"])

    def test_a_bucket_whose_window_has_no_reset_second_holds_nothing_back(self):
        windows = [{**t3_server.usage_window("gemini-5h", "session", 99, iso(from_now(HOUR)), 300), "resetsAt": None}]

        printed = self.printed_with([t3_server.antigravity_with_usage(iso(from_now(-MINUTE)), windows)])

        self.assertNotEqual([], printed["actions"])


class AStageStartsWhileAnotherBucketIsPastItsReserveTests(ReserveCase):
    """The first task is on the full track, so it starts at the research on the light tier's Gemini Carbon model. The
    other two start at the build on the standard tier's Gemini model."""

    def setUp(self):
        super().setUp()
        self.use_routes({"standard": NEON, "light": CARBON})
        self.bd("update", self.tasks[0], "--set-metadata", "lap.track=full")

    def started(self, printed: dict) -> list[str]:
        return [action["task"] for action in printed["actions"]]

    def test_a_bucket_past_its_five_hour_reserve_holds_back_only_the_stages_that_draw_on_it(self):
        printed = self.printed_with(buckets(gemini=(95, 10), carbon=(10, 10)))

        self.assertEqual([self.tasks[0]], self.started(printed))
        self.assertIsNone(printed["paused"])
        self.assertEqual("open", self.shown(self.tasks[1])["status"])

    def test_a_bucket_past_its_weekly_reserve_holds_back_only_the_stages_that_draw_on_it(self):
        printed = self.printed_with(buckets(gemini=(10, 80), carbon=(10, 10)))

        self.assertEqual([self.tasks[0]], self.started(printed))
        self.assertNotIn("human", self.shown(self.epic)["labels"])
        self.assertEqual([], [text for text in self.epic_comments() if text.startswith("Question: ")])

    def test_the_stages_a_bucket_held_back_start_once_it_is_under_its_reserve_again(self):
        self.printed_with(buckets(gemini=(95, 10), carbon=(10, 10)))

        printed = self.printed_with(buckets(gemini=(20, 10), carbon=(10, 10)))

        self.assertEqual({self.tasks[0], self.tasks[1]}, set(self.started(printed)))

    def test_the_epic_pauses_when_every_stage_that_may_start_is_past_the_reserve_of_its_bucket(self):
        printed = self.printed_with(buckets(gemini=(95, 10), carbon=(95, 10)))

        self.assertEqual([], printed["actions"])
        self.assertEqual("reserve", printed["paused"]["cause"])

    def test_a_lap_that_goes_back_to_a_worker_on_a_bucket_past_its_reserve_ends_interrupted_while_another_stage_starts(
            self):
        self.bd("update", self.tasks[2], "--set-metadata", "lap.track=full")
        self.printed_with(buckets(gemini=(10, 10), carbon=(10, 10)))

        with self.server(buckets(gemini=(95, 10), carbon=(10, 10))) as server:
            done = self.call({"T3CODE_THREAD_ID": THREAD, "JIDOKA_T3_PORT": str(server.port)}, SCHEDULER, "report",
                             self.epic, self.tasks[1], "failed", "--why", "the build did not compile")
        self.assertEqual(0, done.returncode, done.stderr)

        printed = json.loads(done.stdout)
        self.assertEqual([self.tasks[2]], self.started(printed))
        [interrupted] = [comment["text"] for comment in self.comments(self.tasks[1])
                         if str(comment["text"]).startswith("Interrupted: ")]
        self.assertIn("Gemini five-hour usage window", interrupted)

    def test_a_pause_on_a_reserve_ends_when_a_stage_on_another_bucket_may_start(self):
        self.printed_with(buckets(gemini=(95, 10), carbon=(95, 10)))

        printed = self.printed_with(buckets(gemini=(95, 10), carbon=(10, 10)))

        self.assertIsNone(printed["paused"])
        self.assertEqual([self.tasks[0]], self.started(printed))


class TheWeeklyReserveOfABucketTests(ReserveCase):
    def setUp(self):
        super().setUp()
        self.use_routes({"standard": NEON, "deep": CARBON})

    def test_a_stage_whose_models_bucket_is_past_its_weekly_reserve_parks_the_epic_with_the_question(self):
        printed = self.printed_with(buckets(gemini=(10, 80)))

        self.assertEqual([], printed["actions"])
        self.assertIn("human", self.shown(self.epic)["labels"])
        [question] = [text for text in self.epic_comments() if text.startswith("Question: ")]
        self.assertIn("Gemini seven-day usage window is 80% used", question)
        self.assertIn("at this pace the window reaches", question)


class AFailedReadingHoldsNothingBackTests(ReserveCase):
    def setUp(self):
        super().setUp()
        self.use_routes({"standard": NEON, "deep": CARBON})

    def refused(self) -> dict:
        with t3_server.FakeT3Server(TOKEN, buckets(gemini=(99, 99)), t3_server.ANSWER, True) as server:
            return json.loads(self.schedule(server.port).stdout)

    def unreachable(self) -> dict:
        return json.loads(self.schedule(closed_port()).stdout)

    def test_a_t3_that_is_not_running_holds_nothing_back(self):
        printed = self.unreachable()

        self.assertNotEqual([], printed["actions"])
        self.assertIsNone(printed["paused"])

    def test_a_stale_reading_holds_nothing_back(self):
        stale = [t3_server.antigravity_with_usage(iso(from_now(-11 * MINUTE)), [
            t3_server.usage_window("gemini-5h", "session", 99, iso(from_now(HOUR)), 300)])]

        printed = self.printed_with(stale)

        self.assertNotEqual([], printed["actions"])

    def test_the_epic_gets_one_comment_the_first_time_a_reading_fails_for_a_cause(self):
        self.unreachable()
        self.unreachable()
        self.unreachable()

        [notice] = self.usage_notices()
        self.assertIn("T3 gave no ticket", notice)

    def test_a_reading_that_fails_for_another_cause_gets_its_own_comment(self):
        self.unreachable()
        self.refused()
        self.refused()

        [first, second] = self.usage_notices()
        self.assertIn("T3 gave no ticket", first)
        self.assertIn("T3 refused the token with 401", second)

    def test_a_stale_reading_is_one_cause_however_old_it_grows(self):
        for minutes in (11, 14):
            self.printed_with([t3_server.antigravity_with_usage(iso(from_now(-minutes * MINUTE)), [
                t3_server.usage_window("gemini-5h", "session", 99, iso(from_now(HOUR)), 300)])])

        self.assertEqual(1, len(self.usage_notices()))

    def test_the_epic_gets_one_comment_when_readings_return_and_none_after(self):
        self.unreachable()
        self.printed_with(buckets(gemini=(10, 10)))
        self.printed_with(buckets(gemini=(10, 10)))

        [failed, back] = self.usage_notices()
        self.assertIn("T3 gave no ticket", failed)
        self.assertIn("readings are back", back)

    def test_a_cause_that_comes_again_after_readings_returned_gets_a_comment_again(self):
        self.unreachable()
        self.printed_with(buckets(gemini=(10, 10)))
        self.unreachable()

        self.assertEqual(3, len(self.usage_notices()))

    def test_an_epic_whose_readings_never_failed_gets_no_comment(self):
        self.printed_with(buckets(gemini=(10, 10)))

        self.assertEqual([], self.usage_notices())


if __name__ == "__main__":
    unittest.main()
