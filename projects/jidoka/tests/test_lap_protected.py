import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_scheduler  # noqa: E402

LAP_PROTECTED = test_scheduler.PLUGIN / "scripts" / "lap_protected.py"
DOCS_APP = {"name": "docs", "kind": "library", "way_in": None, "build": None, "run": None, "test": None,
            "test_target": None, "test_full": None, "hand_run": [], "acceptance": "docs/acceptance"}
NO_ACCEPTANCE_APP = {**DOCS_APP, "name": "tools", "acceptance": None}


class LapProtectedTests(test_scheduler.SchedulerCase):
    def setUp(self):
        self.write_settings({})

    def lap_protected(self, cwd: Path) -> subprocess.CompletedProcess:
        return fixture.run_launcher(test_scheduler.LAUNCHER, [str(LAP_PROTECTED)], None,
                                    self.caller_env(self.home), cwd, test_scheduler.RUN_TIMEOUT_SECONDS)

    def printed(self, cwd: Path) -> list:
        done = self.lap_protected(cwd)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def test_an_ordinary_tasks_lap_is_barred_from_the_acceptance_folder_of_every_app_that_has_one(self):
        lap = self.open_one_lap()
        self.write_settings({"apps": [*self.apps(), DOCS_APP, NO_ACCEPTANCE_APP]})

        self.assertEqual([test_scheduler.ACCEPTANCE, "docs/acceptance"], self.printed(lap.worktree))

    def test_the_spec_tasks_lap_is_barred_from_nothing(self):
        lap = self.open_one_lap()
        fixture.run([self.bd, "update", lap.epic, "--set-metadata", f"acceptance.spec_task={lap.task}"], self.repo)

        self.assertEqual([], self.printed(lap.worktree))

    def test_a_task_that_is_not_the_epics_spec_task_stays_barred_when_the_epic_names_another(self):
        lap = self.open_one_lap()
        other = self.new_task_under(lap.epic)
        fixture.run([self.bd, "update", lap.epic, "--set-metadata", f"acceptance.spec_task={other}"], self.repo)

        self.assertEqual([test_scheduler.ACCEPTANCE], self.printed(lap.worktree))

    def test_a_folder_that_holds_no_tasks_lap_has_no_list_and_exits_with_its_own_code(self):
        done = self.lap_protected(self.repo)

        self.assertEqual(3, done.returncode)
        self.assertEqual("", done.stdout)
        self.assertIn("is not a lap worktree", done.stderr)

    @classmethod
    def apps(cls) -> list[dict]:
        return [{"name": "shop", "kind": "program", "way_in": "its command line", "build": "make", "run": None,
                 "test": cls.test_command, "test_target": "-k <name>", "test_full": None, "hand_run": [],
                 "acceptance": test_scheduler.ACCEPTANCE}]


if __name__ == "__main__":
    unittest.main()
