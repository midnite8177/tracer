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
from test_stop import (HANDOFF, HUMAN, LAUNCHER, ONE_SEAM, OUT_OF_SCOPE, PLUGIN, SCHEDULER,  # noqa: E402
                       StopCase)

WATCH = PLUGIN / "scripts" / "watch.py"
EXIT_TIMEOUT_SECONDS = 60


class WatchCase(StopCase):
    """A handed-off epic with three tasks, and a watcher process that reads its beads every second. The machine's
    one slot is held by another running epic, as it is when the scheduler leaves the epic's ready tasks waiting."""

    def setUp(self):
        super().setUp()
        self.set_machine_limit(1)
        self.other_epic_holds(1, "web", self.repo)

    def set_machine_limit(self, limit: int) -> None:
        (self.home / "settings.json").write_text(json.dumps({"lap_limit": limit}), encoding="utf-8")

    def other_epic_holds(self, slot: int, area: str, repo: Path) -> None:
        """Records a lap of a running epic: its heartbeat is fresh and the slot record holds its one claim."""
        self.other_epic_beats(0)
        claim = {"epic": "other-1", "task": "other-2", "slot": slot, "repo": str(repo), "area": area}
        (self.home / "slots.json").write_text(json.dumps({"slots": [claim]}), encoding="utf-8")

    def other_epic_beats(self, seconds_ago: int) -> None:
        beat = {"epic": "other-1", "time": int(time.time()) - seconds_ago, "session": "manager", "fresh_seconds": 90}
        (self.home / "heartbeat").mkdir(exist_ok=True)
        (self.home / "heartbeat" / "other-1.json").write_text(json.dumps(beat), encoding="utf-8")

    def other_epic_frees_its_slot(self) -> None:
        (self.home / "slots.json").write_text(json.dumps({"slots": []}), encoding="utf-8")

    def start_watch(self) -> subprocess.Popen:
        return self.launch(None)

    def start_watch_under_t3(self) -> subprocess.Popen:
        return self.launch("/t3")

    def launch(self, t3_path: str | None) -> subprocess.Popen:
        environment = {key: value for key, value in os.environ.items() if key != "T3CODE_CLI_PATH"}
        if t3_path is not None:
            environment["T3CODE_CLI_PATH"] = t3_path
        command = fixture.launch_command(LAUNCHER, [str(WATCH), self.epic, "--interval", "1"])
        watcher = subprocess.Popen(command, cwd=self.repo,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                   env={**environment, "PATH": fixture.path_with(self.bin),
                                        "JIDOKA_HOME": str(self.home), "BEADS_ACTOR": HUMAN})
        self.addCleanup(watcher.stdout.close)
        self.addCleanup(watcher.stderr.close)
        self.addCleanup(watcher.wait)
        self.addCleanup(fixture.end_process, watcher.pid)
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

    def test_under_t3_it_goes_on_waiting_while_nothing_changes(self):
        watcher = self.start_watch_under_t3()
        time.sleep(3.5)

        self.assertIsNone(watcher.poll(), "the watcher ended with nothing changed")


class TheWatcherBesideAnotherEpicTests(WatchCase):
    """The epic's ready tasks wait on what another running epic holds in the jidoka home's slot record."""

    def setUp(self):
        super().setUp()
        self.till, self.receipts, self.shelf = self.tasks

    def only_the_till_task_is_ready(self) -> None:
        self.bd("close", self.receipts)
        self.bd("close", self.shelf)

    def test_it_exits_when_another_epic_frees_a_slot_that_a_ready_task_waited_for(self):
        watcher = self.start_watch()
        time.sleep(2.5)
        self.assertIsNone(watcher.poll(), "the watcher ended before anything changed")

        self.other_epic_frees_its_slot()

        event = self.event_of(watcher)
        self.assertEqual(("room-freed", self.epic), (event["event"], event["epic"]))
        self.assertIn(event["bead"], self.tasks)

    def test_it_exits_at_once_when_the_room_was_freed_before_the_watch_began(self):
        self.other_epic_frees_its_slot()

        watcher = self.start_watch()

        event = self.event_of(watcher)
        self.assertEqual(("room-freed", self.epic), (event["event"], event["epic"]))
        self.assertEqual(self.till, event["bead"])

    def test_it_exits_naming_the_task_that_waited_for_the_area_another_epic_of_the_repo_frees(self):
        self.set_machine_limit(4)
        self.only_the_till_task_is_ready()
        self.other_epic_holds(1, "till", self.repo)
        watcher = self.start_watch()

        self.other_epic_holds(1, "web", self.repo)

        self.assertEqual({"epic": self.epic, "event": "room-freed", "bead": self.till}, self.event_of(watcher))

    def test_it_goes_on_waiting_when_another_repos_epic_changes_area_and_still_holds_the_machines_one_slot(self):
        self.only_the_till_task_is_ready()
        self.other_epic_holds(1, "till", self.root / "mill")
        watcher = self.start_watch()

        self.other_epic_holds(1, "web", self.root / "mill")
        time.sleep(3.5)

        self.assertIsNone(watcher.poll(), "the watcher ended though the machine stayed full")

    def test_it_goes_on_waiting_when_a_slot_is_freed_and_the_epic_has_no_ready_task(self):
        for task in self.tasks:
            self.bd("label", "add", task, "human")
        watcher = self.start_watch()

        self.other_epic_frees_its_slot()
        time.sleep(3.5)

        self.assertIsNone(watcher.poll(), "the watcher ended with no ready task")

    def test_it_goes_on_waiting_when_a_slot_is_freed_and_the_epic_is_paused(self):
        until = int(time.time()) + 600
        held = json.dumps({"cause": "usage-limit", "since": until - 300, "until": until, "retries": 0})
        self.bd("update", self.epic, "--set-metadata", f"pause={held}")
        watcher = self.start_watch()

        self.other_epic_frees_its_slot()
        time.sleep(3.5)

        self.assertIsNone(watcher.poll(), "the watcher ended for a paused epic")

    def test_it_exits_when_the_epic_that_the_scheduler_gave_the_machines_one_slot_stops_running(self):
        self.other_epic_frees_its_slot()
        (self.home / "heartbeat" / "other-1.json").unlink()
        other = self.create("Search the shop", "--type=epic", "--description", OUT_OF_SCOPE)
        searching = self.create("Search the card 0", "--type=task", "--parent", other, "--description", ONE_SEAM)
        done = self.script(HANDOFF, "take", other, f"--area={searching}=search")
        self.assertEqual(0, done.returncode, done.stderr)
        opened = json.loads(self.script(SCHEDULER, "next", other, "--jidoka-home", str(self.home)).stdout)
        self.assertEqual([searching], [action["task"] for action in opened["actions"]])
        waiting = json.loads(self.script(SCHEDULER, "next", self.epic, "--jidoka-home", str(self.home)).stdout)
        self.assertEqual(([], True), (waiting["actions"], waiting["watch"]))
        watcher = self.start_watch()

        stale = {"epic": other, "time": int(time.time()) - 600, "session": "manager", "fresh_seconds": 90}
        (self.home / "heartbeat" / f"{other}.json").write_text(json.dumps(stale), encoding="utf-8")

        self.assertEqual("room-freed", self.event_of(watcher)["event"])

    def test_it_exits_when_a_running_epic_that_holds_no_lap_stops_running_and_so_stops_reserving_a_slot(self):
        self.set_machine_limit(2)
        self.other_epic_frees_its_slot()
        done = self.script(SCHEDULER, "next", self.epic, "--jidoka-home", str(self.home))
        self.assertEqual(0, done.returncode, done.stderr)
        waiting = json.loads(done.stdout)
        self.assertEqual(1, len(waiting["actions"]), "the one slot beside the reserved one is taken")
        self.assertTrue(waiting["watch"])
        watcher = self.start_watch()
        time.sleep(2.5)
        self.assertIsNone(watcher.poll(), "the watcher ended before the reservation was released")

        self.other_epic_beats(600)

        self.assertEqual("room-freed", self.event_of(watcher)["event"])


if __name__ == "__main__":
    unittest.main()
