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
ROUTE = PLUGIN / "scripts" / "route.py"

RUN_TIMEOUT_SECONDS = 120
JEFF = "Jeff Router"
CODEX = {"harness": "codex", "model": None, "version": None, "effort": None}
NATIVE_OPUS = {"harness": "claude", "model": "opus", "version": "5.5", "effort": "high"}
NATIVE_SONNET = {"harness": "claude", "model": "sonnet", "version": "5.5", "effort": "high"}
T3_CODEX = {"harness": "t3", "provider": "codex", "model": "gpt-6.1-sol", "version": None, "effort": "high"}
NATIVE_LOCAL = {"harness": "claude", "model": "sonnet", "version": "5.5", "effort": "medium"}
ROUTES = {"standard": NATIVE_SONNET, "deep": NATIVE_OPUS, "second": CODEX, "local": T3_CODEX}


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


class RouteCase(unittest.TestCase):
    """The shop repo with the fake bd first on the route script's PATH, and a jidoka home whose settings route the
    second tier to codex."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.home = cls.root / "jidoka-home"
        cls.home.mkdir()
        (cls.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        (cls.home / "settings.json").write_text(json.dumps({"routes": ROUTES}), encoding="utf-8")
        cls.repo = cls.root / "shop"
        fixture.init_repo(cls.repo)
        git(cls.repo, "config", "user.name", JEFF)
        (cls.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(cls.repo, "Start")
        git(cls.repo, "branch", "-M", "main")
        cls.bin = cls.root / "bin"
        cls.bd = str(fixture.add_fake_beads(cls.repo, cls.bin))
        cls.count = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def new_task(self) -> str:
        type(self).count += 1
        created = json.loads(fixture.run([self.bd, "create", "--title", f"Read the card {self.count}",
                                          "--type=task", "--json"], self.repo))
        return created["id"]

    def route(self, *args: str, home: Path | None = None) -> subprocess.CompletedProcess:
        env = {**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(home or self.home)}
        return fixture.run_launcher(LAUNCHER, [str(ROUTE), *args], None, env, self.repo, RUN_TIMEOUT_SECONDS)

    def fall_back(self, task: str, stage: str, tier: str, run: str) -> dict:
        done = self.route("fallback", task, stage, tier, "--run", run)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def shown(self, bead: str) -> dict:
        return json.loads(fixture.run([self.bd, "show", bead, "--json"], self.repo))[0]

    def comments(self, bead: str) -> list[dict]:
        return json.loads(fixture.run([self.bd, "comments", bead, "--json"], self.repo) or "[]") or []


class FallbackTests(RouteCase):
    def test_a_failing_route_reruns_its_stage_on_the_native_route_of_its_tier(self):
        task = self.new_task()

        printed = self.fall_back(task, "build", "second", "1")

        self.assertEqual({"rerun": True, "route": NATIVE_OPUS}, printed)

    def test_a_failing_t3_route_reruns_its_stage_on_the_native_route_of_its_tier(self):
        task = self.new_task()

        printed = self.fall_back(task, "review", "local", "1")

        self.assertEqual({"rerun": True, "route": NATIVE_LOCAL}, printed)
        [comment] = self.comments(task)
        self.assertIn("t3", comment["text"])

    def test_the_fallback_is_written_on_the_task_with_a_comment_that_names_the_failed_route(self):
        task = self.new_task()

        self.fall_back(task, "build", "second", "1")

        self.assertEqual("1", str(self.shown(task)["metadata"]["route.native.build"]))
        [comment] = self.comments(task)
        self.assertIn("build", comment["text"])
        self.assertIn("codex", comment["text"])

    def test_a_stage_reruns_on_native_only_once_in_a_run(self):
        task = self.new_task()
        self.fall_back(task, "build", "second", "1")
        comments_before = self.comments(task)

        printed = self.fall_back(task, "build", "second", "1")

        self.assertFalse(printed["rerun"])
        self.assertEqual(comments_before, self.comments(task))

    def test_the_next_run_of_the_stage_may_fall_back_again(self):
        task = self.new_task()
        self.fall_back(task, "build", "second", "1")

        printed = self.fall_back(task, "build", "second", "2")

        self.assertTrue(printed["rerun"])
        self.assertEqual("2", str(self.shown(task)["metadata"]["route.native.build"]))

    def test_another_stage_of_the_same_run_falls_back_on_its_own(self):
        task = self.new_task()
        self.fall_back(task, "build", "second", "1")

        printed = self.fall_back(task, "merge", "second", "1")

        self.assertTrue(printed["rerun"])

    def test_a_route_that_already_runs_natively_has_nothing_to_fall_back_to(self):
        task = self.new_task()

        printed = self.fall_back(task, "build", "standard", "1")

        self.assertFalse(printed["rerun"])
        self.assertIn("standard", printed["why"])
        self.assertNotIn("route.native.build", self.shown(task).get("metadata") or {})
        self.assertEqual([], self.comments(task))

    def test_a_home_without_settings_refuses_and_writes_nothing(self):
        task = self.new_task()
        missing = self.root / "home-without-settings"
        missing.mkdir(exist_ok=True)
        (missing / "python").write_text(sys.executable + "\n", encoding="utf-8")

        done = self.route("fallback", task, "build", "second", "--run", "1", home=missing)

        self.assertEqual(1, done.returncode)
        self.assertIn("settings.json does not exist", done.stderr)
        self.assertEqual([], self.comments(task))

    def test_a_tier_the_settings_lack_refuses_and_writes_nothing(self):
        task = self.new_task()

        done = self.route("fallback", task, "build", "light", "--run", "1")

        self.assertEqual(1, done.returncode)
        self.assertIn("'light'", done.stderr)
        self.assertEqual([], self.comments(task))


if __name__ == "__main__":
    unittest.main()
