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
sys.path.insert(0, str(PLUGIN / "scripts"))
import lap_guard_record  # noqa: E402

LAUNCHER = PLUGIN / "bin" / "jidoka-run"
ACCEPT_WORKER = PLUGIN / "scripts" / "accept_worker.py"
RUN_TIMEOUT_SECONDS = 120
MANAGER_THREAD = "thread-of-the-manager"
WORKER_THREAD = "thread-of-the-guide"
STARTED = 1_800_000_000
WALL_CLOCK_SECONDS = 30 * 60
NEON = {"harness": "t3", "model": "gemini-4-neon", "version": None, "effort": "high", "provider": "antigravity-main",
        "driver": "antigravity"}
AMBIENT = ("JIDOKA_SESSION_ID", "T3CODE_THREAD_ID", "JIDOKA_NOW", "T3_ACP_MCP_NODE", "T3_ACP_MCP_ENTRYPOINT")

FAKE_ACP_MCP_CALL = f"""#!{sys.executable}
import json
import os
import sys
from pathlib import Path

folder = Path(os.environ["FAKE_T3_FOLDER"])
tool, arguments = sys.argv[2], json.loads(sys.argv[3])
with (folder / "calls.jsonl").open("a", encoding="utf-8") as calls:
    calls.write(json.dumps({{"tool": tool, "arguments": arguments}}) + "\\n")
answer = json.loads((folder / "answers.json").read_text(encoding="utf-8")).get(tool, {{}})
if answer.get("exit"):
    print(answer.get("stderr", "the fake T3 failed"), file=sys.stderr)
    sys.exit(answer["exit"])
print(json.dumps(answer))
"""


class AcceptWorkerCase(unittest.TestCase):
    """A temporary git repo with the fake bd's beads and one epic, a temporary jidoka home that holds the routes of an
    Antigravity host, and T3 faked behind a fake `acp-mcp-call` that records each tool call and answers it from a file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "shop"
        fixture.init_repo(self.repo)
        (self.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Start")
        fixture.run(["git", "branch", "-M", "main"], self.repo)
        self.bin = self.root / "bin"
        self.fake_bd = str(fixture.add_fake_beads(self.repo, self.bin))
        self.home = self.root / "jidoka-home"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        (self.home / "settings.json").write_text(json.dumps({"antigravity_routes": {"standard": NEON}}),
                                                 encoding="utf-8")
        self.t3 = self.root / "t3"
        self.t3.mkdir()
        self.acp = fixture.write_executable(self.t3 / "acp-node", FAKE_ACP_MCP_CALL)
        self.answer({"t3_thread_launch": {"threadId": WORKER_THREAD}})
        self.epic = json.loads(fixture.run([self.fake_bd, "create", "--title", "Take card payments", "--type=epic",
                                            "--json"], self.repo))["id"]
        self.prompt = self.repo / ".scratch" / "guide-prompt.md"
        self.prompt.parent.mkdir()
        self.prompt.write_text("Write the review guide.\n", encoding="utf-8")

    def answer(self, answers: dict) -> None:
        (self.t3 / "answers.json").write_text(json.dumps(answers), encoding="utf-8")

    def calls(self) -> list[dict]:
        path = self.t3 / "calls.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def accept_worker(self, now: int, *args: str, thread: str | None = MANAGER_THREAD) -> subprocess.CompletedProcess:
        environment = {key: value for key, value in os.environ.items() if key not in AMBIENT}
        environment.update({"PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
                            "BEADS_ACTOR": "Pat Human", "T3_ACP_MCP_NODE": str(self.acp),
                            "FAKE_T3_FOLDER": str(self.t3), "JIDOKA_NOW": str(now)})
        if thread is not None:
            environment["T3CODE_THREAD_ID"] = thread
        return fixture.run_launcher(LAUNCHER, [str(ACCEPT_WORKER), *args], None, environment, self.repo,
                                    RUN_TIMEOUT_SECONDS)

    def start(self, worker: str = "guide", thread: str | None = MANAGER_THREAD) -> subprocess.CompletedProcess:
        return self.accept_worker(STARTED, "start", "--worker", worker, "--epic", self.epic, "--prompt",
                                  str(self.prompt), "--tier", "standard", "--jidoka-home", str(self.home),
                                  thread=thread)

    def started(self, worker: str = "guide") -> dict:
        done = self.start(worker)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)


class StartingAnAcceptWorkerTests(AcceptWorkerCase):
    def test_launches_a_full_access_thread_in_the_project_checkout_on_the_routes_model_and_thought_level(self):
        self.started()

        (launch,) = self.calls()
        arguments = launch["arguments"]
        self.assertEqual("t3_thread_launch", launch["tool"])
        self.assertEqual({"type": "root"}, arguments["workspaceStrategy"])
        self.assertEqual("full-access", arguments["runtimeMode"])
        self.assertEqual({"instanceId": "antigravity-main", "model": "gemini-4-neon",
                          "options": {"thought_level": "high"}}, arguments["modelSelection"])
        self.assertEqual("Write the review guide.\n", arguments["message"])

    def test_titles_each_worker_lap_and_the_epic_title_without_the_bead_id(self):
        for worker, title in (("guide", "lap · Take card payments · review guide"),
                              ("send-back", "lap · Take card payments · send-back")):
            with self.subTest(worker=worker):
                self.started(worker)

                self.assertEqual(title, self.calls()[-1]["arguments"]["title"])
                self.assertNotIn(self.epic, self.calls()[-1]["arguments"]["title"])

    def test_prints_the_thread_the_deadline_and_the_calls_that_wait_and_report_the_worker(self):
        printed = self.started()

        self.assertEqual(WORKER_THREAD, printed["thread"])
        self.assertEqual(STARTED + WALL_CLOCK_SECONDS, printed["deadline"])
        self.assertEqual(WALL_CLOCK_SECONDS, printed["wall_seconds"])
        for name in ("wait", "report"):
            self.assertIn(f"accept_worker.py {name} --worker guide", printed[name].replace("'", ""))

    def test_writes_no_guard_record_that_would_hold_the_manager_in_the_same_checkout(self):
        self.started()

        self.assertIsNone(lap_guard_record.read_record(self.home, self.repo))
        self.assertFalse((self.home / lap_guard_record.FOLDER).exists())

    def test_a_start_repeated_for_one_prompt_keeps_the_request_id_and_a_new_prompt_changes_it(self):
        self.started()
        self.started()
        self.prompt.write_text("Write it again, shorter.\n", encoding="utf-8")
        self.started()

        first, second, third = (call["arguments"]["clientRequestId"] for call in self.calls())
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_a_worker_started_again_after_it_was_reported_is_a_new_launch(self):
        self.started()
        self.answer({"t3_thread_launch": {"threadId": WORKER_THREAD}, "t3_thread_read": {"items": []}})
        reported = self.accept_worker(STARTED + 60, "report", "--worker", "guide", "--jidoka-home", str(self.home))
        self.assertEqual(0, reported.returncode, reported.stderr)

        self.started()

        launches = [call["arguments"]["clientRequestId"] for call in self.calls() if call["tool"] == "t3_thread_launch"]
        self.assertEqual(2, len(set(launches)), launches)

    def test_the_two_workers_are_named_apart_and_keep_their_state_apart(self):
        self.started("guide")
        self.started("send-back")

        guide, send_back = (call["arguments"]["clientRequestId"] for call in self.calls())
        self.assertNotEqual(guide, send_back)
        for worker in ("guide", "send-back"):
            self.assertTrue((self.repo / ".scratch" / f"accept-{worker}" / "t3-stage.json").is_file())

    def test_a_launch_that_fails_is_tried_once_more_under_the_same_request_id_then_exits_one_naming_the_call(self):
        self.answer({"t3_thread_launch": {"exit": 1, "stderr": "no such project"}})

        done = self.start()

        self.assertEqual(1, done.returncode)
        self.assertIn("t3_thread_launch", done.stderr)
        self.assertIn("no such project", done.stderr)
        first, second = (call["arguments"]["clientRequestId"] for call in self.calls())
        self.assertEqual(first, second)

    def test_refuses_on_a_host_that_starts_workers_as_subagents_and_launches_nothing(self):
        done = self.start(thread=None)

        self.assertEqual(1, done.returncode)
        self.assertIn("Antigravity", done.stderr)
        self.assertEqual([], self.calls())

    def test_refuses_a_tier_whose_route_is_not_an_antigravity_thread_and_launches_nothing(self):
        claude = {"harness": "claude", "model": "sonnet", "version": "5.5", "effort": "high"}
        (self.home / "settings.json").write_text(json.dumps({"antigravity_routes": {"standard": claude}}),
                                                 encoding="utf-8")

        done = self.start()

        self.assertEqual(1, done.returncode)
        self.assertIn("standard", done.stderr)
        self.assertEqual([], self.calls())

    def test_refuses_an_empty_prompt_and_launches_nothing(self):
        self.prompt.write_text("\n", encoding="utf-8")

        done = self.start()

        self.assertEqual(1, done.returncode)
        self.assertIn("no prompt", done.stderr)
        self.assertEqual([], self.calls())


class WaitingForAndReportingAnAcceptWorkerTests(AcceptWorkerCase):
    def wait(self, now: int) -> subprocess.CompletedProcess:
        return self.accept_worker(now, "wait", "--worker", "guide", "--jidoka-home", str(self.home))

    def report(self, now: int) -> subprocess.CompletedProcess:
        return self.accept_worker(now, "report", "--worker", "guide", "--jidoka-home", str(self.home))

    def test_a_step_that_times_out_before_the_deadline_says_running_and_names_the_call_to_wait_again(self):
        started = self.started()
        self.answer({"t3_thread_wait": {"timedOut": True}})

        done = self.wait(STARTED + 120)

        printed = json.loads(done.stdout)
        self.assertEqual(("running", started["wait"]), (printed["state"], printed["next"]))
        self.assertEqual({"threadId": WORKER_THREAD, "timeoutMs": 45_000}, self.calls()[-1]["arguments"])

    def test_a_run_that_finished_says_ended_and_names_the_call_that_reports_the_worker(self):
        started = self.started()
        self.answer({"t3_thread_wait": {"timedOut": False}})

        printed = json.loads(self.wait(STARTED + 600).stdout)

        self.assertEqual(("ended", started["report"]), (printed["state"], printed["next"]))

    def test_a_worker_past_its_deadline_is_interrupted_and_ends_cut_off(self):
        self.started()

        printed = json.loads(self.wait(STARTED + WALL_CLOCK_SECONDS + 1).stdout)

        self.assertEqual("cut off", printed["state"])
        self.assertEqual("t3_thread_interrupt", self.calls()[-1]["tool"])
        self.assertEqual(WORKER_THREAD, self.calls()[-1]["arguments"]["threadId"])

    def test_the_report_reads_the_last_reply_archives_the_thread_and_never_deletes_it(self):
        self.started()
        self.answer({"t3_thread_read": {"items": [
            {"position": 1, "type": "assistant_message", "text": "Working."},
            {"position": 3, "type": "assistant_message", "text": '{"outcome": "done"}'}]}})

        done = self.report(STARTED + 90)

        self.assertEqual({"thread": WORKER_THREAD, "cut_off": False, "reply": '{"outcome": "done"}'},
                         json.loads(done.stdout))
        tools = [call["tool"] for call in self.calls()]
        self.assertEqual(["t3_thread_launch", "t3_thread_read", "t3_thread_organize"], tools)
        self.assertEqual({"threadId": WORKER_THREAD, "action": "archive"}, self.calls()[-1]["arguments"])

    def test_the_report_of_a_worker_that_was_cut_off_says_so(self):
        self.started()
        self.wait(STARTED + WALL_CLOCK_SECONDS + 1)

        printed = json.loads(self.report(STARTED + WALL_CLOCK_SECONDS + 2).stdout)

        self.assertTrue(printed["cut_off"])

    def test_a_wait_for_a_worker_that_never_started_exits_one_naming_the_missing_state(self):
        done = self.wait(STARTED)

        self.assertEqual(1, done.returncode)
        self.assertIn("t3-stage.json", done.stderr)


if __name__ == "__main__":
    unittest.main()
