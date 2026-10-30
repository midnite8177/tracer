import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
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
RULES = PLUGIN / "scripts" / "rules.py"
SETTINGS_SCRIPT = PLUGIN / "scripts" / "repo_settings.py"
MERGE_GATE = PLUGIN / "scripts" / "merge_gate.py"
SAVED_PRICE_PAGES = HERE / "fixtures" / "pricing"

RUN_TIMEOUT_SECONDS = 120
OUT_OF_SCOPE = "## Out of Scope\nRefunds."
ONE_SEAM = "## Seams\nThe card reader, run as a process."
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
    """The shop repo, onboarded with a lap limit of two, with the fake bd first on its scripts' PATH, and the helpers
    of the scheduler tests."""

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
        cls.bin = cls.root / "bin"
        cls.bd = str(fixture.add_fake_beads(cls.repo, cls.bin))
        cls.count = 0
        cls.home = cls.root / "jidoka-home"
        cls.home.mkdir()
        (cls.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        cls.runs = cls.root / "runs"
        cls.runs.mkdir()
        runner = cls.root / "runner.py"
        runner.write_text(TEST_COMMAND_THAT_LOGS_ITS_ARGUMENTS_AND_EXITS_WITH_THE_QUEUED_CODE, encoding="utf-8")
        cls.test_command = f'"{sys.executable}" "{runner}" "{cls.runs}"'
        cls.write_settings({})

    @classmethod
    def write_settings(cls, extra: dict) -> None:
        settings = {"lap_test_scope": "targeted", "worker_commands": [], "slot_use": None, "lap_limit": LAP_LIMIT,
                    "apps": [{"name": "shop", "kind": "program", "way_in": "its command line", "build": "make",
                              "run": None, "test": cls.test_command, "test_target": "-k <name>",
                              "test_full": None, "hand_run": [], "acceptance": ACCEPTANCE}], **extra}
        done = subprocess.run(fixture.launch_command(LAUNCHER, [str(SETTINGS_SCRIPT), "write"]),
                              input=json.dumps(settings), capture_output=True, text=True, encoding="utf-8",
                              timeout=RUN_TIMEOUT_SECONDS, env={**os.environ, "JIDOKA_HOME": str(cls.home)},
                              cwd=cls.repo)
        if done.returncode != 0:
            raise fixture.FixtureError(f"repo_settings.py write failed: {done.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def create(self, title: str, *flags: str) -> str:
        return json.loads(fixture.run([self.bd, "create", "--title", title, *flags, "--json"], self.repo))["id"]

    def new_epic(self) -> str:
        type(self).count += 1
        return self.create(f"Take card payments {self.count}", "--type=epic", "--description", OUT_OF_SCOPE)

    def new_task_under(self, epic: str, *flags: str) -> str:
        type(self).count += 1
        return self.create(f"Read the card {self.count}", "--type=task", "--parent", epic,
                           "--description", ONE_SEAM, *flags)

    def new_home(self, name: str) -> Path:
        """A jidoka home that knows the Python and holds no repo settings."""
        home = self.root / name
        home.mkdir()
        (home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        return home

    def caller_env(self, home: Path) -> dict[str, str]:
        """The environment the scripts run in, which reads the providers' pricing pages from the saved copies."""
        return {**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(home), "BEADS_ACTOR": "claude",
                "JIDOKA_PRICE_PAGES": str(SAVED_PRICE_PAGES)}

    def launch(self, script: Path, *args: str) -> subprocess.CompletedProcess:
        return self.launch_in(self.home, script, *args)

    def launch_in(self, home: Path, script: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(fixture.launch_command(LAUNCHER, [str(script), *args]), capture_output=True,
                              text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS, env=self.caller_env(home),
                              cwd=self.repo)

    def hand_off(self, epic: str, areas: dict[str, str]) -> str:
        """Hands the epic to the factory through handoff.py, and returns its epic branch."""
        done = self.launch(HANDOFF, "take", epic, *(f"--area={task}={area}" for task, area in areas.items()))
        if done.returncode != 0:
            raise fixture.FixtureError(f"handoff.py take failed: {done.stderr}")
        return json.loads(done.stdout)["branch"]

    def rules(self, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(fixture.launch_command(LAUNCHER, [str(RULES), *args]), input=stdin,
                              capture_output=True, text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS,
                              env=self.caller_env(self.home), cwd=self.repo)

    def rules_set(self, epic: str, *settings: str) -> dict:
        done = self.rules("set", epic, *settings)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def rule_comments(self, epic: str) -> list[dict]:
        return [comment for comment in self.comments(epic) if str(comment["text"]).startswith("Factory rules:")]

    def handed_off_epic(self, areas: int) -> str:
        epic = self.new_epic()
        tasks = [self.new_task_under(epic) for _ in range(areas)]
        self.hand_off(epic, {task: f"area-{index}" for index, task in enumerate(tasks)})
        return epic

    def next_moves(self, epic: str) -> subprocess.CompletedProcess:
        """Runs `next` as a manager that starts after the one before it is gone, so the epic holds no heartbeat."""
        (self.home / "heartbeat" / f"{epic}.json").unlink(missing_ok=True)
        return self.launch(SCHEDULER, "next", epic)

    def next_printed(self, epic: str) -> dict:
        done = self.next_moves(epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def shown(self, bead: str) -> dict:
        return json.loads(fixture.run([self.bd, "show", bead, "--json"], self.repo))[0]

    def metadata(self, bead: str) -> dict:
        return self.shown(bead).get("metadata") or {}

    def children_of(self, epic: str) -> dict[str, str]:
        """The titles of the epic's children, each with its id."""
        listed = json.loads(fixture.run([self.bd, "list", "--parent", epic, "--all", "--limit", "0", "--json"],
                                        self.repo))
        return {child["title"]: child["id"] for child in listed}

    def bead_titled(self, title: str) -> str:
        listed = json.loads(fixture.run([self.bd, "list", "--all", "--limit", "0", "--json"], self.repo))
        [found] = [bead["id"] for bead in listed if bead["title"] == title]
        return found

    def links_of(self, bead: str) -> set[tuple[str, str]]:
        return {(link["dependency_type"], link["id"]) for link in self.shown(bead).get("dependencies") or []}

    def comments(self, bead: str) -> list[dict]:
        return json.loads(fixture.run([self.bd, "comments", bead, "--json"], self.repo) or "[]") or []

    def report(self, epic: str, task: str, outcome: str, *flags: str) -> subprocess.CompletedProcess:
        return self.launch(SCHEDULER, "report", epic, task, outcome, *flags)

    def report_printed(self, epic: str, task: str, outcome: str, *flags: str) -> dict:
        done = self.report(epic, task, outcome, *flags)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def lap_actions(self, printed: dict) -> list[dict]:
        """The actions that start a lap's worker, leaving out the pass's own actions."""
        return [action for action in printed["actions"] if "task" in action]

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

    def test_a_new_lap_records_its_try_caps_beside_its_tries(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})

        self.next_printed(epic)

        metadata = self.metadata(task)
        self.assertEqual((0, 3, 0, 2), (metadata["lap.tries"], metadata["lap.trycap"], metadata["lap.mergetries"],
                                        metadata["lap.mergetrycap"]))


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


class SchedulerTaskWithNoAreaTests(SchedulerCase):
    def test_a_task_added_after_handoff_is_named_with_the_command_that_gives_it_an_area_and_opens_no_lap(self):
        epic = self.new_epic()
        handed_off = self.new_task_under(epic)
        self.hand_off(epic, {handed_off: "till"})
        added = self.new_task_under(epic)

        done = self.next_moves(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"{added} has no area, so no lap opens for it. Run bd update {added} "
                      "--set-metadata lap.area=<area>", done.stderr)
        printed = json.loads(done.stdout)
        self.assertEqual([added], printed["no_area"])
        self.assertEqual([handed_off], [action["task"] for action in printed["actions"]])
        self.assertNotIn("lap.stage", self.metadata(added))

    def test_a_task_that_was_given_an_area_after_handoff_opens_its_lap(self):
        epic = self.new_epic()
        handed_off = self.new_task_under(epic)
        self.hand_off(epic, {handed_off: "till"})
        added = self.new_task_under(epic)
        fixture.run([self.bd, "update", added, "--set-metadata", "lap.area=receipts"], self.repo)

        done = self.next_moves(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("has no area", done.stderr)
        printed = json.loads(done.stdout)
        self.assertEqual([], printed["no_area"])
        self.assertEqual([handed_off, added], [action["task"] for action in printed["actions"]])

    def test_a_task_with_no_area_that_waits_on_the_human_is_not_named(self):
        epic = self.new_epic()
        handed_off = self.new_task_under(epic)
        self.hand_off(epic, {handed_off: "till"})
        self.new_task_under(epic, "--labels", "human")

        done = self.next_moves(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("has no area", done.stderr)
        self.assertEqual([], json.loads(done.stdout)["no_area"])


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

    def finished_epic(self) -> str:
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        fixture.run([self.bd, "close", task, "--reason", "built"], self.repo)
        return epic

    def test_an_epic_whose_tasks_are_all_closed_runs_its_validation(self):
        epic = self.finished_epic()

        printed = self.next_printed(epic)

        self.assertIsNotNone(printed["validation"])

    def test_an_epic_whose_tasks_are_all_closed_starts_no_pass_stage_while_a_pause_waits(self):
        epic = self.finished_epic()
        now = int(time.time())
        waiting = json.dumps({"cause": "usage-limit", "since": now, "until": now + 3600, "retries": 0})
        fixture.run([self.bd, "update", epic, "--set-metadata", f"pause={waiting}"], self.repo)

        printed = self.next_printed(epic)

        self.assertIsNone(printed["validation"])
        self.assertEqual(([], "usage-limit"), (printed["actions"], printed["paused"]["cause"]))


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


class SchedulerPrivateDocsTests(SchedulerCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.repo / "GLOSSARY.md").write_text("# shop\n", encoding="utf-8")
        (cls.repo / "docs" / "adr").mkdir(parents=True)
        (cls.repo / "docs" / "adr" / "0001-start.md").write_text("# 0001\n", encoding="utf-8")
        cls.write_settings({"glossary_and_adrs": "private"})

    def test_a_lap_worktree_in_a_private_repo_links_to_the_main_checkouts_glossary_and_adrs_and_stays_clean(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})

        worktree = Path(self.next_printed(epic)["actions"][0]["worktree"])

        self.assertEqual(self.repo / "GLOSSARY.md", fixture.link_target(worktree / "GLOSSARY.md"))
        self.assertEqual(self.repo / "docs" / "adr", fixture.link_target(worktree / "docs" / "adr"))
        self.assertEqual("# 0001\n", (worktree / "docs" / "adr" / "0001-start.md").read_text(encoding="utf-8"))
        self.assertEqual("", git(worktree, "status", "--porcelain", "--untracked-files=all"))

    def test_a_lap_worktree_that_holds_its_own_glossary_stops_the_scheduler_before_it_claims_the_task(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        branch = self.hand_off(epic, {task: "till"})
        worktree = self.repo / ".worktrees" / f"lap-{task}"
        git(self.repo, "worktree", "add", "-q", "-b", f"lap/{task}", str(worktree), branch)
        (worktree / "GLOSSARY.md").write_text("# the worktree's own\n", encoding="utf-8")

        done = self.next_moves(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(str(worktree / "GLOSSARY.md"), done.stderr)
        self.assertEqual(("open", ""), (self.shown(task)["status"], self.shown(task).get("assignee") or ""))
        self.assertNotIn("lap.stage", self.metadata(task))


class SchedulerLapStateTests(SchedulerCase):
    def test_a_second_call_opens_each_open_lap_again_as_the_next_lap_on_the_same_slot_and_lists_them(self):
        epic = self.new_epic()
        first, second, third = (self.new_task_under(epic, "--priority", str(number)) for number in (1, 2, 3))
        self.hand_off(epic, {first: "till", second: "receipts", third: "shelf"})
        opened = self.next_printed(epic)["actions"]

        printed = self.next_printed(epic)

        self.assertEqual([{**{key: value for key, value in action.items() if key not in ("action", "answer", "findings", "app_check")},
                           "lap": 2, "stage": "build", "tries": 0} for action in opened],
                         printed["laps"])
        self.assertNotIn("lap.stage", self.metadata(third))

    def test_a_lap_left_at_the_build_with_no_worker_ends_interrupted_and_starts_again_when_next_runs_again(self):
        lap = self.open_one_lap()

        done = self.next_moves(lap.epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([("build", lap.task, str(lap.worktree), 2)],
                         [(action["action"], action["task"], action["worktree"], action["lap"])
                          for action in json.loads(done.stdout)["actions"]])
        self.assertIn(f"{lap.task} was left at the build with no worker", done.stderr)
        self.assertEqual(1, len([text for text in self.texts(lap.task) if text.startswith("Interrupted: ")]))

    def test_a_lap_left_at_the_build_starts_again_with_no_tries_when_next_runs_again(self):
        lap = self.open_one_lap()
        self.report_printed(lap.epic, lap.task, "failed")

        printed = self.next_printed(lap.epic)

        self.assertEqual([lap.task], [action["task"] for action in printed["actions"]])
        self.assertEqual([("build", 0)], [(open_lap["stage"], open_lap["tries"]) for open_lap in printed["laps"]])
        self.assertEqual(0, self.metadata(lap.task)["lap.tries"])

    def test_a_lap_that_next_opens_in_the_same_call_is_not_reported_interrupted(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})

        done = self.next_moves(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("interrupted", done.stderr)

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

        self.assertEqual([(first, 1), (other_area, 2)],
                         [(action["task"], action["slot"]) for action in printed["actions"]])
        self.assertEqual([first, other_area], [open_lap["task"] for open_lap in printed["laps"]])


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
        self.assertEqual(([], []), (self.lap_actions(after_second), after_second["laps"]))
        self.assertEqual(("closed", "closed"), (self.shown(first)["status"], self.shown(second)["status"]))
        self.assertEqual([f"Add {first}.txt", f"Add {second}.txt"],
                         git(self.repo, "log", "--reverse", "--format=%s", f"{branch}~2..{branch}").splitlines())
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

        self.assertEqual(([], []), (self.lap_actions(after_second), after_second["laps"]))
        self.assertEqual(("closed", "closed"), (self.shown(first)["status"], self.shown(second)["status"]))
        self.assertEqual(("built", "built"), (git(self.repo, "show", f"{branch}:{first}.txt"),
                                              git(self.repo, "show", f"{branch}:{second}.txt")))


class LinearEpicBranchTests(SchedulerCase):
    def test_two_laps_merged_one_after_the_other_leave_the_epic_branch_linear_with_one_commit_per_task(self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        branch = self.hand_off(epic, {first: "till", second: "receipts"})
        started = git(self.repo, "rev-parse", branch)
        for action in self.next_printed(epic)["actions"]:
            self.commit_in(Path(action["worktree"]), f"{action['task']}.txt", "built\n")

        self.build_done(epic, first)
        self.build_done(epic, second)

        self.assertEqual("", git(self.repo, "rev-list", "--merges", f"{started}..{branch}"))
        self.assertEqual(started, git(self.repo, "rev-parse", f"{branch}~2"))
        self.assertEqual([f"Add {first}.txt", f"Add {second}.txt"],
                         git(self.repo, "log", "--reverse", "--format=%s", f"{started}..{branch}").splitlines())


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
    def test_the_targeted_tests_run_on_the_lap_head_rebased_onto_the_epic_branch(self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        moved = self.commit_on_epic_branch(lap.epic_branch, "other.txt", "other lap\n")

        self.build_done(lap.epic, lap.task)

        self.assertEqual(["-k test_card"], self.runs_of(lap.task))
        self.assertEqual(moved, git(self.repo, "rev-parse", f"{lap.epic_branch}~1"))
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
        self.assertIn(f"rebased onto {lap.epic_branch}", tested["text"])

    def test_a_filter_that_repeats_the_test_target_counts_a_try_and_runs_nothing(self):
        lap = self.open_one_lap()

        printed = self.report_printed(lap.epic, lap.task, "done", "--app", "shop", "--filter", "-k test_card")

        self.assertEqual([lap.task], [action["task"] for action in printed["actions"]])
        self.assertEqual(1, self.metadata(lap.task)["lap.tries"])
        self.assertEqual([], self.runs_of(lap.task))
        self.assertTrue(any('pass "test_card"' in text for text in self.texts(lap.task)))


class MergeWorkerTests(SchedulerCase):
    def conflicting_lap(self) -> OpenLap:
        """A lap whose card.txt conflicts with newer work already on the epic branch."""
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "the lap's card\n")
        self.commit_on_epic_branch(lap.epic_branch, "card.txt", "another lap's card\n")
        return lap

    def rebase_unfinished(self, worktree: Path, epic_branch: str) -> None:
        """Starts the rebase a merge worker starts, and stops at the conflict."""
        subprocess.run(["git", "rebase", epic_branch], cwd=worktree, capture_output=True, text=True)

    def reconcile(self, worktree: Path, epic_branch: str, name: str, text: str) -> None:
        self.rebase_unfinished(worktree, epic_branch)
        (worktree / name).write_text(text, encoding="utf-8")
        git(worktree, "add", name)
        subprocess.run(["git", "-c", "core.editor=true", "rebase", "--continue"], cwd=worktree, capture_output=True,
                       text=True, env={k: v for k, v in os.environ.items() if k not in ("GIT_EDITOR", "EDITOR")},
                       check=True)

    def test_a_worktree_on_a_detached_head_with_no_rebase_is_no_lap_worktree(self):
        lap = self.conflicting_lap()
        self.build_done(lap.epic, lap.task)
        git(lap.worktree, "checkout", "-q", "--detach")

        done = subprocess.run(fixture.launch_command(LAUNCHER, [str(RULES), "lap-commands"]), capture_output=True,
                              text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS,
                              env=self.caller_env(self.home), cwd=lap.worktree)

        self.assertEqual(1, done.returncode)
        self.assertIn("is not a lap worktree", done.stderr)
        self.assertEqual("", done.stdout)

    def test_a_conflict_rebasing_the_lap_onto_the_epic_branch_calls_the_merge_worker_naming_the_files(self):
        lap = self.conflicting_lap()
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)

        printed = self.build_done(lap.epic, lap.task)

        [action] = printed["actions"]
        self.assertEqual(("merge", lap.task, str(lap.worktree), f"lap/{lap.task}"),
                         (action["action"], action["task"], action["worktree"], action["branch"]))
        self.assertIn("card.txt", action["reason"])
        self.assertIn("conflicts", action["reason"])
        self.assertEqual(lap.epic_branch, printed["branch"])
        metadata = self.metadata(lap.task)
        self.assertEqual(("merge", 0), (metadata["lap.stage"], metadata["lap.tries"]))
        self.assertEqual([], self.runs_of(lap.task))
        self.assertEqual(f"lap/{lap.task}", git(lap.worktree, "branch", "--show-current"))
        self.assertEqual(epic_head, git(self.repo, "rev-parse", lap.epic_branch))

    def test_the_call_leaves_the_task_assigned_to_jidoka_and_posts_why_under_that_actor(self):
        lap = self.conflicting_lap()

        self.build_done(lap.epic, lap.task)

        shown = self.shown(lap.task)
        self.assertEqual(("in_progress", "jidoka"), (shown["status"], shown["assignee"]))
        [called] = [comment for comment in self.comments(lap.task) if "Merge worker" in comment["text"]]
        self.assertEqual("jidoka", called["author"])
        self.assertIn("card.txt", called["text"])

    def test_targeted_tests_that_break_once_newer_work_is_merged_in_call_the_merge_worker_and_count_no_build_try(
            self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.commit_on_epic_branch(lap.epic_branch, "other.txt", "other lap\n")
        self.queue_exit_codes(lap.task, 1)

        printed = self.build_done(lap.epic, lap.task)

        [action] = printed["actions"]
        self.assertEqual(("merge", lap.task), (action["action"], action["task"]))
        self.assertIn("exit code 1", action["reason"])
        metadata = self.metadata(lap.task)
        self.assertEqual(("merge", 0), (metadata["lap.stage"], metadata["lap.tries"]))

    def test_a_reconciled_lap_passes_the_merge_gate_and_merges_as_one_commit_on_top_of_the_newer_work(self):
        lap = self.conflicting_lap()
        newer = git(self.repo, "rev-parse", lap.epic_branch)
        self.build_done(lap.epic, lap.task)
        self.reconcile(lap.worktree, lap.epic_branch, "card.txt", "both cards\n")

        printed = self.build_done(lap.epic, lap.task)

        self.assertEqual([], self.lap_actions(printed))
        shown = self.shown(lap.task)
        self.assertEqual(("closed", "merged"), (shown["status"], (shown.get("metadata") or {}).get("lap.stage")))
        self.assertEqual(newer, git(self.repo, "rev-parse", f"{lap.epic_branch}~1"))
        self.assertEqual("both cards", git(self.repo, "show", f"{lap.epic_branch}:card.txt"))
        self.assertFalse(lap.worktree.exists())

    def test_work_the_merge_worker_leaves_uncommitted_is_folded_into_the_lap_s_commit_before_the_gate(self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        newer = self.commit_on_epic_branch(lap.epic_branch, "other.txt", "other lap\n")
        self.queue_exit_codes(lap.task, 1)
        self.build_done(lap.epic, lap.task)
        self.leave_in(lap.worktree, "card.txt", "built and fixed\n")

        self.build_done(lap.epic, lap.task)

        self.assertEqual("closed", self.shown(lap.task)["status"])
        self.assertEqual(newer, git(self.repo, "rev-parse", f"{lap.epic_branch}~1"))
        self.assertEqual("built and fixed", git(self.repo, "show", f"{lap.epic_branch}:card.txt"))

    def test_the_second_failed_merge_worker_try_parks_the_task_naming_the_merge_try_cap(self):
        lap = self.conflicting_lap()
        self.build_done(lap.epic, lap.task)

        first = self.report_printed(lap.epic, lap.task, "failed")
        second = self.report_printed(lap.epic, lap.task, "failed")

        self.assertEqual([("merge", lap.task)], [(action["action"], action["task"]) for action in first["actions"]])
        self.assertEqual([], second["actions"])
        self.assertIn("the merge try cap of 2", self.assert_parked(lap, 0))

    def test_a_failed_merge_worker_s_why_reaches_the_try_comment_and_the_park_comment(self):
        lap = self.conflicting_lap()
        self.build_done(lap.epic, lap.task)

        self.report_printed(lap.epic, lap.task, "failed", "--why", "both laps rewrote the price table")
        self.report_printed(lap.epic, lap.task, "failed", "--why", "the table's columns no longer line up")

        self.assertIn("Merge try 1 of 2 failed: both laps rewrote the price table. The lap goes back to the merge "
                      "worker.", self.texts(lap.task))
        parked = self.assert_parked(lap, 0)
        self.assertIn("merge try 2 of 2 failed: the table's columns no longer line up", parked)
        self.assertNotIn("reported that the merge failed", parked)

    def test_a_merge_worker_that_leaves_the_rebase_unfinished_counts_a_try_and_the_worktree_is_back_on_the_lap_branch(
            self):
        lap = self.conflicting_lap()
        self.build_done(lap.epic, lap.task)
        self.rebase_unfinished(lap.worktree, lap.epic_branch)

        printed = self.build_done(lap.epic, lap.task)

        self.assertEqual(["merge"], [action["action"] for action in printed["actions"]])
        self.assertEqual("1", str(self.metadata(lap.task)["lap.mergetries"]))
        self.assertEqual(f"lap/{lap.task}", git(lap.worktree, "branch", "--show-current"))
        self.assertTrue(any("left the rebase unfinished" in text for text in self.texts(lap.task)))

    def test_a_merge_worker_that_reports_done_without_bringing_in_the_epic_branch_counts_a_try(self):
        lap = self.conflicting_lap()
        self.build_done(lap.epic, lap.task)

        printed = self.build_done(lap.epic, lap.task)

        self.assertEqual(["merge"], [action["action"] for action in printed["actions"]])
        self.assertEqual("1", str(self.metadata(lap.task)["lap.mergetries"]))
        self.assertTrue(any("does not hold" in text for text in self.texts(lap.task)))

    def test_a_missing_question_report_from_the_merge_worker_counts_a_merge_try_and_no_build_try(self):
        lap = self.conflicting_lap()
        self.build_done(lap.epic, lap.task)

        printed = self.report_printed(lap.epic, lap.task, "question")

        self.assertEqual(["merge"], [action["action"] for action in printed["actions"]])
        metadata = self.metadata(lap.task)
        self.assertEqual(("merge", "1", 0), (metadata["lap.stage"], str(metadata["lap.mergetries"]),
                                             metadata["lap.tries"]))
        self.assertTrue(any("the question could not be posted" in text for text in self.texts(lap.task)))

    def test_red_targeted_tests_after_the_merge_worker_count_a_merge_try_and_the_second_parks_the_task(self):
        lap = self.conflicting_lap()
        self.build_done(lap.epic, lap.task)
        self.reconcile(lap.worktree, lap.epic_branch, "card.txt", "both cards\n")
        self.queue_exit_codes(lap.task, 1, 1)

        first = self.build_done(lap.epic, lap.task)
        second = self.build_done(lap.epic, lap.task)

        self.assertEqual(["merge"], [action["action"] for action in first["actions"]])
        self.assertEqual([], second["actions"])
        self.assertIn("the merge try cap of 2", self.assert_parked(lap, 0))

    def test_a_cut_off_merge_worker_goes_back_to_the_merge_stage_and_counts_no_try(self):
        lap = self.conflicting_lap()
        self.build_done(lap.epic, lap.task)

        printed = self.report_printed(lap.epic, lap.task, "cut off")

        self.assertEqual(["merge"], [action["action"] for action in printed["actions"]])
        metadata = self.metadata(lap.task)
        self.assertEqual(("merge", 0, "0"), (metadata["lap.stage"], metadata["lap.tries"],
                                             str(metadata.get("lap.mergetries", 0))))

    def test_a_manager_restarting_parks_a_lap_left_at_the_merge_stage_whose_new_lap_conflicts_with_the_epic_branch(
            self):
        lap = self.conflicting_lap()
        self.build_done(lap.epic, lap.task)

        printed = self.next_printed(lap.epic)

        self.assertEqual([], printed["actions"])
        self.assertEqual(2, self.metadata(lap.task)["lap.number"])
        self.assertIn("conflicts with", self.assert_parked(lap, 0))
        self.assertIn("card.txt", self.assert_parked(lap, 0))

    def test_two_laps_that_touch_the_same_function_both_merge_the_second_after_a_merge_worker_reconciles_it(self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        branch = self.hand_off(epic, {first: "till", second: "receipts"})
        worktrees = {action["task"]: Path(action["worktree"]) for action in self.next_printed(epic)["actions"]}
        self.commit_in(worktrees[first], "card.py", "def total():\n    return 1\n")
        self.commit_in(worktrees[second], "card.py", "def total():\n    return 2\n")

        self.build_done(epic, first)
        called = self.build_done(epic, second)
        self.reconcile(worktrees[second], branch, "card.py", "def total():\n    return 1 + 2\n")
        merged = self.build_done(epic, second)

        self.assertEqual(["merge"], [action["action"] for action in called["actions"]])
        self.assertEqual([], self.lap_actions(merged))
        self.assertEqual(("closed", "closed"), (self.shown(first)["status"], self.shown(second)["status"]))
        self.assertEqual("def total():\n    return 1 + 2", git(self.repo, "show", f"{branch}:card.py"))


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
        self.assertEqual([second], [action["task"] for action in self.next_printed(epic)["actions"]])
        self.assertEqual("parked", self.metadata(first)["lap.stage"])


class QuestionTests(SchedulerCase):
    FOUND = "The till already rounds to five cents and the task does not say whether receipts should."
    OPTIONS = [{"name": "round receipts too", "confidence": 60}, {"name": "print exact cents", "confidence": 35}]

    def leave_question(self, lap: OpenLap, **changes: object) -> None:
        report = {"found": self.FOUND, "options": self.OPTIONS, "recommended": "round receipts too", **changes}
        self.leave_in(lap.worktree, ".scratch/question.json", json.dumps(report))

    def test_a_question_report_parks_its_task_with_the_human_label_a_comment_and_the_options_in_metadata(self):
        lap = self.open_one_lap()
        self.leave_in(lap.worktree, "card.txt", "half built\n")
        self.leave_question(lap)

        printed = self.report_printed(lap.epic, lap.task, "question")

        self.assertEqual(([], []), (printed["actions"], printed["laps"]))
        self.assertEqual(("open", "", ["human"]), (self.shown(lap.task)["status"],
                                                   self.shown(lap.task).get("assignee") or "",
                                                   self.shown(lap.task).get("labels")))
        metadata = self.metadata(lap.task)
        self.assertEqual(("parked", 0, "round receipts too"),
                         (metadata["lap.stage"], metadata["lap.tries"], metadata["question.recommended"]))
        self.assertEqual(self.OPTIONS, json.loads(metadata["question.options"]))
        self.assertEqual("half built\n", (lap.worktree / "card.txt").read_text(encoding="utf-8"))
        self.assertIn(f"lap/{lap.task}", git(self.repo, "branch", "--list"))
        self.assertFalse((lap.worktree / ".scratch" / "question.json").exists())

    def test_the_question_comment_states_what_was_found_every_option_with_its_confidence_and_the_recommendation(
            self):
        lap = self.open_one_lap()
        self.leave_question(lap)

        self.report_printed(lap.epic, lap.task, "question")

        [question] = [comment for comment in self.comments(lap.task) if str(comment["text"]).startswith("Question: ")]
        self.assertEqual("jidoka", question["author"])
        text = str(question["text"])
        self.assertIn(self.FOUND, text)
        self.assertIn("- round receipts too (60%)", text)
        self.assertIn("- print exact cents (35%)", text)
        self.assertIn("Recommended: round receipts too (60%).", text)

    def test_the_question_a_lap_asks_gets_a_page_in_the_jidoka_home_that_its_comment_links(self):
        lap = self.open_one_lap()
        self.leave_question(lap)

        self.report_printed(lap.epic, lap.task, "question")

        [page] = (self.home / "pages").rglob(f"question-{lap.task}.html")
        html = page.read_text(encoding="utf-8")
        self.assertIn(self.FOUND, html)
        self.assertEqual(2, html.count('<article class="option'))
        self.assertEqual(1, html.count('data-jidoka-slot="answer-panel"'))
        [question] = [comment for comment in self.comments(lap.task) if str(comment["text"]).startswith("Question: ")]
        self.assertIn(f"Page: {page.as_uri()}", str(question["text"]))
        self.assertEqual("", git(self.repo, "status", "--porcelain", "--", ".", ":!.worktrees"))

    def test_the_lap_that_asked_frees_its_slot_and_area_for_the_next_task_while_the_other_lap_keeps_running(self):
        epic = self.new_epic()
        asking, waiting, other = (self.new_task_under(epic, "--priority", str(number)) for number in (1, 2, 3))
        self.hand_off(epic, {asking: "till", waiting: "till", other: "receipts"})
        opened = {action["task"]: action for action in self.next_printed(epic)["actions"]}
        self.assertEqual([asking, other], sorted(opened))
        self.leave_in(Path(opened[asking]["worktree"]), ".scratch/question.json",
                      json.dumps({"found": self.FOUND, "options": self.OPTIONS, "recommended": "print exact cents"}))

        printed = self.report_printed(epic, asking, "question")

        self.assertEqual([(waiting, opened[asking]["slot"])],
                         [(action["task"], action["slot"]) for action in printed["actions"]])
        self.assertEqual([(1, waiting), (2, other)], [(open_lap["slot"], open_lap["task"])
                                                      for open_lap in printed["laps"]])
        self.assertEqual("build", self.metadata(other)["lap.stage"])
        self.assertEqual("parked", self.metadata(asking)["lap.stage"])

    def test_a_missing_question_report_counts_a_try_and_sends_the_lap_back_to_the_build(self):
        lap = self.open_one_lap()

        printed = self.report_printed(lap.epic, lap.task, "question")

        self.assertEqual([lap.task], [action["task"] for action in printed["actions"]])
        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))
        self.assertTrue(any("the question could not be posted" in text for text in self.texts(lap.task)))
        self.assertNotIn("human", self.shown(lap.task).get("labels") or [])

    def test_a_question_report_whose_recommendation_is_not_one_of_its_options_counts_a_try(self):
        lap = self.open_one_lap()
        self.leave_question(lap, recommended="something else")

        self.report_printed(lap.epic, lap.task, "question")

        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))
        self.assertTrue(any("recommended must be the name of one option" in text for text in self.texts(lap.task)))

    def test_an_option_without_a_confidence_in_percent_is_not_posted(self):
        lap = self.open_one_lap()
        self.leave_question(lap, options=[{"name": "round receipts too", "confidence": 160},
                                          {"name": "print exact cents"}])

        self.report_printed(lap.epic, lap.task, "question")

        self.assertEqual("build", self.metadata(lap.task)["lap.stage"])
        self.assertEqual([], [text for text in self.texts(lap.task) if text.startswith("Question: ")])

    def human_comments(self, task: str, text: str) -> None:
        fixture.run_with_env([self.bd, "comment", task, text], self.repo, {**os.environ, "BEADS_ACTOR": JEFF})

    def take_the_human_label_off(self, task: str) -> None:
        fixture.run([self.bd, "label", "remove", task, "human"], self.repo)

    def ask_and_park(self) -> OpenLap:
        lap = self.open_one_lap()
        self.leave_question(lap)
        self.report_printed(lap.epic, lap.task, "question")
        return lap

    def test_unparking_with_a_comment_since_the_question_starts_the_next_lap_carrying_the_comment_as_the_answer(
            self):
        lap = self.ask_and_park()
        self.human_comments(lap.task, "Round receipts too, to the nearest five cents.")
        self.take_the_human_label_off(lap.task)

        printed = self.next_printed(lap.epic)

        [action] = printed["actions"]
        self.assertEqual((lap.task, {"source": "comment", "text": "Round receipts too, to the nearest five cents."}),
                         (action["task"], action["answer"]))

    def test_every_comment_since_the_question_is_part_of_the_answer_and_no_earlier_comment_is(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        self.human_comments(task, "Before the question.")
        [action] = self.next_printed(epic)["actions"]
        self.leave_question(OpenLap(epic, task, "", Path(action["worktree"])))
        self.report_printed(epic, task, "question")
        self.human_comments(task, "Print exact cents.")
        self.human_comments(task, "And say so on the receipt.")
        self.take_the_human_label_off(task)

        [again] = self.next_printed(epic)["actions"]

        self.assertEqual({"source": "comment", "text": "Print exact cents.\n\nAnd say so on the receipt."},
                         again["answer"])

    def test_unparking_with_no_comment_since_the_question_takes_the_recommendation(self):
        lap = self.ask_and_park()
        self.take_the_human_label_off(lap.task)

        [action] = self.next_printed(lap.epic)["actions"]

        self.assertEqual((lap.task, {"source": "recommendation", "text": "round receipts too"}),
                         (action["task"], action["answer"]))

    def test_unparking_a_permission_question_puts_the_denied_calls_pattern_on_the_list_the_answer_names(self):
        lap = self.open_one_lap()
        options = [{"name": name, "confidence": 30} for name in ("epic", "repo", "built-in")]
        self.leave_question(lap, call="cd till && make lint --fix", pattern="make lint", options=options,
                            recommended="epic")
        self.report_printed(lap.epic, lap.task, "question")
        self.human_comments(lap.task, "The epic's list.")
        self.take_the_human_label_off(lap.task)

        [action] = self.next_printed(lap.epic)["actions"]

        self.assertEqual({"source": "comment", "text": "The epic's list."}, action["answer"])
        done = subprocess.run(fixture.launch_command(LAUNCHER, [str(RULES), "show", lap.epic]), capture_output=True,
                              text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS,
                              env=self.caller_env(self.home), cwd=self.repo)
        self.assertEqual(["make lint"], json.loads(done.stdout)["settings"]["extra_commands"])

    def test_a_comment_that_asks_back_gets_a_reply_from_the_stage_which_parks_again_and_the_next_unpark_answers_the_reply(
            self):
        lap = self.ask_and_park()
        self.human_comments(lap.task, "Why round at all?")
        self.take_the_human_label_off(lap.task)
        [asked_back] = self.next_printed(lap.epic)["actions"]
        self.assertEqual({"source": "comment", "text": "Why round at all?"}, asked_back["answer"])
        reply = "The till rounds to five cents because the coin tray holds no pennies."
        self.leave_question(lap, found=reply, options=[{"name": "round receipts too", "confidence": 80},
                                                      {"name": "print exact cents", "confidence": 15}])

        parked = self.report_printed(lap.epic, lap.task, "question")

        self.assertEqual(([], ["human"], "parked"),
                         (parked["actions"], self.shown(lap.task).get("labels"), self.metadata(lap.task)["lap.stage"]))
        questions = [text for text in self.texts(lap.task) if text.startswith("Question: ")]
        self.assertEqual(2, len(questions))
        self.assertIn(reply, questions[1])
        self.take_the_human_label_off(lap.task)

        [after_reply] = self.next_printed(lap.epic)["actions"]

        self.assertEqual({"source": "recommendation", "text": "round receipts too"}, after_reply["answer"])

    def test_the_next_lap_starts_in_the_same_worktree_on_the_same_branch_with_its_commits_and_uncommitted_work(
            self):
        lap = self.open_one_lap()
        committed = self.commit_in(lap.worktree, "till.txt", "rounded\n")
        self.leave_in(lap.worktree, "card.txt", "half built\n")
        self.leave_question(lap)
        self.report_printed(lap.epic, lap.task, "question")
        self.take_the_human_label_off(lap.task)

        [action] = self.next_printed(lap.epic)["actions"]

        self.assertEqual((str(lap.worktree), f"lap/{lap.task}"), (action["worktree"], action["branch"]))
        self.assertEqual(committed, git(lap.worktree, "rev-parse", "HEAD"))
        self.assertEqual("half built\n", (lap.worktree / "card.txt").read_text(encoding="utf-8"))
        self.assertEqual(("in_progress", "jidoka"), (self.shown(lap.task)["status"], self.shown(lap.task)["assignee"]))

    def test_the_answer_stays_with_the_lap_through_a_failed_try_and_a_restart(self):
        lap = self.ask_and_park()
        self.human_comments(lap.task, "Round receipts too.")
        self.take_the_human_label_off(lap.task)
        self.next_printed(lap.epic)

        [after_failure] = self.report_printed(lap.epic, lap.task, "failed")["actions"]
        [after_restart] = self.next_printed(lap.epic)["actions"]

        self.assertEqual({"source": "comment", "text": "Round receipts too."}, after_failure["answer"])
        self.assertEqual(after_failure["answer"], after_restart["answer"])

    def test_a_task_parked_by_its_tries_gets_no_answer_when_the_human_label_comes_off(self):
        lap = self.open_one_lap()
        for _ in range(3):
            self.report_printed(lap.epic, lap.task, "failed")
        self.human_comments(lap.task, "Try the other approach.")
        self.take_the_human_label_off(lap.task)

        [action] = self.next_printed(lap.epic)["actions"]

        self.assertIsNone(action["answer"])

    def test_a_lap_opened_after_three_failed_build_tries_is_lap_two_in_the_parked_laps_worktree_and_branch(self):
        lap = self.open_one_lap()
        committed = self.commit_in(lap.worktree, "till.txt", "rounded\n")
        for _ in range(3):
            self.report_printed(lap.epic, lap.task, "failed")
        self.take_the_human_label_off(lap.task)

        printed = self.next_printed(lap.epic)

        [action] = printed["actions"]
        self.assertEqual((lap.task, 2, str(lap.worktree), f"lap/{lap.task}"),
                         (action["task"], action["lap"], action["worktree"], action["branch"]))
        self.assertEqual([2], [open_lap["lap"] for open_lap in printed["laps"]])
        self.assertEqual("2", str(self.metadata(lap.task)["lap.number"]))
        self.assertEqual(committed, git(lap.worktree, "rev-parse", "HEAD"))

    def test_a_lap_opened_after_the_human_label_came_off_starts_with_no_tries_so_one_failure_does_not_park_it(self):
        lap = self.open_one_lap()
        for _ in range(3):
            self.report_printed(lap.epic, lap.task, "failed")
        self.take_the_human_label_off(lap.task)

        [opened] = self.next_printed(lap.epic)["laps"]
        after_failure = self.report_printed(lap.epic, lap.task, "failed")

        self.assertEqual((0, "build"), (opened["tries"], opened["stage"]))
        self.assertEqual([(lap.task, 2, 1)], [(open_lap["task"], open_lap["lap"], open_lap["tries"])
                                              for open_lap in after_failure["laps"]])

    def test_each_unpark_gives_the_next_lap_number(self):
        lap = self.open_one_lap()
        for _ in range(2):
            for _ in range(3):
                self.report_printed(lap.epic, lap.task, "failed")
            self.take_the_human_label_off(lap.task)
            [action] = self.next_printed(lap.epic)["actions"]

        self.assertEqual(3, action["lap"])

    def test_a_lap_that_never_asked_a_question_carries_no_answer(self):
        lap = self.open_one_lap()

        [action] = self.next_printed(lap.epic)["actions"]

        self.assertIsNone(action["answer"])


class BuildNotesTests(SchedulerCase):
    def leave_notes(self, lap: OpenLap, notes: object) -> None:
        self.leave_in(lap.worktree, ".scratch/build-notes.json", json.dumps(notes))

    def texts_of(self, task: str) -> list[str]:
        return [str(comment["text"]) for comment in self.comments(task)]

    def test_a_done_build_posts_each_assumption_and_public_api_change_as_a_comment_by_jidoka(self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.leave_notes(lap, {"assumptions": ["A card number is 16 digits", "Amounts stay in cents"],
                               "public_api_changes": ["Card.read takes a Reader as its second argument"]})

        self.build_done(lap.epic, lap.task)

        posted = [comment for comment in self.comments(lap.task)
                  if str(comment["text"]).startswith(("assumption:", "public API change:"))]
        self.assertEqual(["assumption: A card number is 16 digits", "assumption: Amounts stay in cents",
                          "public API change: Card.read takes a Reader as its second argument"],
                         [comment["text"] for comment in posted])
        self.assertEqual({"jidoka"}, {comment["author"] for comment in posted})
        self.assertFalse((lap.worktree / ".scratch" / "build-notes.json").exists())

    def test_a_notes_report_that_cannot_be_used_counts_a_try_and_posts_nothing(self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.leave_notes(lap, {"assumptions": ["A card number is 16 digits", ""]})

        self.build_done(lap.epic, lap.task)

        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))
        self.assertEqual([], [text for text in self.texts_of(lap.task) if text.startswith("assumption:")])
        self.assertTrue(any("build-notes.json" in text for text in self.texts_of(lap.task)))

    def test_a_build_that_does_not_end_done_posts_no_note(self):
        lap = self.open_one_lap()
        self.leave_notes(lap, {"assumptions": ["A card number is 16 digits"]})

        self.report_printed(lap.epic, lap.task, "failed", "--why", "the reader is missing")

        self.assertEqual([], [text for text in self.texts_of(lap.task) if text.startswith("assumption:")])


class DiscoveredWorkTests(SchedulerCase):
    def finding(self, title: str, placement: str) -> dict:
        return {"title": title, "description": f"Seen while building the card: {title}", "placement": placement}

    def leave_findings(self, lap: OpenLap, *findings: dict) -> None:
        self.leave_in(lap.worktree, ".scratch/discovered.json", json.dumps(list(findings)))

    def block_on(self, lap: OpenLap, title: str) -> tuple[str, dict]:
        """Ends the lap blocked on a new task, and returns that task's id with what the report printed."""
        self.leave_findings(lap, self.finding(title, "blocks"))
        printed = self.report_printed(lap.epic, lap.task, "blocked")
        return self.children_of(lap.epic)[title], printed

    def test_a_finding_the_epic_cannot_be_accepted_without_is_filed_in_the_epic_linked_discovered_from_the_task(
            self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.leave_findings(lap, self.finding("Round the receipt total", "epic"))

        printed = self.build_done(lap.epic, lap.task)

        filed = self.children_of(lap.epic)["Round the receipt total"]
        self.assertIn(("discovered-from", lap.task), self.links_of(filed))
        metadata = self.metadata(filed)
        self.assertEqual(("till", "simple"), (metadata["lap.area"], metadata["lap.track"]))
        self.assertEqual("closed", self.shown(lap.task)["status"])
        self.assertEqual([filed], [action["task"] for action in printed["actions"]])
        self.assertFalse((lap.worktree / ".scratch" / "discovered.json").exists())

    def test_a_finding_that_acceptance_does_not_need_is_filed_outside_the_epic_linked_discovered_from_the_task(
            self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.leave_findings(lap, self.finding("Sweep the till", "outside"))

        self.build_done(lap.epic, lap.task)

        outside = self.bead_titled("Sweep the till")
        shown = self.shown(outside)
        self.assertEqual((None, {("discovered-from", lap.task)}), (shown.get("parent"), self.links_of(outside)))
        self.assertNotIn("Sweep the till", self.children_of(lap.epic))
        self.assertNotIn("lap.area", self.metadata(outside))

    def test_a_finding_that_blocks_the_task_on_a_build_reported_done_files_nothing_and_counts_a_try(self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.leave_findings(lap, self.finding("Round the receipt total", "blocks"))

        self.build_done(lap.epic, lap.task)

        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))
        self.assertEqual({lap.task}, set(self.children_of(lap.epic).values()))

    def test_a_lap_that_needs_its_discovered_task_ends_blocked_with_no_human_label_and_waits_on_the_new_task(self):
        lap = self.open_one_lap()
        self.leave_in(lap.worktree, "card.txt", "half built\n")

        new_task, printed = self.block_on(lap, "Round the receipt total")

        shown = self.shown(lap.task)
        self.assertEqual(("open", "", None), (shown["status"], shown.get("assignee") or "", shown.get("labels")))
        self.assertEqual("blocked", shown["metadata"]["lap.stage"])
        self.assertEqual({("blocks", new_task), ("parent-child", lap.epic)}, self.links_of(lap.task))
        self.assertIn(("discovered-from", lap.task), self.links_of(new_task))
        self.assertEqual("till", self.metadata(new_task)["lap.area"])
        self.assertEqual("half built\n", (lap.worktree / "card.txt").read_text(encoding="utf-8"))
        self.assertIn(f"lap/{lap.task}", git(self.repo, "branch", "--list"))
        [blocked] = [comment for comment in self.comments(lap.task) if str(comment["text"]).startswith("Blocked: ")]
        self.assertEqual("jidoka", blocked["author"])
        self.assertIn(new_task, str(blocked["text"]))
        self.assertEqual([new_task], [action["task"] for action in printed["actions"]])
        self.assertEqual([new_task], [open_lap["task"] for open_lap in printed["laps"]])

    def status_of(self, worktree: Path) -> list[str]:
        return fixture.run(["git", "status", "--porcelain", "--untracked-files=all"], worktree).splitlines()

    def block_until_the_new_task_merges(self, lap: OpenLap, new_task_file: str) -> tuple[str, dict]:
        """Ends the lap blocked on a new task whose build commits the file and merges, and returns the epic branch's
        head after the merge with what the merge's report printed."""
        new_task, printed = self.block_on(lap, "Round the receipt total")
        [new_action] = printed["actions"]
        self.assertEqual([new_task], [open_lap["task"] for open_lap in self.next_printed(lap.epic)["laps"]])
        self.commit_in(Path(new_action["worktree"]), new_task_file, "rounded\n")
        merged = self.build_done(lap.epic, new_task)
        return git(self.repo, "rev-parse", lap.epic_branch), merged

    def test_the_blocked_task_gets_its_next_lap_in_the_same_worktree_only_after_the_new_task_merges(self):
        lap = self.open_one_lap()
        built = self.commit_in(lap.worktree, "card.txt", "half built\n")

        epic_head, merged = self.block_until_the_new_task_merges(lap, "rounding.txt")

        [again] = merged["actions"]
        self.assertEqual(("build", lap.task, lap.worktree), (again["action"], again["task"], Path(again["worktree"])))
        self.assertIsNone(again["answer"])
        self.assertEqual(epic_head, git(lap.worktree, "rev-parse", "HEAD~1"))
        self.assertNotEqual(built, git(lap.worktree, "rev-parse", "HEAD"))
        self.assertEqual(("Add card.txt", ["card.txt"], "half built"),
                         (git(lap.worktree, "log", "-1", "--format=%s"), self.files_of(f"lap/{lap.task}"),
                          git(lap.worktree, "show", "HEAD:card.txt")))
        self.assertEqual("rounded\n", (lap.worktree / "rounding.txt").read_text(encoding="utf-8"))
        self.assertEqual(("in_progress", "build"), (self.shown(lap.task)["status"],
                                                    self.metadata(lap.task)["lap.stage"]))

    def test_a_task_that_reopens_after_blocked_keeps_its_uncommitted_work_on_top_of_the_epic_head(self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "half built\n")
        self.leave_in(lap.worktree, "card.txt", "more built\n")
        self.leave_in(lap.worktree, "reader.txt", "started\n")

        epic_head, _ = self.block_until_the_new_task_merges(lap, "rounding.txt")

        self.assertEqual(epic_head, git(lap.worktree, "rev-parse", "HEAD~1"))
        self.assertEqual("Add card.txt", git(lap.worktree, "log", "-1", "--format=%s"))
        self.assertEqual(("more built\n", "started\n"),
                         ((lap.worktree / "card.txt").read_text(encoding="utf-8"),
                          (lap.worktree / "reader.txt").read_text(encoding="utf-8")))
        self.assertEqual([" M card.txt", "?? reader.txt"], self.status_of(lap.worktree))

    def test_a_task_whose_work_conflicts_with_the_epic_branch_when_it_reopens_parks_naming_the_files(self):
        lap = self.open_one_lap()
        built = self.commit_in(lap.worktree, "card.txt", "half built\n")
        self.leave_in(lap.worktree, "reader.txt", "started\n")

        _, merged = self.block_until_the_new_task_merges(lap, "card.txt")

        self.assertEqual([], merged["actions"])
        why = self.assert_parked(lap, 0)
        self.assertIn("card.txt", why)
        self.assertIn(f"lap/{lap.task}", why)
        self.assertEqual((f"lap/{lap.task}", built),
                         (git(lap.worktree, "branch", "--show-current"), git(lap.worktree, "rev-parse", "HEAD")))
        self.assertEqual(["?? reader.txt"], self.status_of(lap.worktree))

    def test_a_blocked_task_opens_no_lap_while_the_task_it_waits_on_is_open(self):
        epic = self.new_epic()
        task, other = self.new_task_under(epic, "--priority", "1"), self.new_task_under(epic, "--priority", "2")
        self.hand_off(epic, {task: "till", other: "receipts"})
        opened = {action["task"]: action for action in self.next_printed(epic)["actions"]}
        lap = OpenLap(epic, task, "", Path(opened[task]["worktree"]))
        new_task, _ = self.block_on(lap, "Round the receipt total")

        printed = self.next_printed(epic)

        self.assertEqual({new_task: "build", other: "build"},
                         {open_lap["task"]: open_lap["stage"] for open_lap in printed["laps"]})
        self.assertNotIn(task, [open_lap["task"] for open_lap in printed["laps"]])

    def two_tasks_with_a_lap_on_the_first(self) -> tuple[OpenLap, str, str]:
        """An epic with two tasks and a lap open on the first; returns the lap, the second task and its title."""
        epic = self.new_epic()
        task, sibling = self.new_task_under(epic, "--priority", "1"), self.new_task_under(epic, "--priority", "2")
        self.hand_off(epic, {task: "till", sibling: "receipts"})
        opened = {action["task"]: action for action in self.next_printed(epic)["actions"]}
        title = str(self.shown(sibling)["title"])
        return OpenLap(epic, task, "", Path(opened[task]["worktree"])), sibling, title

    def naming(self, task: str, title: str) -> dict:
        return {**self.finding(title, "blocks"), "task": task}

    def test_a_blocking_finding_that_names_a_sibling_task_waits_on_it_and_files_nothing(self):
        lap, sibling, title = self.two_tasks_with_a_lap_on_the_first()
        before = self.children_of(lap.epic)
        self.leave_findings(lap, self.naming(sibling, title))

        printed = self.report_printed(lap.epic, lap.task, "blocked")

        self.assertEqual(before, self.children_of(lap.epic))
        self.assertEqual({("blocks", sibling), ("parent-child", lap.epic)}, self.links_of(lap.task))
        self.assertEqual("blocked", self.metadata(lap.task)["lap.stage"])
        [blocked] = [comment for comment in self.comments(lap.task) if str(comment["text"]).startswith("Blocked: ")]
        self.assertIn(sibling, str(blocked["text"]))
        self.assertNotIn(lap.task, [open_lap["task"] for open_lap in printed["laps"]])

    def test_a_blocking_finding_whose_title_is_a_sibling_task_but_names_no_task_is_filed_as_a_new_task(self):
        lap, sibling, title = self.two_tasks_with_a_lap_on_the_first()
        self.leave_findings(lap, self.finding(title, "blocks"))

        self.report_printed(lap.epic, lap.task, "blocked")

        [(_, waited_on)] = [link for link in self.links_of(lap.task) if link[0] == "blocks"]
        self.assertNotEqual(sibling, waited_on)

    def test_a_finding_that_names_a_task_the_epic_does_not_hold_counts_a_try_and_files_nothing(self):
        lap, _, title = self.two_tasks_with_a_lap_on_the_first()
        before = self.children_of(lap.epic)
        self.leave_findings(lap, self.naming("no-such-task", title))

        self.report_printed(lap.epic, lap.task, "blocked")

        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))
        self.assertEqual(before, self.children_of(lap.epic))
        self.assertTrue(any("no-such-task" in text for text in self.texts(lap.task)))

    def test_a_finding_that_names_the_task_it_was_found_in_counts_a_try(self):
        lap, _, title = self.two_tasks_with_a_lap_on_the_first()
        self.leave_findings(lap, self.naming(lap.task, title))

        self.report_printed(lap.epic, lap.task, "blocked")

        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))

    def test_a_finding_that_names_a_task_without_blocking_is_refused_and_counts_a_try(self):
        lap, sibling, title = self.two_tasks_with_a_lap_on_the_first()
        self.leave_findings(lap, {**self.finding(title, "outside"), "task": sibling})

        self.report_printed(lap.epic, lap.task, "blocked")

        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))

    def test_a_blocking_finding_that_names_no_task_is_filed_while_another_waits_on_the_sibling(self):
        lap, sibling, title = self.two_tasks_with_a_lap_on_the_first()
        self.leave_findings(lap, self.naming(sibling, title), self.finding("Round the receipt total", "blocks"))

        self.report_printed(lap.epic, lap.task, "blocked")

        new_task = self.children_of(lap.epic)["Round the receipt total"]
        self.assertEqual({("blocks", sibling), ("blocks", new_task), ("parent-child", lap.epic)},
                         self.links_of(lap.task))

    def test_a_blocked_report_naming_no_blocking_finding_counts_a_try_and_files_nothing(self):
        lap = self.open_one_lap()
        self.leave_findings(lap, self.finding("Sweep the till", "outside"))

        self.report_printed(lap.epic, lap.task, "blocked")

        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))
        self.assertTrue(any("placement is blocks" in text for text in self.texts(lap.task)))
        self.assertEqual({lap.task}, set(self.children_of(lap.epic).values()))

    def test_a_blocked_report_with_no_discovered_work_report_counts_a_try(self):
        lap = self.open_one_lap()

        self.report_printed(lap.epic, lap.task, "blocked")

        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))

    def test_a_finding_with_a_placement_outside_the_fixed_set_is_not_filed(self):
        lap = self.open_one_lap()
        self.leave_findings(lap, self.finding("Round the receipt total", "someday"))

        self.report_printed(lap.epic, lap.task, "blocked")

        self.assertEqual("build", self.metadata(lap.task)["lap.stage"])
        self.assertEqual({lap.task}, set(self.children_of(lap.epic).values()))

    def test_the_lap_after_a_block_carries_no_answer_from_a_question_the_human_answered_earlier(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        lap = OpenLap(epic, task, "", Path(action["worktree"]))
        self.leave_in(lap.worktree, ".scratch/question.json", json.dumps(
            {"found": "Which rounding?", "options": [{"name": "five cents", "confidence": 60},
                                                      {"name": "exact", "confidence": 30}],
             "recommended": "five cents"}))
        self.report_printed(epic, task, "question")
        fixture.run([self.bd, "label", "remove", task, "human"], self.repo)
        self.next_printed(epic)
        new_task, printed = self.block_on(lap, "Round the receipt total")
        [new_action] = printed["actions"]
        self.commit_in(Path(new_action["worktree"]), "rounding.txt", "rounded\n")

        [again] = self.build_done(epic, new_task)["actions"]

        self.assertEqual((task, None), (again["task"], again["answer"]))


class TaskAddedToAHeldEpicTests(SchedulerCase):
    def test_a_task_the_human_adds_to_a_held_epic_gets_a_lap_once_the_task_it_waits_on_merges(self):
        epic = self.new_epic()
        first = self.new_task_under(epic)
        self.hand_off(epic, {first: "till"})
        [action] = self.next_printed(epic)["actions"]
        added = self.new_task_under(epic, "--deps", first)
        fixture.run([self.bd, "update", added, "--set-metadata", "lap.area=receipts"], self.repo)
        self.assertEqual([first], [open_lap["task"] for open_lap in self.next_printed(epic)["laps"]])
        self.commit_in(Path(action["worktree"]), "card.txt", "built\n")

        printed = self.build_done(epic, first)

        self.assertEqual([("build", added)], [(opened["action"], opened["task"]) for opened in printed["actions"]])


class CapTests(SchedulerCase):
    def age_stage(self, task: str, seconds: int) -> None:
        """Makes the task's stage look like it started the given seconds ago."""
        fixture.run([self.bd, "update", task, "--set-metadata", f"lap.started={int(time.time()) - seconds}"],
                    self.repo)

    def test_the_third_failed_build_parks_the_task_with_a_comment_naming_the_try_cap(self):
        lap = self.open_one_lap()

        for _ in range(3):
            self.report_printed(lap.epic, lap.task, "failed")

        self.assertIn("the try cap of 3", self.assert_parked(lap, 3))

    def test_the_second_send_back_from_the_checks_parks_the_task_with_a_comment_naming_the_send_back_cap(self):
        lap = self.open_one_lap()

        first = self.report_printed(lap.epic, lap.task, "send back")
        second = self.report_printed(lap.epic, lap.task, "send back")

        self.assertEqual([lap.task], [action["task"] for action in first["actions"]])
        self.assertEqual(0, self.metadata(lap.task)["lap.tries"])
        self.assertEqual([], second["actions"])
        self.assertIn("the send-back cap of 2", self.assert_parked(lap, 0))

    def test_a_send_back_does_not_count_as_a_failed_build_try(self):
        lap = self.open_one_lap()
        self.report_printed(lap.epic, lap.task, "send back")

        self.report_printed(lap.epic, lap.task, "failed")
        self.report_printed(lap.epic, lap.task, "failed")

        self.assertEqual(("build", 2), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))

    def test_the_third_cutoff_of_the_build_parks_the_task_with_a_comment_naming_the_cutoff_cap(self):
        lap = self.open_one_lap()

        first = self.report_printed(lap.epic, lap.task, "cut off")
        second = self.report_printed(lap.epic, lap.task, "cut off")
        third = self.report_printed(lap.epic, lap.task, "cut off")

        self.assertEqual(([lap.task], [lap.task], []),
                         tuple([action["task"] for action in printed["actions"]] for printed in (first, second, third)))
        self.assertIn("the cutoff cap of 3", self.assert_parked(lap, 0))

    def test_a_manager_restarting_is_the_humans_stop_and_counts_no_cutoff(self):
        lap = self.open_one_lap()

        for _ in range(4):
            printed = self.next_printed(lap.epic)

        self.assertEqual([lap.task], [action["task"] for action in printed["actions"]])
        self.assertEqual("build", self.metadata(lap.task)["lap.stage"])

    def test_a_build_reported_past_its_wall_clock_of_60_minutes_ends_cut_off_and_counts_no_try(self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.age_stage(lap.task, 61 * 60)

        printed = self.build_done(lap.epic, lap.task)

        self.assertEqual([lap.task], [action["task"] for action in printed["actions"]])
        metadata = self.metadata(lap.task)
        self.assertEqual(("build", 0), (metadata["lap.stage"], metadata["lap.tries"]))
        self.assertEqual("in_progress", self.shown(lap.task)["status"])
        self.assertTrue(any("wall clock of 60 minutes" in text for text in self.texts(lap.task)))

    def test_the_rerun_after_a_wall_clock_cutoff_gets_a_fresh_wall_clock(self):
        lap = self.open_one_lap()
        self.age_stage(lap.task, 61 * 60)
        self.report_printed(lap.epic, lap.task, "failed")

        printed = self.report_printed(lap.epic, lap.task, "failed")

        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))
        self.assertEqual([lap.task], [action["task"] for action in printed["actions"]])

    def test_a_build_reported_inside_its_wall_clock_is_taken_as_reported(self):
        lap = self.open_one_lap()
        self.age_stage(lap.task, 59 * 60)

        self.report_printed(lap.epic, lap.task, "failed")

        self.assertEqual(1, self.metadata(lap.task)["lap.tries"])

    def test_a_task_that_parks_leaves_the_other_laps_running(self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        self.hand_off(epic, {first: "till", second: "receipts"})
        [first_action, second_action] = self.next_printed(epic)["actions"]
        self.commit_in(Path(second_action["worktree"]), "card.txt", "built\n")

        for _ in range(3):
            parked = self.report_printed(epic, first, "failed")
        merged = self.build_done(epic, second)

        self.assertEqual([second], [open_lap["task"] for open_lap in parked["laps"]])
        self.assertEqual(("parked", "closed"), (self.metadata(first)["lap.stage"], self.shown(second)["status"]))
        self.assertEqual([], merged["laps"])


class BrakeTests(SchedulerCase):
    def fail_three_times(self, epic: str, task: str) -> dict:
        for _ in range(3):
            printed = self.report_printed(epic, task, "failed")
        return printed

    def epic_of_five_tasks(self) -> tuple[str, list[str]]:
        epic = self.new_epic()
        tasks = [self.new_task_under(epic) for _ in range(5)]
        self.hand_off(epic, {task: f"area-{number}" for number, task in enumerate(tasks)})
        self.next_printed(epic)
        return epic, tasks

    def test_three_laps_in_a_row_parked_at_the_build_stop_new_laps_until_a_fix_task_is_filed(self):
        epic, [first, second, third, fourth, fifth] = self.epic_of_five_tasks()
        self.fail_three_times(epic, first)
        self.fail_three_times(epic, second)

        braked = self.fail_three_times(epic, third)

        self.assertEqual({"stage": "build", "laps": 3}, braked["brake"])
        self.assertEqual(([], [fourth]), (braked["actions"], [open_lap["task"] for open_lap in braked["laps"]]))
        self.assertNotIn("lap.stage", self.metadata(fifth))
        still_braked = self.next_moves(epic)
        self.assertEqual(0, still_braked.returncode, still_braked.stderr)
        self.assertEqual([fourth], [action["task"] for action in json.loads(still_braked.stdout)["actions"]])
        self.assertIn("no new lap opens until a fix task is filed", still_braked.stderr)

        fix = self.new_task_under(epic)
        fixture.run([self.bd, "update", fix, "--set-metadata", "lap.area=fix"], self.repo)
        lifted = self.next_printed(epic)

        self.assertIsNone(lifted["brake"])
        self.assertEqual([fourth, fifth], [action["task"] for action in lifted["actions"]][:2])

    def test_a_merge_between_the_parked_laps_keeps_the_brake_off(self):
        epic, [first, second, third, fourth, fifth] = self.epic_of_five_tasks()
        self.fail_three_times(epic, first)
        self.fail_three_times(epic, second)
        third_lap = next(open_lap for open_lap in self.next_printed(epic)["laps"] if open_lap["task"] == third)
        self.commit_in(Path(third_lap["worktree"]), "card.txt", "built\n")
        self.build_done(epic, third)

        printed = self.fail_three_times(epic, fourth)

        self.assertIsNone(printed["brake"])
        self.assertEqual([fifth], [open_lap["task"] for open_lap in printed["laps"]])


class HumanLabelBrakeTests(SchedulerCase):
    def label(self, bead: str) -> None:
        fixture.run([self.bd, "label", "add", bead, "human"], self.repo)

    def unlabel(self, bead: str) -> None:
        fixture.run([self.bd, "label", "remove", bead, "human"], self.repo)

    def test_a_human_label_put_on_a_task_with_a_running_build_stops_the_build_that_a_failed_try_would_start(self):
        lap = self.open_one_lap()
        self.label(lap.task)

        printed = self.report_printed(lap.epic, lap.task, "failed")

        self.assertEqual([], printed["actions"])
        self.assertEqual([("build", 1)], [(open_lap["stage"], open_lap["tries"]) for open_lap in printed["laps"]])
        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))

    def test_a_manager_restarting_starts_no_stage_on_a_task_labeled_human(self):
        lap = self.open_one_lap()
        self.label(lap.task)

        restarted = self.next_moves(lap.epic)

        self.assertEqual(0, restarted.returncode, restarted.stderr)
        self.assertEqual([], json.loads(restarted.stdout)["actions"])
        self.assertIn(lap.task, restarted.stderr)

    def test_taking_the_human_label_off_a_task_lets_its_stopped_build_start_again_as_a_new_lap_on_its_worktree(self):
        lap = self.open_one_lap()
        self.label(lap.task)
        self.report_printed(lap.epic, lap.task, "failed")
        self.unlabel(lap.task)

        [action] = self.next_printed(lap.epic)["actions"]

        self.assertEqual(("build", lap.task, 2, str(lap.worktree)),
                         (action["action"], action["task"], action["lap"], action["worktree"]))

    def test_a_build_that_is_done_when_the_human_label_goes_on_its_task_still_merges(self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.label(lap.task)

        self.build_done(lap.epic, lap.task)

        self.assertEqual("closed", self.shown(lap.task)["status"])

    def test_a_human_label_on_the_epic_opens_no_lap_for_any_ready_task(self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        self.hand_off(epic, {first: "till", second: "receipts"})
        self.label(epic)

        printed = self.next_printed(epic)

        self.assertEqual(([], []), (printed["actions"], printed["laps"]))
        for task in (first, second):
            self.assertNotIn("lap.stage", self.metadata(task))
            self.assertEqual("open", self.shown(task)["status"])

    def test_a_human_label_on_the_epic_stops_the_build_that_a_failed_try_would_start_on_every_running_lap(self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        self.hand_off(epic, {first: "till", second: "receipts"})
        self.next_printed(epic)
        self.label(epic)

        printed = self.report_printed(epic, first, "failed")

        self.assertEqual([], printed["actions"])
        self.assertEqual({first, second}, {open_lap["task"] for open_lap in printed["laps"]})

    def test_taking_the_human_label_off_the_epic_lets_the_factory_open_the_laps_it_held_back(self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        self.hand_off(epic, {first: "till", second: "receipts"})
        self.label(epic)
        self.next_printed(epic)
        self.unlabel(epic)

        printed = self.next_printed(epic)

        self.assertEqual([first, second], [action["task"] for action in printed["actions"]])

    def test_a_running_stage_finishes_when_the_epic_is_parked_and_the_laps_resume_when_the_label_comes_off(self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        fixture.run([self.bd, "dep", "add", second, "--blocked-by", first], self.repo)
        self.hand_off(epic, {first: "till", second: "receipts"})
        [action] = self.next_printed(epic)["actions"]
        self.commit_in(Path(action["worktree"]), "card.txt", "built\n")
        self.label(epic)

        parked = self.build_done(epic, first)

        self.assertEqual(("closed", [], []), (self.shown(first)["status"], parked["actions"], parked["laps"]))
        self.assertNotIn("lap.stage", self.metadata(second))

        self.unlabel(epic)
        [resumed] = self.next_printed(epic)["actions"]

        self.assertEqual(("build", second), (resumed["action"], resumed["task"]))


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
        self.commit_in(lap.worktree, "card.txt", "built\n")
        lock = self.home / "locks" / "merge.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("424242\n", encoding="utf-8")
        self.addCleanup(lambda: lock.unlink(missing_ok=True))
        command = fixture.launch_command(LAUNCHER, [str(SCHEDULER), "report", lap.epic, lap.task, "done", "--app",
                                                    "shop", "--filter", "test_card"])
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   encoding="utf-8", env=self.caller_env(self.home), cwd=self.repo)
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
        self.assertEqual([], self.lap_actions(json.loads(out)))
        self.assertEqual(["-k test_card", "-k test_card"], self.runs_of(lap.task))
        self.assertEqual(moved, git(self.repo, "rev-parse", f"{lap.epic_branch}~1"))
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

    def test_a_why_with_an_outcome_other_than_failed_is_refused_and_nothing_is_written(self):
        lap = self.open_one_lap()

        done = self.report(lap.epic, lap.task, "cut off", "--why", "the worker stopped")

        self.assertEqual(1, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn("--why goes only with failed", done.stderr)
        self.assertEqual(("build", 0), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))
        self.assertEqual("0", str(self.metadata(lap.task).get("lap.cutoffs", 0)))

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


class SchedulerReadsRulesTests(SchedulerCase):
    def test_lowering_the_lap_limit_posts_one_line_under_the_git_user_and_the_scheduler_opens_no_more_laps(self):
        epic = self.handed_off_epic(3)

        self.rules_set(epic, "lap_limit=1")
        printed = self.next_printed(epic)

        [comment] = self.rule_comments(epic)
        self.assertEqual(JEFF, comment["author"])
        self.assertEqual("Factory rules: lap_limit set to 1.", comment["text"])
        self.assertEqual(1, printed["lap_limit"])
        self.assertEqual(1, len(printed["actions"]))
        self.assertEqual(1, len(printed["laps"]))

    def test_without_a_rule_the_scheduler_opens_laps_up_to_the_repo_settings_lap_limit(self):
        epic = self.handed_off_epic(3)

        printed = self.next_printed(epic)

        self.assertEqual((LAP_LIMIT, LAP_LIMIT), (printed["lap_limit"], len(printed["actions"])))

    def test_the_scheduler_reads_the_rules_again_on_every_call(self):
        epic = self.handed_off_epic(3)
        first = self.next_printed(epic)
        self.assertEqual(LAP_LIMIT, first["lap_limit"])

        self.rules_set(epic, "lap_limit=1")
        second = self.next_printed(epic)

        self.assertEqual(1, second["lap_limit"])
        opened = {action["task"] for action in first["actions"]}
        self.assertEqual(1, len(second["actions"]))
        self.assertLessEqual({action["task"] for action in second["actions"]}, opened)
        self.assertEqual({action["task"] for action in second["actions"]}, {lap["task"] for lap in second["laps"]})

    def test_the_scheduler_refuses_an_epic_whose_stored_rules_cannot_be_read(self):
        epic = self.handed_off_epic(1)
        fixture.run([self.bd, "update", epic, "--set-metadata", "rules.lap_limit=0"], self.repo)

        done = self.next_moves(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("lap_limit holds 0, where it needs a whole number above zero", done.stderr)


class FullTrackCase(SchedulerCase):
    """The helpers of the tests of a full-track lap."""
    BRIEF = "Files to change: card.txt\nSeam: the card reader\n"

    def open_full_lap(self) -> OpenLap:
        """An epic handed off with one task on the full track, and the research action its lap opened with."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        branch = self.hand_off(epic, {task: "till"})
        fixture.run([self.bd, "update", task, "--set-metadata", "lap.track=full"], self.repo)
        [action] = self.next_printed(epic)["actions"]
        self.assertEqual("research", action["action"])
        return OpenLap(epic, task, branch, Path(action["worktree"]))

    def finish_research(self, lap: OpenLap) -> dict:
        (lap.worktree / ".scratch" / "research-brief.md").write_text(self.BRIEF, encoding="utf-8")
        return self.report_printed(lap.epic, lap.task, "done")

    def finish_build(self, lap: OpenLap, text: str = "built\n") -> dict:
        self.leave_in(lap.worktree, "card.txt", text)
        return self.build_done(lap.epic, lap.task)

    def write_outcome_block(self, lap: OpenLap, block: dict) -> None:
        (lap.worktree / ".scratch" / "spec-check.json").write_text(json.dumps(block), encoding="utf-8")

    def send_back_block(self, note: str) -> dict:
        return {"outcome": "send back", "findings": [{"kind": "extra", "file": "card.txt", "line": 1,
                                                       "bead": "none", "note": note}]}

    def pass_the_spec_check(self, lap: OpenLap) -> dict:
        return self.report_printed(lap.epic, lap.task, "pass")

    def stages_of(self, printed: dict) -> list[str]:
        return [action["action"] for action in printed["actions"] if action["action"] != "tidy"]


class FullTrackLapTests(FullTrackCase):
    def test_a_full_track_lap_runs_research_build_targeted_tests_and_spec_check_in_order_before_it_merges(self):
        lap = self.open_full_lap()

        after_research = self.finish_research(lap)
        runs_after_research = self.runs_of(lap.task)
        after_build = self.finish_build(lap)
        runs_before_the_check = self.runs_of(lap.task)
        after_check = self.pass_the_spec_check(lap)

        self.assertEqual((["build"], ["spec-check"], []),
                         (self.stages_of(after_research), self.stages_of(after_build), self.stages_of(after_check)))
        self.assertEqual(([], ["-k test_card"]), (runs_after_research, runs_before_the_check))
        self.assertEqual(["-k test_card"], self.runs_of(lap.task))
        self.assertEqual("closed", self.shown(lap.task)["status"])
        self.assertEqual(["card.txt"], self.files_of(lap.epic_branch))

    def test_the_research_brief_is_posted_on_the_task_as_a_research_brief_comment_by_jidoka(self):
        lap = self.open_full_lap()

        self.finish_research(lap)

        [brief] = [comment for comment in self.comments(lap.task) if str(comment["text"]).startswith("research brief: ")]
        self.assertEqual(("jidoka", f"research brief: {self.BRIEF.strip()}"), (brief["author"], brief["text"]))
        self.assertEqual("build", self.metadata(lap.task)["lap.stage"])
        self.assertFalse((lap.worktree / ".scratch" / "research-brief.md").exists())

    def test_the_spec_check_comes_after_the_targeted_tests_and_before_the_merge_gate(self):
        lap = self.open_full_lap()
        self.finish_research(lap)

        after_build = self.finish_build(lap)

        self.assertEqual("spec-check", self.metadata(lap.task)["lap.stage"])
        self.assertEqual("in_progress", self.shown(lap.task)["status"])
        self.assertEqual("spec-check", after_build["laps"][0]["stage"])
        self.assertNotIn(lap.epic_branch, git(self.repo, "branch", "--contains", f"lap/{lap.task}"))

    def test_a_send_back_returns_the_findings_to_a_new_build_that_runs_the_checks_again(self):
        lap = self.open_full_lap()
        self.finish_research(lap)
        self.finish_build(lap)
        self.write_outcome_block(lap, self.send_back_block("adds a flag the task does not ask for"))

        sent_back = self.report_printed(lap.epic, lap.task, "send back")

        [action] = sent_back["actions"]
        self.assertEqual("build", action["action"])
        self.assertEqual([{"kind": "extra", "file": "card.txt", "line": 1, "bead": "none",
                           "note": "adds a flag the task does not ask for"}], action["findings"])
        metadata = self.metadata(lap.task)
        self.assertEqual(("build", 0, 1), (metadata["lap.stage"], metadata["lap.tries"], metadata["lap.sendbacks"]))
        self.assertTrue(any("adds a flag the task does not ask for" in text for text in self.texts(lap.task)))
        self.assertFalse((lap.worktree / ".scratch" / "spec-check.json").exists())

        rebuilt = self.finish_build(lap, "rebuilt\n")
        merged = self.pass_the_spec_check(lap)

        self.assertEqual((["spec-check"], []), (self.stages_of(rebuilt), self.stages_of(merged)))
        self.assertIsNone(rebuilt["actions"][0]["findings"])
        self.assertEqual(["-k test_card", "-k test_card"], self.runs_of(lap.task))
        self.assertEqual("closed", self.shown(lap.task)["status"])

    def test_two_send_backs_from_the_spec_check_park_the_task_naming_the_send_back_cap(self):
        lap = self.open_full_lap()
        self.finish_research(lap)
        self.finish_build(lap)
        self.write_outcome_block(lap, self.send_back_block("first finding"))
        self.report_printed(lap.epic, lap.task, "send back")
        self.finish_build(lap, "rebuilt\n")
        self.write_outcome_block(lap, self.send_back_block("second finding"))

        parked = self.report_printed(lap.epic, lap.task, "send back")

        self.assertEqual([], parked["actions"])
        why = self.assert_parked(lap, 0)
        self.assertIn("the send-back cap of 2", why)
        self.assertIn("second finding", why)

    def test_a_send_back_from_the_spec_check_and_one_from_another_check_together_park_the_task(self):
        lap = self.open_full_lap()
        self.finish_research(lap)
        self.report_printed(lap.epic, lap.task, "send back")
        self.finish_build(lap)
        self.write_outcome_block(lap, self.send_back_block("an extra"))

        self.report_printed(lap.epic, lap.task, "send back")

        self.assertIn("the send-back cap of 2", self.assert_parked(lap, 0))

    def test_a_send_back_with_no_usable_outcome_block_counts_a_try_of_the_spec_check(self):
        lap = self.open_full_lap()
        self.finish_research(lap)
        self.finish_build(lap)

        retried = self.report_printed(lap.epic, lap.task, "send back")

        self.assertEqual(["spec-check"], self.stages_of(retried))
        metadata = self.metadata(lap.task)
        self.assertEqual(("spec-check", 1, 0), (metadata["lap.stage"], metadata["lap.tries"],
                                                 metadata.get("lap.sendbacks", 0)))
        self.assertTrue(any(text.startswith("Spec check try 1 of 3 failed") for text in self.texts(lap.task)))

    def test_a_spec_check_that_cannot_judge_parks_the_task_with_its_reason_and_counts_no_try(self):
        lap = self.open_full_lap()
        self.finish_research(lap)
        self.finish_build(lap)
        self.write_outcome_block(lap, {"outcome": "cannot judge", "reason": "the bead has no description"})

        parked = self.report_printed(lap.epic, lap.task, "cannot judge")

        self.assertEqual([], parked["actions"])
        self.assertIn("the bead has no description", self.assert_parked(lap, 0))
        self.assertEqual("open", self.shown(lap.task)["status"])

    def test_a_lap_whose_task_already_holds_a_research_brief_starts_at_the_build(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        fixture.run([self.bd, "update", task, "--set-metadata", "lap.track=full"], self.repo)
        fixture.run([self.bd, "comment", task, "research brief: Files to change: card.txt"], self.repo)

        [action] = self.next_printed(epic)["actions"]

        self.assertEqual("build", action["action"])

    def test_a_research_stage_that_leaves_no_brief_counts_a_try_and_runs_the_research_again(self):
        lap = self.open_full_lap()

        retried = self.report_printed(lap.epic, lap.task, "done")

        self.assertEqual(["research"], self.stages_of(retried))
        self.assertEqual(("research", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))
        self.assertTrue(any(text.startswith("Research try 1 of 3 failed") for text in self.texts(lap.task)))

    def test_a_spec_check_passed_after_the_epic_branch_moved_runs_the_targeted_tests_again_before_the_merge(self):
        lap = self.open_full_lap()
        self.finish_research(lap)
        self.finish_build(lap)
        moved = self.commit_on_epic_branch(lap.epic_branch, "other.txt", "other lap\n")

        merged = self.pass_the_spec_check(lap)

        self.assertEqual([], self.stages_of(merged))
        self.assertEqual(["-k test_card", "-k test_card"], self.runs_of(lap.task))
        self.assertEqual(moved, git(self.repo, "rev-parse", f"{lap.epic_branch}~1"))
        self.assertEqual("closed", self.shown(lap.task)["status"])

    def test_red_targeted_tests_send_a_full_track_build_back_without_a_spec_check(self):
        lap = self.open_full_lap()
        self.finish_research(lap)
        self.queue_exit_codes(lap.task, 1)

        retried = self.finish_build(lap)

        self.assertEqual(["build"], self.stages_of(retried))
        self.assertEqual(("build", 1), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))

    def test_a_simple_track_lap_starts_at_the_build_and_merges_with_no_spec_check(self):
        lap = self.open_one_lap()
        self.leave_in(lap.worktree, "card.txt", "built\n")

        merged = self.build_done(lap.epic, lap.task)

        self.assertEqual([], self.stages_of(merged))
        self.assertEqual("closed", self.shown(lap.task)["status"])

    def test_a_spec_check_outcome_reported_at_the_build_is_refused_and_nothing_is_written(self):
        lap = self.open_one_lap()

        refused = self.report(lap.epic, lap.task, "pass")

        self.assertEqual(1, refused.returncode)
        self.assertIn("pass is an outcome of the Spec check", refused.stderr)
        self.assertEqual(("build", 0), (self.metadata(lap.task)["lap.stage"], self.metadata(lap.task)["lap.tries"]))

    def test_done_reported_at_the_spec_check_is_refused_and_the_lap_stays_there(self):
        lap = self.open_full_lap()
        self.finish_research(lap)
        self.finish_build(lap)

        refused = self.report(lap.epic, lap.task, "done", "--app", "shop", "--filter", "test_card")

        self.assertEqual(1, refused.returncode)
        self.assertIn("ends pass, send back or cannot judge", refused.stderr)
        self.assertEqual("spec-check", self.metadata(lap.task)["lap.stage"])

    def test_a_cut_off_spec_check_goes_back_to_the_spec_check_and_counts_no_try(self):
        lap = self.open_full_lap()
        self.finish_research(lap)
        self.finish_build(lap)

        again = self.report_printed(lap.epic, lap.task, "cut off")

        self.assertEqual(["spec-check"], self.stages_of(again))
        metadata = self.metadata(lap.task)
        self.assertEqual(("spec-check", 0, 1), (metadata["lap.stage"], metadata["lap.tries"],
                                                 metadata["lap.cutoffs.spec-check"]))


class AppCheckTests(FullTrackCase):
    """The app check of a full-track lap, which runs after the targeted tests when a holdout names the task."""
    UNRELATED = "A shopper pays 9.00 with an expired card and sees Card expired."
    FIRST = "A shopper pays 2.00 and receipt 2 prints."
    SECOND = "A shopper pays 3.00 twice and sees one receipt."
    SAW = "The till printed no receipt after a payment of 2.00, where receipt 2 should have printed."

    def write_holdouts(self, epic: str, holdouts: list[dict]) -> None:
        command = fixture.launch_command(LAUNCHER, [str(PLUGIN / "scripts" / "holdouts.py"), "write", epic])
        done = subprocess.run(command, input=json.dumps(holdouts), capture_output=True, text=True, encoding="utf-8",
                              timeout=RUN_TIMEOUT_SECONDS, env=self.caller_env(self.home), cwd=self.repo)
        if done.returncode != 0:
            raise fixture.FixtureError(f"holdouts.py write failed: {done.stderr}")

    def open_full_lap_under_holdouts(self) -> OpenLap:
        """A full-track task and a second task in its area, with three holdouts: the first names only the second
        task, the others name the first. The lap has finished its research."""
        epic = self.new_epic()
        task = self.new_task_under(epic, "--priority", "1")
        other = self.new_task_under(epic, "--priority", "2")
        branch = self.hand_off(epic, {task: "till", other: "till"})
        fixture.run([self.bd, "update", task, "--set-metadata", "lap.track=full"], self.repo)
        self.write_holdouts(epic, [{"app": "shop", "tasks": [other], "scenario": self.UNRELATED},
                                   {"app": "shop", "tasks": [task], "scenario": self.FIRST},
                                   {"app": "shop", "tasks": [task, other], "scenario": self.SECOND}])
        [action] = self.next_printed(epic)["actions"]
        lap = OpenLap(epic, task, branch, Path(action["worktree"]))
        self.finish_research(lap)
        return lap

    def write_report(self, lap: OpenLap, entries: list[dict]) -> None:
        (lap.worktree / ".scratch" / "app-check.json").write_text(json.dumps(entries), encoding="utf-8")

    def green_report(self) -> list[dict]:
        return [{"holdout": 2, "verdict": "pass", "saw": ""}, {"holdout": 3, "verdict": "pass", "saw": ""}]

    def red_report(self) -> list[dict]:
        return [{"holdout": 2, "verdict": "fail", "saw": self.SAW, "steps": self.FIRST},
                {"holdout": 3, "verdict": "pass", "saw": ""}]

    def test_the_app_check_runs_after_the_targeted_tests_and_before_the_spec_check_and_the_merge_gate(self):
        lap = self.open_full_lap_under_holdouts()

        after_build = self.finish_build(lap)
        self.write_report(lap, self.green_report())
        after_app_check = self.report_printed(lap.epic, lap.task, "done")

        self.assertEqual((["app-check"], ["spec-check"]),
                         (self.stages_of(after_build), self.stages_of(after_app_check)))
        self.assertEqual(["-k test_card"], self.runs_of(lap.task))
        self.assertEqual("spec-check", self.metadata(lap.task)["lap.stage"])
        self.assertNotIn(lap.epic_branch, git(self.repo, "branch", "--contains", f"lap/{lap.task}"))
        self.assertFalse((lap.worktree / ".scratch" / "app-check.json").exists())

    def test_the_app_check_action_names_the_lap_s_slot_and_worktree_and_the_report_it_writes(self):
        lap = self.open_full_lap_under_holdouts()

        [action] = self.finish_build(lap)["actions"]

        self.assertEqual("app-check", action["action"])
        self.assertEqual((lap.task, str(lap.worktree), str(lap.worktree / ".scratch" / "app-check.json")),
                         (action["task"], action["worktree"], action["report"]))
        self.assertEqual(str(self.metadata(lap.task)["lap.slot"]), str(action["slot"]))
        self.assertNotIn(self.FIRST, json.dumps(action))

    def test_a_full_track_lap_that_no_holdout_names_goes_from_the_targeted_tests_to_the_spec_check(self):
        lap = self.open_full_lap()
        self.finish_research(lap)

        after_build = self.finish_build(lap)

        self.assertEqual(["spec-check"], self.stages_of(after_build))

    def test_a_report_that_gives_a_verdict_to_a_holdout_that_names_another_task_counts_a_try_of_the_app_check(self):
        lap = self.open_full_lap_under_holdouts()
        self.finish_build(lap)
        self.write_report(lap, [{"holdout": 1, "verdict": "pass", "saw": ""}, *self.green_report()])

        retried = self.report_printed(lap.epic, lap.task, "done")

        self.assertEqual(["app-check"], self.stages_of(retried))
        metadata = self.metadata(lap.task)
        self.assertEqual(("app-check", 1), (metadata["lap.stage"], metadata["lap.tries"]))
        self.assertTrue(any(text.startswith("App check try 1 of 3 failed") for text in self.texts(lap.task)))

    def test_a_failed_holdout_comes_back_to_the_builder_as_its_id_the_verdict_and_what_a_user_saw_and_no_steps(self):
        lap = self.open_full_lap_under_holdouts()
        self.finish_build(lap)
        self.write_report(lap, self.red_report())

        sent_back = self.report_printed(lap.epic, lap.task, "done")

        [action] = sent_back["actions"]
        self.assertEqual("build", action["action"])
        self.assertEqual([{"holdout": 2, "verdict": "fail", "saw": self.SAW}], action["app_check"])
        self.assertIsNone(action["findings"])
        everything_the_builder_reads = json.dumps(action) + "\n".join(self.texts(lap.task))
        self.assertIn(self.SAW, "\n".join(self.texts(lap.task)))
        for scenario in (self.UNRELATED, self.FIRST, self.SECOND):
            self.assertNotIn(scenario, everything_the_builder_reads)
        self.assertNotIn(self.FIRST, json.dumps(self.metadata(lap.task)))
        metadata = self.metadata(lap.task)
        self.assertEqual(("build", 0, 1), (metadata["lap.stage"], metadata["lap.tries"], metadata["lap.sendbacks"]))
        self.assertFalse((lap.worktree / ".scratch" / "app-check.json").exists())

    def test_the_rebuilt_lap_runs_the_app_check_again_with_no_findings_and_then_the_spec_check(self):
        lap = self.open_full_lap_under_holdouts()
        self.finish_build(lap)
        self.write_report(lap, self.red_report())
        self.report_printed(lap.epic, lap.task, "done")

        rebuilt = self.finish_build(lap, "rebuilt\n")
        self.write_report(lap, self.green_report())
        checked = self.report_printed(lap.epic, lap.task, "done")

        self.assertEqual((["app-check"], ["spec-check"]), (self.stages_of(rebuilt), self.stages_of(checked)))
        self.assertIsNone(rebuilt["actions"][0]["app_check"])
        self.assertEqual(["-k test_card", "-k test_card"], self.runs_of(lap.task))

    def test_a_send_back_from_the_app_check_and_one_from_the_spec_check_together_park_the_task(self):
        lap = self.open_full_lap_under_holdouts()
        self.finish_build(lap)
        self.write_report(lap, self.red_report())
        self.report_printed(lap.epic, lap.task, "done")
        self.finish_build(lap, "rebuilt\n")
        self.write_report(lap, self.green_report())
        self.report_printed(lap.epic, lap.task, "done")
        self.write_outcome_block(lap, self.send_back_block("an extra"))

        parked = self.report_printed(lap.epic, lap.task, "send back")

        self.assertNotIn(lap.task, [action["task"] for action in parked["actions"]])
        self.assertIn("the send-back cap of 2", self.assert_parked(lap, 0))

    def test_two_app_check_send_backs_park_the_task_naming_the_failed_holdout_and_not_its_steps(self):
        lap = self.open_full_lap_under_holdouts()
        self.finish_build(lap)
        self.write_report(lap, self.red_report())
        self.report_printed(lap.epic, lap.task, "done")
        self.finish_build(lap, "rebuilt\n")
        self.write_report(lap, self.red_report())

        parked = self.report_printed(lap.epic, lap.task, "done")

        self.assertNotIn(lap.task, [action["task"] for action in parked["actions"]])
        why = self.assert_parked(lap, 0)
        self.assertIn("the send-back cap of 2", why)
        self.assertIn(self.SAW, why)
        self.assertNotIn(self.FIRST, why)

    def test_a_report_whose_saw_quotes_a_scenario_counts_a_try_and_reaches_no_builder(self):
        lap = self.open_full_lap_under_holdouts()
        self.finish_build(lap)
        self.write_report(lap, [{"holdout": 2, "verdict": "fail", "saw": f"Steps: {self.FIRST}"},
                                {"holdout": 3, "verdict": "pass", "saw": ""}])

        retried = self.report_printed(lap.epic, lap.task, "done")

        self.assertEqual(["app-check"], self.stages_of(retried))
        self.assertEqual(1, int(self.metadata(lap.task)["lap.tries"]))
        self.assertNotIn(self.FIRST, "\n".join(self.texts(lap.task)))
        self.assertFalse(self.metadata(lap.task).get("lap.appfindings"))

    def test_an_app_check_that_leaves_no_report_counts_a_try_of_the_app_check(self):
        lap = self.open_full_lap_under_holdouts()
        self.finish_build(lap)

        retried = self.report_printed(lap.epic, lap.task, "done")

        self.assertEqual(["app-check"], self.stages_of(retried))
        self.assertTrue(any(text.startswith("App check try 1 of 3 failed") for text in self.texts(lap.task)))

    def test_done_with_an_app_and_a_filter_is_refused_at_the_app_check_and_the_lap_stays_there(self):
        lap = self.open_full_lap_under_holdouts()
        self.finish_build(lap)

        refused = self.report(lap.epic, lap.task, "done", "--app", "shop", "--filter", "test_card")

        self.assertEqual(1, refused.returncode)
        self.assertIn("--app and --filter go only with done at the build or the merge", refused.stderr)
        self.assertEqual("app-check", self.metadata(lap.task)["lap.stage"])

    def test_a_cut_off_app_check_goes_back_to_the_app_check_and_counts_no_try(self):
        lap = self.open_full_lap_under_holdouts()
        self.finish_build(lap)

        again = self.report_printed(lap.epic, lap.task, "cut off")

        self.assertEqual(["app-check"], self.stages_of(again))
        metadata = self.metadata(lap.task)
        self.assertEqual(("app-check", 0, 1), (metadata["lap.stage"], metadata["lap.tries"],
                                                metadata["lap.cutoffs.app-check"]))

    def test_two_app_checks_never_share_a_slot(self):
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        self.hand_off(epic, {first: "till", second: "receipts"})
        for task in (first, second):
            fixture.run([self.bd, "update", task, "--set-metadata", "lap.track=full"], self.repo)
        self.write_holdouts(epic, [{"app": "shop", "tasks": [first, second], "scenario": self.FIRST}])
        laps = {action["task"]: OpenLap(epic, action["task"], "", Path(action["worktree"]))
                for action in self.next_printed(epic)["actions"]}
        for lap in laps.values():
            self.finish_research(lap)

        self.finish_build(laps[first])
        printed = self.finish_build(laps[second])

        checking = [lap for lap in printed["laps"] if lap["stage"] == "app-check"]
        self.assertEqual({first, second}, {lap["task"] for lap in checking})
        self.assertEqual(2, len({lap["slot"] for lap in checking}))
        [action] = [action for action in printed["actions"] if action["task"] == second]
        self.assertEqual(("app-check", next(lap["slot"] for lap in checking if lap["task"] == second)),
                         (action["action"], action["slot"]))


class TrackMoveTests(FullTrackCase):
    def red_build(self, lap: OpenLap, codes: list[int]) -> dict:
        self.queue_exit_codes(lap.task, *codes)
        self.leave_in(lap.worktree, "card.txt", "built\n")
        return self.build_done(lap.epic, lap.task)

    def moves_of(self, task: str) -> list[dict]:
        return [comment for comment in self.comments(task) if comment["text"].startswith("Moved to the full track")]

    def test_a_simple_task_whose_targeted_tests_fail_twice_gets_its_next_build_on_the_full_track_with_a_comment(self):
        lap = self.open_one_lap()

        first = self.red_build(lap, [1, 1])
        second = self.build_done(lap.epic, lap.task)

        self.assertEqual(("build", "simple"), (first["actions"][0]["action"], first["actions"][0]["track"]))
        self.assertEqual(("build", "full"), (second["actions"][0]["action"], second["actions"][0]["track"]))
        self.assertEqual("full", self.metadata(lap.task)["lap.track"])
        [moved] = self.moves_of(lap.task)
        self.assertEqual("jidoka", moved["author"])
        self.assertIn("the targeted tests failed twice", moved["text"])
        self.assertIn("exit code 1", moved["text"])

    def test_the_build_after_the_move_goes_through_the_spec_check_before_it_merges(self):
        lap = self.open_one_lap()
        self.red_build(lap, [1, 1, 0])
        self.build_done(lap.epic, lap.task)

        passed = self.build_done(lap.epic, lap.task)

        self.assertEqual(["spec-check"], self.stages_of(passed))
        self.assertEqual("in_progress", self.shown(lap.task)["status"])

    def test_one_failed_targeted_run_leaves_a_simple_task_on_the_simple_track(self):
        lap = self.open_one_lap()

        printed = self.red_build(lap, [1])

        self.assertEqual("simple", printed["actions"][0]["track"])
        self.assertNotEqual("full", self.metadata(lap.task).get("lap.track"))
        self.assertEqual([], self.moves_of(lap.task))

    def test_failed_builds_and_cutoffs_do_not_move_a_simple_task(self):
        lap = self.open_one_lap()

        self.report_printed(lap.epic, lap.task, "failed")
        self.report_printed(lap.epic, lap.task, "cut off")
        printed = self.report_printed(lap.epic, lap.task, "failed")

        self.assertEqual("simple", printed["actions"][0]["track"])
        self.assertNotEqual("full", self.metadata(lap.task).get("lap.track"))
        self.assertEqual([], self.moves_of(lap.task))

    def test_red_targeted_runs_that_newer_work_on_the_epic_branch_causes_do_not_move_a_simple_task(self):
        lap = self.open_one_lap()
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.commit_on_epic_branch(lap.epic_branch, "other.txt", "other lap\n")
        self.queue_exit_codes(lap.task, 1, 1)

        self.build_done(lap.epic, lap.task)

        self.assertEqual("merge", self.metadata(lap.task)["lap.stage"])
        self.assertEqual([], self.moves_of(lap.task))
        self.assertNotEqual("full", self.metadata(lap.task).get("lap.track"))

    def test_a_full_task_whose_targeted_tests_fail_twice_stays_full_and_gets_no_move_comment(self):
        lap = self.open_full_lap()
        self.finish_research(lap)
        self.queue_exit_codes(lap.task, 1, 1)

        self.finish_build(lap)
        self.build_done(lap.epic, lap.task)

        self.assertEqual("full", self.metadata(lap.task)["lap.track"])
        self.assertEqual([], self.moves_of(lap.task))

    def test_a_moved_task_stays_on_the_full_track_through_to_its_merge(self):
        lap = self.open_one_lap()
        self.red_build(lap, [1, 1, 0])
        self.build_done(lap.epic, lap.task)
        self.build_done(lap.epic, lap.task)

        merged = self.report_printed(lap.epic, lap.task, "pass")

        self.assertEqual([], self.lap_actions(merged))
        self.assertEqual(("closed", "full"), (self.shown(lap.task)["status"], self.metadata(lap.task)["lap.track"]))


if __name__ == "__main__":
    unittest.main()
