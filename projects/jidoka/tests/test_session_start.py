import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
HOOK = PLUGIN / "hooks" / "session_start.py"

RULES = [
    "A jidoka skill's own subagents are authorized",
    "never a bare id",
    "load the jidoka:unslop skill",
    "Beads stealth mode covers the tracker only",
    "Bead ids and requirement ids never leave the tracker or the spec",
    "Comments describe the code, never the work",
    "Tests assert runtime behavior",
    "Comment cleanup is requested work",
    "Planning, Factory, Acceptance and Bench",
]
ANTIGRAVITY_RULES = [rule.replace("jidoka:unslop", "jidoka-unslop") for rule in RULES]


def init_committed_repo(repo: Path) -> None:
    fixture.init_repo(repo)
    (repo / "README.md").write_text("shop\n", encoding="utf-8")
    fixture.git_commit_all(repo, "Start")


class SessionStartTests(unittest.TestCase):
    """A beads repo with the fake bd first on the hook's PATH, its linked worktree beside it, and the repos and
    folders that hold no beads."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name).resolve()
        cls.home = root / "jidoka-home"
        cls.home.mkdir()
        (cls.home / "python").write_text(sys.executable + "\n", encoding="utf-8")

        cls.beads_repo = root / "shop"
        init_committed_repo(cls.beads_repo)
        cls.bin = root / "bin"
        cls.bd = str(fixture.add_fake_beads(cls.beads_repo, cls.bin))
        cls.path = fixture.path_with(cls.bin)
        (cls.beads_repo / "src" / "deep").mkdir(parents=True)

        cls.worktree = root / "shop-feature"
        fixture.run(["git", "worktree", "add", "-q", "-b", "feature", str(cls.worktree)], cls.beads_repo)

        cls.plain_repo = root / "plain"
        init_committed_repo(cls.plain_repo)

        cls.plain_worktree = root / "plain-feature"
        fixture.run(["git", "worktree", "add", "-q", "-b", "feature", str(cls.plain_worktree)], cls.plain_repo)

        cls.not_a_repo = fixture.folder_without_beads_above([root, Path(root.anchor)], Path(root.anchor))

        cls.beads_folder_above_the_repo = root / "outer"
        (cls.beads_folder_above_the_repo / ".beads").mkdir(parents=True)
        cls.repo_under_it = cls.beads_folder_above_the_repo / "inner"
        init_committed_repo(cls.repo_under_it)

        cls.home_with_beads = root / "home-with-beads"
        (cls.home_with_beads / ".beads").mkdir(parents=True)
        cls.plain_folder_under_home = cls.home_with_beads / "notes" / "drafts"
        cls.plain_folder_under_home.mkdir(parents=True)

    @classmethod
    def tearDownClass(cls):
        fixture.remove_tree_quietly(cls.not_a_repo)
        cls.tmp.cleanup()

    def start(self, stdin: str, process_cwd: Path, path: str) -> subprocess.CompletedProcess:
        env = {"PATH": path, "JIDOKA_HOME": str(self.home), "HOME": str(self.home),
               **fixture.system_variables(os.environ, fixture.WINDOWS)}
        return fixture.run_launcher(LAUNCHER, [str(HOOK)], stdin, env, process_cwd, None)

    def start_on_path(self, stdin: str, process_cwd: Path, path: str) -> subprocess.CompletedProcess:
        """Starts the hook as start does, on exactly the PATH given, for a test that hides git from it."""
        env = {"PATH": path, "JIDOKA_HOME": str(self.home), "HOME": str(self.home),
               **fixture.system_variables(os.environ, fixture.WINDOWS)}
        return fixture.run_launcher_on_path(LAUNCHER, [str(HOOK)], stdin, env, process_cwd, None)

    def session(self, cwd: Path) -> subprocess.CompletedProcess:
        event = {"session_id": "s1", "hook_event_name": "SessionStart", "source": "startup", "cwd": str(cwd)}
        return self.start(json.dumps(event), self.not_a_repo, self.path)

    def session_with_env_file(self, cwd: Path, env_file: Path, session_id: str) -> subprocess.CompletedProcess:
        event = {"session_id": session_id, "hook_event_name": "SessionStart", "source": "startup", "cwd": str(cwd)}
        env = {"PATH": self.path, "JIDOKA_HOME": str(self.home), "HOME": str(self.home),
               "CLAUDE_ENV_FILE": str(env_file), **fixture.system_variables(os.environ, fixture.WINDOWS)}
        return fixture.run_launcher(LAUNCHER, [str(HOOK)], json.dumps(event), env, self.not_a_repo, None)

    def exported_by(self, env_file: Path) -> str:
        """The value of JIDOKA_SESSION_ID in a shell that sources the env file."""
        source = f". '{env_file.as_posix()}' && printf %s \"$JIDOKA_SESSION_ID\""
        return subprocess.run([fixture.real_shell(), "-c", source], capture_output=True, text=True,
                              encoding="utf-8").stdout

    def test_a_session_start_exports_the_session_id_to_the_calls_the_session_makes(self):
        env_file = Path(self.tmp.name) / "session-env.sh"

        done = self.session_with_env_file(self.beads_repo, env_file, "7f3c-session")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("7f3c-session", self.exported_by(env_file))

    def test_a_session_start_exports_the_session_id_in_a_repo_without_beads_too(self):
        env_file = Path(self.tmp.name) / "plain-session-env.sh"

        done = self.session_with_env_file(self.plain_repo, env_file, "plain-session")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("plain-session", self.exported_by(env_file))

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

    def test_a_session_in_a_repo_without_repo_settings_says_the_glossary_and_adrs_are_always_committed(self):
        done = self.session(self.beads_repo)

        self.assertIn("Code, tests, GLOSSARY.md and ADRs are always committed.", done.stdout)
        self.assertNotIn("uncommitted", done.stdout)

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

    def test_a_beads_folder_in_a_parent_does_not_make_a_plain_folder_outside_any_repo_a_beads_repo(self):
        done = self.session(self.plain_folder_under_home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)

    def test_a_session_in_a_plain_folder_that_holds_a_beads_folder_gets_the_rules(self):
        done = self.session(self.home_with_beads)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Planning, Factory, Acceptance and Bench", done.stdout)

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

        done = self.start_on_path(event, self.not_a_repo, str(self.not_a_repo))

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)

    def test_empty_input_falls_back_to_the_process_folder(self):
        in_beads = self.start("", self.beads_repo, self.path)
        elsewhere = self.start("", self.plain_repo, self.path)

        self.assertEqual(0, in_beads.returncode, in_beads.stderr)
        self.assertIn("Planning, Factory, Acceptance and Bench", in_beads.stdout)
        self.assertEqual(0, elsewhere.returncode, elsewhere.stderr)
        self.assertEqual("", elsewhere.stdout)

    def test_input_that_is_not_json_falls_back_to_the_process_folder(self):
        done = self.start("{not json", self.beads_repo, self.path)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Planning, Factory, Acceptance and Bench", done.stdout)

    def test_input_whose_folder_is_missing_or_not_a_string_falls_back_to_the_process_folder(self):
        for stdin in ('{"cwd": 7}', '{"cwd": "/no/such/folder"}', "[1, 2]", '{"source": "startup"}'):
            with self.subTest(stdin=stdin):
                done = self.start(stdin, self.beads_repo, self.path)

                self.assertEqual(0, done.returncode, done.stderr)
                self.assertIn("Planning, Factory, Acceptance and Bench", done.stdout)

    def antigravity_session(self, cwd: Path, env_file: Path | None) -> subprocess.CompletedProcess:
        event = {"conversationId": "ec33ebf9", "hookEventName": "SessionStart", "cwd": str(cwd),
                 "workspacePaths": [str(cwd)], "modelName": "auto", "lastUserInput": ""}
        env = {"PATH": self.path, "JIDOKA_HOME": str(self.home), "HOME": str(self.home),
               **fixture.system_variables(os.environ, fixture.WINDOWS)}
        if env_file is not None:
            env["CLAUDE_ENV_FILE"] = str(env_file)
        return fixture.run_launcher(LAUNCHER, [str(HOOK), "--host", "antigravity"], json.dumps(event), env,
                                    self.not_a_repo, None)

    def injected_text(self, stdout: str) -> str:
        answer = json.loads(stdout)
        self.assertEqual({"injectSteps"}, set(answer))
        self.assertEqual(1, len(answer["injectSteps"]))
        message = answer["injectSteps"][0]
        self.assertEqual({"systemMessage"}, set(message))
        self.assertEqual({"systemMessage"}, set(message["systemMessage"]))
        return message["systemMessage"]["systemMessage"]

    def test_an_antigravity_session_in_a_beads_repo_gets_one_json_object_with_every_rule_in_inject_steps(self):
        done = self.antigravity_session(self.beads_repo, None)

        self.assertEqual(0, done.returncode, done.stderr)
        text = self.injected_text(done.stdout)
        for rule in ANTIGRAVITY_RULES:
            self.assertIn(rule, text)
        self.assertEqual({"tracker doc", "domain doc"}, set(self.printed_paths(text)))

    def test_an_antigravity_session_names_each_skill_and_command_as_the_profile_copy_installs_it(self):
        text = self.injected_text(self.antigravity_session(self.beads_repo, None).stdout)

        self.assertIn("Run /jidoka-onboard to record them.", text)
        self.assertIn("load the jidoka-unslop skill", text)
        self.assertNotIn("jidoka:", text)

    def test_a_claude_code_session_names_each_skill_and_command_with_the_plugin_namespace(self):
        done = self.session(self.beads_repo)

        self.assertIn("Run /jidoka:onboard to record them.", done.stdout)
        self.assertIn("load the jidoka:unslop skill", done.stdout)
        self.assertNotIn("jidoka-unslop", done.stdout)
        self.assertNotIn("jidoka-onboard", done.stdout)

    def test_a_session_that_sends_the_antigravity_payload_to_the_claude_code_hook_gets_plain_text(self):
        event = {"conversationId": "ec33ebf9", "hookEventName": "SessionStart", "cwd": str(self.beads_repo)}

        done = self.start(json.dumps(event), self.not_a_repo, self.path)

        self.assertTrue(done.stdout.startswith("jidoka rules for this repo, which uses beads."), done.stdout)

    def test_an_antigravity_session_in_a_beads_repo_gets_the_bd_prime_output_after_the_rules(self):
        done = self.antigravity_session(self.beads_repo, None)

        text = self.injected_text(done.stdout)
        self.assertIn("The fake bd stands in for bd prime here.", text)
        self.assertLess(text.index("Planning, Factory, Acceptance and Bench"), text.index("# Beads Workflow Context"))

    def test_an_antigravity_session_in_a_worktree_of_a_stealth_beads_repo_gets_the_rules_and_bd_prime(self):
        done = self.antigravity_session(self.worktree, None)

        text = self.injected_text(done.stdout)
        self.assertIn("Planning, Factory, Acceptance and Bench", text)
        self.assertIn("# Beads Workflow Context", text)

    def test_an_antigravity_session_outside_a_beads_repo_prints_nothing(self):
        for folder in (self.plain_repo, self.plain_worktree, self.not_a_repo, self.repo_under_it):
            with self.subTest(folder=folder):
                done = self.antigravity_session(folder, None)

                self.assertEqual(0, done.returncode, done.stderr)
                self.assertEqual("", done.stdout)
                self.assertEqual("", done.stderr)

    def test_an_antigravity_session_writes_no_env_file(self):
        env_file = Path(self.tmp.name) / "antigravity-env.sh"

        done = self.antigravity_session(self.beads_repo, env_file)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertFalse(env_file.exists())

    def test_a_claude_code_session_gets_plain_text_without_the_bd_prime_output(self):
        done = self.session(self.beads_repo)

        self.assertTrue(done.stdout.startswith("jidoka rules for this repo, which uses beads."), done.stdout)
        self.assertNotIn("injectSteps", done.stdout)
        self.assertNotIn("Beads Workflow Context", done.stdout)


if __name__ == "__main__":
    unittest.main()
