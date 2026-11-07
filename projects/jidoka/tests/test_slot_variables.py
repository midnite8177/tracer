import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
SLOT_VARIABLES = PLUGIN / "scripts" / "slot_variables.py"
APP_PROCESS = PLUGIN / "scripts" / "app_process.py"

RUN_TIMEOUT_SECONDS = 60
SLOT_USE = "CDP_GLOBAL_PORT and port 15280 plus the slot, never PATH, ld_preload, DYLD_X or PYTHONPATH"
NAMES = ["AND", "CDP_GLOBAL_PORT", "NEVER", "OR", "PLUS", "PORT", "SLOT", "THE"]
LEFT_OUT = ["PATH", "LD_PRELOAD", "DYLD_X", "PYTHONPATH"]
NOT_IN_SLOT_USE = ["TOKEN", "port"]


class SlotVariablesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.repo = self.root / "shop"
        fixture.init_repo(self.repo)
        (self.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Start")
        self.home = self.root / "jidoka-home"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")

    def write_settings(self, slot_use: str | None) -> None:
        app = self.root / "app.py"
        app.write_text(fixture.SLEEP_FOR_AN_HOUR, encoding="utf-8")
        settings = {"lap_test_scope": "targeted", "worker_commands": [], "slot_use": slot_use, "lap_limit": 1,
                    "apps": [{"name": "shop", "kind": "program", "way_in": None, "build": "make",
                              "run": f'"{sys.executable}" "{app}"', "test": "true", "test_target": "-k <name>",
                              "test_full": None, "hand_run": [], "acceptance": None}]}
        fixture.write_repo_settings(self.repo, self.home, settings)

    def run_script(self, script: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        env = {**os.environ, "JIDOKA_HOME": str(self.home)}
        return fixture.run_launcher(LAUNCHER, [str(script), *args], None, env, cwd, RUN_TIMEOUT_SECONDS)

    def slot_variables(self) -> subprocess.CompletedProcess:
        return self.run_script(SLOT_VARIABLES, [], self.repo)

    def start_with(self, name: str) -> subprocess.CompletedProcess:
        return self.run_script(APP_PROCESS, ["start", "shop", "--env", f"{name}=1"], self.repo)

    def test_it_prints_each_word_of_the_slot_use_in_capitals_less_the_names_that_change_how_a_program_loads(self):
        self.write_settings(SLOT_USE)

        done = self.slot_variables()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(NAMES, json.loads(done.stdout))

    def test_a_repo_with_no_slot_use_prints_an_empty_list(self):
        self.write_settings(None)

        done = self.slot_variables()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], json.loads(done.stdout))

    def test_a_worktree_of_the_repo_prints_the_names_of_the_main_checkouts_settings(self):
        self.write_settings(SLOT_USE)
        worktree = self.root / "lap"
        fixture.run(["git", "worktree", "add", "-q", "-b", "lap", str(worktree)], self.repo)

        done = self.run_script(SLOT_VARIABLES, [], worktree)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(NAMES, json.loads(done.stdout))

    def test_a_flag_names_the_jidoka_home_it_reads(self):
        self.write_settings(SLOT_USE)
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "python").write_text(sys.executable + "\n", encoding="utf-8")
        env = {**os.environ, "JIDOKA_HOME": str(elsewhere)}

        done = fixture.run_launcher(LAUNCHER, [str(SLOT_VARIABLES), "--jidoka-home", str(self.home)], None, env,
                                    self.repo, RUN_TIMEOUT_SECONDS)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(NAMES, json.loads(done.stdout))

    def test_a_repo_with_no_settings_prints_nothing_and_exits_one_with_the_reason(self):
        done = self.slot_variables()

        self.assertEqual(1, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn("slot_variables: no settings for", done.stderr)

    def test_a_folder_outside_a_git_repo_prints_nothing_and_exits_one_with_the_reason(self):
        outside = self.root / "outside"
        outside.mkdir()

        done = self.run_script(SLOT_VARIABLES, [], outside)

        self.assertEqual(1, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn("is not inside a git repo", done.stderr)

    def test_a_name_it_prints_is_one_the_app_process_script_takes_and_one_it_leaves_out_is_one_that_script_refuses(self):
        self.write_settings(SLOT_USE)
        self.addCleanup(self.run_script, APP_PROCESS, ["stop", "shop"], self.repo)
        printed = json.loads(self.slot_variables().stdout)
        self.assertEqual(NAMES, printed)

        for name in printed:
            started = self.start_with(name)
            self.assertEqual(0, started.returncode, f"{name}: {started.stderr}")
        for name in [*LEFT_OUT, *NOT_IN_SLOT_USE]:
            self.assertNotIn(name, printed)
            refused = self.start_with(name)
            self.assertEqual(1, refused.returncode, f"{name}: {refused.stdout}")
            self.assertIn(f"--env {name} is not a variable", refused.stderr)


if __name__ == "__main__":
    unittest.main()
