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
SCHEDULER = PLUGIN / "scripts" / "scheduler.py"
HANDOFF = PLUGIN / "scripts" / "handoff.py"
SETTINGS_SCRIPT = PLUGIN / "scripts" / "repo_settings.py"

RUN_TIMEOUT_SECONDS = 120
JEFF = "Jeff Scheduler"
LAP_LIMIT = 2


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


class SchedulerCase(unittest.TestCase):
    """The shop repo, onboarded with a lap limit of two, and the helpers of the scheduler tests."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.repo = cls.root / "shop"
        fixture.init_repo(cls.repo)
        git(cls.repo, "config", "user.name", JEFF)
        (cls.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(cls.repo, "Start")
        git(cls.repo, "branch", "-M", "main")
        cls.bd = fixture.real_tool("bd")
        fixture.add_stealth_beads(cls.repo)
        cls.count = 0
        cls.home = cls.root / "jidoka-home"
        cls.home.mkdir()
        (cls.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        settings = {"lap_test_scope": "targeted", "worker_commands": [], "slot_use": None, "lap_limit": LAP_LIMIT,
                    "apps": [{"name": "shop", "kind": "program", "way_in": "its command line", "build": "make",
                              "run": None, "test": "make test", "test_target": "-k <name>", "test_full": None,
                              "hand_run": []}]}
        done = subprocess.run([str(LAUNCHER), str(SETTINGS_SCRIPT), "write"], input=json.dumps(settings),
                              capture_output=True, text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS,
                              env={**os.environ, "JIDOKA_HOME": str(cls.home)}, cwd=cls.repo)
        if done.returncode != 0:
            raise fixture.FixtureError(f"repo_settings.py write failed: {done.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def create(self, title: str, *flags: str) -> str:
        return json.loads(fixture.run([self.bd, "create", "--title", title, *flags, "--json"], self.repo))["id"]

    def new_epic(self) -> str:
        type(self).count += 1
        return self.create(f"Take card payments {self.count}", "--type=epic")

    def new_task_under(self, epic: str, *flags: str) -> str:
        type(self).count += 1
        return self.create(f"Read the card {self.count}", "--type=task", "--parent", epic, *flags)

    def new_home(self, name: str) -> Path:
        """A jidoka home that knows the Python and holds no repo settings."""
        home = self.root / name
        home.mkdir()
        (home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        return home

    def caller_env(self, home: Path) -> dict[str, str]:
        return {**os.environ, "JIDOKA_HOME": str(home), "BEADS_ACTOR": "claude", "BD_DISABLE_EVENT_FLUSH": "1"}

    def launch(self, script: Path, *args: str) -> subprocess.CompletedProcess:
        return self.launch_in(self.home, script, *args)

    def launch_in(self, home: Path, script: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(LAUNCHER), str(script), *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS, env=self.caller_env(home),
                              cwd=self.repo)

    def hand_off(self, epic: str, areas: dict[str, str]) -> str:
        """Hands the epic to the factory through handoff.py, and returns its epic branch."""
        done = self.launch(HANDOFF, "take", epic, *(f"--area={task}={area}" for task, area in areas.items()))
        if done.returncode != 0:
            raise fixture.FixtureError(f"handoff.py take failed: {done.stderr}")
        return json.loads(done.stdout)["branch"]

    def next_moves(self, epic: str) -> subprocess.CompletedProcess:
        return self.launch(SCHEDULER, "next", epic)

    def next_printed(self, epic: str) -> dict:
        done = self.next_moves(epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def shown(self, bead: str) -> dict:
        return json.loads(fixture.run([self.bd, "show", bead, "--json"], self.repo))[0]

    def metadata(self, bead: str) -> dict:
        return self.shown(bead).get("metadata") or {}


class SchedulerOpensLapsTests(SchedulerCase):
    def test_three_ready_tasks_two_in_one_area_open_two_build_laps_in_different_areas_with_their_state_in_bd(self):
        epic = self.new_epic()
        first, second, third = (self.new_task_under(epic) for _ in range(3))
        self.hand_off(epic, {first: "till", second: "till", third: "receipts"})

        printed = self.next_printed(epic)

        actions = printed["actions"]
        self.assertEqual(["build", "build"], [action["action"] for action in actions])
        self.assertEqual([(first, "till"), (third, "receipts")],
                         [(action["task"], action["area"]) for action in actions])
        for action in actions:
            self.assertTrue(Path(action["worktree"]).is_dir())
            metadata = self.metadata(action["task"])
            self.assertEqual((1, "build", 0, action["worktree"], action["slot"], action["branch"]),
                             (metadata.get("lap.number"), metadata.get("lap.stage"), metadata.get("lap.tries"),
                              metadata.get("lap.workspace"), metadata.get("lap.slot"), metadata.get("lap.branch")))
        self.assertNotIn("lap.stage", self.metadata(second))


class SchedulerReadyTaskTests(SchedulerCase):
    def test_a_task_waiting_on_an_open_task_in_the_epic_does_not_open_a_lap(self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        fixture.run([self.bd, "dep", "add", second, "--blocked-by", first], self.repo)
        self.hand_off(epic, {first: "till", second: "receipts"})

        printed = self.next_printed(epic)

        self.assertEqual([first], [action["task"] for action in printed["actions"]])
        self.assertNotIn("lap.stage", self.metadata(second))
        self.assertEqual("open", self.shown(second)["status"])

    def test_an_opened_lap_puts_its_task_in_progress_under_jidoka(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})

        self.next_printed(epic)

        shown = self.shown(task)
        self.assertEqual(("in_progress", "jidoka"), (shown["status"], shown.get("assignee")))

    def test_a_task_someone_has_claimed_never_opens_a_lap(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        fixture.run([self.bd, "update", task, "--assignee=Jeff Scheduler"], self.repo)

        printed = self.next_printed(epic)

        self.assertEqual([], printed["actions"])
        self.assertNotIn("lap.stage", self.metadata(task))

    def test_a_task_labeled_human_never_opens_a_lap(self):
        epic = self.new_epic()
        task = self.new_task_under(epic, "--labels", "human")
        self.hand_off(epic, {task: "till"})

        printed = self.next_printed(epic)

        self.assertEqual([], printed["actions"])
        self.assertNotIn("lap.stage", self.metadata(task))


class SchedulerOrderTests(SchedulerCase):
    def test_ready_tasks_are_taken_in_priority_order(self):
        epic = self.new_epic()
        later = self.new_task_under(epic, "--priority", "3")
        sooner = self.new_task_under(epic, "--priority", "1")
        self.hand_off(epic, {later: "till", sooner: "till"})

        printed = self.next_printed(epic)

        self.assertEqual([sooner], [action["task"] for action in printed["actions"]])

    def test_an_epic_whose_tasks_are_all_closed_gets_no_action(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        fixture.run([self.bd, "close", task, "--reason", "built"], self.repo)

        printed = self.next_printed(epic)

        self.assertEqual(([], []), (printed["actions"], printed["laps"]))


class SchedulerWorkspaceTests(SchedulerCase):
    def test_each_lap_gets_its_own_worktree_on_a_lap_branch_cut_from_the_epic_branch_a_slot_and_a_scratch_folder(
            self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        branch = self.hand_off(epic, {first: "till", second: "receipts"})
        tree = git(self.repo, "rev-parse", f"{branch}^{{tree}}")
        epic_head = git(self.repo, "commit-tree", tree, "-p", branch, "-m", "Work on the epic")
        git(self.repo, "update-ref", f"refs/heads/{branch}", epic_head)

        actions = self.next_printed(epic)["actions"]

        self.assertEqual([1, 2], sorted(action["slot"] for action in actions))
        for action in actions:
            worktree = Path(action["worktree"])
            self.assertEqual(self.repo / ".worktrees" / f"lap-{action['task']}", worktree)
            self.assertEqual(f"lap/{action['task']}", action["branch"])
            self.assertEqual(action["branch"], git(worktree, "branch", "--show-current"))
            self.assertEqual(epic_head, git(worktree, "rev-parse", "HEAD"))
            self.assertEqual(str(worktree / ".scratch"), action["scratch"])
            self.assertTrue((worktree / ".scratch").is_dir())

    def test_a_lap_worktree_and_its_scratch_files_stay_out_of_every_git_status(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})

        action = self.next_printed(epic)["actions"][0]
        worktree = Path(action["worktree"])
        (Path(action["scratch"]) / "notes.txt").write_text("the build's notes\n", encoding="utf-8")

        self.assertEqual("", git(self.repo, "status", "--porcelain", "--untracked-files=all"))
        self.assertEqual("", git(worktree, "status", "--porcelain", "--untracked-files=all"))

    def test_a_rerun_after_the_worktree_was_made_reuses_the_worktree_and_its_branch(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        branch = self.hand_off(epic, {task: "till"})
        worktree = self.repo / ".worktrees" / f"lap-{task}"
        git(self.repo, "worktree", "add", "-q", "-b", f"lap/{task}", str(worktree), branch)

        action = self.next_printed(epic)["actions"][0]

        self.assertEqual((str(worktree), f"lap/{task}"), (action["worktree"], action["branch"]))
        self.assertEqual(str(worktree), self.metadata(task).get("lap.workspace"))


class SchedulerLapStateTests(SchedulerCase):
    def test_a_second_call_opens_nothing_new_and_lists_the_open_laps(self):
        epic = self.new_epic()
        first, second, third = (self.new_task_under(epic) for _ in range(3))
        self.hand_off(epic, {first: "till", second: "receipts", third: "shelf"})
        opened = self.next_printed(epic)["actions"]

        printed = self.next_printed(epic)

        self.assertEqual([], printed["actions"])
        self.assertEqual([{**{key: value for key, value in action.items() if key != "action"},
                           "stage": "build", "tries": 0} for action in opened],
                         printed["laps"])
        self.assertNotIn("lap.stage", self.metadata(third))

    def test_an_open_lap_read_back_from_metadata_holds_its_area_and_its_slot(self):
        epic = self.new_epic()
        first = self.new_task_under(epic)
        same_area = self.new_task_under(epic, "--labels", "human")
        other_area = self.new_task_under(epic, "--labels", "human")
        self.hand_off(epic, {first: "till", same_area: "till", other_area: "receipts"})
        self.assertEqual([first], [action["task"] for action in self.next_printed(epic)["actions"]])
        for task in (same_area, other_area):
            fixture.run([self.bd, "label", "remove", task, "human"], self.repo)

        printed = self.next_printed(epic)

        self.assertEqual([(other_area, 2)], [(action["task"], action["slot"]) for action in printed["actions"]])


class SchedulerRefusalTests(SchedulerCase):
    def assert_nothing_written(self, task: str) -> None:
        self.assertNotIn("lap.stage", self.metadata(task))
        self.assertEqual("open", self.shown(task)["status"])
        self.assertFalse((self.repo / ".worktrees" / f"lap-{task}").exists())

    def test_refuses_an_epic_that_was_never_handed_off_and_says_to_hand_it_off(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)

        done = self.next_moves(epic)

        self.assertEqual(1, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn(f"{epic} does not carry the factory label, so the factory does not hold it. Hand it off "
                      f"first with /jidoka:handoff {epic}", done.stderr)
        self.assert_nothing_written(task)

    def test_refuses_an_epic_whose_epic_branch_is_gone(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        branch = self.hand_off(epic, {task: "till"})
        git(self.repo, "branch", "-D", branch)

        done = self.next_moves(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"the epic branch {branch} that {epic} records does not exist", done.stderr)
        self.assert_nothing_written(task)

    def test_refuses_a_handed_off_epic_that_now_fails_a_handoff_check_reporting_every_problem(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        outside = self.create("Pick a card reader", "--type=task")
        fixture.run([self.bd, "dep", "add", task, "--blocked-by", outside], self.repo)
        inner = self.create("Refund a card", "--type=epic", "--parent", epic)

        done = self.next_moves(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{task} waits on {outside} (Pick a card reader), an open bead outside {epic}", done.stderr)
        self.assertIn(f"{epic} holds {inner}, which is an epic", done.stderr)
        self.assert_nothing_written(task)

    def test_refuses_a_task_and_says_to_run_the_scheduler_on_the_epic_that_holds_it(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})

        done = self.next_moves(task)

        self.assertEqual(1, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn(f"{task} is a task, not an epic. Run the scheduler on the epic that holds it", done.stderr)
        self.assertNotIn("Hand off", done.stderr)
        self.assert_nothing_written(task)

    def test_refuses_a_repo_with_no_repo_settings_and_says_to_onboard_then_run_the_scheduler_again(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        bare_home = self.new_home(f"bare-home-{self.count}")

        done = self.launch_in(bare_home, SCHEDULER, "next", epic)

        self.assertEqual(1, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn("the repo has no repo settings on this machine. Run /jidoka:onboard, then run the scheduler "
                      "again", done.stderr)
        self.assertNotIn("hand the epic off", done.stderr)
        self.assert_nothing_written(task)

    def test_a_call_with_no_epic_is_a_usage_error(self):
        done = self.launch(SCHEDULER, "next")

        self.assertEqual(2, done.returncode)


if __name__ == "__main__":
    unittest.main()
