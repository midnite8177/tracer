import http.server
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
UI = PLUGIN / "scripts" / "ui.py"

RUN_TIMEOUT_SECONDS = 60
WAIT_SECONDS = "20"
SHORT_WAIT_SECONDS = "1"
ANSWER_TIMEOUT_SECONDS = 2

EXITS_AT_ONCE = "\n".join([
    f"#!{sys.executable}",
    "import sys",
    "print('Unhandled exception. Failed to bind to address: address already in use')",
    "sys.exit(134)",
    ""])

NEVER_ANSWERS = "\n".join([
    f"#!{sys.executable}",
    "import time",
    "time.sleep(600)",
    ""])


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def answers(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/", timeout=ANSWER_TIMEOUT_SECONDS):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


class QuietHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"already here\n")

    def log_message(self, format, *args):
        pass


class JidokaUiStartTests(unittest.TestCase):
    """A temporary jidoka home whose machine settings record a published jidoka-ui, and a fake dotnet that runs it,
    with the script run as a process through the launcher."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self.root = root
        self.home = root / "jidoka-home"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        self.app_folder = self.home / "ui" / "published"
        self.app_folder.mkdir(parents=True)
        self.app = self.app_folder / "JidokaUi.Web.dll"
        self.app.write_text("a published app\n", encoding="utf-8")
        self.log = root / "dotnet-calls.log"
        self.dotnet = root / "bin" / "dotnet"
        self.dotnet.parent.mkdir()
        fixture.write_dotnet(self.dotnet, self.log)
        self.port = free_port()
        self.record_ui({"dotnet": str(self.dotnet), "app": str(self.app), "port": self.port})
        self.addCleanup(self.end_started_app)

    def record_ui(self, ui: object) -> None:
        settings = {"python": sys.executable, "ui": ui}
        (self.home / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    def env(self) -> dict[str, str]:
        return {"PATH": os.environ.get("PATH", ""), "HOME": str(self.root), "JIDOKA_HOME": str(self.home),
                **fixture.system_variables(os.environ, fixture.WINDOWS)}

    def command(self, wait: str) -> list[str]:
        return fixture.launch_command(LAUNCHER, [str(UI), "start", "--jidoka-home", str(self.home), "--wait", wait])

    def start(self, wait: str) -> subprocess.CompletedProcess:
        return subprocess.run(self.command(wait), capture_output=True, text=True, encoding="utf-8",
                              timeout=RUN_TIMEOUT_SECONDS, env=self.env(), cwd=self.root)

    def printed(self, done: subprocess.CompletedProcess) -> dict:
        return json.loads(done.stdout)

    def runs(self) -> list[dict]:
        return [call for call in fixture.read_log(self.log) if call["argv"][:1] != ["publish"]]

    def started_pid(self) -> int | None:
        record = self.home / "ui" / "jidoka-ui.pid"
        if not record.is_file():
            return None
        return int(record.read_text(encoding="utf-8").strip())

    def end_started_app(self) -> None:
        pid = self.started_pid()
        if pid is None:
            return
        if fixture.WINDOWS:
            fixture.end_process(pid)
            return
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def serve_here(self) -> None:
        server = http.server.HTTPServer(("127.0.0.1", self.port), QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def test_an_address_that_answers_starts_nothing_and_says_it_answers(self):
        self.serve_here()

        done = self.start(WAIT_SECONDS)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({"state": "answering", "address": f"http://localhost:{self.port}", "why": None,
                          "log": None}, self.printed(done))
        self.assertEqual([], self.runs())

    def test_an_address_that_does_not_answer_gets_jidoka_ui_started_and_answering_when_the_script_returns(self):
        done = self.start(WAIT_SECONDS)

        self.assertEqual(0, done.returncode, done.stderr)
        printed = self.printed(done)
        self.assertEqual("started", printed["state"])
        self.assertEqual(f"http://localhost:{self.port}", printed["address"])
        self.assertTrue(answers(self.port))
        [run] = self.runs()
        self.assertEqual([str(self.app), "--port", str(self.port)], run["argv"])

    def test_the_started_app_runs_in_its_published_folder_with_the_jidoka_home_it_was_started_for(self):
        self.start(WAIT_SECONDS)

        [run] = self.runs()
        self.assertEqual(str(self.app_folder), run["cwd"])
        self.assertEqual(str(self.home), run["jidoka_home"])

    @unittest.skipIf(fixture.WINDOWS, "Windows has no sessions")
    def test_the_started_app_outlives_the_script_in_a_session_of_its_own(self):
        self.start(WAIT_SECONDS)

        pid = self.started_pid()
        self.assertIsNotNone(pid)
        self.assertEqual(pid, os.getsid(pid))
        self.assertNotEqual(os.getsid(0), os.getsid(pid))

    def test_the_output_of_the_started_app_goes_to_a_log_in_the_jidoka_home(self):
        done = self.start(WAIT_SECONDS)

        log = self.home / "ui" / "jidoka-ui.log"
        self.assertEqual(str(log), self.printed(done)["log"])
        self.assertIn("listening", log.read_text(encoding="utf-8"))

    def test_two_starts_at_once_start_one_app_and_both_find_it_answering(self):
        first = subprocess.Popen(self.command(WAIT_SECONDS), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding="utf-8", env=self.env(), cwd=self.root)
        second = subprocess.Popen(self.command(WAIT_SECONDS), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8", env=self.env(), cwd=self.root)
        outputs = [process.communicate(timeout=RUN_TIMEOUT_SECONDS) for process in (first, second)]

        self.assertEqual([0, 0], [first.returncode, second.returncode], [error for _, error in outputs])
        self.assertEqual(["answering", "started"], sorted(json.loads(out)["state"] for out, _ in outputs))
        self.assertEqual(1, len(self.runs()))

    def test_an_app_that_exits_before_it_answers_is_down_with_the_end_of_its_log(self):
        fixture.write_executable(self.dotnet, EXITS_AT_ONCE)

        done = self.start(WAIT_SECONDS)

        self.assertEqual(1, done.returncode)
        printed = self.printed(done)
        self.assertEqual("failed", printed["state"])
        self.assertIn("134", printed["why"])
        self.assertIn("address already in use", printed["why"])

    def test_an_app_that_does_not_answer_within_the_wait_is_down_and_named_by_its_process(self):
        fixture.write_executable(self.dotnet, NEVER_ANSWERS)

        done = self.start(SHORT_WAIT_SECONDS)

        self.assertEqual(1, done.returncode)
        printed = self.printed(done)
        self.assertEqual("failed", printed["state"])
        self.assertIn("within 1 s", printed["why"])
        self.assertIn(str(self.started_pid()), printed["why"])

    def test_a_machine_with_no_published_jidoka_ui_starts_nothing_and_says_to_run_the_installer(self):
        (self.home / "settings.json").write_text(json.dumps({"python": sys.executable}), encoding="utf-8")

        done = self.start(WAIT_SECONDS)

        self.assertEqual(1, done.returncode)
        printed = self.printed(done)
        self.assertEqual("not installed", printed["state"])
        self.assertIsNone(printed["address"])
        self.assertIn("install.py", printed["why"])
        self.assertEqual([], self.runs())

    def test_a_record_that_names_no_port_is_no_published_jidoka_ui(self):
        self.record_ui({"dotnet": str(self.dotnet), "app": str(self.app)})

        done = self.start(WAIT_SECONDS)

        self.assertEqual(1, done.returncode)
        self.assertEqual("not installed", self.printed(done)["state"])
        self.assertEqual([], self.runs())

    def test_a_wait_that_is_not_a_positive_number_is_refused(self):
        done = self.start("0")

        self.assertEqual(2, done.returncode)
        self.assertEqual([], self.runs())


if __name__ == "__main__":
    unittest.main()
