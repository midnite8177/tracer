import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
SCHEDULER = PLUGIN / "scripts" / "scheduler.py"
HANDOFF = PLUGIN / "scripts" / "handoff.py"
HEARTBEAT = PLUGIN / "scripts" / "heartbeat.py"
HOOK = PLUGIN / "hooks" / "session_start.py"

RUN_TIMEOUT_SECONDS = 120
OUT_OF_SCOPE = "## Out of Scope\nRefunds."
ONE_SEAM = "## Seams\nThe card reader, run as a process."
HUMAN = "Pat Human"
LAP_LIMIT = 2
STALE_SECONDS = 600
FRESH_SECONDS = 5
FRESH_FOR_SECONDS = 90
ALMOST_STALE_SECONDS = 89
MANAGER_SESSION = "session-of-the-manager"
OTHER_SESSION = "session-of-an-advisor"
LEAVES_A_SLEEPER_AND_EXITS = ("import subprocess, sys; "
                              f"print(subprocess.Popen([sys.executable, '-c', {fixture.SLEEP_FOR_AN_HOUR!r}]).pid)")


class ResumeCase(unittest.TestCase):
    """A temporary git repo with the fake bd's beads and a temporary jidoka home that holds repo settings,
    with one epic handed off with three tasks in three areas."""

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
        self.write_settings()
        self.epic = self.create("Take card payments", "--type=epic", "--description", OUT_OF_SCOPE)
        self.tasks = [self.create(f"Read the card {number}", "--type=task", "--parent", self.epic,
                                  "--description", ONE_SEAM, "--priority", str(number + 1))
                      for number in range(3)]
        done = self.script(HANDOFF, "take", self.epic,
                           *(f"--area={task}={area}" for task, area in zip(self.tasks, ("till", "receipts", "shelf"))))
        self.assertEqual(0, done.returncode, done.stderr)

    def write_settings(self) -> None:
        settings = {"lap_test_scope": "targeted", "worker_commands": [], "slot_use": None, "lap_limit": LAP_LIMIT,
                    "apps": [{"name": "shop", "kind": "program", "way_in": "its command line", "build": "make",
                              "run": None, "test": "true", "test_target": "-k <name>", "test_full": None,
                              "hand_run": [], "acceptance": "specs/acceptance"}]}
        fixture.write_repo_settings(self.repo, self.home, settings)

    def script(self, script: Path, *args: str) -> subprocess.CompletedProcess:
        return self.script_with(MANAGER_SESSION, {}, script, *args)

    def script_with(self, session: str, env: dict[str, str], script: Path, *args: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(script), *args], None,
                                    {**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
                                     "BEADS_ACTOR": HUMAN, "JIDOKA_SESSION_ID": session, **env},
                                    self.repo, RUN_TIMEOUT_SECONDS)

    def beat_as(self, session: str) -> subprocess.CompletedProcess:
        return self.script(HEARTBEAT, "beat", "--session", session)

    def bd(self, *args: str) -> str:
        return fixture.run([self.fake_bd, *args], self.repo)

    def git(self, *args: str) -> str:
        return fixture.run(["git", *args], self.repo).strip()

    def create(self, title: str, *flags: str) -> str:
        return json.loads(self.bd("create", "--title", title, *flags, "--json"))["id"]

    def shown(self, bead: str) -> dict:
        return json.loads(self.bd("show", bead, "--json"))[0]

    def metadata(self, bead: str) -> dict:
        return self.shown(bead).get("metadata") or {}

    def comments(self, bead: str) -> list[str]:
        return [str(comment["text"]) for comment in json.loads(self.bd("comments", bead, "--json") or "[]") or []]

    def next_epic_branch(self) -> str:
        return str(self.metadata(self.epic)["factory.branch"])

    def next_run(self) -> subprocess.CompletedProcess:
        return self.script(SCHEDULER, "next", self.epic)

    def next_printed(self) -> dict:
        done = self.next_run()
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def beat_file(self) -> Path:
        return self.home / "heartbeat" / f"{self.epic}.json"

    def write_beat(self, seconds_ago: int, session: str) -> None:
        self.beat_file().parent.mkdir(exist_ok=True)
        self.beat_file().write_text(json.dumps({"epic": self.epic, "time": int(time.time()) - seconds_ago,
                                                "session": session}), encoding="utf-8")

    def beat_time(self) -> int:
        return json.loads(self.beat_file().read_text(encoding="utf-8"))["time"]

    def keep_beating(self, session: str) -> None:
        """A live manager's host: the heartbeat is rewritten every fraction of a second, each time as old as it
        would be a second or two before it goes stale, so that a wait the scheduler makes ends on a fresh beat
        whenever it starts."""
        stop = threading.Event()
        self.addCleanup(stop.set)

        def beat() -> None:
            while not stop.is_set():
                self.write_beat(ALMOST_STALE_SECONDS, session)
                stop.wait(0.1)

        self.write_beat(ALMOST_STALE_SECONDS, session)
        threading.Thread(target=beat, daemon=True).start()

    def start_a_manager(self) -> dict[str, dict]:
        return {action["task"]: action for action in self.next_printed()["actions"]}

    def stop_the_host(self) -> dict[str, dict]:
        """The state a closed host leaves: two laps at the build with no worker, and a heartbeat gone stale."""
        opened = self.start_a_manager()
        self.write_beat(STALE_SECONDS, MANAGER_SESSION)
        return opened


class ResumeLapsTests(ResumeCase):
    def test_a_resume_ends_the_running_laps_interrupted_and_starts_fresh_laps_from_their_worktrees(self):
        opened = self.stop_the_host()
        committed, uncommitted = (Path(action["worktree"]) for action in opened.values())
        (committed / "till.txt").write_text("till\n", encoding="utf-8")
        fixture.git_commit_all(committed, "Take the till")
        kept_head = fixture.run(["git", "rev-parse", "HEAD"], committed).strip()
        (uncommitted / "slip.txt").write_text("slip\n", encoding="utf-8")

        done = self.next_run()

        self.assertEqual(0, done.returncode, done.stderr)
        resumed = {action["task"]: action for action in json.loads(done.stdout)["actions"]}
        self.assertEqual(sorted(opened), sorted(resumed))
        for task, action in resumed.items():
            self.assertEqual((opened[task]["worktree"], opened[task]["branch"], 2),
                             (action["worktree"], action["branch"], action["lap"]))
            self.assertEqual("build", self.metadata(task)["lap.stage"])
            self.assertEqual("0", str(self.metadata(task)["lap.tries"]))
            [interrupted] = [text for text in self.comments(task) if text.startswith("Interrupted: ")]
            self.assertIn("worktree", interrupted)
        self.assertEqual(kept_head, fixture.run(["git", "rev-parse", "HEAD"], committed).strip())
        self.assertEqual("slip\n", (uncommitted / "slip.txt").read_text(encoding="utf-8"))
        self.assertIn("interrupted", done.stderr)

    def test_a_resume_counts_no_cutoff_and_no_try(self):
        opened = self.stop_the_host()
        [task, _] = opened

        self.next_printed()

        metadata = self.metadata(task)
        self.assertEqual(("0", 0), (str(metadata["lap.tries"]), int(metadata.get("lap.cutoffs.build", 0))))
        self.assertNotIn("brake.laps", self.metadata(self.epic))

    def test_a_task_the_human_labeled_is_left_as_it_was(self):
        opened = self.stop_the_host()
        [held, other] = opened
        self.bd("label", "add", held, "human")

        done = self.next_run()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([other], [action["task"] for action in json.loads(done.stdout)["actions"]])
        self.assertEqual(("build", "1"), (self.metadata(held)["lap.stage"], str(self.metadata(held)["lap.number"])))

    def test_a_lost_worktree_gets_a_new_folder_with_the_lap_branchs_commits(self):
        opened = self.stop_the_host()
        action = next(iter(opened.values()))
        worktree = Path(action["worktree"])
        (worktree / "till.txt").write_text("till\n", encoding="utf-8")
        fixture.git_commit_all(worktree, "Take the till")
        fixture.remove_tree(worktree)

        resumed = {item["task"]: item for item in self.next_printed()["actions"]}

        self.assertEqual("till\n", (worktree / "till.txt").read_text(encoding="utf-8"))
        self.assertEqual(worktree, Path(resumed[action["task"]]["worktree"]))

    def test_a_half_finished_rebase_is_abandoned_before_the_new_lap_starts(self):
        opened = self.stop_the_host()
        action = next(iter(opened.values()))
        worktree = Path(action["worktree"])
        epic_branch = self.next_epic_branch()
        (worktree / "card.txt").write_text("mine\n", encoding="utf-8")
        fixture.git_commit_all(worktree, "Lap work")
        self.commit_on_epic_branch(epic_branch, "card.txt", "theirs\n")
        rebased = subprocess.run(["git", "rebase", epic_branch], cwd=worktree, capture_output=True, text=True)
        self.assertNotEqual(0, rebased.returncode)

        self.next_printed()

        branch = fixture.run(["git", "symbolic-ref", "--short", "HEAD"], worktree).strip()
        self.assertEqual(action["branch"], branch)

    def commit_on_epic_branch(self, branch: str, name: str, text: str) -> None:
        tree = self.root / "epic-tree"
        self.git("worktree", "add", "-q", str(tree), branch)
        (tree / name).write_text(text, encoding="utf-8")
        fixture.git_commit_all(tree, f"Add {name}")
        self.git("worktree", "remove", "--force", str(tree))


class GitWinsTests(ResumeCase):
    def test_a_lap_git_shows_merged_closes_its_task_instead_of_starting_again(self):
        opened = self.stop_the_host()
        [merged, other] = opened
        worktree = Path(opened[merged]["worktree"])
        (worktree / "till.txt").write_text("till\n", encoding="utf-8")
        fixture.git_commit_all(worktree, self.shown(merged)["title"])
        head = fixture.run(["git", "rev-parse", "HEAD"], worktree).strip()
        self.git("update-ref", f"refs/heads/{self.next_epic_branch()}", head)

        done = self.next_run()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("closed", self.shown(merged)["status"])
        self.assertNotIn(merged, [action["task"] for action in json.loads(done.stdout)["actions"]])
        self.assertIn(other, [action["task"] for action in json.loads(done.stdout)["actions"]])
        self.assertFalse(worktree.exists())
        self.assertIn("git wins", done.stderr)

    def test_a_lap_not_built_yet_is_not_taken_for_merged_when_the_epic_branch_has_not_moved(self):
        opened = self.stop_the_host()
        [unbuilt, _] = opened

        done = self.next_run()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotEqual("closed", self.shown(unbuilt)["status"])
        self.assertIn(unbuilt, [action["task"] for action in json.loads(done.stdout)["actions"]])


class MergeLockTests(ResumeCase):
    def lock(self) -> Path:
        return self.home / "locks" / "merge.lock"

    def test_a_merge_lock_whose_holder_is_gone_is_cleared(self):
        self.stop_the_host()
        gone = subprocess.Popen([sys.executable, "-c", "pass"])
        gone.wait()
        self.lock().parent.mkdir(exist_ok=True)
        self.lock().write_text(f"{gone.pid}\n", encoding="utf-8")

        done = self.next_run()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertFalse(self.lock().exists())
        self.assertIn("merge lock", done.stderr)

    def test_a_merge_lock_whose_holder_still_runs_stays(self):
        self.stop_the_host()
        self.lock().parent.mkdir(exist_ok=True)
        self.lock().write_text(f"{os.getpid()}\n", encoding="utf-8")

        done = self.next_run()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertTrue(self.lock().exists())


class OrphanWorkerTests(ResumeCase):
    def alive(self, pid: int) -> bool:
        return fixture.process_is_running(pid)

    def orphan_in(self, folder: Path) -> int:
        """A process left running in the folder whose parent is gone, as a dead host leaves a worker."""
        launched = subprocess.Popen([sys.executable, "-c", LEAVES_A_SLEEPER_AND_EXITS], cwd=folder,
                                    stdout=subprocess.PIPE, text=True)
        pid = int((launched.stdout.readline() if launched.stdout else "").strip())
        launched.wait()
        self.addCleanup(fixture.end_process, pid)
        deadline = time.time() + 5
        while not fixture.WINDOWS and time.time() < deadline:
            parent = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True)
            if parent.stdout.strip() == "1":
                break
            time.sleep(0.05)
        return pid

    def test_an_orphan_worker_in_a_lap_worktree_is_stopped(self):
        opened = self.stop_the_host()
        worktree = Path(next(iter(opened.values()))["worktree"])
        orphan = self.orphan_in(worktree)
        self.assertTrue(self.alive(orphan))

        done = self.next_run()

        self.assertEqual(0, done.returncode, done.stderr)
        deadline = time.time() + 5
        while self.alive(orphan) and time.time() < deadline:
            time.sleep(0.05)
        self.assertFalse(self.alive(orphan))
        self.assertIn(str(orphan), done.stderr)

    def test_a_process_with_a_live_parent_in_a_lap_worktree_is_left_alone(self):
        opened = self.stop_the_host()
        worktree = Path(next(iter(opened.values()))["worktree"])
        owned = subprocess.Popen([sys.executable, "-c", fixture.SLEEP_FOR_AN_HOUR], cwd=worktree)
        self.addCleanup(owned.wait)
        self.addCleanup(owned.kill)

        done = self.next_run()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIsNone(owned.poll())


class SecondManagerTests(ResumeCase):
    def test_a_manager_is_refused_while_the_epics_heartbeat_is_renewed_during_its_wait_and_nothing_is_written(self):
        self.keep_beating(OTHER_SESSION)

        done = self.next_run()

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{self.epic} already has a manager", done.stderr)
        for task in self.tasks:
            self.assertNotIn("lap.stage", self.metadata(task))

    def test_a_manager_that_starts_while_the_heartbeat_is_fresh_waits_until_it_is_stale_and_then_starts(self):
        now = int(time.time())
        self.write_beat(40, OTHER_SESSION)

        done = self.script_with(MANAGER_SESSION, {"JIDOKA_NOW": str(now)}, SCHEDULER, "next", self.epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"waits {FRESH_FOR_SECONDS - 40 + 1} seconds", done.stderr)
        self.assertEqual(LAP_LIMIT, len(json.loads(done.stdout)["actions"]))
        self.assertEqual(now + FRESH_FOR_SECONDS - 40 + 1, self.beat_time())

    def test_a_manager_that_starts_in_the_session_the_heartbeat_records_takes_the_epic_back_without_waiting(self):
        now = int(time.time())
        self.write_beat(40, MANAGER_SESSION)

        done = self.script_with(MANAGER_SESSION, {"JIDOKA_NOW": str(now)}, SCHEDULER, "next", self.epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("waits", done.stderr)
        self.assertEqual(LAP_LIMIT, len(json.loads(done.stdout)["actions"]))
        self.assertEqual(now, self.beat_time())

    def test_a_manager_starts_when_the_heartbeat_is_stale(self):
        self.write_beat(STALE_SECONDS, MANAGER_SESSION)

        done = self.next_run()

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(LAP_LIMIT, len(json.loads(done.stdout)["actions"]))

    def test_a_manager_starts_when_the_epic_has_no_heartbeat(self):
        done = self.next_run()

        self.assertEqual(0, done.returncode, done.stderr)

    def test_a_manager_that_starts_after_a_host_beat_with_no_manager_is_not_refused(self):
        self.beat_as(MANAGER_SESSION)

        done = self.next_run()

        self.assertEqual(0, done.returncode, done.stderr)

    def test_a_managers_first_call_claims_the_epic_with_a_fresh_heartbeat(self):
        self.next_printed()

        self.assertGreaterEqual(self.beat_time(), int(time.time()) - 60)
        self.assertEqual(MANAGER_SESSION, json.loads(self.beat_file().read_text(encoding="utf-8"))["session"])

    def test_a_managers_later_call_claims_the_epic_again_after_the_heartbeat_went_stale(self):
        self.next_printed()
        self.write_beat(STALE_SECONDS, MANAGER_SESSION)

        self.assertEqual(0, self.script(SCHEDULER, "carry-on", self.epic).returncode)

        self.assertGreaterEqual(self.beat_time(), int(time.time()) - 60)

    def test_a_beat_does_not_bring_a_stale_heartbeat_back_to_fresh(self):
        self.stop_the_host()
        before = self.beat_time()

        done = self.beat_as(MANAGER_SESSION)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(before, self.beat_time())

    def test_a_stop_leaves_the_heartbeat_stale_so_a_host_still_open_shows_no_manager(self):
        self.start_a_manager()
        self.write_beat(0, MANAGER_SESSION)
        self.assertEqual(0, self.script(SCHEDULER, "stop", self.epic).returncode)

        self.beat_as(MANAGER_SESSION)
        resumed = self.next_run()

        self.assertEqual(0, resumed.returncode, resumed.stderr)

    def test_a_stop_from_any_terminal_records_itself_in_the_heartbeat_and_keeps_the_second_of_the_last_beat(self):
        self.start_a_manager()
        self.write_beat(30, MANAGER_SESSION)
        last_beat = self.beat_time()

        done = self.script_with(OTHER_SESSION, {}, SCHEDULER, "stop", self.epic)

        self.assertEqual(0, done.returncode, done.stderr)
        held = json.loads(self.beat_file().read_text(encoding="utf-8"))
        self.assertIs(True, held["stopped"])
        self.assertIsNone(held["session"])
        self.assertEqual(last_beat, held["time"])

    def test_a_stop_of_an_epic_with_no_heartbeat_writes_a_stopped_one_at_the_second_of_the_stop(self):
        now = int(time.time())

        done = self.script_with(MANAGER_SESSION, {"JIDOKA_NOW": str(now)}, SCHEDULER, "stop", self.epic)

        self.assertEqual(0, done.returncode, done.stderr)
        held = json.loads(self.beat_file().read_text(encoding="utf-8"))
        self.assertIs(True, held["stopped"])
        self.assertEqual(now, held["time"])

    def test_a_managers_next_call_clears_the_stop_from_the_heartbeat(self):
        self.start_a_manager()
        self.assertEqual(0, self.script(SCHEDULER, "stop", self.epic).returncode)

        self.next_printed()

        held = json.loads(self.beat_file().read_text(encoding="utf-8"))
        self.assertIs(False, held["stopped"])
        self.assertEqual(MANAGER_SESSION, held["session"])

    def test_the_first_call_of_a_manager_lets_the_host_beat_the_epic_again(self):
        self.stop_the_host()
        self.next_printed()

        self.beat_as(MANAGER_SESSION)

        self.assertGreaterEqual(self.beat_time(), int(time.time()) - FRESH_SECONDS * 2)

    def test_a_beat_made_after_the_clock_moved_past_fresh_renews_nothing(self):
        self.next_printed()
        before = self.beat_time()

        done = self.script_with(MANAGER_SESSION, {"JIDOKA_NOW": str(int(time.time()) + STALE_SECONDS)}, HEARTBEAT,
                                "beat", "--session", MANAGER_SESSION)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(before, self.beat_time())

    def test_a_manager_call_that_knows_no_session_says_so_on_stderr(self):
        done = self.script_with(MANAGER_SESSION, {"JIDOKA_SESSION_ID": ""}, SCHEDULER, "next", self.epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("JIDOKA_SESSION_ID is not set", done.stderr)
        self.assertIsNone(json.loads(self.beat_file().read_text(encoding="utf-8"))["session"])

    def test_a_beat_from_a_session_that_claimed_nothing_leaves_the_epics_heartbeat_to_go_stale(self):
        self.next_printed()
        self.write_beat(80, MANAGER_SESSION)
        before = self.beat_time()

        self.beat_as(OTHER_SESSION)

        self.assertEqual(before, self.beat_time())
        later = self.script_with(OTHER_SESSION, {"JIDOKA_NOW": str(int(time.time()) + 15)}, SCHEDULER, "next",
                                 self.epic)
        self.assertEqual(0, later.returncode, later.stderr)

    def test_a_manager_of_another_session_is_refused_while_the_heartbeat_is_fresh_though_that_session_beat(self):
        self.next_printed()
        self.keep_beating(MANAGER_SESSION)
        self.beat_as(OTHER_SESSION)

        soon = self.script_with(OTHER_SESSION, {}, SCHEDULER, "next", self.epic)

        self.assertEqual(1, soon.returncode)
        self.assertIn("already has a manager", soon.stderr)

    def test_a_manager_that_starts_in_a_new_session_takes_the_epic_over_once_the_old_heartbeat_is_stale(self):
        self.next_printed()
        self.write_beat(STALE_SECONDS, MANAGER_SESSION)

        self.assertEqual(0, self.script_with(OTHER_SESSION, {}, SCHEDULER, "next", self.epic).returncode)
        self.beat_as(MANAGER_SESSION)

        self.assertEqual(OTHER_SESSION, json.loads(self.beat_file().read_text(encoding="utf-8"))["session"])


class SessionStartTests(ResumeCase):
    def session(self) -> str:
        event = {"session_id": "s1", "hook_event_name": "SessionStart", "source": "startup", "cwd": str(self.repo)}
        done = fixture.run_launcher(LAUNCHER, [str(HOOK)], json.dumps(event),
                                    {**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home)},
                                    self.root, RUN_TIMEOUT_SECONDS)
        self.assertEqual(0, done.returncode, done.stderr)
        return done.stdout

    def stopped_lines(self) -> list[str]:
        return [line for line in self.session().splitlines() if "stopped with" in line]

    def test_the_hook_names_a_stopped_factory_and_the_command_that_resumes_it(self):
        self.stop_the_host()

        [line] = self.stopped_lines()

        self.assertEqual(f"jidoka: Take card payments ({self.epic}) stopped with 3 open tasks left. "
                         f"Resume it with /jidoka:factory {self.epic}", line)

    def test_the_hook_names_nothing_while_the_heartbeat_is_fresh(self):
        self.start_a_manager()
        self.write_beat(FRESH_SECONDS, MANAGER_SESSION)

        self.assertEqual([], self.stopped_lines())

    def test_the_hook_names_nothing_for_an_epic_the_factory_has_not_started_on(self):
        self.assertEqual([], self.stopped_lines())

    def test_the_hook_names_nothing_for_an_epic_whose_open_tasks_all_wait_on_the_human(self):
        self.stop_the_host()
        for task in self.tasks:
            self.bd("label", "add", task, "human")

        self.assertEqual([], self.stopped_lines())

    def test_the_hook_names_nothing_for_an_epic_that_waits_on_the_human(self):
        self.stop_the_host()
        self.bd("label", "add", self.epic, "human")

        self.assertEqual([], self.stopped_lines())

    def test_the_hook_names_the_epic_again_after_a_stop(self):
        self.start_a_manager()
        self.assertEqual(0, self.script(SCHEDULER, "stop", self.epic).returncode)

        [line] = self.stopped_lines()

        self.assertIn(f"/jidoka:factory {self.epic}", line)

    def test_the_hook_names_nothing_once_a_resumed_manager_beats(self):
        self.stop_the_host()
        self.next_printed()
        self.beat_as(MANAGER_SESSION)

        self.assertEqual([], self.stopped_lines())

    def test_the_rules_still_open_the_session(self):
        self.assertIn("jidoka rules for this repo", self.session())


if __name__ == "__main__":
    unittest.main()


class BeatReadsTests(ResumeCase):
    """What a beat reads from bd, in a repo that holds more epics than the one the factory runs."""

    def setUp(self):
        super().setUp()
        self.create("Print receipts", "--type=epic")
        closed = self.create("Weigh produce", "--type=epic")
        self.bd("close", closed)
        self.next_printed()

    def calls_of_a_beat(self, session: str) -> list[list[str]]:
        before = len(fixture.fake_beads_calls(self.repo))
        done = self.beat_as(session)
        self.assertEqual(0, done.returncode, done.stderr)
        return fixture.fake_beads_calls(self.repo)[before:]

    def test_a_beat_from_a_session_that_manages_no_epic_makes_no_bd_call(self):
        self.assertEqual([], self.calls_of_a_beat(OTHER_SESSION))

    def test_a_beat_from_the_managers_session_reads_only_the_epic_it_manages(self):
        calls = self.calls_of_a_beat(MANAGER_SESSION)

        self.assertEqual([["show", self.epic, "--json"]], calls)
        self.assertGreaterEqual(self.beat_time(), int(time.time()) - FRESH_SECONDS)
