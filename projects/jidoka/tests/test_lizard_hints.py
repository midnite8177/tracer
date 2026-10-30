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
import test_review  # noqa: E402
import test_scheduler  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
LIZARD_SCRIPT = PLUGIN / "scripts" / "lizard_hints.py"
SETTINGS_SCRIPT = PLUGIN / "scripts" / "repo_settings.py"
TIMEOUT_SECONDS = 120
LIMITS = {"ccn": 5, "length": 80, "arguments": 6}
MODULE = "till.py"


def branching(name: str, branches: int) -> str:
    """A Python function with one decision for each branch, so its cyclomatic complexity is branches plus one."""
    body = "".join(f"    if value == {number}:\n        return {number}\n" for number in range(branches))
    return f"def {name}(value):\n{body}    return 0\n"


def shop_settings(limits: dict) -> dict:
    return {"lap_test_scope": "targeted", "worker_commands": [], "slot_use": None, "lap_limit": 1,
            "apps": [{"name": "shop", "kind": "program", "way_in": "its command line", "build": "make",
                      "run": None, "test": "make test", "test_target": "-k <name>", "test_full": None,
                      "hand_run": []}],
            "lizard_limits": limits}


class LizardScriptCase(unittest.TestCase):
    """A temporary git repo with a temporary jidoka home that records the shop's settings."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self.repo = root / "shop"
        fixture.init_repo(self.repo)
        self.home = root / "home"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        self.record(LIMITS)

    def record(self, limits: dict) -> None:
        done = self.launch(SETTINGS_SCRIPT, "write", stdin=json.dumps(shop_settings(limits)))
        self.assertEqual(0, done.returncode, done.stderr)

    def launch(self, script: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run(fixture.launch_command(LAUNCHER, [str(script), *args]), input=stdin,
                              capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_SECONDS,
                              cwd=self.repo, env={**os.environ, "JIDOKA_HOME": str(self.home)})

    def commit(self, files: dict[str, str]) -> str:
        for name, text in files.items():
            (self.repo / name).write_text(text, encoding="utf-8")
        fixture.git_commit_all(self.repo, "Change " + ", ".join(files))
        return fixture.run(["git", "rev-parse", "HEAD"], self.repo).strip()

    def hints(self, base: str, head: str, *files: str) -> list[dict]:
        done = self.launch(LIZARD_SCRIPT, base, head, *files)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)


class LizardScriptTests(LizardScriptCase):
    def test_lists_a_function_the_range_added_past_a_limit(self):
        base = self.commit({"README.md": "shop\n"})
        head = self.commit({MODULE: branching("total", 9)})

        [hint] = self.hints(base, head)

        self.assertEqual({"file": MODULE, "line": 1, "name": "total", "metric": "ccn", "value": 10, "limit": 5,
                          "was": None}, hint)

    def test_lists_a_function_that_grew_past_a_limit(self):
        base = self.commit({MODULE: branching("total", 2)})
        head = self.commit({MODULE: branching("total", 9)})

        [hint] = self.hints(base, head)

        self.assertEqual(("total", "ccn", 10, 3), (hint["name"], hint["metric"], hint["value"], hint["was"]))

    def test_leaves_out_a_function_that_was_already_past_a_limit_and_did_not_grow(self):
        base = self.commit({MODULE: branching("total", 9)})
        head = self.commit({MODULE: branching("total", 9) + "\n\n" + branching("small", 1), "README.md": "shop\n"})

        self.assertEqual([], self.hints(base, head))

    def test_leaves_out_a_function_that_grew_but_stays_within_the_limits(self):
        base = self.commit({MODULE: branching("total", 1)})
        head = self.commit({MODULE: branching("total", 3)})

        self.assertEqual([], self.hints(base, head))

    def test_lists_a_function_that_is_too_long_or_takes_too_many_arguments(self):
        base = self.commit({"README.md": "shop\n"})
        long_body = "def sweep(a, b, c, d, e, f, g, h):\n" + "    value = 1\n" * 90 + "    return value\n"
        head = self.commit({MODULE: long_body})

        hints = self.hints(base, head)

        self.assertEqual({("length", 92), ("arguments", 8)}, {(each["metric"], each["value"]) for each in hints})

    def test_measures_against_the_limits_the_settings_record(self):
        base = self.commit({"README.md": "shop\n"})
        head = self.commit({MODULE: branching("total", 3)})
        self.assertEqual([], self.hints(base, head))

        self.record({"ccn": 2, "length": 80, "arguments": 6})

        self.assertEqual(["total"], [each["name"] for each in self.hints(base, head)])

    def test_measures_against_the_default_limits_when_the_stored_settings_hold_none(self):
        [stored] = (self.home / "repos").glob("*.json")
        settings = json.loads(stored.read_text(encoding="utf-8"))
        del settings["lizard_limits"]
        stored.write_text(json.dumps(settings), encoding="utf-8")
        base = self.commit({"README.md": "shop\n"})
        head = self.commit({MODULE: branching("total", 15)})

        self.assertEqual(["total"], [each["name"] for each in self.hints(base, head)])

    def test_reads_csharp_and_leaves_out_a_file_in_a_language_it_does_not_know(self):
        base = self.commit({"README.md": "shop\n"})
        branches = "".join(f"if (value == {number}) {{ return {number}; }}\n" for number in range(9))
        csharp = f"class Till {{\n int Total(int value) {{\n{branches} return 0;\n }}\n}}\n"
        head = self.commit({"Till.cs": csharp, "notes.txt": branches})

        hints = self.hints(base, head)

        self.assertEqual([("Till.cs", "ccn")], [(each["file"], each["metric"]) for each in hints])

    def test_lists_only_the_files_it_is_given(self):
        base = self.commit({"README.md": "shop\n"})
        head = self.commit({MODULE: branching("total", 9), "reader.py": branching("read", 9)})

        self.assertEqual(["reader.py"], [each["file"] for each in self.hints(base, head, "reader.py")])

    def test_exits_zero_for_a_file_that_is_not_text(self):
        base = self.commit({"README.md": "shop\n"})
        (self.repo / "blob.py").write_bytes(b"\xff\xfe\x00def (:\n")
        fixture.git_commit_all(self.repo, "Add a blob")
        head = fixture.run(["git", "rev-parse", "HEAD"], self.repo).strip()

        self.assertEqual([], self.hints(base, head))


class DesignLaneHintsTests(test_review.ReviewCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        command = fixture.launch_command(test_scheduler.LAUNCHER, [str(test_scheduler.SETTINGS_SCRIPT), "write"])
        done = subprocess.run(command, input=json.dumps({"lizard_limits": LIMITS}), capture_output=True, text=True,
                              encoding="utf-8", timeout=TIMEOUT_SECONDS, cwd=cls.repo,
                              env={**os.environ, "JIDOKA_HOME": str(cls.home)})
        if done.returncode != 0:
            raise fixture.FixtureError(f"repo_settings.py write failed: {done.stderr}")

    def finish_epic_with_a_long_function(self) -> tuple[str, dict]:
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), MODULE, branching("total", 9))
        return epic, self.tidied(test_scheduler.SchedulerCase.build_done(self, epic, action["task"]))

    def lane(self, printed: dict, name: str) -> dict:
        [action] = [each for each in self.review_actions_of(printed) if each["lane"] == name]
        return action

    def test_the_design_lane_is_given_the_hints_for_the_functions_the_epic_grew_and_the_other_lanes_are_not(self):
        epic, printed = self.finish_epic_with_a_long_function()

        [hint] = self.lane(printed, "design")["hints"]

        self.assertEqual(("total", "ccn", 10), (hint["name"], hint["metric"], hint["value"]))
        for name in ("comments", "standards", "spec"):
            self.assertNotIn("hints", self.lane(printed, name))

    def test_an_epic_that_grows_a_long_function_shows_the_hint_in_the_review_and_still_reaches_the_gate(self):
        epic, printed = self.finish_epic_with_a_long_function()

        moved = self.reviewed(printed, {})

        [hint] = moved["review"]["low"]
        self.assertEqual(("design", MODULE), (hint["lane"], hint["file"]))
        self.assertIn("Lizard hint", hint["title"])
        self.assertEqual([], [each for each in moved["actions"] if each["action"] == "fix"])
        self.assertEqual("pass", moved["validation"]["result"])
        self.assertIn("human", self.shown(epic)["labels"])
        [gate] = self.gate_comments(epic)
        self.assertIn("Lizard hint", gate)

    def test_a_function_a_later_pass_grows_gives_no_hint_because_only_the_first_review_has_the_design_lane(self):
        epic, printed = self.finish_epic_with_a_long_function()
        moved, task = self.red_validation(printed)
        [lap] = [each for each in moved["actions"] if each.get("task") == task]
        self.leave_in(Path(lap["worktree"]), "reader.py", branching("read", 9))
        second = self.tidied(test_scheduler.SchedulerCase.build_done(self, epic, task))

        again = self.reviewed(second, {})

        self.assertNotIn("design", [each["lane"] for each in self.review_actions_of(second)])
        self.assertEqual([], again["review"]["low"])

    def test_a_hint_is_not_fixed_nor_filed_as_a_task(self):
        epic, printed = self.finish_epic_with_a_long_function()

        moved = self.reviewed(printed, {})

        self.assertEqual(([], []), (moved["review"]["filed"], self.lap_actions(moved)))
        self.assertEqual([], moved["review"]["fixes"])


if __name__ == "__main__":
    unittest.main()
