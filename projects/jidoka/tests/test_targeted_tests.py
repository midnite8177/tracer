import json
import os
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
RUN_TIMEOUT_SECONDS = 120

RUNNER = """\
import os, subprocess, sys
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
print("runner output", code)
sys.exit(code)
"""


@dataclass(frozen=True)
class Bead:
    id: str
    worktree: Path


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


class TargetedTestsTests(unittest.TestCase):
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
        cls.bd = fixture.real_tool("bd")
        fixture.run([cls.bd, "init", "--stealth", "--non-interactive"], cls.repo)
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
                 "run": None, "test": cls.test_command, "test_target": "-k <name>"},
                {"name": "untargeted", "kind": "library", "way_in": "its public API", "build": None,
                 "run": None, "test": cls.test_command, "test_target": "--all"},
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

    def move_main_during_the_next_run(self, bead: Bead) -> None:
        (self.runs / f"move-main-{bead.worktree.name}").write_text(str(self.repo), encoding="utf-8")

    def runs_of(self, bead: Bead) -> list[str]:
        log = self.runs / f"{bead.worktree.name}.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def targeted_tests(self, bead: Bead, app: str, test_filter: str, home: Path) -> subprocess.CompletedProcess:
        return subprocess.run([str(LAUNCHER), str(TARGETED_TESTS), "--bead", bead.id,
                               "--worktree", str(bead.worktree), "--app", app, "--filter", test_filter,
                               "--jidoka-home", str(home)],
                              capture_output=True, text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS,
                              env={**os.environ, "JIDOKA_HOME": str(home)}, cwd=self.root)

    def metadata(self, bead: Bead) -> dict:
        shown = json.loads(fixture.run([self.bd, "show", bead.id, "--json"], self.repo))[0]
        return {key: value for key, value in (shown.get("metadata") or {}).items() if key.startswith("tests.")}

    def comments(self, bead: Bead) -> list[str]:
        listed = json.loads(fixture.run([self.bd, "comments", bead.id, "--json"], self.repo) or "[]")
        return [comment["text"] for comment in listed or []]

    def main_head(self) -> str:
        return git(self.repo, "rev-parse", "main")

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

    def test_an_app_the_repo_settings_do_not_name_is_refused_and_nothing_runs(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "kiosk", "test_greeting", self.home)

        self.assertEqual(1, done.returncode)
        self.assertIn("kiosk", done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))

    def test_a_test_target_without_a_placeholder_is_refused_and_nothing_runs(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "untargeted", "test_greeting", self.home)

        self.assertEqual(1, done.returncode)
        self.assertIn("placeholder", done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))

    def test_a_repo_with_no_settings_is_refused_with_a_pointer_to_onboarding(self):
        bead = self.new_bead()

        done = self.targeted_tests(bead, "shop", "test_greeting", self.bare_home)

        self.assertEqual(1, done.returncode)
        self.assertIn("/jidoka:onboard", done.stderr)
        self.assertEqual([], self.runs_of(bead))
        self.assertEqual({}, self.metadata(bead))


if __name__ == "__main__":
    unittest.main()
