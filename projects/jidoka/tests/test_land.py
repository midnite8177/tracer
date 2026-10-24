import json
import os
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
LAND = PLUGIN / "scripts" / "land.py"
SETTINGS_SCRIPT = PLUGIN / "scripts" / "repo_settings.py"

MESSAGE = "Add the greeting\n\nThe greeting is printed once at startup."
DIRTY_EXIT_CODE = 3
PARTLY_LANDED_EXIT_CODE = 4
FULL_SUITE_FAILED_EXIT_CODE = 5
LOCK_LINE_SECONDS = 30
LANDING_TIMEOUT_SECONDS = 120
LOCK = "locks/merge.lock"

RUNNER = """\
import sys
with open(sys.argv[1], "a", encoding="utf-8") as marker:
    marker.write("ran\\n")
print("runner output", sys.argv[2])
sys.exit(int(sys.argv[2]))
"""

SUITE_RUNNER = """\
import json, os, sys
from pathlib import Path
folder, suite = Path(sys.argv[1]), sys.argv[2]
tree = Path.cwd()
with open(folder / f"{tree.name}.log", "a", encoding="utf-8") as log:
    log.write(json.dumps({"suite": suite, "cwd": str(tree), "files": sorted(os.listdir(tree))}) + "\\n")
code_file = folder / f"exit-{suite}-{tree.name}"
code = int(code_file.read_text(encoding="utf-8")) if code_file.exists() else 0
print(f"{suite} suite output {code}")
sys.exit(code)
"""


BD_WRAPPER = """\
import subprocess, sys
args = sys.argv[1:]
if args[:1] == [{subcommand!r}]:
    if {garbage!r}:
        print("this is not json")
        sys.exit(0)
    print("the wrapper refuses this call", file=sys.stderr)
    sys.exit(1)
sys.exit(subprocess.run([{real!r}, *args]).returncode)
"""


@dataclass(frozen=True)
class Bead:
    id: str
    branch: str
    worktree: Path
    marker: Path


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


def first_line_within(stream, seconds: float) -> str | None:
    """Reads one line from the stream, or returns None when none arrives in time."""
    lines: list[str] = []
    reader = threading.Thread(target=lambda: lines.append(stream.readline()), daemon=True)
    reader.start()
    reader.join(seconds)
    return lines[0] if lines else None


class LandingCase(unittest.TestCase):
    """The shop repo, its repo settings and the helpers of the landing tests; each subclass sets up its own."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.home = cls.root / "jidoka-home"
        cls.home.mkdir()
        (cls.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        cls.runner = cls.root / "runner.py"
        cls.runner.write_text(RUNNER, encoding="utf-8")
        cls.suite_runner = cls.root / "suite_runner.py"
        cls.suite_runner.write_text(SUITE_RUNNER, encoding="utf-8")
        cls.suite_runs = cls.root / "suite-runs"
        cls.suite_runs.mkdir()
        cls.bare_home = cls.root / "jidoka-home-without-settings"
        cls.bare_home.mkdir()
        (cls.bare_home / "python").write_text(sys.executable + "\n", encoding="utf-8")

        cls.repo = cls.root / "shop"
        fixture.init_repo(cls.repo)
        (cls.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(cls.repo, "Start")
        git(cls.repo, "branch", "-M", "main")
        cls.bd = fixture.real_tool("bd")
        fixture.add_stealth_beads(cls.repo)
        cls.write_settings()
        cls.count = 0

    def setUp(self):
        self.bd_in_front: Path | None = None
        self.jidoka_home = self.home

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def suite_command(cls, suite: str) -> str:
        return f'"{sys.executable}" "{cls.suite_runner}" "{cls.suite_runs}" {suite}'

    @classmethod
    def write_settings(cls) -> None:
        """Repo settings with two apps, shop then kiosk, whose test commands are the suite runner."""
        settings = {
            "lap_test_scope": "targeted",
            "worker_commands": [],
            "slot_use": None,
            "lap_limit": 3,
            "apps": [
                {"name": "shop", "kind": "program", "way_in": "its command line", "build": None,
                 "run": None, "test": cls.suite_command("shop"), "test_target": "-k <name>"},
                {"name": "kiosk", "kind": "library", "way_in": "its public API", "build": "true",
                 "run": None, "test": cls.suite_command("kiosk"), "test_target": "-k <name>"},
            ],
        }
        done = subprocess.run([str(LAUNCHER), str(SETTINGS_SCRIPT), "write"], input=json.dumps(settings),
                              capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "JIDOKA_HOME": str(cls.home)}, cwd=cls.repo)
        if done.returncode != 0:
            raise fixture.FixtureError(done.stderr)

    def new_bead(self, tests_result: str | None) -> Bead:
        """A bead with a branch and a worktree that adds two files; tests_result None records no tests.

        The recorded command marks the bead's marker file each time it runs.
        """
        type(self).count += 1
        n = type(self).count
        created = json.loads(fixture.run([self.bd, "create", "--title", f"Greeting {n}", "--type=task",
                                          "--json"], self.repo))
        bead_id = created["id"]
        marker = self.root / f"marker-{n}"
        command = f'"{sys.executable}" "{self.runner}" "{marker}" 0'
        if tests_result is not None:
            fixture.run([self.bd, "update", bead_id,
                         "--set-metadata", f"tests.command={command}",
                         "--set-metadata", f"tests.base={git(self.repo, 'rev-parse', 'main')}",
                         "--set-metadata", f"tests.result={tests_result}"], self.repo)
        branch = f"bead-{n}"
        worktree = self.root / f"shop-{n}"
        git(self.repo, "worktree", "add", "-q", "-b", branch, str(worktree))
        for step in (1, 2):
            (worktree / f"greeting-{n}-{step}.txt").write_text(f"hello {step}\n", encoding="utf-8")
            fixture.git_commit_all(worktree, f"Work in progress {step}")
        return Bead(bead_id, branch, worktree, marker)

    def put_bd_in_front(self, subcommand: str, garbage: bool) -> None:
        """Puts a bd first on the PATH that passes every call to the real bd except the subcommand named.

        That one call prints garbage when garbage is true and fails otherwise.
        """
        folder = self.root / f"bd-in-front-{type(self).count}-{subcommand}"
        folder.mkdir()
        wrapper = folder / "bd"
        fixture.write_executable(wrapper, f"#!{sys.executable}\n" +
                                 BD_WRAPPER.format(subcommand=subcommand, garbage=garbage, real=self.bd))
        self.bd_in_front = folder

    def start_land(self, bead: Bead, message: str) -> subprocess.Popen:
        path = os.environ["PATH"]
        if self.bd_in_front is not None:
            path = str(self.bd_in_front) + os.pathsep + path
        env = {**os.environ, "JIDOKA_HOME": str(self.jidoka_home), "PATH": path}
        inside_repo = bead.worktree if bead.worktree.exists() else self.repo
        return subprocess.Popen([str(LAUNCHER), str(LAND), "--repo", str(inside_repo), "--bead", bead.id,
                                 "--branch", bead.branch, "--worktree", str(bead.worktree),
                                 "--message", message, "--jidoka-home", str(self.jidoka_home)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                env=env, cwd=self.root)

    def land(self, bead: Bead, message: str) -> subprocess.CompletedProcess:
        process = self.start_land(bead, message)
        out, err = process.communicate(timeout=LANDING_TIMEOUT_SECONDS)
        return subprocess.CompletedProcess(process.args, process.returncode, out, err)

    def clean_main_checkout(self) -> None:
        git(self.repo, "reset", "-q", "--hard", "HEAD")
        git(self.repo, "clean", "-fdq")

    def shown(self, bead_id: str) -> dict:
        return json.loads(fixture.run([self.bd, "show", bead_id, "--json"], self.repo))[0]

    def move_main(self, name: str, text: str) -> str:
        """Commits a file directly on main, as other work landing would, and returns main's new head."""
        (self.repo / name).write_text(text, encoding="utf-8")
        fixture.git_commit_all(self.repo, f"Add {name}")
        return git(self.repo, "rev-parse", "main")

    def tip(self, bead: Bead) -> str:
        return git(self.repo, "rev-parse", bead.branch)

    def assert_nothing_landed(self, bead: Bead, head: str) -> None:
        self.assertEqual(head, git(self.repo, "rev-parse", "main"))
        self.assertTrue(bead.worktree.is_dir())
        self.assertIn(bead.branch, git(self.repo, "branch", "--list"))
        self.assertEqual("open", self.shown(bead.id)["status"])
        self.assertFalse((self.home / LOCK).exists())

    def main_count(self) -> int:
        return int(git(self.repo, "rev-list", "--count", "main"))

    def fail_suite(self, bead: Bead, suite: str, exit_code: int) -> None:
        (self.suite_runs / f"exit-{suite}-{bead.worktree.name}").write_text(str(exit_code), encoding="utf-8")

    def suite_runs_of(self, bead: Bead) -> list[dict]:
        log = self.suite_runs / f"{bead.worktree.name}.log"
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


class LandingTests(LandingCase):
    def test_landing_puts_the_branch_on_main_as_one_commit_with_the_given_message(self):
        bead = self.new_bead("pass")
        before = self.main_count()

        done = self.land(bead, MESSAGE)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(before + 1, self.main_count())
        self.assertEqual("", git(self.repo, "rev-list", "--merges", "main"))
        self.assertEqual(MESSAGE, git(self.repo, "log", "-1", "--format=%B", "main"))
        self.assertTrue((self.repo / f"greeting-{self.count}-1.txt").is_file())
        self.assertTrue((self.repo / f"greeting-{self.count}-2.txt").is_file())
        self.assertIn(git(self.repo, "rev-parse", "main"), done.stdout)

    def test_landing_closes_the_bead_naming_the_commit_and_removes_its_worktree_and_branch(self):
        bead = self.new_bead("pass")

        done = self.land(bead, MESSAGE)

        self.assertEqual(0, done.returncode, done.stderr)
        shown = self.shown(bead.id)
        self.assertEqual("closed", shown["status"])
        self.assertEqual(f"{git(self.repo, 'rev-parse', 'main')}: Add the greeting", shown["close_reason"])
        self.assertFalse(bead.worktree.exists())
        self.assertNotIn(bead.branch, git(self.repo, "branch", "--list"))
        self.assertNotIn(str(bead.worktree), git(self.repo, "worktree", "list"))

    def test_a_branch_with_no_work_of_its_own_on_main_is_not_taken_for_a_landed_one(self):
        bead = self.new_bead("pass")
        git(bead.worktree, "reset", "--hard", "-q", "main")
        head = git(self.repo, "rev-parse", "main")

        done = self.land(bead, "Land nothing at all")

        self.assertNotEqual(0, done.returncode)
        self.assertEqual(head, git(self.repo, "rev-parse", "main"))
        self.assertEqual("open", self.shown(bead.id)["status"])


class RefusedMessageTests(LandingCase):
    def test_a_message_that_holds_the_beads_own_id_is_refused_before_anything_changes(self):
        bead = self.new_bead("pass")
        head = git(self.repo, "rev-parse", "main")
        tip = self.tip(bead)

        done = self.land(bead, f"Add the greeting for {bead.id}")

        self.assertNotEqual(0, done.returncode)
        self.assertIn(bead.id, done.stderr)
        self.assert_nothing_landed(bead, head)
        self.assertEqual(tip, self.tip(bead))

    def test_a_message_that_holds_the_id_of_another_bead_in_the_tracker_is_refused(self):
        bead = self.new_bead("pass")
        other = json.loads(fixture.run([self.bd, "create", "--title", "Another", "--type=task", "--json"],
                                       self.repo))["id"]
        head = git(self.repo, "rev-parse", "main")
        tip = self.tip(bead)

        done = self.land(bead, f"Follow up on {other}")

        self.assertNotEqual(0, done.returncode)
        self.assertIn(other, done.stderr)
        self.assert_nothing_landed(bead, head)
        self.assertEqual(tip, self.tip(bead))

    def test_a_message_that_holds_the_id_of_a_closed_bead_is_refused(self):
        bead = self.new_bead("pass")
        other = json.loads(fixture.run([self.bd, "create", "--title", "Finished", "--type=task", "--json"],
                                       self.repo))["id"]
        fixture.run([self.bd, "close", other, "--reason", "done"], self.repo)

        done = self.land(bead, f"Follow up on {other}")

        self.assertNotEqual(0, done.returncode)
        self.assertIn(other, done.stderr)

    def test_an_empty_message_is_refused_before_anything_changes(self):
        bead = self.new_bead("pass")
        head = git(self.repo, "rev-parse", "main")

        done = self.land(bead, "  \n")

        self.assertNotEqual(0, done.returncode)
        self.assertIn("message is empty", done.stderr)
        self.assert_nothing_landed(bead, head)


class AcceptedMessageTests(LandingCase):
    def test_a_message_with_a_word_shaped_like_an_id_that_is_not_a_bead_is_accepted(self):
        bead = self.new_bead("pass")
        prefix = bead.id.rsplit("-", 1)[0]

        done = self.land(bead, f"Fix the {prefix}-ui layout")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(f"Fix the {prefix}-ui layout", git(self.repo, "log", "-1", "--format=%B", "main"))

    def test_a_message_whose_first_line_is_blank_closes_the_bead_with_its_first_written_line(self):
        bead = self.new_bead("pass")

        done = self.land(bead, "\n\nAdd the greeting\n\nMore detail.")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(f"{git(self.repo, 'rev-parse', 'main')}: Add the greeting",
                         self.shown(bead.id)["close_reason"])

    def test_a_message_with_hyphenated_words_that_are_not_bead_ids_is_accepted(self):
        bead = self.new_bead("pass")

        done = self.land(bead, "Make the read-only flag work with a built-in default")

        self.assertEqual(0, done.returncode, done.stderr)


class RecordedTestsAndSettingsTests(LandingCase):
    def test_a_bead_with_no_recorded_tests_is_refused_and_main_is_unchanged(self):
        bead = self.new_bead(None)
        head = git(self.repo, "rev-parse", "main")
        tip = self.tip(bead)

        done = self.land(bead, MESSAGE)

        self.assertNotEqual(0, done.returncode)
        self.assertIn("no tests", done.stderr)
        self.assert_nothing_landed(bead, head)
        self.assertEqual(tip, self.tip(bead))

    def test_a_bead_whose_recorded_tests_failed_is_refused_and_main_is_unchanged(self):
        bead = self.new_bead("fail")
        head = git(self.repo, "rev-parse", "main")
        tip = self.tip(bead)

        done = self.land(bead, MESSAGE)

        self.assertNotEqual(0, done.returncode)
        self.assertIn("did not pass", done.stderr)
        self.assert_nothing_landed(bead, head)
        self.assertEqual(tip, self.tip(bead))

    def test_a_repo_with_no_settings_is_refused_with_a_pointer_to_onboarding_and_nothing_lands(self):
        bead = self.new_bead("pass")
        head = git(self.repo, "rev-parse", "main")
        tip = self.tip(bead)
        self.jidoka_home = self.bare_home

        done = self.land(bead, MESSAGE)

        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("/jidoka:onboard", done.stderr)
        self.assertEqual([], self.suite_runs_of(bead))
        self.assert_nothing_landed(bead, head)
        self.assertEqual(tip, self.tip(bead))


class FullSuiteTests(LandingCase):
    def test_landing_runs_every_apps_full_suite_once_in_app_order_on_the_branch_rebased_on_main(self):
        bead = self.new_bead("pass")
        moved_file = f"other-{self.count}.txt"
        moved = self.move_main(moved_file, "other work\n")
        before = self.main_count()

        done = self.land(bead, MESSAGE)

        self.assertEqual(0, done.returncode, done.stderr)
        runs = self.suite_runs_of(bead)
        self.assertEqual(["shop", "kiosk"], [run["suite"] for run in runs])
        for run in runs:
            self.assertEqual(str(bead.worktree), run["cwd"])
            self.assertIn(moved_file, run["files"])
            self.assertIn(f"greeting-{self.count}-1.txt", run["files"])
        self.assertEqual(before + 1, self.main_count())
        self.assertEqual(moved, git(self.repo, "rev-parse", "main~1"))
        self.assertEqual("", git(self.repo, "rev-list", "--merges", "main"))

    def test_the_full_suite_runs_even_when_main_has_not_moved_since_the_recorded_run(self):
        bead = self.new_bead("pass")

        done = self.land(bead, MESSAGE)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["shop", "kiosk"], [run["suite"] for run in self.suite_runs_of(bead)])

    def test_landing_does_not_run_the_recorded_targeted_command_again(self):
        bead = self.new_bead("pass")
        self.move_main(f"other-{self.count}.txt", "other work\n")

        done = self.land(bead, MESSAGE)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertFalse(bead.marker.exists())

    def test_when_one_apps_full_suite_fails_nothing_lands_and_the_refusal_names_its_command_and_output(self):
        bead = self.new_bead("pass")
        moved = self.move_main(f"other-{self.count}.txt", "other work\n")
        self.fail_suite(bead, "shop", 1)

        done = self.land(bead, MESSAGE)

        self.assertEqual(FULL_SUITE_FAILED_EXIT_CODE, done.returncode, done.stderr)
        self.assertEqual(["shop", "kiosk"], [run["suite"] for run in self.suite_runs_of(bead)])
        self.assertIn(self.suite_command("shop"), done.stderr)
        self.assertIn("shop suite output 1", done.stderr)
        self.assertNotIn(self.suite_command("kiosk"), done.stderr)
        self.assert_nothing_landed(bead, moved)

    def test_when_every_apps_full_suite_fails_the_refusal_names_each_failing_command_with_its_output(self):
        bead = self.new_bead("pass")
        head = git(self.repo, "rev-parse", "main")
        self.fail_suite(bead, "shop", 1)
        self.fail_suite(bead, "kiosk", 2)

        done = self.land(bead, MESSAGE)

        self.assertEqual(FULL_SUITE_FAILED_EXIT_CODE, done.returncode, done.stderr)
        for command, output in ((self.suite_command("shop"), "shop suite output 1"),
                                (self.suite_command("kiosk"), "kiosk suite output 2")):
            self.assertIn(command, done.stderr)
            self.assertIn(output, done.stderr)
        self.assert_nothing_landed(bead, head)


class MainCheckoutTests(LandingCase):
    def test_a_branch_that_conflicts_with_main_stops_the_landing_and_leaves_no_rebase_behind(self):
        bead = self.new_bead("pass")
        branch_head = git(bead.worktree, "rev-parse", "HEAD")
        moved = self.move_main(f"greeting-{self.count}-1.txt", "a different hello\n")

        done = self.land(bead, MESSAGE)

        self.assertNotEqual(0, done.returncode)
        self.assertIn("conflict", done.stderr)
        self.assert_nothing_landed(bead, moved)
        self.assertEqual(branch_head, git(bead.worktree, "rev-parse", "HEAD"))
        self.assertEqual("", git(bead.worktree, "status", "--porcelain"))

    def test_an_untracked_file_in_mains_checkout_that_the_bead_also_adds_stops_the_landing_and_is_named(self):
        bead = self.new_bead("pass")
        head = git(self.repo, "rev-parse", "main")
        tip = self.tip(bead)
        clashing = f"greeting-{self.count}-2.txt"
        (self.repo / clashing).write_text("my own notes\n", encoding="utf-8")
        self.addCleanup(self.clean_main_checkout)

        done = self.land(bead, MESSAGE)

        self.assertEqual(DIRTY_EXIT_CODE, done.returncode, done.stderr)
        self.assertIn(clashing, done.stdout)
        self.assertNotIn(f"greeting-{self.count}-1.txt", done.stdout)
        self.assert_nothing_landed(bead, head)
        self.assertEqual(tip, self.tip(bead))
        self.assertEqual("my own notes\n", (self.repo / clashing).read_text(encoding="utf-8"))

    def test_a_modified_tracked_file_in_mains_checkout_that_the_bead_changes_stops_the_landing(self):
        bead = self.new_bead("pass")
        head = git(self.repo, "rev-parse", "main")
        (bead.worktree / "README.md").write_text("shop, with a greeting\n", encoding="utf-8")
        fixture.git_commit_all(bead.worktree, "Change the readme")
        tip = self.tip(bead)
        (self.repo / "README.md").write_text("shop, edited by hand\n", encoding="utf-8")
        self.addCleanup(self.clean_main_checkout)

        done = self.land(bead, MESSAGE)

        self.assertEqual(DIRTY_EXIT_CODE, done.returncode, done.stderr)
        self.assertIn("README.md", done.stdout)
        self.assert_nothing_landed(bead, head)
        self.assertEqual(tip, self.tip(bead))
        self.assertEqual("shop, edited by hand\n", (self.repo / "README.md").read_text(encoding="utf-8"))

    def test_a_staged_rename_in_mains_checkout_of_a_file_the_bead_changes_stops_the_landing(self):
        legacy = f"legacy-{self.count + 1}.txt"
        self.move_main(legacy, "old text\n")
        bead = self.new_bead("pass")
        head = git(self.repo, "rev-parse", "main")
        (bead.worktree / legacy).write_text("new text\n", encoding="utf-8")
        fixture.git_commit_all(bead.worktree, "Change the legacy file")
        tip = self.tip(bead)
        git(self.repo, "mv", legacy, f"renamed-{self.count}.txt")
        self.addCleanup(self.clean_main_checkout)

        done = self.land(bead, MESSAGE)

        self.assertEqual(DIRTY_EXIT_CODE, done.returncode, done.stderr)
        self.assertIn(legacy, done.stdout)
        self.assert_nothing_landed(bead, head)
        self.assertEqual(tip, self.tip(bead))

    def test_uncommitted_edits_to_files_the_bead_does_not_change_do_not_stop_the_landing(self):
        bead = self.new_bead("pass")
        (self.repo / "README.md").write_text("shop, edited by hand\n", encoding="utf-8")
        (self.repo / f"scratch-{self.count}.txt").write_text("notes\n", encoding="utf-8")
        self.addCleanup(self.clean_main_checkout)

        done = self.land(bead, MESSAGE)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("shop, edited by hand\n", (self.repo / "README.md").read_text(encoding="utf-8"))
        self.assertTrue((self.repo / f"scratch-{self.count}.txt").is_file())
        self.assertTrue((self.repo / f"greeting-{self.count}-1.txt").is_file())


class MergeLockAndRecoveryTests(LandingCase):
    def test_a_second_landing_waits_on_the_merge_lock_until_the_first_finishes(self):
        bead = self.new_bead("pass")
        head = git(self.repo, "rev-parse", "main")
        lock = self.home / LOCK
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("424242\n", encoding="utf-8")
        self.addCleanup(lambda: lock.unlink(missing_ok=True))

        process = self.start_land(bead, MESSAGE)
        try:
            line = first_line_within(process.stdout, LOCK_LINE_SECONDS)
            self.assertIsNotNone(line, "the landing printed nothing while the lock was held")
            self.assertIn("waiting for the merge lock", line)
            self.assertIn("424242", line)
            self.assertIsNone(process.poll())
            self.assertEqual(head, git(self.repo, "rev-parse", "main"))
            lock.unlink()
            out, err = process.communicate(timeout=LANDING_TIMEOUT_SECONDS)
        finally:
            process.kill()
            process.communicate()

        self.assertEqual(0, process.returncode, err)
        self.assertNotEqual(head, git(self.repo, "rev-parse", "main"))
        self.assertFalse(lock.exists())

    def test_when_closing_the_bead_fails_main_has_the_commit_and_a_rerun_finishes_the_closing(self):
        bead = self.new_bead("pass")
        before = self.main_count()
        self.put_bd_in_front("close", garbage=False)

        first = self.land(bead, MESSAGE)

        sha = git(self.repo, "rev-parse", "main")
        self.assertEqual(PARTLY_LANDED_EXIT_CODE, first.returncode, first.stderr)
        self.assertEqual(before + 1, self.main_count())
        self.assertIn(sha, first.stdout)
        self.assertIn("bd close", first.stderr)
        self.assertEqual("open", self.shown(bead.id)["status"])
        self.assertFalse((self.home / LOCK).exists())

        self.bd_in_front = None
        second = self.land(bead, MESSAGE)

        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual(before + 1, self.main_count())
        self.assertEqual(sha, git(self.repo, "rev-parse", "main"))
        self.assertIn(sha, second.stdout)
        shown = self.shown(bead.id)
        self.assertEqual("closed", shown["status"])
        self.assertEqual(f"{sha}: Add the greeting", shown["close_reason"])
        self.assertFalse(bead.worktree.exists())
        self.assertNotIn(bead.branch, git(self.repo, "branch", "--list"))

    def test_output_from_bd_that_is_not_json_stops_the_landing_with_a_clear_message(self):
        bead = self.new_bead("pass")
        head = git(self.repo, "rev-parse", "main")
        tip = self.tip(bead)
        self.put_bd_in_front("show", garbage=True)

        done = self.land(bead, MESSAGE)

        self.assertEqual(1, done.returncode)
        self.assertIn("land:", done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assert_nothing_landed(bead, head)
        self.assertEqual(tip, self.tip(bead))


if __name__ == "__main__":
    unittest.main()
