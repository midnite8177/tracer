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

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
HEARTBEAT = PLUGIN / "scripts" / "heartbeat.py"
STATUS = PLUGIN / "scripts" / "status.py"

RUN_TIMEOUT_SECONDS = 120
HUMAN = "Pat Human"
MINUTE = 60
MANAGER_SESSION = "session-of-the-manager"
OTHER_SESSION = "session-of-an-advisor"


class StatusCase(unittest.TestCase):
    """A temporary git repo with the fake bd's beads and a temporary jidoka home."""

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

    def script(self, script: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(LAUNCHER), str(script), *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS, cwd=self.repo,
                              env={**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
                                   "BEADS_ACTOR": HUMAN})

    def bd(self, *args: str) -> str:
        return fixture.run([self.fake_bd, *args], self.repo)

    def create(self, title: str, *flags: str) -> str:
        return json.loads(self.bd("create", "--title", title, *flags, "--json"))["id"]

    def new_epic(self, title: str, *labels: str) -> str:
        epic = self.create(title, "--type=epic")
        for label in labels:
            self.bd("label", "add", epic, label)
        return epic

    def new_task(self, epic: str, title: str, **metadata: str) -> str:
        task = self.create(title, "--type=task", "--parent", epic)
        self.set_metadata(task, **metadata)
        return task

    def set_metadata(self, bead: str, **metadata: str) -> None:
        flags = [flag for key, value in metadata.items() for flag in ("--set-metadata", f"{key.replace('_', '.')}={value}")]
        if flags:
            self.bd("update", bead, *flags)

    def beat_file(self, epic: str) -> Path:
        return self.home / "heartbeat" / f"{epic}.json"

    def write_beat(self, epic: str, seconds_ago: int, session: str) -> None:
        path = self.beat_file(epic)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"epic": epic, "time": int(time.time()) - seconds_ago, "session": session}),
                        encoding="utf-8")

    def status(self) -> str:
        done = self.script(STATUS)
        self.assertEqual(0, done.returncode, done.stderr)
        return done.stdout


class HeartbeatTests(StatusCase):
    def test_a_beat_renews_the_heartbeat_a_manager_claimed_for_an_epic_the_factory_runs(self):
        epic = self.new_epic("Take card payments", "factory")
        self.write_beat(epic, MINUTE, MANAGER_SESSION)
        before = int(time.time())

        done = self.script(HEARTBEAT, "beat", "--session", MANAGER_SESSION)

        self.assertEqual(0, done.returncode, done.stderr)
        beat = json.loads(self.beat_file(epic).read_text(encoding="utf-8"))
        self.assertEqual(epic, beat["epic"])
        self.assertEqual(MANAGER_SESSION, beat["session"])
        self.assertTrue(before <= beat["time"] <= int(time.time()), beat)

    def test_a_beat_renews_one_heartbeat_for_each_epic_the_session_claimed(self):
        first = self.new_epic("Take card payments", "factory")
        second = self.new_epic("Print receipts", "factory")
        self.write_beat(first, MINUTE, MANAGER_SESSION)
        self.write_beat(second, MINUTE, MANAGER_SESSION)
        before = int(time.time())

        self.script(HEARTBEAT, "beat", "--session", MANAGER_SESSION)

        for epic in (first, second):
            self.assertGreaterEqual(json.loads(self.beat_file(epic).read_text(encoding="utf-8"))["time"], before)

    def test_a_beat_renews_the_epics_of_its_own_session_and_leaves_the_epics_of_another(self):
        mine = self.new_epic("Take card payments", "factory")
        theirs = self.new_epic("Print receipts", "factory")
        self.write_beat(mine, MINUTE, MANAGER_SESSION)
        self.write_beat(theirs, MINUTE, OTHER_SESSION)
        before = int(time.time())

        self.script(HEARTBEAT, "beat", "--session", MANAGER_SESSION)

        self.assertGreaterEqual(json.loads(self.beat_file(mine).read_text(encoding="utf-8"))["time"], before)
        self.assertLess(json.loads(self.beat_file(theirs).read_text(encoding="utf-8"))["time"], before - 30)

    def test_a_beat_renews_no_heartbeat_that_records_no_session(self):
        epic = self.new_epic("Take card payments", "factory")
        path = self.beat_file(epic)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"epic": epic, "time": int(time.time()) - MINUTE}), encoding="utf-8")
        before = path.read_text(encoding="utf-8")

        self.script(HEARTBEAT, "beat", "--session", MANAGER_SESSION)

        self.assertEqual(before, path.read_text(encoding="utf-8"))

    def test_a_beat_writes_no_heartbeat_for_an_epic_no_manager_has_claimed(self):
        self.new_epic("Handed off a minute ago", "factory")

        done = self.script(HEARTBEAT, "beat", "--session", MANAGER_SESSION)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertFalse((self.home / "heartbeat").exists())

    def test_a_beat_writes_nothing_where_no_epic_runs(self):
        self.new_epic("Not handed off")
        self.new_epic("Parked", "factory", "human")
        gated = self.new_epic("At the gate", "factory", "human")
        self.set_metadata(gated, gate_state="waiting")

        done = self.script(HEARTBEAT, "beat", "--session", MANAGER_SESSION)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], list((self.home / "heartbeat").glob("*")) if (self.home / "heartbeat").exists() else [])

    def test_a_beat_run_outside_a_repo_exits_with_a_reason_and_writes_nothing(self):
        outside = self.root / "elsewhere"
        outside.mkdir()

        done = subprocess.run([str(LAUNCHER), str(HEARTBEAT), "beat", "--session", MANAGER_SESSION], capture_output=True, text=True,
                              encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS, cwd=outside,
                              env={**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home)})

        self.assertNotEqual(0, done.returncode)
        self.assertIn("not inside a git repo", done.stderr)
        self.assertFalse((self.home / "heartbeat").exists())


class StatusTests(StatusCase):
    def test_it_shows_each_task_of_a_running_epic_with_its_lap_stage_tries_and_time_against_its_clock(self):
        epic = self.new_epic("Take card payments", "factory")
        now = int(time.time())
        building = self.new_task(epic, "Read the card", lap_number="2", lap_stage="build", lap_tries="1",
                                 lap_started=str(now - 12 * MINUTE - 5))
        merging = self.new_task(epic, "Print the slip", lap_number="1", lap_stage="merge", lap_tries="0",
                                lap_mergetries="1", lap_started=str(now - 31 * MINUTE))
        self.write_beat(epic, 40, MANAGER_SESSION)

        output = self.status()

        rows = output.splitlines()
        build_row = next(line for line in rows if building in line)
        merge_row = next(line for line in rows if merging in line)
        self.assertEqual(["2", "build", "1/3"], build_row.split()[1:4])
        self.assertIn("12m of 60m (47m left)", build_row)
        self.assertIn("Read the card", build_row)
        self.assertEqual(["1", "merge", "1/2"], merge_row.split()[1:4])
        self.assertIn("31m of 30m (over)", merge_row)

    def test_it_shows_the_age_of_the_epics_heartbeat(self):
        epic = self.new_epic("Take card payments", "factory")
        self.new_task(epic, "Read the card")
        self.write_beat(epic, 5 * MINUTE + 10, MANAGER_SESSION)

        output = self.status()

        self.assertIn("running", output)
        self.assertIn("heartbeat 5m ago", output)

    def test_it_says_when_the_epic_has_no_heartbeat(self):
        epic = self.new_epic("Take card payments", "factory")
        self.new_task(epic, "Read the card")

        output = self.status()

        self.assertIn("no heartbeat", output)

    def test_it_shows_parked_blocked_waiting_and_merged_tasks_without_a_clock(self):
        epic = self.new_epic("Take card payments", "factory")
        parked = self.new_task(epic, "Round to five cents", lap_number="1", lap_stage="parked", lap_tries="2")
        blocked = self.new_task(epic, "Sign the slip", lap_number="3", lap_stage="blocked", lap_tries="0")
        waiting = self.new_task(epic, "Refund a card")
        merged = self.new_task(epic, "Open the till", lap_number="1", lap_stage="build", lap_tries="0")
        self.bd("close", merged)

        rows = {task: next(line for line in self.status().splitlines() if task in line)
                for task in (parked, blocked, waiting, merged)}

        self.assertEqual(["1", "parked", "2/3"], rows[parked].split()[1:4])
        self.assertEqual(["3", "blocked", "0/3"], rows[blocked].split()[1:4])
        self.assertIn("no lap yet", rows[waiting])
        self.assertIn("merged", rows[merged])
        self.assertNotIn(" of ", rows[parked] + rows[blocked] + rows[waiting] + rows[merged])

    def test_it_shows_no_clock_for_a_lap_a_stop_interrupted_though_it_keeps_its_start(self):
        epic = self.new_epic("Take card payments", "factory")
        interrupted = self.new_task(epic, "Read the card", lap_number="2", lap_stage="interrupted", lap_tries="1",
                                    lap_started=str(int(time.time()) - 12 * MINUTE))

        row = next(line for line in self.status().splitlines() if interrupted in line)

        self.assertEqual(["2", "interrupted", "1/3"], row.split()[1:4])
        self.assertNotIn(" of ", row)

    def test_it_names_an_epic_that_waits_on_the_human(self):
        parked = self.new_epic("Parked epic", "factory", "human")
        gated = self.new_epic("Gated epic", "factory", "human")
        self.set_metadata(gated, gate_state="waiting")

        output = self.status()

        self.assertIn(f"{parked}  Parked epic [parked]", output)
        self.assertIn(f"{gated}  Gated epic [at the acceptance gate]", output)

    def test_it_says_so_when_the_factory_holds_no_epic(self):
        self.new_epic("Not handed off")

        output = self.status()

        self.assertIn("no epic is in the factory", output)

    def test_it_runs_from_a_second_terminal_with_no_host_and_changes_no_bead(self):
        epic = self.new_epic("Take card payments", "factory")
        task = self.new_task(epic, "Read the card", lap_number="1", lap_stage="build", lap_tries="0",
                             lap_started=str(int(time.time())))
        before = self.bd("show", task, "--json")

        self.status()

        self.assertEqual(before, self.bd("show", task, "--json"))


if __name__ == "__main__":
    unittest.main()
