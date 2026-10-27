import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
SYSTEM_PATH = "/usr/bin:/bin"
RUN_TIMEOUT_SECONDS = 60

JIDOKA_ENABLED = {"id": "jidoka@jidoka", "version": "0.1.12", "scope": "user", "enabled": True}
JIDOKA_DISABLED = {**JIDOKA_ENABLED, "enabled": False}
OTHER_PLUGIN = {"id": "smells@skills-dir", "version": "0.1.0", "scope": "user", "enabled": True}


class FactoryCheckCase(unittest.TestCase):
    """A copy of the plugin, a jidoka home that knows the Python, and a fake claude whose plugin list the test picks."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.plugin = self.root / "plugins" / "jidoka"
        shutil.copytree(PLUGIN, self.plugin)
        self.jidoka_home = self.root / "jidoka-home"
        self.jidoka_home.mkdir()
        (self.jidoka_home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        self.home = self.root / "home"
        self.home.mkdir()
        self.config_dir = self.root / "claude-config"
        self.config_dir.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()

    def claude_lists(self, plugins: list) -> None:
        """Puts on the PATH a claude whose `plugin list --json` prints these plugins and which refuses anything else."""
        fixture.write_executable(self.bin / "claude", "\n".join([
            f"#!{sys.executable}",
            "import sys",
            "if sys.argv[1:] != ['plugin', 'list', '--json']:",
            "    print('the fake claude does not know this command', file=sys.stderr)",
            "    sys.exit(1)",
            f"print({json.dumps(plugins)!r})",
            ""]))

    def claude_fails(self, message: str) -> None:
        fixture.write_executable(self.bin / "claude", "\n".join([
            f"#!{sys.executable}",
            "import sys",
            f"print({message!r}, file=sys.stderr)",
            "sys.exit(1)",
            ""]))

    def hooks_load(self, modules: list) -> None:
        hooks = self.plugin / "hooks" / "hooks.json"
        settings = json.loads(hooks.read_text(encoding="utf-8"))
        settings["modules"] = modules
        hooks.write_text(json.dumps(settings), encoding="utf-8")

    def check(self, config_dir: Path | None) -> subprocess.CompletedProcess:
        env = {"PATH": f"{self.bin}:{SYSTEM_PATH}", "HOME": str(self.home), "JIDOKA_HOME": str(self.jidoka_home)}
        if config_dir is not None:
            env["CLAUDE_CONFIG_DIR"] = str(config_dir)
        return subprocess.run(["/bin/sh", str(self.plugin / "bin" / "jidoka-run"),
                               str(self.plugin / "scripts" / "factory.py"), "check"],
                              capture_output=True, text=True, encoding="utf-8", env=env, cwd=self.root,
                              timeout=RUN_TIMEOUT_SECONDS)


class FactoryCheckPassesTests(FactoryCheckCase):
    def test_passes_when_the_plugin_loads_the_lap_mod_and_the_config_dir_has_jidoka_enabled(self):
        self.claude_lists([OTHER_PLUGIN, JIDOKA_ENABLED])

        done = self.check(self.config_dir)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stderr)
        self.assertEqual(f"factory: the lap mod is loaded from {self.plugin}, and {self.config_dir} has jidoka "
                         "enabled\n", done.stdout)


class FactoryCheckLapModTests(FactoryCheckCase):
    def test_refuses_a_plugin_whose_hooks_load_no_lap_mod_and_says_to_start_a_new_session(self):
        self.claude_lists([JIDOKA_ENABLED])
        self.hooks_load([])

        done = self.check(self.config_dir)

        self.assertEqual(1, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn(f"this session runs the jidoka plugin at {self.plugin}, whose hooks do not load the lap mod",
                      done.stderr)
        self.assertIn("Start a new session", done.stderr)

    def test_refuses_a_plugin_whose_hooks_name_the_lap_mod_but_lack_its_file(self):
        self.claude_lists([JIDOKA_ENABLED])
        (self.plugin / "hooks" / "lap_mod.ts").unlink()

        done = self.check(self.config_dir)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"whose hooks do not load the lap mod: {self.plugin / 'hooks' / 'lap_mod.ts'} does not exist",
                      done.stderr)
        self.assertIn("Start a new session", done.stderr)

    def test_refuses_a_plugin_with_no_hooks_file(self):
        self.claude_lists([JIDOKA_ENABLED])
        (self.plugin / "hooks" / "hooks.json").unlink()

        done = self.check(self.config_dir)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{self.plugin / 'hooks' / 'hooks.json'} does not exist", done.stderr)
        self.assertIn("Start a new session", done.stderr)


class FactoryCheckConfigDirTests(FactoryCheckCase):
    def test_refuses_when_the_config_dir_that_claude_config_dir_names_lacks_jidoka_or_has_it_disabled(self):
        for plugins in ([OTHER_PLUGIN], [OTHER_PLUGIN, JIDOKA_DISABLED]):
            with self.subTest(plugins=plugins):
                self.claude_lists(plugins)

                done = self.check(self.config_dir)

                self.assertEqual(1, done.returncode)
                self.assertEqual("", done.stdout)
                self.assertIn(f"{self.config_dir} does not have jidoka enabled", done.stderr)
                self.assertIn(f"Run install.py --config-dir {self.config_dir} from your jidoka checkout",
                              done.stderr)

    def test_refuses_when_the_default_config_dir_under_home_lacks_jidoka_and_names_that_dir(self):
        self.claude_lists([OTHER_PLUGIN])

        done = self.check(None)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{self.home / '.claude'} does not have jidoka enabled", done.stderr)

    def test_refuses_when_claude_is_not_on_the_path_and_names_the_config_dir_it_could_not_ask(self):
        done = self.check(self.config_dir)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"claude is not on the PATH, so the check cannot tell whether {self.config_dir} has jidoka "
                      "enabled", done.stderr)

    def test_refuses_when_claude_cannot_list_its_plugins_and_shows_what_claude_said(self):
        self.claude_fails("the plugin list is unreadable")

        done = self.check(self.config_dir)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"claude plugin list --json failed under {self.config_dir}: the plugin list is unreadable",
                      done.stderr)


class FactoryCheckAllProblemsTests(FactoryCheckCase):
    def test_a_plugin_without_the_lap_mod_and_a_config_dir_without_jidoka_are_both_named_at_once(self):
        self.claude_lists([])
        self.hooks_load([])

        done = self.check(self.config_dir)

        self.assertEqual(1, done.returncode)
        self.assertIn("whose hooks do not load the lap mod", done.stderr)
        self.assertIn(f"{self.config_dir} does not have jidoka enabled", done.stderr)


if __name__ == "__main__":
    unittest.main()
