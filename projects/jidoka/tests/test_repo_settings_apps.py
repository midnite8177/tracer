import sys
import unittest
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

sys.path.insert(0, str(fixture.PROJECT / "plugin" / "jidoka" / "scripts"))
from repo_settings import (App, HandRun, SettingsError, app_named, apps_of,  # noqa: E402
                           hand_run_groups, problems_of_app, stored_hand_run_groups)


def stored_app(**changes) -> dict:
    app = {"name": "tool", "kind": "program", "way_in": "run tool", "build": "make", "run": "./tool",
           "test": "pytest", "test_full": "-q", "test_target": "-k", "hand_run": [], "acceptance": "specs"}
    return {**app, **changes}


class AppsOfTests(unittest.TestCase):
    def test_gives_every_field_of_an_app_the_settings_hold(self):
        group = {"name": "slow", "exclusion": "-m slow", "command": "pytest -m slow", "reason": "it takes minutes"}
        settings = {"apps": [stored_app(hand_run=[group])]}

        self.assertEqual(
            [App(name="tool", kind="program", build="make", run="./tool", test="pytest", test_full="-q",
                 test_target="-k", way_in="run tool", acceptance="specs",
                 hand_run=(HandRun(name="slow", exclusion="-m slow", command="pytest -m slow",
                                   reason="it takes minutes"),))],
            apps_of(settings))

    def test_gives_none_for_what_an_app_has_not_and_no_hand_run_groups(self):
        settings = {"apps": [stored_app(build=None, run=None, test=None, test_full=None, test_target=None,
                                        way_in=None, acceptance=None)]}

        self.assertEqual(
            [App(name="tool", kind="program", build=None, run=None, test=None, test_full=None, test_target=None,
                 way_in=None, acceptance=None, hand_run=())],
            apps_of(settings))

    def test_keeps_the_order_of_the_apps_and_leaves_out_an_entry_that_is_not_an_object(self):
        settings = {"apps": [stored_app(name="b"), "stray", stored_app(name="a")]}

        self.assertEqual(["b", "a"], [app.name for app in apps_of(settings)])

    def test_gives_no_apps_when_the_settings_list_none(self):
        self.assertEqual([], apps_of({}))
        self.assertEqual([], apps_of({"apps": "none"}))


class AppCommandTests(unittest.TestCase):
    def app(self, **changes) -> App:
        [app] = apps_of({"apps": [stored_app(**changes)]})
        return app

    def test_the_full_suite_command_is_the_test_command_followed_by_test_full(self):
        self.assertEqual("pytest -q", self.app().full_suite_command)

    def test_the_full_suite_command_is_the_test_command_alone_when_test_full_is_none(self):
        self.assertEqual("pytest", self.app(test_full=None).full_suite_command)

    def test_the_targeted_command_is_the_test_command_followed_by_test_target(self):
        self.assertEqual("pytest -k", self.app().targeted_command)

    def test_an_app_with_no_test_command_has_neither_command(self):
        app = self.app(test=None, test_full=None, test_target=None)

        self.assertIsNone(app.full_suite_command)
        self.assertIsNone(app.targeted_command)


class ProblemsOfAppTests(unittest.TestCase):
    def test_gives_the_problems_of_the_first_app_that_has_the_name(self):
        settings = {"apps": ["stray", stored_app(name="a"), stored_app(name="tool", test_target=None)]}

        self.assertEqual(["app 'tool' has a test command but does not say how to target a test"],
                         problems_of_app(settings, "tool"))

    def test_gives_none_for_an_app_the_settings_do_not_hold(self):
        self.assertEqual([], problems_of_app({"apps": [stored_app()]}, "other"))
        self.assertEqual([], problems_of_app({}, "tool"))


class AppNamedTests(unittest.TestCase):
    def test_gives_the_first_app_that_has_the_name(self):
        settings = {"apps": [stored_app(name="a"), stored_app(name="tool")]}

        self.assertEqual(apps_of(settings)[1], app_named(settings, "tool"))

    def test_refuses_a_name_no_app_has_and_lists_the_apps(self):
        settings = {"apps": [stored_app(name="a"), stored_app(name="b")]}

        with self.assertRaisesRegex(SettingsError, "no app named 'tool'; the apps are a, b"):
            app_named(settings, "tool")

    def test_refuses_an_app_whose_entry_has_a_problem_the_write_refuses(self):
        settings = {"apps": [stored_app(test_target=None)]}

        with self.assertRaisesRegex(SettingsError, "app 'tool' are incomplete: .*does not say how to target a test"):
            app_named(settings, "tool")


class HandRunGroupsTests(unittest.TestCase):
    GROUP = {"name": "slow", "exclusion": "-m slow", "command": "pytest -m slow", "reason": "it takes minutes"}

    def test_reads_back_the_list_it_stores(self):
        groups = hand_run_groups(apps_of({"apps": [stored_app(hand_run=[self.GROUP])]}))
        stored = {"hand_run": [asdict(group) for group in groups]}

        self.assertEqual(groups, stored_hand_run_groups(stored))

    def test_refuses_stored_settings_that_hold_no_usable_hand_run_list(self):
        group = {"app": "tool", "name": "slow", "reason": "it takes minutes", "command": "pytest -m slow"}
        for settings in ({}, {"hand_run": "none"}, {"hand_run": ["slow"]}, {"hand_run": [{**group, "command": 3}]},
                         {"hand_run": [{key: value for key, value in group.items() if key != "app"}]}):
            with self.subTest(settings=settings), self.assertRaisesRegex(SettingsError, "no hand_run list.*onboard"):
                stored_hand_run_groups(settings)


if __name__ == "__main__":
    unittest.main()
