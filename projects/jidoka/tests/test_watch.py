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
from test_stop import HUMAN, LAUNCHER, PLUGIN, StopCase  # noqa: E402

WATCH = PLUGIN / "scripts" / "watch.py"
EXIT_TIMEOUT_SECONDS = 60


class WatchCase(StopCase):
    """A handed-off epic with three tasks, and a watcher process that reads its beads every second."""

    def start_watch(self) -> subprocess.Popen:
        watcher = subprocess.Popen([str(LAUNCHER), str(WATCH), self.epic, "--interval", "1"], cwd=self.repo,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                   env={**os.environ, "PATH": fixture.path_with(self.bin),
                                        "JIDOKA_HOME": str(self.home), "BEADS_ACTOR": HUMAN})
        self.addCleanup(watcher.kill)
        self.addCleanup(watcher.stdout.close)
        self.addCleanup(watcher.stderr.close)
        began = watcher.stderr.readline()
        self.assertIn("watching", began, began)
        return watcher

    def event_of(self, watcher: subprocess.Popen) -> dict:
        try:
            out, err = watcher.communicate(timeout=EXIT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            self.fail("the watcher did not exit")
        self.assertEqual(0, watcher.returncode, err)
        return json.loads(out)


class TheWatcherTests(WatchCase):
    def test_it_exits_when_a_parked_task_is_unparked(self):
        [parked, *_] = self.tasks
        self.bd("label", "add", parked, "human")
        watcher = self.start_watch()
        time.sleep(2.5)
        self.assertIsNone(watcher.poll(), "the watcher ended before anything changed")

        self.bd("label", "remove", parked, "human")

        self.assertEqual({"epic": self.epic, "event": "unparked", "bead": parked}, self.event_of(watcher))

    def test_it_exits_when_the_parked_epic_is_unparked(self):
        self.bd("label", "add", self.epic, "human")
        watcher = self.start_watch()

        self.bd("label", "remove", self.epic, "human")

        self.assertEqual({"epic": self.epic, "event": "unparked", "bead": self.epic}, self.event_of(watcher))

    def test_it_exits_when_a_task_is_added_to_the_epic(self):
        watcher = self.start_watch()

        added = self.create("Read the card 9", "--type=task", "--parent", self.epic)

        self.assertEqual({"epic": self.epic, "event": "new-task", "bead": added}, self.event_of(watcher))

    def test_it_exits_when_a_task_merges(self):
        watcher = self.start_watch()

        self.bd("close", self.tasks[1])

        self.assertEqual({"epic": self.epic, "event": "merged", "bead": self.tasks[1]}, self.event_of(watcher))

    def test_it_exits_when_the_pause_it_found_is_over(self):
        ends = int(time.time()) + 3
        held = json.dumps({"cause": "usage-limit", "since": ends - 300, "until": ends, "retries": 0})
        self.bd("update", self.epic, "--set-metadata", f"pause={held}")

        watcher = self.start_watch()

        self.assertEqual({"epic": self.epic, "event": "pause-over", "bead": ""}, self.event_of(watcher))


if __name__ == "__main__":
    unittest.main()
