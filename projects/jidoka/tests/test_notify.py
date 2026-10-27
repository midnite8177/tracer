import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
NOTIFY = PLUGIN / "scripts" / "notify.py"
PARK = PLUGIN / "scripts" / "park.py"

RUN_TIMEOUT_SECONDS = 120
HUMAN = "Pat Human"
USER_KEY = "u-pat"
APP_TOKEN = "a-jidoka"
UI_URL = "http://board.example:5099"
FOUND = "Should the till round to five cents?"


class PushoverStandIn(http.server.ThreadingHTTPServer):
    """A local server that answers every POST with Pushover's success and keeps what it was sent."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), self.Handler)
        self.received: list[dict[str, str]] = []
        threading.Thread(target=self.serve_forever, daemon=True).start()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
            self.server.received.append({key: values[0] for key, values in urllib.parse.parse_qs(body).items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":1}')

        def log_message(self, *args: object) -> None:
            return

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/1/messages.json"


class NotifyCase(unittest.TestCase):
    """A temporary git repo with the fake bd's beads, a temporary jidoka home and a Pushover stand-in."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "shop"
        fixture.init_repo(self.repo)
        fixture.run(["git", "config", "user.name", HUMAN], self.repo)
        (self.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Start")
        fixture.run(["git", "branch", "-M", "main"], self.repo)
        self.bin = self.root / "bin"
        self.fake_bd = str(fixture.add_fake_beads(self.repo, self.bin))
        self.home = self.root / "jidoka-home"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        self.pushover = PushoverStandIn()
        self.addCleanup(self.pushover.server_close)
        self.addCleanup(self.pushover.shutdown)

    def configure_pushover(self, **changes: str) -> None:
        keys = {"user_key": USER_KEY, "app_token": APP_TOKEN, "ui_url": UI_URL, "api_url": self.pushover.url}
        (self.home / "pushover.json").write_text(json.dumps({**keys, **changes}), encoding="utf-8")

    def script(self, script: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(LAUNCHER), str(script), *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS, cwd=self.repo,
                              env={**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
                                   "BEADS_ACTOR": HUMAN})

    def notify(self, *args: str) -> subprocess.CompletedProcess:
        return self.script(NOTIFY, *args)

    def bd(self, *args: str) -> str:
        return fixture.run([self.fake_bd, *args], self.repo)

    def create(self, title: str, *flags: str) -> str:
        return json.loads(self.bd("create", "--title", title, *flags, "--json"))["id"]

    def new_epic(self, *labels: str) -> str:
        epic = self.create("Take card payments", "--type=epic")
        for label in labels:
            self.bd("label", "add", epic, label)
        return epic

    def new_task(self, epic: str, title: str = "Read the card") -> str:
        return self.create(title, "--type=task", "--parent", epic)

    def shown(self, bead: str) -> dict:
        return json.loads(self.bd("show", bead, "--json"))[0]

    def park_with_question(self, task: str) -> None:
        scratch = self.root / f"scratch-{task}"
        scratch.mkdir(exist_ok=True)
        report = {"found": FOUND, "options": [{"name": "yes", "confidence": 60}, {"name": "no", "confidence": 40}],
                  "recommended": "yes"}
        (scratch / "question.json").write_text(json.dumps(report), encoding="utf-8")
        done = self.script(PARK, "question", task, "--scratch", str(scratch), "--worktree",
                           str(self.repo / ".worktrees" / f"lap-{task}"), "--branch", f"lap/{task}", "--tries", "0")
        self.assertEqual(0, done.returncode, done.stderr)

    def unpark(self, task: str) -> None:
        self.bd("label", "remove", task, "human")

    def sent_to_pushover(self) -> list[dict[str, str]]:
        return self.pushover.received

    def link_to(self, bead: str) -> str:
        project = urllib.parse.quote(str(self.repo), safe="")
        return f"{UI_URL}/bead/{urllib.parse.quote(bead, safe='')}?project={project}"

    def notified(self, epic: str) -> dict:
        return json.loads(self.shown(epic)["metadata"]["notification"])


class ParkedTaskTests(NotifyCase):
    def test_a_parked_task_sends_one_pushover_message_that_links_to_the_task(self):
        self.configure_pushover()
        epic = self.new_epic()
        task = self.new_task(epic)
        self.park_with_question(task)

        done = self.notify("task-parked", task)

        self.assertEqual(0, done.returncode, done.stderr)
        [message] = self.sent_to_pushover()
        self.assertEqual((USER_KEY, APP_TOKEN), (message["user"], message["token"]))
        self.assertEqual("Task parked: Read the card", message["title"])
        self.assertIn(FOUND, message["message"])
        self.assertEqual(self.link_to(task), message["url"])

    def test_the_same_park_is_not_announced_twice(self):
        self.configure_pushover()
        epic = self.new_epic()
        task = self.new_task(epic)
        self.park_with_question(task)

        first = self.notify("task-parked", task)
        second = self.notify("task-parked", task)

        self.assertEqual(0, second.returncode, second.stderr)
        self.assertIn(task, first.stdout)
        self.assertEqual("", second.stdout)
        self.assertIn("already sent", second.stderr)
        self.assertEqual(1, len(self.sent_to_pushover()))

    def test_a_later_park_of_the_same_task_is_announced_again(self):
        self.configure_pushover()
        epic = self.new_epic()
        task = self.new_task(epic)
        self.park_with_question(task)
        self.notify("task-parked", task)
        self.unpark(task)
        self.park_with_question(task)

        self.notify("task-parked", task)

        self.assertEqual(2, len(self.sent_to_pushover()))

    def test_the_epics_notification_key_records_the_event_on_the_task(self):
        epic = self.new_epic()
        task = self.new_task(epic)
        self.park_with_question(task)

        self.notify("task-parked", task)

        self.assertEqual([f"task-parked:{task}"], list(self.notified(epic)))

    def test_the_host_line_names_the_event_and_the_bead(self):
        epic = self.new_epic()
        task = self.new_task(epic)
        self.park_with_question(task)

        done = self.notify("task-parked", task)

        self.assertEqual(f"jidoka: Task parked: Read the card. {FOUND} ({task})\n", done.stdout)

    def test_a_task_that_is_not_parked_sends_nothing(self):
        self.configure_pushover()
        epic = self.new_epic()
        task = self.new_task(epic)

        done = self.notify("task-parked", task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)
        self.assertIn("is not parked", done.stderr)
        self.assertEqual([], self.sent_to_pushover())
        self.assertNotIn("notification", self.shown(epic).get("metadata") or {})


class PushoverConfigurationTests(NotifyCase):
    def test_no_pushover_message_goes_out_where_the_machine_has_no_keys(self):
        epic = self.new_epic()
        task = self.new_task(epic)
        self.park_with_question(task)

        done = self.notify("task-parked", task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Task parked", done.stdout)
        self.assertEqual([], self.sent_to_pushover())

    def test_a_file_with_only_one_key_means_no_pushover(self):
        self.configure_pushover(app_token="")
        epic = self.new_epic()
        task = self.new_task(epic)
        self.park_with_question(task)

        done = self.notify("task-parked", task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], self.sent_to_pushover())

    def test_a_pushover_that_cannot_be_reached_is_a_warning_and_the_notification_still_counts(self):
        self.configure_pushover(api_url="http://127.0.0.1:1/1/messages.json")
        epic = self.new_epic()
        task = self.new_task(epic)
        self.park_with_question(task)

        done = self.notify("task-parked", task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Pushover did not take the message", done.stderr)
        self.assertIn("Task parked", done.stdout)
        self.assertEqual([f"task-parked:{task}"], list(self.notified(epic)))

    def test_the_link_uses_the_default_address_of_jidoka_ui_when_the_file_names_none(self):
        self.configure_pushover(ui_url="")
        epic = self.new_epic()
        task = self.new_task(epic)
        self.park_with_question(task)

        self.notify("task-parked", task)

        [message] = self.sent_to_pushover()
        self.assertTrue(message["url"].startswith("http://localhost:5099/bead/"), message["url"])


class EpicEventTests(NotifyCase):
    def test_a_parked_epic_is_announced_once_and_links_to_the_epic(self):
        self.configure_pushover()
        epic = self.new_epic("factory")
        self.bd("label", "add", epic, "human")

        self.notify("epic-parked", epic)
        self.notify("epic-parked", epic)

        [message] = self.sent_to_pushover()
        self.assertEqual("Epic parked: Take card payments", message["title"])
        self.assertEqual(self.link_to(epic), message["url"])

    def test_an_epic_at_the_acceptance_gate_is_not_announced_as_parked(self):
        self.configure_pushover()
        epic = self.new_epic("factory", "human")
        self.bd("update", epic, "--set-metadata", "gate.state=waiting")

        done = self.notify("epic-parked", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], self.sent_to_pushover())

    def test_only_parked_tasks_left_links_to_the_first_parked_task(self):
        self.configure_pushover()
        epic = self.new_epic("factory")
        first, second = self.new_task(epic, "Read the card"), self.new_task(epic, "Print the receipt")
        self.park_with_question(first)
        self.park_with_question(second)

        self.notify("only-parked-left", epic)
        self.notify("only-parked-left", epic)

        [message] = self.sent_to_pushover()
        self.assertEqual("Only parked tasks left: Take card payments", message["title"])
        self.assertEqual(self.link_to(min(first, second)), message["url"])
        self.assertIn(first, message["message"])
        self.assertIn(second, message["message"])

    def test_a_task_that_is_not_parked_means_not_only_parked_tasks_left(self):
        self.configure_pushover()
        epic = self.new_epic("factory")
        parked, working = self.new_task(epic), self.new_task(epic, "Print the receipt")
        self.park_with_question(parked)
        self.bd("update", working, "--status=in_progress")

        done = self.notify("only-parked-left", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], self.sent_to_pushover())

    def test_the_epic_at_the_acceptance_gate_is_announced_once(self):
        self.configure_pushover()
        epic = self.new_epic("factory", "human")
        self.bd("update", epic, "--set-metadata", "gate.state=waiting", "--set-metadata", "validation.head=abc123")

        self.notify("acceptance-gate", epic)
        self.notify("acceptance-gate", epic)

        [message] = self.sent_to_pushover()
        self.assertEqual("Ready for acceptance: Take card payments", message["title"])
        self.assertEqual(self.link_to(epic), message["url"])
        self.assertEqual([f"acceptance-gate:{epic}"], list(self.notified(epic)))

    def test_an_epic_that_is_not_at_the_gate_sends_no_gate_notification(self):
        self.configure_pushover()
        epic = self.new_epic("factory")

        done = self.notify("acceptance-gate", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], self.sent_to_pushover())

    def test_a_stopped_factory_with_work_left_is_announced_once(self):
        self.configure_pushover()
        epic = self.new_epic("factory")
        task = self.new_task(epic)

        self.notify("factory-stopped", epic)
        self.notify("factory-stopped", epic)

        [message] = self.sent_to_pushover()
        self.assertEqual("Factory stopped: Take card payments", message["title"])
        self.assertIn(task, message["message"])
        self.assertEqual(self.link_to(epic), message["url"])

    def test_a_stopped_factory_with_no_work_left_sends_nothing(self):
        self.configure_pushover()
        epic = self.new_epic("factory")
        task = self.new_task(epic)
        self.bd("close", task)

        done = self.notify("factory-stopped", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], self.sent_to_pushover())

    def test_a_bead_that_is_not_an_epic_is_refused_for_an_epic_event(self):
        epic = self.new_epic("factory")
        task = self.new_task(epic)

        done = self.notify("acceptance-gate", task)

        self.assertEqual(1, done.returncode)
        self.assertIn("not an epic", done.stderr)


class PermissionPromptTests(NotifyCase):
    def test_a_host_permission_prompt_while_an_epic_runs_names_the_running_epic(self):
        self.configure_pushover()
        self.new_epic()
        running = self.new_epic("factory")

        done = self.notify("permission-prompt")

        self.assertEqual(0, done.returncode, done.stderr)
        [message] = self.sent_to_pushover()
        self.assertEqual("Permission prompt: Take card payments", message["title"])
        self.assertEqual(self.link_to(running), message["url"])
        self.assertIn(running, done.stdout)

    def test_each_permission_prompt_is_announced(self):
        self.configure_pushover()
        self.new_epic("factory")

        self.notify("permission-prompt")
        self.notify("permission-prompt")

        self.assertEqual(2, len(self.sent_to_pushover()))

    def test_a_permission_prompt_with_no_epic_running_sends_nothing(self):
        self.configure_pushover()
        self.new_epic()
        self.new_epic("factory", "human")

        done = self.notify("permission-prompt")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)
        self.assertIn("no epic is running", done.stderr)
        self.assertEqual([], self.sent_to_pushover())


class UsageTests(NotifyCase):
    def test_an_event_that_needs_a_bead_refuses_without_one(self):
        done = self.notify("task-parked")

        self.assertEqual(1, done.returncode)
        self.assertIn("needs the bead", done.stderr)


if __name__ == "__main__":
    unittest.main()
