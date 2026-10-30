import contextlib
import dataclasses
import io
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
from test_stop import HUMAN, LAUNCHER, PLUGIN, RUN_TIMEOUT_SECONDS, StopCase  # noqa: E402

sys.path.insert(0, str(PLUGIN / "scripts"))
import t3_wake  # noqa: E402
import watch  # noqa: E402

T3_WAKE = PLUGIN / "scripts" / "t3_wake.py"
SESSION_END = PLUGIN / "hooks" / "session_end.py"
SESSION = "session-1"
THREAD = "thread-7"
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

    def record(self, thread: str) -> None:
        command = fixture.launch_command(LAUNCHER, [str(T3_WAKE), "record", self.epic, "--thread", thread])
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS,
                              cwd=self.repo, env=self.environment(SESSION))
        self.assertEqual(0, done.returncode, done.stderr)

    def end_session(self, session: str) -> subprocess.CompletedProcess:
        return subprocess.run(fixture.launch_command(LAUNCHER, [str(SESSION_END)]), input=json.dumps(
            {"session_id": session, "cwd": str(self.repo), "reason": "other"}), capture_output=True, text=True,
            encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS, cwd=self.repo, env=self.environment(None))

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
        subprocess.run(["pkill", "-f", f"t3_wake.py wait {self.epic}"], capture_output=True)


class TheSessionEndHookTests(WakeCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.kill_wakers)

    def test_it_returns_at_once_and_a_new_task_makes_the_waker_send_the_carry_on_prompt(self):
        self.record(THREAD)

        began = time.monotonic()
        done = self.end_session(SESSION)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertLess(time.monotonic() - began, 20)
        self.assert_nothing_sent_for(2.5)
        self.create("Read the card 9", "--type=task", "--parent", self.epic)

        [line] = self.wait_for_send()

        self.assertTrue(line.startswith(f"thread send {THREAD} "), line)
        self.assertIn(f"scheduler carry-on {self.epic}", line)

    def test_a_session_with_no_recorded_thread_starts_no_waker(self):
        done = self.end_session(SESSION)
        self.assertEqual(0, done.returncode, done.stderr)

        self.create("Read the card 9", "--type=task", "--parent", self.epic)

        self.assert_nothing_sent_for(4)

    def test_a_session_other_than_the_recorded_one_starts_no_waker(self):
        self.record(THREAD)
        self.end_session("session-2")

        self.create("Read the card 9", "--type=task", "--parent", self.epic)

        self.assert_nothing_sent_for(4)

    def test_an_epic_the_factory_no_longer_holds_starts_no_waker(self):
        self.record(THREAD)
        self.bd("close", self.epic)
        done = self.end_session(SESSION)
        self.assertEqual(0, done.returncode, done.stderr)

        self.create("Read the card 9", "--type=task", "--parent", self.epic)

        self.assert_nothing_sent_for(4)


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
        pacing = watch.Pacing(self.sleep, lambda: now, lambda: 0.0)
        with contextlib.redirect_stderr(io.StringIO()):
            return t3_wake.wait_and_send("epic-1", THREAD, Path("/home"), 30, self.read, self.held, pacing, self.send)


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
