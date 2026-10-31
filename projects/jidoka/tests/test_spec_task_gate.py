import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
from test_scheduler import ACCEPTANCE, MERGE_GATE, PLUGIN, OpenLap, SchedulerCase, git  # noqa: E402

SPECS = PLUGIN / "scripts" / "specs.py"
RESULTS = f"{ACCEPTANCE}/results.json"

OLD = "A shopper adds an item to the basket"
NEW = "A shopper pays by card and the till prints a receipt"
ANOTHER_NEW = "A shopper refunds a card payment"
TRUE = "A shopper sees the basket total"

# A stand-in for an app's acceptance runner. results.json maps each spec to pass, fail (a failed check), error (an
# exception in the driver) or build (the acceptance project does not build). It runs the spec after --spec, or all of
# them, and prints a summary like unittest's.
SPEC_RUNNER = f'''import json
import sys
from pathlib import Path

results = json.loads(Path({RESULTS!r}).read_text(encoding="utf-8"))
chosen = [sys.argv[2]] if sys.argv[1:2] == ["--spec"] else list(results)
if any(results[name] == "build" for name in chosen):
    print("error CS1002: the acceptance project does not build")
    sys.exit(1)
counts = {{kind: sum(results[name] == kind for name in chosen) for kind in ("fail", "error")}}
print(f"Ran {{len(chosen)}} tests in 0.001s")
if counts["fail"] or counts["error"]:
    parts = [f"{{word}}={{counts[kind]}}" for kind, word in (("fail", "failures"), ("error", "errors")) if counts[kind]]
    print("FAILED (" + ", ".join(parts) + ")")
    sys.exit(1)
'''


class SpecTaskGateTests(SchedulerCase):
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

    def spec_task_lap(self, before: dict, after: dict, new: list[str], already_true: list[str]) -> tuple[OpenLap, str]:
        """The lap of an epic's spec task, built to leave the acceptance folder's results as after, on an epic branch
        whose folder holds before. Another task of the epic makes the new specs pass, and the spec task lists the
        specs planning marked as already true. The targeted run is recorded as passing. Returns the lap and the epic
        branch's head."""
        epic = self.new_epic()
        spec_task = self.new_task_under(epic)
        maker = self.new_task_under(epic)
        self.assertEqual(0, self.launch(SPECS, "spec-task", epic, spec_task).returncode)
        self.assertEqual(0, self.launch(SPECS, "makes-pass", epic, maker, *new).returncode)
        if already_true:
            self.assertEqual(0, self.launch(SPECS, "already-true", epic, spec_task, *already_true).returncode)
        branch = self.hand_off(epic, {spec_task: f"{epic}-driver", maker: f"{epic}-till"})
        epic_head = self.commit_on_epic_branch(branch, RESULTS, json.dumps(before))
        [action] = [each for each in self.next_printed(epic)["actions"] if each["task"] == spec_task]
        lap = OpenLap(epic, spec_task, branch, Path(action["worktree"]))
        self.commit_in(lap.worktree, RESULTS, json.dumps(after))
        fixture.run([self.bd, "update", spec_task, "--set-metadata", "tests.command=make test -k test_card",
                     "--set-metadata", f"tests.base={epic_head}", "--set-metadata", "tests.result=pass"], self.repo)
        return lap, epic_head

    def assert_refused_naming(self, lap: OpenLap, epic_head: str, *reasons: str) -> None:
        done = self.launch(MERGE_GATE, lap.task)

        self.assertEqual(1, done.returncode, done.stderr)
        for reason in reasons:
            self.assertIn(reason, done.stderr)
        self.assertEqual(epic_head, git(self.repo, "rev-parse", lap.epic_branch))
        self.assertEqual("in_progress", self.shown(lap.task)["status"])

    def test_it_merges_a_spec_task_whose_new_specs_fail_as_checks_and_whose_old_and_already_true_specs_pass(self):
        lap, _ = self.spec_task_lap({OLD: "pass", TRUE: "pass"},
                                    {OLD: "pass", TRUE: "pass", NEW: "fail", ANOTHER_NEW: "fail"},
                                    [NEW, ANOTHER_NEW], [TRUE])
        built = git(lap.worktree, "rev-parse", "HEAD")

        done = self.launch(MERGE_GATE, lap.task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(built, git(self.repo, "rev-parse", lap.epic_branch))
        self.assertEqual("closed", self.shown(lap.task)["status"])

    def test_it_refuses_a_spec_task_whose_new_spec_ends_in_a_build_error(self):
        lap, epic_head = self.spec_task_lap({OLD: "pass"}, {OLD: "pass", NEW: "build"}, [NEW], [])

        self.assert_refused_naming(lap, epic_head, f"the new spec {NEW!r} ended in a build or driver error")

    def test_it_refuses_a_spec_task_whose_new_spec_ends_in_a_driver_error(self):
        lap, epic_head = self.spec_task_lap({OLD: "pass"}, {OLD: "pass", NEW: "error"}, [NEW], [])

        self.assert_refused_naming(lap, epic_head, f"the new spec {NEW!r} ended in a build or driver error")

    def test_it_refuses_a_spec_task_whose_new_spec_passes(self):
        lap, epic_head = self.spec_task_lap({OLD: "pass"}, {OLD: "pass", NEW: "pass"}, [NEW], [])

        self.assert_refused_naming(lap, epic_head, f"the new spec {NEW!r} passes")

    def test_it_refuses_a_spec_task_under_which_an_old_spec_fails(self):
        lap, epic_head = self.spec_task_lap({OLD: "pass"}, {OLD: "fail", NEW: "fail"}, [NEW], [])

        self.assert_refused_naming(lap, epic_head, "1 more spec fail", "an old spec fails")

    def test_it_refuses_a_spec_task_under_which_an_old_spec_ends_in_a_driver_error(self):
        lap, epic_head = self.spec_task_lap({OLD: "pass"}, {OLD: "error", NEW: "fail"}, [NEW], [])

        self.assert_refused_naming(lap, epic_head, "an old spec cannot be judged")

    def test_it_refuses_a_spec_task_whose_already_true_spec_fails(self):
        lap, epic_head = self.spec_task_lap({OLD: "pass", TRUE: "pass"}, {OLD: "pass", TRUE: "fail", NEW: "fail"},
                                            [NEW], [TRUE])

        self.assert_refused_naming(lap, epic_head, f"the spec {TRUE!r}, which planning marked as already true")

    def test_it_refuses_a_spec_task_whose_lap_changed_no_acceptance_folder(self):
        lap, epic_head = self.spec_task_lap({OLD: "pass"}, {OLD: "pass", NEW: "fail"}, [NEW], [])
        git(lap.worktree, "reset", "-q", "--hard", epic_head)
        self.commit_in(lap.worktree, "card.txt", "built\n")

        self.assert_refused_naming(lap, epic_head, "changed the acceptance folder of no app")


if __name__ == "__main__":
    unittest.main()
