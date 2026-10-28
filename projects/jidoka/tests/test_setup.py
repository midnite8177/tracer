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
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
SETUP = PLUGIN / "scripts" / "setup.py"

RUN_TIMEOUT_SECONDS = 120
SYSTEM_PATH = f"/usr/bin{os.pathsep}/bin"
KEY_VARIABLES = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY"]
CODEX = {"harness": "codex", "model": None, "version": None, "effort": None}
NATIVE_OPUS = {"harness": "claude", "model": "opus", "version": "5.5", "effort": "high"}
SETTINGS_FROM_THE_INSTALLER = {
    "python": "/opt/python3",
    "config_dirs": ["/home/jeff/.claude"],
    "routes": {"deep": {"harness": "claude", "model": "opus", "version": "5.5", "effort": "low"}},
    "source_repo": "/home/jeff/tracer",
}


class SetupCase(unittest.TestCase):
    """The shop repo, a PATH of the fake bd and the system tools alone, and a jidoka home of its own for each test,
    so a test decides which harnesses and keys the machine has."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.repo = cls.root / "shop"
        fixture.init_repo(cls.repo)
        (cls.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(cls.repo, "Start")
        cls.bin = cls.root / "bin"
        fixture.add_fake_beads(cls.repo, cls.bin)
        cls.count = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        type(self).count += 1
        self.home = self.root / f"home-{self.count}"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        self.keys: dict[str, str] = {}

    def with_codex(self) -> None:
        fixture.write_executable(self.bin / "codex", "#!/bin/sh\nexit 0\n")

    def without_codex(self) -> None:
        (self.bin / "codex").unlink(missing_ok=True)

    def setup_script(self, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
        env = {name: value for name, value in os.environ.items() if name not in KEY_VARIABLES}
        env.update({"PATH": f"{self.bin}{os.pathsep}{SYSTEM_PATH}", "JIDOKA_HOME": str(self.home), **self.keys})
        return subprocess.run([str(LAUNCHER), str(SETUP), *args], input=stdin, capture_output=True, text=True,
                              encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS, env=env, cwd=self.repo)

    def proposal(self) -> dict:
        done = self.setup_script("propose")
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def confirm(self, proposal: dict) -> subprocess.CompletedProcess:
        return self.setup_script("write", "--confirmed", stdin=json.dumps(proposal))

    def settings(self) -> dict:
        return json.loads((self.home / "settings.json").read_text(encoding="utf-8"))

    def record_installer_settings(self) -> bytes:
        (self.home / "settings.json").write_text(json.dumps(SETTINGS_FROM_THE_INSTALLER), encoding="utf-8")
        return (self.home / "settings.json").read_bytes()

    def home_files(self) -> list[str]:
        return sorted(path.name for path in self.home.iterdir())


class ProposeTests(SetupCase):
    def test_without_codex_the_second_tier_is_proposed_on_native_opus(self):
        self.without_codex()

        self.assertEqual(NATIVE_OPUS, self.proposal()["routes"]["second"])

    def test_with_codex_the_second_tier_is_proposed_on_codex(self):
        self.with_codex()

        self.assertEqual(CODEX, self.proposal()["routes"]["second"])

    def test_every_other_tier_is_proposed_on_the_native_route_of_the_tier(self):
        self.without_codex()

        routes = self.proposal()["routes"]

        self.assertEqual(["deep", "light", "local", "second", "standard"], sorted(routes))
        self.assertEqual({"harness": "claude", "model": "haiku", "version": "5.5", "effort": "medium"},
                         routes["light"])
        self.assertEqual({"harness": "claude", "model": "sonnet", "version": "5.5", "effort": "high"},
                         routes["standard"])
        self.assertEqual(NATIVE_OPUS, routes["deep"])

    def test_it_says_which_harnesses_it_found_on_the_machine(self):
        self.with_codex()

        found = self.proposal()["found"]

        self.assertEqual(str(self.bin / "codex"), found["codex"])

    def test_it_reports_no_codex_when_the_machine_has_none(self):
        self.without_codex()

        self.assertIsNone(self.proposal()["found"]["codex"])

    def test_a_subscription_account_gets_a_reserve_and_the_larger_budget_default(self):
        self.without_codex()

        proposal = self.proposal()

        self.assertEqual({"claude": 0.2}, proposal["reserves"])
        self.assertEqual(50, proposal["budget"])

    def test_an_account_on_an_api_key_gets_no_reserve_and_the_smaller_budget_default(self):
        self.without_codex()
        self.keys = {"ANTHROPIC_API_KEY": "sk-test"}

        proposal = self.proposal()

        self.assertEqual({}, proposal["reserves"])
        self.assertEqual(20, proposal["budget"])

    def test_codex_on_a_subscription_gets_no_reserve_because_only_the_claude_account_is_read(self):
        self.with_codex()

        self.assertEqual({"claude": 0.2}, self.proposal()["reserves"])

    def test_codex_on_an_api_key_gets_no_reserve(self):
        self.with_codex()
        self.keys = {"OPENAI_API_KEY": "sk-test"}

        self.assertEqual({"claude": 0.2}, self.proposal()["reserves"])

    def test_the_proposal_shows_what_the_settings_record_now(self):
        self.without_codex()
        self.record_installer_settings()

        recorded = self.proposal()["recorded"]

        self.assertEqual(SETTINGS_FROM_THE_INSTALLER["routes"], recorded["routes"])
        self.assertIsNone(recorded["budget"])
        self.assertIsNone(recorded["reserves"])

    def test_proposing_writes_nothing(self):
        self.without_codex()
        before = self.record_installer_settings()

        self.proposal()

        self.assertEqual(before, (self.home / "settings.json").read_bytes())
        self.assertEqual(["python", "settings.json"], self.home_files())

    def test_proposing_in_a_home_without_settings_creates_no_settings(self):
        self.without_codex()

        self.proposal()

        self.assertEqual(["python"], self.home_files())


class WriteTests(SetupCase):
    CONFIRMED = {
        "routes": {"deep": NATIVE_OPUS, "second": CODEX},
        "budget": 35.5,
        "reserves": {"claude": 0.25},
    }

    def test_confirming_writes_the_routes_the_budget_default_and_the_reserves(self):
        done = self.confirm(self.CONFIRMED)

        self.assertEqual(0, done.returncode, done.stderr)
        settings = self.settings()
        self.assertEqual(self.CONFIRMED["routes"], settings["routes"])
        self.assertEqual(35.5, settings["budget"])
        self.assertEqual({"claude": 0.25}, settings["reserves"])

    def test_confirming_keeps_every_setting_the_installer_recorded_besides_the_routes(self):
        self.record_installer_settings()

        self.confirm(self.CONFIRMED)

        settings = self.settings()
        self.assertEqual("/opt/python3", settings["python"])
        self.assertEqual(["/home/jeff/.claude"], settings["config_dirs"])
        self.assertEqual("/home/jeff/tracer", settings["source_repo"])

    def test_without_the_confirmation_flag_it_refuses_and_writes_nothing(self):
        done = self.setup_script("write", stdin=json.dumps(self.CONFIRMED))

        self.assertEqual(2, done.returncode)
        self.assertEqual(["python"], self.home_files())

    def test_a_reserve_that_is_not_a_share_is_refused_and_nothing_is_written(self):
        before = self.record_installer_settings()
        bad = {**self.CONFIRMED, "reserves": {"claude": 1.5}}

        done = self.confirm(bad)

        self.assertEqual(1, done.returncode)
        self.assertIn("reserves", done.stderr)
        self.assertEqual(before, (self.home / "settings.json").read_bytes())

    def test_a_budget_that_is_not_dollars_above_zero_is_refused(self):
        done = self.confirm({**self.CONFIRMED, "budget": 0})

        self.assertEqual(1, done.returncode)
        self.assertIn("budget", done.stderr)
        self.assertEqual(["python"], self.home_files())

    def test_a_route_without_a_harness_is_refused(self):
        bad = {**self.CONFIRMED, "routes": {"deep": {"model": "opus"}}}

        done = self.confirm(bad)

        self.assertEqual(1, done.returncode)
        self.assertIn("deep", done.stderr)
        self.assertEqual(["python"], self.home_files())

    def test_a_proposal_that_is_not_json_is_refused(self):
        done = self.setup_script("write", "--confirmed", stdin="not json")

        self.assertEqual(1, done.returncode)
        self.assertEqual(["python"], self.home_files())

    def test_the_proposal_that_propose_prints_can_be_confirmed_as_it_is(self):
        self.without_codex()

        done = self.confirm(self.proposal())

        self.assertEqual(0, done.returncode, done.stderr)
        settings = self.settings()
        self.assertEqual(NATIVE_OPUS, settings["routes"]["second"])
        self.assertEqual(50, settings["budget"])
        self.assertEqual({"claude": 0.2}, settings["reserves"])


if __name__ == "__main__":
    unittest.main()
