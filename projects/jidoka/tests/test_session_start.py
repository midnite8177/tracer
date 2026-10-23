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
HOOK = PLUGIN / "hooks" / "session_start.py"

RULES = [
    "A jidoka skill's own subagents are authorized",
    "never a bare id",
    'call the Skill tool with "unslop"',
    "Beads stealth mode covers the tracker only",
    "Bead ids and requirement ids never leave the tracker or the spec",
    "Comments describe the code, never the work",
    "Tests assert runtime behavior",
    "Comment cleanup is requested work",
    "Planning, Factory, Acceptance and Bench",
]


def init_committed_repo(repo: Path) -> None:
    fixture.init_repo(repo)
    (repo / "README.md").write_text("shop\n", encoding="utf-8")
    fixture.git_commit_all(repo, "Start")


class SessionStartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name).resolve()
        cls.home = root / "jidoka-home"
        cls.home.mkdir()
        (cls.home / "python").write_text(sys.executable + "\n", encoding="utf-8")

        cls.beads_repo = root / "shop"
        cls.bd = fixture.real_tool("bd")
        init_committed_repo(cls.beads_repo)
        fixture.run([cls.bd, "init", "--stealth", "--non-interactive"], cls.beads_repo)
        (cls.beads_repo / "src" / "deep").mkdir(parents=True)

        cls.worktree = root / "shop-feature"
        fixture.run(["git", "worktree", "add", "-q", "-b", "feature", str(cls.worktree)], cls.beads_repo)

        cls.plain_repo = root / "plain"
        init_committed_repo(cls.plain_repo)

        cls.plain_worktree = root / "plain-feature"
        fixture.run(["git", "worktree", "add", "-q", "-b", "feature", str(cls.plain_worktree)], cls.plain_repo)

        cls.not_a_repo = root / "folder"
        cls.not_a_repo.mkdir()

        cls.beads_folder_above_the_repo = root / "outer"
        (cls.beads_folder_above_the_repo / ".beads").mkdir(parents=True)
        cls.repo_under_it = cls.beads_folder_above_the_repo / "inner"
        init_committed_repo(cls.repo_under_it)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def start(self, stdin: str, process_cwd: Path, path: str) -> subprocess.CompletedProcess:
        env = {"PATH": path, "JIDOKA_HOME": str(self.home), "HOME": str(self.home)}
        return subprocess.run([str(LAUNCHER), str(HOOK)], input=stdin, capture_output=True, text=True,
                              encoding="utf-8", env=env, cwd=process_cwd)

    def session(self, cwd: Path) -> subprocess.CompletedProcess:
        event = {"session_id": "s1", "hook_event_name": "SessionStart", "source": "startup", "cwd": str(cwd)}
        return self.start(json.dumps(event), self.not_a_repo, os.environ["PATH"])

    def printed_paths(self, stdout: str) -> dict:
        paths = {}
        for line in stdout.splitlines():
            for label in ("tracker doc", "domain doc"):
                if line.startswith(label + ": "):
                    paths[label] = Path(line[len(label) + 2:])
        return paths

    def test_a_session_in_a_beads_repo_opens_with_every_rule(self):
        done = self.session(self.beads_repo)

        self.assertEqual(0, done.returncode, done.stderr)
        for rule in RULES:
            self.assertIn(rule, done.stdout)

    def test_the_rules_come_with_the_paths_of_the_tracker_doc_and_the_domain_doc(self):
        done = self.session(self.beads_repo)

        paths = self.printed_paths(done.stdout)
        self.assertEqual({"tracker doc", "domain doc"}, set(paths))
        for path in paths.values():
            self.assertTrue(path.is_absolute(), path)
            self.assertTrue(path.is_file(), path)

    def test_a_session_in_a_repo_without_beads_prints_nothing_and_exits_cleanly(self):
        done = self.session(self.plain_repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)
        self.assertEqual("", done.stderr)

    def test_a_session_in_a_worktree_of_a_repo_without_beads_prints_nothing(self):
        done = self.session(self.plain_worktree)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)

    def test_a_beads_folder_above_a_repo_does_not_make_the_repo_a_beads_repo(self):
        done = self.session(self.repo_under_it)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)

    def test_a_session_in_a_folder_that_is_not_a_repo_prints_nothing_and_exits_cleanly(self):
        done = self.session(self.not_a_repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)

    def test_a_session_in_a_worktree_of_a_stealth_beads_repo_gets_the_rules(self):
        self.assertFalse((self.worktree / ".beads").exists())
        listed = subprocess.run([self.bd, "list", "--json"], cwd=self.worktree, capture_output=True, text=True)
        self.assertEqual(0, listed.returncode, listed.stderr)

        done = self.session(self.worktree)

        self.assertEqual(0, done.returncode, done.stderr)
        for rule in RULES:
            self.assertIn(rule, done.stdout)
        self.assertEqual({"tracker doc", "domain doc"}, set(self.printed_paths(done.stdout)))

    def test_a_session_in_a_subfolder_of_a_beads_repo_gets_the_rules(self):
        done = self.session(self.beads_repo / "src" / "deep")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Planning, Factory, Acceptance and Bench", done.stdout)

    def test_a_session_in_a_subfolder_of_a_worktree_of_a_stealth_beads_repo_gets_the_rules(self):
        (self.worktree / "lib").mkdir(exist_ok=True)

        done = self.session(self.worktree / "lib")

        self.assertIn("Planning, Factory, Acceptance and Bench", done.stdout)

    def test_a_worktree_session_without_git_on_the_path_prints_nothing_and_exits_cleanly(self):
        event = json.dumps({"hook_event_name": "SessionStart", "cwd": str(self.worktree)})

        done = self.start(event, self.not_a_repo, str(self.not_a_repo))

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)

    def test_empty_input_falls_back_to_the_process_folder(self):
        in_beads = self.start("", self.beads_repo, os.environ["PATH"])
        elsewhere = self.start("", self.plain_repo, os.environ["PATH"])

        self.assertEqual(0, in_beads.returncode, in_beads.stderr)
        self.assertIn("Planning, Factory, Acceptance and Bench", in_beads.stdout)
        self.assertEqual(0, elsewhere.returncode, elsewhere.stderr)
        self.assertEqual("", elsewhere.stdout)

    def test_input_that_is_not_json_falls_back_to_the_process_folder(self):
        done = self.start("{not json", self.beads_repo, os.environ["PATH"])

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Planning, Factory, Acceptance and Bench", done.stdout)

    def test_input_whose_folder_is_missing_or_not_a_string_falls_back_to_the_process_folder(self):
        for stdin in ('{"cwd": 7}', '{"cwd": "/no/such/folder"}', "[1, 2]", '{"source": "startup"}'):
            with self.subTest(stdin=stdin):
                done = self.start(stdin, self.beads_repo, os.environ["PATH"])

                self.assertEqual(0, done.returncode, done.stderr)
                self.assertIn("Planning, Factory, Acceptance and Bench", done.stdout)


if __name__ == "__main__":
    unittest.main()
