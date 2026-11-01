import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_gate  # noqa: E402
import test_gate_page  # noqa: E402
import test_ledger  # noqa: E402
import test_scheduler  # noqa: E402
import test_t3_tidy  # noqa: E402
import test_tidy  # noqa: E402
import test_validation  # noqa: E402

STARTED_AT = 1_800_000_000
CHILD_SECONDS = 90
LOCAL_SECONDS = 95
NATIVE_SECONDS = 40
LOCALLY_TIDIED = "total = 1\n"
NATIVELY_TIDIED = "total = one\n"


def trial_ref(epic: str) -> str:
    return f"refs/jidoka/tidy-trial/{epic}"


class LocalRouteOnOpenCode(test_ledger.LedgerBooks):
    """A home whose local tier is routed to t3 OpenCode."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.home / "settings.json").write_text(test_t3_tidy.settings_with_local_tier(test_t3_tidy.T3_OPENCODE),
                                                encoding="utf-8")

    def local_tier(self, local: dict) -> None:
        (self.home / "settings.json").write_text(test_t3_tidy.settings_with_local_tier(local), encoding="utf-8")


class TheTrialRuns:
    """What a test needs to take an epic on trial through its first pass: a clock the test moves, and the two tidies
    reported one after the other."""

    now = STARTED_AT
    child_wall_seconds = 1_800
    child_asked_for_approval = False

    def caller_env(self, home: Path) -> dict[str, str]:
        return {**super().caller_env(home), "JIDOKA_NOW": str(self.now)}

    def epic_on_trial(self, built: str, text: str) -> tuple[str, str, dict]:
        """An epic with local_trial on whose one task built a file, merged at the start of the clock; returns the
        epic, its branch and the moves printed, which hold the first tidy."""
        epic = self.new_epic()
        task = self.new_task_under(epic)
        branch = self.hand_off(epic, {task: "till"})
        self.rules_set(epic, "local_trial=true")
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), built, text)
        self.now = STARTED_AT
        return epic, branch, test_scheduler.SchedulerCase.build_done(self, epic, task)

    def report_tidy_at(self, epic: str, seconds_after_start: int) -> dict:
        self.now = STARTED_AT + seconds_after_start
        done = self.launch(test_scheduler.SCHEDULER, "report-tidy", epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def run_local_batch_as_child(self, action: dict, reply: str) -> None:
        """Runs the batch through the T3 tidy script, saving the child's last reply where `start` says. The child
        takes CHILD_SECONDS of a stage whose wall clock is `child_wall_seconds`."""
        saved = Path(action["scratch"]) / "action.json"
        saved.write_text(json.dumps(action), encoding="utf-8")
        started = self.launch(test_t3_tidy.T3_TIDY, "start", "--action", str(saved), "--wall-seconds",
                              str(self.child_wall_seconds))
        self.assertEqual(0, started.returncode, started.stderr)
        Path(json.loads(started.stdout)["reply"]).write_text(reply, encoding="utf-8")
        self.now = STARTED_AT + CHILD_SECONDS
        asked = ["--asked-for-approval"] if self.child_asked_for_approval else []
        self.launch(test_t3_tidy.T3_TIDY, "finish", "--scratch", action["scratch"], *asked)

    def tidy_the_trial(self, epic: str, printed: dict, built: str, child_reply: str | None) -> dict:
        """Tidies the file once locally and once natively, with the times of the constants, and returns the moves
        printed after the second tidy. The local batch ran as a T3 child that gave `child_reply`, or never ran as one
        when that is None."""
        [local] = [each for each in printed["actions"] if each["action"] == "tidy"]
        self.leave_in(Path(local["worktree"]), built, LOCALLY_TIDIED)
        if child_reply is not None:
            self.run_local_batch_as_child(local, child_reply)
        between = self.report_tidy_at(epic, LOCAL_SECONDS)
        [native] = [each for each in between["actions"] if each["action"] == "tidy"]
        self.leave_in(Path(native["worktree"]), built, NATIVELY_TIDIED)
        return self.report_tidy_at(epic, LOCAL_SECONDS + NATIVE_SECONDS)

    def ref_head(self, epic: str) -> str | None:
        done = subprocess.run(["git", "rev-parse", "--verify", "--quiet", trial_ref(epic)], cwd=self.repo,
                              capture_output=True, text=True)
        return done.stdout.strip() if done.returncode == 0 else None


class TheFirstPassTidiesTwiceTests(LocalRouteOnOpenCode, TheTrialRuns, test_tidy.TidyCase):
    def test_an_epic_on_trial_is_handed_the_tidy_on_the_local_route_first(self):
        epic, branch, printed = self.epic_on_trial(test_tidy.BUILT_FILE, test_tidy.COMMENTED)

        action = self.tidy_action_of(printed)

        self.assertEqual("local", action["route"])
        self.assertEqual([test_tidy.BUILT_FILE], action["files"])
        self.assertEqual(test_validation.git(self.repo, "rev-parse", branch), action["head"])

    def test_the_local_tidy_is_kept_on_a_ref_of_its_own_and_changes_nothing_on_the_epic_branch(self):
        epic, branch, printed = self.epic_on_trial(test_tidy.BUILT_FILE, test_tidy.COMMENTED)
        head = test_validation.git(self.repo, "rev-parse", branch)
        [local] = self.tidy_actions_of(printed)
        self.leave_in(Path(local["worktree"]), test_tidy.BUILT_FILE, LOCALLY_TIDIED)

        moved = self.report_tidy_at(epic, LOCAL_SECONDS)

        self.assertEqual(head, test_validation.git(self.repo, "rev-parse", branch))
        self.assertEqual(LOCALLY_TIDIED.strip(),
                         test_validation.git(self.repo, "show", f"{trial_ref(epic)}:{test_tidy.BUILT_FILE}"))
        self.assertEqual(head, test_validation.git(self.repo, "rev-parse", f"{trial_ref(epic)}^"))
        self.assertNotIn("tidy.state", self.metadata(epic))
        self.assertEqual([test_tidy.BUILT_FILE], moved["tidy"]["changed"])
        self.assertFalse(Path(local["worktree"]).exists())

    def test_the_native_tidy_follows_from_the_same_head_and_lands_on_the_epic_branch(self):
        epic, branch, printed = self.epic_on_trial(test_tidy.BUILT_FILE, test_tidy.COMMENTED)
        head = test_validation.git(self.repo, "rev-parse", branch)
        [local] = self.tidy_actions_of(printed)
        self.leave_in(Path(local["worktree"]), test_tidy.BUILT_FILE, LOCALLY_TIDIED)

        between = self.report_tidy_at(epic, LOCAL_SECONDS)

        [native] = self.tidy_actions_of(between)
        self.assertEqual(("native", head), (native["route"], native["head"]))
        self.assertEqual("sonnet", native["native_route"]["model"])
        self.assertNotEqual(local["worktree"], native["worktree"])
        self.leave_in(Path(native["worktree"]), test_tidy.BUILT_FILE, NATIVELY_TIDIED)
        after = self.report_tidy_at(epic, LOCAL_SECONDS + NATIVE_SECONDS)
        self.assertEqual(NATIVELY_TIDIED.strip(),
                         test_validation.git(self.repo, "show", f"{branch}:{test_tidy.BUILT_FILE}"))
        self.assertEqual(LOCALLY_TIDIED.strip(),
                         test_validation.git(self.repo, "show", f"{trial_ref(epic)}:{test_tidy.BUILT_FILE}"))
        self.assertEqual("done", self.metadata(epic)["tidy.state"])
        self.assertEqual(["review"] * 4, [each["action"] for each in after["actions"]])

    def test_an_epic_that_has_tidied_on_both_routes_tidies_once_when_its_pass_starts_again(self):
        epic, branch, printed = self.epic_on_trial(test_tidy.BUILT_FILE, test_tidy.COMMENTED)
        self.tidy_the_trial(epic, printed, test_tidy.BUILT_FILE, None)
        self.bd_here("update", epic, "--unset-metadata", "tidy.state")

        again = self.next_printed(epic)

        self.assertNotIn("route", self.tidy_action_of(again))

    def test_an_epic_not_on_trial_hands_out_its_tidy_with_no_route(self):
        _, _, printed = self.finish_epic_whose_task_built_a_commented_file()

        self.assertNotIn("route", self.tidy_action_of(printed))

    def test_only_the_first_pass_is_on_trial(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        self.rules_set(epic, "local_trial=true")
        self.bd_here("update", epic, "--set-metadata", "review.passes=1")
        [action] = self.next_printed(epic)["actions"]
        self.leave_in(Path(action["worktree"]), test_tidy.BUILT_FILE, test_tidy.COMMENTED)

        printed = test_scheduler.SchedulerCase.build_done(self, epic, task)

        self.assertNotIn("route", self.tidy_action_of(printed))


class TheGateShowsBothTidiesTests(LocalRouteOnOpenCode, TheTrialRuns, test_gate_page.GatePageCase):
    def epic_at_the_gate_after_a_trial(self, child_reply: str | None) -> tuple[str, str]:
        number = self.count + 2000
        type(self).count += 1
        built = f"till-{number}.txt"
        epic, branch, printed = self.epic_on_trial(built, test_tidy.COMMENTED)
        after = self.tidy_the_trial(epic, printed, built, child_reply)
        self.settle_tidy_and_review(after)
        self.assertEqual("waiting", self.metadata(epic)["gate.state"])
        return epic, built

    def trial_html(self, epic: str) -> str:
        return test_gate_page.section_of(self.page_for(epic), "Tidy trial")

    def test_the_page_shows_each_tidy_with_its_route_model_wall_time_and_files_changed(self):
        epic, built = self.epic_at_the_gate_after_a_trial(None)

        trial = self.trial_html(epic)

        local, native = trial.split("Native route")
        self.assertIn("Local route", local)
        for text in ("t3", test_t3_tidy.T3_OPENCODE["model"], f"{LOCAL_SECONDS} s", "1 file changed", built):
            self.assertIn(text, local)
        for text in ("claude", "sonnet", f"{NATIVE_SECONDS} s", "1 file changed", built):
            self.assertIn(text, native)

    def test_the_page_shows_the_diff_of_each_tidy_against_the_head_both_started_from(self):
        epic, _ = self.epic_at_the_gate_after_a_trial(None)

        local, native = self.trial_html(epic).split("Native route")

        self.assertIn("-total = 1  # add one", local)
        self.assertIn("+total = 1</span>", local)
        self.assertIn("-total = 1  # add one", native)
        self.assertIn("+total = one</span>", native)
        self.assertNotIn("+total = one", local)

    def test_the_page_says_a_batch_the_local_model_did_was_done_by_the_local_model(self):
        epic, _ = self.epic_at_the_gate_after_a_trial(test_t3_tidy.DONE_REPLY)

        local, native = self.trial_html(epic).split("Native route")

        self.assertIn("Batch 1: the local model did it", local)
        self.assertNotIn("fell back", local)
        self.assertNotIn("Batch 1", native)

    def test_the_page_names_a_batch_whose_child_failed_as_fallen_back_to_sonnet(self):
        epic, _ = self.epic_at_the_gate_after_a_trial("{\"outcome\": \"failed\", \"why\": \"lost the file\"}")

        local, _ = self.trial_html(epic).split("Native route")

        self.assertIn("Batch 1: fell back to Sonnet", local)
        self.assertNotIn("the local model did it", local)

    def test_the_page_names_a_batch_that_never_ran_as_a_child_as_fallen_back_to_sonnet(self):
        epic, _ = self.epic_at_the_gate_after_a_trial(None)

        local, _ = self.trial_html(epic).split("Native route")

        self.assertIn("Batch 1: fell back to Sonnet", local)

    def test_the_page_says_a_batch_whose_child_ran_out_the_wall_clock_was_cut_off_and_counts_it(self):
        self.child_wall_seconds = CHILD_SECONDS - 30
        epic, _ = self.epic_at_the_gate_after_a_trial(test_t3_tidy.DONE_REPLY)

        local, _ = self.trial_html(epic).split("Native route")

        self.assertIn("Batch 1: fell back to Sonnet; its child ran out the wall clock", local)
        self.assertIn("1 of 1 batches ran out the wall clock", local)

    def test_the_page_names_a_batch_whose_child_asked_for_an_approval_as_fallen_back_and_not_cut_off(self):
        self.child_asked_for_approval = True
        epic, _ = self.epic_at_the_gate_after_a_trial(test_t3_tidy.DONE_REPLY)

        local, _ = self.trial_html(epic).split("Native route")

        self.assertIn("Batch 1: fell back to Sonnet", local)
        self.assertNotIn("the local model did it", local)
        self.assertNotIn("ran out the wall clock", local)

    def test_the_page_does_not_call_a_batch_that_failed_before_the_wall_clock_cut_off(self):
        epic, _ = self.epic_at_the_gate_after_a_trial("{\"outcome\": \"failed\", \"why\": \"lost the file\"}")

        local, _ = self.trial_html(epic).split("Native route")

        self.assertNotIn("ran out the wall clock", local)

    def test_the_page_names_the_route_the_local_tidy_was_handed_out_on_whatever_the_settings_say_by_the_settle(self):
        number = self.count + 2000
        type(self).count += 1
        built = f"till-{number}.txt"
        epic, _, printed = self.epic_on_trial(built, test_tidy.COMMENTED)
        self.local_tier({**test_t3_tidy.T3_OPENCODE, "model": "other-model"})
        try:
            after = self.tidy_the_trial(epic, printed, built, None)
        finally:
            self.local_tier(test_t3_tidy.T3_OPENCODE)
        self.settle_tidy_and_review(after)

        local, _ = self.trial_html(epic).split("Native route")

        self.assertIn(test_t3_tidy.T3_OPENCODE["model"], local)
        self.assertNotIn("other-model", local)

    def test_an_epic_that_ran_no_trial_has_no_such_section(self):
        epic, *_ = self.epic_with_changes()

        self.assertNotIn("Tidy trial", self.page_for(epic))

    def test_merging_the_epic_deletes_the_local_tidys_ref(self):
        epic, _ = self.epic_at_the_gate_after_a_trial(None)
        self.assertIsNotNone(self.ref_head(epic))

        done = self.merge(epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIsNone(self.ref_head(epic))

    def test_dropping_the_epic_deletes_the_local_tidys_ref(self):
        epic, _ = self.epic_at_the_gate_after_a_trial(None)
        self.assertIsNotNone(self.ref_head(epic))

        done = self.launch(test_gate.GATE, "drop", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIsNone(self.ref_head(epic))

    def test_dropping_an_epic_with_no_trial_still_succeeds(self):
        epic, _, _ = self.epic_at_the_gate()

        done = self.launch(test_gate.GATE, "drop", epic)

        self.assertEqual(0, done.returncode, done.stderr)


if __name__ == "__main__":
    unittest.main()
