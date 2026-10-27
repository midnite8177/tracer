import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
SCHEDULER = PLUGIN / "scripts" / "scheduler.py"
HANDOFF = PLUGIN / "scripts" / "handoff.py"
SETTINGS_SCRIPT = PLUGIN / "scripts" / "repo_settings.py"
MERGE_GATE = PLUGIN / "scripts" / "merge_gate.py"

RUN_TIMEOUT_SECONDS = 120
JEFF = "Jeff Scheduler"
LAP_LIMIT = 2
ACCEPTANCE = "specs/acceptance"
EPIC_BRANCH_MOVED_EXIT_CODE = 3
LOCK_LINE_SECONDS = 60

TEST_COMMAND_THAT_LOGS_ITS_ARGUMENTS_AND_EXITS_WITH_THE_QUEUED_CODE = """\
import sys
from pathlib import Path
folder = Path(sys.argv[1])
name = Path.cwd().name
with open(folder / f"{name}.log", "a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[2:]) + "\\n")
codes = folder / f"exit-codes-{name}"
code = 0
if codes.exists():
    lines = codes.read_text(encoding="utf-8").split()
    code = int(lines[0]) if lines else 0
    codes.write_text("\\n".join(lines[1:]), encoding="utf-8")
print("runner output", code)
sys.exit(code)
"""


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


@dataclass(frozen=True)
class OpenLap:
    """An epic handed off with one task, and the lap the scheduler opened for it."""
    epic: str
    task: str
    epic_branch: str
    worktree: Path


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
        cls.runs = cls.root / "runs"
        cls.runs.mkdir()
        runner = cls.root / "runner.py"
        runner.write_text(TEST_COMMAND_THAT_LOGS_ITS_ARGUMENTS_AND_EXITS_WITH_THE_QUEUED_CODE, encoding="utf-8")
        cls.test_command = f'"{sys.executable}" "{runner}" "{cls.runs}"'
        settings = {"lap_test_scope": "targeted", "worker_commands": [], "slot_use": None, "lap_limit": LAP_LIMIT,
                    "apps": [{"name": "shop", "kind": "program", "way_in": "its command line", "build": "make",
                              "run": None, "test": cls.test_command, "test_target": "-k <name>",
                              "test_full": None, "hand_run": [], "acceptance": ACCEPTANCE}]}
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

    def comments(self, bead: str) -> list[dict]:
        return json.loads(fixture.run([self.bd, "comments", bead, "--json"], self.repo) or "[]") or []

    def report(self, epic: str, task: str, outcome: str, *flags: str) -> subprocess.CompletedProcess:
        return self.launch(SCHEDULER, "report", epic, task, outcome, *flags)

    def report_printed(self, epic: str, task: str, outcome: str, *flags: str) -> dict:
        done = self.report(epic, task, outcome, *flags)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def build_done(self, epic: str, task: str) -> dict:
        return self.report_printed(epic, task, "done", "--app", "shop", "--filter", "test_card")

    def commit_in(self, worktree: Path, name: str, text: str) -> str:
        """Commits one file in the worktree, as a build worker would, and returns the new head."""
        path = worktree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        fixture.git_commit_all(worktree, f"Add {name}")
        return git(worktree, "rev-parse", "HEAD")

    def leave_in(self, worktree: Path, name: str, text: str) -> None:
        """Writes one file in the worktree and commits nothing, as a build worker does."""
        path = worktree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def files_of(self, commit: str) -> list[str]:
        return sorted(git(self.repo, "show", "--format=", "--name-only", commit).splitlines())

    def queue_exit_codes(self, task: str, *codes: int) -> None:
        (self.runs / f"exit-codes-lap-{task}").write_text("\n".join(str(code) for code in codes), encoding="utf-8")

    def runs_of(self, task: str) -> list[str]:
        log = self.runs / f"lap-{task}.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def is_on(self, commit: str, branch: str) -> bool:
        return subprocess.run(["git", "merge-base", "--is-ancestor", commit, branch], cwd=self.repo).returncode == 0

    def open_one_lap(self) -> OpenLap:
        epic = self.new_epic()
        task = self.new_task_under(epic)
        branch = self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        return OpenLap(epic, task, branch, Path(action["worktree"]))

    def commit_on_epic_branch(self, branch: str, name: str, text: str) -> str:
        """Commits one file on the epic branch, as another lap's merge would, and returns its new head."""
        type(self).count += 1
        tree = self.root / f"epic-tree-{self.count}"
        git(self.repo, "worktree", "add", "-q", str(tree), branch)
        head = self.commit_in(tree, name, text)
        git(self.repo, "worktree", "remove", "--force", str(tree))
        return head

    def check_out_in_main_checkout(self, branch: str) -> None:
        git(self.repo, "checkout", "-q", branch)
        self.addCleanup(lambda: git(self.repo, "checkout", "-q", "--force", "main"))

    def texts(self, bead: str) -> list[str]:
        return [str(comment["text"]) for comment in self.comments(bead)]

    def assert_parked(self, lap: OpenLap, tries: int) -> str:
        """Asserts the task waits on the human with its work kept, and returns the comment that says why."""
        shown = self.shown(lap.task)
        metadata = shown.get("metadata") or {}
        self.assertEqual(("open", "", ["human"]), (shown["status"], shown.get("assignee") or "",
                                                    shown.get("labels")))
        self.assertEqual(("parked", tries), (metadata.get("lap.stage"), metadata.get("lap.tries")))
        self.assertTrue(lap.worktree.is_dir())
        self.assertIn(f"lap/{lap.task}", git(self.repo, "branch", "--list"))
        parked = [comment for comment in self.comments(lap.task) if str(comment["text"]).startswith("Parked: ")]
        self.assertEqual(1, len(parked))
        self.assertEqual("jidoka", parked[0]["author"])
        return str(parked[0]["text"])


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


class ManagerDrivesAnEpicTests(SchedulerCase):
    def test_the_manager_drives_a_two_task_epic_until_both_tasks_are_closed_and_the_epic_branch_holds_both_commits(
            self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        branch = self.hand_off(epic, {first: "till", second: "receipts"})
        actions = self.next_printed(epic)["actions"]
        built = {action["task"]: self.commit_in(Path(action["worktree"]), f"{action['task']}.txt", "built\n")
                 for action in actions}

        after_first = self.build_done(epic, first)
        after_second = self.build_done(epic, second)

        self.assertEqual([first, second], sorted(built))
        self.assertEqual(([], [second]), (after_first["actions"], [lap["task"] for lap in after_first["laps"]]))
        self.assertEqual(([], []), (after_second["actions"], after_second["laps"]))
        self.assertEqual(("closed", "closed"), (self.shown(first)["status"], self.shown(second)["status"]))
        self.assertTrue(all(self.is_on(commit, branch) for commit in built.values()))
        self.assertEqual(["-k test_card"], self.runs_of(first))
        self.assertEqual(["-k test_card"], self.runs_of(second))

    def test_the_manager_drives_a_two_task_epic_whose_builds_leave_their_work_uncommitted_until_both_merge(self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        branch = self.hand_off(epic, {first: "till", second: "receipts"})
        for action in self.next_printed(epic)["actions"]:
            self.leave_in(Path(action["worktree"]), f"{action['task']}.txt", "built\n")

        self.build_done(epic, first)
        after_second = self.build_done(epic, second)

        self.assertEqual(([], []), (after_second["actions"], after_second["laps"]))
        self.assertEqual(("closed", "closed"), (self.shown(first)["status"], self.shown(second)["status"]))
        self.assertEqual(("built", "built"), (git(self.repo, "show", f"{branch}:{first}.txt"),
                                              git(self.repo, "show", f"{branch}:{second}.txt")))


class BuildCommitTests(SchedulerCase):
    def test_a_done_build_s_uncommitted_work_merges_as_one_commit_named_by_the_task_title_under_the_git_user(self):
        lap = self.open_one_lap()
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)
        self.leave_in(lap.worktree, "card.txt", "built\n")
        self.leave_in(lap.worktree, "reader/card.py", "print('card')\n")

        self.build_done(lap.epic, lap.task)

        title = self.shown(lap.task)["title"]
        self.assertEqual("closed", self.shown(lap.task)["status"])
        self.assertEqual(epic_head, git(self.repo, "rev-parse", f"{lap.epic_branch}~1"))
        self.assertEqual(f"{title}\n{JEFF}", git(self.repo, "log", "-1", "--format=%s%n%an", lap.epic_branch))
        self.assertEqual(["card.txt", "reader/card.py"], self.files_of(lap.epic_branch))

    def test_the_scratch_folder_stays_out_of_the_commit_of_the_build_s_work(self):
        lap = self.open_one_lap()
        self.leave_in(lap.worktree, "card.txt", "built\n")
        self.leave_in(lap.worktree, ".scratch/notes.txt", "the build's notes\n")

        self.build_done(lap.epic, lap.task)

        self.assertEqual("closed", self.shown(lap.task)["status"])
        self.assertEqual(["card.txt"], self.files_of(lap.epic_branch))

    def test_the_scratch_folder_stays_out_of_the_commit_even_when_the_exclude_file_no_longer_hides_it(self):
        lap = self.open_one_lap()
        exclude = self.repo / ".git" / "info" / "exclude"
        kept = exclude.read_text(encoding="utf-8")
        self.addCleanup(lambda: exclude.write_text(kept, encoding="utf-8"))
        exclude.write_text("".join(line for line in kept.splitlines(keepends=True) if ".scratch" not in line),
                           encoding="utf-8")
        self.leave_in(lap.worktree, "card.txt", "built\n")
        self.leave_in(lap.worktree, ".scratch/notes.txt", "the build's notes\n")

        self.build_done(lap.epic, lap.task)

        self.assertEqual("closed", self.shown(lap.task)["status"])
        self.assertEqual(["card.txt"], self.files_of(lap.epic_branch))

    def test_a_done_build_that_left_only_scratch_files_makes_no_commit_and_counts_an_empty_lap_try(self):
        lap = self.open_one_lap()
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)
        self.leave_in(lap.worktree, ".scratch/notes.txt", "the build's notes\n")

        printed = self.build_done(lap.epic, lap.task)

        self.assertEqual([(lap.task, 1)], [(open_lap["task"], open_lap["tries"]) for open_lap in printed["laps"]])
        self.assertIn(f"Build try 1 of 3 failed: no commits on the lap that {lap.epic_branch} lacks. The lap goes "
                      "back to the build.", self.texts(lap.task))
        self.assertEqual(epic_head, git(lap.worktree, "rev-parse", "HEAD"))
        self.assertEqual(epic_head, git(self.repo, "rev-parse", lap.epic_branch))

    def test_a_build_that_committed_its_own_work_and_left_a_clean_tree_gets_no_second_commit(self):
        lap = self.open_one_lap()
        built = self.commit_in(lap.worktree, "card.txt", "built\n")

        self.build_done(lap.epic, lap.task)

        self.assertEqual(built, git(self.repo, "rev-parse", lap.epic_branch))


class BuildOutcomeTests(SchedulerCase):
    def test_a_failed_build_sends_the_lap_back_to_the_build_and_counts_a_try(self):
        lap = self.open_one_lap()

        printed = self.report_printed(lap.epic, lap.task, "failed")

        self.assertEqual([("build", lap.task, str(lap.worktree))],
                         [(action["action"], action["task"], action["worktree"]) for action in printed["actions"]])
        self.assertEqual([("build", 1)], [(open_lap["stage"], open_lap["tries"]) for open_lap in printed["laps"]])
        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))
        self.assertEqual("in_progress", self.shown(lap.task)["status"])

    def test_a_cut_off_build_goes_back_to_the_build_without_counting_a_try(self):
        lap = self.open_one_lap()

        printed = self.report_printed(lap.epic, lap.task, "cut off")

        self.assertEqual([("build", lap.task)], [(action["action"], action["task"]) for action in printed["actions"]])
        self.assertEqual(0, self.metadata(lap.task)["lap.tries"])

    def test_a_task_whose_build_fails_three_times_shows_the_human_label_and_a_comment_saying_why(self):
        lap = self.open_one_lap()

        self.report_printed(lap.epic, lap.task, "failed")
        self.report_printed(lap.epic, lap.task, "failed")
        printed = self.report_printed(lap.epic, lap.task, "failed")

        self.assertEqual(([], []), (printed["actions"], printed["laps"]))
        why = self.assert_parked(lap, 3)
        self.assertIn("build try 3 of 3 failed", why)
        self.assertIn("the build worker reported that the build failed", why)


    def test_a_build_reported_done_with_no_commits_counts_a_try_each_time_and_the_third_parks_the_task(self):
        lap = self.open_one_lap()
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)

        first = self.build_done(lap.epic, lap.task)
        self.build_done(lap.epic, lap.task)
        third = self.build_done(lap.epic, lap.task)

        self.assertEqual([(lap.task, 1)], [(open_lap["task"], open_lap["tries"]) for open_lap in first["laps"]])
        self.assertEqual([("build", lap.task)], [(action["action"], action["task"]) for action in first["actions"]])
        self.assertIn(f"Build try 1 of 3 failed: no commits on the lap that {lap.epic_branch} lacks. The lap goes "
                      "back to the build.", self.texts(lap.task))
        self.assertEqual(([], []), (third["actions"], third["laps"]))
        why = self.assert_parked(lap, 3)
        self.assertIn("build try 3 of 3 failed: no commits on the lap", why)
        self.assertEqual(epic_head, git(self.repo, "rev-parse", lap.epic_branch))


class TargetedRunTests(SchedulerCase):
    def test_the_targeted_tests_run_on_the_lap_head_merged_with_the_epic_branch(self):
        lap = self.open_one_lap()
        built = self.commit_in(lap.worktree, "card.txt", "built\n")
        moved = self.commit_on_epic_branch(lap.epic_branch, "other.txt", "other lap\n")

        self.build_done(lap.epic, lap.task)

        self.assertEqual(["-k test_card"], self.runs_of(lap.task))
        self.assertEqual(f"{built} {moved}", git(self.repo, "log", "-1", "--format=%P", lap.epic_branch))
        self.assertEqual(moved, self.metadata(lap.task)["tests.base"])

    def test_red_targeted_tests_send_the_lap_back_to_the_build_and_count_a_try_recorded_by_jidoka(self):
        lap = self.open_one_lap()
        before = git(self.repo, "rev-parse", lap.epic_branch)
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.queue_exit_codes(lap.task, 1)

        printed = self.build_done(lap.epic, lap.task)

        self.assertEqual([lap.task], [action["task"] for action in printed["actions"]])
        metadata = self.metadata(lap.task)
        self.assertEqual(("build", 1, "fail"), (metadata["lap.stage"], metadata["lap.tries"],
                                                metadata["tests.result"]))
        self.assertEqual(before, git(self.repo, "rev-parse", lap.epic_branch))
        [tested] = [comment for comment in self.comments(lap.task) if "Targeted tests failed" in comment["text"]]
        self.assertEqual("jidoka", tested["author"])
        self.assertIn(f"merged with {lap.epic_branch}", tested["text"])

    def test_a_filter_that_repeats_the_test_target_counts_a_try_and_runs_nothing(self):
        lap = self.open_one_lap()

        printed = self.report_printed(lap.epic, lap.task, "done", "--app", "shop", "--filter", "-k test_card")

        self.assertEqual([lap.task], [action["task"] for action in printed["actions"]])
        self.assertEqual(1, self.metadata(lap.task)["lap.tries"])
        self.assertEqual([], self.runs_of(lap.task))
        self.assertTrue(any('pass "test_card"' in text for text in self.texts(lap.task)))

    def test_a_conflict_merging_the_epic_branch_into_the_lap_parks_the_task_at_once_naming_the_files(self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "the lap's card\n")
        epic_head = self.commit_on_epic_branch(lap.epic_branch, "card.txt", "another lap's card\n")

        printed = self.build_done(lap.epic, lap.task)

        self.assertEqual([], printed["actions"])
        why = self.assert_parked(lap, 0)
        self.assertIn("card.txt", why)
        self.assertIn("conflicts", why)
        self.assertEqual([], self.runs_of(lap.task))
        self.assertEqual(epic_head, git(self.repo, "rev-parse", lap.epic_branch))


class MergedLapTests(SchedulerCase):
    def test_a_merged_lap_closes_its_task_naming_the_commit_and_leaves_no_worktree_or_lap_branch(self):
        lap = self.open_one_lap()
        built = self.commit_in(lap.worktree, "card.txt", "built\n")

        self.build_done(lap.epic, lap.task)

        shown = self.shown(lap.task)
        self.assertEqual(built, git(self.repo, "rev-parse", lap.epic_branch))
        self.assertEqual(("closed", f"{built}: merged into {lap.epic_branch}", "merged"),
                         (shown["status"], shown["close_reason"], (shown.get("metadata") or {}).get("lap.stage")))
        self.assertFalse(lap.worktree.exists())
        self.assertNotIn(str(lap.worktree), git(self.repo, "worktree", "list"))
        self.assertEqual("", git(self.repo, "branch", "--list", f"lap/{lap.task}"))

    def test_the_report_that_merges_a_lap_opens_the_lap_of_the_task_that_waited_on_it(self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        fixture.run([self.bd, "dep", "add", second, "--blocked-by", first], self.repo)
        branch = self.hand_off(epic, {first: "till", second: "receipts"})
        [action] = self.next_printed(epic)["actions"]
        built = self.commit_in(Path(action["worktree"]), "card.txt", "built\n")

        printed = self.build_done(epic, first)

        [opened] = printed["actions"]
        self.assertEqual(("build", second), (opened["action"], opened["task"]))
        self.assertEqual(built, git(Path(opened["worktree"]), "rev-parse", "HEAD"))
        self.assertEqual(built, git(self.repo, "rev-parse", branch))

    def test_a_clean_main_checkout_with_the_epic_branch_checked_out_gets_the_merged_files(self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.check_out_in_main_checkout(lap.epic_branch)

        self.build_done(lap.epic, lap.task)

        self.assertEqual("closed", self.shown(lap.task)["status"])
        self.assertEqual("built\n", (self.repo / "card.txt").read_text(encoding="utf-8"))
        self.assertEqual("", git(self.repo, "status", "--porcelain", "--untracked-files=all"))


class ParkedLapTests(SchedulerCase):
    def test_the_report_that_parks_a_lap_opens_a_lap_for_the_next_task_in_its_area_on_its_slot(self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic, "--priority", "1"), self.new_task_under(epic, "--priority", "2")
        self.hand_off(epic, {first: "till", second: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.report_printed(epic, first, "failed")
        self.report_printed(epic, first, "failed")

        printed = self.report_printed(epic, first, "failed")

        self.assertEqual([(second, action["slot"])],
                         [(opened["task"], opened["slot"]) for opened in printed["actions"]])
        self.assertEqual([second], [open_lap["task"] for open_lap in printed["laps"]])
        self.assertEqual([], self.next_printed(epic)["actions"])
        self.assertEqual("parked", self.metadata(first)["lap.stage"])


class MergeGateRefusalTests(SchedulerCase):
    def test_a_lap_that_changed_a_protected_path_is_parked_with_a_comment_naming_the_check(self):
        lap = self.open_one_lap()
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)
        self.commit_in(lap.worktree, f"{ACCEPTANCE}/card.txt", "an easier spec\n")

        printed = self.build_done(lap.epic, lap.task)

        self.assertEqual([], printed["actions"])
        why = self.assert_parked(lap, 0)
        self.assertIn("protected paths", why)
        self.assertIn(f"{ACCEPTANCE}/card.txt", why)
        self.assertEqual(epic_head, git(self.repo, "rev-parse", lap.epic_branch))

    def test_a_main_checkout_with_the_epic_branch_checked_out_and_uncommitted_edits_parks_the_lap(self):
        lap = self.open_one_lap()
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.check_out_in_main_checkout(lap.epic_branch)
        (self.repo / "README.md").write_text("shop, edited by hand\n", encoding="utf-8")

        self.build_done(lap.epic, lap.task)

        why = self.assert_parked(lap, 0)
        self.assertIn("main checkout", why)
        self.assertIn("README.md", why)
        self.assertEqual(epic_head, git(self.repo, "rev-parse", lap.epic_branch))
        self.assertEqual("shop, edited by hand\n", (self.repo / "README.md").read_text(encoding="utf-8"))


class MergeGateRecordTests(SchedulerCase):
    def record_tests(self, task: str, base: str, result: str) -> None:
        fixture.run([self.bd, "update", task, "--set-metadata", "tests.command=make test -k test_card",
                     "--set-metadata", f"tests.base={base}", "--set-metadata", f"tests.result={result}"], self.repo)

    def assert_nothing_merged(self, lap: OpenLap, epic_head: str) -> None:
        self.assertEqual(epic_head, git(self.repo, "rev-parse", lap.epic_branch))
        self.assertEqual("in_progress", self.shown(lap.task)["status"])
        self.assertTrue(lap.worktree.is_dir())

    def test_the_gate_refuses_a_lap_whose_latest_targeted_run_did_not_pass(self):
        lap = self.open_one_lap()
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.record_tests(lap.task, epic_head, "fail")

        done = self.launch(MERGE_GATE, lap.task)

        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("the record does not support the merge", done.stderr)
        self.assert_nothing_merged(lap, epic_head)

    def test_the_gate_refuses_a_lap_with_no_commits_the_epic_branch_lacks_names_the_check_and_writes_nothing(self):
        lap = self.open_one_lap()
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)
        self.record_tests(lap.task, epic_head, "pass")

        done = self.launch(MERGE_GATE, lap.task)

        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(f"refused: no commits on the lap that {lap.epic_branch} lacks", done.stderr)
        self.assert_nothing_merged(lap, epic_head)
        self.assertEqual(0, self.metadata(lap.task)["lap.tries"])
        self.assertEqual([], self.comments(lap.task))

    def test_the_gate_sends_back_to_the_targeted_tests_a_lap_whose_run_merged_an_older_epic_head(self):
        lap = self.open_one_lap()
        older = git(self.repo, "rev-parse", lap.epic_branch)
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.record_tests(lap.task, older, "pass")
        moved = self.commit_on_epic_branch(lap.epic_branch, "other.txt", "other lap\n")

        done = self.launch(MERGE_GATE, lap.task)

        self.assertEqual(EPIC_BRANCH_MOVED_EXIT_CODE, done.returncode, done.stderr)
        self.assertIn(f"merged in {lap.epic_branch} at {older}", done.stderr)
        self.assert_nothing_merged(lap, moved)

    def test_the_gate_sends_back_to_the_targeted_tests_a_lap_whose_head_lacks_the_epic_branch(self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        moved = self.commit_on_epic_branch(lap.epic_branch, "other.txt", "other lap\n")
        self.record_tests(lap.task, moved, "pass")

        done = self.launch(MERGE_GATE, lap.task)

        self.assertEqual(EPIC_BRANCH_MOVED_EXIT_CODE, done.returncode, done.stderr)
        self.assertIn(f"does not contain {lap.epic_branch} at {moved}", done.stderr)
        self.assert_nothing_merged(lap, moved)


class EpicBranchMovesBeforeTheGateTests(SchedulerCase):
    def test_when_the_epic_branch_moves_while_the_gate_waits_on_the_lock_the_tests_run_again_and_the_lap_merges(
            self):
        lap = self.open_one_lap()
        built = self.commit_in(lap.worktree, "card.txt", "built\n")
        lock = self.home / "locks" / "merge.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("424242\n", encoding="utf-8")
        self.addCleanup(lambda: lock.unlink(missing_ok=True))
        process = subprocess.Popen([str(LAUNCHER), str(SCHEDULER), "report", lap.epic, lap.task, "done", "--app",
                                    "shop", "--filter", "test_card"], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                   env=self.caller_env(self.home), cwd=self.repo)
        lines: queue.Queue = queue.Queue()
        threading.Thread(target=lambda: [lines.put(line) for line in process.stderr], daemon=True).start()
        try:
            line = ""
            while "waiting for the merge lock" not in line:
                line = lines.get(timeout=LOCK_LINE_SECONDS)
            moved = self.commit_on_epic_branch(lap.epic_branch, "other.txt", "other lap\n")
            lock.unlink()
            out = process.stdout.read()
            process.wait(timeout=RUN_TIMEOUT_SECONDS)
        finally:
            process.kill()
            process.wait()

        self.assertEqual(0, process.returncode)
        self.assertEqual([], json.loads(out)["actions"])
        self.assertEqual(["-k test_card", "-k test_card"], self.runs_of(lap.task))
        self.assertEqual(f"{built} {moved}", git(self.repo, "log", "-1", "--format=%P", lap.epic_branch))
        self.assertEqual("closed", self.shown(lap.task)["status"])
        self.assertEqual(0, self.metadata(lap.task)["lap.tries"])


class ReportRefusalTests(SchedulerCase):
    def test_done_without_an_app_and_a_filter_is_refused_and_nothing_is_written(self):
        lap = self.open_one_lap()

        done = self.report(lap.epic, lap.task, "done")

        self.assertEqual(1, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn("done needs --app and --filter", done.stderr)
        self.assertEqual(("build", 0), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))
        self.assertEqual([], self.runs_of(lap.task))

    def test_a_report_on_a_task_with_no_open_lap_is_refused(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})

        done = self.report(epic, task, "failed")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{task} has no open lap", done.stderr)
        self.assertNotIn("lap.tries", self.metadata(task))

    def test_an_outcome_outside_the_fixed_set_is_a_usage_error(self):
        lap = self.open_one_lap()

        done = self.report(lap.epic, lap.task, "finished")

        self.assertEqual(2, done.returncode)
        self.assertEqual(0, self.metadata(lap.task)["lap.tries"])


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
