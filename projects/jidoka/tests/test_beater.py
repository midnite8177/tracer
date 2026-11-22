import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
from test_stop import HUMAN, LAUNCHER, PLUGIN, RUN_TIMEOUT_SECONDS, SCHEDULER, StopCase  # noqa: E402

sys.path.insert(0, str(PLUGIN / "scripts"))
import beater  # noqa: E402
import file_lock  # noqa: E402
import heartbeat  # noqa: E402
import processes  # noqa: E402

FACTORY_STATE = PLUGIN / "scripts" / "factory_state.py"
THREAD = "thread-7"
OTHER_THREAD = "thread-9"
CLAUDE_SESSION = "session-1"
WAIT_SECONDS = 30
BEAT_SECONDS = "1"
SECONDS_AHEAD_OF_THE_STAND_IN_CLOCK = 5


class BeaterCase(StopCase):
    """A handed-off epic and the scheduler, the factory state and the beater run as processes in a temp repo, with a
    beat every second, and the caller's session and thread named by the variables a test gives each call."""

    def setUp(self):
        super().setUp()
        self.addCleanup(self.end_beaters)

    def call(self, variables: dict[str, str], script: Path, *args: str) -> subprocess.CompletedProcess:
        ambient = ("JIDOKA_SESSION_ID", "T3CODE_THREAD_ID", "JIDOKA_NOW")
        environment = {key: value for key, value in os.environ.items() if key not in ambient}
        environment.update({"PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
                            "BEADS_ACTOR": HUMAN, beater.INTERVAL_VARIABLE: BEAT_SECONDS, **variables})
        return fixture.run_launcher(LAUNCHER, [str(script), *args], None, environment, self.repo, RUN_TIMEOUT_SECONDS)

    def next_in_thread(self, thread: str) -> subprocess.CompletedProcess:
        return self.call({"T3CODE_THREAD_ID": thread}, SCHEDULER, "next", self.epic)

    def claim_in_thread(self, thread: str) -> list[str]:
        done = self.next_in_thread(thread)
        self.assertEqual(0, done.returncode, done.stderr)
        return [action["task"] for action in json.loads(done.stdout)["actions"]]

    def end_beaters(self) -> None:
        for path in sorted((self.home / beater.BEATER_FOLDER).glob("*.json")):
            held = json.loads(path.read_text(encoding="utf-8"))
            pid = beater.running_beater(self.home, held["thread"])
            if pid is not None:
                processes.end_process(pid)

    def wait_until(self, condition: Callable[[], bool], what: str) -> None:
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.2)
        self.fail(f"it never came about: {what}")

    def wait_for_the_beater_to_end(self, thread: str) -> None:
        self.wait_until(lambda: beater.running_beater(self.home, thread) is None, "the beater ended")

    def held_beat(self) -> heartbeat.Heartbeat:
        held = heartbeat.read_heartbeat(self.home, self.epic)
        self.assertIsNotNone(held)
        return held


class TheBeaterStartsTests(BeaterCase):
    def test_with_only_the_thread_id_set_the_claim_names_the_thread(self):
        self.claim_in_thread(THREAD)

        self.assertEqual(THREAD, heartbeat.beat_session(self.home, self.epic))

    def test_a_scheduler_call_starts_one_beater_and_a_second_call_starts_none(self):
        self.claim_in_thread(THREAD)
        started = beater.running_beater(self.home, THREAD)
        self.assertIsNotNone(started)

        carried_on = self.call({"T3CODE_THREAD_ID": THREAD}, SCHEDULER, "carry-on", self.epic)
        again = self.next_in_thread(THREAD)

        self.assertEqual(0, carried_on.returncode, carried_on.stderr)
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertEqual(started, beater.running_beater(self.home, THREAD))

    def test_a_host_that_exports_a_session_starts_no_beater_though_it_runs_in_a_thread(self):
        done = self.call({"JIDOKA_SESSION_ID": CLAUDE_SESSION, "T3CODE_THREAD_ID": THREAD}, SCHEDULER, "next",
                         self.epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(CLAUDE_SESSION, heartbeat.beat_session(self.home, self.epic))
        self.assertFalse((self.home / beater.BEATER_FOLDER).exists())

    def test_a_call_that_knows_no_thread_starts_no_beater(self):
        done = self.call({}, SCHEDULER, "next", self.epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertFalse((self.home / beater.BEATER_FOLDER).exists())


class TheBeaterBeatsTests(BeaterCase):
    def test_the_beater_renews_the_heartbeat_that_names_its_thread_while_the_manager_sits_idle(self):
        self.claim_in_thread(THREAD)
        claimed = self.held_beat().time

        self.wait_until(lambda: self.held_beat().time > claimed, "the heartbeat was renewed")
        renewed = self.held_beat()
        self.wait_until(lambda: self.held_beat().time > renewed.time, "the heartbeat was renewed again")

        self.assertEqual(THREAD, self.held_beat().session)
        self.assertTrue(self.held_beat().is_fresh(int(time.time())))
        self.assertIsNotNone(beater.running_beater(self.home, THREAD))

    def test_a_heartbeat_that_names_another_session_is_not_renewed_and_ends_the_beater(self):
        self.claim_in_thread(THREAD)
        now = int(time.time())
        heartbeat.write_beat(self.home, self.epic, now, "session-2")

        self.wait_for_the_beater_to_end(THREAD)

        self.assertEqual(heartbeat.Heartbeat(now, "session-2", False), self.held_beat())

    def test_a_stale_heartbeat_is_not_renewed_and_ends_the_beater(self):
        self.claim_in_thread(THREAD)
        long_ago = int(time.time()) - 200
        heartbeat.write_beat(self.home, self.epic, long_ago, THREAD)

        self.wait_for_the_beater_to_end(THREAD)

        self.assertEqual(heartbeat.Heartbeat(long_ago, THREAD, False), self.held_beat())

    def test_a_stop_ends_the_beater_and_the_heartbeat_stays_stopped(self):
        self.claim_in_thread(THREAD)

        stopped = self.call({}, SCHEDULER, "stop", self.epic)

        self.assertEqual(0, stopped.returncode, stopped.stderr)
        self.wait_for_the_beater_to_end(THREAD)
        self.assertTrue(self.held_beat().stopped)


class ASecondManagerTests(BeaterCase):
    def test_a_manager_in_another_thread_is_refused_and_stops_no_live_lap_and_no_heartbeat(self):
        running = self.claim_in_thread(THREAD)
        self.assertTrue(running)
        stand_in = str(int(time.time()) - SECONDS_AHEAD_OF_THE_STAND_IN_CLOCK)

        refused = self.call({"T3CODE_THREAD_ID": OTHER_THREAD, "JIDOKA_NOW": stand_in}, SCHEDULER, "next", self.epic)
        closing = self.call({"T3CODE_THREAD_ID": OTHER_THREAD}, FACTORY_STATE, "--json", "--stopping", self.epic)

        self.assertEqual(1, refused.returncode)
        self.assertIn(f"{self.epic} already has a manager", refused.stderr)
        self.assertEqual(0, closing.returncode, closing.stderr)
        for task in running:
            self.assertEqual("build", self.metadata(task)["lap.stage"])
        self.assertEqual(THREAD, self.held_beat().session)
        self.assertFalse(self.held_beat().stopped)
        self.assertIsNone(beater.running_beater(self.home, OTHER_THREAD))
        self.assertIsNotNone(beater.running_beater(self.home, THREAD))


class SerializedHeartbeatWritesTests(unittest.TestCase):
    """The renewal, the stop and the claim of one epic's heartbeat take the epic's lock from the read to the write.
    Each test holds the lock as a stop or a claim from another process would, and lets the write in question come
    after it."""

    EPIC = "epic-1"
    NOW = 1_800_000_000
    HELD_LONG_ENOUGH_SECONDS = 0.3

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        heartbeat.write_beat(self.home, self.EPIC, self.NOW, THREAD)

    def run_while_the_lock_is_held(self, write: Callable[[], object], during_the_hold: Callable[[], None]) -> object:
        """Starts `write` while this test holds the epic's lock, runs `during_the_hold`, lets go and returns what
        `write` returned. It fails when `write` finished before the lock was let go."""
        returned: list[object] = []
        writing = threading.Thread(target=lambda: returned.append(write()))
        with file_lock.exclusive(heartbeat.lock_path(self.home, self.EPIC)):
            writing.start()
            writing.join(self.HELD_LONG_ENOUGH_SECONDS)
            self.assertTrue(writing.is_alive(), "the write did not wait for the lock")
            during_the_hold()
        writing.join(WAIT_SECONDS)
        self.assertFalse(writing.is_alive())
        return returned[0]

    def test_a_renewal_that_waited_for_a_stop_leaves_the_heartbeat_stopped(self):
        stopped = heartbeat.Heartbeat(self.NOW, None, True)

        renewed = self.run_while_the_lock_is_held(
            lambda: heartbeat.renew(self.home, self.EPIC, self.NOW + 30, THREAD),
            lambda: heartbeat.write_heartbeat(self.home, self.EPIC, stopped))

        self.assertIs(False, renewed)
        self.assertEqual(stopped, heartbeat.read_heartbeat(self.home, self.EPIC))

    def test_a_renewal_that_waited_for_another_sessions_claim_leaves_that_claim(self):
        claim = heartbeat.Heartbeat(self.NOW + 10, "session-2", False)

        renewed = self.run_while_the_lock_is_held(
            lambda: heartbeat.renew(self.home, self.EPIC, self.NOW + 30, THREAD),
            lambda: heartbeat.write_heartbeat(self.home, self.EPIC, claim))

        self.assertIs(False, renewed)
        self.assertEqual(claim, heartbeat.read_heartbeat(self.home, self.EPIC))

    def test_a_renewal_with_the_lock_free_writes_a_beat_for_the_session_that_claimed_the_epic(self):
        renewed = heartbeat.renew(self.home, self.EPIC, self.NOW + 30, THREAD)

        self.assertIs(True, renewed)
        self.assertEqual(heartbeat.Heartbeat(self.NOW + 30, THREAD, False),
                         heartbeat.read_heartbeat(self.home, self.EPIC))

    def test_a_stop_waits_for_the_lock_before_it_reads_which_session_claimed_the_epic(self):
        claim = heartbeat.Heartbeat(self.NOW + 10, "session-2", False)

        self.run_while_the_lock_is_held(lambda: heartbeat.stop(self.home, self.EPIC, self.NOW + 20, THREAD),
                                        lambda: heartbeat.write_heartbeat(self.home, self.EPIC, claim))

        self.assertEqual(claim, heartbeat.read_heartbeat(self.home, self.EPIC))


if __name__ == "__main__":
    unittest.main()
