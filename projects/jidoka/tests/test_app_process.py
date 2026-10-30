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
APP_PROCESS = PLUGIN / "scripts" / "app_process.py"

RUN_TIMEOUT_SECONDS = 60
GONE_WAIT_SECONDS = 10.0
GONE_POLL_SECONDS = 0.05

TWO_PROCESSES = "\n".join([
    "import os, subprocess, sys",
    f"child = subprocess.Popen([sys.executable, '-c', {fixture.SLEEP_FOR_AN_HOUR!r}])",
    "with open(os.environ['PIDS'], 'a') as pids:",
    "    pids.write(f'{os.getpid()}\\n{child.pid}\\n')",
    "child.wait()",
    ""])
RECORDS_ITS_FOLDER_AND_PORT = "\n".join([
    "import os, time",
    "with open(os.environ['PIDS'], 'w') as seen:",
    "    seen.write(os.getcwd() + '\\n' + os.environ['PORT'] + '\\n')",
    "time.sleep(3600)",
    ""])
PRINTS_AND_WAITS = "import time\nprint('listening', flush=True)\ntime.sleep(3600)\n"
EXITS_AT_ONCE = "pass\n"
SLOT_USE = "PORT 5100 plus the slot"

is_running = fixture.process_is_running


class AppProcessTests(unittest.TestCase):
    """A temporary git repo with repo settings in a temporary jidoka home, and a script run as a process in it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self.root = root
        self.repo = root / "shop"
        fixture.init_repo(self.repo)
        (self.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Start")
        self.home = root / "jidoka-home"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        self.pids = root / "pids"
        self.write_settings([{"name": "shop", "run": self.app_command(TWO_PROCESSES)}])
        self.addCleanup(self.kill_what_is_left)

    slot_use = SLOT_USE

    def app_command(self, source: str) -> str:
        program = self.root / f"app-{len(list(self.root.glob('app-*.py')))}.py"
        program.write_text(source, encoding="utf-8")
        return f'"{sys.executable}" "{program}"'

    def write_settings(self, apps: list[dict]) -> None:
        full = [{"kind": "program", "way_in": "curl localhost", "build": "make", "test": "true",
                 "test_target": "-k <name>", "test_full": None, "hand_run": [], "acceptance": None, **app}
                for app in apps]
        settings = {"lap_test_scope": "targeted", "worker_commands": [], "slot_use": self.slot_use, "lap_limit": 1,
                    "apps": full}
        fixture.write_repo_settings(self.repo, self.home, settings)

    def env(self) -> dict[str, str]:
        return {**os.environ, "JIDOKA_HOME": str(self.home), "PIDS": str(self.pids)}

    def app_process(self, *args: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(APP_PROCESS), *args], None, self.env(), self.repo,
                                    RUN_TIMEOUT_SECONDS)

    def app_pids(self) -> list[int]:
        """The pids the app has written so far, waiting for the app to write both. The file exists, empty, from the
        moment the app opens it, before it writes."""
        deadline = time.monotonic() + GONE_WAIT_SECONDS
        while time.monotonic() < deadline:
            written = self.pids.read_text(encoding="utf-8").split() if self.pids.is_file() else []
            if written and len(written) % 2 == 0:
                return [int(pid) for pid in written]
            time.sleep(GONE_POLL_SECONDS)
        self.fail("the app wrote no pids")

    def wait_until_gone(self, pids: list[int]) -> list[int]:
        """The pids still running after the wait."""
        deadline = time.monotonic() + GONE_WAIT_SECONDS
        running = [pid for pid in pids if is_running(pid)]
        while running and time.monotonic() < deadline:
            time.sleep(GONE_POLL_SECONDS)
            running = [pid for pid in pids if is_running(pid)]
        return running

    def kill_what_is_left(self) -> None:
        if not self.pids.is_file():
            return
        for pid in self.pids.read_text(encoding="utf-8").split():
            fixture.end_process(int(pid))

    def test_an_app_started_runs_until_it_is_stopped_and_then_no_process_of_it_is_left(self):
        started = self.app_process("start", "shop")
        self.assertEqual(0, started.returncode, started.stderr)
        pids = self.app_pids()
        self.assertEqual(2, len(pids))
        self.assertTrue(all(is_running(pid) for pid in pids))

        stopped = self.app_process("stop", "shop")

        self.assertEqual(0, stopped.returncode, stopped.stderr)
        self.assertEqual([], self.wait_until_gone(pids))

    def test_starting_an_app_that_a_check_left_running_stops_that_one_first(self):
        self.assertEqual(0, self.app_process("start", "shop").returncode)
        first = self.app_pids()
        self.pids.unlink()

        self.assertEqual(0, self.app_process("start", "shop").returncode)
        second = self.app_pids()

        self.assertEqual([], self.wait_until_gone(first))
        self.assertTrue(all(is_running(pid) for pid in second))
        self.assertEqual(0, self.app_process("stop", "shop").returncode)

    def test_the_app_runs_in_the_folder_the_script_ran_in_with_the_variables_it_was_given(self):
        self.write_settings([{"name": "shop", "run": self.app_command(RECORDS_ITS_FOLDER_AND_PORT)}])

        self.assertEqual(0, self.app_process("start", "shop", "--env", "PORT=5103").returncode)
        deadline = time.monotonic() + GONE_WAIT_SECONDS
        while time.monotonic() < deadline and (not self.pids.is_file()
                                               or len(self.pids.read_text(encoding="utf-8").split()) < 2):
            time.sleep(GONE_POLL_SECONDS)
        cwd, port = self.pids.read_text(encoding="utf-8").split()
        self.assertEqual(0, self.app_process("stop", "shop").returncode)

        self.assertEqual(str(self.repo), cwd)
        self.assertEqual("5103", port)
        self.pids.unlink()

    def test_the_app_s_output_goes_to_a_log_in_the_scratch_folder(self):
        self.write_settings([{"name": "shop", "run": self.app_command(PRINTS_AND_WAITS)}])

        self.assertEqual(0, self.app_process("start", "shop").returncode)
        log = self.repo / ".scratch" / "apps" / "shop.log"
        deadline = time.monotonic() + GONE_WAIT_SECONDS
        while time.monotonic() < deadline and "listening" not in log.read_text(encoding="utf-8"):
            time.sleep(GONE_POLL_SECONDS)
        self.assertEqual(0, self.app_process("stop", "shop").returncode)

        self.assertEqual("listening\n", log.read_text(encoding="utf-8"))

    def test_stopping_an_app_that_was_never_started_succeeds_and_says_so(self):
        stopped = self.app_process("stop", "shop")

        self.assertEqual(0, stopped.returncode, stopped.stderr)
        self.assertIn("not running", stopped.stdout)

    def test_stopping_an_app_that_already_ended_succeeds(self):
        self.write_settings([{"name": "shop", "run": self.app_command(EXITS_AT_ONCE)}])
        self.assertEqual(0, self.app_process("start", "shop").returncode)
        time.sleep(0.5)

        stopped = self.app_process("stop", "shop")

        self.assertEqual(0, stopped.returncode, stopped.stderr)
        self.assertEqual([], self.records())

    def test_an_app_the_settings_do_not_name_is_refused_and_nothing_starts(self):
        started = self.app_process("start", "bakery")

        self.assertEqual(1, started.returncode)
        self.assertIn("bakery", started.stderr)
        self.assertFalse(self.pids.exists())

    def test_an_app_with_no_run_command_is_refused(self):
        self.write_settings([{"name": "shop", "run": None}])

        started = self.app_process("start", "shop")

        self.assertEqual(1, started.returncode)
        self.assertIn("no run command", started.stderr)

    def test_a_variable_given_without_a_name_and_a_value_is_refused(self):
        started = self.app_process("start", "shop", "--env", "PORT")

        self.assertEqual(2, started.returncode)
        self.assertFalse(self.pids.exists())

    def records(self) -> list[Path]:
        """The records of started apps, which live under the jidoka home."""
        return sorted(self.home.glob("apps/*/shop.json"))

    def sleeper(self) -> subprocess.Popen:
        """A process of its own group that this test, not the script, started."""
        process = subprocess.Popen([sys.executable, "-c", fixture.SLEEP_FOR_AN_HOUR], start_new_session=True)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process

    def test_the_record_of_a_started_app_is_under_the_jidoka_home_and_not_in_the_worktree(self):
        self.assertEqual(0, self.app_process("start", "shop").returncode)

        self.assertEqual(1, len(self.records()))
        self.assertFalse((self.repo / ".scratch" / "apps" / "shop.json").exists())
        self.assertEqual(0, self.app_process("stop", "shop").returncode)

    def test_a_record_a_worker_writes_in_the_worktree_stops_nothing(self):
        bystander = self.sleeper()
        planted = self.repo / ".scratch" / "apps"
        planted.mkdir(parents=True)
        (planted / "shop.json").write_text(json.dumps({"app": "shop", "group": bystander.pid}), encoding="utf-8")

        stopped = self.app_process("stop", "shop")

        self.assertEqual(0, stopped.returncode, stopped.stderr)
        self.assertIn("not running", stopped.stdout)
        self.assertTrue(is_running(bystander.pid))

    def test_a_record_whose_leader_began_at_another_time_is_dropped_without_a_signal(self):
        self.assertEqual(0, self.app_process("start", "shop").returncode)
        pids = self.app_pids()
        [record] = self.records()
        shown = json.loads(record.read_text(encoding="utf-8"))
        record.write_text(json.dumps({**shown, "started": "Thu Jan  1 00:00:00 1970"}), encoding="utf-8")

        stopped = self.app_process("stop", "shop")

        self.assertEqual(0, stopped.returncode, stopped.stderr)
        self.assertTrue(all(is_running(pid) for pid in pids))
        self.assertEqual([], self.records())

    def test_a_flag_that_names_another_jidoka_home_is_refused(self):
        started = self.app_process("start", "shop", "--jidoka-home", str(self.repo))

        self.assertEqual(2, started.returncode)
        self.assertFalse(self.pids.exists())

    def test_a_variable_the_slot_use_does_not_name_is_refused_and_nothing_starts(self):
        started = self.app_process("start", "shop", "--env", "TOKEN=1")

        self.assertEqual(1, started.returncode)
        self.assertIn("TOKEN", started.stderr)
        self.assertFalse(self.pids.exists())

    def test_a_variable_that_changes_how_a_program_loads_is_refused_even_when_the_slot_use_names_it(self):
        self.slot_use = "PORT, PATH and LD_PRELOAD from the slot"
        self.write_settings([{"name": "shop", "run": self.app_command(TWO_PROCESSES)}])

        for name in ("PATH", "LD_PRELOAD"):
            started = self.app_process("start", "shop", "--env", f"{name}=/tmp/x")
            self.assertEqual(1, started.returncode, name)
            self.assertFalse(self.pids.exists(), name)

    def test_an_app_name_that_climbs_out_of_the_records_folder_is_refused(self):
        stopped = self.app_process("stop", "../shop")

        self.assertEqual(2, stopped.returncode)


if __name__ == "__main__":
    unittest.main()
