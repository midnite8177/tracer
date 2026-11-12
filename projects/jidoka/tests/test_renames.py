import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_cleanup  # noqa: E402
import test_review  # noqa: E402
import test_scheduler  # noqa: E402
import test_validation  # noqa: E402

SPEC = f"{test_scheduler.ACCEPTANCE}/till.feature"
FINDINGS = {"comments": [test_review.finding("Echo", "small", "high")]}


class RenameCase(test_review.ReviewCase, test_cleanup.CleanupCase):
    """Runs every git the scripts start with diff.renames set to RENAMES, as `git -c` would, so a test shows what the
    scripts read from a rename whatever the user's git config says."""
    RENAMES = ""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        spec = cls.repo / SPEC
        spec.parent.mkdir(parents=True, exist_ok=True)
        spec.write_text("Feature: till\n  Scenario: a total\n", encoding="utf-8")
        fixture.git_commit_all(cls.repo, "Add the till spec")

    def caller_env(self, home: Path) -> dict[str, str]:
        return {**super().caller_env(home), "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "diff.renames",
                "GIT_CONFIG_VALUE_0": self.RENAMES}

    def rename_in(self, worktree: Path, old: str, new: str) -> None:
        """Moves a file in the worktree and commits nothing, as a worker that renames a file does."""
        (worktree / new).parent.mkdir(parents=True, exist_ok=True)
        os.rename(worktree / old, worktree / new)

    def fix_owed_after_a_task_that_renamed(self, renames: dict[str, str]) -> tuple[str, dict]:
        """An epic whose one task built a file and renamed each old path in `renames` to its new one, reviewed with
        one finding to fix; returns the epic and the fix action."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        worktree = Path(action["worktree"])
        self.leave_in(worktree, test_review.BUILT_FILE, "total = 1\n")
        for old, new in renames.items():
            self.rename_in(worktree, old, new)
        printed = self.tidied(test_scheduler.SchedulerCase.build_done(self, epic, action["task"]))
        return epic, self.fix_action_of(self.reviewed(printed, FINDINGS))


class RenamedFileTests:
    def test_a_file_the_epic_renamed_is_among_the_files_the_fix_may_change_and_a_fix_to_it_commits(self):
        epic, action = self.fix_owed_after_a_task_that_renamed({"README.md": "GUIDE.md"})
        self.leave_in(Path(action["worktree"]), "GUIDE.md", "shop, renamed\n")

        done = self.report_fix(epic)

        self.assertEqual(["GUIDE.md", test_review.BUILT_FILE], action["files"])
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["GUIDE.md"], json.loads(done.stdout)["fix"]["changed"])

    def test_a_fix_that_renames_an_epic_file_commits_the_removal_and_the_new_file(self):
        epic, action = self.fix_owed_after_a_task_that_renamed({})
        branch = self.metadata(epic)["factory.branch"]
        self.rename_in(Path(action["worktree"]), test_review.BUILT_FILE, "till_totals.txt")

        done = self.report_fix(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([test_review.BUILT_FILE, "till_totals.txt"], json.loads(done.stdout)["fix"]["changed"])
        files = test_validation.git(self.repo, "ls-tree", "--name-only", branch).splitlines()
        self.assertEqual((False, True), (test_review.BUILT_FILE in files, "till_totals.txt" in files))

    def test_a_cleanup_that_renames_a_test_of_the_epic_is_refused_and_the_refusal_names_the_new_path(self):
        epic, _, printed = self.finish_epic_whose_task_added_tests()
        branch = self.metadata(epic)["factory.branch"]
        head = test_validation.git(self.repo, "rev-parse", branch)
        action = self.cleanup_action_of(printed)
        self.rename_in(Path(action["worktree"]), test_cleanup.TEST_FILE, "tests/test_till_renamed.py")
        self.write_report(action, [])

        done = self.report_cleanup(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("tests/test_till_renamed.py", done.stderr)
        self.assertEqual(head, test_validation.git(self.repo, "rev-parse", branch))

    def test_a_fix_that_renames_a_file_out_of_an_acceptance_folder_is_refused_as_a_change_inside_it(self):
        epic, action = self.fix_owed_after_a_task_that_renamed({})
        branch = self.metadata(epic)["factory.branch"]
        head = test_validation.git(self.repo, "rev-parse", branch)
        self.rename_in(Path(action["worktree"]), SPEC, "till.feature")

        done = self.report_fix(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"changed paths inside an acceptance folder: {SPEC}", done.stderr)
        self.assertEqual(head, test_validation.git(self.repo, "rev-parse", branch))


class RenamesFoundWithCopiesTests(RenamedFileTests, RenameCase):
    RENAMES = "copies"


class RenamesNotFoundTests(RenamedFileTests, RenameCase):
    RENAMES = "false"


if __name__ == "__main__":
    unittest.main()
