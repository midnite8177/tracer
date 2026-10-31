import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_gate_page  # noqa: E402
import test_scheduler  # noqa: E402
from test_scheduler import ACCEPTANCE, MERGE_GATE, PLUGIN, OpenLap, SchedulerCase, git  # noqa: E402

RUN_SPECS = PLUGIN / "scripts" / "run_specs.py"
SPECS = PLUGIN / "scripts" / "specs.py"
LAP_LISTS = PLUGIN / "scripts" / "lap_lists.py"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"

PAYS = "A shopper pays by card and the till prints a receipt"
REFUNDS = "A shopper refunds a card payment"
ADDS = "A shopper adds an item to the basket"
MISSING_CARD = "missing: card.txt"

SPEC_RUNNER = f'''import sys
from pathlib import Path

name = sys.argv[2]
passes = Path("card.txt").exists() or name == {ADDS!r}
print("ok" if passes else {MISSING_CARD!r})
print("Ran 1 tests in 0.001s")
sys.exit(0 if passes else 1)
'''


class SpecRunsCase(SchedulerCase):
    """The scheduler tests' shop repo, whose app also records a spec command, and helpers that open a lap for a task
    that makes specs pass."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        runner = cls.root / "spec_runner.py"
        runner.write_text(SPEC_RUNNER, encoding="utf-8")
        cls.write_settings({"apps": [{
            "name": "shop", "kind": "program", "way_in": "its command line", "build": "make", "run": None,
            "test": cls.test_command, "test_target": "-k <name>", "test_full": None, "hand_run": [],
            "acceptance": ACCEPTANCE, "spec_command": f'"{Path(sys.executable).as_posix()}" "{runner.as_posix()}"',
            "spec_target": "--spec <spec>"}]})

    def open_lap_making_pass(self, *names: str) -> tuple[OpenLap, dict]:
        """Opens a lap for a new epic whose one task makes the specs pass, or none when no spec is named, in an area of
        its own; returns the lap and its build action."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        if names:
            recorded = self.launch(SPECS, "makes-pass", epic, task, *names)
            self.assertEqual(0, recorded.returncode, recorded.stderr)
        branch = self.hand_off(epic, {task: f"{epic}-area"})
        [action] = self.next_printed(epic)["actions"]
        return OpenLap(epic, task, branch, Path(action["worktree"])), action

    def run_specs(self, lap: OpenLap, *flags: str) -> subprocess.CompletedProcess:
        return self.launch(RUN_SPECS, "shop", "--checkout", str(lap.worktree), *flags)

    def red_run(self, lap: OpenLap, *expected: str) -> subprocess.CompletedProcess:
        return self.run_specs(lap, "--record", "red", "--task", lap.task,
                              *(argument for each in expected for argument in ("--expect", each)))

    def green_run(self, lap: OpenLap) -> subprocess.CompletedProcess:
        return self.run_specs(lap, "--record", "green", "--task", lap.task)

    def record_tests(self, task: str, base: str, result: str) -> None:
        fixture.run([self.bd, "update", task, "--set-metadata", "tests.command=make test -k test_card",
                     "--set-metadata", f"tests.base={base}", "--set-metadata", f"tests.result={result}"], self.repo)

    def recorded(self, task: str, key: str) -> dict:
        return json.loads(self.metadata(task)[key])

    def lap_ready_for_the_gate(self, *names: str) -> OpenLap:
        """A lap whose task makes the specs pass, red-run before the build, with the build committed and the targeted
        run recorded as passing, so that only the spec runs stand between the lap and the gate."""
        lap, _ = self.open_lap_making_pass(*names)
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)
        done = self.red_run(lap, *(f"{name}=still missing card.txt" for name in names if name != ADDS))
        self.assertEqual(0, done.returncode, done.stderr)
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.record_tests(lap.task, epic_head, "pass")
        return lap


class RedRunTests(SpecRunsCase):
    def test_a_red_run_records_the_head_each_specs_result_and_the_failure_expected(self):
        lap, _ = self.open_lap_making_pass(PAYS, REFUNDS)
        head = git(lap.worktree, "rev-parse", "HEAD")

        done = self.red_run(lap, f"{PAYS}=the till prints no receipt", f"{REFUNDS}=card.txt is missing")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(f"fail {PAYS}\nfail {REFUNDS}\n", done.stdout)
        self.assertIn(MISSING_CARD, done.stderr)
        self.assertEqual({"head": head, "runs": [
            {"spec": PAYS, "passed": False, "expected": "the till prints no receipt"},
            {"spec": REFUNDS, "passed": False, "expected": "card.txt is missing"}]},
                         self.recorded(lap.task, "acceptance.red"))

    def test_a_red_run_records_a_spec_that_already_passes_and_asks_no_failure_of_it(self):
        lap, _ = self.open_lap_making_pass(PAYS, ADDS)

        done = self.red_run(lap, f"{PAYS}=the till prints no receipt")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(f"fail {PAYS}\npass {ADDS}\n", done.stdout)
        runs = self.recorded(lap.task, "acceptance.red")["runs"]
        self.assertEqual([(PAYS, False), (ADDS, True)], [(each["spec"], each["passed"]) for each in runs])

    def test_a_red_run_of_a_failing_spec_with_no_expected_failure_records_nothing(self):
        lap, _ = self.open_lap_making_pass(PAYS, REFUNDS)

        done = self.red_run(lap, f"{PAYS}=the till prints no receipt")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"fail {REFUNDS}", done.stdout)
        self.assertIn(f"no expected failure was given for {REFUNDS}", done.stderr)
        self.assertNotIn("acceptance.red", self.metadata(lap.task))

    def test_a_task_holds_one_red_run_and_a_second_is_refused(self):
        lap, _ = self.open_lap_making_pass(PAYS)
        self.assertEqual(0, self.red_run(lap, f"{PAYS}=no receipt").returncode)
        self.commit_in(lap.worktree, "card.txt", "built\n")

        done = self.red_run(lap)

        self.assertEqual(1, done.returncode)
        self.assertIn("holds a red run already", done.stderr)
        self.assertFalse(self.recorded(lap.task, "acceptance.red")["runs"][0]["passed"])

    def test_a_red_run_for_a_task_that_makes_no_spec_pass_is_refused(self):
        lap = self.open_one_lap()

        done = self.red_run(lap)

        self.assertEqual(1, done.returncode)
        self.assertIn("makes no acceptance spec pass", done.stderr)

    def test_an_expected_failure_that_names_no_spec_of_the_task_is_refused_before_any_spec_runs(self):
        lap, _ = self.open_lap_making_pass(PAYS)

        done = self.red_run(lap, f"{REFUNDS}=no refund")

        self.assertEqual(1, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn("does not start with the name of one of the task's specs", done.stderr)

    def test_a_recorded_run_takes_no_spec_name_because_it_runs_the_specs_of_the_task(self):
        lap, _ = self.open_lap_making_pass(PAYS)

        done = self.run_specs(lap, "--record", "red", "--task", lap.task, PAYS)

        self.assertEqual(2, done.returncode)

    def test_a_task_flag_without_a_record_is_a_usage_error(self):
        lap, _ = self.open_lap_making_pass(PAYS)

        self.assertEqual(2, self.run_specs(lap, "--task", lap.task, PAYS).returncode)


class GreenRunTests(SpecRunsCase):
    def test_a_green_run_records_the_checkouts_head_and_exits_3_when_a_spec_fails(self):
        lap, _ = self.open_lap_making_pass(PAYS)

        failing = self.green_run(lap)
        self.commit_in(lap.worktree, "card.txt", "built\n")
        passing = self.green_run(lap)

        self.assertEqual((3, f"fail {PAYS}\n"), (failing.returncode, failing.stdout))
        self.assertEqual((0, f"pass {PAYS}\n"), (passing.returncode, passing.stdout))
        self.assertEqual({"head": git(lap.worktree, "rev-parse", "HEAD"),
                          "runs": [{"spec": PAYS, "passed": True, "expected": ""}]},
                         self.recorded(lap.task, "acceptance.green"))

    def test_a_green_run_is_refused_on_a_checkout_with_an_uncommitted_change(self):
        lap, _ = self.open_lap_making_pass(PAYS)
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.leave_in(lap.worktree, "card.txt", "edited\n")

        done = self.green_run(lap)

        self.assertEqual(1, done.returncode)
        self.assertIn("uncommitted changes", done.stderr)
        self.assertNotIn("acceptance.green", self.metadata(lap.task))


class MergeGateSpecRunTests(SpecRunsCase):
    def assert_refused(self, lap: OpenLap, reason: str) -> None:
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)

        done = self.launch(MERGE_GATE, lap.task)

        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(reason, done.stderr)
        self.assertEqual(epic_head, git(self.repo, "rev-parse", lap.epic_branch))
        self.assertEqual("in_progress", self.shown(lap.task)["status"])

    def test_the_gate_refuses_a_lap_with_no_red_run_of_its_tasks_specs(self):
        lap, _ = self.open_lap_making_pass(PAYS)
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.record_tests(lap.task, epic_head, "pass")
        self.assertEqual(0, self.green_run(lap).returncode)

        self.assert_refused(lap, f"no red run of the task's specs is recorded, and the build runs them before it "
                                 f"writes code: {PAYS}")

    def test_the_gate_refuses_a_lap_whose_red_run_leaves_out_one_of_its_tasks_specs(self):
        lap, _ = self.open_lap_making_pass(PAYS)
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)
        self.assertEqual(0, self.red_run(lap, f"{PAYS}=no receipt").returncode)
        fixture.run([self.bd, "update", lap.task, "--set-metadata",
                     f"acceptance.specs={json.dumps([PAYS, REFUNDS])}"], self.repo)
        self.commit_in(lap.worktree, "card.txt", "built\n")
        self.record_tests(lap.task, epic_head, "pass")

        self.assert_refused(lap, f"the red run records no result for these specs of the task: {REFUNDS}")

    def test_the_gate_refuses_a_lap_with_no_green_run_of_its_tasks_specs(self):
        lap = self.lap_ready_for_the_gate(PAYS)

        self.assert_refused(lap, "the task's specs are not recorded green on the lap's head")

    def test_the_gate_refuses_a_lap_whose_green_run_was_made_on_an_earlier_head(self):
        lap = self.lap_ready_for_the_gate(PAYS)
        self.assertEqual(0, self.green_run(lap).returncode)
        self.commit_in(lap.worktree, "other.txt", "later work\n")

        self.assert_refused(lap, "the task's specs are not recorded green on the lap's head")

    def test_the_gate_refuses_a_lap_whose_specs_are_not_green_on_its_head(self):
        lap, _ = self.open_lap_making_pass(PAYS)
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)
        self.assertEqual(0, self.red_run(lap, f"{PAYS}=no receipt").returncode)
        self.commit_in(lap.worktree, "other.txt", "work that does not make the spec pass\n")
        self.record_tests(lap.task, epic_head, "pass")
        self.assertEqual(3, self.green_run(lap).returncode)

        head = git(lap.worktree, "rev-parse", "HEAD")
        self.assert_refused(lap, f"the task's specs are not green on the lap's head {head}: {PAYS}")

    def test_the_gate_merges_a_lap_with_a_red_run_before_the_build_and_a_green_run_on_its_head(self):
        lap = self.lap_ready_for_the_gate(PAYS, ADDS)
        self.assertEqual(0, self.green_run(lap).returncode)
        built = git(lap.worktree, "rev-parse", "HEAD")

        done = self.launch(MERGE_GATE, lap.task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(built, git(self.repo, "rev-parse", lap.epic_branch))
        self.assertEqual("closed", self.shown(lap.task)["status"])


class SchedulerRunsTheSpecsTests(SpecRunsCase):
    def test_a_build_action_names_the_specs_and_the_call_that_runs_them_and_a_task_with_none_has_neither(self):
        _, action = self.open_lap_making_pass(PAYS, REFUNDS)
        _, other_action = self.open_lap_making_pass()

        self.assertEqual([PAYS, REFUNDS], action["specs"])
        self.assertEqual(f"sh {LAUNCHER.resolve().as_posix()} {RUN_SPECS.resolve().as_posix()}",
                         action["specs_command"])
        self.assertEqual(([], None), (other_action["specs"], other_action["specs_command"]))

    def test_a_build_that_made_the_specs_pass_merges_with_a_red_run_then_a_green_run_in_the_record(self):
        lap, _ = self.open_lap_making_pass(PAYS)
        self.assertEqual(0, self.red_run(lap, f"{PAYS}=no receipt").returncode)
        self.leave_in(lap.worktree, "card.txt", "built\n")

        printed = self.build_done(lap.epic, lap.task)

        self.assertEqual([], self.lap_actions(printed))
        merged = git(self.repo, "rev-parse", lap.epic_branch)
        self.assertEqual("closed", self.shown(lap.task)["status"])
        self.assertFalse(self.recorded(lap.task, "acceptance.red")["runs"][0]["passed"])
        self.assertEqual({"head": merged, "runs": [{"spec": PAYS, "passed": True, "expected": ""}]},
                         self.recorded(lap.task, "acceptance.green"))

    def test_a_build_whose_specs_are_still_red_counts_a_try_and_goes_back_to_the_build_naming_them(self):
        lap, _ = self.open_lap_making_pass(PAYS, ADDS)
        self.assertEqual(0, self.red_run(lap, f"{PAYS}=no receipt").returncode)
        self.leave_in(lap.worktree, "other.txt", "work that does not make the spec pass\n")

        printed = self.build_done(lap.epic, lap.task)

        [again] = self.lap_actions(printed)
        self.assertEqual(("build", lap.task), (again["action"], again["task"]))
        self.assertEqual(1, self.metadata(lap.task)["lap.tries"])
        self.assertIn(f"not green on the lap's head: {PAYS}", "\n".join(self.texts(lap.task)))
        self.assertEqual("in_progress", self.shown(lap.task)["status"])

    def test_a_lap_that_skipped_the_red_run_is_parked_by_the_merge_gate(self):
        lap, _ = self.open_lap_making_pass(PAYS)
        epic_head = git(self.repo, "rev-parse", lap.epic_branch)
        self.leave_in(lap.worktree, "card.txt", "built\n")

        printed = self.build_done(lap.epic, lap.task)

        self.assertEqual([], printed["actions"])
        why = self.assert_parked(lap, 0)
        self.assertIn("no red run of the task's specs is recorded", why)
        self.assertEqual(epic_head, git(self.repo, "rev-parse", lap.epic_branch))

    def test_a_task_that_makes_no_spec_pass_runs_no_spec(self):
        lap = self.open_one_lap()
        self.leave_in(lap.worktree, "card.txt", "built\n")

        printed = self.build_done(lap.epic, lap.task)

        self.assertEqual([], self.lap_actions(printed))
        self.assertEqual("closed", self.shown(lap.task)["status"])
        self.assertNotIn("acceptance.green", self.metadata(lap.task))


class LapListTests(SpecRunsCase):
    def lap_list(self, lap: OpenLap) -> list:
        done = fixture.run_launcher(LAUNCHER, [str(LAP_LISTS), "lap"], None, self.caller_env(self.home),
                                    lap.worktree, test_scheduler.RUN_TIMEOUT_SECONDS)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def test_a_task_that_makes_specs_pass_may_run_the_spec_script_with_any_words_but_a_jidoka_home(self):
        lap, action = self.open_lap_making_pass(PAYS)

        self.assertIn({"command": action["specs_command"], "then": "words", "refusing": ["--jidoka-home"]},
                      self.lap_list(lap))

    def test_a_task_that_makes_no_spec_pass_may_not_run_the_spec_script(self):
        lap = self.open_one_lap()

        self.assertNotIn("run_specs", json.dumps(self.lap_list(lap)))


class AcceptanceListsAlreadyPassingSpecsTests(test_gate_page.GatePageCase):
    def red_run_that_found(self, task: str, passed: list[str], failed: list[str]) -> None:
        runs = [{"spec": name, "passed": True, "expected": ""} for name in passed] \
               + [{"spec": name, "passed": False, "expected": "no receipt"} for name in failed]
        fixture.run([self.bd, "update", task, "--set-metadata",
                     "acceptance.red=" + json.dumps({"head": "abc123", "runs": runs})], self.repo)

    def test_the_gate_page_lists_the_specs_that_passed_before_the_build_and_not_the_ones_the_build_made_pass(self):
        epic, task, *_ = self.epic_with_changes()
        self.red_run_that_found(task, [ADDS], [PAYS])

        section = test_gate_page.section_of(self.page_for(epic), "Assumptions")

        self.assertIn("Acceptance specs that passed before the build", section)
        self.assertIn(f"{task} {self.shown(task)['title']}: {ADDS}", section)
        self.assertNotIn(PAYS, section)

    def test_the_gate_comment_lists_the_specs_that_passed_before_the_build(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.red_run_that_found(task, [ADDS], [PAYS])
        self.leave_in(Path(action["worktree"]), self.work_file(task), "built\n")
        self.build_done(epic, task)

        [comment] = [text for text in self.texts(epic) if text.startswith("Acceptance gate:")]

        self.assertIn(f"Acceptance specs that passed before the build:\n- {task} {self.shown(task)['title']}: {ADDS}",
                      comment)

    def test_the_gate_page_lists_no_such_heading_when_every_spec_failed_before_the_build(self):
        epic, task, *_ = self.epic_with_changes()
        self.red_run_that_found(task, [], [PAYS])

        section = test_gate_page.section_of(self.page_for(epic), "Assumptions")

        self.assertNotIn("passed before the build", section)


if __name__ == "__main__":
    unittest.main()
