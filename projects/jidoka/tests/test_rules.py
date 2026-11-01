import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_scheduler  # noqa: E402

sys.path.insert(0, str(test_scheduler.PLUGIN / "scripts"))

import routes  # noqa: E402

LAP_LIMIT = test_scheduler.LAP_LIMIT
FACTORY_SKILL = test_scheduler.PLUGIN / "skills" / "factory" / "SKILL.md"
STAGES_THAT_ONLY_READ = ("research", "app-check", "spec-check", "review")


def stage_tier_rows(skill: str) -> set[tuple[str, str]]:
    """The (stage, tier) pairs of the factory skill's Stages and tiers table."""
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in skill.splitlines()
            if line.startswith("|")]
    start = rows.index(["Stage", "Track", "Tier"]) + 2
    table = []
    for row in rows[start:]:
        if len(row) != 3:
            break
        table.append((row[0], row[2]))
    return set(table)


class TheStagesThatWriteMatchTheFactorySkillTests(unittest.TestCase):
    def test_the_stages_that_write_are_the_rows_of_the_skills_table_that_are_not_read_only(self):
        table = stage_tier_rows(FACTORY_SKILL.read_text(encoding="utf-8"))

        writing = {(stage, tier) for stage, tier in table if not stage.startswith(STAGES_THAT_ONLY_READ)}

        self.assertEqual(set(routes.WRITING_STAGE_TIERS), writing)


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

    def test_a_codex_route_for_a_tier_whose_stages_write_is_refused_and_writes_nothing(self):
        epic = self.handed_off_epic(1)

        done = self.rules("set", epic, 'tier_routes={"deep":"codex"}')

        self.assertEqual(1, done.returncode)
        self.assertIn("deep", done.stderr)
        self.assertIn("codex exec runs read-only review only", done.stderr)
        for stage in ("build", "merge", "test-cleanup"):
            self.assertIn(stage, done.stderr)
        self.assertEqual([], self.rule_comments(epic))
        self.assertNotIn("rules.tier_routes", self.metadata(epic))

    def test_a_stage_moved_onto_a_tier_with_a_codex_route_makes_that_tier_refused(self):
        epic = self.handed_off_epic(1)
        self.rules_set(epic, 'tier_routes={"light":"codex"}')

        done = self.rules("set", epic, 'stage_tiers={"fix":"light"}')

        self.assertEqual(1, done.returncode)
        self.assertIn("light", done.stderr)
        self.assertIn("fix", done.stderr)
        self.assertNotIn("rules.stage_tiers", self.metadata(epic))

    def test_a_stage_that_writes_moved_onto_the_second_tier_is_refused_beside_its_codex_route(self):
        epic = self.handed_off_epic(1)

        done = self.rules("set", epic, 'tier_routes={"second":"codex"}', 'stage_tiers={"build":"second"}')

        self.assertEqual(1, done.returncode)
        self.assertIn("second", done.stderr)
        self.assertIn("build", done.stderr)
        self.assertNotIn("rules.tier_routes", self.metadata(epic))

    def test_a_codex_route_for_the_second_tier_is_accepted(self):
        epic = self.handed_off_epic(1)

        self.rules_set(epic, 'tier_routes={"second":"codex"}')

        shown = json.loads(self.rules("show", epic).stdout)
        self.assertEqual({"second": "codex"}, shown["settings"]["tier_routes"])

    def test_every_setting_is_stored_and_shown_with_one_comment_each(self):
        epic = self.handed_off_epic(1)
        wanted = {"lap_test_scope": "full", "lap_limit": 1, "wall_clocks": {"build": 30}, "passes": 2,
                  "discovered_bugs_into_epic": True, "extra_commands": ["make lint"],
                  "tier_routes": {"deep": "opus-high"}, "stage_tiers": {"build": "deep"}, "budget": 12.5,
                  "reserves": {"home": 0.2}, "commits_on_main": "per_task", "local_trial": True}

        self.rules_set(epic, *(f"{name}={json.dumps(value)}" for name, value in wanted.items()))

        shown = json.loads(self.rules("show", epic).stdout)
        self.assertEqual(wanted, shown["settings"])
        self.assertEqual(len(wanted), len(self.rule_comments(epic)))
        self.assertTrue(all("\n" not in comment["text"] for comment in self.rule_comments(epic)))

    def test_the_local_trial_is_true_or_false_and_nothing_else(self):
        epic = self.handed_off_epic(1)

        done = self.rules("set", epic, "local_trial=yes")

        self.assertEqual(1, done.returncode)
        self.assertIn("local_trial must be true or false", done.stderr)
        self.assertNotIn("rules.local_trial", self.metadata(epic))

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
