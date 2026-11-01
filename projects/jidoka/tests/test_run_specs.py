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
RUN_SPECS = PLUGIN / "scripts" / "run_specs.py"
RUN_TIMEOUT_SECONDS = 120

ADDS = "A shopper adds an item to the basket"
PAYS = "A shopper pays by card and the till prints a receipt"
QUOTED = "A shopper can't pay twice"
REFUNDS = "A shopper refunds a card payment"

RUNNER = '''import json
import sys
from pathlib import Path

results = json.loads((Path(__file__).parent / "results.json").read_text(encoding="utf-8"))
chosen = [sys.argv[2]] if sys.argv[1:2] == ["--spec"] else list(results)
ran = [name for name in chosen if name in results]
for name in ran:
    print(("ok: " if results[name] else "broken: ") + name)
print(f"Ran {len(ran)} tests in 0.001s")
sys.exit(0 if all(results[name] for name in ran) else 1)
'''


def interpreter() -> str:
    return f'"{Path(sys.executable).as_posix()}"'


def app(name: str, **changes) -> dict:
    return {"name": name, "kind": "program", "way_in": "its command line", "build": "make", "run": None,
            "test": "make test", "test_target": "T=<name>", "test_full": None, "hand_run": [], "acceptance": None,
            **changes}


SHOP = app("shop", acceptance="acceptance", spec_command=f"{interpreter()} acceptance/run.py",
           spec_target="--spec <spec>")
NO_SPEC_COMMAND = app("till", acceptance="till/acceptance", spec_command=None, spec_target=None)
NO_ACCEPTANCE = app("tools")


class RunSpecsTests(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(fixture.remove_tree_quietly, root)
        self.root = root
        self.home = root / "home"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        self.repo = root / "shop-repo"
        fixture.init_repo(self.repo)
        (self.repo / "acceptance").mkdir()
        (self.repo / "acceptance" / "run.py").write_text(RUNNER, encoding="utf-8")
        self.write_results(self.repo, {ADDS: True, PAYS: False, QUOTED: True, REFUNDS: False})
        fixture.git_commit_all(self.repo, "Start")
        self.write_settings([SHOP, NO_SPEC_COMMAND, NO_ACCEPTANCE])

    def write_results(self, checkout: Path, results: dict) -> None:
        (checkout / "acceptance" / "results.json").write_text(json.dumps(results), encoding="utf-8")

    def write_settings(self, apps: list) -> None:
        fixture.write_repo_settings(self.repo, self.home, {"lap_test_scope": "targeted", "worker_commands": [],
                                                           "slot_use": None, "lap_limit": 2, "apps": apps})

    def env(self) -> dict:
        return {**os.environ, "JIDOKA_HOME": str(self.home), **fixture.home_variables(self.home)}

    def run_specs_in(self, checkout: Path, app_name: str, *specs: str) -> subprocess.CompletedProcess:
        subcommand = "named" if specs else "all"
        return fixture.run_launcher(LAUNCHER, [str(RUN_SPECS), subcommand, app_name, "--checkout", str(checkout),
                                               *specs], None, self.env(), self.root, RUN_TIMEOUT_SECONDS)

    def run_specs(self, app_name: str, *specs: str) -> subprocess.CompletedProcess:
        return self.run_specs_in(self.repo, app_name, *specs)

    def test_prints_the_name_of_a_named_spec_that_passes_with_pass(self):
        done = self.run_specs("shop", ADDS)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(f"pass {ADDS}\n", done.stdout)

    def test_prints_the_name_of_a_named_spec_that_fails_with_fail_and_exits_3_with_the_runners_output(self):
        done = self.run_specs("shop", PAYS)

        self.assertEqual(3, done.returncode, done.stderr)
        self.assertEqual(f"fail {PAYS}\n", done.stdout)
        self.assertIn(f"broken: {PAYS}", done.stderr)

    def test_prints_a_line_for_each_of_several_named_specs_in_the_order_given(self):
        done = self.run_specs("shop", REFUNDS, ADDS, PAYS)

        self.assertEqual(3, done.returncode, done.stderr)
        self.assertEqual(f"fail {REFUNDS}\npass {ADDS}\nfail {PAYS}\n", done.stdout)

    def test_hands_a_spec_name_with_a_quote_in_it_to_the_runner_whole(self):
        done = self.run_specs("shop", QUOTED)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(f"pass {QUOTED}\n", done.stdout)

    def test_runs_a_spec_named_twice_once(self):
        done = self.run_specs("shop", ADDS, f"  {ADDS} ")

        self.assertEqual(f"pass {ADDS}\n", done.stdout)

    def test_runs_all_the_specs_with_the_spec_command_when_none_is_named(self):
        done = self.run_specs("shop")

        self.assertEqual(3, done.returncode, done.stderr)
        self.assertEqual("fail all specs\n", done.stdout)
        self.assertIn(f"broken: {PAYS}", done.stderr)

    def test_prints_pass_for_all_specs_when_every_spec_passes(self):
        self.write_results(self.repo, {ADDS: True, PAYS: True})

        done = self.run_specs("shop")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("pass all specs\n", done.stdout)

    def test_runs_the_specs_of_the_checkout_it_is_given(self):
        other = self.root / "shop-lap"
        fixture.run(["git", "worktree", "add", "-q", "-b", "lap", str(other)], self.repo)
        self.write_results(other, {ADDS: True, PAYS: True, QUOTED: True, REFUNDS: True})

        on_main = self.run_specs("shop", PAYS)
        on_lap = self.run_specs_in(other, "shop", PAYS)

        self.assertEqual(f"fail {PAYS}\n", on_main.stdout)
        self.assertEqual(f"pass {PAYS}\n", on_lap.stdout)
        self.assertEqual(0, on_lap.returncode, on_lap.stderr)

    def test_fails_a_named_spec_that_the_runner_does_not_know_instead_of_passing_it(self):
        done = self.run_specs("shop", "A shopper does something nobody wrote down")

        self.assertEqual(3, done.returncode, done.stderr)
        self.assertEqual("fail A shopper does something nobody wrote down\n", done.stdout)
        self.assertIn("ran no specs", done.stderr)

    def test_refuses_an_app_with_no_acceptance_folder_and_says_to_record_one(self):
        done = self.run_specs("tools", ADDS)

        self.assertEqual(1, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn("'tools' has no acceptance folder", done.stderr)
        self.assertIn("/jidoka:onboard", done.stderr)

    def test_refuses_an_app_with_an_acceptance_folder_and_no_spec_command_and_says_to_record_one(self):
        for specs in ([], [ADDS]):
            with self.subTest(specs=specs):
                done = self.run_specs("till", *specs)

                self.assertEqual(1, done.returncode)
                self.assertEqual("", done.stdout)
                self.assertIn("'till' has an acceptance folder but no spec command", done.stderr)
                self.assertIn("/jidoka:onboard", done.stderr)

    def test_refuses_an_app_the_settings_do_not_name_and_lists_the_apps_they_do(self):
        done = self.run_specs("kiosk", ADDS)

        self.assertEqual(1, done.returncode)
        self.assertIn("no app named 'kiosk'", done.stderr)
        self.assertIn("shop, till, tools", done.stderr)

    def test_refuses_a_repo_with_no_settings_and_says_to_onboard_it(self):
        other = self.root / "other"
        fixture.init_repo(other)
        done = fixture.run_launcher(LAUNCHER, [str(RUN_SPECS), "named", "shop", "--checkout", str(other), ADDS], None,
                                    self.env(), self.root, RUN_TIMEOUT_SECONDS)

        self.assertEqual(1, done.returncode)
        self.assertIn("/jidoka:onboard", done.stderr)

    def test_refuses_a_spec_target_without_exactly_one_placeholder(self):
        self.write_settings([{**SHOP, "spec_target": "--spec"}])

        done = self.run_specs("shop", ADDS)

        self.assertEqual(1, done.returncode)
        self.assertIn("needs exactly one <...> placeholder", done.stderr)

    def test_a_named_run_needs_a_spec_name_and_the_refusal_names_the_named_subcommand(self):
        done = fixture.run_launcher(LAUNCHER, [str(RUN_SPECS), "named", "shop", "--checkout", str(self.repo)], None,
                                    self.env(), self.root, RUN_TIMEOUT_SECONDS)

        self.assertEqual(2, done.returncode)
        self.assertIn("run_specs.py named: error", done.stderr)

    def test_a_run_of_all_specs_takes_no_spec_name_and_the_refusal_names_the_all_subcommand(self):
        done = fixture.run_launcher(LAUNCHER, [str(RUN_SPECS), "all", "shop", "--checkout", str(self.repo), ADDS],
                                    None, self.env(), self.root, RUN_TIMEOUT_SECONDS)

        self.assertEqual(2, done.returncode)
        self.assertIn("run_specs.py all: error", done.stderr)

    def test_refuses_a_checkout_that_is_not_a_folder(self):
        done = self.run_specs_in(self.root / "missing", "shop", ADDS)

        self.assertEqual(1, done.returncode)
        self.assertIn("missing", done.stderr)


if __name__ == "__main__":
    unittest.main()
