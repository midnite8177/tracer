import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
from test_stop import HUMAN, LAUNCHER, PLUGIN, RUN_TIMEOUT_SECONDS, SCHEDULER, StopCase  # noqa: E402

WAKE = PLUGIN / "scripts" / "wake.py"
STATUS = PLUGIN / "scripts" / "status.py"
MINUTE = 60
HOUR = 60 * MINUTE
MANAGER_SESSION = "session-of-the-manager"
ADVISOR_SESSION = "session-of-an-advisor"


class PauseCase(StopCase):
    """A handed-off epic whose scheduler runs on a faked clock, the way a manager that meets a limit would."""

    def setUp(self):
        super().setUp()
        self.t0 = int(time.time())

    def call(self, env: dict[str, str], script: Path, *args: str) -> subprocess.CompletedProcess:
        """Runs a script as a call of the manager's session, with more variables in its environment."""
        return subprocess.run([str(LAUNCHER), str(script), *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS, cwd=self.repo,
                              env={**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
                                   "BEADS_ACTOR": HUMAN, "JIDOKA_SESSION_ID": MANAGER_SESSION, **env})

    def script(self, script: Path, *args: str) -> subprocess.CompletedProcess:
        return self.call({}, script, *args)

    def at(self, seconds: int, script: Path, *args: str) -> subprocess.CompletedProcess:
        """Runs a script as a call of the manager's session, on the clock t0 plus the seconds."""
        return self.call({"JIDOKA_NOW": str(self.t0 + seconds)}, script, *args)

    def printed(self, done: subprocess.CompletedProcess) -> dict:
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def report_trouble(self, seconds: int, task: str, cause: str) -> dict:
        return self.printed(self.at(seconds, SCHEDULER, "report", self.epic, task, "cut off", "--cause", cause))

    def carry_on(self, seconds: int) -> dict:
        return self.printed(self.at(seconds, SCHEDULER, "carry-on", self.epic))

    def pause_held(self) -> str:
        return str(self.metadata(self.epic).get("pause") or "")


class AFactoryThatMeetsALimitTests(PauseCase):
    def test_a_usage_limit_pauses_the_epic_and_the_laps_go_on_when_the_back_off_is_over(self):
        running = self.open_two_laps()
        first, second = running

        paused = self.report_trouble(0, first, "usage-limit")

        self.assertEqual({"cause": "usage-limit", "wait_seconds": 5 * MINUTE},
                         {key: paused["paused"][key] for key in ("cause", "wait_seconds")})
        self.assertEqual([], paused["actions"])
        self.assertTrue(paused["watch"])
        self.assertEqual("interrupted", self.metadata(first)["lap.stage"])
        self.assertEqual("open", self.shown(first)["status"])

        again = self.report_trouble(10, second, "usage-limit")
        self.assertEqual(5 * MINUTE - 10, again["paused"]["wait_seconds"])
        self.assertEqual([], self.carry_on(5 * MINUTE - 1)["actions"])
        self.assertEqual(1, self.carry_on(5 * MINUTE - 1)["paused"]["wait_seconds"])

        resumed = self.carry_on(5 * MINUTE)

        self.assertIsNone(resumed["paused"])
        self.assertEqual(sorted(running), sorted(action["task"] for action in resumed["actions"]))
        self.assertEqual({2}, {action["lap"] for action in resumed["actions"]})
        for task in running:
            self.assertEqual("build", self.metadata(task)["lap.stage"])

    def test_the_wait_grows_to_5_15_and_30_minutes_and_then_stays_at_an_hour(self):
        self.open_two_laps()
        waits: list[int] = []
        now = 0
        printed = self.carry_on(now)

        for _ in range(6):
            task = printed["laps"][0]["task"]
            paused = self.report_trouble(now, task, "outage")
            waits.append(paused["paused"]["wait_seconds"])
            now += waits[-1]
            printed = self.carry_on(now)

        self.assertEqual([5 * MINUTE, 15 * MINUTE, 30 * MINUTE, HOUR, HOUR, HOUR], waits)

    def test_a_pause_counts_no_try_no_cutoff_and_parks_no_task(self):
        self.open_two_laps()
        now = 0
        printed = self.carry_on(now)
        for _ in range(4):
            paused = self.report_trouble(now, printed["laps"][0]["task"], "usage-limit")
            now += paused["paused"]["wait_seconds"]
            printed = self.carry_on(now)

        for task in self.tasks:
            shown = self.shown(task)
            self.assertNotIn("human", shown.get("labels") or [])
            self.assertEqual("0", str(shown["metadata"].get("lap.tries", "0")))
            self.assertEqual("0", str(shown["metadata"].get("lap.cutoffs.build", "0")))
        self.assertNotIn("brake.laps", self.metadata(self.epic))

    def test_a_worker_that_ends_without_the_trouble_after_the_wait_ends_the_pause(self):
        [first, _] = self.open_two_laps()
        self.report_trouble(0, first, "usage-limit")
        retried = self.carry_on(5 * MINUTE)
        task = retried["actions"][0]["task"]

        ended = self.printed(self.at(5 * MINUTE + 30, SCHEDULER, "report", self.epic, task, "failed"))

        self.assertEqual("", self.pause_held())
        self.assertIsNone(ended["paused"])

    def test_a_worker_that_ends_while_the_pause_waits_leaves_its_lap_for_the_pause_to_end(self):
        [first, second] = self.open_two_laps()
        self.report_trouble(0, first, "usage-limit")

        waiting = self.printed(self.at(30, SCHEDULER, "report", self.epic, second, "failed"))

        self.assertEqual([], waiting["actions"])
        self.assertEqual(5 * MINUTE - 30, waiting["paused"]["wait_seconds"])
        self.assertNotEqual("", self.pause_held())
        self.assertEqual("interrupted", self.metadata(second)["lap.stage"])
        resumed = self.carry_on(5 * MINUTE)
        self.assertIn(second, [action["task"] for action in resumed["actions"]])

    def test_a_cause_goes_only_with_cut_off(self):
        [first, _] = self.open_two_laps()

        done = self.at(0, SCHEDULER, "report", self.epic, first, "failed", "--cause", "outage")

        self.assertEqual(1, done.returncode)
        self.assertEqual("", self.pause_held())


class StatusOfAPausedEpicTests(PauseCase):
    def test_status_shows_the_cause_the_wait_left_and_the_retries_of_a_paused_epic(self):
        [first, _] = self.open_two_laps()
        self.report_trouble(0, first, "usage-limit")
        retried = self.carry_on(5 * MINUTE)["actions"][0]["task"]
        self.report_trouble(5 * MINUTE + 10, retried, "usage-limit")

        done = self.at(5 * MINUTE + 70, STATUS)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("paused on a usage limit, 14m left, 1 retry", done.stdout)

    def test_status_shows_no_pause_once_the_wait_is_over(self):
        [first, _] = self.open_two_laps()
        self.report_trouble(0, first, "usage-limit")

        done = self.at(5 * MINUTE, STATUS)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("paused on", done.stdout)


class APauseThatWaitsOnTheHumanTests(PauseCase):
    def trouble_then_message(self, cause: str) -> list[dict]:
        [first, _] = self.open_two_laps()
        self.report_trouble(0, first, cause)
        self.carry_on(MINUTE)
        return self.pushover.received

    def test_a_billing_error_sends_one_notification_that_names_the_epic(self):
        [message] = self.trouble_then_message("billing")

        self.assertEqual("Factory paused: Take card payments", message["title"])
        self.assertIn("billing error", message["message"])

    def test_an_auth_failure_sends_one_notification(self):
        [message] = self.trouble_then_message("auth")

        self.assertIn("auth failure", message["message"])

    def test_a_usage_limit_sends_no_notification(self):
        self.assertEqual([], self.trouble_then_message("usage-limit"))

    def test_an_outage_sends_a_notification_only_once_it_has_lasted_an_hour(self):
        self.open_two_laps()
        for now in (0, 5 * MINUTE, 20 * MINUTE, 50 * MINUTE):
            task = self.carry_on(now)["laps"][0]["task"]
            self.report_trouble(now, task, "outage")
        self.assertEqual([], self.pushover.received)

        self.carry_on(HOUR - 1)
        self.assertEqual([], self.pushover.received)
        self.carry_on(HOUR)
        self.carry_on(HOUR + 100)

        [message] = self.pushover.received
        self.assertIn("outage", message["message"])


class WakingAPausedHostTests(PauseCase):
    def wake(self, failures: int) -> subprocess.CompletedProcess:
        return self.at(0, WAKE, "--failures", str(failures), "--session", MANAGER_SESSION)

    def test_the_wake_script_names_the_back_off_for_the_failure_and_the_prompt_that_carries_on(self):
        self.open_two_laps()

        first = self.printed(self.wake(1))
        fourth = self.printed(self.wake(4))

        self.assertEqual((self.epic, 5 * MINUTE, HOUR), (first["epic"], first["seconds"], fourth["seconds"]))
        self.assertIn("scheduler.py", first["text"])
        self.assertIn(f"carry-on {self.epic}", first["text"])

    def wake_after(self, failures: int, error: str) -> subprocess.CompletedProcess:
        return self.at(0, WAKE, "--failures", str(failures), "--session", MANAGER_SESSION, "--error", error)

    def test_a_failed_turn_of_a_session_that_manages_no_epic_pauses_and_wakes_nothing(self):
        self.open_two_laps()

        done = self.at(0, WAKE, "--failures", "1", "--session", ADVISOR_SESSION, "--error", "billing_error")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)
        self.assertEqual("", self.pause_held())
        self.assertEqual([], self.pushover.received)

    def test_a_host_turn_that_ends_on_a_billing_error_pauses_the_epic_and_sends_one_notification(self):
        self.open_two_laps()

        woken = self.printed(self.wake_after(1, "billing_error"))
        self.printed(self.wake_after(2, "billing_error"))

        self.assertEqual(self.epic, woken["epic"])
        self.assertEqual("billing", json.loads(self.pause_held())["cause"])
        [message] = self.pushover.received
        self.assertEqual("Factory paused: Take card payments", message["title"])
        self.assertIn("billing error", message["message"])

    def test_a_host_turn_that_ends_on_an_auth_failure_pauses_the_epic_and_sends_one_notification(self):
        self.open_two_laps()

        self.printed(self.wake_after(1, "authentication_failed"))

        self.assertEqual("auth", json.loads(self.pause_held())["cause"])
        [message] = self.pushover.received
        self.assertIn("auth failure", message["message"])

    def test_a_host_turn_that_ends_on_a_rate_limit_pauses_nothing_and_sends_nothing(self):
        self.open_two_laps()

        self.printed(self.wake_after(1, "rate_limit"))

        self.assertEqual("", self.pause_held())
        self.assertEqual([], self.pushover.received)

    def test_the_wake_script_prints_nothing_where_no_epic_runs(self):
        self.bd("update", self.epic, "--add-label", "human")

        done = self.wake(1)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)


if __name__ == "__main__":
    unittest.main()
