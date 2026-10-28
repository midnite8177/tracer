import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_scheduler  # noqa: E402

LAP_LISTS = test_scheduler.PLUGIN / "scripts" / "lap_lists.py"
APP = {"name": "shop", "kind": "program", "way_in": None, "build": "make", "run": None,
       "test": "make test", "test_target": "T=<name>", "test_full": None, "hand_run": [], "acceptance": None}
DOCS_APP = {**APP, "name": "docs", "build": None, "test": None, "test_target": None}
MERGE_GRANT = [
    {"command": "git rebase {branch}", "then": "nothing"},
    {"command": "git rebase --abort", "then": "nothing"},
    {"command": "git -c core.editor=true rebase --continue", "then": "nothing"},
    {"command": "git add", "then": "paths"},
    {"command": "git status", "then": "words", "refusing": ["--output"]},
    {"command": "git diff", "then": "words", "refusing": ["--output"]},
    {"command": "git log", "then": "words", "refusing": ["--output"]},
]


class LapListsTests(test_scheduler.SchedulerCase):
    def lap_list(self, kind: str, cwd: Path, home: Path) -> subprocess.CompletedProcess:
        return subprocess.run([str(test_scheduler.LAUNCHER), str(LAP_LISTS), kind], capture_output=True, text=True,
                              encoding="utf-8", timeout=test_scheduler.RUN_TIMEOUT_SECONDS,
                              env=self.caller_env(home), cwd=cwd)

    def printed(self, kind: str, cwd: Path) -> list:
        done = self.lap_list(kind, cwd, self.home)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def add_built_in(self, *commands: str) -> None:
        path = self.home / "built_in_commands.json"
        path.write_text(json.dumps(list(commands)), encoding="utf-8")
        self.addCleanup(path.unlink)

    def test_a_lap_worker_may_run_each_apps_test_command_the_worker_commands_the_built_in_additions_and_the_epics_commands_in_that_order(
            self):
        lap = self.open_one_lap()
        self.write_settings({"worker_commands": ["make build"], "apps": [APP, DOCS_APP]})
        self.add_built_in("make fmt")
        self.rules_set(lap.epic, 'extra_commands=["make lint"]')

        printed = self.printed("lap", lap.worktree)

        self.assertEqual(["make test", "make build", "make fmt", "make lint"], printed)

    def test_a_merge_worker_is_also_granted_the_rebase_the_epic_branch_needs(self):
        self.write_settings({"worker_commands": [], "apps": [APP]})
        lap = self.open_one_lap()
        fixture.run([self.bd, "update", lap.task, "--set-metadata", "lap.stage=merge"], self.repo)

        printed = self.printed("lap", lap.worktree)

        grant = [{**entry, "command": entry["command"].format(branch=lap.epic_branch)} for entry in MERGE_GRANT]
        self.assertEqual(["make test", *grant], printed)

    def test_a_lap_at_the_merge_whose_worktree_is_in_the_middle_of_a_rebase_still_gets_the_merge_worker_s_commands(
            self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "the lap's card\n")
        self.commit_on_epic_branch(lap.epic_branch, "card.txt", "another lap's card\n")
        self.build_done(lap.epic, lap.task)
        subprocess.run(["git", "rebase", lap.epic_branch], cwd=lap.worktree, capture_output=True, text=True)

        mid_rebase = self.printed("lap", lap.worktree)

        self.assertIn({"command": "git rebase --abort", "then": "nothing"}, mid_rebase)
        self.assertIn({"command": f"git rebase {lap.epic_branch}", "then": "nothing"}, mid_rebase)

    def test_a_lap_list_without_repo_settings_keeps_the_epics_commands(self):
        lap = self.open_one_lap()
        self.rules_set(lap.epic, 'extra_commands=["make lint"]')
        bare = self.new_home("home-without-settings")

        done = self.lap_list("lap", lap.worktree, bare)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["make lint"], json.loads(done.stdout))

    def test_a_check_worker_may_run_each_apps_build_run_and_way_in_and_the_worker_commands(self):
        self.write_settings({"worker_commands": ["make build"], "apps": [
            {**APP, "run": "make run && make seed", "way_in": "curl localhost:8080"}, DOCS_APP]})

        printed = self.printed("check", self.repo)

        self.assertEqual(["make", "make run && make seed", "curl localhost:8080", "make build"], printed)

    def test_a_check_workers_values_are_printed_whole_for_the_lap_mod_to_split(self):
        self.write_settings({"worker_commands": ["echo $(date)"], "apps": [
            {**APP, "build": 'make "my target"', "run": "make run > out.txt", "way_in": "echo `date`"}]})

        printed = self.printed("check", self.repo)

        self.assertEqual(['make "my target"', "make run > out.txt", "echo `date`", "echo $(date)"], printed)

    def test_a_folder_that_is_no_lap_worktree_gets_no_lap_list(self):
        done = self.lap_list("lap", self.repo, self.home)

        self.assertEqual(1, done.returncode)
        self.assertIn("is not a lap worktree", done.stderr)
        self.assertEqual("", done.stdout)

    def test_a_call_with_no_worker_kind_is_a_usage_error(self):
        done = subprocess.run([str(test_scheduler.LAUNCHER), str(LAP_LISTS)], capture_output=True, text=True,
                              encoding="utf-8", timeout=test_scheduler.RUN_TIMEOUT_SECONDS,
                              env=self.caller_env(self.home), cwd=self.repo)

        self.assertEqual(2, done.returncode)


if __name__ == "__main__":
    unittest.main()
