import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import install  # noqa: E402
import jidoka_fixture as fixture  # noqa: E402
import test_factory  # noqa: E402

PLUGIN_HOOKS = fixture.PROJECT / "plugin" / "jidoka" / "hooks" / "hooks.json"
INSTALLED_GROUPS = install.antigravity_hooks(PLUGIN_HOOKS, Path("/home/jidoka/plugins/0.1.62/jidoka"),
                                             Path("/home/jidoka"))["jidoka"]["PreToolUse"]
GUARD_GROUP = INSTALLED_GROUPS[-1]
OTHER_GROUP = {"matcher": "run_command",
               "hooks": [{"type": "command", "command": 'sh "/home/jidoka/bin/jidoka-run" "/home/jidoka/hooks/x.py"',
                          "timeout": 60}]}
THREAD = "thread-of-the-manager"


class FactoryCheckOnAntigravityTests(test_factory.FactoryCheckCase):
    """The check run from a T3 thread that exports no jidoka session, which is how an Antigravity host runs it. T3's
    userdata is under the temp home, and no claude is on the PATH: Antigravity has no `claude plugin list`."""

    def setUp(self):
        super().setUp()
        self.profiles = self.home / ".t3" / "userdata" / "providers" / "antigravity"

    def install_copy(self, profile: str, groups: list | None) -> None:
        """Gives the profile a config folder and, unless groups is None, a jidoka copy whose hooks.json holds these
        PreToolUse groups."""
        config = self.profiles / profile / "config"
        config.mkdir(parents=True)
        if groups is not None:
            copy = config / "plugins" / "jidoka"
            copy.mkdir(parents=True)
            (copy / "hooks.json").write_text(json.dumps({"jidoka": {"PreToolUse": groups}}), encoding="utf-8")

    def check_in_a_thread(self, acp_node: str | None) -> subprocess.CompletedProcess:
        env = {"PATH": test_factory.SYSTEM_PATH, "HOME": str(self.home), "USERPROFILE": str(self.home),
               "JIDOKA_HOME": str(self.jidoka_home), "T3CODE_THREAD_ID": THREAD,
               **fixture.system_variables(os.environ, fixture.WINDOWS)}
        if acp_node is not None:
            env["T3_ACP_MCP_NODE"] = acp_node
        return fixture.run_launcher(self.plugin / "bin" / "jidoka-run",
                                    [str(self.plugin / "scripts" / "factory.py"), "check"], None, env, self.root,
                                    test_factory.RUN_TIMEOUT_SECONDS)

    def test_passes_when_the_profile_copy_carries_the_guard_without_asking_claude_or_the_lap_mod(self):
        self.install_copy("profile-a", [OTHER_GROUP, GUARD_GROUP])
        self.hooks_load([])

        done = self.check_in_a_thread("acp-node")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stderr)
        self.assertEqual(f"factory: the profile guard is in the jidoka copy of {self.profiles / 'profile-a'}\n",
                         done.stdout)

    def test_passes_for_every_group_the_installer_writes_into_a_profile_copy(self):
        self.install_copy("profile-a", INSTALLED_GROUPS)

        done = self.check_in_a_thread("acp-node")

        self.assertEqual(0, done.returncode, done.stderr)

    def test_refuses_a_profile_copy_that_holds_no_guard_and_says_to_run_the_installer(self):
        self.install_copy("profile-a", [OTHER_GROUP])

        done = self.check_in_a_thread("acp-node")

        self.assertEqual(1, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn(f"the jidoka copy in {self.profiles / 'profile-a'} holds no profile guard", done.stderr)
        self.assertIn("Run install.py from your jidoka checkout", done.stderr)

    def test_refuses_one_profile_without_the_guard_though_another_carries_it(self):
        self.install_copy("profile-a", [GUARD_GROUP])
        self.install_copy("profile-b", [OTHER_GROUP])

        done = self.check_in_a_thread("acp-node")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"the jidoka copy in {self.profiles / 'profile-b'} holds no profile guard", done.stderr)
        self.assertNotIn("profile-a", done.stderr)

    def test_refuses_when_no_profile_holds_a_jidoka_copy(self):
        self.install_copy("profile-a", None)

        done = self.check_in_a_thread("acp-node")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"no T3 Antigravity profile under {self.profiles} holds a jidoka copy", done.stderr)

    def test_names_a_missing_acp_node_and_a_missing_guard_in_one_refusal(self):
        self.install_copy("profile-a", [OTHER_GROUP])

        done = self.check_in_a_thread(None)

        self.assertEqual(1, done.returncode)
        self.assertIn("T3_ACP_MCP_NODE is not set", done.stderr)
        self.assertIn("holds no profile guard", done.stderr)


if __name__ == "__main__":
    unittest.main()
