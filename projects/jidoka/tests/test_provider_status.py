import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fake_t3_server as t3_server  # noqa: E402
import jidoka_fixture as fixture  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
STATUS = PLUGIN / "scripts" / "provider_status.py"
SETUP = PLUGIN / "scripts" / "setup.py"

RUN_TIMEOUT_SECONDS = 120
CLOSE_WAIT_SECONDS = 10
SYSTEM_PATH = (str(Path(os.environ["SystemRoot"]) / "System32") if fixture.WINDOWS
               else f"/usr/bin{os.pathsep}/bin")
T3_VARIABLES = ["T3CODE_CLI_PATH", "T3CODE_THREAD_ID"]
TOKEN = "t3-read-token-0123456789abcdef"
SIGNED_IN = [t3_server.provider("codex", "authenticated"), t3_server.provider("antigravity", "authenticated")]
SIGNED_OUT = [t3_server.provider("codex", "authenticated"), t3_server.provider("antigravity", "unauthenticated")]


class StatusCase(unittest.TestCase):
    """The status command run as a process against a temp jidoka home, a fake t3 CLI and a fake T3 server."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.bin = cls.root / "bin"
        cls.bin.mkdir()
        cls.count = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        type(self).count += 1
        self.home = self.root / f"home-{self.count}"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")

    def save_token(self) -> None:
        (self.home / "t3-token").write_text(TOKEN + "\n", encoding="utf-8")

    def server(self, providers: list[dict]) -> t3_server.FakeT3Server:
        """A T3 that issues a ticket for the token and answers the config call with the providers."""
        return self.server_that(providers, t3_server.ANSWER)

    def server_that(self, providers: list[dict], on_request: str) -> t3_server.FakeT3Server:
        """A T3 that issues a ticket for the token and, when the config call comes, does what `on_request` names."""
        return t3_server.FakeT3Server(TOKEN, providers, on_request, False)

    def server_refusing_the_ticket(self, providers: list[dict]) -> t3_server.FakeT3Server:
        return t3_server.FakeT3Server(TOKEN, providers, t3_server.ANSWER, True)

    def environment(self) -> dict[str, str]:
        """The caller's environment without the variables that name a real T3, so no test reaches one."""
        env = {name: value for name, value in os.environ.items() if name not in T3_VARIABLES}
        env.update({"PATH": f"{self.bin}{os.pathsep}{SYSTEM_PATH}", "JIDOKA_HOME": str(self.home)})
        return env

    def status(self, port: int, *extra: str) -> subprocess.CompletedProcess:
        env = self.environment()
        done = fixture.run_launcher(LAUNCHER, [str(STATUS), "antigravity", "--port", str(port), *extra], None, env,
                                    self.root, RUN_TIMEOUT_SECONDS)
        self.assertNotIn(TOKEN, done.stdout + done.stderr)
        self.assertNotIn(t3_server.TICKET, done.stdout + done.stderr)
        return done

    def closed_port(self) -> int:
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            return holder.getsockname()[1]

    def assert_no_status(self, done: subprocess.CompletedProcess) -> None:
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertIn("no status", done.stderr)
        self.assertEqual("", done.stdout)


class ReadingTheStatusTests(StatusCase):
    def test_a_signed_in_antigravity_account_is_reported_signed_in(self):
        self.save_token()
        with self.server(SIGNED_IN) as server:
            done = self.status(server.port)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("The Antigravity account is signed in.", done.stdout.strip())

    def test_a_signed_out_antigravity_account_is_reported_signed_out(self):
        self.save_token()
        with self.server(SIGNED_OUT) as server:
            done = self.status(server.port)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("The Antigravity account is signed out.", done.stdout.strip())

    def test_only_the_antigravity_provider_decides_the_status(self):
        self.save_token()
        providers = [t3_server.provider("codex", "unauthenticated"), t3_server.provider("antigravity", "authenticated")]
        with self.server(providers) as server:
            done = self.status(server.port)

        self.assertEqual("The Antigravity account is signed in.", done.stdout.strip())

    def test_the_token_goes_to_the_ticket_route_as_a_bearer_and_the_ticket_opens_the_socket(self):
        self.save_token()
        with self.server(SIGNED_IN) as server:
            self.status(server.port)

        self.assertEqual([f"Bearer {TOKEN}"], server.bearers)
        self.assertEqual(f"/ws?orchestrationProtocol=2&wsTicket={t3_server.TICKET}", server.paths[-1])

    def test_the_client_masks_its_frames_answers_a_ping_and_closes_the_socket(self):
        self.save_token()
        with self.server_that(SIGNED_IN, t3_server.PING_FIRST) as server:
            done = self.status(server.port)
            self.assertTrue(server.closed.wait(CLOSE_WAIT_SECONDS))

        self.assertEqual("The Antigravity account is signed in.", done.stdout.strip())
        self.assertTrue(all(masked for _, masked, _ in server.client_frames), server.client_frames)
        self.assertEqual([0x1, 0xA, 0x8], [opcode for opcode, _, _ in server.client_frames])
        [request] = [json.loads(payload) for opcode, _, payload in server.client_frames if opcode == 0x1]
        self.assertEqual("server.getConfig", request["tag"])
        [pong] = [payload for opcode, _, payload in server.client_frames if opcode == 0xA]
        self.assertEqual(b"are you there", pong)


class NoStatusTests(StatusCase):
    def test_a_refused_ticket_reports_no_status(self):
        self.save_token()
        with self.server_refusing_the_ticket(SIGNED_IN) as server:
            done = self.status(server.port)

        self.assert_no_status(done)

    def test_a_socket_that_t3_closes_reports_no_status(self):
        self.save_token()
        with self.server_that(SIGNED_IN, t3_server.CLOSE) as server:
            done = self.status(server.port)

        self.assert_no_status(done)

    def test_a_reply_that_is_not_json_reports_no_status(self):
        self.save_token()
        with self.server_that(SIGNED_IN, t3_server.GARBAGE) as server:
            done = self.status(server.port)

        self.assert_no_status(done)

    def test_a_reply_of_an_unknown_shape_reports_no_status(self):
        self.save_token()
        with self.server_that(SIGNED_IN, t3_server.UNKNOWN_SHAPE) as server:
            done = self.status(server.port)

        self.assert_no_status(done)

    def test_a_call_that_failed_reports_no_status(self):
        self.save_token()
        with self.server_that(SIGNED_IN, t3_server.FAILURE) as server:
            done = self.status(server.port)

        self.assert_no_status(done)

    def test_a_config_with_no_antigravity_provider_reports_no_status(self):
        self.save_token()
        with self.server([t3_server.provider("codex", "authenticated")]) as server:
            done = self.status(server.port)

        self.assert_no_status(done)

    def test_an_auth_state_that_is_neither_signed_in_nor_signed_out_reports_no_status(self):
        self.save_token()
        with self.server([t3_server.provider("antigravity", "unknown")]) as server:
            done = self.status(server.port)

        self.assert_no_status(done)

    def test_a_t3_that_never_answers_reports_no_status_when_the_time_is_up(self):
        self.save_token()
        with self.server_that(SIGNED_IN, t3_server.SILENCE) as server:
            began = time.monotonic()
            done = self.status(server.port, "--timeout", "2")

        self.assert_no_status(done)
        self.assertLess(time.monotonic() - began, 60)

    def test_no_server_on_the_port_reports_no_status(self):
        self.save_token()

        self.assert_no_status(self.status(self.closed_port()))

    def test_no_token_reports_no_status_and_asks_nothing_of_t3(self):
        with self.server(SIGNED_IN) as server:
            done = self.status(server.port)

        self.assert_no_status(done)
        self.assertIn("setup", done.stderr)
        self.assertEqual([], server.paths)


class TheHumanConfirmsTheTokenAndReadsTheStatusTests(StatusCase):
    def test_after_setup_issues_the_token_the_status_command_says_the_account_is_signed_in(self):
        fixture.write_executable(self.bin / "t3", f"#!/bin/sh\nprintf '%s\\n' '{TOKEN}'\n")
        issued = fixture.run_launcher(LAUNCHER, [str(SETUP), "issue-token", "--confirmed"], None,
                                      self.environment(), self.root, RUN_TIMEOUT_SECONDS)
        self.assertEqual(0, issued.returncode, issued.stderr)

        with self.server(SIGNED_IN) as server:
            done = self.status(server.port)

        self.assertEqual("The Antigravity account is signed in.", done.stdout.strip())


if __name__ == "__main__":
    unittest.main()
