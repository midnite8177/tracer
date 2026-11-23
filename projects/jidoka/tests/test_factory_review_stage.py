import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_review  # noqa: E402
from test_codex_lane import CODEX_ROUTE, FAKE_CODEX, USAGE  # noqa: E402
from test_factory_pass_stage import FACTORY, REPLY, PassStageCase  # noqa: E402
from test_factory_t3_stage import NEON  # noqa: E402

CODEX_LANE = FACTORY.parent / "codex_lane.py"
HELIUM = {"harness": "t3", "model": "gemini-4-helium", "version": None, "effort": "low", "provider": "antigravity-main",
          "driver": "antigravity"}
LANE_THREAD = "thread-of-a-lane"
FIX_THREAD = "thread-of-the-fix"
FINDINGS = {"comments": [test_review.finding("Echo", "small", "high")]}


class ReviewStageCase(PassStageCase, test_review.ReviewCase):
    """An epic at its review, the factory script run as a process in a T3 thread with T3 faked behind a fake
    `acp-mcp-call`, and the second tier routed to a fake codex."""

    def setUp(self):
        super().setUp()
        self.codex_bin = self.t3 / "codex-bin"
        self.codex_bin.mkdir()
        fixture.write_executable(self.codex_bin / "codex", FAKE_CODEX.format(python=sys.executable))
        self.codex_behavior = self.t3 / "codex-behavior.json"
        self.codex_calls = self.t3 / "codex-calls.json"
        self.codex_behavior.write_text(json.dumps({"message": "[]", "usage": USAGE}), encoding="utf-8")
        self.answer({"t3_thread_launch": {"threadId": LANE_THREAD}, **REPLY})
        self.use_routes({"standard": HELIUM, "deep": NEON, "second": CODEX_ROUTE})

    def environment(self, thread: str | None, now: int | None) -> dict[str, str]:
        environment = super().environment(thread, now)
        environment.update({"PATH": f"{self.codex_bin}{os.pathsep}{environment['PATH']}",
                            "CODEX_FAKE": str(self.codex_behavior), "CODEX_CALLS": str(self.codex_calls)})
        return environment

    def lane_scratch(self, action: dict) -> str:
        return str(Path(action["scratch"]) / f"lane-{action['lane']}")

    def lane_call(self, mode: str, action: dict, *more: str):
        return self.run_script(FACTORY, mode, "--worktree", action["worktree"], "--scratch", self.lane_scratch(action),
                               *more, "--jidoka-home", str(self.home))

    def start_lane(self, action: dict, tier: str):
        scratch = Path(self.lane_scratch(action))
        scratch.mkdir(parents=True, exist_ok=True)
        prompt = scratch / "prompt.md"
        prompt.write_text(f"Review the {action['lane']} lane.\n", encoding="utf-8")
        return self.lane_call("start", action, "--prompt", str(prompt), "--tier", tier)

    def lanes_at_the_review(self) -> tuple[str, dict, list[dict]]:
        epic, printed = self.finish_epic_at_the_review()
        return epic, printed, self.review_actions_of(printed)

    def lane_named(self, lanes: list[dict], name: str) -> dict:
        [lane] = [each for each in lanes if each["lane"] == name]
        return lane

    def epic_at_the_fix(self) -> tuple[str, dict]:
        epic, printed = self.finish_epic_at_the_review()
        return epic, self.fix_action_of(self.reviewed(printed, FINDINGS))

    def start_fix(self, action: dict):
        prompt = Path(action["scratch"]) / "prompt.md"
        prompt.write_text("Fix the findings.\n", encoding="utf-8")
        return self.stage_call("start", action, "--prompt", str(prompt), "--tier", "standard")


class StartingTheReviewLanesTests(ReviewStageCase):
    def test_each_lane_launches_one_thread_in_the_review_worktree_on_its_tiers_antigravity_route(self):
        _, _, lanes = self.lanes_at_the_review()

        for name, tier in (("comments", "standard"), ("standards", "standard"), ("design", "deep")):
            done = self.start_lane(self.lane_named(lanes, name), tier)
            self.assertEqual(0, done.returncode, done.stderr)

        models = [(each["modelSelection"]["model"], each["modelSelection"]["options"]) for each in self.launches()]
        self.assertEqual([("gemini-4-helium", {"thought_level": "low"})] * 2 + [("gemini-4-neon",
                                                                                  {"thought_level": "high"})],
                         models)
        for each in self.launches():
            self.assertEqual({"type": "existing_worktree", "worktreePath": lanes[0]["worktree"]},
                             each["workspaceStrategy"])

    def test_writes_the_lap_guard_record_of_the_review_worktree_before_the_launch(self):
        _, _, lanes = self.lanes_at_the_review()

        self.start_lane(self.lane_named(lanes, "comments"), "standard")

        self.assertEqual(1, len(self.calls()[0]["guards"]))
        held = self.guard_of(lanes[0])
        self.assertIsNotNone(held)
        self.assertEqual(("lap", "review", []), (held.kind, held.stage, held.barred))
        self.assertEqual(self.lap_list_in(lanes[0]["worktree"]), held.commands)
        self.assertIn({"command": "git diff", "then": "words", "refusing": ["--output"]}, held.commands)

    def test_each_lane_keeps_its_own_state_and_request_id_in_its_own_scratch_folder(self):
        _, _, lanes = self.lanes_at_the_review()

        printed = [json.loads(self.start_lane(self.lane_named(lanes, name), "standard").stdout)
                   for name in ("comments", "standards")]

        for name, each in zip(("comments", "standards"), printed):
            scratch = self.lane_scratch(self.lane_named(lanes, name))
            self.assertTrue(Path(scratch, "t3-stage.json").is_file())
            self.assertIn(scratch, each["wait"])
            self.assertIn(scratch, each["report"])
        self.assertEqual(2, len({each["clientRequestId"] for each in self.launches()}))

    def test_refuses_a_lane_that_names_no_scratch_folder_of_its_own_and_launches_nothing(self):
        _, _, lanes = self.lanes_at_the_review()
        lane = self.lane_named(lanes, "comments")
        prompt = Path(lane["scratch"]) / "prompt.md"
        prompt.write_text("Review.\n", encoding="utf-8")

        done = self.stage_call("start", lane, "--prompt", str(prompt), "--tier", "standard")

        self.assertEqual(1, done.returncode)
        self.assertIn("scratch folder of its own", done.stderr)
        self.assertEqual([], self.calls())
        self.assertIsNone(self.guard_of(lane))


class TheSpecLaneStaysOnCodexTests(ReviewStageCase):
    def test_codex_runs_the_spec_lane_read_only_in_the_review_worktree_on_an_antigravity_host(self):
        epic, _, lanes = self.lanes_at_the_review()
        spec = self.lane_named(lanes, "spec")

        done = self.run_script(CODEX_LANE, epic, "--worktree", spec["worktree"], "--report", spec["report"],
                               "--base", spec["base"], "--head", spec["head"],
                               *(part for each in spec["files"] for part in ("--file", each)), "--doc",
                               str(self.repo / "CLAUDE.md"), "--jidoka-home", str(self.home))

        self.assertEqual(0, done.returncode, done.stderr)
        argv = json.loads(self.codex_calls.read_text(encoding="utf-8"))["argv"]
        self.assertEqual(["exec", "--sandbox", "read-only"], argv[:3])
        self.assertEqual(spec["worktree"], argv[argv.index("--cd") + 1])
        self.assertEqual("gpt-5.5", argv[argv.index("--model") + 1])
        self.assertEqual([], self.calls())


class EndingTheReviewLanesTests(ReviewStageCase):
    def test_each_lane_is_archived_when_it_is_reported_and_the_guard_record_goes_with_the_last(self):
        _, _, lanes = self.lanes_at_the_review()
        names = ("comments", "standards", "design")
        tiers = ("standard", "standard", "deep")
        for name, tier in zip(names, tiers):
            self.start_lane(self.lane_named(lanes, name), tier)

        self.lane_call("report", self.lane_named(lanes, "comments"))
        held_between = self.guard_of(lanes[0])
        self.lane_call("report", self.lane_named(lanes, "standards"))
        self.lane_call("report", self.lane_named(lanes, "design"))

        archives = [call["arguments"] for call in self.calls() if call["tool"] == "t3_thread_organize"]
        self.assertEqual([{"threadId": LANE_THREAD, "action": "archive"}] * 3, archives)
        self.assertIsNotNone(held_between)
        self.assertIsNone(self.guard_of(lanes[0]))

    def test_the_lanes_reports_settle_the_review_as_they_do_on_claude_code(self):
        epic, printed, lanes = self.lanes_at_the_review()
        self.start_lane(self.lane_named(lanes, "comments"), "standard")
        reported = self.lane_call("report", self.lane_named(lanes, "comments"))

        moved = self.reviewed(printed, FINDINGS)

        self.assertEqual(0, reported.returncode, reported.stderr)
        self.assertEqual(["Echo"], [each["title"] for each in self.fix_action_of(moved)["findings"]])


class TheFixWorkerTests(ReviewStageCase):
    def test_the_fix_worker_launches_one_thread_in_the_fix_worktree_on_the_standard_tiers_route(self):
        epic, action = self.epic_at_the_fix()
        self.answer({"t3_thread_launch": {"threadId": FIX_THREAD}, **REPLY})

        done = self.start_fix(action)

        self.assertEqual(0, done.returncode, done.stderr)
        [arguments] = self.launches()
        self.assertEqual({"type": "existing_worktree", "worktreePath": action["worktree"]},
                         arguments["workspaceStrategy"])
        self.assertEqual({"instanceId": "antigravity-main", "model": "gemini-4-helium",
                          "options": {"thought_level": "low"}}, arguments["modelSelection"])
        self.assertEqual(f"lap · {self.shown(epic)['title']} · fix", arguments["title"])
        self.assertEqual(FIX_THREAD, json.loads(done.stdout)["thread"])

    def test_what_the_fix_worker_left_is_committed_by_the_schedulers_report_of_the_fix(self):
        epic, action = self.epic_at_the_fix()
        self.start_fix(action)
        self.leave_in(Path(action["worktree"]), test_review.BUILT_FILE, "total = 2\n")
        self.stage_call("report", action)

        done = self.report_fix(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(test_review.FIX_SUBJECT, self.epic_log(epic)[0])


if __name__ == "__main__":
    unittest.main()
