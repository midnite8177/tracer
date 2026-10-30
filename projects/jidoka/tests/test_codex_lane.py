import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_ledger  # noqa: E402
import test_review  # noqa: E402
import test_scheduler  # noqa: E402
from test_scheduler import PLUGIN  # noqa: E402

CODEX_LANE = PLUGIN / "scripts" / "codex_lane.py"
SPEC_REPORT_NAME = "review-spec.json"
CODEX_ROUTE = {"harness": "codex", "model": "gpt-5.5", "version": None, "effort": "high"}
USAGE = {"input_tokens": 1_000_000, "cached_input_tokens": 400_000, "output_tokens": 100_000}

FAKE_CODEX = """#!{python}
import json
import os
import subprocess
import sys
import time

behavior = json.loads(open(os.environ["CODEX_FAKE"], encoding="utf-8").read())
argv = sys.argv[1:]
for index, each in enumerate(argv):
    if each == "-c" and argv[index + 1].startswith("model_providers.openai."):
        print("Error: model_providers contains reserved built-in provider IDs: openai. "
              "Built-in providers cannot be overridden.", file=sys.stderr)
        sys.exit(1)
if "child_pid_file" in behavior:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    with open(behavior["child_pid_file"], "w", encoding="utf-8") as written:
        written.write(str(child.pid))
with open(os.environ["CODEX_CALLS"], "w", encoding="utf-8") as calls:
    json.dump({{"argv": argv, "stdin": sys.stdin.read(), "cwd": os.getcwd()}}, calls)
time.sleep(behavior.get("sleep", 0))
if "message" in behavior:
    with open(argv[argv.index("--output-last-message") + 1], "w", encoding="utf-8") as out:
        out.write(behavior["message"])
if "usage" in behavior:
    print(json.dumps({{"type": "turn.completed", "usage": behavior["usage"]}}))
print(behavior.get("stderr", ""), file=sys.stderr)
sys.exit(behavior.get("exit", 0))
"""


def spec_finding(title: str) -> dict:
    return test_review.finding(title, "small", "high")


class CodexLaneCase(test_ledger.LedgerBooks, test_review.ReviewCase):
    """The review's lanes, with a fake codex first on the PATH that a test tells how to end."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.home / "settings.json").write_text(json.dumps({"routes": {**test_ledger.ROUTES["routes"],
                                                                        "second": CODEX_ROUTE}}), encoding="utf-8")
        cls.codex_bin = cls.root / "codex-bin"
        cls.codex_bin.mkdir()
        fixture.write_executable(cls.codex_bin / "codex", FAKE_CODEX.format(python=sys.executable))
        cls.fakes = 0

    def setUp(self):
        type(self).fakes += 1
        self.behavior_file = self.root / f"codex-behavior-{self.fakes}.json"
        self.calls_file = self.root / f"codex-calls-{self.fakes}.json"
        self.codex_ends()

    def caller_env(self, home: Path) -> dict[str, str]:
        env = super().caller_env(home)
        return {**env, "PATH": f"{self.codex_bin}{os.pathsep}{env['PATH']}", "CODEX_FAKE": str(self.behavior_file),
                "CODEX_CALLS": str(self.calls_file)}

    def codex_ends(self, **behavior) -> None:
        self.behavior_file.write_text(json.dumps(behavior), encoding="utf-8")

    def codex_call(self) -> dict:
        return json.loads(self.calls_file.read_text(encoding="utf-8"))

    def spec_action_of(self, printed: dict) -> dict:
        [action] = [each for each in self.review_actions_of(printed) if each["lane"] == "spec"]
        return action

    def run_lane(self, epic: str, action: dict, *flags: str) -> subprocess.CompletedProcess:
        return self.launch(CODEX_LANE, epic, "--worktree", action["worktree"], "--report", action["report"],
                           "--base", action["base"], "--head", action["head"],
                           *(part for each in action["files"] for part in ("--file", each)), "--doc",
                           str(self.repo / "CLAUDE.md"), *flags)

    def other_lanes_found_nothing(self, printed: dict) -> None:
        for action in self.review_actions_of(printed):
            if action["lane"] != "spec":
                Path(action["report"]).write_text("[]", encoding="utf-8")

    def rows_of(self, epic: str) -> list[dict]:
        return self.passes_of(epic)


class TheSpecLaneRunsInCodexTests(CodexLaneCase):
    def test_codex_exec_runs_read_only_in_the_review_worktree_without_overriding_a_built_in_provider(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        self.codex_ends(message="[]", usage=USAGE)

        done = self.run_lane(epic, action)

        self.assertEqual(0, done.returncode, done.stderr)
        call = self.codex_call()
        argv = call["argv"]
        self.assertEqual(["exec", "--sandbox", "read-only"], argv[:3])
        self.assertEqual(action["worktree"], argv[argv.index("--cd") + 1])
        self.assertEqual([], [each for each in argv if each.startswith("model_providers")])
        self.assertEqual("gpt-5.5", argv[argv.index("--model") + 1])
        self.assertIn('model_reasoning_effort="high"', argv)
        self.assertIn(f"git diff {action['base']} {action['head']}", call["stdin"])
        self.assertIn(test_review.BUILT_FILE, call["stdin"])
        self.assertIn("Take card payments", call["stdin"])

    def test_the_lane_report_is_written_from_codexs_last_message_and_the_reviews_settle_accepts_it(self):
        epic, printed = self.finish_epic_at_the_review()
        self.other_lanes_found_nothing(printed)
        self.codex_ends(message=f"The diff is thin.\n```json\n{json.dumps([spec_finding('Missing tax')])}\n```\n",
                        usage=USAGE)

        done = self.run_lane(epic, self.spec_action_of(printed))
        settled = self.report_review(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(0, settled.returncode, settled.stderr)
        self.assertEqual({"findings": 1, "lane": "spec"},
                         {key: json.loads(done.stdout)[key] for key in ("findings", "lane")})
        [fixed] = json.loads(settled.stdout)["review"]["fixes"]
        self.assertEqual(("spec", "Missing tax"), (fixed["lane"], fixed["title"]))

    def test_a_last_message_that_is_the_bare_list_is_the_report(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        self.codex_ends(message=json.dumps([]), usage=USAGE)

        done = self.run_lane(epic, action)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], json.loads(Path(action["report"]).read_text(encoding="utf-8")))

    def test_the_run_writes_one_ledger_row_with_harness_codex_and_codexs_token_totals(self):
        epic, printed = self.finish_epic_at_the_review()
        self.codex_ends(message="[]", usage=USAGE)

        done = self.run_lane(epic, self.spec_action_of(printed))

        self.assertEqual(0, done.returncode, done.stderr)
        [row] = self.rows_of(epic)
        self.assertEqual({"stage": "review", "tier": "second", "harness": "codex", "model": "gpt-5.5",
                          "effort": "high", "agent": None, "outcome": "done", "task": None,
                          "input_tokens": 600_000, "cache_read_tokens": 400_000, "cache_write_tokens": 0,
                          "output_tokens": 100_000},
                         {key: row[key] for key in ("stage", "tier", "harness", "model", "effort", "agent", "outcome",
                                                    "task", "input_tokens", "cache_read_tokens", "cache_write_tokens",
                                                    "output_tokens")})
        self.assertAlmostEqual(3.0 + 3.0 + 0.2, row["dollars"], places=6)
        self.assertAlmostEqual(row["dollars"], float(self.metadata(epic)["spend.dollars"]), places=6)


class AFailedCodexRunExitsOneAndLeavesNoReportTests(CodexLaneCase):
    def assert_failed_without_a_report(self, epic: str, action: dict, done: subprocess.CompletedProcess,
                                       reason: str) -> None:
        self.assertEqual(1, done.returncode)
        self.assertIn(reason, done.stderr)
        self.assertFalse(Path(action["report"]).exists())
        [row] = self.rows_of(epic)
        self.assertEqual(("codex", "failed"), (row["harness"], row["outcome"]))

    def test_a_codex_that_exits_nonzero_fails_the_lane_and_leaves_no_report(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        self.codex_ends(exit=1, stderr="ERROR: You've hit your usage limit.", message="[]")

        done = self.run_lane(epic, action)

        self.assert_failed_without_a_report(epic, action, done, "usage limit")

    def test_a_last_message_with_no_list_of_findings_fails_the_lane(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        self.codex_ends(message="The diff looks fine to me.", usage=USAGE)

        done = self.run_lane(epic, action)

        self.assert_failed_without_a_report(epic, action, done, "no JSON list")

    def test_a_list_the_review_would_refuse_fails_the_lane_so_settle_never_sees_it(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        unsized = spec_finding("Missing tax")
        del unsized["size"]
        self.codex_ends(message=json.dumps([unsized]), usage=USAGE)

        done = self.run_lane(epic, action)

        self.assert_failed_without_a_report(epic, action, done, "size")

    def test_an_empty_last_message_fails_the_lane(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        self.codex_ends(message="   ")

        done = self.run_lane(epic, action)

        self.assert_failed_without_a_report(epic, action, done, "empty last message")

    def test_a_run_past_the_wall_clock_is_stopped_and_counts_as_failed(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        self.codex_ends(sleep=30, message="[]")

        done = self.run_lane(epic, action, "--wall-seconds", "1")

        self.assert_failed_without_a_report(epic, action, done, "wall clock")

    def test_a_run_past_the_wall_clock_ends_the_processes_codex_started_too(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        child_pid_file = self.root / f"codex-child-{self.fakes}.txt"
        self.codex_ends(sleep=30, message="[]", child_pid_file=str(child_pid_file))

        self.run_lane(epic, action, "--wall-seconds", "2")

        child = int(child_pid_file.read_text(encoding="utf-8"))
        self.assertTrue(self.ends_soon(child), "the process codex started is still running")

    @staticmethod
    def ends_soon(pid: int) -> bool:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if not fixture.process_is_running(pid):
                return True
            time.sleep(0.1)
        return False

    def test_settings_that_hold_no_route_for_the_second_tier_fail_the_lane_before_codex_starts(self):
        epic, printed = self.finish_epic_at_the_review()
        action = self.spec_action_of(printed)
        bare_home = self.root / "bare-home"
        bare_home.mkdir()
        (bare_home / "python").write_text((self.home / "python").read_text(encoding="utf-8"), encoding="utf-8")
        self.codex_ends(message="[]", usage=USAGE)

        done = self.launch_in(bare_home, CODEX_LANE, epic, "--worktree", action["worktree"], "--report",
                              action["report"], "--base", action["base"], "--head", action["head"],
                              *(part for each in action["files"] for part in ("--file", each)))

        self.assertEqual(1, done.returncode)
        self.assertIn("settings.json", done.stderr)
        self.assertFalse(self.calls_file.exists())
        self.assertFalse(Path(action["report"]).exists())


if __name__ == "__main__":
    unittest.main()
