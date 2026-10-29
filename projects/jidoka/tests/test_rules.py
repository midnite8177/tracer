import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_scheduler  # noqa: E402

LAP_LIMIT = test_scheduler.LAP_LIMIT


class FactoryRulesTests(test_scheduler.SchedulerCase):
    def test_a_lap_limit_that_is_not_below_the_repo_settings_is_refused_and_writes_nothing(self):
        epic = self.handed_off_epic(1)

        for higher in (LAP_LIMIT, LAP_LIMIT + 1):
            done = self.rules("set", epic, f"lap_limit={higher}")

            self.assertEqual(1, done.returncode)
            self.assertIn(f"lap_limit must be below the repo's {LAP_LIMIT}", done.stderr)
        self.assertEqual([], self.rule_comments(epic))
        self.assertNotIn("rules.lap_limit", self.metadata(epic))

    def test_a_refusal_names_every_bad_setting_and_writes_none_of_them(self):
        epic = self.handed_off_epic(1)

        done = self.rules("set", epic, "passes=0", "budget=cheap", "colour=red", "lap_limit=1")

        self.assertEqual(1, done.returncode)
        self.assertIn("passes must be a whole number above zero", done.stderr)
        self.assertIn("budget must be a number of dollars above zero", done.stderr)
        self.assertIn("colour is not a setting", done.stderr)
        self.assertEqual([], self.rule_comments(epic))
        self.assertNotIn("rules.lap_limit", self.metadata(epic))

    def test_every_setting_is_stored_and_shown_with_one_comment_each(self):
        epic = self.handed_off_epic(1)
        wanted = {"lap_test_scope": "full", "lap_limit": 1, "wall_clocks": {"build": 30}, "passes": 2,
                  "discovered_bugs_into_epic": True, "extra_commands": ["make lint"],
                  "tier_routes": {"deep": "opus-high"}, "stage_tiers": {"build": "deep"}, "budget": 12.5,
                  "reserves": {"home": 0.2}, "commits_on_main": "per_task"}

        self.rules_set(epic, *(f"{name}={json.dumps(value)}" for name, value in wanted.items()))

        shown = json.loads(self.rules("show", epic).stdout)
        self.assertEqual(wanted, shown["settings"])
        self.assertEqual(len(wanted), len(self.rule_comments(epic)))
        self.assertTrue(all("\n" not in comment["text"] for comment in self.rule_comments(epic)))

    def test_a_bare_word_is_taken_as_text_and_a_change_names_the_value_it_replaced(self):
        epic = self.handed_off_epic(1)

        self.rules_set(epic, "lap_test_scope=full")
        self.rules_set(epic, "lap_test_scope=targeted")

        self.assertEqual(['Factory rules: lap_test_scope set to "full".',
                          'Factory rules: lap_test_scope set to "targeted", was "full".'],
                         [comment["text"] for comment in self.rule_comments(epic)])

    def test_a_setting_already_at_its_value_posts_nothing(self):
        epic = self.handed_off_epic(1)
        self.rules_set(epic, "passes=2")

        printed = self.rules_set(epic, "passes=2")

        self.assertEqual({}, printed["changed"])
        self.assertEqual(1, len(self.rule_comments(epic)))

    def test_choices_list_each_pickable_setting_with_its_choices_and_the_value_the_epic_holds(self):
        epic = self.handed_off_epic(1)
        self.rules_set(epic, "commits_on_main=per_task")

        done = self.rules("choices", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({"epic": epic, "settings": [
            {"name": "lap_test_scope", "choices": ["targeted", "full"], "value": None},
            {"name": "lap_limit", "choices": list(range(1, LAP_LIMIT)), "value": None},
            {"name": "discovered_bugs_into_epic", "choices": [True, False], "value": None},
            {"name": "commits_on_main", "choices": ["one", "per_task"], "value": "per_task"}]},
            json.loads(done.stdout))

    def test_choices_on_a_task_are_refused(self):
        task = self.new_task_under(self.handed_off_epic(1))

        done = self.rules("choices", task)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{task} is a task, not an epic", done.stderr)

    def test_guidance_is_stored_whole_and_its_comment_gives_its_size_not_its_text(self):
        epic = self.handed_off_epic(1)
        text = "Prefer small functions.\nName a test for its behavior.\n"

        done = self.rules("guidance", epic, stdin=text)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(text.strip(), json.loads(self.rules("show", epic).stdout)["guidance"])
        self.assertEqual(["Factory rules: guidance set, 2 lines."],
                         [comment["text"] for comment in self.rule_comments(epic)])

    def test_the_improvement_epic_preset_holds_the_guidance_that_it_changes_nothing_a_user_sees(self):
        epic = self.handed_off_epic(1)

        self.rules_set(epic, "lap_limit=1")
        done = self.rules("preset", epic, "improvement-epic")

        self.assertEqual(0, done.returncode, done.stderr)
        shown = json.loads(self.rules("show", epic).stdout)
        self.assertEqual({"lap_limit": 1}, shown["settings"])
        self.assertEqual("changes nothing a user sees", shown["guidance"])

    def test_the_bug_epic_preset_files_discovered_bugs_into_the_epic_and_commits_once_per_task(self):
        epic = self.handed_off_epic(1)

        done = self.rules("preset", epic, "bug-epic")

        self.assertEqual(0, done.returncode, done.stderr)
        shown = json.loads(self.rules("show", epic).stdout)
        self.assertEqual({"discovered_bugs_into_epic": True, "commits_on_main": "per_task"}, shown["settings"])

    def test_rules_on_a_task_are_refused(self):
        task = self.new_task_under(self.handed_off_epic(1))

        done = self.rules("set", task, "passes=2")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{task} is a task, not an epic", done.stderr)


if __name__ == "__main__":
    unittest.main()
