import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_scheduler  # noqa: E402

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


class ValidationMergeConflictTests(ValidationCase):
    def test_a_conflict_with_main_stops_validation_naming_the_files_and_writes_nothing(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        branch = self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), "clash.txt", "the epic's\n")
        self.commit_in(self.repo, "clash.txt", "main's\n")
        epic_head_before = git(self.repo, "rev-parse", branch)

        done = self.report(epic, task, "done", "--app", "shop", "--filter", "test_card")

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
