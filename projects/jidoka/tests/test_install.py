from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import install  # noqa: E402
import jidoka_fixture as fixture  # noqa: E402


def older_python() -> str | None:
    for candidate in ["python3.9", "python3.8", "/usr/bin/python3"]:
        found = shutil.which(candidate)
        if found is None:
            continue
        version = subprocess.run([found, "-c", "import sys; print(sys.version_info >= (3, 10))"],
                                 capture_output=True, text=True, encoding="utf-8")
        if version.returncode == 0 and version.stdout.strip() == "False":
            return found
    return None


class InstallerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "checkout"
        self.home = self.root / "jidoka-home"
        self.log = self.root / "calls.log"
        self.bin = self.root / "bin"
        self.user_home = self.root / "user"
        self.user_home.mkdir()
        self.config_a = self.root / "claude-a"
        self.config_b = self.root / "claude-b"
        fixture.build_checkout(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, tools: fixture.ToolsOnPath, config_dirs: list, claude_fails_on: str) -> subprocess.CompletedProcess:
        fixture.build_bin(self.bin, tools, self.log, claude_fails_on)
        args = ["--jidoka-home", str(self.home)]
        for config_dir in config_dirs:
            args += ["--config-dir", str(config_dir)]
        return fixture.run_script(self.repo, "install.py", args, fixture.script_env(self.bin, self.user_home))

    def calls(self, tool: str) -> list:
        return [call for call in fixture.read_log(self.log) if call["tool"] == tool]

    def settings(self) -> dict:
        return json.loads((self.home / "settings.json").read_text(encoding="utf-8"))


class InstallIntoConfigDirTests(InstallerTestCase):
    def test_each_named_config_dir_gets_the_marketplace_added_and_the_plugin_installed_at_user_scope(self):
        done = self.install(fixture.WITHOUT_CODEX, [self.config_a, self.config_b], "")

        self.assertEqual(0, done.returncode, done.stderr)
        plugin_folder = str((self.repo / "plugin").resolve())
        for config_dir in [self.config_a, self.config_b]:
            commands = [call["argv"] for call in self.calls("claude") if call["config_dir"] == str(config_dir.resolve())]
            self.assertEqual(["plugin", "marketplace", "add", plugin_folder], commands[0])
            self.assertIn(["plugin", "install", "jidoka@jidoka", "--scope", "user"], commands)
            self.assertLess(commands.index(["plugin", "marketplace", "add", plugin_folder]),
                            commands.index(["plugin", "install", "jidoka@jidoka", "--scope", "user"]))

    def test_codex_gets_the_marketplace_and_the_plugin_when_it_is_on_the_path(self):
        done = self.install(fixture.ALL_TOOLS, [self.config_a], "")

        self.assertEqual(0, done.returncode, done.stderr)
        plugin_folder = str((self.repo / "plugin").resolve())
        self.assertEqual([["plugin", "marketplace", "add", plugin_folder], ["plugin", "add", "jidoka@jidoka"]],
                         [call["argv"] for call in self.calls("codex")])

    def test_codex_is_left_alone_when_it_is_not_on_the_path(self):
        done = self.install(fixture.WITHOUT_CODEX, [self.config_a], "")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], self.calls("codex"))

    def test_running_it_again_refreshes_the_marketplace_and_updates_the_plugin_in_each_config_dir(self):
        self.install(fixture.WITHOUT_CODEX, [self.config_a], "")
        self.log.unlink()

        done = self.install(fixture.WITHOUT_CODEX, [self.config_a], "")

        self.assertEqual(0, done.returncode, done.stderr)
        commands = [call["argv"] for call in self.calls("claude")]
        self.assertIn(["plugin", "marketplace", "update", "jidoka"], commands)
        self.assertIn(["plugin", "update", "jidoka@jidoka", "--scope", "user"], commands)

    def test_a_failing_claude_command_stops_the_run_and_names_the_command(self):
        done = self.install(fixture.WITHOUT_CODEX, [self.config_a], claude_fails_on="install")

        self.assertEqual(2, done.returncode)
        self.assertIn("plugin install jidoka@jidoka", done.stderr)
        self.assertIn("the fake refuses this call", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_it_reports_the_version_it_installed(self):
        done = self.install(fixture.WITHOUT_CODEX, [self.config_a], "")

        self.assertIn("0.1.0", done.stdout)

    def test_naming_no_config_dir_is_refused_and_nothing_is_written(self):
        done = self.install(fixture.WITHOUT_CODEX, [], "")

        self.assertEqual(2, done.returncode)
        self.assertIn("--config-dir", done.stderr)
        self.assertFalse(self.home.exists())
        self.assertEqual([], fixture.read_log(self.log))


class RecordedSettingsTests(InstallerTestCase):
    def test_the_python_that_ran_the_installer_is_recorded_in_one_line(self):
        self.install(fixture.WITHOUT_CODEX, [self.config_a], "")

        self.assertEqual(sys.executable + "\n", (self.home / "python").read_text(encoding="utf-8"))

    def test_the_settings_hold_the_python_the_config_dirs_and_a_route_for_each_tier(self):
        self.install(fixture.ALL_TOOLS, [self.config_a, self.config_b], "")

        settings = self.settings()
        self.assertEqual(sys.executable, settings["python"])
        self.assertEqual([str(self.config_a.resolve()), str(self.config_b.resolve())], settings["config_dirs"])
        self.assertEqual({
            "light": {"harness": "claude", "model": "haiku", "version": "5.5", "effort": "medium"},
            "standard": {"harness": "claude", "model": "sonnet", "version": "5.5", "effort": "high"},
            "deep": {"harness": "claude", "model": "opus", "version": "5.5", "effort": "high"},
            "second": {"harness": "codex", "model": None, "version": None, "effort": None},
            "local": {"harness": "claude", "model": "sonnet", "version": "5.5", "effort": "medium"},
        }, settings["routes"])

    def test_the_second_route_runs_in_claude_when_codex_is_not_on_the_path(self):
        self.install(fixture.WITHOUT_CODEX, [self.config_a], "")

        self.assertEqual({"harness": "claude", "model": "opus", "version": "5.5", "effort": "high"},
                         self.settings()["routes"]["second"])

    def test_settings_keys_the_installer_does_not_own_survive_a_second_run(self):
        self.install(fixture.WITHOUT_CODEX, [self.config_a], "")
        kept = self.settings()
        kept["budget"] = {"weekly": 40}
        kept["config_dirs"] = ["/stale"]
        (self.home / "settings.json").write_text(json.dumps(kept), encoding="utf-8")

        self.install(fixture.WITHOUT_CODEX, [self.config_b], "")

        settings = self.settings()
        self.assertEqual({"weekly": 40}, settings["budget"])
        self.assertEqual([str(self.config_b.resolve())], settings["config_dirs"])

    def test_a_settings_file_that_is_not_json_stops_the_run_before_anything_is_installed(self):
        self.home.mkdir()
        (self.home / "settings.json").write_text("{not json", encoding="utf-8")

        done = self.install(fixture.WITHOUT_CODEX, [self.config_a], "")

        self.assertEqual(2, done.returncode)
        self.assertIn("settings.json", done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assertEqual([], fixture.read_log(self.log))
        self.assertFalse((self.home / "python").exists())

    def test_the_home_defaults_to_the_jidoka_folder_in_the_users_home(self):
        fixture.build_bin(self.bin, fixture.WITHOUT_CODEX, self.log, "")

        done = fixture.run_script(self.repo, "install.py", ["--config-dir", str(self.config_a)],
                                  fixture.script_env(self.bin, self.user_home))

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertTrue((self.user_home / ".jidoka" / "python").is_file())


class PrerequisiteTests(InstallerTestCase):
    def assert_nothing_installed(self):
        self.assertFalse(self.home.exists())
        self.assertEqual([], fixture.read_log(self.log))

    def test_a_missing_tool_is_named_and_nothing_is_installed(self):
        cases = {
            "git": fixture.ToolsOnPath(git=False, bd=fixture.Bd.FAKE, claude=True, codex=True),
            "bd": fixture.ToolsOnPath(git=True, bd=fixture.Bd.NONE, claude=True, codex=True),
            "claude": fixture.ToolsOnPath(git=True, bd=fixture.Bd.FAKE, claude=False, codex=True),
        }
        for name, tools in cases.items():
            with self.subTest(missing=name):
                self.bin = self.root / f"bin-without-{name}"

                done = self.install(tools, [self.config_a], "")

                self.assertEqual(2, done.returncode)
                self.assertIn(f"`{name}`", done.stderr)
                self.assert_nothing_installed()

    def test_every_missing_tool_is_named_in_one_message(self):
        done = self.install(fixture.ToolsOnPath(git=False, bd=fixture.Bd.NONE, claude=False, codex=False), [self.config_a], "")

        self.assertEqual(2, done.returncode)
        for name in ["git", "bd", "claude"]:
            self.assertIn(f"`{name}`", done.stderr)
        self.assertNotIn("codex", done.stderr)
        self.assert_nothing_installed()

    def test_an_installer_run_by_a_python_older_than_3_10_names_it_instead_of_crashing(self):
        old_python = older_python()
        if old_python is None:
            self.skipTest("no Python older than 3.10 on this machine")
        fixture.build_bin(self.bin, fixture.WITHOUT_CODEX, self.log, "")

        done = subprocess.run([old_python, str(self.repo / "install.py"), "--config-dir", str(self.config_a),
                               "--jidoka-home", str(self.home)],
                              capture_output=True, text=True, encoding="utf-8", cwd=self.repo,
                              env=fixture.script_env(self.bin, self.user_home))

        self.assertEqual(2, done.returncode, done.stderr)
        self.assertIn("Python 3.10", done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assert_nothing_installed()

    def test_a_python_older_than_3_10_is_named_as_missing(self):
        everything_found = lambda name: f"/bin/{name}"

        missing = install.find_missing((3, 9), everything_found)

        self.assertEqual(1, len(missing))
        self.assertIn("Python 3.10", missing[0])
        self.assertIn("3.9", missing[0])

    def test_python_3_10_and_all_three_tools_leave_nothing_missing(self):
        self.assertEqual([], install.find_missing((3, 10), lambda name: f"/bin/{name}"))

    def test_the_missing_tools_and_an_old_python_come_back_together(self):
        missing = install.find_missing((3, 8), lambda name: None)

        self.assertEqual(4, len(missing))


class DirtyPluginFolderTests(InstallerTestCase):
    def test_an_edited_file_in_the_plugin_folder_stops_the_install_and_is_named(self):
        manifest = self.repo / "plugin" / "jidoka" / ".claude-plugin" / "plugin.json"
        manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        done = self.install(fixture.ALL_TOOLS, [self.config_a], "")

        self.assertEqual(2, done.returncode)
        self.assertIn("plugin/jidoka/.claude-plugin/plugin.json", done.stderr)
        self.assertFalse(self.home.exists())
        self.assertEqual([], fixture.read_log(self.log))

    def test_a_new_untracked_file_in_a_new_folder_of_the_plugin_stops_the_install_and_is_named(self):
        (self.repo / "plugin" / "jidoka" / "skills" / "draft").mkdir(parents=True)
        (self.repo / "plugin" / "jidoka" / "skills" / "draft" / "notes.txt").write_text("scratch\n", encoding="utf-8")

        done = self.install(fixture.ALL_TOOLS, [self.config_a], "")

        self.assertEqual(2, done.returncode)
        self.assertIn("plugin/jidoka/skills/draft/notes.txt", done.stderr)
        self.assertFalse(self.home.exists())

    def test_an_update_stops_for_an_uncommitted_change_and_leaves_the_recorded_settings_as_they_were(self):
        self.install(fixture.ALL_TOOLS, [self.config_a], "")
        before = (self.home / "settings.json").read_text(encoding="utf-8")
        self.log.unlink()
        (self.repo / "plugin" / "jidoka" / "bin" / "jidoka-run").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        done = self.install(fixture.ALL_TOOLS, [self.config_b], "")

        self.assertEqual(2, done.returncode)
        self.assertIn("plugin/jidoka/bin/jidoka-run", done.stderr)
        self.assertEqual(before, (self.home / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual([], fixture.read_log(self.log))

    def test_changes_outside_the_plugin_folder_do_not_stop_the_install(self):
        (self.repo / "scratch.txt").write_text("not part of the plugin\n", encoding="utf-8")

        done = self.install(fixture.ALL_TOOLS, [self.config_a], "")

        self.assertEqual(0, done.returncode, done.stderr)

    def test_a_plugin_folder_outside_any_git_repo_is_refused(self):
        loose = self.root / "loose"
        loose.mkdir()
        shutil.copy2(fixture.PROJECT / "install.py", loose / "install.py")
        shutil.copytree(fixture.PROJECT / "plugin", loose / "plugin")
        fixture.build_bin(self.bin, fixture.ALL_TOOLS, self.log, "")

        done = fixture.run_script(loose, "install.py", ["--jidoka-home", str(self.home), "--config-dir", str(self.config_a)],
                                  fixture.script_env(self.bin, self.user_home))

        self.assertEqual(2, done.returncode)
        self.assertIn("git repository", done.stderr)
        self.assertFalse(self.home.exists())


class StealthWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_dir = tempfile.TemporaryDirectory()
        cls.template = Path(cls.template_dir.name) / "checkout"
        fixture.build_checkout(cls.template)
        fixture.run(["bd", "init", "--stealth", "--non-interactive"], cls.template)
        fixture.run(["bd", "create", "--title=Carry on", "--type=task"], cls.template)

    @classmethod
    def tearDownClass(cls):
        cls.template_dir.cleanup()

    def test_a_checkout_with_a_stealth_bd_workspace_installs_and_the_workspace_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = fixture.ToolsOnPath(git=True, bd=fixture.Bd.REAL, claude=True, codex=False)
            fixture.build_bin(root / "bin", tools, root / "calls.log", "")
            user = root / "user"
            user.mkdir()

            done = fixture.run_script(self.template, "install.py",
                                      ["--jidoka-home", str(root / "home"), "--config-dir", str(root / "claude")],
                                      fixture.script_env(root / "bin", user))

            self.assertEqual(0, done.returncode, done.stderr)
            self.assertIn("Carry on", fixture.run(["bd", "list"], self.template))
            self.assertEqual("", fixture.run(["git", "status", "--porcelain"], self.template))


if __name__ == "__main__":
    unittest.main()
