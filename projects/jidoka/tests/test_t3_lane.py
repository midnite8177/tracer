import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_ledger  # noqa: E402
import test_review  # noqa: E402
import test_scheduler  # noqa: E402
from test_scheduler import LAUNCHER, PLUGIN, RUN_TIMEOUT_SECONDS  # noqa: E402

T3_LANE = PLUGIN / "scripts" / "t3_lane.py"
T3_ROUTE = {"harness": "t3", "provider": "codex-home", "model": "gpt-6.1-sol", "version": None, "effort": "high"}
STARTED_AT = 1_800_000_000
FINISHED_AT = STARTED_AT + 95


def spec_finding(title: str) -> dict:
    return test_review.finding(title, "small", "high")


def settings_with_second_tier(second: dict) -> str:
    return json.dumps({"routes": {**test_ledger.ROUTES["routes"], "second": second}})


class T3LaneCase(test_ledger.LedgerBooks, test_review.ReviewCase):
    """The review's lanes, with the second tier routed to t3 and a child's reply given as a file."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.home / "settings.json").write_text(settings_with_second_tier(T3_ROUTE), encoding="utf-8")

    def spec_action_of(self, printed: dict) -> dict:
        [action] = [each for each in self.review_actions_of(printed) if each["lane"] == "spec"]
        return action

    def lane_at(self, now: int, mode: str, *args: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(T3_LANE), mode, *args], None,
                                    {**self.caller_env(self.home), "JIDOKA_NOW": str(now)}, self.repo,
                                    RUN_TIMEOUT_SECONDS)

    def start_lane(self, epic: str, action: dict, *extra: str) -> subprocess.CompletedProcess:
        return self.lane_at(STARTED_AT, "start", epic, "--worktree", action["worktree"], "--report", action["report"],
                            "--base", action["base"], "--head", action["head"],
                            *(part for each in action["files"] for part in ("--file", each)), "--doc",
                            str(self.repo / "CLAUDE.md"), *extra)

    def finish_lane(self, action: dict, started: dict | None, reply: str | None) -> subprocess.CompletedProcess:
        """Finishes the lane after saving the reply where `start` said to; a lane that never started has no path."""
        if started is not None:
            reply_file = Path(started["reply"])
            reply_file.unlink(missing_ok=True)
            if reply is not None:
                reply_file.write_text(reply, encoding="utf-8")
        return self.lane_at(FINISHED_AT, "finish", "--report", action["report"])

    def started(self, epic: str, action: dict, *extra: str) -> dict:
        done = self.start_lane(epic, action, *extra)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def second_tier_settings(self, second: dict) -> None:
        (self.home / "settings.json").write_text(settings_with_second_tier(second), encoding="utf-8")

    def other_lanes_found_nothing(self, printed: dict) -> None:
        for action in self.review_actions_of(printed):
            if action["lane"] != "spec":
                Path(action["report"]).write_text("[]", encoding="utf-8")

    def rows_of(self, epic: str) -> list[dict]:
        return self.passes_of(epic)


class TheSpecLaneStartsAsAT3ChildTaskTests(T3LaneCase):
    def test_the_task_reads_the_review_worktree_by_absolute_paths_and_writes_nothing(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)

        task = self.started(epic, action)["delegate_task"]["task"]

        worktree = action["worktree"]
        self.assertIn(f"git -C {worktree} diff {action['base']} {action['head']}", task)
        self.assertIn(f"{worktree}/{test_review.BUILT_FILE}", task)
        self.assertIn("Change no file", task)
        self.assertIn("Take card payments", task)

    def test_start_prints_the_delegate_task_arguments_whole_as_a_shared_async_review_on_the_route(self):
        epic, printed = self.finish_epic_at_the_review()

        delegate = self.started(epic, self.spec_action_of(printed))["delegate_task"]

        self.assertTrue(delegate.pop("task"))
        self.assertEqual({"role": "review", "isolation": "shared", "mode": "async",
                          "target": {"providerInstanceId": "codex-home", "model": "gpt-6.1-sol",
                                     "options": {"effort": "high"}}}, delegate)

    def test_start_prints_the_deadline_from_the_review_stages_wall_clock(self):
        epic, printed = self.finish_epic_at_the_review()

        started = self.started(epic, self.spec_action_of(printed), "--wall-seconds", "600")

        self.assertEqual((600, STARTED_AT + 600), (started["wall_seconds"], started["deadline"]))

    def test_a_second_tier_that_does_not_route_to_t3_refuses_to_start(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        (self.home / "settings.json").write_text(json.dumps(test_ledger.ROUTES), encoding="utf-8")
        try:
            done = self.start_lane(epic, action)
        finally:
            self.second_tier_settings(T3_ROUTE)

        self.assertEqual(1, done.returncode)
        self.assertIn("not on t3", done.stderr)

    def test_a_t3_route_without_an_effort_refuses_to_start(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        self.second_tier_settings({**T3_ROUTE, "effort": None})
        try:
            done = self.start_lane(epic, action)
        finally:
            self.second_tier_settings(T3_ROUTE)

        self.assertEqual(1, done.returncode)
        self.assertIn("effort", done.stderr)

    def test_a_t3_route_without_a_model_refuses_to_start(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        self.second_tier_settings({**T3_ROUTE, "model": None})
        try:
            done = self.start_lane(epic, action)
        finally:
            self.second_tier_settings(T3_ROUTE)

        self.assertEqual(1, done.returncode)
        self.assertIn("the t3 route of the tier 'second' needs a model", done.stderr)


class TheReportIsWrittenFromTheChildsLastReplyTests(T3LaneCase):
    def test_the_report_is_written_from_the_reply_and_the_reviews_settle_accepts_it(self):
        epic, printed = self.finish_epic_at_the_review()
        self.other_lanes_found_nothing(printed)
        action = self.spec_action_of(printed)
        started = self.started(epic, action)
        reply = f"The diff is thin.\n```json\n{json.dumps([spec_finding('Missing tax')])}\n```\n"

        done = self.finish_lane(action, started, reply)
        settled = self.report_review(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(0, settled.returncode, settled.stderr)
        self.assertEqual({"findings": 1, "lane": "spec"},
                         {key: json.loads(done.stdout)[key] for key in ("findings", "lane")})
        [fixed] = json.loads(settled.stdout)["review"]["fixes"]
        self.assertEqual(("spec", "Missing tax"), (fixed["lane"], fixed["title"]))

    def test_the_run_writes_one_ledger_row_with_harness_t3_the_wall_time_and_no_tokens(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        started = self.started(epic, action)

        done = self.finish_lane(action, started, "[]")

        self.assertEqual(0, done.returncode, done.stderr)
        [row] = self.rows_of(epic)
        keys = ("stage", "tier", "harness", "model", "effort", "agent", "outcome", "task", "wall_seconds",
                "input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens")
        self.assertEqual({"stage": "review", "tier": "second", "harness": "t3", "model": "gpt-6.1-sol",
                          "effort": "high", "agent": None, "outcome": "done", "task": None, "wall_seconds": 95,
                          "input_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0, "output_tokens": 0},
                         {key: row[key] for key in keys})

    def test_a_settings_change_between_start_and_finish_does_not_change_the_route_the_row_names(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        started = self.started(epic, action)
        self.second_tier_settings({**T3_ROUTE, "model": "gpt-6-luna", "effort": "low"})
        try:
            done = self.finish_lane(action, started, "[]")
        finally:
            self.second_tier_settings(T3_ROUTE)

        self.assertEqual(0, done.returncode, done.stderr)
        [row] = self.rows_of(epic)
        self.assertEqual(("gpt-6.1-sol", "high"), (row["model"], row["effort"]))


class AFailedChildRunExitsOneAndLeavesNoReportTests(T3LaneCase):
    def assert_failed_without_a_report(self, epic: str, action: dict, done: subprocess.CompletedProcess,
                                       reason: str) -> None:
        self.assertEqual(1, done.returncode)
        self.assertIn(reason, done.stderr)
        self.assertFalse(Path(action["report"]).exists())
        [row] = self.rows_of(epic)
        self.assertEqual(("t3", "failed", 95), (row["harness"], row["outcome"], row["wall_seconds"]))

    def test_a_reply_with_no_list_of_findings_fails_the_lane(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        started = self.started(epic, action)

        done = self.finish_lane(action, started, "The diff looks fine to me.")

        self.assert_failed_without_a_report(epic, action, done, "no JSON list")

    def test_a_list_the_review_would_refuse_fails_the_lane_so_settle_never_sees_it(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        started = self.started(epic, action)
        unsized = spec_finding("Missing tax")
        del unsized["size"]

        done = self.finish_lane(action, started, json.dumps([unsized]))

        self.assert_failed_without_a_report(epic, action, done, "size")

    def test_a_blank_reply_fails_the_lane(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        started = self.started(epic, action)

        done = self.finish_lane(action, started, "   ")

        self.assert_failed_without_a_report(epic, action, done, "no reply")

    def test_a_child_that_left_no_reply_file_fails_the_lane(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        started = self.started(epic, action)

        done = self.finish_lane(action, started, None)

        self.assert_failed_without_a_report(epic, action, done, "no reply")

    def test_a_main_checkout_that_changed_while_the_child_ran_fails_the_lane_even_with_a_good_reply(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        started = self.started(epic, action)
        (self.repo / "written-by-the-child.txt").write_text("oops\n", encoding="utf-8")
        try:
            done = self.finish_lane(action, started, "[]")
        finally:
            (self.repo / "written-by-the-child.txt").unlink()

        self.assert_failed_without_a_report(epic, action, done, "changed while the child ran")

    def test_a_run_past_the_stages_wall_clock_fails_the_lane_even_with_a_good_reply(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        started = self.started(epic, action, "--wall-seconds", "60")

        done = self.finish_lane(action, started, "[]")

        self.assert_failed_without_a_report(epic, action, done, "wall clock of 60 seconds")

    def test_a_lane_that_never_started_fails_without_a_row(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)

        done = self.finish_lane(action, None, None)

        self.assertEqual(1, done.returncode)
        self.assertIn("never started", done.stderr)
        self.assertFalse(Path(action["report"]).exists())
        self.assertEqual([], self.rows_of(epic))


if __name__ == "__main__":
    unittest.main()
