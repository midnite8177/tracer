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
SETTINGS_SCRIPT = PLUGIN / "scripts" / "repo_settings.py"
STEALTH_SCRIPT = PLUGIN / "scripts" / "beads_stealth.py"
HOOK = PLUGIN / "hooks" / "session_start.py"
ONBOARDING_LINE = "/jidoka:onboard"


def tracer_apps() -> list:
    return [
        {"name": "tracer-ui", "kind": "program", "way_in": "its web UI",
         "build": "dotnet build projects/tracer-ui/TracerUi.slnx",
         "run": "dotnet run --project projects/tracer-ui/src/TracerUi.Web",
         "test": "dotnet test projects/tracer-ui/TracerUi.slnx",
         "test_target": '--filter "FullyQualifiedName~<Class>"', "test_full": None, "hand_run": []},
        {"name": "tracer-seed", "kind": "program", "way_in": "its command line",
         "build": "python3 projects/tracer-seed/build.py", "run": "python3 projects/tracer-seed/build.py",
         "test": "python3 -m unittest discover -s projects/tracer-seed/tests", "test_target": "-k <name>",
         "test_full": None, "hand_run": []},
        {"name": "jidoka", "kind": "program", "way_in": "its command line", "build": None,
         "run": "python3 projects/jidoka/install.py --config-dir <path>",
         "test": "python3 -m unittest discover -s projects/jidoka/tests", "test_target": "-k <name>",
         "test_full": None, "hand_run": []},
    ]


def tracer_settings() -> dict:
    return {
        "lap_test_scope": "targeted",
        "worker_commands": ["dotnet build", "dotnet test", "python3 -m unittest"],
        "slot_use": None,
        "lap_limit": 3,
        "apps": tracer_apps(),
    }


WINDOW_TESTS = {"name": "window tests", "exclusion": "FullyQualifiedName!~CampfireWindowTests",
                "command": 'dotnet test RecoveredBox.Tests --filter "FullyQualifiedName~CampfireWindowTests"',
                "reason": "they open windows that take keyboard focus"}
LIVE_MCP_TESTS = {"name": "live MCP tests", "exclusion": "FullyQualifiedName!~LiveMcpStdioTests",
                  "command": 'dotnet test RecoveredBox.Tests --filter "FullyQualifiedName~LiveMcpStdioTests"',
                  "reason": "they start the real MCP server over stdio"}
MODEM_SCRIPTS = {"name": "modem scripts", "exclusion": "tests/",
                 "command": ".venv/bin/python tools/modem-duplex/run.py",
                 "reason": "they need the modem plugged in"}


def recovered_box_app() -> dict:
    return {"name": "recovered-box", "kind": "program", "way_in": "its windows",
            "build": "dotnet build RecoveredBox.slnx", "run": None,
            "test": "dotnet test RecoveredBox.Tests",
            "test_full": '--filter "FullyQualifiedName!~CampfireWindowTests&FullyQualifiedName!~LiveMcpStdioTests"',
            "test_target": '--filter "FullyQualifiedName~<name>&FullyQualifiedName!~CampfireWindowTests'
                           '&FullyQualifiedName!~LiveMcpStdioTests"',
            "hand_run": [dict(WINDOW_TESTS), dict(LIVE_MCP_TESTS)]}


def spam_app() -> dict:
    return {"name": "spam", "kind": "program", "way_in": "its command line", "build": None, "run": None,
            "test": ".venv/bin/python -m pytest tests/ -q", "test_full": None, "test_target": "-k <name>",
            "hand_run": [dict(MODEM_SCRIPTS)]}


def hand_run_settings() -> dict:
    return {**tracer_settings(), "apps": [recovered_box_app(), spam_app()]}


def editor_app() -> dict:
    return {"name": "editor", "kind": "program", "way_in": "its windows", "build": "dotnet build Editor.slnx",
            "run": None, "test": None, "test_target": None, "test_full": None, "hand_run": []}


def untested_settings() -> dict:
    tracer_ui, tracer_seed, jidoka = tracer_apps()
    help_pages = {**editor_app(), "name": "help-pages", "kind": "library", "build": None}
    return {**tracer_settings(), "apps": [editor_app(), tracer_ui, help_pages, tracer_seed, jidoka]}


def init_committed_repo(repo: Path) -> None:
    fixture.init_repo(repo)
    (repo / "README.md").write_text("shop\n", encoding="utf-8")
    fixture.git_commit_all(repo, "Start")


class OnboardingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()

        cls.repo = cls.root / "shop"
        init_committed_repo(cls.repo)
        fixture.add_stealth_beads(cls.repo)
        cls.worktree = cls.root / "shop-feature"
        fixture.run(["git", "worktree", "add", "-q", "-b", "feature", str(cls.worktree)], cls.repo)

        cls.other_repo = cls.root / "kiosk"
        init_committed_repo(cls.other_repo)
        fixture.add_stealth_beads(cls.other_repo)

        cls.plain_repo = cls.root / "plain"
        init_committed_repo(cls.plain_repo)
        cls.count = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        type(self).count += 1
        self.home = self.root / f"jidoka-home-{self.count}"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        for repo in (self.repo, self.other_repo):
            local = repo / "CLAUDE.local.md"
            if local.exists():
                local.unlink()

    def env(self) -> dict:
        return {"PATH": os.environ["PATH"], "JIDOKA_HOME": str(self.home), "HOME": str(self.home)}

    def settings_script(self, cwd: Path, args: list, stdin: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(LAUNCHER), str(SETTINGS_SCRIPT), *args], input=stdin, capture_output=True,
                              text=True, encoding="utf-8", env=self.env(), cwd=cwd)

    def write(self, cwd: Path, settings: dict) -> subprocess.CompletedProcess:
        return self.settings_script(cwd, ["write"], json.dumps(settings))

    def show(self, cwd: Path) -> subprocess.CompletedProcess:
        return self.settings_script(cwd, ["show"], "")

    def stored_files(self) -> list:
        repos = self.home / "repos"
        return sorted(repos.iterdir()) if repos.is_dir() else []

    def session(self, cwd: Path) -> subprocess.CompletedProcess:
        event = {"session_id": "s1", "hook_event_name": "SessionStart", "source": "startup", "cwd": str(cwd)}
        return subprocess.run([str(LAUNCHER), str(HOOK)], input=json.dumps(event), capture_output=True,
                              text=True, encoding="utf-8", env=self.env(), cwd=self.root)

    def test_writes_one_settings_file_per_repo_named_for_its_main_worktree(self):
        first = self.write(self.repo, tracer_settings())
        again = self.write(self.repo, tracer_settings())
        other = self.write(self.other_repo, tracer_settings())

        for done in (first, again, other):
            self.assertEqual(0, done.returncode, done.stderr)
        files = self.stored_files()
        self.assertEqual(2, len(files))
        kiosk_file, shop_file = files
        self.assertTrue(kiosk_file.name.startswith("kiosk-") and kiosk_file.suffix == ".json", kiosk_file)
        self.assertTrue(shop_file.name.startswith("shop-") and shop_file.suffix == ".json", shop_file)
        kiosk = json.loads(kiosk_file.read_text(encoding="utf-8"))
        self.assertEqual(str(self.other_repo), kiosk["main_worktree"])
        stored = json.loads(shop_file.read_text(encoding="utf-8"))
        self.assertEqual(str(self.repo), stored["main_worktree"])
        self.assertEqual(["tracer-ui", "tracer-seed", "jidoka"], [app["name"] for app in stored["apps"]])

    def test_the_repo_build_runs_every_app_build_in_order_and_skips_an_app_without_one(self):
        self.write(self.repo, tracer_settings())

        shown = json.loads(self.show(self.repo).stdout)

        self.assertEqual(["dotnet build projects/tracer-ui/TracerUi.slnx",
                          "python3 projects/tracer-seed/build.py"], shown["build"])

    def test_the_full_suite_runs_every_app_test_command_in_order(self):
        self.write(self.repo, tracer_settings())

        shown = json.loads(self.show(self.repo).stdout)

        self.assertEqual(["dotnet test projects/tracer-ui/TracerUi.slnx",
                          "python3 -m unittest discover -s projects/tracer-seed/tests",
                          "python3 -m unittest discover -s projects/jidoka/tests"], shown["full_suite"])
        self.assertEqual('--filter "FullyQualifiedName~<Class>"', shown["apps"][0]["test_target"])

    def test_the_full_suite_leaves_out_each_app_with_no_test_command_and_untested_apps_names_them_in_order(self):
        self.write(self.repo, untested_settings())

        shown = json.loads(self.show(self.repo).stdout)

        self.assertEqual(["dotnet test projects/tracer-ui/TracerUi.slnx",
                          "python3 -m unittest discover -s projects/tracer-seed/tests",
                          "python3 -m unittest discover -s projects/jidoka/tests"], shown["full_suite"])
        self.assertEqual(["editor", "help-pages"], shown["untested_apps"])

    def test_settings_in_which_every_app_has_a_test_command_store_no_untested_apps(self):
        self.write(self.repo, tracer_settings())

        shown = json.loads(self.show(self.repo).stdout)

        self.assertEqual([], shown["untested_apps"])

    def test_the_full_suite_adds_an_apps_test_full_to_its_test_command(self):
        self.write(self.repo, hand_run_settings())

        shown = json.loads(self.show(self.repo).stdout)

        self.assertEqual(['dotnet test RecoveredBox.Tests --filter '
                          '"FullyQualifiedName!~CampfireWindowTests&FullyQualifiedName!~LiveMcpStdioTests"',
                          ".venv/bin/python -m pytest tests/ -q"], shown["full_suite"])

    def test_each_apps_hand_run_groups_are_stored_and_listed_with_their_app_in_app_order(self):
        done = self.write(self.repo, hand_run_settings())

        self.assertEqual(0, done.returncode, done.stderr)
        shown = json.loads(self.show(self.repo).stdout)
        self.assertEqual([WINDOW_TESTS, LIVE_MCP_TESTS], shown["apps"][0]["hand_run"])
        self.assertEqual([MODEM_SCRIPTS], shown["apps"][1]["hand_run"])
        self.assertEqual([
            {"app": "recovered-box", "name": "window tests", "reason": "they open windows that take keyboard focus",
             "command": 'dotnet test RecoveredBox.Tests --filter "FullyQualifiedName~CampfireWindowTests"'},
            {"app": "recovered-box", "name": "live MCP tests", "reason": "they start the real MCP server over stdio",
             "command": 'dotnet test RecoveredBox.Tests --filter "FullyQualifiedName~LiveMcpStdioTests"'},
            {"app": "spam", "name": "modem scripts", "reason": "they need the modem plugged in",
             "command": ".venv/bin/python tools/modem-duplex/run.py"},
        ], shown["hand_run"])

    def test_settings_with_no_hand_run_groups_store_an_empty_list(self):
        self.write(self.repo, tracer_settings())

        shown = json.loads(self.show(self.repo).stdout)

        self.assertEqual([], shown["hand_run"])

    def test_refuses_an_app_that_leaves_out_test_full_or_hand_run(self):
        for key in ("test_full", "hand_run"):
            with self.subTest(key=key):
                settings = tracer_settings()
                del settings["apps"][2][key]

                done = self.write(self.repo, settings)

                self.assertNotEqual(0, done.returncode)
                self.assertIn("'jidoka' has no " + key, done.stderr)
                self.assertEqual([], self.stored_files())

    def test_refuses_every_hand_run_group_without_a_name_exclusion_command_or_reason_at_once(self):
        settings = hand_run_settings()
        settings["apps"][0]["hand_run"] = [
            {"name": "window tests", "exclusion": "FullyQualifiedName!~CampfireWindowTests", "command": "  ",
             "reason": "they take keyboard focus"},
            {"exclusion": "FullyQualifiedName!~LiveMcpStdioTests", "command": "dotnet test", "reason": "stdio"},
        ]
        settings["apps"][1]["hand_run"] = [{"name": "modem scripts", "exclusion": "tests/", "command": "make modem"}]

        done = self.write(self.repo, settings)

        self.assertNotEqual(0, done.returncode)
        self.assertIn("'recovered-box' has a hand_run group 'window tests' with no command", done.stderr)
        self.assertIn("'recovered-box' has a hand_run group hand_run[1] with no name", done.stderr)
        self.assertIn("'spam' has a hand_run group 'modem scripts' with no reason", done.stderr)
        self.assertEqual([], self.stored_files())

    def test_refuses_a_hand_run_that_is_not_a_list_of_groups(self):
        settings = hand_run_settings()
        settings["apps"][1]["hand_run"] = "tools/modem-duplex"

        done = self.write(self.repo, settings)

        self.assertNotEqual(0, done.returncode)
        self.assertIn("'spam' has a hand_run that is not a list", done.stderr)
        self.assertEqual([], self.stored_files())

    def test_refuses_a_group_whose_exclusion_neither_the_full_suite_nor_the_targeted_command_holds(self):
        settings = hand_run_settings()
        settings["apps"][0]["hand_run"][0]["exclusion"] = "FullyQualifiedName!~WindowTests&Category!=Ui"

        done = self.write(self.repo, settings)

        self.assertNotEqual(0, done.returncode)
        for command in ("full-suite command", "targeted command"):
            self.assertIn("'window tests' whose exclusion 'FullyQualifiedName!~WindowTests&Category!=Ui' "
                          f"is not in the {command}", done.stderr)
        self.assertEqual([], self.stored_files())

    def test_refuses_a_group_whose_exclusion_is_only_in_test_full_because_the_targeted_command_would_run_it(self):
        settings = hand_run_settings()
        app = settings["apps"][0]
        app["test_target"] = '--filter "FullyQualifiedName~<name>&FullyQualifiedName!~LiveMcpStdioTests"'

        done = self.write(self.repo, settings)

        self.assertNotEqual(0, done.returncode)
        self.assertIn("'window tests' whose exclusion 'FullyQualifiedName!~CampfireWindowTests' is not in the "
                      "targeted command, 'dotnet test RecoveredBox.Tests --filter "
                      "\"FullyQualifiedName~<name>&FullyQualifiedName!~LiveMcpStdioTests\"'", done.stderr)
        self.assertNotIn("full-suite command", done.stderr)
        self.assertNotIn("'live MCP tests'", done.stderr)
        self.assertEqual([], self.stored_files())

    def test_accepts_a_group_whose_exclusion_is_only_in_the_test_command_both_commands_start_with(self):
        settings = {**tracer_settings(), "apps": [{**tracer_apps()[0], "hand_run": []}, spam_app()]}

        done = self.write(self.repo, settings)

        self.assertEqual(0, done.returncode, done.stderr)
        shown = json.loads(self.show(self.repo).stdout)
        self.assertEqual([MODEM_SCRIPTS], shown["apps"][1]["hand_run"])

    def test_refuses_settings_in_which_no_app_has_a_build_and_writes_nothing(self):
        settings = tracer_settings()
        for app in settings["apps"]:
            app["build"] = None

        done = self.write(self.repo, settings)

        self.assertNotEqual(0, done.returncode)
        self.assertIn("build", done.stderr)
        self.assertEqual([], self.stored_files())

    def test_refuses_settings_in_which_no_app_has_a_test_command_and_leaves_claude_local_md_untouched(self):
        local = self.repo / "CLAUDE.local.md"
        local.write_bytes(b"# shop\r\nbuild with make\r\n")
        settings = {**tracer_settings(), "apps": [editor_app(), {**editor_app(), "name": "help-pages"}]}
        settings["moved_lines"] = ["build with make"]

        done = self.write(self.repo, settings)

        self.assertNotEqual(0, done.returncode)
        self.assertIn("no app has a test command", done.stderr)
        self.assertEqual([], self.stored_files())
        self.assertEqual(b"# shop\r\nbuild with make\r\n", local.read_bytes())

    def test_accepts_an_app_whose_test_command_and_test_target_are_null(self):
        done = self.write(self.repo, untested_settings())

        self.assertEqual(0, done.returncode, done.stderr)
        shown = json.loads(self.show(self.repo).stdout)
        self.assertEqual(editor_app(), shown["apps"][0])

    def test_refuses_an_app_with_a_null_test_or_test_target_whose_other_test_settings_are_not_empty(self):
        cases = {
            "test_target": ({"test_target": "-k <name>"}, "'editor' has a test_target but no test command"),
            "test_full": ({"test_full": "--exclude windows"}, "'editor' has a test_full but no test command"),
            "hand_run": ({"hand_run": [dict(MODEM_SCRIPTS)]}, "'editor' has hand_run groups but no test command"),
            "test": ({"test": "dotnet test Editor.Tests"},
                     "'editor' has a test command but does not say how to target a test"),
        }
        for key, (change, problem) in cases.items():
            with self.subTest(key=key):
                settings = untested_settings()
                settings["apps"][0].update(change)

                done = self.write(self.repo, settings)

                self.assertNotEqual(0, done.returncode)
                self.assertIn(problem, done.stderr)
                self.assertNotIn("'help-pages'", done.stderr)
                self.assertEqual([], self.stored_files())

    def test_refuses_a_value_outside_its_allowed_set(self):
        cases = {"lap_test_scope": "some", "lap_limit": 0, "worker_commands": "make"}
        for key, value in cases.items():
            with self.subTest(key=key):
                settings = tracer_settings()
                settings[key] = value

                done = self.write(self.repo, settings)

                self.assertNotEqual(0, done.returncode)
                self.assertIn(key, done.stderr)
                self.assertEqual([], self.stored_files())

    def test_settings_written_from_the_main_worktree_are_found_from_a_linked_worktree(self):
        self.write(self.repo, tracer_settings())

        done = self.show(self.worktree)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(str(self.repo), json.loads(done.stdout)["main_worktree"])

    def test_settings_written_from_a_linked_worktree_are_found_from_the_main_worktree(self):
        self.write(self.worktree, tracer_settings())

        done = self.show(self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(3, json.loads(done.stdout)["lap_limit"])

    def test_show_says_there_are_no_settings_and_fails_in_a_repo_never_onboarded(self):
        done = self.show(self.repo)

        self.assertNotEqual(0, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn("no settings", done.stderr)

    def test_a_rerun_replaces_the_settings_it_is_given_and_keeps_the_rest(self):
        self.write(self.repo, tracer_settings())
        jidoka_only = [tracer_apps()[2]]
        jidoka_only[0]["build"] = "python3 projects/jidoka/release.py --bump patch"

        done = self.write(self.repo, {"lap_limit": 5, "apps": jidoka_only})

        self.assertEqual(0, done.returncode, done.stderr)
        shown = json.loads(self.show(self.repo).stdout)
        self.assertEqual(5, shown["lap_limit"])
        self.assertEqual(["jidoka"], [app["name"] for app in shown["apps"]])
        self.assertEqual(["python3 projects/jidoka/release.py --bump patch"], shown["build"])
        self.assertEqual(["python3 -m unittest discover -s projects/jidoka/tests"], shown["full_suite"])
        self.assertEqual("targeted", shown["lap_test_scope"])
        self.assertEqual(["dotnet build", "dotnet test", "python3 -m unittest"], shown["worker_commands"])

    def test_a_rerun_that_would_leave_no_build_is_refused_and_keeps_the_stored_settings(self):
        self.write(self.repo, tracer_settings())
        before = [path.read_bytes() for path in self.stored_files()]

        done = self.write(self.repo, {"apps": [tracer_apps()[2]]})

        self.assertNotEqual(0, done.returncode)
        self.assertEqual(before, [path.read_bytes() for path in self.stored_files()])

    def test_moved_lines_leave_claude_local_md_and_every_other_byte_stays(self):
        local = self.repo / "CLAUDE.local.md"
        local.write_bytes(b"@AGENTS.local.md\r\n\r\nBuild: dotnet build\r\nKeep this line.\n"
                          b"Test: dotnet test\nLast line, no newline")
        settings = tracer_settings()
        settings["moved_lines"] = ["Build: dotnet build", "Test: dotnet test"]

        done = self.write(self.repo, settings)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(b"@AGENTS.local.md\r\n\r\nKeep this line.\nLast line, no newline", local.read_bytes())
        self.assertNotIn("moved_lines", json.loads(self.show(self.repo).stdout))

    def test_a_line_named_once_leaves_one_copy_and_the_other_copies_stay(self):
        local = self.repo / "CLAUDE.local.md"
        local.write_text("Build: make\nKeep.\nBuild: make\n", encoding="utf-8", newline="")
        settings = tracer_settings()
        settings["moved_lines"] = ["Build: make"]

        done = self.write(self.repo, settings)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("Keep.\nBuild: make\n", local.read_text(encoding="utf-8"))

    def test_refuses_a_blank_moved_line_and_leaves_claude_local_md_untouched(self):
        local = self.repo / "CLAUDE.local.md"
        local.write_text("Build: make\n\nKeep.\n", encoding="utf-8", newline="")
        settings = tracer_settings()
        settings["moved_lines"] = ["Build: make", ""]

        done = self.write(self.repo, settings)

        self.assertNotEqual(0, done.returncode)
        self.assertIn("blank", done.stderr)
        self.assertEqual([], self.stored_files())
        self.assertEqual("Build: make\n\nKeep.\n", local.read_text(encoding="utf-8"))

    def test_moved_lines_are_removed_from_the_main_worktree_when_written_from_a_linked_one(self):
        local = self.repo / "CLAUDE.local.md"
        local.write_text("Build: make\nKeep.\n", encoding="utf-8", newline="")
        settings = tracer_settings()
        settings["moved_lines"] = ["Build: make"]

        done = self.write(self.worktree, settings)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("Keep.\n", local.read_text(encoding="utf-8"))

    def test_refuses_a_moved_line_that_claude_local_md_does_not_hold(self):
        local = self.repo / "CLAUDE.local.md"
        local.write_text("Build: make\n", encoding="utf-8", newline="")
        settings = tracer_settings()
        settings["moved_lines"] = ["Build: make", "Test: make check"]

        done = self.write(self.repo, settings)

        self.assertNotEqual(0, done.returncode)
        self.assertIn("Test: make check", done.stderr)
        self.assertEqual([], self.stored_files())
        self.assertEqual("Build: make\n", local.read_text(encoding="utf-8"))

    def committed_beads_repo(self) -> Path:
        repo = self.root / f"depot-{self.count}"
        init_committed_repo(repo)
        fixture.add_committed_beads(repo)
        return repo

    def test_refuses_settings_while_git_tracks_the_beads_and_says_how_to_switch(self):
        repo = self.committed_beads_repo()
        worktree = self.root / f"depot-{self.count}-feature"
        fixture.run(["git", "worktree", "add", "-q", "-b", "feature", str(worktree)], repo)

        for cwd in (repo, worktree):
            with self.subTest(cwd=cwd):
                done = self.write(cwd, tracer_settings())

                self.assertEqual(1, done.returncode)
                self.assertIn(".beads", done.stderr)
                self.assertIn("beads_stealth.py", done.stderr)
                self.assertEqual([], self.stored_files())

    def test_writes_settings_once_the_switch_has_untracked_the_beads(self):
        repo = self.committed_beads_repo()
        switched = subprocess.run([str(LAUNCHER), str(STEALTH_SCRIPT)], capture_output=True, text=True,
                                  encoding="utf-8", env=self.env(), cwd=repo)

        done = self.write(repo, tracer_settings())

        self.assertEqual(0, switched.returncode, switched.stderr)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(1, len(self.stored_files()))

    def repo_with_untracked_glossary_and_adrs(self) -> Path:
        repo = self.root / f"atlas-{self.count}"
        init_committed_repo(repo)
        fixture.add_stealth_beads(repo)
        (repo / "GLOSSARY.md").write_text("# atlas\n", encoding="utf-8")
        (repo / "docs" / "adr").mkdir(parents=True)
        (repo / "docs" / "adr" / "0001-start.md").write_text("# 0001\n", encoding="utf-8")
        return repo

    def status(self, repo: Path) -> str:
        return fixture.run(["git", "status", "--porcelain", "--untracked-files=normal"], repo)

    def exclude_file(self, repo: Path) -> Path:
        return repo / ".git" / "info" / "exclude"

    def test_settings_keep_the_glossary_and_adrs_committed_at_their_usual_paths_when_not_given(self):
        done = self.write(self.repo, tracer_settings())

        self.assertEqual(0, done.returncode, done.stderr)
        shown = json.loads(self.show(self.repo).stdout)
        self.assertEqual("GLOSSARY.md", shown["glossary"])
        self.assertEqual("docs/adr", shown["adrs"])
        self.assertEqual("committed", shown["glossary_and_adrs"])

    def test_choosing_private_hides_the_glossary_and_adrs_from_git_status(self):
        repo = self.repo_with_untracked_glossary_and_adrs()
        self.assertIn("GLOSSARY.md", self.status(repo))
        self.assertIn("docs/", self.status(repo))

        done = self.write(repo, {**tracer_settings(), "glossary_and_adrs": "private"})

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", self.status(repo))
        self.assertTrue((repo / "GLOSSARY.md").is_file())
        self.assertTrue((repo / "docs" / "adr" / "0001-start.md").is_file())
        self.assertEqual("private", json.loads(self.show(repo).stdout)["glossary_and_adrs"])

    def test_private_hides_an_adr_folder_and_a_glossary_written_after_the_choice(self):
        repo = self.root / f"atlas-{self.count}"
        init_committed_repo(repo)
        fixture.add_stealth_beads(repo)

        done = self.write(repo, {**tracer_settings(), "glossary_and_adrs": "private"})
        (repo / "GLOSSARY.md").write_text("# atlas\n", encoding="utf-8")
        (repo / "docs" / "adr").mkdir(parents=True)
        (repo / "docs" / "adr" / "0001-start.md").write_text("# 0001\n", encoding="utf-8")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", self.status(repo))

    def test_choosing_private_again_adds_each_exclude_line_once(self):
        repo = self.repo_with_untracked_glossary_and_adrs()

        for _ in range(2):
            done = self.write(repo, {**tracer_settings(), "glossary_and_adrs": "private"})
            self.assertEqual(0, done.returncode, done.stderr)

        lines = self.exclude_file(repo).read_text(encoding="utf-8").splitlines()
        self.assertEqual(1, lines.count("/GLOSSARY.md"), lines)
        self.assertEqual(1, lines.count("/docs/adr/"), lines)

    def test_private_hides_the_configured_paths(self):
        repo = self.repo_with_untracked_glossary_and_adrs()
        (repo / "docs" / "adr" / "0001-start.md").rename(repo / "docs" / "0001-start.md")
        (repo / "docs" / "adr").rmdir()
        (repo / "docs" / "decisions").mkdir()
        (repo / "docs" / "0001-start.md").rename(repo / "docs" / "decisions" / "0001-start.md")
        (repo / "GLOSSARY.md").rename(repo / "docs" / "WORDS.md")

        done = self.write(repo, {**tracer_settings(), "glossary_and_adrs": "private",
                                 "glossary": "docs/WORDS.md", "adrs": "docs/decisions"})

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", self.status(repo))
        shown = json.loads(self.show(repo).stdout)
        self.assertEqual(("docs/WORDS.md", "docs/decisions"), (shown["glossary"], shown["adrs"]))

    def test_choosing_private_from_a_linked_worktree_hides_them_in_the_main_worktree(self):
        repo = self.repo_with_untracked_glossary_and_adrs()
        worktree = self.root / f"atlas-{self.count}-feature"
        fixture.run(["git", "worktree", "add", "-q", "-b", "feature", str(worktree)], repo)

        done = self.write(worktree, {**tracer_settings(), "glossary_and_adrs": "private"})

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", self.status(repo))

    def test_choosing_committed_again_removes_the_exclude_lines_and_keeps_every_other_byte(self):
        repo = self.repo_with_untracked_glossary_and_adrs()
        with open(self.exclude_file(repo), "a", encoding="utf-8", newline="") as fh:
            fh.write("/build/\r\n/GLOSSARY.md.bak\n# GLOSSARY.md\n")
        before = self.exclude_file(repo).read_bytes()
        self.write(repo, {**tracer_settings(), "glossary_and_adrs": "private"})

        done = self.write(repo, {"glossary_and_adrs": "committed"})

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(before, self.exclude_file(repo).read_bytes())
        self.assertIn("GLOSSARY.md", self.status(repo))
        self.assertIn("docs/", self.status(repo))
        self.assertEqual("committed", json.loads(self.show(repo).stdout)["glossary_and_adrs"])

    def test_moving_a_private_glossary_swaps_its_exclude_line(self):
        repo = self.repo_with_untracked_glossary_and_adrs()
        self.write(repo, {**tracer_settings(), "glossary_and_adrs": "private"})

        done = self.write(repo, {"glossary": "docs/WORDS.md"})

        self.assertEqual(0, done.returncode, done.stderr)
        lines = self.exclude_file(repo).read_text(encoding="utf-8").splitlines()
        self.assertNotIn("/GLOSSARY.md", lines)
        self.assertEqual(1, lines.count("/docs/WORDS.md"), lines)
        self.assertEqual(1, lines.count("/docs/adr/"), lines)

    def test_a_rerun_that_leaves_out_the_choice_keeps_it_with_its_paths_and_exclude_lines(self):
        repo = self.repo_with_untracked_glossary_and_adrs()
        self.write(repo, {**tracer_settings(), "glossary_and_adrs": "private",
                          "glossary": "GLOSSARY.md", "adrs": "docs/adr"})

        done = self.write(repo, {"lap_limit": 5})

        self.assertEqual(0, done.returncode, done.stderr)
        shown = json.loads(self.show(repo).stdout)
        self.assertEqual(("private", "GLOSSARY.md", "docs/adr", 5),
                         (shown["glossary_and_adrs"], shown["glossary"], shown["adrs"], shown["lap_limit"]))
        self.assertEqual("", self.status(repo))

    def test_refuses_private_while_git_tracks_the_glossary_or_the_adrs(self):
        for tracked in ("GLOSSARY.md", "docs/adr"):
            with self.subTest(tracked=tracked):
                repo = self.repo_with_untracked_glossary_and_adrs()
                type(self).count += 1
                fixture.run(["git", "add", "--", tracked], repo)
                fixture.run(["git", "commit", "-q", "-m", "Add docs"], repo)
                before = self.exclude_file(repo).read_bytes()

                done = self.write(repo, {**tracer_settings(), "glossary_and_adrs": "private"})

                self.assertEqual(1, done.returncode)
                self.assertIn("nothing was written", done.stderr)
                self.assertIn(f"git tracks {tracked}", done.stderr)
                self.assertEqual([], self.stored_files())
                self.assertEqual(before, self.exclude_file(repo).read_bytes())

    def test_refuses_a_choice_or_a_path_jidoka_cannot_use(self):
        cases = {
            "glossary_and_adrs": ({"glossary_and_adrs": "hidden"},
                                  "glossary_and_adrs must be one of committed, private"),
            "glossary": ({"glossary": "/etc/GLOSSARY.md"}, "glossary must be a path inside the repo"),
            "adrs": ({"adrs": "../docs/adr"}, "adrs must be a path inside the repo"),
            "blank": ({"adrs": " "}, "adrs must be a path inside the repo"),
        }
        for name, (change, problem) in cases.items():
            with self.subTest(name=name):
                done = self.write(self.repo, {**tracer_settings(), **change})

                self.assertEqual(1, done.returncode)
                self.assertIn(problem, done.stderr)
                self.assertEqual([], self.stored_files())

    def test_a_session_in_a_private_repo_says_the_glossary_and_adrs_stay_uncommitted(self):
        repo = self.repo_with_untracked_glossary_and_adrs()
        worktree = self.root / f"atlas-{self.count}-feature"
        fixture.run(["git", "worktree", "add", "-q", "-b", "feature", str(worktree)], repo)
        self.write(repo, {**tracer_settings(), "glossary_and_adrs": "private", "adrs": "docs/adr"})

        for cwd in (repo, worktree):
            with self.subTest(cwd=cwd):
                done = self.session(cwd)

                self.assertEqual(0, done.returncode, done.stderr)
                self.assertIn("Planning, Factory, Acceptance and Bench", done.stdout)
                self.assertIn("GLOSSARY.md and the ADRs in docs/adr stay uncommitted in this repo", done.stdout)
                self.assertNotIn("always committed", done.stdout)

    def test_a_session_in_a_committed_repo_says_the_glossary_and_adrs_are_always_committed(self):
        self.write(self.repo, {**tracer_settings(), "glossary_and_adrs": "committed"})

        done = self.session(self.repo)

        self.assertIn("Code, tests, GLOSSARY.md and ADRs are always committed.", done.stdout)
        self.assertNotIn("uncommitted", done.stdout)

    def test_a_session_whose_settings_cannot_be_read_gets_every_rule_with_the_committed_wording(self):
        self.write(self.repo, {**tracer_settings(), "glossary_and_adrs": "committed"})
        self.stored_files()[0].write_text("{not json", encoding="utf-8")

        done = self.session(self.repo)

        self.assertIn("Planning, Factory, Acceptance and Bench", done.stdout)
        self.assertIn("Code, tests, GLOSSARY.md and ADRs are always committed.", done.stdout)

    def test_the_session_hook_says_to_onboard_a_beads_repo_without_settings(self):
        for cwd in (self.repo, self.worktree):
            with self.subTest(cwd=cwd):
                done = self.session(cwd)

                self.assertEqual(0, done.returncode, done.stderr)
                self.assertIn("Planning, Factory, Acceptance and Bench", done.stdout)
                lines = [line for line in done.stdout.splitlines() if ONBOARDING_LINE in line]
                self.assertEqual(1, len(lines), done.stdout)

    def test_the_session_hook_stops_saying_to_onboard_once_the_repo_has_settings(self):
        self.write(self.repo, tracer_settings())

        for cwd in (self.repo, self.worktree):
            with self.subTest(cwd=cwd):
                done = self.session(cwd)

                self.assertIn("Planning, Factory, Acceptance and Bench", done.stdout)
                self.assertNotIn(ONBOARDING_LINE, done.stdout)

    def test_settings_for_another_repo_do_not_silence_the_onboarding_line(self):
        self.write(self.other_repo, tracer_settings())

        done = self.session(self.repo)

        self.assertIn(ONBOARDING_LINE, done.stdout)

    def test_the_session_hook_never_says_to_onboard_a_repo_without_beads(self):
        done = self.session(self.plain_repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)


if __name__ == "__main__":
    unittest.main()
