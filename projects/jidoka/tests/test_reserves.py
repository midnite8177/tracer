import json
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
from test_scheduler import PLUGIN, SCHEDULER, SchedulerCase  # noqa: E402

STATUS = PLUGIN / "scripts" / "status.py"
HOUR = 60 * 60
DAY = 24 * HOUR


class ReservesCase(SchedulerCase):
    def leave_usage(self, five_hour: float | None = None, seven_day: float | None = None, *,
                    resets_in: int = HOUR, read_ago: int = 0) -> None:
        """Leaves the reading the lap mod writes when the manager calls the scheduler, one entry for each window whose
        used percent is given, and none for a window left None, as an account on an API key has none."""
        now = int(time.time())
        reading: dict = {"read_at": now - read_ago}
        if five_hour is not None:
            reading["five_hour"] = {"used_percent": five_hour, "resets_at": now + resets_in}
        if seven_day is not None:
            reading["seven_day"] = {"used_percent": seven_day, "resets_at": now + resets_in}
        folder = self.home / "usage"
        folder.mkdir(exist_ok=True)
        path = folder / "claude.json"
        path.write_text(json.dumps(reading), encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

    def machine_reserves(self, reserves: object) -> None:
        path = self.home / "settings.json"
        path.write_text(json.dumps({"reserves": reserves}), encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

    def one_task_epic(self) -> tuple[str, str]:
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        return epic, task

    def two_running_laps(self) -> tuple[str, str, str]:
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        self.hand_off(epic, {first: "till", second: "receipts"})
        self.next_printed(epic)
        return epic, first, second

    def carry_on(self, epic: str) -> dict:
        done = self.launch(SCHEDULER, "carry-on", epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def labels(self, bead: str) -> list[str]:
        return self.shown(bead).get("labels") or []

    def question_comments(self, epic: str) -> list[str]:
        return [text for text in self.texts(epic) if text.startswith("Question: ")]


class TheFiveHourReserveTests(ReservesCase):
    def test_a_five_hour_window_past_its_reserve_opens_no_lap_and_pauses_until_the_reset(self):
        epic, task = self.one_task_epic()
        self.leave_usage(five_hour=91, resets_in=HOUR)

        printed = self.next_printed(epic)

        self.assertEqual(([], []), (printed["actions"], printed["laps"]))
        self.assertEqual("reserve", printed["paused"]["cause"])
        self.assertAlmostEqual(HOUR, printed["paused"]["wait_seconds"], delta=30)
        self.assertNotIn("lap.stage", self.metadata(task))
        self.assertNotIn("human", self.labels(epic))
        self.assertTrue(printed["watch"])

    def test_a_five_hour_window_at_its_reserve_exactly_starts_the_lap(self):
        epic, task = self.one_task_epic()
        self.leave_usage(five_hour=90)

        printed = self.next_printed(epic)

        self.assertEqual([task], [action["task"] for action in printed["actions"]])
        self.assertIsNone(printed["paused"])

    def test_a_window_that_reset_since_the_reading_holds_nothing_back(self):
        epic, task = self.one_task_epic()
        self.leave_usage(five_hour=99, resets_in=-60)

        printed = self.next_printed(epic)

        self.assertEqual([task], [action["task"] for action in printed["actions"]])

    def test_a_reading_older_than_ten_minutes_holds_nothing_back(self):
        epic, task = self.one_task_epic()
        self.leave_usage(five_hour=99, read_ago=11 * 60)

        printed = self.next_printed(epic)

        self.assertEqual([task], [action["task"] for action in printed["actions"]])

    def test_an_account_with_no_usage_windows_holds_nothing_back(self):
        epic, task = self.one_task_epic()
        self.leave_usage()

        printed = self.next_printed(epic)

        self.assertEqual([task], [action["task"] for action in printed["actions"]])

    def test_a_machine_with_no_reading_holds_nothing_back(self):
        epic, task = self.one_task_epic()

        printed = self.next_printed(epic)

        self.assertEqual([task], [action["task"] for action in printed["actions"]])

    def test_a_lap_that_would_go_back_to_a_worker_ends_interrupted_while_the_window_is_past_its_reserve(self):
        epic, first, second = self.two_running_laps()
        self.leave_usage(five_hour=95)

        printed = self.report_printed(epic, first, "failed", "--why", "red")

        self.assertEqual([], printed["actions"])
        self.assertEqual("interrupted", self.metadata(first)["lap.stage"])
        self.assertEqual("reserve", printed["paused"]["cause"])

    def test_the_pause_ends_when_the_next_reading_shows_the_window_under_its_reserve(self):
        epic, task = self.one_task_epic()
        self.leave_usage(five_hour=91)
        self.next_printed(epic)
        self.leave_usage(five_hour=12)

        printed = self.carry_on(epic)

        self.assertIsNone(printed["paused"])
        self.assertEqual([task], [action["task"] for action in printed["actions"]])
        self.assertEqual("", str(self.metadata(epic).get("pause") or ""))

    def test_a_pause_on_the_reserve_holds_while_the_next_reading_still_shows_the_window_past_it(self):
        epic, task = self.one_task_epic()
        self.leave_usage(five_hour=91)
        self.next_printed(epic)
        self.leave_usage(five_hour=93)

        printed = self.carry_on(epic)

        self.assertEqual("reserve", printed["paused"]["cause"])
        self.assertEqual([], printed["actions"])

    def leave_expired_reserve_pause(self, epic: str) -> None:
        now = int(time.time())
        expired = json.dumps({"cause": "reserve", "since": now - 2 * HOUR, "until": now - HOUR, "retries": 0})
        fixture.run([self.bd, "update", epic, "--set-metadata", f"pause={expired}"], self.repo)

    def test_a_pause_on_the_reserve_that_ran_out_is_cleared_by_a_reading_under_the_reserve(self):
        epic, task = self.one_task_epic()
        self.leave_expired_reserve_pause(epic)
        self.leave_usage(five_hour=12)

        printed = self.carry_on(epic)

        self.assertEqual("", str(self.metadata(epic).get("pause") or ""))
        self.assertEqual([task], [action["task"] for action in printed["actions"]])

    def test_trouble_a_worker_meets_after_the_reserve_pause_ran_out_starts_a_pause_of_its_own(self):
        epic, first, second = self.two_running_laps()
        self.leave_expired_reserve_pause(epic)

        printed = self.report_printed(epic, first, "cut off", "--cause", "outage")

        self.assertEqual(("outage", 0), (printed["paused"]["cause"], printed["paused"]["retries"]))
        self.assertGreater(json.loads(self.metadata(epic)["pause"])["since"], int(time.time()) - HOUR)

    def test_a_pause_on_a_limit_the_worker_met_is_not_ended_by_a_reading_under_the_reserve(self):
        epic, first, second = self.two_running_laps()
        self.leave_usage(five_hour=10)
        self.report_printed(epic, first, "cut off", "--cause", "usage-limit")

        printed = self.carry_on(epic)

        self.assertEqual("usage-limit", printed["paused"]["cause"])

    def test_status_names_the_reserve_as_the_cause_of_the_pause(self):
        epic, _ = self.one_task_epic()
        self.leave_usage(five_hour=91)
        self.next_printed(epic)

        done = self.launch(STATUS)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("paused on the five-hour reserve", done.stdout)


class TheReserveFromTheRulesAndTheMachineTests(ReservesCase):
    def test_the_machines_reserve_for_the_account_sets_the_share_of_the_five_hour_window_left_free(self):
        self.machine_reserves({"claude": 0.3})
        epic, task = self.one_task_epic()
        self.leave_usage(five_hour=71, resets_in=HOUR)

        printed = self.next_printed(epic)

        self.assertEqual("reserve", printed["paused"]["cause"])
        self.assertNotIn("lap.stage", self.metadata(task))
        self.assertIn("reserve of 30%", " ".join(self.texts(epic)))

    def test_the_machines_reserve_lets_a_five_hour_window_at_its_reserve_exactly_start_the_lap(self):
        self.machine_reserves({"claude": 0.3})
        epic, task = self.one_task_epic()
        self.leave_usage(five_hour=70)

        printed = self.next_printed(epic)

        self.assertEqual([task], [action["task"] for action in printed["actions"]])

    def test_a_small_machine_reserve_lets_the_five_hour_window_fill_past_the_default(self):
        self.machine_reserves({"claude": 0.05})
        epic, task = self.one_task_epic()
        self.leave_usage(five_hour=94)

        printed = self.next_printed(epic)

        self.assertEqual([task], [action["task"] for action in printed["actions"]])

    def test_the_machines_reserve_sets_the_share_of_the_seven_day_window_left_free(self):
        self.machine_reserves({"claude": 0.4})
        epic, _ = self.one_task_epic()
        self.leave_usage(seven_day=61, resets_in=DAY)

        printed = self.next_printed(epic)

        self.assertEqual([], printed["actions"])
        self.assertIn("human", self.labels(epic))
        [comment] = self.question_comments(epic)
        self.assertIn("keeps 40% of it free", comment)

    def test_the_epics_reserve_rule_wins_over_the_machines_reserve(self):
        self.machine_reserves({"claude": 0.05})
        epic, task = self.one_task_epic()
        self.rules_set(epic, 'reserves={"claude":0.3}')
        self.leave_usage(five_hour=75, resets_in=HOUR)

        printed = self.next_printed(epic)

        self.assertEqual("reserve", printed["paused"]["cause"])
        self.assertNotIn("lap.stage", self.metadata(task))

    def test_the_epics_reserve_rule_can_be_smaller_than_the_machines_reserve(self):
        self.machine_reserves({"claude": 0.5})
        epic, task = self.one_task_epic()
        self.rules_set(epic, 'reserves={"claude":0.05}')
        self.leave_usage(five_hour=75, seven_day=75)

        printed = self.next_printed(epic)

        self.assertEqual([task], [action["task"] for action in printed["actions"]])
        self.assertNotIn("human", self.labels(epic))

    def test_an_epic_rule_for_another_account_leaves_the_machines_reserve_for_this_one(self):
        self.machine_reserves({"claude": 0.3})
        epic, _ = self.one_task_epic()
        self.rules_set(epic, 'reserves={"codex":0.05}')
        self.leave_usage(five_hour=75, resets_in=HOUR)

        printed = self.next_printed(epic)

        self.assertEqual("reserve", printed["paused"]["cause"])

    def test_a_machine_reserve_for_another_account_leaves_the_default_for_this_one(self):
        self.machine_reserves({"codex": 0.5})
        epic, task = self.one_task_epic()
        self.leave_usage(five_hour=80, seven_day=70)

        printed = self.next_printed(epic)

        self.assertEqual([task], [action["task"] for action in printed["actions"]])

    def test_a_machine_reserve_that_is_not_a_share_leaves_the_default(self):
        self.machine_reserves({"claude": 1.5})
        epic, task = self.one_task_epic()
        self.leave_usage(five_hour=80, seven_day=70)

        printed = self.next_printed(epic)

        self.assertEqual([task], [action["task"] for action in printed["actions"]])


class TheSevenDayReserveTests(ReservesCase):
    def test_a_seven_day_window_past_its_reserve_parks_the_epic_with_a_projection_and_three_choices(self):
        epic, task = self.one_task_epic()
        self.leave_usage(seven_day=76, resets_in=DAY)

        printed = self.next_printed(epic)

        self.assertEqual(([], []), (printed["actions"], printed["laps"]))
        self.assertNotIn("lap.stage", self.metadata(task))
        self.assertIn("human", self.labels(epic))
        [comment] = self.question_comments(epic)
        self.assertIn("76%", comment)
        self.assertIn("seven-day", comment)
        self.assertIn("at this pace the window reaches", comment)
        options = json.loads(self.metadata(epic)["question.options"])
        self.assertEqual(["Wait for the reset", "Go on into the reserve", "Land what the epic holds"],
                         [option["name"] for option in options])
        self.assertEqual("Wait for the reset", self.metadata(epic)["question.recommended"])
        for option in options:
            self.assertIn(f"- {option['name']} ({option['confidence']}%): ", comment)

    def test_the_question_opens_with_one_sentence_and_every_option_says_what_happens_next(self):
        epic, _ = self.one_task_epic()
        self.leave_usage(seven_day=76, resets_in=DAY)

        self.next_printed(epic)

        [comment] = self.question_comments(epic)
        opening = comment.split("\n\n")[0]
        self.assertEqual(f"Question: Should {epic} wait for the seven-day usage window to reset before it goes on?",
                         opening)
        option_lines = [line for line in comment.splitlines() if line.startswith("- ")]
        self.assertEqual(3, len(option_lines))
        for line in option_lines:
            self.assertRegex(line, r"^- .+ \(\d+%\): .+\.$")
        self.assertIn("Page: file:", comment)

    def test_the_projection_follows_the_pace_of_the_window_so_far(self):
        epic, _ = self.one_task_epic()
        self.leave_usage(seven_day=80, resets_in=6 * DAY)

        self.next_printed(epic)

        [comment] = self.question_comments(epic)
        self.assertIn("at this pace the window reaches 560% when it resets in 6d", comment)

    def test_the_epic_parks_with_a_notification_that_points_at_it(self):
        epic, _ = self.one_task_epic()
        self.leave_usage(seven_day=76)

        done = self.next_moves(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"epic-parked:{epic}", json.dumps(self.metadata(epic)["notification"]))

    def test_a_seven_day_window_at_its_reserve_exactly_starts_the_lap(self):
        epic, task = self.one_task_epic()
        self.leave_usage(seven_day=75)

        printed = self.next_printed(epic)

        self.assertEqual([task], [action["task"] for action in printed["actions"]])
        self.assertNotIn("human", self.labels(epic))

    def test_the_stage_that_runs_finishes_before_the_epic_parks(self):
        epic, first, second = self.two_running_laps()
        self.leave_usage(seven_day=80)

        after_first = self.report_printed(epic, first, "failed", "--why", "red")

        self.assertEqual([], after_first["actions"])
        self.assertEqual([second], [lap["task"] for lap in after_first["laps"]])
        self.assertNotIn("human", self.labels(epic))
        self.assertEqual("interrupted", self.metadata(first)["lap.stage"])

        after_second = self.report_printed(epic, second, "failed", "--why", "red")

        self.assertEqual(([], []), (after_second["actions"], after_second["laps"]))
        self.assertIn("human", self.labels(epic))
        self.assertEqual(1, len(self.question_comments(epic)))

    def test_a_parked_epic_is_not_asked_about_again_by_a_later_call(self):
        epic, _ = self.one_task_epic()
        self.leave_usage(seven_day=76)
        self.next_printed(epic)

        self.next_printed(epic)

        self.assertEqual(1, len(self.question_comments(epic)))

    def test_taking_the_label_off_goes_on_into_the_reserve_and_asks_no_more_in_that_window(self):
        epic, task = self.one_task_epic()
        self.leave_usage(seven_day=76, resets_in=DAY)
        self.next_printed(epic)
        fixture.run([self.bd, "label", "remove", epic, "human"], self.repo)

        printed = self.next_printed(epic)

        self.assertEqual([task], [action["task"] for action in printed["actions"]])
        self.assertEqual(1, len(self.question_comments(epic)))

    def test_a_later_window_past_its_reserve_asks_again(self):
        epic, task = self.one_task_epic()
        self.leave_usage(seven_day=76, resets_in=DAY)
        self.next_printed(epic)
        fixture.run([self.bd, "label", "remove", epic, "human"], self.repo)
        self.next_printed(epic)
        self.leave_usage(seven_day=77, resets_in=7 * DAY)

        self.report_printed(epic, task, "failed", "--why", "red")

        self.assertEqual(2, len(self.question_comments(epic)))
        self.assertIn("human", self.labels(epic))

    def test_an_epic_that_waits_on_the_human_already_is_not_parked_again(self):
        epic, _ = self.one_task_epic()
        fixture.run([self.bd, "update", epic, "--add-label", "human"], self.repo)
        self.leave_usage(seven_day=90)

        self.launch(SCHEDULER, "carry-on", epic)

        self.assertEqual([], self.question_comments(epic))


if __name__ == "__main__":
    unittest.main()
