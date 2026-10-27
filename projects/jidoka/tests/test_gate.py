import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_scheduler  # noqa: E402
import test_validation  # noqa: E402

GATE = test_scheduler.PLUGIN / "scripts" / "gate.py"
HOLDOUTS = test_scheduler.PLUGIN / "scripts" / "holdouts.py"
MESSAGE = "Take card payments at the till\n\nThe till reads the card and charges it once."
WAITING_ON_EDITS_EXIT_CODE = 3
FULL_SUITE_FAILED_EXIT_CODE = 5


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


class GateCase(test_validation.ValidationCase):
    """The shop repo with an epic that validation brought to the acceptance gate."""

    def epic_at_the_gate(self) -> tuple[str, str, str]:
        """An epic that waits at the gate; returns the epic, its task and its epic branch.

        The task's work is a file of its own, because the tests share one repo and main keeps what earlier tests
        landed.
        """
        epic = self.new_epic()
        task = self.new_task_under(epic)
        branch = self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), self.work_file(task), "built\n")
        self.build_done(epic, task)
        return epic, task, branch

    def work_file(self, task: str) -> str:
        return f"{task}.txt"

    def merge(self, epic: str, message: str = MESSAGE) -> subprocess.CompletedProcess:
        return self.launch(GATE, "merge", epic, "--message", message)

    def landing_runs_of(self, epic: str) -> list[str]:
        log = self.runs / f"landing-{epic}.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def commits_on_main_since(self, commit: str) -> list[str]:
        return git(self.repo, "rev-list", f"{commit}..main").splitlines()

    def branches(self) -> list[str]:
        return git(self.repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()

    def queue_landing_exit_codes(self, epic: str, *codes: int) -> None:
        (self.runs / f"exit-codes-landing-{epic}").write_text("\n".join(str(code) for code in codes),
                                                              encoding="utf-8")


class MergeLandsTheEpicTests(GateCase):
    def test_merge_puts_the_epic_on_local_main_as_one_fast_forward_commit_with_the_given_message(self):
        epic, task, branch = self.epic_at_the_gate()
        main_before = git(self.repo, "rev-parse", "main")
        work = git(self.repo, "rev-parse", f"{branch}^{{tree}}")

        done = self.merge(epic)

        landed = git(self.repo, "rev-parse", "main")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(landed, done.stdout.splitlines()[0])
        self.assertEqual([landed], self.commits_on_main_since(main_before))
        self.assertEqual(main_before, git(self.repo, "rev-parse", f"{landed}^"))
        self.assertEqual(MESSAGE, git(self.repo, "log", "-1", "--format=%B", landed))
        self.assertEqual(work, git(self.repo, "rev-parse", f"{landed}^{{tree}}"))
        self.assertEqual("built", (self.repo / self.work_file(task)).read_text(encoding="utf-8").strip())
        self.assertEqual("", git(self.repo, "status", "--porcelain", "--untracked-files=all"))

    def test_merge_retires_the_epic_s_holdouts_and_keeps_its_other_metadata(self):
        epic, task, branch = self.epic_at_the_gate()
        written = subprocess.run([str(test_scheduler.LAUNCHER), str(HOLDOUTS), "write", epic],
                                 input=json.dumps([{"app": "shop", "tasks": [task], "scenario": "Pay 5.00."}]),
                                 capture_output=True, text=True, encoding="utf-8",
                                 timeout=test_scheduler.RUN_TIMEOUT_SECONDS, env=self.caller_env(self.home),
                                 cwd=self.repo)
        self.assertEqual(0, written.returncode, written.stderr)
        self.assertIn("holdouts", self.metadata(epic))

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("closed", self.shown(epic)["status"])
        self.assertNotIn("holdouts", self.metadata(epic))
        self.assertEqual(branch, self.metadata(epic)["factory.branch"])
        read = self.launch(HOLDOUTS, "read", epic)
        self.assertEqual([], json.loads(read.stdout))

    def test_merge_never_pushes(self):
        epic, _, _ = self.epic_at_the_gate()
        remote = self.root / "remote.git"
        git(self.root, "init", "-q", "--bare", str(remote))
        git(self.repo, "remote", "add", "origin", str(remote))
        git(self.repo, "push", "-q", "origin", "main")
        self.addCleanup(lambda: git(self.repo, "remote", "remove", "origin"))
        remote_before = git(remote, "rev-parse", "main")

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(remote_before, git(remote, "rev-parse", "main"))
        self.assertNotEqual(remote_before, git(self.repo, "rev-parse", "main"))

    def test_merge_lists_the_hand_run_tests_after_it_lands(self):
        epic, _, _ = self.epic_at_the_gate()

        done = self.merge(epic)

        self.assertIn(f"{test_validation.HAND_RUN_REASON}\n    {test_validation.HAND_RUN_COMMAND}", done.stdout)

    def test_merge_refuses_a_message_that_names_a_bead_and_changes_nothing(self):
        epic, task, _ = self.epic_at_the_gate()
        main_before = git(self.repo, "rev-parse", "main")

        done = self.merge(epic, f"Take card payments for {task}")

        self.assertEqual(1, done.returncode)
        self.assertIn(task, done.stderr)
        self.assertEqual(main_before, git(self.repo, "rev-parse", "main"))
        self.assertEqual("open", self.shown(epic)["status"])

    def test_merge_refuses_an_epic_that_does_not_wait_at_the_gate(self):
        epic = self.new_epic()
        self.new_task_under(epic)
        main_before = git(self.repo, "rev-parse", "main")

        done = self.merge(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("acceptance gate", done.stderr)
        self.assertEqual(main_before, git(self.repo, "rev-parse", "main"))


class MergeValidationTests(GateCase):
    def test_merge_runs_no_tests_when_main_has_not_moved_since_validation(self):
        epic, _, _ = self.epic_at_the_gate()

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], self.landing_runs_of(epic))
        self.assertEqual(1, len(self.validation_runs_of(epic)))

    def test_merge_reruns_the_full_suite_on_the_rebuilt_commit_when_main_moved_since_validation(self):
        epic, task, _ = self.epic_at_the_gate()
        moved = self.commit_in(self.repo, f"moved-{task}.txt", "main moved\n")

        done = self.merge(epic)

        landed = git(self.repo, "rev-parse", "main")
        files = git(self.repo, "ls-tree", "--name-only", landed).split()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([f"{test_validation.SKIP_HAND_RUN} {landed}"], self.landing_runs_of(epic))
        self.assertEqual(moved, git(self.repo, "rev-parse", f"{landed}^"))
        self.assertIn(f"moved-{task}.txt", files)
        self.assertIn(self.work_file(task), files)

    def test_a_red_rerun_returns_the_epic_to_the_gate_with_a_comment_and_leaves_main_alone(self):
        epic, task, branch = self.epic_at_the_gate()
        moved = self.commit_in(self.repo, f"moved-{task}.txt", "main moved\n")
        self.queue_landing_exit_codes(epic, 1)

        done = self.merge(epic)

        shown = self.shown(epic)
        self.assertEqual(FULL_SUITE_FAILED_EXIT_CODE, done.returncode)
        self.assertEqual(moved, git(self.repo, "rev-parse", "main"))
        self.assertEqual(("open", "waiting"), (shown["status"], shown["metadata"].get("gate.state")))
        self.assertIn("human", shown["labels"])
        self.assertIn("factory", shown["labels"])
        [comment] = [text for text in self.texts(epic) if text.startswith("Landing")]
        self.assertIn("FAIL: test_till_total", comment)
        self.assertIn("waits at the gate again", comment)
        self.assertIn(branch, self.branches())
        self.assertFalse((self.repo / ".worktrees" / f"landing-{epic}").exists())

    def test_the_epic_lands_once_a_green_rerun_follows_the_red_one(self):
        epic, task, _ = self.epic_at_the_gate()
        self.commit_in(self.repo, f"moved-{task}.txt", "main moved\n")
        self.queue_landing_exit_codes(epic, 1)
        self.merge(epic)

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("closed", self.shown(epic)["status"])


class MergeWaitsOnEditsTests(GateCase):
    def test_uncommitted_edits_to_files_the_epic_changed_make_landing_wait_and_name_them(self):
        epic, task, branch = self.epic_at_the_gate()
        main_before = git(self.repo, "rev-parse", "main")
        edited = self.repo / self.work_file(task)
        edited.write_text("my own till\n", encoding="utf-8")
        self.addCleanup(lambda: edited.unlink(missing_ok=True))

        done = self.merge(epic)

        self.assertEqual(WAITING_ON_EDITS_EXIT_CODE, done.returncode)
        self.assertIn(edited.name, done.stdout)
        self.assertEqual(main_before, git(self.repo, "rev-parse", "main"))
        self.assertEqual("my own till\n", edited.read_text(encoding="utf-8"))
        self.assertEqual(("open", True), (self.shown(epic)["status"], branch in self.branches()))

    def test_landing_goes_on_once_the_edits_are_gone(self):
        epic, task, _ = self.epic_at_the_gate()
        edited = self.repo / self.work_file(task)
        edited.write_text("my own till\n", encoding="utf-8")
        self.merge(epic)
        edited.unlink()

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)

    def test_edits_to_files_the_epic_did_not_change_do_not_stop_landing(self):
        epic, _, _ = self.epic_at_the_gate()
        unrelated = self.repo / "notes.txt"
        unrelated.write_text("mine\n", encoding="utf-8")
        self.addCleanup(lambda: unrelated.unlink(missing_ok=True))

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("mine\n", unrelated.read_text(encoding="utf-8"))


class MergeClosesTheEpicTests(GateCase):
    def test_the_epic_closes_with_a_reason_that_names_the_commit_and_loses_its_labels(self):
        epic, _, _ = self.epic_at_the_gate()

        done = self.merge(epic)

        landed = git(self.repo, "rev-parse", "main")
        shown = self.shown(epic)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("closed", shown["status"])
        self.assertIn(landed, shown["close_reason"])
        self.assertNotIn("factory", shown.get("labels") or [])
        self.assertNotIn("human", shown.get("labels") or [])
        self.assertEqual(("merge", landed),
                         (shown["metadata"].get("gate.decision"), shown["metadata"].get("gate.landed")))

    def test_no_epic_or_lap_branch_or_worktree_is_left(self):
        epic, task, branch = self.epic_at_the_gate()
        parked = self.root / f"parked-lap-{task}"
        git(self.repo, "worktree", "add", "-q", "-b", f"lap/{task}", str(parked), "main")
        self.addCleanup(lambda: git(self.repo, "worktree", "prune"))

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], [name for name in self.branches() if name.startswith(("lap/", "epic/"))])
        self.assertNotIn(branch, self.branches())
        self.assertFalse(parked.exists())
        self.assertEqual(1, len(git(self.repo, "worktree", "list").splitlines()))

    def test_a_rerun_on_a_landed_epic_prints_the_same_commit_and_lands_nothing_again(self):
        epic, _, _ = self.epic_at_the_gate()
        self.merge(epic)
        landed = git(self.repo, "rev-parse", "main")

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(landed, done.stdout.splitlines()[0])
        self.assertEqual(landed, git(self.repo, "rev-parse", "main"))


if __name__ == "__main__":
    unittest.main()
