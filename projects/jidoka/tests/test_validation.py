import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_scheduler  # noqa: E402

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

    def finish_epic_but_for_the_last_report(self) -> tuple[str, str, str]:
        """An epic with one task whose build left its work in the lap's worktree; returns the epic, task, branch."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        branch = self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), "till.txt", "built\n")
        return epic, task, branch

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
        self.assertEqual(("pass", 7, 2, git(self.repo, "rev-parse", branch)),
                         (metadata.get("validation.result"), metadata.get("validation.tests"),
                          metadata.get("validation.skipped"), metadata.get("validation.head")))
        self.assertGreater(float(metadata["validation.seconds"]), 0)

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
        self.assertEqual(("fail", 7, 2), tuple((shown.get("metadata") or {})[f"validation.{key}"]
                                                   for key in ("result", "tests", "skipped")))
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
        written = subprocess.run(fixture.launch_command(test_scheduler.LAUNCHER, [str(HOLDOUTS), "write", epic]),
                                 input=json.dumps([{"app": "shop", "tasks": [task], "scenario": each}
                                                   for each in scenarios]),
                                 capture_output=True, text=True, encoding="utf-8", env=self.caller_env(self.home),
                                 cwd=self.repo)
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
        subprocess.run(fixture.launch_command(test_scheduler.LAUNCHER, [str(HOLDOUTS), "write", epic]),
                       input=json.dumps([{"app": "shop", "tasks": [task], "scenario": SCENARIO}]),
                       capture_output=True, text=True, encoding="utf-8", env=self.caller_env(self.home),
                       cwd=self.repo, check=True)
        self.queue_validation_exit_codes(epic, 1)

        printed = self.build_done(epic, task)

        self.assertEqual("fail", printed["validation"]["result"])
        self.assertEqual(["build"], [each["action"] for each in printed["actions"]])
        self.assertFalse((self.repo / ".worktrees" / f"validation-{epic}").exists())


class ValidationMergeConflictTests(ValidationCase):
    def test_a_conflict_with_main_stops_validation_naming_the_files_and_writes_nothing(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        branch = self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), "clash.txt", "the epic's\n")
        self.commit_in(self.repo, "clash.txt", "main's\n")
        epic_head_before = git(self.repo, "rev-parse", branch)

        self.report_printed(epic, task, "done", "--app", "shop", "--filter", "test_card")
        tidied = self.launch(test_scheduler.SCHEDULER, "report-tidy", epic)
        for action in json.loads(tidied.stdout)["actions"]:
            Path(action["report"]).write_text("[]", encoding="utf-8")
        done = self.launch(test_scheduler.SCHEDULER, "report-review", epic)

        shown = self.shown(epic)
        self.assertEqual(1, done.returncode)
        self.assertIn("clash.txt", done.stderr)
        self.assertNotIn("human", shown.get("labels") or [])
        self.assertNotIn("gate.state", shown.get("metadata") or {})
        self.assertEqual([], self.validation_runs_of(epic))
        self.assertEqual(epic_head_before, git(self.repo, "rev-parse", f"{branch}~1"))
        self.assertFalse((self.repo / ".worktrees" / f"validation-{epic}").exists())


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


if __name__ == "__main__":
    unittest.main()
