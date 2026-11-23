import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fake_t3_server as t3_server  # noqa: E402
import jidoka_fixture as fixture  # noqa: E402
import test_beater  # noqa: E402
import test_review  # noqa: E402
import test_scheduler  # noqa: E402
from test_antigravity_reserves import ARGON, CARBON, NEON, buckets  # noqa: E402
from test_antigravity_usage import THREAD, TOKEN, closed_port  # noqa: E402
from test_cleanup import TEST_FILE, TWO_TESTS  # noqa: E402

sys.path.insert(0, str(test_scheduler.PLUGIN / "scripts"))
import worktrees  # noqa: E402

FINDINGS = {"comments": [test_review.finding("Echo", "small", "high")]}
SETTLED = (10, 10)
PAST_FIVE_HOURS = (95, 10)
PAST_A_WEEK = (10, 99)


class PassReserveCase(test_review.ReviewCase):
    """An epic that has finished its tasks, scheduled from an Antigravity thread against a fake T3 server, with the
    deep tier on a Gemini Carbon model, the standard tier on a Gemini Argon one, and the local and second tiers on a
    Gemini one."""

    def setUp(self):
        self.addCleanup(self.clean_home)
        self.addCleanup(test_beater.BeaterCase.end_beaters, self)
        (self.home / "t3-token").write_text(TOKEN + "\n", encoding="utf-8")
        self.use_routes({"deep": CARBON, "standard": ARGON, "local": NEON, "second": NEON})

    def clean_home(self) -> None:
        for name in ("t3-token", "settings.json"):
            (self.home / name).unlink(missing_ok=True)
        for name in ("usage", "beater"):
            fixture.run(["rm", "-rf", str(self.home / name)], self.root)

    def use_routes(self, routes: dict) -> None:
        (self.home / "settings.json").write_text(json.dumps({"antigravity_routes": routes}), encoding="utf-8")

    def schedule(self, port: int, epic: str) -> dict:
        (self.home / "heartbeat" / f"{epic}.json").unlink(missing_ok=True)
        environment = {key: value for key, value in self.caller_env(self.home).items() if key != "JIDOKA_SESSION_ID"}
        environment.update({"T3CODE_THREAD_ID": THREAD, "JIDOKA_T3_PORT": str(port),
                            test_beater.beater.INTERVAL_VARIABLE: test_beater.BEAT_SECONDS})
        done = fixture.run_launcher(test_scheduler.LAUNCHER, [str(test_scheduler.SCHEDULER), "next", epic], None,
                                    environment, self.repo, test_scheduler.RUN_TIMEOUT_SECONDS)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def scheduled_with(self, epic: str, gemini=SETTLED, argon=SETTLED, carbon=SETTLED) -> dict:
        with t3_server.FakeT3Server(TOKEN, buckets(gemini, argon, carbon), t3_server.ANSWER, False) as server:
            return self.schedule(server.port, epic)

    def actions_of(self, printed: dict) -> list[str]:
        return [action["action"] for action in printed["actions"]]

    def epic_at_cleanup(self) -> str:
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), "till.txt", "built\n")
        self.leave_in(Path(action["worktree"]), TEST_FILE, TWO_TESTS)
        test_scheduler.SchedulerCase.build_done(self, epic, task)
        return epic

    def epic_at_tidy(self) -> str:
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), "till.txt", "built\n")
        printed = test_scheduler.SchedulerCase.build_done(self, epic, task)
        self.assertEqual(["tidy"], self.actions_of(printed))
        return epic

    def epic_at_fix(self) -> str:
        epic, printed = self.finish_epic_at_the_review()
        self.assertEqual(["fix"], self.actions_of(self.reviewed(printed, FINDINGS)))
        return epic

    def epic_at_merge(self) -> str:
        epic, _, printed = self.conflicting_epic()
        self.assertEqual(["merge"], self.actions_of(printed))
        return epic

    def removed_cleanup_worktree_of(self, epic: str) -> Path:
        """The path of the test cleanup's worktree, which the call that finished the epic cut and this removes, so that
        a later call shows whether it cuts the worktree again."""
        path = worktrees.stage_worktree("cleanup-", epic, self.repo)
        fixture.run(["git", "worktree", "remove", "--force", str(path)], self.repo)
        return path

    def assert_paused_on_reserve(self, printed: dict) -> None:
        self.assertEqual([], printed["actions"])
        self.assertEqual("reserve", printed["paused"]["cause"])

    def assert_parked_with_the_question(self, epic: str, printed: dict) -> None:
        self.assertEqual([], printed["actions"])
        self.assertIn("human", self.shown(epic)["labels"])
        self.assertEqual(1, len([each for each in self.comments(epic) if str(each["text"]).startswith("Question: ")]))


class TheTestCleanupAndTheReservesTests(PassReserveCase):
    def test_a_test_cleanup_whose_models_bucket_is_past_its_five_hour_reserve_pauses_the_epic(self):
        epic = self.epic_at_cleanup()

        printed = self.scheduled_with(epic, carbon=PAST_FIVE_HOURS)

        self.assert_paused_on_reserve(printed)

    def test_a_held_back_test_cleanup_cuts_no_worktree(self):
        epic = self.epic_at_cleanup()
        worktree = self.removed_cleanup_worktree_of(epic)

        self.scheduled_with(epic, carbon=PAST_FIVE_HOURS)

        self.assertFalse(worktree.exists())

    def test_a_test_cleanup_that_runs_gets_its_worktree_cut_again(self):
        epic = self.epic_at_cleanup()
        worktree = self.removed_cleanup_worktree_of(epic)

        self.scheduled_with(epic)

        self.assertTrue(worktree.is_dir())

    def test_a_test_cleanup_whose_models_bucket_is_past_its_weekly_reserve_parks_the_epic_with_the_question(self):
        epic = self.epic_at_cleanup()
        worktree = self.removed_cleanup_worktree_of(epic)

        printed = self.scheduled_with(epic, carbon=PAST_A_WEEK)

        self.assert_parked_with_the_question(epic, printed)
        self.assertFalse(worktree.exists())

    def test_a_test_cleanup_on_another_bucket_runs_while_the_other_buckets_are_past_their_reserves(self):
        epic = self.epic_at_cleanup()

        printed = self.scheduled_with(epic, gemini=PAST_FIVE_HOURS, argon=PAST_A_WEEK)

        self.assertEqual(["test-cleanup"], self.actions_of(printed))
        self.assertIsNone(printed["paused"])

    def test_a_test_cleanup_runs_when_the_reading_cannot_be_had(self):
        epic = self.epic_at_cleanup()

        printed = self.schedule(closed_port(), epic)

        self.assertEqual(["test-cleanup"], self.actions_of(printed))


class TheTidyAndTheReservesTests(PassReserveCase):
    def test_a_tidy_whose_models_bucket_is_past_its_five_hour_reserve_pauses_the_epic(self):
        epic = self.epic_at_tidy()

        printed = self.scheduled_with(epic, gemini=PAST_FIVE_HOURS)

        self.assert_paused_on_reserve(printed)

    def test_a_tidy_whose_models_bucket_is_past_its_weekly_reserve_parks_the_epic_with_the_question(self):
        epic = self.epic_at_tidy()

        printed = self.scheduled_with(epic, gemini=PAST_A_WEEK)

        self.assert_parked_with_the_question(epic, printed)

    def test_a_tidy_runs_while_the_bucket_of_a_later_stage_is_past_its_reserve(self):
        epic = self.epic_at_tidy()

        printed = self.scheduled_with(epic, argon=PAST_FIVE_HOURS, carbon=PAST_A_WEEK)

        self.assertEqual(["tidy"], self.actions_of(printed))


class TheReviewAndTheReservesTests(PassReserveCase):
    def epic_at_review(self) -> str:
        epic, printed = self.finish_epic_at_the_review()
        self.assertEqual({"review"}, set(self.actions_of(printed)))
        return epic

    def test_a_review_pauses_the_epic_when_the_bucket_of_any_of_its_lanes_is_past_its_five_hour_reserve(self):
        for bucket in ("gemini", "argon", "carbon"):
            with self.subTest(bucket=bucket):
                epic = self.epic_at_review()

                printed = self.scheduled_with(epic, **{bucket: PAST_FIVE_HOURS})

                self.assert_paused_on_reserve(printed)

    def test_a_review_parks_the_epic_when_the_bucket_of_its_spec_lane_is_past_its_weekly_reserve(self):
        epic = self.epic_at_review()

        printed = self.scheduled_with(epic, gemini=PAST_A_WEEK)

        self.assert_parked_with_the_question(epic, printed)

    def test_a_review_whose_lanes_draw_on_no_bucket_past_its_reserve_runs(self):
        self.use_routes({"standard": ARGON, "second": ARGON})
        epic = self.epic_at_review()

        printed = self.scheduled_with(epic, gemini=PAST_FIVE_HOURS, carbon=PAST_A_WEEK)

        self.assertEqual({"review"}, set(self.actions_of(printed)))
        self.assertEqual(4, len(printed["actions"]))


class TheFixAndTheReservesTests(PassReserveCase):
    def test_a_fix_whose_models_bucket_is_past_its_five_hour_reserve_pauses_the_epic(self):
        epic = self.epic_at_fix()

        printed = self.scheduled_with(epic, argon=PAST_FIVE_HOURS)

        self.assert_paused_on_reserve(printed)

    def test_a_fix_runs_while_the_bucket_of_another_stage_is_past_its_reserve(self):
        epic = self.epic_at_fix()

        printed = self.scheduled_with(epic, gemini=PAST_FIVE_HOURS, carbon=PAST_A_WEEK)

        self.assertEqual(["fix"], self.actions_of(printed))


class TheValidationMergeAndTheReservesTests(PassReserveCase):
    def test_a_validation_merge_whose_models_bucket_is_past_its_five_hour_reserve_pauses_the_epic(self):
        epic = self.epic_at_merge()

        printed = self.scheduled_with(epic, carbon=PAST_FIVE_HOURS)

        self.assert_paused_on_reserve(printed)

    def test_a_validation_merge_whose_models_bucket_is_past_its_weekly_reserve_parks_the_epic_with_the_question(self):
        epic = self.epic_at_merge()

        printed = self.scheduled_with(epic, carbon=PAST_A_WEEK)

        self.assert_parked_with_the_question(epic, printed)

    def test_a_validation_merge_on_another_bucket_runs(self):
        epic = self.epic_at_merge()

        printed = self.scheduled_with(epic, gemini=PAST_FIVE_HOURS, argon=PAST_A_WEEK)

        self.assertEqual(["merge"], self.actions_of(printed))


if __name__ == "__main__":
    unittest.main()
