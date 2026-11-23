import json
import socket
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fake_t3_server as t3_server  # noqa: E402
from test_beater import PLUGIN, SCHEDULER, BeaterCase  # noqa: E402

STATUS = PLUGIN / "scripts" / "status.py"
THREAD = "thread-of-the-antigravity-manager"
TOKEN = "t3-read-token-0123456789abcdef"
CLAUDE_SESSION = "session-of-a-claude-manager"
GEMINI = "gemini-3-pro"
FLASH = "gemini-3-flash"
MINUTE = timedelta(minutes=1)


def iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def from_now(delta: timedelta) -> datetime:
    return datetime.now(timezone.utc) + delta


def closed_port() -> int:
    """A local port that nothing listens on."""
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        return holder.getsockname()[1]


def two_buckets(checked_at: datetime) -> list[dict]:
    """The Antigravity provider T3 lists for an account whose Gemini Pro and Gemini Flash buckets each have a
    five-hour and a weekly window, and whose Claude and GPT bucket has a monthly one."""
    resets = from_now(timedelta(hours=2))
    weekly = from_now(timedelta(days=3))
    return [t3_server.antigravity_with_usage(iso(checked_at), [
        t3_server.usage_window(f"{GEMINI}-5h", "session", 42, iso(resets), 300),
        t3_server.usage_window(f"{GEMINI}-weekly", "weekly", 18.5, iso(weekly), 10080),
        t3_server.usage_window(f"{FLASH}-5h", "session", 7, iso(resets), 300),
        t3_server.usage_window(f"{FLASH}-weekly", "weekly", 3, iso(weekly), 10080),
        t3_server.usage_window("claude-gpt-monthly", "monthly", 90, iso(weekly), 43200)])]


class UsageCase(BeaterCase):
    """The scheduler run as a process in an Antigravity thread, against a temp repo, the fake bd, a temp jidoka home
    and a fake T3 server."""

    def setUp(self):
        super().setUp()
        (self.home / "t3-token").write_text(TOKEN + "\n", encoding="utf-8")

    @property
    def usage_file(self) -> Path:
        return self.home / "usage" / "antigravity.json"

    def server(self, providers: list[dict], on_request: str = t3_server.ANSWER) -> t3_server.FakeT3Server:
        return t3_server.FakeT3Server(TOKEN, providers, on_request, False)

    def schedule(self, port: int, **variables: str) -> subprocess.CompletedProcess:
        """One call of the scheduler from the Antigravity thread, with T3 at the port, that must succeed."""
        done = self.call({"T3CODE_THREAD_ID": THREAD, "JIDOKA_T3_PORT": str(port), **variables}, SCHEDULER, "next",
                         self.epic)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn(TOKEN, done.stdout + done.stderr)
        self.assertNotIn(t3_server.TICKET, done.stdout + done.stderr)
        return done

    def assert_no_reading_because(self, done: subprocess.CompletedProcess, cause: str) -> None:
        self.assertFalse(self.usage_file.exists())
        self.assertIn("scheduler: no Antigravity usage reading: ", done.stderr)
        self.assertIn(cause, done.stderr)
        self.assertNotEqual([], json.loads(done.stdout)["actions"])


class AGoodReadingTests(UsageCase):
    def test_a_good_reading_writes_the_session_and_weekly_windows_of_each_bucket(self):
        checked_at = from_now(-2 * MINUTE)
        with self.server(two_buckets(checked_at)) as server:
            done = self.schedule(server.port)

        reading = json.loads(self.usage_file.read_text(encoding="utf-8"))
        self.assertEqual(int(checked_at.timestamp()), reading["checkedAt"])
        self.assertEqual([FLASH, GEMINI], sorted(reading["buckets"]))
        session = reading["buckets"][GEMINI]["session"]
        self.assertEqual((f"{GEMINI}-5h", 42, 300), (session["id"], session["usedPercent"],
                                                      session["windowDurationMins"]))
        self.assertAlmostEqual(from_now(timedelta(hours=2)).timestamp(), session["resetsAt"], delta=120)
        weekly = reading["buckets"][GEMINI]["weekly"]
        self.assertEqual((f"{GEMINI}-weekly", 18.5, 10080), (weekly["id"], weekly["usedPercent"],
                                                              weekly["windowDurationMins"]))
        self.assertEqual((7, 3), (reading["buckets"][FLASH]["session"]["usedPercent"],
                                  reading["buckets"][FLASH]["weekly"]["usedPercent"]))
        self.assertNotIn("Antigravity usage", done.stderr)

    def test_a_window_that_is_neither_a_session_nor_a_weekly_one_is_left_out(self):
        with self.server(two_buckets(from_now(-MINUTE))) as server:
            self.schedule(server.port)

        self.assertNotIn("claude-gpt", json.loads(self.usage_file.read_text(encoding="utf-8"))["buckets"])

    def test_the_token_and_the_ticket_are_in_no_file(self):
        with self.server(two_buckets(from_now(-MINUTE))) as server:
            self.schedule(server.port)

        written = "".join(path.read_text(encoding="utf-8") for path in self.home.rglob("*") if path.is_file()
                          and path.name != "t3-token" and path.suffix in (".json", ".log", ""))
        self.assertNotIn(TOKEN, written)
        self.assertNotIn(t3_server.TICKET, written)

    def test_a_host_that_exports_a_session_asks_t3_nothing_and_writes_no_reading(self):
        with self.server(two_buckets(from_now(-MINUTE))) as server:
            self.schedule(server.port, JIDOKA_SESSION_ID=CLAUDE_SESSION)

        self.assertEqual([], server.paths)
        self.assertFalse(self.usage_file.exists())


class NoReadingTests(UsageCase):
    def test_a_refused_ticket_writes_no_reading_and_logs_the_refusal(self):
        with t3_server.FakeT3Server(TOKEN, two_buckets(from_now(-MINUTE)), t3_server.ANSWER, True) as server:
            done = self.schedule(server.port)

        self.assert_no_reading_because(done, "T3 refused the token with 401")

    def test_a_socket_that_t3_closes_writes_no_reading_and_logs_it(self):
        with self.server(two_buckets(from_now(-MINUTE)), t3_server.CLOSE) as server:
            done = self.schedule(server.port)

        self.assert_no_reading_because(done, "T3 closed the socket")

    def test_a_reply_of_an_unknown_shape_writes_no_reading_and_logs_it(self):
        with self.server(two_buckets(from_now(-MINUTE)), t3_server.UNKNOWN_SHAPE) as server:
            done = self.schedule(server.port)

        self.assert_no_reading_because(done, "T3 sent a reply of an unknown shape")

    def test_a_t3_that_is_not_running_writes_no_reading_and_logs_it(self):
        done = self.schedule(closed_port())

        self.assert_no_reading_because(done, "T3 gave no ticket")

    def test_no_token_writes_no_reading_and_asks_t3_nothing(self):
        (self.home / "t3-token").unlink()
        with self.server(two_buckets(from_now(-MINUTE))) as server:
            done = self.schedule(server.port)

        self.assert_no_reading_because(done, "run /jidoka-setup")
        self.assertEqual([], server.paths)

    def test_a_checked_at_past_ten_minutes_counts_as_no_reading(self):
        with self.server(two_buckets(from_now(-11 * MINUTE))) as server:
            done = self.schedule(server.port)

        self.assert_no_reading_because(done, "T3 last checked the Antigravity quota 11 minutes ago")

    def test_a_checked_at_just_inside_ten_minutes_is_a_reading(self):
        with self.server(two_buckets(from_now(-9 * MINUTE))) as server:
            self.schedule(server.port)

        self.assertTrue(self.usage_file.exists())

    def test_a_provider_with_no_usage_limits_writes_no_reading_and_logs_it(self):
        with self.server([t3_server.provider("antigravity", "authenticated")]) as server:
            done = self.schedule(server.port)

        self.assert_no_reading_because(done, "T3 holds no usage limits")

    def test_usage_that_t3_calls_unavailable_writes_no_reading_and_logs_it(self):
        unavailable = {**t3_server.provider("antigravity", "authenticated"),
                       "usageLimits": {"checkedAt": iso(from_now(-MINUTE)), "windows": [],
                                       "unavailable": {"reason": "unsupported"}}}
        with self.server([unavailable]) as server:
            done = self.schedule(server.port)

        self.assert_no_reading_because(done, "T3 says the Antigravity usage is unavailable")

    def test_a_failed_call_removes_the_reading_an_earlier_call_wrote(self):
        with self.server(two_buckets(from_now(-MINUTE))) as server:
            self.schedule(server.port)
        self.assertTrue(self.usage_file.exists())

        with self.server(two_buckets(from_now(-MINUTE)), t3_server.CLOSE) as server:
            self.schedule(server.port)

        self.assertFalse(self.usage_file.exists())


class StatusShowsTheReadingTests(UsageCase):
    def status(self) -> str:
        done = self.call({}, STATUS)
        self.assertEqual(0, done.returncode, done.stderr)
        return done.stdout

    def test_status_shows_the_five_hour_and_weekly_use_of_each_bucket(self):
        with self.server(two_buckets(from_now(-2 * MINUTE))) as server:
            self.schedule(server.port)

        lines = self.status().splitlines()

        [heading] = [line for line in lines if line.startswith("Antigravity usage")]
        self.assertIn("checked 2m ago", heading)
        [gemini] = [line for line in lines if line.strip().startswith(GEMINI)]
        self.assertRegex(gemini, r"five-hour 42% used, resets in 1h5\dm; weekly 18\.5% used, resets in 71h5\dm")
        [flash] = [line for line in lines if line.strip().startswith(FLASH)]
        self.assertRegex(flash, r"five-hour 7% used, resets in 1h5\dm; weekly 3% used, resets in 71h5\dm")

    def test_status_shows_no_quota_when_the_reading_is_older_than_ten_minutes(self):
        with self.server(two_buckets(from_now(-MINUTE))) as server:
            self.schedule(server.port)
        reading = json.loads(self.usage_file.read_text(encoding="utf-8"))
        reading["checkedAt"] -= 11 * 60
        self.usage_file.write_text(json.dumps(reading), encoding="utf-8")

        self.assertNotIn("Antigravity usage", self.status())

    def test_status_shows_no_quota_when_the_scheduler_left_no_reading(self):
        self.assertNotIn("Antigravity usage", self.status())


if __name__ == "__main__":
    unittest.main()
