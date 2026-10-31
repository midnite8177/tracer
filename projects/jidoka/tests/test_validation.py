import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_scheduler  # noqa: E402

sys.path.insert(0, str(test_scheduler.PLUGIN / "scripts"))

import heartbeat  # noqa: E402
import slots  # noqa: E402
import recorded_validation  # noqa: E402
import settings_reader  # noqa: E402
import spec_time_limit  # noqa: E402
from recorded_validation import CommandRun, RecordedValidation  # noqa: E402
from settings_reader import SuiteCommand  # noqa: E402
from validation_specs import SpecFigures, SpecsRun, TimedSpecRun  # noqa: E402

HOLDOUTS = test_scheduler.PLUGIN / "scripts" / "holdouts.py"
SCENARIO = "Run `till total` with items 3.50 and 4.25, then read the line the till prints."
SECOND_SCENARIO = "Run `till receipt` after one sale, then open the receipt it writes."
WHAT_A_USER_SAW = "The till printed a total of 7.7 where the user's items add up to 7.75."
SKIP_HAND_RUN = "--skip-window"
HAND_RUN_COMMAND = "dotnet test --filter FullyQualifiedName~Window"
HAND_RUN_REASON = "they take keyboard focus"

SUITE_THAT_PRINTS_UNITTEST_FIGURES_AND_EXITS_WITH_THE_QUEUED_CODE = """\
import subprocess
import sys
from pathlib import Path
folder = Path(sys.argv[1])
name = Path.cwd().name
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
with open(folder / f"{name}.log", "a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[2:]) + f" {head}\\n")
codes = folder / f"exit-codes-{name}"
code = 0
if codes.exists():
    lines = codes.read_text(encoding="utf-8").split()
    code = int(lines[0]) if lines else 0
    codes.write_text("\\n".join(lines[1:]), encoding="utf-8")
if code:
    print("FAIL: test_till_total")
print("Ran 7 tests in 0.500s\\n")
print("OK (skipped=2)" if code == 0 else "FAILED (failures=1, skipped=2)")
sys.exit(code)
"""


class ValidationCase(test_scheduler.SchedulerCase):
    """The shop repo, whose only app has a suite that prints unittest's figures and a hand-run group."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        suite = cls.root / "suite.py"
        suite.write_text(SUITE_THAT_PRINTS_UNITTEST_FIGURES_AND_EXITS_WITH_THE_QUEUED_CODE, encoding="utf-8")
        cls.write_settings({"apps": [{
            "name": "shop", "kind": "program", "way_in": "its command line", "build": "make", "run": None,
            "test": f'"{sys.executable}" "{suite}" "{cls.runs}"', "test_target": f"{SKIP_HAND_RUN} -k <name>",
            "test_full": SKIP_HAND_RUN,
            "hand_run": [{"name": "window tests", "exclusion": SKIP_HAND_RUN, "command": HAND_RUN_COMMAND,
                          "reason": HAND_RUN_REASON}],
            "acceptance": test_scheduler.ACCEPTANCE}]})

    def epic_building_in_its_lap(self) -> tuple[str, str, str, Path]:
        """An epic with one task whose lap is open; returns the epic, task, branch and the lap's worktree."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        branch = self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        return epic, task, branch, Path(action["worktree"])

    def finish_epic_but_for_the_last_report(self) -> tuple[str, str, str]:
        """An epic with one task whose build left its work in the lap's worktree; returns the epic, task, branch."""
        epic, task, branch, worktree = self.epic_building_in_its_lap()
        self.leave_in(worktree, "till.txt", "built\n")
        return epic, task, branch

    def conflicting_epic(self) -> tuple[str, str, dict]:
        """An epic whose only task wrote clash.txt after main wrote it too, driven to the moves of its validation;
        returns the epic, its branch and those moves."""
        epic, task, branch, worktree = self.epic_building_in_its_lap()
        self.leave_in(worktree, "clash.txt", f"the epic's {epic}\n")
        self.commit_in(self.repo, "clash.txt", f"main's {epic}\n")
        return epic, branch, self.build_done(epic, task)

    def start_the_merge(self, worktree: Path) -> None:
        """What the merge worker of a validation does first: merges main, and stops at the conflict."""
        subprocess.run(["git", "merge", "main"], cwd=worktree, capture_output=True, text=True)

    def reconcile(self, worktree: Path, clash: str) -> str:
        """What the merge worker of a validation does in full: merges main, resolves the clashing file and commits the
        merge; returns the merge commit."""
        self.start_the_merge(worktree)
        (worktree / clash).write_text("the epic's and main's\n", encoding="utf-8")
        git(worktree, "add", clash)
        subprocess.run(["git", "-c", "core.editor=true", "merge", "--continue"], cwd=worktree, capture_output=True,
                       text=True, check=True,
                       env={key: value for key, value in os.environ.items() if key not in ("GIT_EDITOR", "EDITOR")})
        return git(worktree, "rev-parse", "HEAD")

    def settle_tidy_and_review(self, printed: dict) -> dict:
        """Reports the tidy worker done with nothing changed, and every review lane with no finding, for as long as
        the moves hold a tidy or a review action, as a test does that is about neither."""
        while True:
            stages = {each["action"] for each in printed["actions"]}
            if "tidy" in stages:
                done = self.launch(test_scheduler.SCHEDULER, "report-tidy", printed["epic"])
            elif "review" in stages:
                for action in printed["actions"]:
                    if action["action"] == "review":
                        Path(action["report"]).write_text("[]", encoding="utf-8")
                done = self.launch(test_scheduler.SCHEDULER, "report-review", printed["epic"])
            else:
                return printed
            self.assertEqual(0, done.returncode, done.stderr)
            printed = json.loads(done.stdout)

    def build_done(self, epic: str, task: str) -> dict:
        return self.settle_tidy_and_review(super().build_done(epic, task))

    def validation_runs_of(self, epic: str) -> list[str]:
        log = self.runs / f"validation-{epic}.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def queue_validation_exit_codes(self, epic: str, *codes: int) -> None:
        (self.runs / f"exit-codes-validation-{epic}").write_text("\n".join(str(code) for code in codes),
                                                                 encoding="utf-8")

    def gate_comments(self, epic: str) -> list[str]:
        return [text for text in self.texts(epic) if text.startswith("Acceptance gate:")]


class ValidationReachesTheGateTests(ValidationCase):
    def test_the_manager_drives_an_epic_until_it_carries_the_human_label_a_gate_state_and_a_gate_comment(self):
        epic, task, branch = self.finish_epic_but_for_the_last_report()
        title = self.shown(task)["title"]

        printed = self.build_done(epic, task)

        shown = self.shown(epic)
        self.assertEqual(([], "pass"), (printed["actions"], printed["validation"]["result"]))
        self.assertIn("human", shown["labels"])
        self.assertEqual("waiting", (shown.get("metadata") or {}).get("gate.state"))
        [comment] = self.gate_comments(epic)
        self.assertIn(f"{git(self.repo, 'rev-parse', branch)[:7]} {title}", comment)
        self.assertIn("7 tests, 2 skipped", comment)
        self.assertIn(f"- shop, window tests: {HAND_RUN_REASON}\n  {HAND_RUN_COMMAND}", comment)

    def test_validation_runs_the_full_suite_without_the_hand_run_group_and_the_gate_comment_lists_the_group(self):
        epic, task, _ = self.finish_epic_but_for_the_last_report()

        self.build_done(epic, task)

        self.assertEqual([f"{SKIP_HAND_RUN} {self.metadata(epic)['validation.head']}"],
                         self.validation_runs_of(epic))

    def test_validation_records_the_suite_time_the_test_count_and_the_skip_count_on_the_epic(self):
        epic, task, branch = self.finish_epic_but_for_the_last_report()

        self.build_done(epic, task)

        metadata = self.metadata(epic)
        recorded = recorded_validation.read(metadata)
        self.assertEqual(("pass", 7, 2, git(self.repo, "rev-parse", branch)),
                         (metadata.get("validation.result"), recorded.tests, recorded.skipped,
                          metadata.get("validation.head")))
        self.assertGreater(recorded.seconds, 0)

    def test_validation_stores_no_total_apart_from_the_runs_it_sums(self):
        epic, task, branch = self.finish_epic_but_for_the_last_report()

        self.build_done(epic, task)

        metadata = self.metadata(epic)
        self.assertEqual([], [key for key in ("validation.tests", "validation.skipped", "validation.seconds")
                              if key in metadata])

    def test_validation_runs_on_the_epic_branch_after_it_merges_main(self):
        epic, task, branch = self.finish_epic_but_for_the_last_report()
        main_head = self.commit_in(self.repo, "main.txt", "main moved\n")

        self.build_done(epic, task)

        validated_head = git(self.repo, "rev-parse", branch)
        self.assertEqual([f"{SKIP_HAND_RUN} {validated_head}"], self.validation_runs_of(epic))
        self.assertTrue(self.is_on(main_head, validated_head))
        self.assertEqual("main moved", git(self.repo, "show", f"{branch}:main.txt"))
        self.assertEqual(git(self.repo, "rev-parse", branch), self.metadata(epic)["validation.head"])

    def test_validation_leaves_no_worktree_behind(self):
        epic, task, _ = self.finish_epic_but_for_the_last_report()

        self.build_done(epic, task)

        self.assertFalse((self.repo / ".worktrees" / f"validation-{epic}").exists())
        self.assertEqual("", git(self.repo, "status", "--porcelain", "--untracked-files=all"))

    def test_an_epic_at_the_gate_is_not_validated_again(self):
        epic, task, _ = self.finish_epic_but_for_the_last_report()
        self.build_done(epic, task)

        printed = self.next_printed(epic)

        self.assertEqual((None, []), (printed["validation"], printed["actions"]))
        self.assertEqual(1, len(self.validation_runs_of(epic)))
        self.assertEqual(1, len(self.gate_comments(epic)))


class ValidationFailsTests(ValidationCase):
    def test_a_red_run_files_a_task_in_the_epic_that_says_what_failed_and_opens_its_lap(self):
        epic, task, _ = self.finish_epic_but_for_the_last_report()
        self.queue_validation_exit_codes(epic, 1)

        printed = self.build_done(epic, task)

        [action] = printed["actions"]
        filed = self.shown(action["task"])
        self.assertEqual((action["task"], "fail"), (printed["validation"]["filed"], printed["validation"]["result"]))
        self.assertEqual(epic, filed["parent"])
        self.assertIn(f"{SKIP_HAND_RUN}` exited 1", filed["description"])
        self.assertIn("FAIL: test_till_total", filed["description"])
        self.assertEqual(("build", "shop", "in_progress"),
                         (self.metadata(action["task"]).get("lap.stage"), action["area"], filed["status"]))
        self.assertTrue(Path(action["worktree"]).is_dir())

    def test_a_red_run_leaves_the_epic_without_the_human_label_or_a_gate_state_and_records_the_failure(self):
        epic, task, _ = self.finish_epic_but_for_the_last_report()
        self.queue_validation_exit_codes(epic, 1)

        self.build_done(epic, task)

        shown = self.shown(epic)
        self.assertNotIn("human", shown.get("labels") or [])
        self.assertNotIn("gate.state", shown.get("metadata") or {})
        recorded = recorded_validation.read(shown.get("metadata") or {})
        self.assertEqual(("fail", 7, 2), (recorded.result, recorded.tests, recorded.skipped))
        self.assertEqual([], self.gate_comments(epic))

    def test_the_next_pass_validates_again_and_reaches_the_gate_once_the_filed_task_merges(self):
        epic, task, branch = self.finish_epic_but_for_the_last_report()
        self.queue_validation_exit_codes(epic, 1)
        [action] = self.build_done(epic, task)["actions"]
        self.leave_in(Path(action["worktree"]), "repair.txt", "repaired\n")

        printed = self.build_done(epic, action["task"])

        self.assertEqual(("pass", []), (printed["validation"]["result"], printed["actions"]))
        self.assertEqual(2, len(self.validation_runs_of(epic)))
        self.assertIn("human", self.shown(epic)["labels"])
        self.assertEqual("repaired", git(self.repo, "show", f"{branch}:repair.txt"))
        self.assertEqual(1, len(self.gate_comments(epic)))


class ValidationHoldoutsCase(ValidationCase):
    def finish_epic_with_holdouts(self, scenarios: list[str]) -> tuple[str, str, dict]:
        """An epic with one task and one holdout for each scenario; returns the epic, the task and the printed moves
        of the build's report, which ends with the holdouts action."""
        epic, task, _ = self.finish_epic_but_for_the_last_report()
        written = fixture.run_launcher(test_scheduler.LAUNCHER, [str(HOLDOUTS), "write", epic],
                                       json.dumps([{"app": "shop", "tasks": [task], "scenario": each}
                                                   for each in scenarios]),
                                       self.caller_env(self.home), self.repo, None)
        self.assertEqual(0, written.returncode, written.stderr)
        return epic, task, self.build_done(epic, task)

    def write_report(self, action: dict, entries: list[dict]) -> None:
        Path(action["report"]).write_text(json.dumps(entries), encoding="utf-8")

    def report_holdouts(self, epic: str) -> subprocess.CompletedProcess:
        return self.launch(test_scheduler.SCHEDULER, "report-holdouts", epic)

    def holdouts_action_of(self, printed: dict) -> dict:
        [action] = [each for each in printed["actions"] if each["action"] == "holdouts"]
        return action


class ValidationHoldoutsTests(ValidationHoldoutsCase):
    def test_a_green_suite_keeps_an_epic_with_holdouts_from_the_gate_until_they_are_run(self):
        epic, _, printed = self.finish_epic_with_holdouts([SCENARIO, SECOND_SCENARIO])

        action = self.holdouts_action_of(printed)
        shown = self.shown(epic)
        self.assertEqual(("pending", 2, epic), (printed["validation"]["result"], action["holdouts"], action["epic"]))
        self.assertNotIn("human", shown.get("labels") or [])
        self.assertNotIn("gate.state", shown.get("metadata") or {})
        self.assertEqual([], self.gate_comments(epic))
        self.assertEqual(self.metadata(epic)["validation.head"], action["head"])
        self.assertTrue(Path(action["worktree"]).is_dir())

    def test_the_worktree_of_the_holdouts_run_holds_the_epic_branch_head_and_hides_its_scratch_folder(self):
        epic, _, printed = self.finish_epic_with_holdouts([SCENARIO])

        action = self.holdouts_action_of(printed)

        worktree = Path(action["worktree"])
        self.assertEqual(action["head"], git(worktree, "rev-parse", "HEAD"))
        self.assertTrue((worktree / "till.txt").is_file())
        self.assertTrue(Path(action["scratch"]).is_dir())
        self.assertEqual("", git(worktree, "status", "--porcelain", "--untracked-files=all"))

    def test_an_epic_with_no_holdouts_goes_to_the_gate_with_no_holdouts_action(self):
        epic, task, _ = self.finish_epic_but_for_the_last_report()

        printed = self.build_done(epic, task)

        self.assertEqual(([], "pass"), (printed["actions"], printed["validation"]["result"]))

    def test_every_holdout_green_puts_the_epic_at_the_gate_and_removes_the_worktree(self):
        epic, _, printed = self.finish_epic_with_holdouts([SCENARIO, SECOND_SCENARIO])
        action = self.holdouts_action_of(printed)
        self.write_report(action, [{"holdout": 1, "verdict": "pass", "saw": ""},
                                   {"holdout": 2, "verdict": "pass", "saw": ""}])

        done = self.report_holdouts(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        shown = self.shown(epic)
        self.assertEqual(("pass", []), (json.loads(done.stdout)["validation"]["result"],
                                        json.loads(done.stdout)["actions"]))
        self.assertIn("human", shown["labels"])
        self.assertEqual(("waiting", "pass"), (shown["metadata"].get("gate.state"),
                                               shown["metadata"].get("validation.result")))
        self.assertNotIn("validation.holdouts", shown["metadata"])
        self.assertEqual(1, len(self.gate_comments(epic)))
        self.assertFalse(Path(action["worktree"]).exists())

    def test_a_red_holdout_files_a_task_of_what_a_user_saw_and_no_steps_and_opens_its_lap(self):
        epic, _, printed = self.finish_epic_with_holdouts([SCENARIO, SECOND_SCENARIO])
        self.write_report(self.holdouts_action_of(printed),
                          [{"holdout": 1, "verdict": "pass", "saw": ""},
                           {"holdout": 2, "verdict": "fail", "saw": WHAT_A_USER_SAW}])

        done = self.report_holdouts(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        moved = json.loads(done.stdout)
        [action] = moved["actions"]
        filed = self.shown(action["task"])
        self.assertEqual(("fail", action["task"]), (moved["validation"]["result"], moved["validation"]["filed"]))
        self.assertEqual(epic, filed["parent"])
        self.assertIn(WHAT_A_USER_SAW, filed["description"])
        self.assertIn("reaching it through its command line", filed["description"])
        for hidden in (SCENARIO, SECOND_SCENARIO, "Run `till total`"):
            self.assertNotIn(hidden, filed["description"] + filed["title"])
        self.assertEqual(("build", "shop", "in_progress"),
                         (self.metadata(action["task"]).get("lap.stage"), action["area"], filed["status"]))

    def test_a_red_holdout_keeps_the_epic_from_the_gate_and_records_the_failure(self):
        epic, _, printed = self.finish_epic_with_holdouts([SCENARIO])
        self.write_report(self.holdouts_action_of(printed), [{"holdout": 1, "verdict": "fail",
                                                              "saw": WHAT_A_USER_SAW}])

        self.report_holdouts(epic)

        shown = self.shown(epic)
        self.assertNotIn("human", shown.get("labels") or [])
        self.assertNotIn("gate.state", shown["metadata"])
        self.assertEqual("fail", shown["metadata"]["validation.result"])
        self.assertNotIn("validation.holdouts", shown["metadata"])
        self.assertEqual([], self.gate_comments(epic))

    def test_one_task_is_filed_for_each_red_holdout(self):
        epic, _, printed = self.finish_epic_with_holdouts([SCENARIO, SECOND_SCENARIO])
        self.write_report(self.holdouts_action_of(printed),
                          [{"holdout": 1, "verdict": "fail", "saw": WHAT_A_USER_SAW},
                           {"holdout": 2, "verdict": "fail", "saw": "The receipt was blank."}])

        moved = json.loads(self.report_holdouts(epic).stdout)

        self.assertEqual(2, len(moved["validation"]["filed_all"]))
        self.assertEqual([epic, epic], [self.shown(task)["parent"] for task in moved["validation"]["filed_all"]])
        self.assertEqual([moved["validation"]["filed"]], [each["task"] for each in moved["actions"]])

    def test_a_report_that_quotes_a_scenario_is_refused_and_writes_nothing(self):
        epic, _, printed = self.finish_epic_with_holdouts([SCENARIO])
        self.write_report(self.holdouts_action_of(printed), [{"holdout": 1, "verdict": "fail",
                                                              "saw": f"It broke. {SCENARIO}"}])

        done = self.report_holdouts(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("never the steps", done.stderr)
        self.assertEqual("pending", self.metadata(epic)["validation.result"])
        self.assertEqual([], [text for text in self.texts(epic) if text.startswith("Holdouts:")])
        self.assertEqual([], [text for text in self.texts(epic) if "Fix what a user" in text])

    def test_a_report_that_leaves_a_holdout_out_is_refused_and_the_epic_stays_pending(self):
        epic, _, printed = self.finish_epic_with_holdouts([SCENARIO, SECOND_SCENARIO])
        self.write_report(self.holdouts_action_of(printed), [{"holdout": 1, "verdict": "pass", "saw": ""}])

        done = self.report_holdouts(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("holdout 2 of 2", done.stderr)
        self.assertEqual("pending", self.metadata(epic)["validation.result"])
        self.assertNotIn("human", self.shown(epic).get("labels") or [])

    def test_a_missing_report_is_refused_and_the_next_call_starts_the_holdouts_run_again(self):
        epic, _, printed = self.finish_epic_with_holdouts([SCENARIO])
        first = self.holdouts_action_of(printed)

        done = self.report_holdouts(epic)
        again = self.holdouts_action_of(self.next_printed(epic))

        self.assertEqual(1, done.returncode)
        self.assertEqual((first["head"], first["worktree"]), (again["head"], again["worktree"]))
        self.assertEqual(1, len(self.validation_runs_of(epic)))

    def test_a_validation_worker_that_fails_every_run_parks_the_epic_at_the_try_cap_with_its_why_and_one_notification(self):
        epic, _, _ = self.finish_epic_with_holdouts([SCENARIO])
        why = "the app did not start"

        runs = [self.launch(test_scheduler.SCHEDULER, "report-holdouts", epic, "--ended", "failed", "--why", why)
                for _ in range(3)]

        shown = self.shown(epic)
        parked = [text for text in self.texts(epic) if text.startswith("Parked:")]
        self.assertEqual([0, 0, 0], [done.returncode for done in runs])
        self.assertEqual([], [each for each in json.loads(runs[2].stdout)["actions"] if each["action"] == "holdouts"])
        self.assertEqual([True, True, False], [self.has_holdouts_action(json.loads(done.stdout)) for done in runs[:2]]
                         + [self.has_holdouts_action(json.loads(runs[2].stdout))])
        self.assertIn("human", shown["labels"])
        self.assertEqual(1, len(parked))
        self.assertIn(why, parked[0])
        self.assertEqual(1, len(json.loads(shown["metadata"]["notification"])))
        self.assertIn(f"epic-parked:{epic}", shown["metadata"]["notification"])

    def has_holdouts_action(self, printed: dict) -> bool:
        return any(each["action"] == "holdouts" for each in printed["actions"])

    def test_a_cut_off_validation_worker_counts_a_run_toward_the_same_cap(self):
        epic, _, _ = self.finish_epic_with_holdouts([SCENARIO])

        for _ in range(3):
            self.launch(test_scheduler.SCHEDULER, "report-holdouts", epic, "--ended", "cut-off")

        self.assertIn("human", self.shown(epic)["labels"])

    def test_a_report_for_an_epic_that_waits_on_no_holdouts_is_refused(self):
        epic, task, _ = self.finish_epic_but_for_the_last_report()
        self.build_done(epic, task)

        done = self.report_holdouts(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("waits on no run of its holdouts", done.stderr)

    def test_the_next_pass_runs_the_holdouts_again_once_the_filed_task_merges(self):
        epic, _, printed = self.finish_epic_with_holdouts([SCENARIO])
        self.write_report(self.holdouts_action_of(printed), [{"holdout": 1, "verdict": "fail",
                                                              "saw": WHAT_A_USER_SAW}])
        [lap] = json.loads(self.report_holdouts(epic).stdout)["actions"]
        self.leave_in(Path(lap["worktree"]), "repair.txt", "repaired\n")

        moved = self.build_done(epic, lap["task"])

        again = self.holdouts_action_of(moved)
        self.assertEqual("pending", moved["validation"]["result"])
        self.assertEqual(2, len(self.validation_runs_of(epic)))
        self.assertTrue((Path(again["worktree"]) / "repair.txt").is_file())

    def test_a_red_suite_runs_no_holdouts(self):
        epic, task, _ = self.finish_epic_but_for_the_last_report()
        written = fixture.run_launcher(test_scheduler.LAUNCHER, [str(HOLDOUTS), "write", epic],
                                       json.dumps([{"app": "shop", "tasks": [task], "scenario": SCENARIO}]),
                                       self.caller_env(self.home), self.repo, None)
        self.assertEqual(0, written.returncode, written.stderr)
        self.queue_validation_exit_codes(epic, 1)

        printed = self.build_done(epic, task)

        self.assertEqual("fail", printed["validation"]["result"])
        self.assertEqual(["build"], [each["action"] for each in printed["actions"]])
        self.assertFalse((self.repo / ".worktrees" / f"validation-{epic}").exists())


class ValidationMergeConflictTests(ValidationCase):
    """The manager's side of a validation whose merge of main conflicts: it starts the merge worker the scheduler
    prints, the worker merges main in the validation worktree, and the manager reports it."""

    def is_merging(self, worktree: Path) -> bool:
        return subprocess.run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=worktree,
                              capture_output=True).returncode == 0

    def report_merge(self, epic: str, *flags: str) -> subprocess.CompletedProcess:
        return self.launch(test_scheduler.SCHEDULER, "report-merge", epic, *flags)

    def report_merge_printed(self, epic: str, *flags: str) -> dict:
        done = self.report_merge(epic, *flags)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def merge_actions(self, printed: dict) -> list[dict]:
        return [action for action in printed["actions"] if action["action"] == "merge"]

    def merge_tries(self, epic: str) -> int:
        return int(self.metadata(epic).get("validation.mergetries") or 0)

    def question_comments(self, epic: str) -> list[str]:
        return [text for text in self.texts(epic) if text.startswith("Question: ")]

    def test_a_conflict_with_main_prints_a_merge_action_for_the_validation_worktree_naming_the_files(self):
        epic, branch, printed = self.conflicting_epic()

        [action] = self.merge_actions(printed)

        worktree = self.repo / ".worktrees" / f"validation-{epic}"
        self.assertEqual((epic, str(worktree), branch), (action["epic"], action["worktree"], printed["branch"]))
        self.assertEqual(["clash.txt"], action["files"])
        self.assertIn("clash.txt", action["reason"])
        self.assertEqual(str(worktree / ".scratch"), action["scratch"])
        self.assertNotIn("task", action)

    def test_a_conflict_with_main_refuses_nothing_and_leaves_the_epic_and_its_branch_as_they_were(self):
        epic, branch, printed = self.conflicting_epic()

        shown = self.shown(epic)
        self.assertIsNone(printed["validation"])
        self.assertNotIn("human", shown.get("labels") or [])
        self.assertNotIn("gate.state", shown.get("metadata") or {})
        self.assertEqual([], self.validation_runs_of(epic))
        self.assertFalse(self.is_on(git(self.repo, "rev-parse", "main"), branch))

    def test_the_validation_worktree_waits_for_the_merge_worker_at_the_epic_head_with_no_merge_begun(self):
        epic, branch, _ = self.conflicting_epic()
        worktree = self.repo / ".worktrees" / f"validation-{epic}"

        self.assertEqual(git(self.repo, "rev-parse", branch), git(worktree, "rev-parse", "HEAD"))
        self.assertEqual("", git(worktree, "status", "--porcelain"))
        self.assertFalse(self.is_merging(worktree))

    def test_the_epic_records_the_merge_it_owes_until_the_merge_is_validated(self):
        epic, _, printed = self.conflicting_epic()
        [action] = self.merge_actions(printed)
        self.assertEqual(f"{action['head']}:{action['base']}", self.metadata(epic)["validation.merge"])
        self.reconcile(Path(action["worktree"]), "clash.txt")

        self.report_merge_printed(epic)

        self.assertNotIn("validation.merge", self.metadata(epic))

    def test_the_merge_worker_s_merge_is_validated_and_the_epic_branch_moves_to_it(self):
        epic, branch, printed = self.conflicting_epic()
        [action] = self.merge_actions(printed)
        merged = self.reconcile(Path(action["worktree"]), "clash.txt")

        reported = self.report_merge_printed(epic)

        self.assertEqual("pass", reported["validation"]["result"])
        self.assertEqual(merged, git(self.repo, "rev-parse", branch))
        self.assertEqual([f"{SKIP_HAND_RUN} {merged}"], self.validation_runs_of(epic))
        self.assertEqual(merged, self.metadata(epic)["validation.head"])
        self.assertEqual("the epic's and main's", git(self.repo, "show", f"{branch}:clash.txt"))
        self.assertTrue(self.is_on(git(self.repo, "rev-parse", "main"), branch))
        self.assertEqual("waiting", self.metadata(epic).get("gate.state"))
        self.assertFalse(Path(action["worktree"]).exists())

    def test_what_the_merge_worker_left_uncommitted_after_its_merge_joins_the_merge_commit(self):
        epic, branch, printed = self.conflicting_epic()
        [action] = self.merge_actions(printed)
        worktree = Path(action["worktree"])
        self.reconcile(worktree, "clash.txt")
        (worktree / "loose.txt").write_text("left over\n", encoding="utf-8")

        self.report_merge_printed(epic)

        self.assertEqual("left over", git(self.repo, "show", f"{branch}:loose.txt"))
        self.assertEqual(2, len(git(self.repo, "show", "--no-patch", "--format=%P", branch).split()))

    def test_a_call_while_the_merge_worker_works_prints_the_action_again_and_leaves_its_merge_alone(self):
        epic, _, printed = self.conflicting_epic()
        [action] = self.merge_actions(printed)
        worktree = Path(action["worktree"])
        self.start_the_merge(worktree)

        again = self.next_printed(epic)

        [repeated] = self.merge_actions(again)
        self.assertEqual((action["worktree"], ["clash.txt"]), (repeated["worktree"], repeated["files"]))
        self.assertTrue(self.is_merging(worktree))

    def test_a_merge_worker_that_reports_done_with_no_merge_made_counts_a_try_and_is_called_again(self):
        epic, _, _ = self.conflicting_epic()

        reported = self.report_merge_printed(epic)

        self.assertEqual(1, len(self.merge_actions(reported)))
        self.assertFalse(reported["merge"]["reconciled"])
        self.assertEqual(1, self.merge_tries(epic))
        self.assertIn("Merge try 1 of 2", "\n".join(self.texts(epic)))
        self.assertNotIn("human", self.shown(epic).get("labels") or [])

    def test_a_merge_worker_that_leaves_the_merge_unfinished_counts_a_try_and_the_worktree_starts_clean_again(self):
        epic, branch, printed = self.conflicting_epic()
        [action] = self.merge_actions(printed)
        self.start_the_merge(Path(action["worktree"]))

        reported = self.report_merge_printed(epic)

        [again] = self.merge_actions(reported)
        worktree = Path(again["worktree"])
        self.assertEqual(1, self.merge_tries(epic))
        self.assertEqual(git(self.repo, "rev-parse", branch), git(worktree, "rev-parse", "HEAD"))
        self.assertFalse(self.is_merging(worktree))

    def test_a_failed_merge_worker_counts_a_try_and_its_why_reaches_the_comment(self):
        epic, _, _ = self.conflicting_epic()

        reported = self.report_merge_printed(epic, "--ended", "failed", "--why", "git refused the merge")

        self.assertEqual(1, len(self.merge_actions(reported)))
        self.assertEqual(1, self.merge_tries(epic))
        self.assertIn("git refused the merge", "\n".join(self.texts(epic)))

    def test_a_cut_off_merge_worker_counts_no_try_and_is_called_again(self):
        epic, _, _ = self.conflicting_epic()

        reported = self.report_merge_printed(epic, "--ended", "cut-off")

        self.assertEqual(1, len(self.merge_actions(reported)))
        self.assertEqual(0, self.merge_tries(epic))

    def test_two_failed_merge_worker_tries_park_the_epic_with_the_human_label_and_a_question(self):
        epic, _, printed = self.conflicting_epic()
        [action] = self.merge_actions(printed)
        self.report_merge_printed(epic, "--ended", "failed", "--why", "first")

        parked = self.report_merge_printed(epic, "--ended", "failed", "--why", "second")

        shown = self.shown(epic)
        self.assertIn("human", shown["labels"])
        self.assertEqual([], parked["actions"])
        [question] = self.question_comments(epic)
        self.assertIn("second", question)
        self.assertIn("clash.txt", question)
        options = json.loads(shown["metadata"]["question.options"])
        self.assertGreaterEqual(len(options), 2)
        self.assertIn(shown["metadata"]["question.recommended"], [option["name"] for option in options])
        self.assertFalse(Path(action["worktree"]).exists())
        self.assertEqual([], self.validation_runs_of(epic))

    def test_the_second_try_may_be_a_done_report_with_no_merge_made(self):
        epic, _, _ = self.conflicting_epic()
        self.report_merge_printed(epic, "--ended", "failed", "--why", "first")

        parked = self.report_merge_printed(epic)

        self.assertIn("human", self.shown(epic)["labels"])
        self.assertEqual([], self.merge_actions(parked))

    def test_taking_the_human_label_off_gives_the_merge_worker_two_new_tries(self):
        epic, _, _ = self.conflicting_epic()
        self.report_merge_printed(epic, "--ended", "failed", "--why", "first")
        self.report_merge_printed(epic, "--ended", "failed", "--why", "second")
        fixture.run([self.bd, "label", "remove", epic, "human"], self.repo)

        again = self.next_printed(epic)

        self.assertEqual(1, len(self.merge_actions(again)))
        self.assertEqual(0, self.merge_tries(epic))

    def test_a_try_counted_earlier_is_forgotten_once_the_merge_is_validated(self):
        epic, _, printed = self.conflicting_epic()
        [action] = self.merge_actions(printed)
        self.report_merge_printed(epic, "--ended", "failed", "--why", "first")
        self.reconcile(Path(action["worktree"]), "clash.txt")

        self.report_merge_printed(epic)

        self.assertEqual(0, self.merge_tries(epic))

    def test_a_report_for_an_epic_that_waits_on_no_merge_worker_is_refused(self):
        epic, task, _ = self.finish_epic_but_for_the_last_report()
        self.build_done(epic, task)

        done = self.report_merge(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("waits on no merge worker", done.stderr)

    def test_a_report_for_an_epic_that_owes_no_merge_is_refused_although_a_validation_worktree_is_left(self):
        epic, task, _ = self.finish_epic_but_for_the_last_report()
        self.build_done(epic, task)
        leftover = self.repo / ".worktrees" / f"validation-{epic}"
        git(self.repo, "worktree", "add", "--detach", str(leftover), "main")
        self.addCleanup(git, self.repo, "worktree", "remove", "--force", str(leftover))

        done = self.report_merge(epic, "--ended", "failed", "--why", "nothing")

        self.assertEqual(1, done.returncode)
        self.assertIn("waits on no merge worker", done.stderr)
        self.assertEqual(0, self.merge_tries(epic))


SPEC_RUNNER = """\
import os
import sys
import time
from pathlib import Path
folder = Path(sys.argv[1])
name = sys.argv[3]
mine = folder / "running" / f"{os.getpid()}"
mine.parent.mkdir(exist_ok=True)
mine.write_text(name, encoding="utf-8")
slot = os.environ["JIDOKA_SLOT"]
on_slot = folder / "on-slot" / slot
on_slot.parent.mkdir(exist_ok=True)
on_slot.touch(exist_ok=False)
with open(folder / "peaks.log", "a", encoding="utf-8") as log:
    log.write(f"{len(list(mine.parent.iterdir()))}\\n")
with open(folder / "specs.log", "a", encoding="utf-8") as log:
    log.write(name + "\\n")
with open(folder / "slots.log", "a", encoding="utf-8") as log:
    log.write(slot + "\\n")
pause = 0.4
delays = folder / "delays.txt"
if delays.exists():
    for line in delays.read_text(encoding="utf-8").splitlines():
        delayed, _, seconds = line.rpartition("=")
        if delayed == name:
            pause = float(seconds)
time.sleep(pause)
mine.unlink()
on_slot.unlink()
failing = folder / "failing.txt"
broken = failing.exists() and name in failing.read_text(encoding="utf-8").splitlines()
if broken:
    print("FAIL: " + name)
print("Ran 1 tests in 0.4s\\n")
print("FAILED (failures=1)" if broken else "OK")
sys.exit(1 if broken else 0)
"""
ADDS = "A shopper adds an item to the basket"
PAYS = "A shopper pays by card and the till prints a receipt"
REFUNDS = "A shopper refunds a card payment"
VOIDS = "A shopper voids a sale"
SPECS = [ADDS, PAYS, REFUNDS, VOIDS]


def seconds_shown(cost: str, spec: str) -> float:
    """The time the gate page's cost section shows beside the spec, in seconds."""
    found = re.search(re.escape(spec) + r": ([0-9.]+) s", cost)
    if found is None:
        raise AssertionError(f"the cost section shows no time for {spec!r}: {cost}")
    return float(found.group(1))


class ValidationSpecsCase(ValidationCase):
    """The shop repo, whose app also has acceptance specs that a stand-in runner runs one at a time and logs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.spec_runs = cls.root / "spec-runs"
        cls.spec_runs.mkdir()
        runner = cls.root / "specrun.py"
        runner.write_text(SPEC_RUNNER, encoding="utf-8")
        suite = cls.root / "suite.py"
        cls.shop = {
            "name": "shop", "kind": "program", "way_in": "its command line", "build": "make", "run": None,
            "test": f'"{sys.executable}" "{suite}" "{cls.runs}"', "test_target": f"{SKIP_HAND_RUN} -k <name>",
            "test_full": SKIP_HAND_RUN, "hand_run": [], "acceptance": test_scheduler.ACCEPTANCE,
            "spec_command": f'"{sys.executable}" "{runner}" "{cls.spec_runs}"', "spec_target": "--spec <spec>"}
        cls.write_settings({"apps": [cls.shop]})

    def setUp(self):
        for leftover in self.spec_runs.iterdir():
            if leftover.is_dir():
                shutil.rmtree(leftover)
            else:
                leftover.unlink()

    def epic_with_specs_made_pass_by_a_closed_task(self, specs: list[str]) -> tuple[str, str]:
        """An epic with a closed task that makes the specs pass and one task whose build is done but for the last
        report; returns the epic and that task."""
        return self.epic_with_specs_of_a_closed_task_in_an_area(specs, "shop")

    def epic_with_specs_of_a_closed_task_in_an_area(self, specs: list[str], area: str) -> tuple[str, str]:
        """Like `epic_with_specs_made_pass_by_a_closed_task`, with the closed task in the area, whatever app that names;
        its specs belong to the shop."""
        epic = self.new_epic()
        made = self.new_task_under(epic)
        fixture.run([self.bd, "update", made, "--set-metadata", f"lap.area={area}", "--set-metadata",
                     "acceptance.specs=" + json.dumps(specs), "--set-metadata", "acceptance.app=shop"], self.repo)
        fixture.run([self.bd, "close", made, "--reason", "done"], self.repo)
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), "till.txt", "built\n")
        return epic, task

    def specs_run(self) -> list[str]:
        log = self.spec_runs / "specs.log"
        return sorted(log.read_text(encoding="utf-8").splitlines()) if log.exists() else []

    def most_specs_at_once(self) -> int:
        log = self.spec_runs / "peaks.log"
        return max(int(line) for line in log.read_text(encoding="utf-8").split()) if log.exists() else 0

    def another_epic_holds_slots(self, *slots: int) -> None:
        """Another running epic, in another repo, holds the slots, under a machine lap limit of four."""
        settings = self.home / "settings.json"
        settings.write_text(json.dumps({"lap_limit": 4}), encoding="utf-8")
        self.addCleanup(settings.unlink, missing_ok=True)
        beat = self.home / "heartbeat" / "mill-1.json"
        beat.parent.mkdir(exist_ok=True)
        beat.write_text(json.dumps({"epic": "mill-1", "time": int(time.time()), "session": "manager"}),
                        encoding="utf-8")
        (self.home / "slots.json").write_text(json.dumps({"slots": [
            {"epic": "mill-1", "task": f"mill-{slot}", "slot": slot, "repo": str(self.root / "mill"),
             "area": f"area-{slot}"} for slot in slots]}), encoding="utf-8")

    def fail_specs(self, *names: str) -> None:
        (self.spec_runs / "failing.txt").write_text("\n".join(names), encoding="utf-8")


class ValidationRunsTheSpecsTests(ValidationSpecsCase):
    def test_validation_runs_every_spec_the_epics_tasks_make_pass_after_the_suite_passes(self):
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)

        printed = self.build_done(epic, task)

        self.assertEqual(("pass", sorted(SPECS)), (printed["validation"]["result"], self.specs_run()))
        self.assertIn("human", self.shown(epic)["labels"])

    def test_validation_runs_the_specs_on_the_app_that_records_them_whatever_the_area_of_their_task_names(self):
        epic, task = self.epic_with_specs_of_a_closed_task_in_an_area(SPECS, "the-till-area")

        printed = self.build_done(epic, task)

        self.assertEqual(("pass", sorted(SPECS)), (printed["validation"]["result"], self.specs_run()))

    def test_validation_runs_no_spec_when_the_suite_fails(self):
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)
        self.queue_validation_exit_codes(epic, 1)

        printed = self.build_done(epic, task)

        self.assertEqual(("fail", []), (printed["validation"]["result"], self.specs_run()))

    def test_validation_runs_the_specs_side_by_side_on_the_slots_the_machine_has_free(self):
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)
        self.another_epic_holds_slots(1)

        self.build_done(epic, task)

        self.assertEqual((sorted(SPECS), 3), (self.specs_run(), self.most_specs_at_once()))

    def test_validation_runs_one_spec_at_a_time_when_the_machine_has_no_free_slot(self):
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)
        self.another_epic_holds_slots(1, 2, 3, 4)

        self.build_done(epic, task)

        self.assertEqual((sorted(SPECS), 1), (self.specs_run(), self.most_specs_at_once()))

    def test_validation_gives_each_spec_that_runs_side_by_side_a_free_slot_of_its_own(self):
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)
        self.another_epic_holds_slots(1)

        printed = self.build_done(epic, task)

        slots_used = set((self.spec_runs / "slots.log").read_text(encoding="utf-8").split())
        self.assertEqual(("pass", {"2", "3", "4"}), (printed["validation"]["result"], slots_used))

    def test_validation_leaves_a_slot_for_another_running_epic_that_holds_none(self):
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)
        self.another_epic_holds_slots()

        self.build_done(epic, task)

        self.assertEqual((sorted(SPECS), 3), (self.specs_run(), self.most_specs_at_once()))

    def test_validation_gives_the_slots_back_when_the_specs_are_done(self):
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)

        self.build_done(epic, task)

        held = json.loads((self.home / "slots.json").read_text(encoding="utf-8"))["slots"]
        self.assertEqual([], [claim for claim in held if claim["epic"] == epic])

    def test_validation_records_the_spec_runs_time_and_count_beside_the_suites(self):
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)

        self.build_done(epic, task)

        metadata = self.metadata(epic)
        self.assertEqual((7, 4), (recorded_validation.read(metadata).tests, metadata["validation.specs"]))
        self.assertGreater(float(metadata["validation.spec_seconds"]), 0)
        [comment] = self.gate_comments(epic)
        self.assertIn("4 acceptance specs", comment)

    def test_validation_runs_a_spec_that_two_tasks_make_pass_once(self):
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task([ADDS, ADDS, PAYS])

        self.build_done(epic, task)

        self.assertEqual(sorted([ADDS, PAYS]), self.specs_run())


class ValidationPlansTheSpecsBeforeTheSuiteTests(ValidationSpecsCase):
    def refusal_after(self, printed: dict) -> subprocess.CompletedProcess:
        """Reports the tidy worker and every review lane done until a report is refused; returns that report."""
        while True:
            stages = {each["action"] for each in printed["actions"]}
            if "tidy" in stages:
                done = self.launch(test_scheduler.SCHEDULER, "report-tidy", printed["epic"])
            elif "review" in stages:
                for action in printed["actions"]:
                    if action["action"] == "review":
                        Path(action["report"]).write_text("[]", encoding="utf-8")
                done = self.launch(test_scheduler.SCHEDULER, "report-review", printed["epic"])
            else:
                self.fail("validation was never refused")
            if done.returncode != 0:
                return done
            printed = json.loads(done.stdout)

    def test_a_spec_that_the_settings_cannot_run_refuses_validation_before_its_suite_runs(self):
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)
        self.write_settings({"apps": [{**self.shop, "spec_command": None, "spec_target": None}]})
        self.addCleanup(self.write_settings, {"apps": [self.shop]})

        done = self.refusal_after(test_scheduler.SchedulerCase.build_done(self, epic, task))

        self.assertIn("no spec command", done.stderr)
        self.assertEqual(([], []), (self.validation_runs_of(epic), self.specs_run()))


class ValidationFailingSpecTests(ValidationSpecsCase):
    def test_a_failing_spec_files_a_task_in_the_epic_that_names_the_spec_and_opens_its_lap(self):
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)
        self.fail_specs(PAYS)

        printed = self.build_done(epic, task)

        [action] = printed["actions"]
        filed = self.shown(action["task"])
        self.assertEqual(("fail", action["task"]), (printed["validation"]["result"], printed["validation"]["filed"]))
        self.assertEqual(epic, filed["parent"])
        self.assertIn(PAYS, filed["title"])
        self.assertIn(PAYS, filed["description"])
        self.assertIn(f"FAIL: {PAYS}", filed["description"])
        self.assertEqual("shop", action["area"])

    def test_each_failing_spec_files_a_task_of_its_own_and_the_epic_stays_off_the_gate(self):
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)
        self.fail_specs(PAYS, VOIDS)

        printed = self.build_done(epic, task)

        shown = self.shown(epic)
        self.assertEqual(2, len(printed["validation"]["filed_all"]))
        self.assertNotIn("human", shown.get("labels") or [])
        self.assertEqual("fail", shown["metadata"]["validation.result"])
        self.assertEqual(4, shown["metadata"]["validation.specs"])


class ValidationSlowSpecsTests(ValidationSpecsCase):
    def setUp(self):
        super().setUp()
        for each in self.open_design_beads():
            fixture.run([self.bd, "close", each["id"], "--reason", "closed by the test"], self.repo)

    def open_design_beads(self) -> list[dict]:
        return json.loads(fixture.run([self.bd, "list", "--label", "design", "--type", "task", "--limit", "0",
                                       "--json"], self.repo))

    def limit_the_spec_run_to(self, seconds: float) -> None:
        self.write_settings({"apps": [{**self.shop, "spec_seconds_limit": seconds}]})
        self.addCleanup(self.write_settings, {"apps": [self.shop]})

    def make_slow(self, spec: str, seconds: float) -> None:
        with open(self.spec_runs / "delays.txt", "a", encoding="utf-8") as delays:
            delays.write(f"{spec}={seconds}\n")

    def validate_an_epic_over_the_limit(self) -> str:
        self.limit_the_spec_run_to(0.5)
        self.make_slow(PAYS, 1.4)
        self.make_slow(REFUNDS, 1.0)
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)
        self.build_done(epic, task)
        return epic

    def cost_section(self, epic: str) -> str:
        guide = self.root / "slow-guide.json"
        guide.write_text(json.dumps({"in_short": "The till prints receipts."}), encoding="utf-8")
        done = self.launch(test_scheduler.PLUGIN / "scripts" / "gate_page.py", epic, "--guide", str(guide))
        self.assertEqual(0, done.returncode, done.stderr)
        html = Path(done.stdout.strip()).read_text(encoding="utf-8")
        found = re.search(r"(?s)<h2>Cost</h2>(.*?)</section>", html)
        self.assertIsNotNone(found)
        return found.group(1)

    def test_a_spec_run_over_the_apps_limit_shows_its_slowest_specs_with_their_times_at_the_gate(self):
        epic = self.validate_an_epic_over_the_limit()

        cost = self.cost_section(epic)

        self.assertIn("over the 0.5 s limit", cost)
        self.assertGreaterEqual(seconds_shown(cost, PAYS), 1.4)
        self.assertGreaterEqual(seconds_shown(cost, REFUNDS), 1.0)
        self.assertLess(cost.index(PAYS), cost.index(REFUNDS))
        self.assertLess(cost.index(REFUNDS), cost.index(ADDS))

    def test_a_spec_run_over_the_apps_limit_files_a_design_finding_against_the_protocol_driver(self):
        epic = self.validate_an_epic_over_the_limit()

        [finding] = self.open_design_beads()

        shown = self.shown(finding["id"])
        self.assertIn("protocol driver", shown["title"])
        self.assertIn(test_scheduler.ACCEPTANCE, shown["title"])
        self.assertIn("0.5 s", shown["description"])
        self.assertIn(PAYS, shown["description"])
        self.assertNotIn("parent", shown)
        [sighting] = self.texts(finding["id"])
        self.assertIn(epic, sighting)

    def test_a_second_epic_over_the_limit_adds_a_sighting_to_the_open_design_finding(self):
        first = self.validate_an_epic_over_the_limit()
        second = self.validate_an_epic_over_the_limit()

        [finding] = self.open_design_beads()

        sightings = self.texts(finding["id"])
        self.assertEqual(2, len(sightings))
        self.assertIn(first, sightings[0])
        self.assertIn(second, sightings[1])

    def test_a_spec_run_under_the_limit_files_nothing_and_shows_no_slow_specs(self):
        self.limit_the_spec_run_to(600)
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)

        printed = self.build_done(epic, task)

        self.assertEqual("pass", printed["validation"]["result"])
        self.assertEqual([], self.open_design_beads())
        self.assertNotIn("limit", self.cost_section(epic))

    def test_an_app_with_no_limit_files_nothing(self):
        self.make_slow(PAYS, 1.0)
        epic, task = self.epic_with_specs_made_pass_by_a_closed_task(SPECS)

        self.build_done(epic, task)

        self.assertEqual([], self.open_design_beads())
        self.assertNotIn("limit", self.cost_section(epic))


class SpecTimeLimitTests(unittest.TestCase):
    def test_an_apps_limit_judges_its_own_part_of_the_run_and_not_the_time_of_the_apps_beside_it(self):
        settings = settings_reader.settings_of(
            {"apps": [{"name": "till", "acceptance": "till/specs", "spec_seconds_limit": 5},
                      {"name": "mill", "acceptance": "mill/specs", "spec_seconds_limit": 5}]}, Path("settings.json"))
        run = SpecsRun([TimedSpecRun("till", "A till total", True, "", 0.0, 1.0),
                        TimedSpecRun("mill", "A mill grind", True, "", 0.0, 60.0)])

        over = spec_time_limit.over_the_limit(settings, run)

        self.assertEqual([("mill", 60.0)], [(each.app, each.seconds) for each in over])


class RecordedValidationTests(unittest.TestCase):
    def recorded(self) -> RecordedValidation:
        runs = [CommandRun(SuiteCommand("shop", "dotnet test"), 0, 1.25, 7, 2, "out"),
                CommandRun(SuiteCommand("kiosk", "make test"), 1, 0.5, None, 0, "")]
        slow = [spec_time_limit.OverTheLimit("shop", "shop/specs", 5.0, 9.5, 3,
                                             (spec_time_limit.SlowSpec("A till total", 4.0),))]
        return RecordedValidation("fail", "abc123", runs, SpecFigures(3, 9.5), slow)

    def written_then_read(self, recorded: RecordedValidation) -> RecordedValidation | None:
        arguments = recorded.metadata()
        pairs = [pair.split("=", 1) for flag, pair in zip(arguments, arguments[1:]) if flag == "--set-metadata"]
        return recorded_validation.read(dict(pairs))

    def test_a_recorded_validation_is_read_back_as_it_was_written_apart_from_the_output_of_its_commands(self):
        recorded = self.recorded()

        read = self.written_then_read(recorded)

        without_output = [replace(each, output="") for each in recorded.runs]
        self.assertEqual(replace(recorded, runs=without_output), read)

    def test_the_totals_are_those_of_the_commands_and_untested_commands_count_no_tests(self):
        recorded = self.recorded()

        self.assertEqual((7, 2, 1.75), (recorded.tests, recorded.skipped, recorded.seconds))

    def test_no_runs_on_the_epic_is_no_recorded_validation(self):
        self.assertIsNone(recorded_validation.read({"validation.result": "pass"}))

    def test_a_validation_without_slow_specs_takes_the_key_off_the_epic(self):
        recorded = replace(self.recorded(), slow=[])

        self.assertEqual(["--unset-metadata", "validation.slow_specs"], recorded.metadata()[-2:])

    def test_the_comment_gives_the_headline_the_figures_and_the_slow_specs(self):
        lines = self.recorded().comment_lines("Validation failed.")

        self.assertEqual(["Validation failed.", "Validation of abc123: 7 tests, 2 skipped, 1.75 s."], lines[:2])
        self.assertIn("A till total: 4.0 s", lines)


class ValidationSlotHoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.main_tree = Path("/work/shop")
        self.now = int(time.time())
        for epic in ("shop-1", "shop-2"):
            heartbeat.write_beat(self.home, epic, self.now, "manager")

    def standing(self, epic: str) -> slots.Standing:
        return slots.Standing(self.home, epic, self.main_tree, 4, self.now)

    def test_a_validations_hold_names_no_area_so_it_blocks_no_task_of_another_epic(self):
        slots.hold_free(self.standing("shop-1"))

        machine, _ = slots.machine_beside(self.standing("shop-2"))

        self.assertEqual(frozenset(), machine.areas)

    def test_a_validation_leaves_a_slot_free_for_each_running_epic_that_holds_none(self):
        held = slots.hold_free(self.standing("shop-1"))

        self.assertEqual([1, 2, 3], held)

    def test_a_validation_that_the_machine_leaves_no_slot_still_gets_one(self):
        slots.write(self.home, [slots.Claim("shop-2", f"shop-{number}", number, str(self.main_tree), f"area-{number}")
                                for number in (1, 2, 3, 4)])

        self.assertEqual([5], slots.hold_free(self.standing("shop-1")))

    def test_releasing_takes_off_the_validation_holds_and_leaves_the_laps_of_other_epics(self):
        lap = slots.Claim("shop-2", "shop-9", 4, str(self.main_tree), "till")
        slots.write(self.home, [lap])
        slots.hold_free(self.standing("shop-1"))

        slots.release(self.home, "shop-1")

        self.assertEqual([lap], slots.read(self.home))


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


if __name__ == "__main__":
    unittest.main()
