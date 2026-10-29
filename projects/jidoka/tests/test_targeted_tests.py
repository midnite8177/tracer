import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
TARGETED_TESTS = PLUGIN / "scripts" / "targeted_tests.py"
SETTINGS_SCRIPT = PLUGIN / "scripts" / "repo_settings.py"

TESTS_FAILED_EXIT_CODE = 3
FILTER_REFUSED_EXIT_CODE = 4
NO_TEST_MATCHES = ("[xUnit.net 00:00:00.07] Shop.Tests: Exception filtering tests: Incorrect format for "
                   "TestCaseFilter Error: Invalid Condition 'FullyQualifiedName~FullyQualifiedName~Cart'\n"
                   "No test matches the given testcase filter `FullyQualifiedName~FullyQualifiedName~Cart` "
                   "in /shop/Shop.Tests/bin/Debug/net10.0/Shop.Tests.dll")
THIRTY_THREE_PASSED = ("Passed!  - Failed:     0, Passed:    33, Skipped:     0, Total:    33, Duration: 18 ms "
                       "- Shop.Tests.dll (net10.0)")
RUN_TIMEOUT_SECONDS = 120
WINDOW_TESTS = {"name": "window tests", "exclusion": "FullyQualifiedName!~WindowTests",
                "command": "dotnet test Shop.Tests --filter FullyQualifiedName~WindowTests",
                "reason": "they take keyboard focus"}

RUNNER = """\
import json, os, subprocess, sys
from pathlib import Path
folder = Path(sys.argv[1])
name = Path.cwd().name
with open(folder / f"{name}.log", "a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[2:]) + "\\n")
mover = folder / f"move-main-{name}"
if mover.exists():
    repo = mover.read_text(encoding="utf-8").strip()
    mover.unlink()
    (Path(repo) / f"moved-{name}.txt").write_text("moved\\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Move main"], cwd=repo, check=True)
codes = folder / f"exit-codes-{name}"
code = 0
if codes.exists():
    lines = codes.read_text(encoding="utf-8").split()
    code = int(lines[0])
    codes.write_text("\\n".join(lines[1:]), encoding="utf-8")
outputs = folder / f"outputs-{name}"
if outputs.exists():
    queued = json.loads(outputs.read_text(encoding="utf-8"))
    if queued:
        print(queued[0])
        outputs.write_text(json.dumps(queued[1:]), encoding="utf-8")
print("runner output", code)
sys.exit(code)
"""


@dataclass(frozen=True)
class Bead:
    id: str
    worktree: Path


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


class TargetedTestsCase(unittest.TestCase):
    """The shop repo, its repo settings, the fake bd first on the script's PATH, and the helpers of the targeted tests
    script tests.

    Each subclass sets up its own.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.runs = cls.root / "runs"
        cls.runs.mkdir()
        cls.runner = cls.root / "runner.py"
        cls.runner.write_text(RUNNER, encoding="utf-8")
        cls.home = cls.make_home("jidoka-home")
        cls.bare_home = cls.make_home("jidoka-home-without-settings")

        cls.repo = cls.root / "shop"
        fixture.init_repo(cls.repo)
        (cls.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(cls.repo, "Start")
        git(cls.repo, "branch", "-M", "main")
        cls.bin = cls.root / "bin"
        cls.bd = str(fixture.add_fake_beads(cls.repo, cls.bin))
        cls.test_command = f'"{sys.executable}" "{cls.runner}" "{cls.runs}"'
        cls.write_settings()
        cls.count = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def make_home(cls, name: str) -> Path:
        home = cls.root / name
        home.mkdir()
        (home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        return home

    @classmethod
    def write_settings(cls) -> None:
        settings = {
            "lap_test_scope": "targeted",
            "worker_commands": ["python3 -m unittest"],
            "slot_use": None,
            "lap_limit": 3,
            "apps": [
                {"name": "shop", "kind": "program", "way_in": "its command line", "build": "true",
                 "run": None, "test": cls.test_command, "test_full": None, "test_target": "-k <name>",
                 "hand_run": []},
                {"name": "untargeted", "kind": "library", "way_in": "its public API", "build": None,
                 "run": None, "test": cls.test_command, "test_full": None, "test_target": "--all",
                 "hand_run": []},
                {"name": "dotnet-shop", "kind": "program", "way_in": "its web pages", "build": "true",
                 "run": None, "test": cls.test_command, "test_full": None,
                 "test_target": "--filter FullyQualifiedName~<name>", "hand_run": []},
                {"name": "bare", "kind": "library", "way_in": "its public API", "build": None,
                 "run": None, "test": cls.test_command, "test_full": None, "test_target": "<name>",
                 "hand_run": []},
                {"name": "windowed-shop", "kind": "program", "way_in": "its windows", "build": "true",
                 "run": None, "test": cls.test_command, "test_full": '--filter "FullyQualifiedName!~WindowTests"',
                 "test_target": '--filter "FullyQualifiedName~<name>&FullyQualifiedName!~WindowTests"',
                 "hand_run": [WINDOW_TESTS]},
                {"name": "single-quoted-shop", "kind": "program", "way_in": "its web pages", "build": "true",
                 "run": None, "test": cls.test_command, "test_full": None,
                 "test_target": "--filter 'FullyQualifiedName~<name>'", "hand_run": []},
                {"name": "editor", "kind": "program", "way_in": "its windows", "build": "true",
                 "run": None, "test": None, "test_full": None, "test_target": None, "hand_run": []},
            ],
        }
        done = subprocess.run([str(LAUNCHER), str(SETTINGS_SCRIPT), "write"], input=json.dumps(settings),
                              capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "JIDOKA_HOME": str(cls.home)}, cwd=cls.repo)
        if done.returncode != 0:
            raise fixture.FixtureError(done.stderr)

    def new_bead(self) -> Bead:
        """A bead with a worktree on its own branch that adds one file."""
        type(self).count += 1
        n = type(self).count
        created = json.loads(fixture.run([self.bd, "create", "--title", f"Greeting {n}", "--type=task",
                                          "--json"], self.repo))
        worktree = self.root / f"shop-{n}"
        git(self.repo, "worktree", "add", "-q", "-b", f"bead-{n}", str(worktree))
        (worktree / f"greeting-{n}.txt").write_text("hello\n", encoding="utf-8")
        fixture.git_commit_all(worktree, "Add the greeting")
        return Bead(created["id"], worktree)

    def queue_exit_codes(self, bead: Bead, *codes: int) -> None:
        (self.runs / f"exit-codes-{bead.worktree.name}").write_text(
            "\n".join(str(code) for code in codes), encoding="utf-8")

    def queue_outputs(self, bead: Bead, *outputs: str) -> None:
        (self.runs / f"outputs-{bead.worktree.name}").write_text(json.dumps(outputs), encoding="utf-8")

    def move_main_during_the_next_run(self, bead: Bead) -> None:
        (self.runs / f"move-main-{bead.worktree.name}").write_text(str(self.repo), encoding="utf-8")

    def runs_of(self, bead: Bead) -> list[str]:
        log = self.runs / f"{bead.worktree.name}.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def targeted_tests(self, bead: Bead, app: str, test_filter: str, home: Path) -> subprocess.CompletedProcess:
        return self.targeted_tests_on(bead, app, test_filter, home, "main")

    def targeted_tests_on(self, bead: Bead, app: str, test_filter: str, home: Path,
                          base: str, *flags: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(LAUNCHER), str(TARGETED_TESTS), "--bead", bead.id,
                               "--worktree", str(bead.worktree), "--base", base, "--app", app,
                               "--filter", test_filter, "--jidoka-home", str(home), *flags],
                              capture_output=True, text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS,
                              env={**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(home)},
                              cwd=self.root)

    def metadata(self, bead: Bead) -> dict:
        shown = json.loads(fixture.run([self.bd, "show", bead.id, "--json"], self.repo))[0]
        return {key: value for key, value in (shown.get("metadata") or {}).items() if key.startswith("tests.")}

    def comments(self, bead: Bead) -> list[str]:
        listed = json.loads(fixture.run([self.bd, "comments", bead.id, "--json"], self.repo) or "[]")
        return [comment["text"] for comment in listed or []]

    def main_head(self) -> str:
        return git(self.repo, "rev-parse", "main")


class RecordedRunTests(TargetedTestsCase):
    def test_a_passing_run_posts_the_exact_command_and_records_a_pass_on_the_bead(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "shop", "test_greeting", self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        command = f"{self.test_command} -k test_greeting"
        self.assertEqual(["-k test_greeting"], self.runs_of(bead))
        self.assertEqual({"tests.command": command, "tests.base": self.main_head(), "tests.result": "pass"},
                         self.metadata(bead))
        [comment] = self.comments(bead)
        self.assertIn(f"\n{command}\n", f"\n{comment}\n")
        self.assertIn("passed", comment)
        self.assertIn(self.main_head(), comment)

    def test_a_failing_run_posts_the_command_and_records_a_failure_on_the_bead(self):
        bead = self.new_bead()
        self.queue_exit_codes(bead, 1)

        done = self.targeted_tests(bead, "shop", "test_greeting", self.home)

        self.assertEqual(TESTS_FAILED_EXIT_CODE, done.returncode, done.stderr)
        self.assertIn("runner output 1", done.stdout)
        command = f"{self.test_command} -k test_greeting"
        self.assertEqual({"tests.command": command, "tests.base": self.main_head(), "tests.result": "fail"},
                         self.metadata(bead))
        [comment] = self.comments(bead)
        self.assertIn(f"\n{command}\n", f"\n{comment}\n")
        self.assertIn("failed with exit code 1", comment)

    def test_the_tests_run_on_the_worktrees_head_merged_with_mains_head(self):
        bead = self.new_bead()
        (self.repo / f"other-{self.count}.txt").write_text("other work\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Add other work")
        branch_head = git(bead.worktree, "rev-parse", "HEAD")

        done = self.targeted_tests(bead, "shop", "test_greeting", self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["-k test_greeting"], self.runs_of(bead))
        self.assertEqual(f"{branch_head} {self.main_head()}", git(bead.worktree, "log", "-1", "--format=%P"))
        self.assertEqual(self.main_head(), self.metadata(bead)["tests.base"])

    def test_when_main_moves_during_the_run_it_merges_again_and_reruns_once_and_records_the_rerun(self):
        bead = self.new_bead()
        first_base = self.main_head()
        self.queue_exit_codes(bead, 1, 0)
        self.move_main_during_the_next_run(bead)

        done = self.targeted_tests(bead, "shop", "test_greeting", self.home)

        moved = self.main_head()
        self.assertNotEqual(first_base, moved)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["-k test_greeting", "-k test_greeting"], self.runs_of(bead))
        self.assertEqual(moved, git(bead.worktree, "log", "-1", "--format=%P").split()[1])
        self.assertEqual({"tests.command": f"{self.test_command} -k test_greeting", "tests.base": moved,
                          "tests.result": "pass"}, self.metadata(bead))
        [comment] = self.comments(bead)
        self.assertIn(moved, comment)
        self.assertIn("passed", comment)


class BaseBranchTests(TargetedTestsCase):
    def test_the_tests_run_on_the_worktree_merged_with_the_base_branch_named_and_record_its_head(self):
        bead = self.new_bead()
        type(self).count += 1
        base = f"epic/greeting-{self.count}"
        git(self.repo, "branch", base, "main")
        tree = git(self.repo, "rev-parse", "main^{tree}")
        base_head = git(self.repo, "commit-tree", tree, "-p", base, "-m", "Work on the epic")
        git(self.repo, "update-ref", f"refs/heads/{base}", base_head)
        branch_head = git(bead.worktree, "rev-parse", "HEAD")
        main_before = self.main_head()

        done = self.targeted_tests_on(bead, "shop", "test_greeting", self.home, base)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(f"{branch_head} {base_head}", git(bead.worktree, "log", "-1", "--format=%P"))
        self.assertEqual(base_head, self.metadata(bead)["tests.base"])
        self.assertEqual(main_before, self.main_head())
        [comment] = self.comments(bead)
        self.assertIn(f"merged with {base} at {base_head}", comment)

    def test_with_rebase_the_worktree_is_rebased_onto_the_base_branch_and_the_comment_says_so(self):
        bead = self.new_bead()
        (self.repo / f"other-{self.count}.txt").write_text("other work\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Add other work")

        done = self.targeted_tests_on(bead, "shop", "test_greeting", self.home, "main", "--rebase")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(self.main_head(), git(bead.worktree, "rev-parse", "HEAD~1"))
        self.assertEqual(self.main_head(), self.metadata(bead)["tests.base"])
        [comment] = self.comments(bead)
        self.assertIn(f"rebased onto main at {self.main_head()}", comment)

    def test_a_conflict_rebasing_stops_the_run_names_the_file_and_leaves_the_worktree_as_it_was(self):
        bead = self.new_bead()
        (self.repo / f"greeting-{self.count}.txt").write_text("a different hello\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Add a different greeting")
        branch_head = git(bead.worktree, "rev-parse", "HEAD")

        done = self.targeted_tests_on(bead, "shop", "test_greeting", self.home, "main", "--rebase")

        self.assertEqual(1, done.returncode)
        self.assertIn("rebasing main conflicts", done.stderr)
        self.assertIn(f"greeting-{self.count}.txt", done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))
        self.assertEqual(branch_head, git(bead.worktree, "rev-parse", "HEAD"))
        self.assertEqual(f"bead-{self.count}", git(bead.worktree, "branch", "--show-current"))
        self.assertEqual("", git(bead.worktree, "status", "--porcelain"))

    def test_a_base_branch_that_does_not_exist_is_refused_and_nothing_runs(self):
        bead = self.new_bead()

        done = self.targeted_tests_on(bead, "shop", "test_greeting", self.home, "epic/gone")

        self.assertEqual(1, done.returncode)
        self.assertIn("no branch epic/gone", done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))


class RefusedRunTests(TargetedTestsCase):
    def test_a_conflict_with_main_stops_the_run_names_the_file_and_records_nothing(self):
        bead = self.new_bead()
        (self.repo / f"greeting-{self.count}.txt").write_text("a different hello\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Add a different greeting")
        branch_head = git(bead.worktree, "rev-parse", "HEAD")

        done = self.targeted_tests(bead, "shop", "test_greeting", self.home)

        self.assertEqual(1, done.returncode)
        self.assertIn("conflict", done.stderr)
        self.assertIn(f"greeting-{self.count}.txt", done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))
        self.assertEqual([], self.comments(bead))
        self.assertEqual(branch_head, git(bead.worktree, "rev-parse", "HEAD"))
        self.assertEqual("", git(bead.worktree, "status", "--porcelain"))

    def test_an_app_the_repo_settings_do_not_name_is_refused_and_nothing_runs(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "kiosk", "test_greeting", self.home)

        self.assertEqual(1, done.returncode)
        self.assertIn("kiosk", done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))

    def test_an_app_with_no_test_command_is_refused_with_the_bench_and_onboarding_before_main_is_merged(self):
        bead = self.new_bead()
        (self.repo / f"other-{self.count}.txt").write_text("other work\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Add other work")
        branch_head = git(bead.worktree, "rev-parse", "HEAD")

        done = self.targeted_tests(bead, "editor", "test_greeting", self.home)

        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("editor has no test command. Build a test project for it at the bench, then run "
                      "/jidoka:onboard to record its command.", done.stderr)
        self.assertNotIn("running:", done.stdout)
        self.assertEqual(branch_head, git(bead.worktree, "rev-parse", "HEAD"))
        self.assertEqual({}, self.metadata(bead))
        self.assertEqual([], self.comments(bead))

    def test_a_test_target_without_a_placeholder_is_refused_and_nothing_runs(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "untargeted", "test_greeting", self.home)

        self.assertEqual(1, done.returncode)
        self.assertIn("placeholder", done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))

    def test_an_app_whose_stored_settings_lack_test_full_and_hand_run_is_refused_with_a_pointer_to_onboarding(self):
        bead = self.new_bead()
        stale_home = self.root / f"jidoka-home-with-stale-settings-{self.count}"
        shutil.copytree(self.home, stale_home)
        [stored] = (stale_home / "repos").iterdir()
        settings = json.loads(stored.read_text(encoding="utf-8"))
        for key in ("test_full", "hand_run"):
            del settings["apps"][0][key]
        stored.write_text(json.dumps(settings), encoding="utf-8")

        done = self.targeted_tests(bead, "shop", "test_greeting", stale_home)

        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("test_full", done.stderr)
        self.assertIn("hand_run", done.stderr)
        self.assertIn("Run /jidoka:onboard", done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))

    def test_stored_settings_that_lack_untested_apps_are_refused_with_a_pointer_to_onboarding(self):
        bead = self.new_bead()
        stale_home = self.root / f"jidoka-home-without-untested-apps-{self.count}"
        shutil.copytree(self.home, stale_home)
        [stored] = (stale_home / "repos").iterdir()
        settings = json.loads(stored.read_text(encoding="utf-8"))
        del settings["untested_apps"]
        stored.write_text(json.dumps(settings), encoding="utf-8")

        done = self.targeted_tests(bead, "shop", "test_greeting", stale_home)

        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("untested_apps", done.stderr)
        self.assertIn("Run /jidoka:onboard", done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))

    def test_a_repo_with_no_settings_is_refused_with_a_pointer_to_onboarding(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "shop", "test_greeting", self.bare_home)

        self.assertEqual(1, done.returncode)
        self.assertIn("/jidoka:onboard", done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))


class FilterTests(TargetedTestsCase):
    def test_a_filter_that_repeats_the_text_before_the_placeholder_is_refused_with_the_filter_to_pass(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "dotnet-shop", "FullyQualifiedName~BindAddressTests", self.home)

        self.assertEqual(FILTER_REFUSED_EXIT_CODE, done.returncode, done.stderr)
        self.assertIn('pass "BindAddressTests"', done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))
        self.assertEqual([], self.comments(bead))

    def test_a_filter_that_repeats_a_whole_test_target_prefix_with_its_space_is_refused(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "shop", "-k test_greeting", self.home)

        self.assertEqual(FILTER_REFUSED_EXIT_CODE, done.returncode, done.stderr)
        self.assertIn('pass "test_greeting"', done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))

    def test_a_plain_filter_runs_inside_a_test_target_that_puts_text_before_its_placeholder(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "dotnet-shop", "BindAddressTests", self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["--filter FullyQualifiedName~BindAddressTests"], self.runs_of(bead))
        self.assertEqual("pass", self.metadata(bead)["tests.result"])

    def test_a_filter_runs_inside_a_test_target_that_leaves_out_the_hand_run_tests(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "windowed-shop", "Cart", self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["--filter FullyQualifiedName~Cart&FullyQualifiedName!~WindowTests"], self.runs_of(bead))
        self.assertEqual("pass", self.metadata(bead)["tests.result"])

    def test_a_filter_with_a_pipe_reaches_the_test_command_whole_when_the_placeholder_is_unquoted(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "dotnet-shop", "A|B", self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["--filter FullyQualifiedName~A|B"], self.runs_of(bead))
        self.assertEqual("pass", self.metadata(bead)["tests.result"])

    def test_a_filter_with_shell_characters_reaches_the_test_command_whole_inside_double_quotes(self):
        bead = self.new_bead()
        hostile = 'A|B "C" $HOME `id` \\ ; $(id)'

        done = self.targeted_tests(bead, "windowed-shop", hostile, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([f"--filter FullyQualifiedName~{hostile}&FullyQualifiedName!~WindowTests"],
                         self.runs_of(bead))

    def test_a_filter_with_a_single_quote_reaches_the_test_command_whole_inside_single_quotes(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "single-quoted-shop", "A|B's $HOME", self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["--filter FullyQualifiedName~A|B's $HOME"], self.runs_of(bead))

    def test_any_filter_runs_when_the_test_target_is_only_the_placeholder(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "bare", "FullyQualifiedName~BindAddressTests", self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["FullyQualifiedName~BindAddressTests"], self.runs_of(bead))
        self.assertEqual("pass", self.metadata(bead)["tests.result"])


class NoTestsExecutedTests(TargetedTestsCase):
    def test_a_run_whose_output_says_no_test_matches_the_filter_is_refused_and_records_nothing(self):
        bead = self.new_bead()
        self.queue_outputs(bead, NO_TEST_MATCHES)

        done = self.targeted_tests(bead, "dotnet-shop", "Cart", self.home)

        self.assertEqual(FILTER_REFUSED_EXIT_CODE, done.returncode, done.stderr)
        self.assertIn("executed no tests", done.stderr)
        self.assertIn("--filter 'Cart'", done.stderr)
        self.assertIn("--filter FullyQualifiedName~<name>", done.stderr)
        self.assertEqual(["--filter FullyQualifiedName~Cart"], self.runs_of(bead))
        self.assertNotIn("hand-run", done.stderr)
        self.assertEqual({}, self.metadata(bead))
        self.assertEqual([], self.comments(bead))

    def test_a_run_that_executed_no_tests_names_the_hand_run_groups_the_test_target_leaves_out(self):
        bead = self.new_bead()
        self.queue_outputs(bead, NO_TEST_MATCHES)

        done = self.targeted_tests(bead, "windowed-shop", "WindowTests", self.home)

        self.assertEqual(FILTER_REFUSED_EXIT_CODE, done.returncode, done.stderr)
        self.assertIn("executed no tests", done.stderr)
        self.assertIn("window tests", done.stderr)
        self.assertIn("they take keyboard focus", done.stderr)
        self.assertIn("dotnet test Shop.Tests --filter FullyQualifiedName~WindowTests", done.stderr)
        self.assertEqual({}, self.metadata(bead))
        self.assertEqual([], self.comments(bead))

    def test_a_run_where_one_assembly_matches_no_test_and_another_runs_tests_records_a_pass(self):
        bead = self.new_bead()
        self.queue_outputs(bead, f"{NO_TEST_MATCHES}\n{THIRTY_THREE_PASSED}")

        done = self.targeted_tests(bead, "dotnet-shop", "Cart", self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("pass", self.metadata(bead)["tests.result"])

    def test_a_unittest_run_that_ran_no_tests_is_refused_and_records_nothing(self):
        bead = self.new_bead()
        self.queue_exit_codes(bead, 5)
        self.queue_outputs(bead, "\n----------------------------------------------------------------------\n"
                                 "Ran 0 tests in 0.000s\n\nNO TESTS RAN")

        done = self.targeted_tests(bead, "shop", "test_nothing", self.home)

        self.assertEqual(FILTER_REFUSED_EXIT_CODE, done.returncode, done.stderr)
        self.assertIn("executed no tests", done.stderr)
        self.assertEqual({}, self.metadata(bead))
        self.assertEqual([], self.comments(bead))

    def test_a_unittest_run_that_ran_tests_and_failed_records_a_failure(self):
        bead = self.new_bead()
        self.queue_exit_codes(bead, 1)
        self.queue_outputs(bead, "Ran 3 tests in 0.004s\n\nFAILED (failures=1)")

        done = self.targeted_tests(bead, "shop", "test_greeting", self.home)

        self.assertEqual(TESTS_FAILED_EXIT_CODE, done.returncode, done.stderr)
        self.assertEqual("fail", self.metadata(bead)["tests.result"])

    def test_a_rerun_after_main_moved_that_executed_no_tests_is_refused_and_records_nothing(self):
        bead = self.new_bead()
        self.queue_outputs(bead, THIRTY_THREE_PASSED, NO_TEST_MATCHES)
        self.move_main_during_the_next_run(bead)

        done = self.targeted_tests(bead, "dotnet-shop", "Cart", self.home)

        self.assertEqual(FILTER_REFUSED_EXIT_CODE, done.returncode, done.stderr)
        self.assertIn("executed no tests", done.stderr)
        self.assertEqual(2, len(self.runs_of(bead)))
        self.assertEqual({}, self.metadata(bead))
        self.assertEqual([], self.comments(bead))


if __name__ == "__main__":
    unittest.main()
