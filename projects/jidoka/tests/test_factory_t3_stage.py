import json
import os
import shlex
import subprocess
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import t3_state  # noqa: E402
from test_stop import LAUNCHER, PLUGIN, RUN_TIMEOUT_SECONDS, StopCase  # noqa: E402

sys.path.insert(0, str(PLUGIN / "scripts"))
import lap_guard_record  # noqa: E402
import launcher  # noqa: E402

LEDGER = PLUGIN / "scripts" / "ledger.py"
FACTORY = PLUGIN / "scripts" / "factory.py"
SCHEDULER = PLUGIN / "scripts" / "scheduler.py"
STALE_SECONDS = 600
LAP_LISTS = PLUGIN / "scripts" / "lap_lists.py"
LAP_PROTECTED = PLUGIN / "scripts" / "lap_protected.py"
MANAGER_THREAD = "thread-of-the-manager"
WORKER_THREAD = "thread-of-the-build"
STARTED = 1_800_000_000
BUILD_WALL_CLOCK_SECONDS = 60 * 60
WAIT_STEP_MILLISECONDS = 45_000
NEON = {"harness": "t3", "model": "gemini-4-neon", "version": None, "effort": "high", "provider": "antigravity-main",
        "driver": "antigravity"}
AMBIENT = ("JIDOKA_SESSION_ID", "T3CODE_THREAD_ID", "JIDOKA_NOW", "T3_ACP_MCP_NODE", "T3_ACP_MCP_ENTRYPOINT")

FAKE_ACP_MCP_CALL = f"""#!{sys.executable}
import json
import os
import sys
import time
from pathlib import Path

folder = Path(os.environ["FAKE_T3_FOLDER"])
tool, arguments = sys.argv[2], json.loads(sys.argv[3])
guards = Path(os.environ["FAKE_T3_GUARDS"])
with (folder / "calls.jsonl").open("a", encoding="utf-8") as calls:
    calls.write(json.dumps({{"argv": sys.argv[1:2], "tool": tool, "arguments": arguments,
                            "electron": os.environ.get("ELECTRON_RUN_AS_NODE"),
                            "guards": sorted(path.name for path in guards.glob("*.json"))}}) + "\\n")
answers = json.loads((folder / "answers.json").read_text(encoding="utf-8"))
answer = answers.get(tool, {{}})
time.sleep(answer.get("sleep", 0))
if answer.get("exit"):
    print(answer.get("stderr", "the fake T3 failed"), file=sys.stderr)
    sys.exit(answer["exit"])
print(json.dumps(answer))
"""


class T3StageCase(StopCase):
    """A handed-off epic whose first lap is open, the factory script run as a process in a T3 thread that exports no
    jidoka session, and T3 faked behind a fake `acp-mcp-call` that records each tool call and answers it from a file."""

    def setUp(self):
        super().setUp()
        self.t3 = self.root / "t3"
        self.t3.mkdir()
        t3_state.create(self.t3_db, t3_state.TOKEN_TABLES)
        self.acp = fixture.write_executable(self.t3 / "acp-node", FAKE_ACP_MCP_CALL)
        self.answer({"t3_thread_launch": {"threadId": WORKER_THREAD}})
        (self.home / "settings.json").write_text(json.dumps({"antigravity_routes": {"standard": NEON, "deep": NEON}}),
                                                 encoding="utf-8")
        self.action = self.next_printed()["actions"][0]
        self.worktree = self.action["worktree"]
        self.prompt = Path(self.action["scratch"]) / "build-prompt.md"
        self.prompt.write_text(f"jidoka lap worktree: {self.worktree}\n\nBuild the task.\n", encoding="utf-8")

    @property
    def t3_db(self) -> Path:
        """T3's state db, which every script of the case reads through $JIDOKA_T3_STATE_DB, so that none reads a real
        one."""
        return self.root / "statev2.sqlite"

    def environment(self, extra: dict[str, str]) -> dict[str, str]:
        environment = {key: value for key, value in os.environ.items() if key not in AMBIENT}
        return {**environment, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
                "BEADS_ACTOR": "Pat Human", "JIDOKA_T3_STATE_DB": str(self.t3_db), **extra}

    def script(self, script: Path, *args: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(script), *args], None, self.environment({}), self.repo,
                                    RUN_TIMEOUT_SECONDS)

    def factory(self, now: int | None, *args: str, thread: str | None) -> subprocess.CompletedProcess:
        """Runs factory.py with JIDOKA_NOW at `now`, or on the machine's clock when `now` is None."""
        extra = {"T3_ACP_MCP_NODE": str(self.acp), "FAKE_T3_FOLDER": str(self.t3),
                 "FAKE_T3_GUARDS": str(self.home / lap_guard_record.FOLDER)}
        if now is not None:
            extra["JIDOKA_NOW"] = str(now)
        if thread is not None:
            extra["T3CODE_THREAD_ID"] = thread
        return fixture.run_launcher(LAUNCHER, [str(FACTORY), *args], None, self.environment(extra), self.repo,
                                    RUN_TIMEOUT_SECONDS)

    def script_in(self, script: Path, folder: str, *args: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(script), *args], None, self.environment({}), Path(folder),
                                    RUN_TIMEOUT_SECONDS)

    def start(self, now: int, tier: str) -> subprocess.CompletedProcess:
        return self.factory(now, "start", "--worktree", self.worktree, "--prompt", str(self.prompt), "--tier", tier,
                            "--jidoka-home", str(self.home), thread=MANAGER_THREAD)

    def wait(self, now: int | None) -> subprocess.CompletedProcess:
        return self.factory(now, "wait", "--worktree", self.worktree, "--jidoka-home", str(self.home),
                            thread=MANAGER_THREAD)

    def report(self, now: int | None) -> subprocess.CompletedProcess:
        return self.factory(now, "report", "--worktree", self.worktree, "--jidoka-home", str(self.home),
                            thread=MANAGER_THREAD)

    def answer(self, answers: dict) -> None:
        (self.t3 / "answers.json").write_text(json.dumps(answers), encoding="utf-8")

    def calls(self) -> list[dict]:
        path = self.t3 / "calls.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def tools_called(self) -> list[str]:
        return [call["tool"] for call in self.calls()]

    def started(self) -> dict:
        done = self.start(STARTED, "standard")
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def guard(self) -> lap_guard_record.GuardRecord | None:
        return lap_guard_record.read_record(self.home, Path(self.worktree))


class StartingTheBuildTests(T3StageCase):
    def test_launches_a_thread_in_the_lap_worktree_on_the_routes_model_and_thought_level(self):
        self.started()

        (launch,) = self.calls()
        arguments = launch["arguments"]
        self.assertEqual("t3_thread_launch", launch["tool"])
        self.assertEqual(["acp-mcp-call"], launch["argv"])
        self.assertEqual("1", launch["electron"])
        self.assertEqual({"type": "existing_worktree", "worktreePath": self.worktree}, arguments["workspaceStrategy"])
        self.assertEqual({"instanceId": "antigravity-main", "model": "gemini-4-neon",
                          "options": {"thought_level": "high"}}, arguments["modelSelection"])
        self.assertEqual(self.prompt.read_text(encoding="utf-8"), arguments["message"])

    def test_titles_the_thread_lap_and_the_task_title_without_the_bead_id(self):
        self.started()

        title = self.calls()[0]["arguments"]["title"]
        self.assertEqual(f"lap · {self.shown(self.action['task'])['title']}", title)
        self.assertNotIn(self.action["task"], title)

    def test_names_the_launch_with_a_client_request_id_that_a_second_start_of_the_same_lap_repeats(self):
        self.started()
        self.started()

        first, second = (call["arguments"]["clientRequestId"] for call in self.calls())
        self.assertTrue(first)
        self.assertEqual(first, second)

    def test_names_a_start_apart_from_every_earlier_start_of_the_same_stage_in_the_lap(self):
        self.started()
        requests = {"first start": self.calls()[-1]["arguments"]["clientRequestId"]}
        returns = {"a failed try": ("lap.tries", "1"), "a send-back": ("lap.sendbacks", "1"),
                   "a merge try": ("lap.mergetries", "1"), "a cutoff of the stage": ("lap.cutoffs.build", "1")}
        for name, (key, value) in returns.items():
            self.bd("update", self.action["task"], "--set-metadata", f"{key}={value}")
            self.started()
            requests[name] = self.calls()[-1]["arguments"]["clientRequestId"]

        self.assertEqual(len(requests), len(set(requests.values())), requests)

    def test_names_each_call_of_the_merge_worker_apart_by_the_epic_head_it_was_called_at(self):
        self.bd("update", self.action["task"], "--set-metadata", "lap.stage=merge")
        requests = []
        for base in ("0123456789abcdef0123", "fedcba9876543210fedc"):
            self.bd("update", self.action["task"], "--set-metadata", f"lap.mergebase={base}")
            self.started()
            requests.append(self.calls()[-1]["arguments"]["clientRequestId"])

        self.assertEqual(2, len(set(requests)), requests)

    def test_a_cutoff_of_another_stage_does_not_rename_the_launch_of_this_one(self):
        self.started()
        self.bd("update", self.action["task"], "--set-metadata", "lap.cutoffs.research=1")
        self.started()

        first, second = (call["arguments"]["clientRequestId"] for call in self.calls())
        self.assertEqual(first, second)

    def test_the_retry_of_a_failed_launch_keeps_the_request_id_of_a_lap_that_went_back_to_the_stage(self):
        self.bd("update", self.action["task"], "--set-metadata", "lap.tries=1")
        self.bd("update", self.action["task"], "--set-metadata", "lap.sendbacks=2")
        self.answer({"t3_thread_launch": {"exit": 1, "stderr": "no such project"}})

        self.start(STARTED, "standard")

        first, second = (call["arguments"]["clientRequestId"] for call in self.calls())
        self.assertEqual(first, second)

    def test_prints_the_thread_the_deadline_and_the_calls_that_wait_and_report_the_stage(self):
        printed = self.started()

        self.assertEqual(WORKER_THREAD, printed["thread"])
        self.assertEqual(STARTED + BUILD_WALL_CLOCK_SECONDS, printed["deadline"])
        self.assertEqual(BUILD_WALL_CLOCK_SECONDS, printed["wall_seconds"])
        for name in ("wait", "report"):
            self.assertIn(f"factory.py {name} --worktree", printed[name].replace('"', "").replace("'", ""))
            self.assertIn(self.worktree, printed[name])

    def test_writes_the_guard_record_before_the_launch_with_the_lists_the_lap_mod_would_hold_the_worker_to(self):
        self.started()

        self.assertEqual(1, len(self.calls()[0]["guards"]))
        held = self.guard()
        listed = self.script_in(LAP_LISTS, self.worktree, "lap")
        protected = self.script_in(LAP_PROTECTED, self.worktree)
        self.assertEqual(0, protected.returncode, protected.stderr)
        self.assertIsNotNone(held)
        self.assertEqual(("lap", "build"), (held.kind, held.stage))
        self.assertEqual(json.loads(listed.stdout), held.commands)
        self.assertEqual(json.loads(protected.stdout), held.barred)

    def test_writes_barred_as_null_when_lap_protected_cannot_print_the_folders(self):
        for settings in self.home.glob("repos/*.json"):
            settings.unlink()
        protected = self.script_in(LAP_PROTECTED, self.worktree)
        self.assertEqual(1, protected.returncode)

        self.started()

        held = self.guard()
        self.assertIsNotNone(held)
        self.assertIsNone(held.barred)

    def test_refuses_a_folder_that_holds_no_tasks_lap_and_writes_no_guard_record_for_it(self):
        done = self.factory(STARTED, "start", "--worktree", str(self.repo), "--prompt", str(self.prompt), "--tier",
                            "standard", "--jidoka-home", str(self.home), thread=MANAGER_THREAD)

        self.assertEqual(1, done.returncode)
        self.assertEqual([], self.calls())
        self.assertIsNone(lap_guard_record.read_record(self.home, self.repo))

    def test_a_launch_that_fails_is_tried_once_more_under_the_same_request_id_then_exits_one_naming_the_call(self):
        self.answer({"t3_thread_launch": {"exit": 1, "stderr": "no such project"}})

        done = self.start(STARTED, "standard")

        self.assertEqual(1, done.returncode)
        self.assertIn("t3_thread_launch", done.stderr)
        self.assertIn("no such project", done.stderr)
        self.assertEqual(["t3_thread_launch", "t3_thread_launch"], self.tools_called())
        self.assertEqual(self.calls()[0]["arguments"]["clientRequestId"], self.calls()[1]["arguments"]["clientRequestId"])

    def test_a_launch_that_fails_leaves_no_guard_record_behind(self):
        self.answer({"t3_thread_launch": {"exit": 1, "stderr": "no such project"}})

        self.start(STARTED, "standard")

        self.assertEqual(1, len(self.calls()[0]["guards"]))
        self.assertIsNone(self.guard())

    def test_refuses_on_a_host_that_runs_workers_as_agents_and_launches_nothing(self):
        done = self.factory(STARTED, "start", "--worktree", self.worktree, "--prompt", str(self.prompt), "--tier",
                            "standard", "--jidoka-home", str(self.home), thread=None)

        self.assertEqual(1, done.returncode)
        self.assertIn("Antigravity", done.stderr)
        self.assertEqual([], self.calls())
        self.assertIsNone(self.guard())

    def test_refuses_a_tier_whose_route_is_not_an_antigravity_thread_before_it_writes_the_guard(self):
        claude = {"harness": "claude", "model": "sonnet", "version": "5.5", "effort": "high"}
        (self.home / "settings.json").write_text(json.dumps({"antigravity_routes": {"standard": claude}}),
                                                 encoding="utf-8")

        done = self.start(STARTED, "standard")

        self.assertEqual(1, done.returncode)
        self.assertIn("standard", done.stderr)
        self.assertEqual([], self.calls())
        self.assertIsNone(self.guard())

    def test_refuses_a_lap_that_rests_at_no_worker_stage_and_launches_nothing(self):
        self.bd("update", self.action["task"], "--set-metadata", "lap.stage=parked")

        done = self.start(STARTED, "standard")

        self.assertEqual(1, done.returncode)
        self.assertIn("parked", done.stderr)
        self.assertEqual([], self.calls())
        self.assertIsNone(self.guard())


class StartingEachStageTests(T3StageCase):
    """Every stage of a lap starts through the one launcher, as a thread in the lap's worktree."""

    STAGES = ("research", "build", "app-check", "spec-check", "merge")

    def at(self, stage: str) -> None:
        self.bd("update", self.action["task"], "--set-metadata", f"lap.stage={stage}")

    def first_message(self) -> str:
        return self.calls()[0]["arguments"]["message"]

    def test_each_stage_launches_one_thread_in_the_lap_worktree_on_its_tiers_route(self):
        for stage in self.STAGES:
            with self.subTest(stage=stage):
                self.at(stage)
                self.t3.joinpath("calls.jsonl").unlink(missing_ok=True)

                printed = self.started()

                (launch,) = self.calls()
                arguments = launch["arguments"]
                self.assertEqual("t3_thread_launch", launch["tool"])
                self.assertEqual({"type": "existing_worktree", "worktreePath": self.worktree},
                                 arguments["workspaceStrategy"])
                self.assertEqual({"instanceId": "antigravity-main", "model": "gemini-4-neon",
                                  "options": {"thought_level": "high"}}, arguments["modelSelection"])
                self.assertEqual(f"lap · {self.shown(self.action['task'])['title']}", arguments["title"])
                self.assertTrue(arguments["message"].endswith(self.prompt.read_text(encoding="utf-8")))
                self.assertEqual(WORKER_THREAD, printed["thread"])

    def test_a_stage_that_is_not_the_build_has_the_thirty_minute_wall_clock(self):
        for stage in ("research", "app-check", "spec-check", "merge"):
            with self.subTest(stage=stage):
                self.at(stage)

                printed = self.started()

                self.assertEqual(30 * 60, printed["wall_seconds"])
                self.assertEqual(STARTED + 30 * 60, printed["deadline"])

    def test_a_launch_of_one_stage_is_named_apart_from_the_launch_of_another(self):
        requests = []
        for stage in ("research", "build"):
            self.at(stage)
            self.started()
            requests.append(self.calls()[-1]["arguments"]["clientRequestId"])

        self.assertEqual(2, len(set(requests)))

    def test_the_app_check_thread_opens_with_the_app_check_agents_instructions_and_then_the_prompt(self):
        self.at("app-check")

        self.started()

        message = self.first_message()
        self.assertTrue(message.startswith("# App check worker"), message[:80])
        self.assertIn("app_process.py start <app>", message)
        self.assertNotIn("name: app-check", message)
        self.assertTrue(message.endswith("\n\n---\n\n" + self.prompt.read_text(encoding="utf-8")))

    def test_the_spec_check_thread_opens_with_the_spec_check_skills_instructions_and_then_the_prompt(self):
        self.at("spec-check")

        self.started()

        message = self.first_message()
        self.assertIn("The Spec check holds one bead's diff to the bead.", message)
        self.assertNotIn("argument-hint", message)
        self.assertTrue(message.endswith("\n\n---\n\n" + self.prompt.read_text(encoding="utf-8")))

    def test_a_research_and_a_merge_thread_open_with_the_prompt_alone(self):
        for stage in ("research", "merge"):
            with self.subTest(stage=stage):
                self.at(stage)
                self.t3.joinpath("calls.jsonl").unlink(missing_ok=True)

                self.started()

                self.assertEqual(self.prompt.read_text(encoding="utf-8"), self.first_message())

    def test_the_app_check_workers_guard_record_is_a_check_record_that_holds_the_check_list_and_bars_no_folder(self):
        self.at("app-check")

        self.started()

        held = self.guard()
        listed = self.script_in(LAP_LISTS, self.worktree, "check")
        self.assertEqual(0, listed.returncode, listed.stderr)
        self.assertIsNotNone(held)
        self.assertEqual(("check", "app-check"), (held.kind, held.stage))
        self.assertEqual(json.loads(listed.stdout), held.commands)
        self.assertEqual([], held.barred)

    def test_the_merge_workers_guard_record_holds_the_grants_of_its_stage(self):
        self.at("merge")
        branch = self.metadata(self.epic)["factory.branch"]

        self.started()

        held = self.guard()
        listed = self.script_in(LAP_LISTS, self.worktree, "lap")
        self.assertIsNotNone(held)
        self.assertEqual(("lap", "merge"), (held.kind, held.stage))
        self.assertEqual(json.loads(listed.stdout), held.commands)
        self.assertIn({"command": f"git rebase {branch}", "then": "nothing"}, held.commands)
        self.assertIn({"command": "git -c core.editor=true rebase --continue", "then": "nothing"}, held.commands)

    def test_the_guard_record_of_a_stage_before_the_merge_holds_no_merge_grant(self):
        for stage in ("research", "build", "spec-check"):
            with self.subTest(stage=stage):
                self.at(stage)

                self.started()

                self.assertNotIn("git rebase --abort", [entry.get("command") for entry in self.guard().commands
                                                        if isinstance(entry, dict)])

    def test_an_app_check_whose_repo_has_no_settings_is_refused_with_no_guard_record_and_no_launch(self):
        self.at("app-check")
        for settings in self.home.glob("repos/*.json"):
            settings.unlink()

        done = self.start(STARTED, "standard")

        self.assertEqual(1, done.returncode)
        self.assertEqual([], self.calls())
        self.assertIsNone(self.guard())


class ReportingEachStageTests(T3StageCase):
    def test_a_stage_other_than_the_build_waits_and_reports_as_the_build_does(self):
        self.bd("update", self.action["task"], "--set-metadata", "lap.stage=spec-check")
        started = self.started()
        self.answer({"t3_thread_wait": {"timedOut": False},
                     "t3_thread_read": {"items": [{"position": 3, "type": "assistant_message", "text": '```json\n{"outcome": "pass"}\n```'}]}})

        waited = json.loads(self.wait(STARTED + 60).stdout)
        reported = self.report(STARTED + 90)

        self.assertEqual(("ended", started["report"]), (waited["state"], waited["next"]))
        self.assertEqual({"thread": WORKER_THREAD, "cut_off": False, "reply": '```json\n{"outcome": "pass"}\n```'},
                         json.loads(reported.stdout))
        self.assertIsNone(self.guard())

    def test_a_merge_stage_past_its_thirty_minute_wall_clock_is_stopped_and_ends_cut_off(self):
        self.bd("update", self.action["task"], "--set-metadata", "lap.stage=merge")
        self.started()

        done = self.wait(STARTED + 30 * 60 + 1)

        self.assertEqual("cut off", json.loads(done.stdout)["state"])
        self.assertEqual("t3_thread_interrupt", self.calls()[-1]["tool"])


class WaitingForTheBuildTests(T3StageCase):
    def test_a_step_that_times_out_before_the_deadline_says_running_and_names_the_call_to_wait_again(self):
        started = self.started()
        self.answer({"t3_thread_wait": {"timedOut": True}})

        done = self.wait(STARTED + 120)

        self.assertEqual(0, done.returncode, done.stderr)
        printed = json.loads(done.stdout)
        self.assertEqual("running", printed["state"])
        self.assertEqual(started["wait"], printed["next"])
        self.assertEqual({"threadId": WORKER_THREAD, "timeoutMs": WAIT_STEP_MILLISECONDS},
                         self.calls()[-1]["arguments"])
        self.assertNotIn("t3_thread_interrupt", self.tools_called())

    def test_a_run_that_finished_says_ended_and_names_the_call_that_reports_the_stage(self):
        started = self.started()
        self.answer({"t3_thread_wait": {"timedOut": False}})

        done = self.wait(STARTED + 600)

        printed = json.loads(done.stdout)
        self.assertEqual("ended", printed["state"])
        self.assertEqual(started["report"], printed["next"])

    def test_a_worker_past_its_deadline_is_stopped_with_an_interrupt_and_the_stage_ends_cut_off(self):
        started = self.started()

        done = self.wait(STARTED + BUILD_WALL_CLOCK_SECONDS + 1)

        self.assertEqual(0, done.returncode, done.stderr)
        printed = json.loads(done.stdout)
        self.assertEqual("cut off", printed["state"])
        self.assertEqual(started["report"], printed["next"])
        interrupt = self.calls()[-1]
        self.assertEqual("t3_thread_interrupt", interrupt["tool"])
        self.assertEqual(WORKER_THREAD, interrupt["arguments"]["threadId"])
        self.assertIs(True, interrupt["arguments"]["stop"])
        self.assertNotIn("t3_thread_wait", self.tools_called())

    def test_a_wait_that_cannot_reach_t3_exits_one_and_names_the_call(self):
        self.started()
        self.answer({"t3_thread_wait": {"exit": 3, "stderr": "the bridge is down"}})

        done = self.wait(STARTED + 60)

        self.assertEqual(1, done.returncode)
        self.assertIn("t3_thread_wait", done.stderr)
        self.assertIn("the bridge is down", done.stderr)


class WaitingAcrossTheDeadlineTests(T3StageCase):
    """A step of the wait that begins before the stage's deadline and returns after it, on the machine's own clock,
    because only a real wait lets the clock pass the deadline inside one call."""

    WAIT_LASTS_SECONDS = 3
    DEADLINE_IN_SECONDS = 1

    def start_a_stage_whose_deadline_falls_inside_the_next_wait(self) -> None:
        self.started()
        state = Path(self.worktree) / ".scratch" / "t3-stage.json"
        held = json.loads(state.read_text(encoding="utf-8"))
        state.write_text(json.dumps({**held, "deadline": int(time.time()) + self.DEADLINE_IN_SECONDS}),
                         encoding="utf-8")

    def test_a_run_that_ended_after_the_deadline_while_the_step_waited_ends_cut_off_without_an_interrupt(self):
        self.start_a_stage_whose_deadline_falls_inside_the_next_wait()
        self.answer({"t3_thread_wait": {"timedOut": False, "sleep": self.WAIT_LASTS_SECONDS}})

        done = self.wait(None)

        printed = json.loads(done.stdout)
        self.assertEqual("cut off", printed["state"])
        self.assertEqual(self.started_report_call(), printed["next"])
        self.assertNotIn("t3_thread_interrupt", self.tools_called())

    def test_a_run_still_going_after_the_deadline_when_the_step_returns_is_interrupted_and_ends_cut_off(self):
        self.start_a_stage_whose_deadline_falls_inside_the_next_wait()
        self.answer({"t3_thread_wait": {"timedOut": True, "sleep": self.WAIT_LASTS_SECONDS}})

        done = self.wait(None)

        self.assertEqual("cut off", json.loads(done.stdout)["state"])
        self.assertEqual("t3_thread_interrupt", self.calls()[-1]["tool"])

    def test_the_report_after_such_a_step_says_the_stage_was_cut_off(self):
        self.start_a_stage_whose_deadline_falls_inside_the_next_wait()
        self.answer({"t3_thread_wait": {"timedOut": False, "sleep": self.WAIT_LASTS_SECONDS},
                     "t3_thread_read": {"items": [{"position": 3, "type": "assistant_message", "text": "Done."}]}})
        self.wait(None)

        done = self.report(None)

        self.assertIs(True, json.loads(done.stdout)["cut_off"])

    def started_report_call(self) -> str:
        return (f"{launcher.command_for('factory.py')} report --worktree {shlex.quote(self.worktree)} "
                f"--jidoka-home {shlex.quote(str(self.home))}")


class PricingTheThreadWhenTheStageIsReportedTests(T3StageCase):
    """The report of a stage writes the ledger rows of its thread, and the scheduler's report of the same worker gives
    them its outcome and writes none, so no token is counted twice."""

    REPLY = {"t3_thread_read": {"items": [{"position": 3, "type": "assistant_message", "text": "Built it."}]}}

    def give_the_thread_a_turn(self, input_tokens: int, output_tokens: int) -> None:
        t3_state.add_next_run(self.t3_db, "run-1", WORKER_THREAD, "gemini-4-neon", "completed", "completed")
        t3_state.add_next_turn(self.t3_db, WORKER_THREAD, "run-1",
                               t3_state.usage(input_tokens, 0, 0, output_tokens, 0))

    def rows(self) -> list[dict]:
        done = self.script(LEDGER, "list", self.epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)["rows"]

    def scheduler_report(self, outcome: str, *more: str) -> subprocess.CompletedProcess:
        """The scheduler's report of the build, in the manager's thread, on the machine's clock."""
        return fixture.run_launcher(
            LAUNCHER, [str(SCHEDULER), "report", self.epic, self.action["task"], outcome, "--agent", WORKER_THREAD,
                       "--tier", "standard", *more], None,
            self.environment({"T3CODE_THREAD_ID": MANAGER_THREAD}), self.repo, RUN_TIMEOUT_SECONDS)

    def test_the_report_of_a_stage_writes_one_row_for_each_model_of_its_thread_with_the_lap_it_ran_in(self):
        self.started()
        self.answer(self.REPLY)
        self.give_the_thread_a_turn(1_000_000, 100_000)

        done = self.report(STARTED + 900)

        self.assertEqual(0, done.returncode, done.stderr)
        [row] = self.rows()
        self.assertEqual((self.action["task"], "build", "standard", WORKER_THREAD, "gemini-4-neon", "done"),
                         (row["task"], row["stage"], row["tier"], row["agent"], row["model"], row["outcome"]))
        self.assertEqual((1_000_000, 100_000), (row["input_tokens"], row["output_tokens"]))
        self.assertGreater(row["dollars"], 0)

    def test_a_stage_that_was_cut_off_is_priced_as_cut_off(self):
        self.started()
        self.answer(self.REPLY)
        self.give_the_thread_a_turn(1_000, 10)
        self.wait(STARTED + BUILD_WALL_CLOCK_SECONDS + 5)

        self.report(STARTED + BUILD_WALL_CLOCK_SECONDS + 6)

        [row] = self.rows()
        self.assertEqual("cut off", row["outcome"])

    def test_the_schedulers_report_of_the_same_worker_counts_its_tokens_once_and_gives_the_rows_its_outcome(self):
        self.started()
        self.answer(self.REPLY)
        self.give_the_thread_a_turn(1_000_000, 100_000)
        self.report(STARTED + 900)

        reported = self.scheduler_report("failed", "--why", "red")

        self.assertEqual(0, reported.returncode, reported.stderr)
        [row] = self.rows()
        self.assertEqual((1_000_000, 100_000, "failed"), (row["input_tokens"], row["output_tokens"], row["outcome"]))

    def test_a_thread_with_no_turns_is_priced_with_no_tokens_and_the_report_still_answers(self):
        self.started()
        self.answer(self.REPLY)

        done = self.report(STARTED + 900)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("no tokens for thread", done.stderr)
        [row] = self.rows()
        self.assertEqual((WORKER_THREAD, 0, 0), (row["agent"], row["input_tokens"], row["output_tokens"]))

    def test_the_report_of_a_stage_that_was_never_priced_leaves_the_schedulers_report_to_price_it(self):
        self.started()
        self.give_the_thread_a_turn(2_000, 20)

        reported = self.scheduler_report("failed", "--why", "red")

        self.assertEqual(0, reported.returncode, reported.stderr)
        [row] = self.rows()
        self.assertEqual((WORKER_THREAD, 2_000, "failed"), (row["agent"], row["input_tokens"], row["outcome"]))


class ReportingTheBuildTests(T3StageCase):
    REPLIES = {"t3_thread_read": {"items": [
        {"position": 0, "type": "user_message", "text": "the task"},
        {"position": 23, "type": "assistant_message", "text": "Waiting for the targeted test run to finish."},
        {"position": 25, "type": "assistant_message", "text": 'Built it.\n```json\n{"outcome": "done"}\n```'}]}}

    def test_reads_the_last_reply_then_archives_the_thread_and_prints_the_reply(self):
        self.started()
        self.answer(self.REPLIES)

        done = self.report(STARTED + 900)

        self.assertEqual(0, done.returncode, done.stderr)
        printed = json.loads(done.stdout)
        self.assertEqual({"thread": WORKER_THREAD, "cut_off": False,
                          "reply": 'Built it.\n```json\n{"outcome": "done"}\n```'}, printed)
        read, organize = self.calls()[-2:]
        self.assertEqual("t3_thread_read", read["tool"])
        self.assertEqual({"threadId": WORKER_THREAD, "view": "messages"},
                         {key: read["arguments"][key] for key in ("threadId", "view")})
        self.assertEqual(("t3_thread_organize", {"threadId": WORKER_THREAD, "action": "archive"}),
                         (organize["tool"], organize["arguments"]))

    def test_removes_the_guard_record_once_the_thread_is_archived(self):
        self.started()
        self.answer(self.REPLIES)

        self.report(STARTED + 900)

        self.assertIsNone(self.guard())

    def test_removes_the_guard_record_when_the_archive_fails_because_the_reply_was_read(self):
        self.started()
        self.answer({**self.REPLIES, "t3_thread_organize": {"exit": 1, "stderr": "archive refused"}})

        done = self.report(STARTED + 900)

        self.assertEqual(1, done.returncode)
        self.assertIn("t3_thread_organize", done.stderr)
        self.assertIsNone(self.guard())

    def test_keeps_the_guard_record_when_the_read_fails_because_the_worker_may_still_run(self):
        self.started()
        self.answer({"t3_thread_read": {"exit": 1, "stderr": "no such thread"}})

        done = self.report(STARTED + 900)

        self.assertEqual(1, done.returncode)
        self.assertIsNotNone(self.guard())
        self.assertNotIn("t3_thread_organize", self.tools_called())

    def test_a_stage_that_was_cut_off_reports_it_beside_the_last_reply(self):
        self.started()
        self.answer(self.REPLIES)
        self.wait(STARTED + BUILD_WALL_CLOCK_SECONDS + 5)

        done = self.report(STARTED + BUILD_WALL_CLOCK_SECONDS + 6)

        self.assertIs(True, json.loads(done.stdout)["cut_off"])

    def test_the_last_reply_is_the_assistant_message_with_the_highest_position_whatever_the_order(self):
        self.started()
        self.answer({"t3_thread_read": {"items": [
            {"position": 9, "type": "assistant_message", "text": "the final reply"},
            {"position": 4, "type": "assistant_message", "text": "a progress note"},
            {"position": 12, "type": "user_message", "text": "a later user message"}]}})

        done = self.report(STARTED + 900)

        self.assertEqual("the final reply", json.loads(done.stdout)["reply"])

    def test_a_thread_with_no_assistant_message_reports_an_empty_reply(self):
        self.started()
        self.answer({"t3_thread_read": {"items": [{"position": 0, "type": "user_message", "text": "the task"}]}})

        done = self.report(STARTED + 900)

        self.assertEqual("", json.loads(done.stdout)["reply"])

    def test_no_call_of_a_whole_stage_deletes_a_thread(self):
        self.started()
        self.answer({**self.REPLIES, "t3_thread_wait": {"timedOut": True}})
        self.wait(STARTED + 60)
        self.wait(STARTED + BUILD_WALL_CLOCK_SECONDS + 5)
        self.report(STARTED + BUILD_WALL_CLOCK_SECONDS + 6)

        for call in self.calls():
            with self.subTest(call=call["tool"]):
                self.assertNotIn("delete", call["tool"])
                self.assertNotEqual("delete", call["arguments"].get("action"))
        self.assertEqual(["t3_thread_launch", "t3_thread_wait", "t3_thread_interrupt", "t3_thread_read",
                          "t3_thread_organize"], self.tools_called())


class EndingAThreadedLapTests(T3StageCase):
    """A stop and a resume end a lap whose stage thread may still run. They interrupt and archive the thread named in
    t3-stage.json before they remove the lap's guard record."""

    def scheduler(self, t3: bool, *args: str) -> subprocess.CompletedProcess:
        extra = {"T3_ACP_MCP_NODE": str(self.acp), "FAKE_T3_FOLDER": str(self.t3),
                 "FAKE_T3_GUARDS": str(self.home / lap_guard_record.FOLDER)} if t3 else {}
        return fixture.run_launcher(LAUNCHER, [str(SCHEDULER), *args], None, self.environment(extra), self.repo,
                                    RUN_TIMEOUT_SECONDS)

    def stop_the_host(self, t3: bool) -> subprocess.CompletedProcess:
        done = self.scheduler(t3, "stop", self.epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return done

    def resume(self) -> subprocess.CompletedProcess:
        beat = self.home / "heartbeat" / f"{self.epic}.json"
        beat.parent.mkdir(exist_ok=True)
        beat.write_text(json.dumps({"epic": self.epic, "time": int(time.time()) - STALE_SECONDS,
                                    "session": "session-of-the-closed-host"}), encoding="utf-8")
        done = self.scheduler(True, "next", self.epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return done

    def guard_by_hand(self) -> None:
        fixture.write_guard_record(self.home, Path(self.worktree).resolve())

    def git_shows_the_lap_merged(self) -> None:
        worktree = Path(self.worktree)
        (worktree / "till.txt").write_text("till\n", encoding="utf-8")
        fixture.git_commit_all(worktree, self.shown(self.action["task"])["title"])
        head = fixture.run(["git", "rev-parse", "HEAD"], worktree).strip()
        branch = self.metadata(self.epic)["factory.branch"]
        fixture.run(["git", "update-ref", f"refs/heads/{branch}", head], self.repo)

    def test_a_stop_interrupts_the_thread_then_archives_it_while_the_guard_record_still_stands(self):
        self.started()

        self.stop_the_host(True)

        launch, interrupt, organize = self.calls()
        self.assertEqual(["t3_thread_launch", "t3_thread_interrupt", "t3_thread_organize"],
                         [launch["tool"], interrupt["tool"], organize["tool"]])
        self.assertEqual({"threadId": WORKER_THREAD, "stop": True},
                         {key: interrupt["arguments"][key] for key in ("threadId", "stop")})
        self.assertEqual({"threadId": WORKER_THREAD, "action": "archive"}, organize["arguments"])
        self.assertEqual(1, len(interrupt["guards"]))
        self.assertEqual(1, len(organize["guards"]))
        self.assertIsNone(self.guard())

    def test_a_stop_still_ends_the_lap_interrupted_when_t3_cannot_interrupt_and_keeps_the_guard_record(self):
        self.started()
        self.answer({"t3_thread_interrupt": {"exit": 1, "stderr": "the bridge is down"}})

        done = self.stop_the_host(True)

        self.assertEqual("interrupted", self.metadata(self.action["task"])["lap.stage"])
        self.assertIn("t3_thread_interrupt", done.stderr)
        self.assertIn("the bridge is down", done.stderr)
        self.assertNotIn("t3_thread_organize", self.tools_called())
        self.assertIsNotNone(self.guard())

    def test_a_stop_in_a_session_with_no_t3_program_keeps_the_guard_record_and_says_so(self):
        self.started()

        done = self.stop_the_host(False)

        self.assertEqual("interrupted", self.metadata(self.action["task"])["lap.stage"])
        self.assertIn("T3_ACP_MCP_NODE", done.stderr)
        self.assertEqual(["t3_thread_launch"], self.tools_called())
        self.assertIsNotNone(self.guard())

    def test_a_stop_removes_the_guard_record_when_the_archive_fails_because_the_thread_was_interrupted(self):
        self.started()
        self.answer({"t3_thread_organize": {"exit": 1, "stderr": "archive refused"}})

        done = self.stop_the_host(True)

        self.assertIn("t3_thread_organize", done.stderr)
        self.assertIn("archive refused", done.stderr)
        self.assertIsNone(self.guard())

    def test_a_stop_makes_no_t3_call_for_a_lap_that_has_no_stage_thread(self):
        self.guard_by_hand()

        self.stop_the_host(True)

        self.assertEqual([], self.calls())
        self.assertIsNone(self.guard())

    def test_a_stop_keeps_the_guard_record_of_a_lap_whose_state_file_names_no_thread(self):
        self.started()
        (Path(self.worktree) / ".scratch" / "t3-stage.json").write_text("not json", encoding="utf-8")

        done = self.stop_the_host(True)

        self.assertEqual(["t3_thread_launch"], self.tools_called())
        self.assertIn("t3-stage.json", done.stderr)
        self.assertIsNotNone(self.guard())

    def test_a_resume_interrupts_the_thread_then_archives_it_before_it_removes_the_guard_record(self):
        self.started()

        self.resume()

        launch, interrupt, organize = self.calls()
        self.assertEqual(["t3_thread_launch", "t3_thread_interrupt", "t3_thread_organize"],
                         [launch["tool"], interrupt["tool"], organize["tool"]])
        self.assertEqual(WORKER_THREAD, interrupt["arguments"]["threadId"])
        self.assertEqual(1, len(interrupt["guards"]))
        self.assertEqual(1, len(organize["guards"]))
        self.assertIsNone(self.guard())

    def test_a_resume_that_cannot_interrupt_still_starts_the_new_lap_and_keeps_the_guard_record(self):
        self.started()
        self.answer({"t3_thread_interrupt": {"exit": 1, "stderr": "the bridge is down"}})

        done = self.resume()

        self.assertIn("t3_thread_interrupt", done.stderr)
        self.assertIn(2, [action["lap"] for action in json.loads(done.stdout)["actions"]])
        self.assertNotIn("t3_thread_organize", self.tools_called())
        self.assertIsNotNone(self.guard())

    def test_a_resume_makes_no_t3_call_for_a_lap_that_has_no_stage_thread(self):
        self.guard_by_hand()

        self.resume()

        self.assertEqual([], self.calls())
        self.assertIsNone(self.guard())

    def test_a_resume_that_finds_the_lap_merged_interrupts_and_archives_its_thread_before_the_worktree_goes(self):
        self.started()
        self.git_shows_the_lap_merged()

        self.resume()

        launch, interrupt, organize = self.calls()
        self.assertEqual(["t3_thread_launch", "t3_thread_interrupt", "t3_thread_organize"],
                         [launch["tool"], interrupt["tool"], organize["tool"]])
        self.assertEqual({"threadId": WORKER_THREAD, "stop": True},
                         {key: interrupt["arguments"][key] for key in ("threadId", "stop")})
        self.assertEqual({"threadId": WORKER_THREAD, "action": "archive"}, organize["arguments"])
        self.assertEqual(1, len(interrupt["guards"]))
        self.assertEqual(1, len(organize["guards"]))
        self.assertEqual("closed", self.shown(self.action["task"])["status"])
        self.assertFalse(Path(self.worktree).exists())
        self.assertIsNone(self.guard())

    def test_a_resume_that_finds_the_lap_merged_closes_the_task_and_keeps_the_guard_record_when_t3_cannot_interrupt(
            self):
        self.started()
        self.git_shows_the_lap_merged()
        self.answer({"t3_thread_interrupt": {"exit": 1, "stderr": "the bridge is down"}})

        done = self.resume()

        self.assertIn("the bridge is down", done.stderr)
        self.assertEqual("closed", self.shown(self.action["task"])["status"])
        self.assertNotIn("t3_thread_organize", self.tools_called())
        self.assertIsNotNone(self.guard())

    def test_a_resume_that_finds_a_lap_with_no_stage_thread_merged_makes_no_t3_call(self):
        self.guard_by_hand()
        self.git_shows_the_lap_merged()

        self.resume()

        self.assertEqual([], self.calls())
        self.assertEqual("closed", self.shown(self.action["task"])["status"])
        self.assertIsNone(self.guard())

    def test_a_stop_and_a_resume_delete_no_thread(self):
        self.started()
        self.stop_the_host(True)
        self.resume()

        for call in self.calls():
            with self.subTest(call=call["tool"]):
                self.assertNotIn("delete", call["tool"])
                self.assertNotEqual("delete", call["arguments"].get("action"))


if __name__ == "__main__":
    unittest.main()
