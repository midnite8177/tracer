import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_review  # noqa: E402
import test_scheduler  # noqa: E402
import test_validation  # noqa: E402

LAP_LISTS = test_scheduler.PLUGIN / "scripts" / "lap_lists.py"
APP = {"name": "shop", "kind": "program", "way_in": None, "build": "make", "run": None,
       "test": "make test", "test_target": "T=<name>", "test_full": None, "hand_run": [], "acceptance": None}
DOCS_APP = {**APP, "name": "docs", "build": None, "test": None, "test_target": None}
SETTINGS = {"lap_test_scope": "targeted", "worker_commands": ["make build"], "slot_use": None,
            "lap_limit": test_scheduler.LAP_LIMIT, "apps": [APP]}
MERGE_GRANT = [
    {"command": "git rebase {branch}", "then": "nothing"},
    {"command": "git rebase --abort", "then": "nothing"},
    {"command": "git -c core.editor=true rebase --continue", "then": "nothing"},
    {"command": "git add", "then": "paths"},
    {"command": "git status", "then": "words", "refusing": ["--output"]},
    {"command": "git diff", "then": "words", "refusing": ["--output"]},
    {"command": "git log", "then": "words", "refusing": ["--output"]},
]
MERGE_MAIN_GRANT = [
    {"command": "git merge main", "then": "nothing"},
    {"command": "git merge --abort", "then": "nothing"},
    {"command": "git -c core.editor=true merge --continue", "then": "nothing"},
    {"command": "git add", "then": "paths"},
    {"command": "git status", "then": "words", "refusing": ["--output"]},
    {"command": "git diff", "then": "words", "refusing": ["--output"]},
    {"command": "git log", "then": "words", "refusing": ["--output"]},
]


def lap_lists(kind: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return fixture.run_launcher(test_scheduler.LAUNCHER, [str(LAP_LISTS), kind], None, env, cwd,
                                test_scheduler.RUN_TIMEOUT_SECONDS)


def with_bd_refusing(bead: str, env: dict[str, str], folder: Path, fake_bd: str) -> dict[str, str]:
    folder.mkdir()
    fixture.write_executable(folder / "bd", f"""#!/bin/sh
for arg in "$@"; do
  if [ "$arg" = "{bead}" ]; then
    echo "Error fetching {bead}: database is locked" >&2
    exit 1
  fi
done
exec "{fake_bd}" "$@"
""")
    return {**env, "PATH": f"{folder}{os.pathsep}{env['PATH']}"}


def write_settings_in(home: Path, settings: dict, repo: Path) -> Path:
    fixture.write_repo_settings(repo, home, settings)
    [written] = (home / "repos").glob("*.json")
    return written


class LapListsTests(test_scheduler.SchedulerCase):
    def setUp(self):
        self.write_settings({})

    def lap_list(self, kind: str, cwd: Path, home: Path) -> subprocess.CompletedProcess:
        return lap_lists(kind, cwd, self.caller_env(home))

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

    def test_a_check_list_without_repo_settings_is_refused_with_a_pointer_to_onboarding(self):
        bare = self.new_home("home-without-settings-for-a-check")

        done = self.lap_list("check", self.repo, bare)

        self.assertEqual(1, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn("no settings for ", done.stderr)
        self.assertIn(". Run /jidoka:onboard to record them", done.stderr)

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

    def test_a_lap_worker_whose_epic_bd_refuses_still_gets_the_repo_settings_commands_and_the_built_in_list(self):
        lap = self.open_one_lap()
        self.write_settings({"worker_commands": ["make build"], "apps": [APP]})
        self.add_built_in("make fmt")
        self.rules_set(lap.epic, 'extra_commands=["make lint"]')
        env = with_bd_refusing(lap.epic, self.caller_env(self.home), self.root / "bd-refusing-the-epic", self.bd)

        done = lap_lists("lap", lap.worktree, env)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["make test", "make build", "make fmt"], json.loads(done.stdout))
        self.assertIn("the epic's commands", done.stderr)
        self.assertIn(f"Error fetching {lap.epic}", done.stderr)

    def test_a_folder_that_names_no_epic_gets_the_repo_settings_commands_and_the_built_in_list(self):
        self.write_settings({"worker_commands": ["make build"], "apps": [APP]})
        self.add_built_in("make fmt")

        done = self.lap_list("lap", self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["make test", "make build", "make fmt"], json.loads(done.stdout))
        self.assertIn("the epic's commands", done.stderr)
        self.assertIn("is not a lap worktree", done.stderr)

    def test_repo_settings_that_do_not_read_drop_only_the_apps_and_worker_commands(self):
        lap = self.open_one_lap()
        self.rules_set(lap.epic, 'extra_commands=["make lint"]')
        home = self.new_home("home-with-broken-settings")
        (home / "built_in_commands.json").write_text(json.dumps(["make fmt"]), encoding="utf-8")
        write_settings_in(home, SETTINGS, self.repo).write_text("{", encoding="utf-8")

        done = self.lap_list("lap", lap.worktree, home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["make fmt", "make lint"], json.loads(done.stdout))
        self.assertIn("the repo settings' commands", done.stderr)

    def test_a_built_in_list_that_does_not_read_drops_only_itself(self):
        lap = self.open_one_lap()
        self.write_settings({"worker_commands": ["make build"], "apps": [APP]})
        self.rules_set(lap.epic, 'extra_commands=["make lint"]')
        built_in = self.home / "built_in_commands.json"
        built_in.write_text("[", encoding="utf-8")
        self.addCleanup(built_in.unlink)

        done = self.lap_list("lap", lap.worktree, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["make test", "make build", "make lint"], json.loads(done.stdout))
        self.assertIn("the built-in list", done.stderr)

    def test_a_call_with_no_worker_kind_is_a_usage_error(self):
        done = fixture.run_launcher(test_scheduler.LAUNCHER, [str(LAP_LISTS)], None, self.caller_env(self.home),
                                    self.repo, test_scheduler.RUN_TIMEOUT_SECONDS)

        self.assertEqual(2, done.returncode)


class PassWorktreeListsTests(test_review.ReviewCase):
    """The lap lists in the worktree of a pass's fix worker, read with a jidoka home of their own, so the scheduler
    runs the pass on the repo settings it was set up with."""

    def fix_worktree(self) -> tuple[str, Path]:
        epic, printed = self.finish_epic_at_the_review()
        moved = self.reviewed(printed, {"comments": [test_review.finding("Echo", "small", "high")]})
        return epic, Path(self.fix_action_of(moved)["worktree"])

    def home_with_settings(self) -> Path:
        home = self.new_home(f"home-{self.id().rpartition('.')[2]}")
        write_settings_in(home, SETTINGS, self.repo)
        (home / "built_in_commands.json").write_text(json.dumps(["make fmt"]), encoding="utf-8")
        return home

    def test_a_fix_worker_in_a_pass_worktree_may_run_each_apps_test_command_the_worker_commands_the_built_in_additions_and_the_epics_commands(
            self):
        epic, worktree = self.fix_worktree()
        self.rules_set(epic, 'extra_commands=["make lint"]')

        done = lap_lists("lap", worktree, self.caller_env(self.home_with_settings()))

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["make test", "make build", "make fmt", "make lint"], json.loads(done.stdout))
        self.assertEqual("", done.stderr)

    def test_a_pass_worktree_whose_epic_bd_refuses_still_gets_the_repo_settings_commands_and_the_built_in_list(self):
        epic, worktree = self.fix_worktree()
        self.rules_set(epic, 'extra_commands=["make lint"]')
        env = with_bd_refusing(epic, self.caller_env(self.home_with_settings()), self.root / "bd-refusing-the-epic",
                               self.bd)

        done = lap_lists("lap", worktree, env)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["make test", "make build", "make fmt"], json.loads(done.stdout))
        self.assertIn("the epic's commands", done.stderr)
        self.assertIn(f"Error fetching {epic}", done.stderr)


class ValidationWorktreeListsTests(test_validation.ValidationCase):
    """The lap lists in the validation worktree, where a merge worker merges main into the epic branch."""

    def test_a_merge_worker_in_the_validation_worktree_may_merge_main_and_nothing_more(self):
        epic, _, printed = self.conflicting_epic()
        [action] = [each for each in printed["actions"] if each["action"] == "merge"]

        done = lap_lists("lap", Path(action["worktree"]), self.caller_env(self.home))

        self.assertEqual(0, done.returncode, done.stderr)
        listed = json.loads(done.stdout)
        self.assertEqual(MERGE_MAIN_GRANT, listed[-len(MERGE_MAIN_GRANT):])
        self.assertEqual(1 + len(MERGE_MAIN_GRANT), len(listed))
        self.assertEqual("", done.stderr)

    def test_a_validation_worktree_of_an_epic_that_owes_no_merge_worker_gets_no_merge_grant(self):
        epic, task, _ = self.finish_epic_but_for_the_last_report()
        self.build_done(epic, task)
        leftover = self.repo / ".worktrees" / f"validation-{epic}"
        fixture.run(["git", "worktree", "add", "--detach", str(leftover), "main"], self.repo)
        self.addCleanup(fixture.run, ["git", "worktree", "remove", "--force", str(leftover)], self.repo)

        done = lap_lists("lap", leftover, self.caller_env(self.home))

        self.assertEqual(0, done.returncode, done.stderr)
        listed = json.loads(done.stdout)
        self.assertEqual(1, len(listed))
        self.assertNotIn(MERGE_MAIN_GRANT[0], listed)


if __name__ == "__main__":
    unittest.main()
