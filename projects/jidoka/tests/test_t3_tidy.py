import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_ledger  # noqa: E402
import test_tidy  # noqa: E402
import test_validation  # noqa: E402
from test_scheduler import LAUNCHER, PLUGIN, RUN_TIMEOUT_SECONDS  # noqa: E402

T3_TIDY = PLUGIN / "scripts" / "t3_tidy.py"
T3_OPENCODE = {"harness": "t3", "driver": "opencode", "provider": "strata", "model": "qwen3-coder-next",
               "version": None, "effort": "medium"}
STARTED_AT = 1_800_000_000
FINISHED_AT = STARTED_AT + 95
DONE_REPLY = "I removed the comment.\n{\"outcome\": \"done\"}"


def settings_with_local_tier(local: dict) -> str:
    return json.dumps({"routes": {**test_ledger.ROUTES["routes"], "local": local}})


class T3TidyCase(test_ledger.LedgerBooks, test_tidy.TidyCase):
    """The tidy, with the local tier routed to t3 OpenCode and a child's reply given as a file."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.home / "settings.json").write_text(settings_with_local_tier(T3_OPENCODE), encoding="utf-8")

    def tidy_at(self, now: int, mode: str, *args: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(T3_TIDY), mode, *args], None,
                                    {**self.caller_env(self.home), "JIDOKA_NOW": str(now)}, self.repo,
                                    RUN_TIMEOUT_SECONDS)

    def start_batch(self, action: dict, *extra: str) -> subprocess.CompletedProcess:
        """Starts the batch from its action, saved in the batch's scratch folder as the manager saves it."""
        saved = Path(action["scratch"]) / "action.json"
        saved.write_text(json.dumps(action), encoding="utf-8")
        return self.tidy_at(STARTED_AT, "start", "--action", str(saved), "--doc", str(self.repo / "CLAUDE.md"),
                            *extra)

    def started(self, action: dict, *extra: str) -> dict:
        done = self.start_batch(action, *extra)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def finish_batch(self, action: dict, started: dict | None, reply: str | None,
                     *extra: str) -> subprocess.CompletedProcess:
        """Finishes the batch after saving the reply where `start` said to; a batch that never started has no path."""
        if started is not None:
            reply_file = Path(started["reply"])
            reply_file.unlink(missing_ok=True)
            if reply is not None:
                reply_file.write_text(reply, encoding="utf-8")
        return self.tidy_at(FINISHED_AT, "finish", "--scratch", action["scratch"], *extra)

    def local_tier(self, local: dict) -> None:
        (self.home / "settings.json").write_text(settings_with_local_tier(local), encoding="utf-8")

    def result_of(self, action: dict) -> dict:
        return json.loads((Path(action["scratch"]) / "t3-tidy-result.json").read_text(encoding="utf-8"))

    def tidy_rows_of(self, epic: str) -> list[dict]:
        return [row for row in self.passes_of(epic) if row["stage"] == "tidy"]


class AT3TidyBatchStartsAsAnOpenCodeChildTaskTests(T3TidyCase):
    def test_the_task_holds_the_batchs_diff_and_names_its_files_by_absolute_path_because_the_child_has_no_shell(self):
        _, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        action = self.tidy_action_of(printed)

        task = self.started(action)["delegate_task"]["task"]

        self.assertIn(f"{action['worktree']}/{test_tidy.BUILT_FILE}", task)
        self.assertIn("+" + test_tidy.COMMENTED.strip(), task)
        self.assertIn("Run no shell command", task)
        self.assertIn("edit tool", task)
        self.assertIn(f"{action['scratch']}/discovered.json", task)
        self.assertIn("Unattended", task)

    def test_the_task_holds_only_the_diff_of_its_own_batch(self):
        _, printed = self.finish_epic_whose_task_built({f"till_{number}.txt": f"total = {number}  # one\n"
                                                        for number in range(1, 6)})
        first, second = self.tidy_actions_of(printed)

        task = self.started(first)["delegate_task"]["task"]

        for name in first["files"]:
            self.assertIn(f"+++ b/{name}", task)
        for name in second["files"]:
            self.assertNotIn(f"+++ b/{name}", task)

    def test_start_prints_the_delegate_task_arguments_whole_with_the_routes_effort_as_variant_and_no_agent(self):
        _, _, printed = self.finish_epic_whose_task_built_a_commented_file()

        delegate = self.started(self.tidy_action_of(printed), "--wall-seconds", "1800")["delegate_task"]

        self.assertTrue(delegate.pop("task"))
        self.assertEqual({"role": "implementation", "isolation": "shared", "mode": "wait", "timeoutMs": 1_800_000,
                          "runtimeMode": "auto-accept-edits",
                          "target": {"providerInstanceId": "strata", "driverKind": "opencode",
                                     "model": "qwen3-coder-next", "options": {"variant": "medium"}}}, delegate)

    def test_start_prints_the_deadline_from_the_stages_wall_clock(self):
        _, _, printed = self.finish_epic_whose_task_built_a_commented_file()

        started = self.started(self.tidy_action_of(printed), "--wall-seconds", "600")

        self.assertEqual((600, STARTED_AT + 600), (started["wall_seconds"], started["deadline"]))

    def test_a_local_tier_that_does_not_route_to_t3_opencode_refuses_to_start(self):
        _, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        action = self.tidy_action_of(printed)
        for local in ({**T3_OPENCODE, "driver": None}, test_ledger.ROUTES["routes"]["standard"]):
            self.local_tier(local)
            try:
                done = self.start_batch(action)
            finally:
                self.local_tier(T3_OPENCODE)

            self.assertEqual(1, done.returncode)
            self.assertIn("not a t3 opencode route", done.stderr)

    def test_a_t3_opencode_route_without_an_effort_refuses_to_start(self):
        _, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        self.local_tier({**T3_OPENCODE, "effort": None})
        try:
            done = self.start_batch(self.tidy_action_of(printed))
        finally:
            self.local_tier(T3_OPENCODE)

        self.assertEqual(1, done.returncode)
        self.assertIn("effort", done.stderr)

    def test_an_action_file_that_is_not_json_refuses_to_start(self):
        saved = self.home / "action.json"
        saved.write_text("not json", encoding="utf-8")

        done = self.tidy_at(STARTED_AT, "start", "--action", str(saved))

        self.assertEqual(1, done.returncode)
        self.assertIn("not read as JSON", done.stderr)

    def test_an_action_without_files_refuses_to_start(self):
        _, _, printed = self.finish_epic_whose_task_built_a_commented_file()

        done = self.start_batch({**self.tidy_action_of(printed), "files": []})

        self.assertEqual(1, done.returncode)
        self.assertIn("files", done.stderr)


class AFinishedBatchLeavesItsEditsForTheTidysSettleTests(T3TidyCase):
    def test_the_childs_edits_land_in_the_commit_no_comments_and_unslop_and_the_row_names_t3(self):
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        action = self.tidy_action_of(printed)
        branch = self.metadata(epic)["factory.branch"]
        started = self.started(action)
        self.tidy_by_hand(action, test_tidy.CLEAN)

        done = self.finish_batch(action, started, DONE_REPLY)
        settled = self.report_tidy(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(0, settled.returncode, settled.stderr)
        self.assertEqual(test_tidy.TIDY_SUBJECT, self.epic_log(epic)[0])
        self.assertEqual(test_tidy.CLEAN.strip(),
                         test_validation.git(self.repo, "show", f"{branch}:{test_tidy.BUILT_FILE}"))

    def test_each_batch_writes_one_ledger_row_with_harness_t3_the_wall_time_and_no_tokens(self):
        epic, printed = self.finish_epic_whose_task_built({f"till_{number}.txt": test_tidy.COMMENTED
                                                           for number in range(1, 6)})
        actions = self.tidy_actions_of(printed)
        for action in actions:
            self.finish_batch(action, self.started(action), DONE_REPLY)

        rows = self.tidy_rows_of(epic)

        keys = ("stage", "tier", "harness", "model", "effort", "agent", "outcome", "task", "wall_seconds",
                "input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens")
        self.assertEqual([{"stage": "tidy", "tier": "local", "harness": "t3", "model": "qwen3-coder-next",
                           "effort": "medium", "agent": None, "outcome": "done", "task": None, "wall_seconds": 95,
                           "input_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0,
                           "output_tokens": 0}] * len(actions),
                         [{key: row[key] for key in keys} for row in rows])

    def test_a_finished_batch_leaves_a_result_that_names_its_outcome(self):
        _, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        action = self.tidy_action_of(printed)
        self.finish_batch(action, self.started(action), DONE_REPLY)

        self.assertEqual({"outcome": "done"}, self.result_of(action))

    def test_a_settings_change_between_start_and_finish_does_not_change_the_route_the_row_names(self):
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        action = self.tidy_action_of(printed)
        started = self.started(action)
        self.local_tier({**T3_OPENCODE, "model": "other-model", "effort": "low"})
        try:
            done = self.finish_batch(action, started, DONE_REPLY)
        finally:
            self.local_tier(T3_OPENCODE)

        self.assertEqual(0, done.returncode, done.stderr)
        [row] = self.tidy_rows_of(epic)
        self.assertEqual(("qwen3-coder-next", "medium"), (row["model"], row["effort"]))

    def test_a_reply_that_ends_in_a_fenced_outcome_is_accepted(self):
        _, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        action = self.tidy_action_of(printed)
        started = self.started(action)

        done = self.finish_batch(action, started, "Done.\n```json\n{\"outcome\": \"done\"}\n```\n")

        self.assertEqual(0, done.returncode, done.stderr)


class AFailedChildRunExitsOneRestoresItsFilesAndWritesAFailedRowTests(T3TidyCase):
    def assert_failed(self, epic: str, action: dict, done: subprocess.CompletedProcess, reason: str,
                      outcome: str = "failed") -> None:
        self.assertEqual(1, done.returncode)
        self.assertIn(reason, done.stderr)
        [row] = self.tidy_rows_of(epic)
        self.assertEqual(("t3", outcome, 95), (row["harness"], row["outcome"], row["wall_seconds"]))
        self.assertEqual(test_tidy.COMMENTED, (Path(action["worktree"]) / test_tidy.BUILT_FILE).read_text(
            encoding="utf-8"))

    def failing_run(self, reply: str | None, start_extra: tuple[str, ...],
                    finish_extra: tuple[str, ...]) -> tuple[str, dict, subprocess.CompletedProcess]:
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        action = self.tidy_action_of(printed)
        started = self.started(action, *start_extra)
        self.tidy_by_hand(action, test_tidy.CLEAN)
        return epic, action, self.finish_batch(action, started, reply, *finish_extra)

    def test_a_child_that_ended_failed_fails_the_batch(self):
        epic, action, done = self.failing_run(
            "{\"outcome\": \"failed\", \"why\": \"the model lost the file\"}", (), ())

        self.assert_failed(epic, action, done, "the model lost the file")
        self.assertEqual({"outcome": "failed"}, self.result_of(action))

    def test_a_reply_that_does_not_end_with_an_outcome_fails_the_batch(self):
        epic, action, done = self.failing_run("I changed the file.", (), ())

        self.assert_failed(epic, action, done, "does not end with an outcome")

    def test_a_blank_reply_fails_the_batch(self):
        epic, action, done = self.failing_run("   ", (), ())

        self.assert_failed(epic, action, done, "no reply")

    def test_a_child_that_left_no_reply_file_fails_the_batch(self):
        epic, action, done = self.failing_run(None, (), ())

        self.assert_failed(epic, action, done, "no reply")

    def test_a_child_that_asked_for_an_approval_fails_the_batch_whatever_it_replied(self):
        epic, action, done = self.failing_run(DONE_REPLY, (), ("--asked-for-approval",))

        self.assert_failed(epic, action, done, "asked for an approval")
        self.assertEqual({"outcome": "failed"}, self.result_of(action))

    def test_a_child_that_asked_for_an_approval_and_left_no_reply_fails_the_batch_for_the_approval(self):
        epic, action, done = self.failing_run(None, (), ("--asked-for-approval",))

        self.assert_failed(epic, action, done, "asked for an approval")

    def test_a_run_past_the_stages_wall_clock_is_cut_off_even_with_a_good_reply(self):
        epic, action, done = self.failing_run(DONE_REPLY, ("--wall-seconds", "60"), ())

        self.assert_failed(epic, action, done, "wall clock of 60 seconds", "cut off")
        self.assertEqual({"outcome": "cut off"}, self.result_of(action))

    def test_a_main_checkout_that_changed_while_the_child_ran_fails_the_batch_even_with_a_good_reply(self):
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        action = self.tidy_action_of(printed)
        started = self.started(action)
        self.tidy_by_hand(action, test_tidy.CLEAN)
        (self.repo / "written-by-the-child.txt").write_text("oops\n", encoding="utf-8")
        try:
            done = self.finish_batch(action, started, DONE_REPLY)
        finally:
            (self.repo / "written-by-the-child.txt").unlink()

        self.assert_failed(epic, action, done, "changed while the child ran")

    def test_a_failed_batch_leaves_the_files_of_the_other_batches_as_their_children_left_them(self):
        _, printed = self.finish_epic_whose_task_built({f"till_{number}.txt": test_tidy.COMMENTED
                                                        for number in range(1, 6)})
        first, second = self.tidy_actions_of(printed)
        started = self.started(first)
        for name in first["files"]:
            self.leave_in(Path(first["worktree"]), name, test_tidy.CLEAN)
        for name in second["files"]:
            self.leave_in(Path(second["worktree"]), name, test_tidy.CLEAN)

        done = self.finish_batch(first, started, "no outcome")

        self.assertEqual(1, done.returncode)
        for name in first["files"]:
            self.assertEqual(test_tidy.COMMENTED, (Path(first["worktree"]) / name).read_text(encoding="utf-8"))
        for name in second["files"]:
            self.assertEqual(test_tidy.CLEAN, (Path(second["worktree"]) / name).read_text(encoding="utf-8"))

    def test_a_restore_that_cannot_run_still_writes_the_row_and_the_result_and_reports_the_first_failure(self):
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        action = self.tidy_action_of(printed)
        started = self.started(action)
        state_file = Path(action["scratch"]) / "t3-tidy-start.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state_file.write_text(json.dumps({**state, "head": "0" * 40}), encoding="utf-8")

        done = self.finish_batch(action, started, "{\"outcome\": \"failed\", \"why\": \"lost the file\"}")

        self.assertEqual(1, done.returncode)
        self.assertIn("lost the file", done.stderr)
        self.assertIn("not put back", done.stderr)
        [row] = self.tidy_rows_of(epic)
        self.assertEqual("failed", row["outcome"])
        self.assertEqual({"outcome": "failed"}, self.result_of(action))

    def test_a_batch_that_never_started_fails_without_a_row(self):
        epic, _, printed = self.finish_epic_whose_task_built_a_commented_file()
        action = self.tidy_action_of(printed)

        done = self.finish_batch(action, None, None)

        self.assertEqual(1, done.returncode)
        self.assertIn("never started", done.stderr)
        self.assertEqual([], self.tidy_rows_of(epic))


if __name__ == "__main__":
    unittest.main()
