import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import t3_state  # noqa: E402
import test_scheduler  # noqa: E402
from test_cleanup import TEST_FILE, TWO_TESTS, CleanupCase  # noqa: E402
from test_factory_t3_stage import AMBIENT, FAKE_ACP_MCP_CALL, MANAGER_THREAD, NEON  # noqa: E402

PLUGIN = test_scheduler.PLUGIN
sys.path.insert(0, str(PLUGIN / "scripts"))
import lap_guard_record  # noqa: E402

FACTORY = PLUGIN / "scripts" / "factory.py"
LAP_LISTS = PLUGIN / "scripts" / "lap_lists.py"
LEDGER = PLUGIN / "scripts" / "ledger.py"
STARTED = 1_800_000_000
PASS_WALL_CLOCK_SECONDS = 30 * 60
CLEANUP_THREAD = "thread-of-the-cleanup"
HYDROGEN = {"harness": "t3", "model": "gemini-4-hydrogen", "version": None, "effort": "medium",
            "provider": "antigravity-main", "driver": "antigravity"}
OPENCODE = {"harness": "t3", "model": "qwen3-coder-next", "version": None, "effort": "medium",
            "provider": "strata", "driver": "opencode"}
SHELF_FILES = 5
REPLY = {"t3_thread_read": {"items": [{"position": 3, "type": "assistant_message",
                                       "text": 'Done.\n```json\n{"outcome": "done"}\n```'}]}}


class PassStageCase(CleanupCase):
    """An epic whose tasks have landed, so that its pass owes the test cleanup and then the tidy, the factory script run
    as a process in a T3 thread that exports no jidoka session, and T3 faked behind a fake `acp-mcp-call`."""

    def setUp(self):
        self.t3 = self.root / "t3"
        shutil.rmtree(self.t3, ignore_errors=True)
        self.t3.mkdir()
        self.t3_db = self.root / "statev2.sqlite"
        self.t3_db.unlink(missing_ok=True)
        t3_state.create(self.t3_db, t3_state.TOKEN_TABLES)
        self.acp = fixture.write_executable(self.t3 / "acp-node", FAKE_ACP_MCP_CALL)
        self.answer({"t3_thread_launch": {"threadId": CLEANUP_THREAD}, **REPLY})
        self.use_routes({"deep": NEON, "local": HYDROGEN})

    def tearDown(self):
        (self.home / "settings.json").unlink(missing_ok=True)
        shutil.rmtree(self.home / lap_guard_record.FOLDER, ignore_errors=True)
        super().tearDown()

    def use_routes(self, table: dict) -> None:
        (self.home / "settings.json").write_text(json.dumps({"antigravity_routes": table}), encoding="utf-8")

    def answer(self, answers: dict) -> None:
        (self.t3 / "answers.json").write_text(json.dumps(answers), encoding="utf-8")

    def calls(self) -> list[dict]:
        path = self.t3 / "calls.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def launches(self) -> list[dict]:
        return [call["arguments"] for call in self.calls() if call["tool"] == "t3_thread_launch"]

    def environment(self, thread: str | None, now: int | None) -> dict[str, str]:
        environment = {key: value for key, value in self.caller_env(self.home).items() if key not in AMBIENT}
        environment.update({"JIDOKA_T3_STATE_DB": str(self.t3_db), "T3_ACP_MCP_NODE": str(self.acp),
                            "FAKE_T3_FOLDER": str(self.t3), "FAKE_T3_GUARDS": str(self.home / lap_guard_record.FOLDER),
                            "BEADS_ACTOR": "Pat Human"})
        environment.pop("JIDOKA_SESSION_ID", None)
        if thread is not None:
            environment["T3CODE_THREAD_ID"] = thread
        if now is not None:
            environment["JIDOKA_NOW"] = str(now)
        return environment

    def run_script(self, script: Path, *args: str, thread: str | None = MANAGER_THREAD, now: int | None = STARTED,
                   cwd: Path | None = None) -> subprocess.CompletedProcess:
        return fixture.run_launcher(test_scheduler.LAUNCHER, [str(script), *args], None,
                                    self.environment(thread, now), cwd or self.repo, test_scheduler.RUN_TIMEOUT_SECONDS)

    def stage_call(self, mode: str, action: dict, *more: str, thread: str | None = MANAGER_THREAD,
                   now: int | None = STARTED) -> subprocess.CompletedProcess:
        return self.run_script(FACTORY, mode, "--worktree", action["worktree"], "--scratch", action["scratch"], *more,
                               "--jidoka-home", str(self.home), thread=thread, now=now)

    def start(self, action: dict, tier: str, thread: str | None = MANAGER_THREAD) -> subprocess.CompletedProcess:
        prompt = Path(action["scratch"]) / "prompt.md"
        prompt.write_text(f"jidoka lap worktree: {action['worktree']}\n\nDo the stage.\n", encoding="utf-8")
        return self.stage_call("start", action, "--prompt", str(prompt), "--tier", tier, thread=thread)

    def start_natively(self, action: dict, tier: str) -> subprocess.CompletedProcess:
        prompt = Path(action["scratch"]) / "prompt.md"
        prompt.write_text(f"jidoka lap worktree: {action['worktree']}\n\nDo the stage.\n", encoding="utf-8")
        return self.stage_call("start", action, "--prompt", str(prompt), "--tier", tier, "--native")

    def started(self, action: dict, tier: str) -> dict:
        done = self.start(action, tier)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def guard_of(self, action: dict) -> lap_guard_record.GuardRecord | None:
        return lap_guard_record.read_record(self.home, Path(action["worktree"]))

    def epic_at_cleanup(self) -> tuple[str, dict]:
        epic, _, printed = self.finish_epic_whose_task_added_tests()
        return epic, self.cleanup_action_of(printed)

    def epic_at_tidy(self, shelf_files: int) -> tuple[str, list[dict]]:
        """An epic whose test cleanup is done and whose tidy owes a batch for every four of its files."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [lap] = self.next_printed(epic)["actions"]
        for number in range(shelf_files):
            self.leave_in(Path(lap["worktree"]), f"shelf{number}.txt", "stocked\n")
        self.leave_in(Path(lap["worktree"]), TEST_FILE, TWO_TESTS)
        cleanup = self.cleanup_action_of(self.build_done(epic, task))
        Path(cleanup["report"]).write_text("[]", encoding="utf-8")
        done = self.report_cleanup(epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return epic, [action for action in json.loads(done.stdout)["actions"] if action["action"] == "tidy"]

    def rows_of_the_thread(self, epic: str) -> list[dict]:
        rows = json.loads(self.run_script(LEDGER, "list", epic).stdout)["rows"]
        return [row for row in rows if row["agent"] == CLEANUP_THREAD]

    def lap_list_in(self, worktree: str) -> list:
        listed = self.run_script(LAP_LISTS, "lap", cwd=Path(worktree), thread=None, now=None)
        self.assertEqual(0, listed.returncode, listed.stderr)
        return json.loads(listed.stdout)


class StartingTheTestCleanupTests(PassStageCase):
    def test_launches_one_thread_in_the_pass_worktree_on_the_deep_tiers_route(self):
        _, action = self.epic_at_cleanup()

        printed = self.started(action, "deep")

        (launch,) = self.calls()
        arguments = launch["arguments"]
        self.assertEqual("t3_thread_launch", launch["tool"])
        self.assertEqual({"type": "existing_worktree", "worktreePath": action["worktree"]},
                         arguments["workspaceStrategy"])
        self.assertEqual({"instanceId": "antigravity-main", "model": "gemini-4-neon",
                          "options": {"thought_level": "high"}}, arguments["modelSelection"])
        self.assertEqual("full-access", arguments["runtimeMode"])
        self.assertEqual(Path(action["scratch"], "prompt.md").read_text(encoding="utf-8"), arguments["message"])
        self.assertEqual(CLEANUP_THREAD, printed["thread"])

    def test_titles_the_thread_lap_the_epics_title_and_the_stage_without_the_bead_id(self):
        epic, action = self.epic_at_cleanup()

        self.started(action, "deep")

        title = self.calls()[0]["arguments"]["title"]
        self.assertEqual(f"lap · {self.shown(epic)['title']} · test-cleanup", title)
        self.assertNotIn(epic, title)

    def test_writes_a_lap_guard_record_before_the_launch_with_the_list_the_lap_mod_gives_a_pass_worktree(self):
        _, action = self.epic_at_cleanup()

        self.started(action, "deep")

        self.assertEqual(1, len(self.calls()[0]["guards"]))
        held = self.guard_of(action)
        self.assertIsNotNone(held)
        self.assertEqual(("lap", "test-cleanup", []), (held.kind, held.stage, held.barred))
        self.assertEqual(self.lap_list_in(action["worktree"]), held.commands)

    def test_the_guard_records_list_holds_the_epics_looks_and_no_merge_grant(self):
        _, action = self.epic_at_cleanup()

        self.started(action, "deep")

        commands = self.guard_of(action).commands
        self.assertIn({"command": "git diff", "then": "words", "refusing": ["--output"]}, commands)
        self.assertEqual([], [entry for entry in commands if isinstance(entry, dict)
                              and entry["command"] in ("git merge main", "git add")])

    def test_prints_the_calls_that_wait_for_and_report_the_stage_with_its_scratch_folder(self):
        _, action = self.epic_at_cleanup()

        printed = self.started(action, "deep")

        for name in ("wait", "report"):
            self.assertIn(f"factory.py {name} --worktree", printed[name].replace('"', "").replace("'", ""))
            self.assertIn(action["worktree"], printed[name])
        self.assertEqual(PASS_WALL_CLOCK_SECONDS, printed["wall_seconds"])
        self.assertEqual(STARTED + PASS_WALL_CLOCK_SECONDS, printed["deadline"])

    def test_a_start_that_is_repeated_before_its_report_keeps_the_request_id_and_one_after_it_names_a_new_one(self):
        _, action = self.epic_at_cleanup()

        self.started(action, "deep")
        self.started(action, "deep")
        self.stage_call("report", action)
        self.started(action, "deep")

        first, again, after = (call["arguments"]["clientRequestId"]
                               for call in self.calls() if call["tool"] == "t3_thread_launch")
        self.assertEqual(first, again)
        self.assertNotEqual(first, after)

    def test_refuses_a_scratch_folder_that_is_outside_the_worktree(self):
        _, action = self.epic_at_cleanup()
        prompt = Path(action["scratch"]) / "prompt.md"
        prompt.write_text("Do the stage.\n", encoding="utf-8")

        done = self.run_script(FACTORY, "start", "--worktree", action["worktree"], "--scratch", str(self.root),
                               "--prompt", str(prompt), "--tier", "deep", "--jidoka-home", str(self.home))

        self.assertEqual(1, done.returncode)
        self.assertIn("scratch folder", done.stderr)
        self.assertEqual([], self.calls())
        self.assertIsNone(self.guard_of(action))


class EndingTheTestCleanupTests(PassStageCase):
    def test_the_report_reads_the_last_reply_archives_the_thread_and_removes_the_guard_record(self):
        _, action = self.epic_at_cleanup()
        self.started(action, "deep")

        done = self.stage_call("report", action)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({"thread": CLEANUP_THREAD, "cut_off": False,
                          "reply": 'Done.\n```json\n{"outcome": "done"}\n```'}, json.loads(done.stdout))
        read, organize = self.calls()[-2:]
        self.assertEqual(("t3_thread_read", "t3_thread_organize"), (read["tool"], organize["tool"]))
        self.assertEqual({"threadId": CLEANUP_THREAD, "action": "archive"}, organize["arguments"])
        self.assertIsNone(self.guard_of(action))

    def test_the_report_writes_no_ledger_row_because_the_schedulers_report_of_the_worker_prices_its_thread(self):
        epic, action = self.epic_at_cleanup()
        self.started(action, "deep")
        t3_state.add_next_run(self.t3_db, "run-1", CLEANUP_THREAD, "gemini-4-neon", "completed", "completed")
        t3_state.add_next_turn(self.t3_db, CLEANUP_THREAD, "run-1", t3_state.usage(1_000_000, 0, 0, 100_000, 0))

        done = self.stage_call("report", action)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], self.rows_of_the_thread(epic))


class StartingTheTidyBatchesTests(PassStageCase):
    def test_each_batch_launches_one_thread_in_the_pass_worktree_on_the_local_tiers_antigravity_route(self):
        _, batches = self.epic_at_tidy(SHELF_FILES)
        self.assertEqual(2, len(batches))

        for action in batches:
            self.started(action, "local")

        launches = [call["arguments"] for call in self.calls()]
        self.assertEqual(2, len(launches))
        for arguments in launches:
            self.assertEqual({"type": "existing_worktree", "worktreePath": batches[0]["worktree"]},
                             arguments["workspaceStrategy"])
            self.assertEqual({"instanceId": "antigravity-main", "model": "gemini-4-hydrogen",
                              "options": {"thought_level": "medium"}}, arguments["modelSelection"])

    def test_a_batch_whose_local_route_is_t3_opencode_reruns_as_a_thread_on_the_native_antigravity_route(self):
        self.use_routes({"deep": NEON, "light": HYDROGEN, "local": OPENCODE})
        _, batches = self.epic_at_tidy(SHELF_FILES)
        refused = self.start(batches[0], "local")

        started = self.start_natively(batches[0], "local")

        self.assertEqual(1, refused.returncode)
        self.assertIn("not a T3 Antigravity thread", refused.stderr)
        self.assertEqual(0, started.returncode, started.stderr)
        [launch] = self.launches()
        self.assertEqual({"instanceId": "antigravity-main", "model": "gemini-4-hydrogen",
                          "options": {"thought_level": "medium"}}, launch["modelSelection"])
        self.assertEqual({"type": "existing_worktree", "worktreePath": batches[0]["worktree"]},
                         launch["workspaceStrategy"])

    def test_a_native_start_with_no_antigravity_thread_to_rerun_on_refuses_and_launches_nothing(self):
        self.use_routes({"deep": NEON, "local": OPENCODE})
        _, batches = self.epic_at_tidy(SHELF_FILES)

        done = self.start_natively(batches[0], "local")

        self.assertEqual(1, done.returncode)
        self.assertIn("light", done.stderr)
        self.assertEqual([], self.calls())
        self.assertIsNone(self.guard_of(batches[0]))

    def test_writes_the_lap_guard_record_of_the_pass_worktree_with_the_stage_tidy(self):
        _, batches = self.epic_at_tidy(SHELF_FILES)

        self.started(batches[0], "local")

        held = self.guard_of(batches[0])
        self.assertIsNotNone(held)
        self.assertEqual(("lap", "tidy", []), (held.kind, held.stage, held.barred))
        self.assertEqual(self.lap_list_in(batches[0]["worktree"]), held.commands)

    def test_each_batch_keeps_its_own_state_in_its_own_scratch_folder_and_names_it_in_the_calls_it_prints(self):
        _, batches = self.epic_at_tidy(SHELF_FILES)

        printed = [self.started(action, "local") for action in batches]

        for action, each in zip(batches, printed):
            self.assertTrue(Path(action["scratch"], "t3-stage.json").is_file())
            self.assertIn(action["scratch"], each["wait"])
            self.assertIn(action["scratch"], each["report"])
        self.assertEqual(2, len({call["arguments"]["clientRequestId"] for call in self.calls()}))

    def test_the_guard_record_stays_until_the_last_batch_was_reported(self):
        _, batches = self.epic_at_tidy(SHELF_FILES)
        for action in batches:
            self.started(action, "local")

        self.stage_call("report", batches[0])
        held_between = self.guard_of(batches[0])
        self.stage_call("report", batches[1])

        self.assertIsNotNone(held_between)
        self.assertIsNone(self.guard_of(batches[0]))


class EndingAPassStageThatRunsTests(PassStageCase):
    """A stop and a resume end the threads of a pass stage that may still run, wherever the stage keeps its state: in
    the pass worktree's scratch folder, or in the folder of a tidy batch."""

    def scheduler(self, *args: str) -> subprocess.CompletedProcess:
        return self.run_script(test_scheduler.SCHEDULER, *args, thread=None, now=None)

    def stop(self, epic: str) -> subprocess.CompletedProcess:
        done = self.scheduler("stop", epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return done

    def resume(self, epic: str) -> subprocess.CompletedProcess:
        beat = self.home / "heartbeat" / f"{epic}.json"
        beat.parent.mkdir(exist_ok=True)
        beat.write_text(json.dumps({"epic": epic, "time": 1, "session": "session-of-the-closed-host"}),
                        encoding="utf-8")
        done = self.scheduler("next", epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return done

    def tools_called(self) -> list[str]:
        return [call["tool"] for call in self.calls()]

    def test_a_stop_interrupts_and_archives_the_thread_of_a_tidy_batch_and_removes_the_guard_record(self):
        epic, batches = self.epic_at_tidy(SHELF_FILES)
        for action in batches:
            self.started(action, "local")

        self.stop(epic)

        self.assertEqual(["t3_thread_launch"] * 2 + ["t3_thread_interrupt", "t3_thread_organize"] * 2,
                         self.tools_called())
        interrupt = self.calls()[2]
        self.assertEqual({"threadId": CLEANUP_THREAD, "stop": True},
                         {key: interrupt["arguments"][key] for key in ("threadId", "stop")})
        self.assertEqual({"threadId": CLEANUP_THREAD, "action": "archive"}, self.calls()[3]["arguments"])
        self.assertEqual(1, len(interrupt["guards"]))
        self.assertIsNone(self.guard_of(batches[0]))

    def test_a_stop_interrupts_and_archives_the_thread_of_a_test_cleanup_kept_in_the_pass_scratch_folder(self):
        epic, action = self.epic_at_cleanup()
        self.started(action, "deep")

        self.stop(epic)

        self.assertEqual(["t3_thread_launch", "t3_thread_interrupt", "t3_thread_organize"], self.tools_called())
        self.assertIsNone(self.guard_of(action))

    def test_a_stop_leaves_a_batch_that_was_reported_alone_and_ends_the_one_that_still_runs(self):
        epic, batches = self.epic_at_tidy(SHELF_FILES)
        for action in batches:
            self.started(action, "local")
        self.stage_call("report", batches[0])
        before = len(self.calls())

        self.stop(epic)

        self.assertEqual(["t3_thread_interrupt", "t3_thread_organize"],
                         [call["tool"] for call in self.calls()[before:]])
        self.assertIsNone(self.guard_of(batches[1]))

    def test_a_stop_that_cannot_interrupt_a_batch_keeps_the_guard_record(self):
        epic, batches = self.epic_at_tidy(SHELF_FILES)
        self.started(batches[0], "local")
        self.answer({"t3_thread_launch": {"threadId": CLEANUP_THREAD},
                     "t3_thread_interrupt": {"exit": 1, "stderr": "the bridge is down"}})

        done = self.stop(epic)

        self.assertIn("the bridge is down", done.stderr)
        self.assertNotIn("t3_thread_organize", self.tools_called())
        self.assertIsNotNone(self.guard_of(batches[0]))

    def test_a_stop_makes_no_t3_call_for_an_epic_whose_pass_started_no_thread(self):
        epic, _ = self.epic_at_tidy(SHELF_FILES)

        self.stop(epic)

        self.assertEqual([], self.calls())

    def test_a_resume_interrupts_and_archives_the_thread_of_a_tidy_batch_and_removes_the_guard_record(self):
        epic, batches = self.epic_at_tidy(SHELF_FILES)
        self.started(batches[0], "local")

        self.resume(epic)

        self.assertEqual(["t3_thread_launch", "t3_thread_interrupt", "t3_thread_organize"], self.tools_called())
        self.assertIsNone(self.guard_of(batches[0]))

    def test_a_resume_of_an_epic_that_carries_the_human_label_still_ends_the_thread_of_a_tidy_batch(self):
        epic, batches = self.epic_at_tidy(SHELF_FILES)
        self.started(batches[0], "local")
        self.bd_here("label", "add", epic, "human")

        self.resume(epic)

        self.assertEqual(["t3_thread_launch", "t3_thread_interrupt", "t3_thread_organize"], self.tools_called())
        self.assertIsNone(self.guard_of(batches[0]))

    def test_a_batch_started_again_after_a_stop_is_a_new_launch_to_t3(self):
        epic, batches = self.epic_at_tidy(SHELF_FILES)
        self.started(batches[0], "local")
        self.stop(epic)

        self.started(batches[0], "local")

        first, second = [call["arguments"]["clientRequestId"] for call in self.calls()
                         if call["tool"] == "t3_thread_launch"]
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
