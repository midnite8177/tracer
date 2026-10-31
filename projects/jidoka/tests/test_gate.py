import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture
import test_scheduler
import test_validation

GATE = test_scheduler.PLUGIN / "scripts" / "gate.py"
T3_WAKE = test_scheduler.PLUGIN / "scripts" / "t3_wake.py"
HOLDOUTS = test_scheduler.PLUGIN / "scripts" / "holdouts.py"
MESSAGE = "Take card payments at the till\n\nThe till reads the card and charges it once."
WAITING_ON_EDITS_EXIT_CODE = 3
FULL_SUITE_FAILED_EXIT_CODE = 5


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


class GateCase(test_validation.ValidationCase):
    """The shop repo with an epic that validation brought to the acceptance gate."""

    def epic_at_the_gate(self) -> tuple[str, str, str]:
        """An epic that waits at the gate; returns the epic, its task and its epic branch. The task's work is a file of
        its own, because the tests share one repo and main keeps what earlier tests landed."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        branch = self.hand_off(epic, {task: "till"})
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), self.work_file(task), "built\n")
        self.build_done(epic, task)
        return epic, task, branch

    def bug_epic_at_the_gate(self, task_count: int) -> tuple[str, list[str], str]:
        """A bug epic whose tasks each leave a file of their own and merge one after the other, brought to the gate;
        returns the epic, its tasks in merge order and its epic branch."""
        epic = self.new_epic()
        tasks = [self.new_task_under(epic) for _ in range(task_count)]
        branch = self.hand_off(epic, {task: f"area-{index}" for index, task in enumerate(tasks)})
        preset = self.rules("preset", epic, "bug-epic")
        self.assertEqual(0, preset.returncode, preset.stderr)
        merged: list[str] = []
        pending = self.lap_actions(self.next_printed(epic))
        while pending:
            action = pending.pop(0)
            self.leave_in(Path(action["worktree"]), self.work_file(action["task"]), "built\n")
            printed = self.build_done(epic, action["task"])
            merged.append(action["task"])
            queued = {each["task"] for each in pending}
            pending += [each for each in self.lap_actions(printed)
                        if each["task"] not in queued and each["task"] not in merged]
        return epic, merged, branch

    def parked_at_the_pass_cap(self, passes: int) -> tuple[str, str, str]:
        """An epic whose first task merged and whose second is still open, parked on the question the pass cap asks
        after the given number of passes; returns the epic, the merged task and the open one."""
        epic, task, _ = self.epic_at_the_gate()
        open_task = self.new_task_under(epic)
        fixture.run([self.bd, "update", epic, "--unset-metadata", "gate.state", "--set-metadata",
                     f"review.passes={passes}", "--set-metadata", f"pass.asked={passes}"], self.repo)
        return epic, task, open_task

    def work_file(self, task: str) -> str:
        return f"{task}.txt"

    def commit_subjects_since(self, commit: str) -> list[str]:
        return git(self.repo, "log", "--reverse", "--format=%s", f"{commit}..main").splitlines()

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

    def test_merge_deletes_the_epic_s_t3_thread_record(self):
        epic, _, _ = self.epic_at_the_gate()
        recorded = self.launch(T3_WAKE, "record", epic, "--thread", "thread-7")
        self.assertEqual(0, recorded.returncode, recorded.stderr)
        self.assertTrue((self.home / "t3-thread" / f"{epic}.json").is_file())

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertFalse((self.home / "t3-thread" / f"{epic}.json").exists())

    def test_merge_retires_the_epic_s_holdouts_and_keeps_its_other_metadata(self):
        epic, task, branch = self.epic_at_the_gate()
        written = fixture.run_launcher(test_scheduler.LAUNCHER, [str(HOLDOUTS), "write", epic],
                                       json.dumps([{"app": "shop", "tasks": [task], "scenario": "Pay 5.00."}]),
                                       self.caller_env(self.home), self.repo, test_scheduler.RUN_TIMEOUT_SECONDS)
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

    def test_a_red_rerun_leaves_main_and_the_epic_branch_alone(self):
        epic, task, branch = self.epic_at_the_gate()
        moved = self.commit_in(self.repo, f"moved-{task}.txt", "main moved\n")
        branch_before = git(self.repo, "rev-parse", branch)
        self.queue_landing_exit_codes(epic, 1)

        done = self.merge(epic)

        self.assertEqual(FULL_SUITE_FAILED_EXIT_CODE, done.returncode)
        self.assertEqual(moved, git(self.repo, "rev-parse", "main"))
        self.assertEqual(branch_before, git(self.repo, "rev-parse", branch))
        self.assertEqual("open", self.shown(epic)["status"])


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


class MergeOfABugEpicTests(GateCase):
    def test_a_bug_epic_of_three_tasks_lands_three_commits_each_with_its_task_s_title_and_file(self):
        epic, tasks, branch = self.bug_epic_at_the_gate(3)
        titles = [self.shown(task)["title"] for task in tasks]
        main_before = git(self.repo, "rev-parse", "main")
        work = git(self.repo, "rev-parse", f"{branch}^{{tree}}")

        done = self.merge(epic)

        landed = git(self.repo, "rev-parse", "main")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(landed, done.stdout.splitlines()[0])
        self.assertEqual(titles, self.commit_subjects_since(main_before))
        commits = reversed(self.commits_on_main_since(main_before))
        self.assertEqual([[self.work_file(task)] for task in tasks],
                         [sorted(git(self.repo, "show", "--format=", "--name-only", commit).splitlines())
                          for commit in commits])
        self.assertEqual(work, git(self.repo, "rev-parse", f"{landed}^{{tree}}"))
        self.assertEqual(("closed", landed), (self.shown(epic)["status"], self.metadata(epic)["gate.landed"]))

    def test_what_a_pass_changed_is_folded_into_the_commit_of_the_task_that_owns_the_file(self):
        epic, tasks, branch = self.bug_epic_at_the_gate(3)
        self.commit_on_epic_branch(branch, self.work_file(tasks[0]), "tidied\n")
        self.commit_on_epic_branch(branch, "tidy-notes.txt", "kept\n")
        main_before = git(self.repo, "rev-parse", "main")
        work = git(self.repo, "rev-parse", f"{branch}^{{tree}}")

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        first, second, third = reversed(self.commits_on_main_since(main_before))
        self.assertEqual(3, len(self.commits_on_main_since(main_before)))
        self.assertEqual("tidied", git(self.repo, "show", f"{first}:{self.work_file(tasks[0])}"))
        self.assertEqual([self.work_file(tasks[1])], self.files_of(second))
        self.assertEqual(sorted([self.work_file(tasks[2]), "tidy-notes.txt"]), self.files_of(third))
        self.assertEqual(work, git(self.repo, "rev-parse", f"{git(self.repo, 'rev-parse', 'main')}^{{tree}}"))
        self.assertEqual(self.commit_subjects_since(main_before),
                         [self.shown(task)["title"] for task in tasks])

    def test_a_bug_epic_that_main_moved_under_runs_the_full_suite_once_on_its_last_commit(self):
        epic, tasks, _ = self.bug_epic_at_the_gate(2)
        main_before = self.commit_in(self.repo, f"moved-{tasks[0]}.txt", "main moved\n")

        done = self.merge(epic)

        landed = git(self.repo, "rev-parse", "main")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(2, len(self.commits_on_main_since(main_before)))
        self.assertEqual([f"{test_validation.SKIP_HAND_RUN} {landed}"], self.landing_runs_of(epic))


class MergeAtThePassCapTests(GateCase):
    def test_an_epic_parked_at_its_pass_cap_with_an_open_task_lands_and_closes(self):
        epic, task, open_task = self.parked_at_the_pass_cap(3)

        done = self.merge(epic)

        landed = git(self.repo, "rev-parse", "main")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("built", (self.repo / self.work_file(task)).read_text(encoding="utf-8").strip())
        self.assertEqual(("closed", landed), (self.shown(epic)["status"], self.metadata(epic)["gate.landed"]))
        self.assertNotIn("human", self.shown(epic).get("labels") or [])
        self.assertNotEqual("closed", self.shown(open_task)["status"])

    def test_the_open_tasks_move_to_a_new_epic_that_carries_no_factory_label(self):
        epic, _, open_task = self.parked_at_the_pass_cap(3)
        title = self.shown(epic)["title"]

        self.merge(epic)

        new_epic = self.bead_titled(f"{title}, the tasks left open")
        shown = self.shown(new_epic)
        self.assertEqual(new_epic, self.metadata(epic)["gate.open_tasks_epic"])
        self.assertEqual(("epic", "open", []), (shown["issue_type"], shown["status"], shown.get("labels") or []))
        self.assertEqual({open_task: new_epic}, {child: self.shown(child)["parent"]
                                                 for child in self.children_of(new_epic).values()})
        self.assertEqual("open", self.shown(open_task)["status"])
        self.assertEqual([], [child for child in self.children_of(epic).values() if child == open_task])

    def test_a_rerun_after_the_landing_makes_no_second_epic_for_the_open_tasks(self):
        epic, _, _ = self.parked_at_the_pass_cap(3)
        title = self.shown(epic)["title"]
        self.merge(epic)

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.bead_titled(f"{title}, the tasks left open")

    def test_an_epic_under_the_pass_cap_that_waits_on_the_human_is_refused_and_main_is_unchanged(self):
        epic, _, open_task = self.parked_at_the_pass_cap(2)
        main_before = git(self.repo, "rev-parse", "main")

        done = self.merge(epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("pass cap", done.stderr)
        self.assertEqual(main_before, git(self.repo, "rev-parse", "main"))
        self.assertEqual(epic, self.shown(open_task)["parent"])

    def test_an_epic_at_the_pass_cap_with_no_open_task_is_refused(self):
        epic, _, open_task = self.parked_at_the_pass_cap(3)
        fixture.run([self.bd, "close", open_task, "--reason", "done"], self.repo)

        done = self.merge(epic)

        self.assertEqual(1, done.returncode)
        self.assertEqual("open", self.shown(epic)["status"])


if __name__ == "__main__":
    unittest.main()
