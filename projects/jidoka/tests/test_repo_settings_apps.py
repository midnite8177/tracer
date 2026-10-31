import sys
import unittest
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

sys.path.insert(0, str(fixture.PROJECT / "plugin" / "jidoka" / "scripts"))
from repo_settings import hand_run_groups  # noqa: E402
from settings_reader import SettingsError, apps_of, settings_of  # noqa: E402


def stored_app(**changes) -> dict:
    app = {"name": "tool", "kind": "program", "way_in": "run tool", "build": "make", "run": "./tool",
           "test": "pytest", "test_full": "-q", "test_target": "-k", "hand_run": [], "acceptance": "specs"}
    return {**app, **changes}


class HandRunGroupsTests(unittest.TestCase):
    GROUP = {"name": "slow", "exclusion": "-m slow", "command": "pytest -m slow", "reason": "it takes minutes"}

    def test_reads_back_the_list_it_stores(self):
        groups = hand_run_groups(apps_of({"apps": [stored_app(hand_run=[self.GROUP])]}))
        stored = {"hand_run": [asdict(group) for group in groups]}

        self.assertEqual(tuple(groups), settings_of(stored, Path("settings.json")).hand_run())

    def test_refuses_stored_settings_that_hold_no_usable_hand_run_list(self):
        group = {"app": "tool", "name": "slow", "reason": "it takes minutes", "command": "pytest -m slow"}
        for settings in ({}, {"hand_run": "none"}, {"hand_run": ["slow"]}, {"hand_run": [{**group, "command": 3}]},
                         {"hand_run": [{key: value for key, value in group.items() if key != "app"}]}):
            with self.subTest(settings=settings), self.assertRaisesRegex(SettingsError, "no hand_run list.*onboard"):
                settings_of(settings, Path("settings.json")).hand_run()


if __name__ == "__main__":
    unittest.main()
