import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import launcher  # noqa: E402
import test_scheduler  # noqa: E402
import test_validation  # noqa: E402
from test_factory_pass_stage import FACTORY, LAP_LISTS, REPLY, STARTED, PassStageCase  # noqa: E402
from test_factory_review_stage import HELIUM  # noqa: E402
from test_factory_t3_stage import MANAGER_THREAD, NEON  # noqa: E402

VALIDATION_THREAD = "thread-of-the-validation"
WALL_CLOCK_SECONDS = 30 * 60
GREEN = [{"holdout": 1, "verdict": "pass", "saw": ""}]


class ValidationStageCase(PassStageCase, test_validation.ValidationHoldoutsCase):
    """An epic at its validation, the factory script run as a process in a T3 thread that exports no jidoka session,
    and T3 faked behind a fake `acp-mcp-call`."""

    def setUp(self):
        super().setUp()
        self.answer({"t3_thread_launch": {"threadId": VALIDATION_THREAD}, **REPLY})
        self.use_routes({"standard": HELIUM, "deep": NEON})

    def start(self, action: dict, tier: str, thread: str | None = MANAGER_THREAD):
        prompt = Path(action["scratch"]) / "prompt.md"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text("Do the stage.\n", encoding="utf-8")
        return self.stage_call("start", action, "--prompt", str(prompt), "--tier", tier, thread=thread)

    def epic_at_the_holdouts(self) -> tuple[str, dict]:
        epic, _, printed = self.finish_epic_with_holdouts([test_validation.SCENARIO])
        return epic, self.holdouts_action_of(printed)

    def epic_at_the_merge(self) -> tuple[str, dict]:
        epic, _, printed = self.conflicting_epic()
        [action] = [each for each in printed["actions"] if each["action"] == "merge"]
        return epic, action

    def check_list_in(self, worktree: str) -> list:
        listed = self.run_script(LAP_LISTS, "check", cwd=Path(worktree), thread=None, now=None)
        self.assertEqual(0, listed.returncode, listed.stderr)
        return json.loads(listed.stdout)


class StartingTheValidationWorkerTests(ValidationStageCase):
    def test_launches_one_thread_in_the_validation_worktree_on_the_standard_tiers_route(self):
        _, action = self.epic_at_the_holdouts()

        printed = self.started(action, "standard")

        (launch,) = self.launches()
        self.assertEqual({"type": "existing_worktree", "worktreePath": action["worktree"]},
                         launch["workspaceStrategy"])
        self.assertEqual({"instanceId": "antigravity-main", "model": "gemini-4-helium",
                          "options": {"thought_level": "low"}}, launch["modelSelection"])
        self.assertEqual("full-access", launch["runtimeMode"])
        self.assertEqual(VALIDATION_THREAD, printed["thread"])
        self.assertEqual((WALL_CLOCK_SECONDS, STARTED + WALL_CLOCK_SECONDS),
                         (printed["wall_seconds"], printed["deadline"]))

    def test_titles_the_thread_lap_the_epics_title_and_holdouts_without_the_bead_id(self):
        epic, action = self.epic_at_the_holdouts()

        self.started(action, "standard")

        title = self.launches()[0]["title"]
        self.assertEqual(f"lap · {self.shown(epic)['title']} · holdouts", title)
        self.assertNotIn(epic, title)

    def test_the_thread_opens_with_the_validation_agents_instructions_and_then_the_prompt(self):
        _, action = self.epic_at_the_holdouts()

        self.started(action, "standard")

        message = self.launches()[0]["message"]
        self.assertTrue(message.startswith("# Validation worker"), message[:80])
        self.assertIn("app_process.py start <app>", message)
        self.assertNotIn("name: validation", message)
        self.assertTrue(message.endswith("\n\n---\n\nDo the stage.\n"))

    def test_writes_a_check_guard_record_before_the_launch_that_holds_the_check_list_and_bars_no_folder(self):
        _, action = self.epic_at_the_holdouts()

        self.started(action, "standard")

        self.assertEqual(1, len(self.calls()[0]["guards"]))
        held = self.guard_of(action)
        self.assertIsNotNone(held)
        self.assertEqual(("check", "holdouts", []), (held.kind, held.stage, held.barred))
        self.assertEqual([*self.check_list_in(action["worktree"]), launcher.command_for("holdouts.py"),
                          launcher.command_for("app_process.py")], held.commands)
        self.assertIn("make", held.commands)

    def test_an_epic_that_owes_neither_the_holdouts_nor_a_merge_is_refused_and_launches_nothing(self):
        epic, action = self.epic_at_the_holdouts()
        self.bd_here("update", epic, "--unset-metadata", "validation.holdouts")

        done = self.start(action, "standard")

        self.assertEqual(1, done.returncode)
        self.assertIn("neither a merge worker nor a run of its holdouts", done.stderr)
        self.assertEqual([], self.calls())
        self.assertIsNone(self.guard_of(action))

    def test_the_report_archives_the_thread_removes_the_guard_record_and_writes_no_ledger_row(self):
        epic, action = self.epic_at_the_holdouts()
        self.started(action, "standard")

        done = self.stage_call("report", action)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({"thread": VALIDATION_THREAD, "cut_off": False,
                          "reply": 'Done.\n```json\n{"outcome": "done"}\n```'}, json.loads(done.stdout))
        self.assertEqual({"threadId": VALIDATION_THREAD, "action": "archive"}, self.calls()[-1]["arguments"])
        self.assertIsNone(self.guard_of(action))
        self.assertEqual([], self.rows_of_the_thread(epic))


class StartingTheValidationMergeWorkerTests(ValidationStageCase):
    def test_titles_the_thread_lap_the_epics_title_and_validation_merge_and_opens_with_the_prompt_alone(self):
        epic, action = self.epic_at_the_merge()

        self.started(action, "deep")

        (launch,) = self.launches()
        self.assertEqual(f"lap · {self.shown(epic)['title']} · validation-merge", launch["title"])
        self.assertEqual({"type": "existing_worktree", "worktreePath": action["worktree"]},
                         launch["workspaceStrategy"])
        self.assertEqual("gemini-4-neon", launch["modelSelection"]["model"])
        self.assertEqual("Do the stage.\n", launch["message"])

    def test_the_guard_record_holds_the_grants_of_merging_main_and_bars_no_folder(self):
        _, action = self.epic_at_the_merge()

        self.started(action, "deep")

        self.assertEqual(1, len(self.calls()[0]["guards"]))
        held = self.guard_of(action)
        self.assertIsNotNone(held)
        self.assertEqual(("lap", "validation-merge", []), (held.kind, held.stage, held.barred))
        self.assertEqual(self.lap_list_in(action["worktree"]), held.commands)
        for whole in ("git merge main", "git merge --abort", "git -c core.editor=true merge --continue"):
            self.assertIn({"command": whole, "then": "nothing"}, held.commands)
        self.assertIn({"command": "git add", "then": "paths"}, held.commands)
        self.assertIn({"command": "git diff", "then": "words", "refusing": ["--output"]}, held.commands)

    def test_the_guard_record_holds_no_rebase_grant_because_the_worker_merges_and_rebases_nothing(self):
        _, action = self.epic_at_the_merge()

        self.started(action, "deep")

        wholes = [entry["command"] for entry in self.guard_of(action).commands if isinstance(entry, dict)]
        self.assertEqual([], [command for command in wholes if command.startswith("git rebase")])


class AnEpicHostedInAntigravityTests(ValidationStageCase):
    def report_to_the_scheduler(self, mode: str, epic: str, *more: str):
        return self.run_script(test_scheduler.SCHEDULER, mode, epic, *more, "--worker", VALIDATION_THREAD, "standard",
                               "--jidoka-home", str(self.home), thread=None, now=None)

    def two_tasks_built_with_a_holdout(self) -> tuple[str, dict]:
        epic = self.new_epic()
        first = self.new_task_under(epic)
        second = self.new_task_under(epic)
        self.hand_off(epic, {first: "till", second: "reader"})
        laps = {each["task"]: each for each in self.next_printed(epic)["actions"]}
        for number, task in enumerate((first, second)):
            self.leave_in(Path(laps[task]["worktree"]), f"card{number}.txt", "built\n")
        written = fixture.run_launcher(
            test_scheduler.LAUNCHER, [str(test_validation.HOLDOUTS), "write", epic],
            json.dumps([{"app": "shop", "tasks": [first, second], "scenario": test_validation.SCENARIO}]),
            self.caller_env(self.home), self.repo, None)
        self.assertEqual(0, written.returncode, written.stderr)
        self.build_done(epic, first)
        return epic, self.holdouts_action_of(self.build_done(epic, second))

    def test_reaches_the_acceptance_gate_with_the_validation_worker_a_thread_and_no_claude_code_session(self):
        epic, action = self.two_tasks_built_with_a_holdout()
        self.started(action, "standard")
        self.assertEqual(0, self.stage_call("wait", action).returncode)
        reported = self.stage_call("report", action)
        self.assertEqual(0, reported.returncode, reported.stderr)
        Path(action["report"]).write_text(json.dumps(GREEN), encoding="utf-8")

        done = self.report_to_the_scheduler("report-holdouts", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        shown = self.shown(epic)
        self.assertEqual(("pass", []), (json.loads(done.stdout)["validation"]["result"],
                                        json.loads(done.stdout)["actions"]))
        self.assertIn("human", shown["labels"])
        self.assertEqual("waiting", shown["metadata"].get("gate.state"))
        self.assertEqual(["t3_thread_launch", "t3_thread_wait", "t3_thread_read", "t3_thread_organize"],
                         [call["tool"] for call in self.calls()])

    def test_the_merge_worker_a_thread_merged_main_and_validation_goes_on_to_the_gate(self):
        epic, action = self.epic_at_the_merge()
        self.started(action, "deep")
        self.reconcile(Path(action["worktree"]), "clash.txt")
        self.assertEqual(0, self.stage_call("report", action).returncode)

        done = self.report_to_the_scheduler("report-merge", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("pass", json.loads(done.stdout)["validation"]["result"])
        self.assertEqual("waiting", self.metadata(epic).get("gate.state"))


if __name__ == "__main__":
    unittest.main()
