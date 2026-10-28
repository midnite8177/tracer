import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
from test_scheduler import SchedulerCase  # noqa: E402


SONNET = "claude-sonnet-4-6"
THREE_DOLLARS = 1_000_000
SIX_DOLLARS = 2_000_000


class BudgetCase(SchedulerCase):
    def spend(self, epic: str, dollars: float) -> None:
        """Puts a running total on an epic that a call without a report reads."""
        fixture.run([self.bd, "update", epic, "--set-metadata", f"spend.dollars={dollars}"], self.repo)

    def leave_tokens(self, agent: str, input_tokens: int) -> None:
        """Leaves the sums the lap mod keeps for an agent that used only input tokens of Sonnet, at three dollars for
        each million."""
        folder = self.home / "tokens"
        folder.mkdir(exist_ok=True)
        (folder / f"{agent}.json").write_text(json.dumps(
            {"model": SONNET, "steps": 1, "input_tokens": input_tokens, "output_tokens": 0,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}), encoding="utf-8")

    def failed_after_spending(self, epic: str, task: str, input_tokens: int) -> dict:
        """Reports the build failed, with a worker whose run the ledger prices at list price."""
        agent = f"agent-{task}-{input_tokens}"
        self.leave_tokens(agent, input_tokens)
        return self.report_printed(epic, task, "failed", "--agent", agent, "--why", "red")

    def machine_default(self, dollars: object) -> None:
        path = self.home / "settings.json"
        path.write_text(json.dumps({"budget": dollars}), encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

    def two_running_laps(self) -> tuple[str, str, str]:
        epic = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        self.hand_off(epic, {first: "till", second: "receipts"})
        self.next_printed(epic)
        return epic, first, second

    def labels(self, bead: str) -> list[str]:
        return self.shown(bead).get("labels") or []

    def parked_comments(self, epic: str) -> list[str]:
        return [text for text in self.texts(epic) if text.startswith("Parked: ")]


class BudgetFromTheRulesTests(BudgetCase):
    def test_an_epic_whose_spend_reaches_its_rule_parks_with_a_comment_naming_the_spend_once_its_running_stages_end(
            self):
        epic, first, second = self.two_running_laps()
        self.rules_set(epic, "budget=5")

        after_first = self.failed_after_spending(epic, first, SIX_DOLLARS)

        self.assertEqual([], after_first["actions"])
        self.assertEqual([second], [lap["task"] for lap in after_first["laps"]])
        self.assertNotIn("human", self.labels(epic))
        self.assertEqual("interrupted", self.metadata(first)["lap.stage"])

        after_second = self.report_printed(epic, second, "failed")

        self.assertEqual(([], []), (after_second["actions"], after_second["laps"]))
        self.assertIn("human", self.labels(epic))
        [comment] = self.parked_comments(epic)
        self.assertIn("$6.00", comment)
        self.assertIn("$5.00", comment)
        self.assertEqual("jidoka", [c for c in self.comments(epic) if c["text"] == comment][0]["author"])

    def test_the_epic_parks_with_a_notification_that_points_at_it(self):
        epic, first, second = self.two_running_laps()
        self.rules_set(epic, "budget=1")
        self.failed_after_spending(epic, first, THREE_DOLLARS)

        done = self.report(epic, second, "failed")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Epic parked", done.stderr)
        self.assertIn(epic, done.stderr)
        self.assertIn(f"epic-parked:{epic}", json.dumps(self.metadata(epic)["notification"]))

    def test_an_epic_under_its_budget_goes_on(self):
        epic, first, second = self.two_running_laps()
        self.rules_set(epic, "budget=5")

        printed = self.failed_after_spending(epic, first, THREE_DOLLARS)

        self.assertEqual(["build"], [action["action"] for action in printed["actions"]])
        self.assertNotIn("human", self.labels(epic))

    def test_a_stage_that_ends_done_at_the_budget_still_merges_and_no_pass_begins(self):
        lap = self.open_one_lap()
        self.rules_set(lap.epic, "budget=2")
        self.leave_tokens("agent-builder", THREE_DOLLARS)
        self.commit_in(lap.worktree, "card.txt", "built\n")

        printed = self.report_printed(lap.epic, lap.task, "done", "--app", "shop", "--filter", "test_card",
                                      "--agent", "agent-builder")

        self.assertEqual("closed", self.shown(lap.task)["status"])
        self.assertEqual(([], []), (printed["actions"], printed["laps"]))
        self.assertIn("human", self.labels(lap.epic))
        self.assertEqual(1, len(self.parked_comments(lap.epic)))

    def test_a_manager_that_starts_at_the_budget_opens_no_lap_and_parks_the_epic(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        self.rules_set(epic, "budget=3")
        self.spend(epic, 3)

        printed = self.next_printed(epic)

        self.assertEqual(([], []), (printed["actions"], printed["laps"]))
        self.assertNotIn("lap.stage", self.metadata(task))
        self.assertIn("human", self.labels(epic))

    def test_a_manager_that_restarts_at_the_budget_ends_the_laps_an_earlier_session_left_and_parks_the_epic(self):
        epic, first, second = self.two_running_laps()
        self.rules_set(epic, "budget=3")
        self.spend(epic, 3)

        printed = self.next_printed(epic)

        self.assertEqual(([], []), (printed["actions"], printed["laps"]))
        self.assertEqual({"interrupted"}, {self.metadata(first)["lap.stage"], self.metadata(second)["lap.stage"]})
        self.assertIn("human", self.labels(epic))

    def test_taking_the_label_off_after_raising_the_budget_lets_the_factory_go_on(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        self.rules_set(epic, "budget=3")
        self.spend(epic, 3)
        self.next_printed(epic)
        self.rules_set(epic, "budget=10")
        fixture.run([self.bd, "label", "remove", epic, "human"], self.repo)

        [action] = self.next_printed(epic)["actions"]

        self.assertEqual(("build", task), (action["action"], action["task"]))

    def test_a_parked_epic_is_not_parked_again_by_a_later_call(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        self.rules_set(epic, "budget=3")
        self.spend(epic, 3)
        self.next_printed(epic)

        self.next_printed(epic)

        self.assertEqual(1, len(self.parked_comments(epic)))


class BudgetFromTheMachineTests(BudgetCase):
    def test_an_epic_with_no_budget_rule_parks_at_the_machines_default(self):
        self.machine_default(4)
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        self.spend(epic, 4.5)

        printed = self.next_printed(epic)

        self.assertEqual([], printed["actions"])
        self.assertIn("human", self.labels(epic))
        [comment] = self.parked_comments(epic)
        self.assertIn("$4.50", comment)
        self.assertIn("$4.00", comment)

    def test_the_epics_rule_wins_over_the_machines_default(self):
        self.machine_default(4)
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        self.rules_set(epic, "budget=100")
        self.spend(epic, 4.5)

        [action] = self.next_printed(epic)["actions"]

        self.assertEqual(task, action["task"])
        self.assertNotIn("human", self.labels(epic))

    def test_an_epic_is_never_parked_for_spend_when_neither_the_rules_nor_the_machine_set_a_budget(self):
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        self.spend(epic, 100000)

        [action] = self.next_printed(epic)["actions"]

        self.assertEqual(task, action["task"])
        self.assertNotIn("human", self.labels(epic))

    def test_a_machine_budget_that_is_not_dollars_sets_no_budget(self):
        self.machine_default({"weekly": 40})
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})
        self.spend(epic, 100)

        [action] = self.next_printed(epic)["actions"]

        self.assertEqual(task, action["task"])

    def test_an_epic_that_has_spent_nothing_is_under_any_budget(self):
        self.machine_default(0.5)
        epic = self.new_epic()
        task = self.new_task_under(epic)
        self.hand_off(epic, {task: "till"})

        [action] = self.next_printed(epic)["actions"]

        self.assertEqual(task, action["task"])


if __name__ == "__main__":
    unittest.main()
