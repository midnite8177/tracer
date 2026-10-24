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
HOOK = PLUGIN / "hooks" / "session_start.py"
ONBOARDING_LINE = "/jidoka:onboard"


def tracer_apps() -> list:
    return [
        {"name": "tracer-ui", "kind": "program", "way_in": "its web UI",
         "build": "dotnet build projects/tracer-ui/TracerUi.slnx",
         "run": "dotnet run --project projects/tracer-ui/src/TracerUi.Web",
         "test": "dotnet test projects/tracer-ui/TracerUi.slnx",
         "test_target": '--filter "FullyQualifiedName~<Class>"'},
        {"name": "tracer-seed", "kind": "program", "way_in": "its command line",
         "build": "python3 projects/tracer-seed/build.py", "run": "python3 projects/tracer-seed/build.py",
         "test": "python3 -m unittest discover -s projects/tracer-seed/tests", "test_target": "-k <name>"},
        {"name": "jidoka", "kind": "program", "way_in": "its command line", "build": None,
         "run": "python3 projects/jidoka/install.py --config-dir <path>",
         "test": "python3 -m unittest discover -s projects/jidoka/tests", "test_target": "-k <name>"},
    ]


def tracer_settings() -> dict:
    return {
        "lap_test_scope": "targeted",
        "worker_commands": ["dotnet build", "dotnet test", "python3 -m unittest"],
        "slot_use": None,
        "lap_limit": 3,
        "apps": tracer_apps(),
    }


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

    def test_refuses_settings_in_which_no_app_has_a_build_and_writes_nothing(self):
        settings = tracer_settings()
        for app in settings["apps"]:
            app["build"] = None

        done = self.write(self.repo, settings)

        self.assertNotEqual(0, done.returncode)
        self.assertIn("build", done.stderr)
        self.assertEqual([], self.stored_files())

    def test_refuses_an_app_without_a_test_command_and_leaves_claude_local_md_untouched(self):
        local = self.repo / "CLAUDE.local.md"
        local.write_bytes(b"# shop\r\nbuild with make\r\n")
        settings = tracer_settings()
        settings["apps"][1]["test"] = None
        settings["moved_lines"] = ["build with make"]

        done = self.write(self.repo, settings)

        self.assertNotEqual(0, done.returncode)
        self.assertIn("tracer-seed", done.stderr)
        self.assertIn("test command", done.stderr)
        self.assertEqual([], self.stored_files())
        self.assertEqual(b"# shop\r\nbuild with make\r\n", local.read_bytes())

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
