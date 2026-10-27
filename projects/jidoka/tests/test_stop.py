import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
from test_notify import APP_TOKEN, USER_KEY, UI_URL, PushoverStandIn  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
SCHEDULER = PLUGIN / "scripts" / "scheduler.py"
HANDOFF = PLUGIN / "scripts" / "handoff.py"
SETTINGS_SCRIPT = PLUGIN / "scripts" / "repo_settings.py"

RUN_TIMEOUT_SECONDS = 120
OUT_OF_SCOPE = "## Out of Scope\nRefunds."
ONE_SEAM = "## Seams\nThe card reader, run as a process."
HUMAN = "Pat Human"
LAP_LIMIT = 2


class StopCase(unittest.TestCase):
    """A temporary git repo with the fake bd's beads, a temporary jidoka home that holds repo settings
    and Pushover keys, a Pushover stand-in, and one epic handed off with three tasks in three areas."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "shop"
        fixture.init_repo(self.repo)
        fixture.run(["git", "config", "user.name", HUMAN], self.repo)
        (self.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Start")
        fixture.run(["git", "branch", "-M", "main"], self.repo)
        self.bin = self.root / "bin"
        self.fake_bd = str(fixture.add_fake_beads(self.repo, self.bin))
        self.home = self.root / "jidoka-home"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        self.pushover = PushoverStandIn()
        self.addCleanup(self.pushover.server_close)
        self.addCleanup(self.pushover.shutdown)
        keys = {"user_key": USER_KEY, "app_token": APP_TOKEN, "ui_url": UI_URL, "api_url": self.pushover.url}
        (self.home / "pushover.json").write_text(json.dumps(keys), encoding="utf-8")
        self.write_settings()
        self.epic = self.create("Take card payments", "--type=epic", "--description", OUT_OF_SCOPE)
        self.tasks = [self.create(f"Read the card {number}", "--type=task", "--parent", self.epic,
                                  "--description", ONE_SEAM)
                      for number in range(3)]
        self.hand_off(dict(zip(self.tasks, ("till", "receipts", "shelf"))))

    def write_settings(self) -> None:
        settings = {"lap_test_scope": "targeted", "worker_commands": [], "slot_use": None, "lap_limit": LAP_LIMIT,
                    "apps": [{"name": "shop", "kind": "program", "way_in": "its command line", "build": "make",
                              "run": None, "test": "true", "test_target": "-k <name>", "test_full": None,
                              "hand_run": [], "acceptance": "specs/acceptance"}]}
        done = subprocess.run([str(LAUNCHER), str(SETTINGS_SCRIPT), "write"], input=json.dumps(settings),
                              capture_output=True, text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS,
                              env={**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home)},
                              cwd=self.repo)
        self.assertEqual(0, done.returncode, done.stderr)

    def script(self, script: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(LAUNCHER), str(script), *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS, cwd=self.repo,
                              env={**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
                                   "BEADS_ACTOR": HUMAN})

    def bd(self, *args: str) -> str:
        return fixture.run([self.fake_bd, *args], self.repo)

    def create(self, title: str, *flags: str) -> str:
        return json.loads(self.bd("create", "--title", title, *flags, "--json"))["id"]

    def hand_off(self, areas: dict[str, str]) -> None:
        done = self.script(HANDOFF, "take", self.epic, *(f"--area={task}={area}" for task, area in areas.items()))
        self.assertEqual(0, done.returncode, done.stderr)

    def shown(self, bead: str) -> dict:
        return json.loads(self.bd("show", bead, "--json"))[0]

    def metadata(self, bead: str) -> dict:
        return self.shown(bead).get("metadata") or {}

    def comments(self, bead: str) -> list[dict]:
        return json.loads(self.bd("comments", bead, "--json") or "[]") or []

    def next_printed(self) -> dict:
        done = self.script(SCHEDULER, "next", self.epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def stop(self) -> subprocess.CompletedProcess:
        return self.script(SCHEDULER, "stop", self.epic)

    def open_two_laps(self) -> list[str]:
        return [action["task"] for action in self.next_printed()["actions"]]


class StoppingTheHostTests(StopCase):
    def test_a_stop_ends_every_running_lap_interrupted_and_keeps_its_worktree_and_branch(self):
        running = self.open_two_laps()

        done = self.stop()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(sorted(running), sorted(json.loads(done.stdout)["interrupted"]))
        for task in running:
            shown = self.shown(task)
            self.assertEqual(("open", "", "interrupted"),
                             (shown["status"], shown.get("assignee") or "", shown["metadata"]["lap.stage"]))
            self.assertTrue((self.repo / ".worktrees" / f"lap-{task}").is_dir())
            self.assertIn(f"lap/{task}", fixture.run(["git", "branch", "--list"], self.repo))
            [comment] = [text for text in (str(c["text"]) for c in self.comments(task))
                         if text.startswith("Interrupted: ")]
            self.assertIn("stopped", comment)

    def test_a_stop_leaves_the_task_with_no_lap_unchanged(self):
        running = self.open_two_laps()
        [idle] = [task for task in self.tasks if task not in running]

        done = self.stop()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("lap.stage", self.metadata(idle))

    def test_a_stop_is_not_a_cutoff_and_counts_against_no_cap(self):
        [first, _] = self.open_two_laps()
        for _ in range(2):
            done = self.script(SCHEDULER, "report", self.epic, first, "cut off")
            self.assertEqual(0, done.returncode, done.stderr)
        before = self.metadata(first)

        done = self.stop()

        self.assertEqual(0, done.returncode, done.stderr)
        after = self.metadata(first)
        shown = self.shown(first)
        self.assertEqual("2", str(after["lap.cutoffs.build"]))
        self.assertEqual(before["lap.tries"], after["lap.tries"])
        self.assertNotIn("human", shown.get("labels") or [])
        self.assertNotIn("brake.laps", self.metadata(self.epic))
        self.assertEqual([], [text for text in (str(c["text"]) for c in self.comments(first))
                              if text.startswith("Parked: ")])

    def test_the_next_call_after_a_stop_gives_each_interrupted_task_a_new_lap_with_no_tries(self):
        running = self.open_two_laps()
        self.assertEqual(0, self.stop().returncode)

        actions = self.next_printed()["actions"]

        self.assertEqual(sorted(running), sorted(action["task"] for action in actions))
        self.assertEqual({2}, {action["lap"] for action in actions})
        for task in running:
            self.assertEqual(("build", "0"), (self.metadata(task)["lap.stage"], str(self.metadata(task)["lap.tries"])))

    def test_a_stop_sends_one_stopped_with_work_left_notification_that_links_to_the_epic(self):
        self.open_two_laps()

        done = self.stop()

        self.assertEqual(0, done.returncode, done.stderr)
        [message] = self.pushover.received
        self.assertEqual("Factory stopped: Take card payments", message["title"])
        for task in self.tasks:
            self.assertIn(task, message["message"])
        project = urllib.parse.quote(str(self.repo), safe="")
        self.assertEqual(f"{UI_URL}/bead/{urllib.parse.quote(self.epic, safe='')}?project={project}",
                         message["url"])
        self.assertEqual([f"factory-stopped:{self.epic}"],
                         list(json.loads(self.metadata(self.epic)["notification"])))
        self.assertIn("jidoka: Factory stopped: Take card payments.", done.stderr)

    def test_a_later_stop_with_the_same_open_tasks_sends_its_own_notification(self):
        self.open_two_laps()
        self.assertEqual(0, self.stop().returncode)
        self.next_printed()

        done = self.stop()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["Factory stopped: Take card payments"] * 2,
                         [message["title"] for message in self.pushover.received])

    def test_a_stop_with_every_task_closed_sends_no_notification(self):
        for task in self.tasks:
            self.bd("close", task)

        done = self.stop()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], json.loads(done.stdout)["interrupted"])
        self.assertEqual([], self.pushover.received)

    def test_a_stop_on_a_bead_that_is_not_a_handed_off_epic_is_refused_and_writes_nothing(self):
        done = self.script(SCHEDULER, "stop", self.tasks[0])

        self.assertEqual(1, done.returncode)
        self.assertEqual([], self.pushover.received)


if __name__ == "__main__":
    unittest.main()
