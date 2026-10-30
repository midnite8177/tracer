import contextlib
import dataclasses
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
from test_stop import HUMAN, LAUNCHER, PLUGIN, RUN_TIMEOUT_SECONDS, SCHEDULER, StopCase  # noqa: E402

sys.path.insert(0, str(PLUGIN / "scripts"))
import heartbeat  # noqa: E402
import t3_wake  # noqa: E402
import watch  # noqa: E402

T3_WAKE = PLUGIN / "scripts" / "t3_wake.py"
SESSION_END = PLUGIN / "hooks" / "session_end.py"
SESSION = "session-1"
THREAD = "thread-7"
T3_RELEASE = "other"
SETTLE_SECONDS = 2.5
WAIT_SECONDS = 60


class WakeCase(StopCase):
    """A handed-off epic, a fake t3 that appends its arguments to a file, and the scripts run as processes."""

    def setUp(self):
        super().setUp()
        self.sent = self.root / "sent.txt"
        fake = fixture.write_executable(self.bin / "t3", f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "{self.sent.as_posix()}"\n')
        self.t3 = str(fake)

    def environment(self, session: str | None) -> dict[str, str]:
        environment = {key: value for key, value in os.environ.items() if key != "JIDOKA_SESSION_ID"}
        environment.update({"PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
                            "BEADS_ACTOR": HUMAN, "T3CODE_CLI_PATH": self.t3, "JIDOKA_WAKE_INTERVAL_SECONDS": "1"})
        if session is not None:
            environment["JIDOKA_SESSION_ID"] = session
        return environment

    def claim_the_epic(self, session: str) -> None:
        claimed = self.script_in_session(SCHEDULER, session, "next", self.epic)
        self.assertEqual(0, claimed.returncode, claimed.stderr)

    def record(self, thread: str) -> None:
        self.claim_the_epic(SESSION)
        done = fixture.run_launcher(LAUNCHER, [str(T3_WAKE), "record", self.epic, "--thread", thread], None,
                                    self.environment(SESSION), self.repo, RUN_TIMEOUT_SECONDS)
        self.assertEqual(0, done.returncode, done.stderr)

    def end_session(self, session: str, reason: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(SESSION_END)],
                                    json.dumps({"session_id": session, "cwd": str(self.repo), "reason": reason}),
                                    self.environment(None), self.repo, RUN_TIMEOUT_SECONDS)

    def script_in_session(self, script: Path, session: str, *args: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(script), *args], None, self.environment(session), self.repo,
                                    RUN_TIMEOUT_SECONDS)

    def sent_lines(self) -> list[str]:
        return self.sent.read_text(encoding="utf-8").splitlines() if self.sent.exists() else []

    def wait_for_send(self) -> list[str]:
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            if self.sent_lines():
                return self.sent_lines()
            time.sleep(0.5)
        self.fail("nothing was sent to the thread")

    def assert_nothing_sent_for(self, seconds: float) -> None:
        time.sleep(seconds)
        self.assertEqual([], self.sent_lines())

    def kill_wakers(self) -> None:
        if fixture.WINDOWS:
            fixture.end_orphans_in(self.repo)
            return
        subprocess.run(["pkill", "-f", f"t3_wake.py wait {self.epic} .*--jidoka-home {self.home}$"],
                       capture_output=True)


class TheSessionEndHookTests(WakeCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.kill_wakers)

    def test_it_returns_at_once_and_a_new_task_makes_the_waker_send_the_carry_on_prompt(self):
        self.record(THREAD)

        began = time.monotonic()
        done = self.end_session(SESSION, T3_RELEASE)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertLess(time.monotonic() - began, 20)
        self.assert_nothing_sent_for(2.5)
        self.create("Read the card 9", "--type=task", "--parent", self.epic)

        [line] = self.wait_for_send()

        self.assertTrue(line.startswith(f"thread send {THREAD} "), line)
        self.assertIn(f"scheduler carry-on {self.epic}", line)

    def test_a_session_with_no_recorded_thread_starts_no_waker(self):
        done = self.end_session(SESSION, T3_RELEASE)
        self.assertEqual(0, done.returncode, done.stderr)

        self.create("Read the card 9", "--type=task", "--parent", self.epic)

        self.assert_nothing_sent_for(4)

    def test_a_session_other_than_the_recorded_one_starts_no_waker(self):
        self.record(THREAD)
        self.end_session("session-2", T3_RELEASE)

        self.create("Read the card 9", "--type=task", "--parent", self.epic)

        self.assert_nothing_sent_for(4)

    def test_an_epic_the_factory_no_longer_holds_starts_no_waker(self):
        self.record(THREAD)
        self.bd("close", self.epic)
        done = self.end_session(SESSION, T3_RELEASE)
        self.assertEqual(0, done.returncode, done.stderr)

        self.create("Read the card 9", "--type=task", "--parent", self.epic)

        self.assert_nothing_sent_for(4)

    def test_a_session_end_that_is_not_t3_releasing_the_host_starts_no_waker(self):
        self.record(THREAD)
        for reason in ("clear", "resume", "logout", "prompt_input_exit"):
            done = self.end_session(SESSION, reason)
            self.assertEqual(0, done.returncode, done.stderr)

        self.create("Read the card 9", "--type=task", "--parent", self.epic)

        self.assert_nothing_sent_for(4)

    def test_a_second_session_end_while_a_waker_waits_starts_no_second_waker(self):
        self.record(THREAD)
        self.end_session(SESSION, T3_RELEASE)
        self.end_session(SESSION, T3_RELEASE)
        self.assert_nothing_sent_for(SETTLE_SECONDS)

        self.create("Read the card 9", "--type=task", "--parent", self.epic)

        self.wait_for_send()
        time.sleep(4)
        self.assertEqual(1, len(self.sent_lines()), self.sent_lines())

    def test_a_session_end_after_the_waker_sent_its_prompt_starts_a_new_waker(self):
        self.record(THREAD)
        self.end_session(SESSION, T3_RELEASE)
        self.assert_nothing_sent_for(SETTLE_SECONDS)
        self.create("Read the card 9", "--type=task", "--parent", self.epic)
        self.wait_for_send()
        time.sleep(SETTLE_SECONDS)

        self.end_session(SESSION, T3_RELEASE)
        time.sleep(SETTLE_SECONDS)
        self.create("Read the card 10", "--type=task", "--parent", self.epic)

        deadline = time.monotonic() + WAIT_SECONDS
        while len(self.sent_lines()) < 2 and time.monotonic() < deadline:
            time.sleep(0.5)
        self.assertEqual(2, len(self.sent_lines()), self.sent_lines())

    def test_a_session_resumed_under_a_new_session_id_still_matches_its_epic_s_record(self):
        self.record(THREAD)
        heartbeat.write_beat(self.home, self.epic, 0, SESSION)
        self.claim_the_epic("session-2")

        self.end_session("session-2", T3_RELEASE)
        self.assert_nothing_sent_for(SETTLE_SECONDS)
        self.create("Read the card 9", "--type=task", "--parent", self.epic)

        [line] = self.wait_for_send()
        self.assertTrue(line.startswith(f"thread send {THREAD} "), line)


class TheWakerHeartbeatTests(WakeCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.kill_wakers)

    def beat(self) -> dict | None:
        path = self.home / "heartbeat" / f"{self.epic}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def wait_for_beat(self, accepts) -> dict:
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            held = self.beat()
            if held is not None and accepts(held):
                return held
            time.sleep(0.5)
        self.fail(f"the heartbeat never became what was asked: {self.beat()}")

    def test_a_waiting_waker_beats_the_epic_with_the_session_it_will_wake_and_goes_on_beating(self):
        self.record(THREAD)
        claimed = self.beat()
        self.assertEqual(SESSION, claimed["session"])

        self.end_session(SESSION, T3_RELEASE)

        first = self.wait_for_beat(lambda held: held["time"] > claimed["time"])
        self.assertEqual(self.epic, first["epic"])
        self.assertEqual(SESSION, first["session"])
        later = self.wait_for_beat(lambda held: held["time"] > first["time"])
        self.assertEqual(SESSION, later["session"])


TASKS = frozenset({"t-1", "t-2"})
QUIET = watch.Snapshot(parked=frozenset(), tasks=TASKS, open_tasks=TASKS, paused_until=None)


class FakeEpic:
    """An epic that changes as the waker sleeps: step n is what the waker reads after n sleeps, and the last step
    stays. Each step says what the epic holds and whether the factory still holds it."""

    def __init__(self, steps: list[tuple[watch.Snapshot, bool]]):
        self.steps = steps
        self.step = 0
        self.sent: list[tuple[str, str]] = []

    def read(self) -> watch.Snapshot:
        return self.steps[min(self.step, len(self.steps) - 1)][0]

    def held(self) -> bool:
        return self.steps[min(self.step, len(self.steps) - 1)][1]

    def sleep(self, seconds: float) -> None:
        self.step += 1

    def send(self, thread: str, prompt: str) -> None:
        self.sent.append((thread, prompt))

    def wait_and_send(self, now: int) -> str | None:
        pacing = watch.Pacing(self.sleep, lambda: now)
        with contextlib.redirect_stderr(io.StringIO()):
            return t3_wake.wait_and_send("epic-1", THREAD, Path("/home"), 30, self.read, self.held, pacing, self.send)


class TheWakerBeatTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)

    def read_and_beat(self, now: int) -> None:
        t3_wake.beating(self.home, "epic-1", lambda: QUIET, lambda: now)()

    def test_a_beat_keeps_the_session_that_the_heartbeat_names(self):
        heartbeat.write_beat(self.home, "epic-1", 1000, "session-2")

        self.read_and_beat(1030)

        self.assertEqual(0, heartbeat.beat_age_seconds(self.home, "epic-1", 1030))
        self.assertEqual("session-2", heartbeat.beat_session(self.home, "epic-1"))

    def test_a_heartbeat_that_names_no_session_is_left_as_it_is(self):
        heartbeat.write_beat(self.home, "epic-1", 1000, None)

        self.read_and_beat(1030)

        self.assertEqual(30, heartbeat.beat_age_seconds(self.home, "epic-1", 1030))

    def test_a_beat_starts_no_heartbeat_for_an_epic_that_has_none(self):
        self.read_and_beat(1030)

        self.assertIsNone(heartbeat.beat_age_seconds(self.home, "epic-1", 1030))


class TheWakerTests(unittest.TestCase):
    def test_a_new_task_sends_the_thread_the_carry_on_prompt(self):
        epic = FakeEpic([(QUIET, True), (dataclasses.replace(QUIET, tasks=TASKS | {"t-3"}), True)])

        event = epic.wait_and_send(1000)

        self.assertEqual("new-task", event)
        [(thread, prompt)] = epic.sent
        self.assertEqual(THREAD, thread)
        self.assertIn("scheduler carry-on epic-1", prompt)

    def test_an_unpark_sends_the_carry_on_prompt(self):
        parked = dataclasses.replace(QUIET, parked=frozenset({"t-1"}))
        epic = FakeEpic([(parked, True), (QUIET, True)])

        self.assertEqual("unparked", epic.wait_and_send(1000))
        self.assertEqual(1, len(epic.sent))

    def test_the_end_of_a_pause_sends_the_carry_on_prompt(self):
        epic = FakeEpic([(dataclasses.replace(QUIET, paused_until=1500), True)])

        self.assertEqual("pause-over", epic.wait_and_send(1500))
        self.assertEqual(1, len(epic.sent))

    def test_a_merge_alone_sends_nothing_and_the_watch_goes_on_from_what_the_epic_holds_then(self):
        merged = dataclasses.replace(QUIET, open_tasks=frozenset({"t-1"}))
        added = dataclasses.replace(merged, tasks=TASKS | {"t-3"}, open_tasks=merged.open_tasks | {"t-3"})
        epic = FakeEpic([(QUIET, True), (merged, True), (merged, True), (added, True)])

        self.assertEqual("new-task", epic.wait_and_send(1000))
        self.assertEqual(3, epic.step)
        self.assertEqual(1, len(epic.sent))

    def test_an_epic_the_factory_stops_holding_while_it_waits_sends_nothing(self):
        epic = FakeEpic([(QUIET, True), (dataclasses.replace(QUIET, tasks=TASKS | {"t-3"}), False)])

        self.assertIsNone(epic.wait_and_send(1000))
        self.assertEqual([], epic.sent)

    def test_an_epic_the_factory_does_not_hold_sends_nothing(self):
        epic = FakeEpic([(QUIET, False)])

        self.assertIsNone(epic.wait_and_send(1000))
        self.assertEqual([], epic.sent)


if __name__ == "__main__":
    unittest.main()
