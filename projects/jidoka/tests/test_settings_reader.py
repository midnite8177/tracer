import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

sys.path.insert(0, str(fixture.PROJECT / "plugin" / "jidoka" / "scripts"))
from settings_reader import (App, HandRun, HandRunGroup, Settings, SettingsError, SuiteCommand, apps_of,  # noqa: E402
                             find_settings, problems_of_app, read_settings, read_stored, require_stored, settings_of,
                             settings_path)


def stored_app(**changes) -> dict:
    app = {"name": "tool", "kind": "program", "way_in": "run tool", "build": "make", "run": "./tool",
           "test": "pytest", "test_full": "-q", "test_target": "-k", "hand_run": [], "acceptance": "specs",
           "spec_command": "pytest specs", "spec_target": "-k <spec>", "spec_seconds_limit": 12.5}
    return {**app, **changes}


class AppsOfTests(unittest.TestCase):
    def test_gives_every_field_of_an_app_the_settings_hold(self):
        group = {"name": "slow", "exclusion": "-m slow", "command": "pytest -m slow", "reason": "it takes minutes"}
        settings = {"apps": [stored_app(hand_run=[group])]}

        self.assertEqual(
            [App(name="tool", kind="program", build="make", run="./tool", test="pytest", test_full="-q",
                 test_target="-k", way_in="run tool", acceptance="specs",
                 spec_command="pytest specs", spec_target="-k <spec>", spec_seconds_limit=12.5,
                 hand_run=(HandRun(name="slow", exclusion="-m slow", command="pytest -m slow",
                                   reason="it takes minutes"),))],
            apps_of(settings))

    def test_gives_none_for_what_an_app_has_not_and_no_hand_run_groups(self):
        settings = {"apps": [stored_app(build=None, run=None, test=None, test_full=None, test_target=None,
                                        way_in=None, acceptance=None, spec_command=None,
                                        spec_target=None, spec_seconds_limit=None)]}

        self.assertEqual(
            [App(name="tool", kind="program", build=None, run=None, test=None, test_full=None, test_target=None,
                 way_in=None, acceptance=None, spec_command=None, spec_target=None, spec_seconds_limit=None,
                 hand_run=())],
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


SETTINGS_FILE = Path("repos/shop.json")


def settings_with(**stored) -> Settings:
    return settings_of(stored, SETTINGS_FILE)


class AppNamedTests(unittest.TestCase):
    def test_gives_the_first_app_that_has_the_name(self):
        settings = settings_with(apps=[stored_app(name="a"), stored_app(name="tool")])

        self.assertEqual(settings.apps[1], settings.app_named("tool"))

    def test_finds_no_app_for_a_name_no_app_has_without_refusing(self):
        settings = settings_with(apps=[stored_app(name="a")])

        self.assertEqual((settings.apps[0], None), (settings.find_app("a"), settings.find_app("tool")))

    def test_refuses_a_name_no_app_has_and_lists_the_apps(self):
        settings = settings_with(apps=[stored_app(name="a"), stored_app(name="b")])

        with self.assertRaisesRegex(SettingsError, "no app named 'tool'; the apps are a, b"):
            settings.app_named("tool")

    def test_refuses_an_app_whose_entry_has_a_problem_the_write_refuses(self):
        settings = settings_with(apps=[stored_app(test_target=None)])

        with self.assertRaisesRegex(SettingsError, "app 'tool' are incomplete: .*does not say how to target a test"):
            settings.app_named("tool")


class SettingsFieldsTests(unittest.TestCase):
    GROUP = {"app": "tool", "name": "slow", "reason": "it takes minutes", "command": "pytest -m slow"}
    HAND_RUN = {"name": "slow", "exclusion": "-m slow", "command": "pytest -m slow", "reason": "it takes minutes"}

    def test_gives_the_fields_the_stored_object_holds(self):
        settings = settings_with(apps=[stored_app(hand_run=[self.HAND_RUN]),
                                       stored_app(name="docs", test=None, test_full=None, test_target=None)],
                                 worker_commands=["make build"], slot_use="PORT 5000 plus slot",
                                 lap_limit=3, glossary_and_adrs="private", glossary="GLOSSARY.md",
                                 adrs="docs/adr", lizard_limits={"ccn": 10, "length": 50, "arguments": 4})

        self.assertEqual(["tool", "docs"], [app.name for app in settings.apps])
        self.assertEqual(("make build",), settings.worker_commands)
        self.assertEqual("PORT 5000 plus slot", settings.slot_use)
        self.assertEqual(3, settings.lap_limit)
        self.assertEqual({"ccn": 10, "length": 50, "arguments": 4}, settings.lizard_limits)
        self.assertEqual(("GLOSSARY.md", "docs/adr"), settings.private_docs)
        self.assertEqual(SETTINGS_FILE, settings.path)

    def test_gives_empty_values_for_what_the_stored_object_leaves_out(self):
        settings = settings_with(apps=[stored_app()])

        self.assertEqual((), settings.worker_commands)
        self.assertIsNone(settings.slot_use)
        self.assertEqual(0, settings.lap_limit)
        self.assertEqual({"ccn": 15, "length": 80, "arguments": 6}, settings.lizard_limits)
        self.assertEqual((), settings.private_docs)

    def test_takes_a_lizard_limit_the_settings_hold_wrongly_as_its_default(self):
        settings = settings_with(lizard_limits={"ccn": "ten", "length": 0, "arguments": 4})

        self.assertEqual({"ccn": 15, "length": 80, "arguments": 4}, settings.lizard_limits)

    def test_takes_a_lap_limit_that_is_not_a_whole_number_above_zero_as_none(self):
        for limit in (0, -1, 2.5, True, "3"):
            with self.subTest(limit=limit):
                self.assertEqual(0, settings_with(lap_limit=limit).lap_limit)

    def test_keeps_only_the_worker_commands_that_are_text(self):
        self.assertEqual(("make", "make lint"), settings_with(worker_commands=["make", 3, "make lint"]).worker_commands)

    def test_refuses_a_full_suite_when_no_app_has_a_test_command_in_words_that_point_at_onboarding(self):
        settings = settings_with(apps=[stored_app(test=None, test_full=None, test_target=None)])

        with self.assertRaisesRegex(SettingsError, f"no app in {re.escape(str(SETTINGS_FILE))} has a test command.*onboard"):
            settings.full_suite()

    def test_works_the_derived_lists_out_from_the_apps_and_ignores_the_ones_an_older_write_stored(self):
        settings = settings_with(
            apps=[stored_app(name="first", test="pytest", test_full="-q", hand_run=[self.HAND_RUN]),
                  stored_app(name="docs", test=None, test_full=None, test_target=None),
                  stored_app(name="last", test="make test", test_full=None)],
            full_suite=["stale"], untested_apps=["stale"], hand_run=[self.GROUP])

        self.assertEqual((SuiteCommand("first", "pytest -q"), SuiteCommand("last", "make test")), settings.full_suite())
        self.assertEqual(("docs",), settings.untested_apps())
        self.assertEqual((HandRunGroup("first", "slow", "it takes minutes", "pytest -m slow"),), settings.hand_run())

    def test_gives_no_hand_run_groups_and_no_untested_apps_when_every_app_is_tested_and_runs_whole(self):
        settings = settings_with(apps=[stored_app()])

        self.assertEqual((), settings.hand_run())
        self.assertEqual((), settings.untested_apps())


class StoredSettingsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name) / "home"
        self.main_tree = Path(folder.name) / "shop"

    def store(self, text: str) -> None:
        path = settings_path(self.home, self.main_tree)
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")

    def test_reading_the_stored_object_of_a_repo_with_no_settings_gives_an_empty_object(self):
        self.assertEqual({}, read_stored(self.home, self.main_tree))

    def test_reading_the_stored_object_gives_what_is_stored_for_the_main_tree(self):
        self.store('{"lap_limit": 3}')

        self.assertEqual({"lap_limit": 3}, read_stored(self.home, self.main_tree))

    def test_reading_settings_gives_the_fields_of_what_is_stored_for_the_main_tree(self):
        self.store('{"lap_limit": 3}')

        settings = read_settings(self.home, self.main_tree)

        self.assertEqual(3, settings.lap_limit)
        self.assertEqual(settings_path(self.home, self.main_tree), settings.path)

    def test_finding_the_settings_of_a_repo_with_none_gives_none_and_of_one_with_some_gives_their_fields(self):
        self.assertIsNone(find_settings(self.home, self.main_tree))

        self.store('{"lap_limit": 3}')

        self.assertEqual(3, find_settings(self.home, self.main_tree).lap_limit)

    def test_a_repo_with_no_settings_is_refused_in_the_one_wording_that_points_at_onboarding(self):
        wording = f"no settings for {self.main_tree} in {self.home / 'repos'}. Run /jidoka:onboard to record them"
        for read in (read_settings, require_stored):
            with self.subTest(read=read.__name__), self.assertRaises(SettingsError) as refused:
                read(self.home, self.main_tree)
            self.assertEqual(wording, str(refused.exception))

    def test_a_settings_file_that_holds_an_empty_object_is_refused_in_the_same_words(self):
        self.store("{}")

        with self.assertRaisesRegex(SettingsError, "^no settings for .*Run /jidoka:onboard to record them$"):
            read_settings(self.home, self.main_tree)


if __name__ == "__main__":
    unittest.main()
