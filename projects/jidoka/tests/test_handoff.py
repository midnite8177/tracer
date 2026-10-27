import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
HANDOFF = PLUGIN / "scripts" / "handoff.py"
HOLDOUTS = PLUGIN / "scripts" / "holdouts.py"
SETTINGS_SCRIPT = PLUGIN / "scripts" / "repo_settings.py"

RUN_TIMEOUT_SECONDS = 120
JEFF = "Jeff Handoff"
SEAMS = "## What\nTake a card.\n\n## Demo\nThe till takes a card.\n\n## Seams\nThe till's command line.\n"


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


def shop_app() -> dict:
    return {"name": "shop", "kind": "program", "way_in": "its command line", "build": "make", "run": None,
            "test": "make test", "test_target": "-k <name>", "test_full": None, "hand_run": []}


class HandoffCase(unittest.TestCase):
    """The shop repo, onboarded in one jidoka home, and the helpers of the handoff script tests."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.repo = cls.root / "shop"
        fixture.init_repo(cls.repo)
        git(cls.repo, "config", "user.name", JEFF)
        (cls.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(cls.repo, "Start")
        git(cls.repo, "branch", "-M", "main")
        cls.bd = fixture.real_tool("bd")
        fixture.add_stealth_beads(cls.repo)
        cls.count = 0
        cls.home = cls.new_home("jidoka-home")
        cls.write_settings(cls.home, [shop_app()])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def new_home(cls, name: str) -> Path:
        home = cls.root / name
        home.mkdir()
        (home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        return home

    @classmethod
    def write_settings(cls, home: Path, apps: list) -> None:
        settings = {"lap_test_scope": "targeted", "worker_commands": [], "slot_use": None, "lap_limit": 1,
                    "apps": apps}
        done = subprocess.run([str(LAUNCHER), str(SETTINGS_SCRIPT), "write"], input=json.dumps(settings),
                              capture_output=True, text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS,
                              env={**os.environ, "JIDOKA_HOME": str(home)}, cwd=cls.repo)
        if done.returncode != 0:
            raise fixture.FixtureError(f"repo_settings.py write failed: {done.stderr}")

    def create(self, title: str, *flags: str) -> str:
        return json.loads(fixture.run([self.bd, "create", "--title", title, *flags, "--json"], self.repo))["id"]

    def new_epic(self) -> tuple[str, str]:
        """A new epic's id and the slug its title gives the epic branch."""
        type(self).count += 1
        return self.create(f"Take card payments {self.count}!", "--type=epic"), f"take-card-payments-{self.count}"

    def new_task_under(self, epic: str) -> str:
        type(self).count += 1
        return self.create(f"Read the card {self.count}", "--type=task", "--parent", epic, "--description", SEAMS)

    def caller_env(self, home: Path) -> dict[str, str]:
        return {**os.environ, "JIDOKA_HOME": str(home), "BEADS_ACTOR": "claude", "BD_DISABLE_EVENT_FLUSH": "1"}

    def handoff(self, *args: str) -> subprocess.CompletedProcess:
        return self.handoff_in(self.home, *args)

    def handoff_in(self, home: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(LAUNCHER), str(HANDOFF), *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS, env=self.caller_env(home),
                              cwd=self.repo)

    def write_holdouts(self, epic: str, holdouts: list) -> None:
        done = subprocess.run([str(LAUNCHER), str(HOLDOUTS), "write", epic], input=json.dumps(holdouts),
                              capture_output=True, text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS,
                              env=self.caller_env(self.home), cwd=self.repo)
        if done.returncode != 0:
            raise fixture.FixtureError(f"holdouts.py write failed: {done.stderr}")

    def shown(self, bead: str) -> dict:
        return json.loads(fixture.run([self.bd, "show", bead, "--json"], self.repo))[0]

    def comments(self, bead: str) -> list[dict]:
        return json.loads(fixture.run([self.bd, "comments", bead, "--json"], self.repo) or "[]") or []

    def branch_exists(self, branch: str) -> bool:
        return subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                              cwd=self.repo, capture_output=True).returncode == 0

    def assert_nothing_written(self, epic: str, tasks: list[str], name: str) -> None:
        shown = self.shown(epic)
        self.assertNotIn("factory", shown.get("labels", []))
        self.assertNotIn("factory.branch", shown.get("metadata") or {})
        self.assertEqual([], self.comments(epic))
        self.assertFalse(self.branch_exists(f"epic/{name}"))
        for task in tasks:
            self.assertNotIn("lap.area", self.shown(task).get("metadata") or {})


class HandoffTakesAnEpicTests(HandoffCase):
    def test_a_passing_epic_gets_the_factory_label_an_epic_branch_from_main_named_from_its_title_and_a_table(self):
        epic, name = self.new_epic()
        first = self.new_task_under(epic)
        second = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{first}=till", "--area", f"{second}=receipts")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("factory", self.shown(epic).get("labels", []))
        self.assertEqual(git(self.repo, "rev-parse", "main"), git(self.repo, "rev-parse", f"epic/{name}"))
        comments = self.comments(epic)
        self.assertEqual(1, len(comments))
        self.assertEqual(JEFF, comments[0]["author"])
        table = comments[0]["text"]
        self.assertIn(f"epic/{name}", table)
        self.assertIn("| Task | Track | Area | State |", table)
        self.assertIn(f"| {first} Read the card {self.count - 1} | simple | till | open |", table)
        self.assertIn(f"| {second} Read the card {self.count} | simple | receipts | open |", table)

    def test_every_task_carries_the_simple_track_and_its_area_in_its_metadata(self):
        epic, _ = self.new_epic()
        first = self.new_task_under(epic)
        second = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{first}=till", "--area", f"{second}=receipts")

        self.assertEqual(0, done.returncode, done.stderr)
        for task, area in ((first, "till"), (second, "receipts")):
            metadata = self.shown(task).get("metadata") or {}
            self.assertEqual(("simple", area), (metadata.get("lap.track"), metadata.get("lap.area")))

    def test_a_closed_task_is_not_handed_off_and_needs_no_area(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)
        done_task = self.new_task_under(epic)
        fixture.run([self.bd, "close", done_task, "--reason", "built at the bench"], self.repo)

        done = self.handoff("take", epic, "--area", f"{task}=till")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([task], [row["id"] for row in json.loads(done.stdout)["tasks"]])
        self.assertNotIn("lap.track", self.shown(done_task).get("metadata") or {})

    def test_a_rerun_after_a_failure_before_the_label_keeps_the_branch_and_posts_no_second_table(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        first = self.handoff("take", epic, "--area", f"{task}=till")
        self.assertEqual(0, first.returncode, first.stderr)
        fixture.run([self.bd, "label", "remove", epic, "factory"], self.repo)

        done = self.handoff("take", epic, "--area", f"{task}=till")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(f"epic/{name}", json.loads(done.stdout)["branch"])
        self.assertIn("factory", self.shown(epic).get("labels", []))
        self.assertEqual(1, len(self.comments(epic)))


class HandoffCheckTests(HandoffCase):
    def test_check_prints_the_epic_branch_and_each_task_with_its_seams_and_writes_nothing(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)

        done = self.handoff("check", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({"epic": epic, "title": f"Take card payments {self.count - 1}!", "branch": f"epic/{name}",
                          "tasks": [{"id": task, "title": f"Read the card {self.count}", "status": "open",
                                     "seams": "The till's command line."}]},
                         json.loads(done.stdout))
        self.assert_nothing_written(epic, [task], name)


class HandoffAreaTests(HandoffCase):
    def test_take_refuses_a_task_with_no_area_and_writes_nothing(self):
        epic, name = self.new_epic()
        first = self.new_task_under(epic)
        second = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{first}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{second} has no area. Pass --area {second}=<area>", done.stderr)
        self.assert_nothing_written(epic, [first, second], name)

    def test_take_refuses_an_area_for_a_bead_that_is_not_a_task_of_the_epic_and_writes_nothing(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        stranger = self.create("Sweep the floor", "--type=task")

        done = self.handoff("take", epic, "--area", f"{task}=till", "--area", f"{stranger}=floor")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"names {stranger}, which is not a task of {epic}", done.stderr)
        self.assert_nothing_written(epic, [task, stranger], name)


class HandoffRefusalTests(HandoffCase):
    def test_refuses_a_task_that_waits_on_an_open_bead_outside_the_epic_naming_both_and_the_fix(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        outside = self.create("Pick a card reader", "--type=task")
        fixture.run([self.bd, "dep", "add", task, "--blocked-by", outside], self.repo)

        done = self.handoff("take", epic, "--area", f"{task}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{task} waits on {outside} (Pick a card reader), an open bead outside {epic}. "
                      f"Close {outside}, move it into the epic, or remove the dependency with "
                      f"bd dep remove {task} {outside}", done.stderr)
        self.assert_nothing_written(epic, [task], name)

    def test_refuses_an_epic_that_waits_on_an_open_bead_outside_it(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        other_epic, _ = self.new_epic()
        fixture.run([self.bd, "dep", "add", epic, "--blocked-by", other_epic], self.repo)

        done = self.handoff("check", epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{epic} waits on {other_epic}", done.stderr)
        self.assert_nothing_written(epic, [task], name)

    def test_a_closed_bead_outside_the_epic_and_a_task_inside_it_do_not_stop_the_handoff(self):
        epic, _ = self.new_epic()
        first = self.new_task_under(epic)
        second = self.new_task_under(epic)
        outside = self.create("Pick a card reader", "--type=task")
        fixture.run([self.bd, "dep", "add", first, "--blocked-by", outside], self.repo)
        fixture.run([self.bd, "close", outside, "--reason", "picked"], self.repo)
        fixture.run([self.bd, "dep", "add", second, "--blocked-by", first], self.repo)

        done = self.handoff("check", epic)

        self.assertEqual(0, done.returncode, done.stderr)

    def test_refuses_an_epic_that_holds_an_epic(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        inner = self.create("Refund a card", "--type=epic", "--parent", epic)

        done = self.handoff("check", epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{epic} holds {inner}, which is an epic. An epic holds only tasks: move {inner} out "
                      "of it, or make it a task", done.stderr)
        self.assert_nothing_written(epic, [task], name)

    def test_refuses_a_task_and_says_to_hand_off_the_epic_that_holds_it(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)

        done = self.handoff("take", task, "--area", f"{task}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{task} is a task, not an epic. Hand off the epic that holds it", done.stderr)
        self.assert_nothing_written(epic, [task], name)

    def test_refuses_an_epic_with_no_tasks(self):
        epic, name = self.new_epic()

        done = self.handoff("take", epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{epic} holds no open tasks. Add its tasks with bd create --parent {epic}", done.stderr)
        self.assert_nothing_written(epic, [], name)

    def test_refuses_a_repo_that_is_not_onboarded_and_says_to_run_onboard(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        bare_home = self.new_home(f"bare-home-{self.count}")

        done = self.handoff_in(bare_home, "take", epic, "--area", f"{task}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn("the repo has no repo settings on this machine. Run /jidoka:onboard, then hand the epic off",
                      done.stderr)
        self.assert_nothing_written(epic, [task], name)

    def test_refuses_while_an_app_has_no_test_command_and_says_how_to_record_one(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        home = self.new_home(f"untested-home-{self.count}")
        editor = {**shop_app(), "name": "editor", "test": None, "test_target": None}
        self.write_settings(home, [shop_app(), editor])

        done = self.handoff_in(home, "take", epic, "--area", f"{task}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn("the app editor has no test command, so the factory cannot test its work. Build a test "
                      "project for it at the bench, then run /jidoka:onboard to record its command", done.stderr)
        self.assert_nothing_written(epic, [task], name)

    def test_refuses_a_holdout_that_names_a_task_outside_the_epic(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        outside = self.create("Sweep the floor", "--type=task")
        self.write_holdouts(epic, [{"app": "shop", "tasks": [task, outside]}])

        done = self.handoff("take", epic, "--area", f"{task}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"a holdout of the app shop names {outside}, which is not a task of {epic}. Move "
                      f"{outside} into the epic, or take it out of the holdout", done.stderr)
        self.assertNotIn(task, done.stderr.replace(f"{task}=", ""))
        self.assert_nothing_written(epic, [task], name)

    def test_refuses_an_epic_the_factory_already_holds(self):
        epic, _ = self.new_epic()
        self.new_task_under(epic)
        fixture.run([self.bd, "label", "add", epic, "factory"], self.repo)

        done = self.handoff("check", epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{epic} already carries the factory label, so the factory holds it. Start it with "
                      f"/jidoka:factory {epic}", done.stderr)
        self.assertEqual([], self.comments(epic))

    def test_refuses_an_app_with_holdouts_and_no_way_in(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        home = self.new_home(f"no-way-in-home-{self.count}")
        self.write_settings(home, [{**shop_app(), "way_in": None}])
        self.write_holdouts(epic, [{"app": "shop", "tasks": [task]}])

        done = self.handoff_in(home, "take", epic, "--area", f"{task}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn("the app shop has holdouts but no way in, so no app check can reach it. Run "
                      "/jidoka:onboard to record how a person or a program reaches it", done.stderr)
        self.assert_nothing_written(epic, [task], name)

    def test_refuses_an_app_with_acceptance_specs_and_no_way_in(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        home = self.new_home(f"specs-home-{self.count}")
        self.write_settings(home, [{**shop_app(), "way_in": None, "acceptance": "acceptance"}])

        done = self.handoff_in(home, "take", epic, "--area", f"{task}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn("the app shop has acceptance specs but no way in", done.stderr)
        self.assert_nothing_written(epic, [task], name)

    def test_refuses_a_holdout_of_an_app_the_repo_settings_do_not_list(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        self.write_holdouts(epic, [{"app": "kiosk", "tasks": [task]}])

        done = self.handoff("check", epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("a holdout reaches the app kiosk, which the repo settings do not list. Run /jidoka:onboard "
                      "to record it with its way in", done.stderr)
        self.assert_nothing_written(epic, [task], name)

    def test_reports_every_failing_check_at_once(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        inner = self.create("Refund a card", "--type=epic", "--parent", epic)
        outside = self.create("Pick a card reader", "--type=task")
        fixture.run([self.bd, "dep", "add", task, "--blocked-by", outside], self.repo)

        done = self.handoff("take", epic)

        self.assertEqual(1, done.returncode)
        for problem in (f"{task} waits on {outside}", f"{epic} holds {inner}", f"{task} has no area"):
            self.assertIn(problem, done.stderr)
        self.assert_nothing_written(epic, [task], name)


class HandoffBranchTests(HandoffCase):
    def test_refuses_an_epic_branch_that_already_exists_and_writes_nothing(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        git(self.repo, "branch", f"epic/{name}")
        self.addCleanup(git, self.repo, "branch", "-D", f"epic/{name}")

        done = self.handoff("take", epic, "--area", f"{task}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"the branch epic/{name} already exists and {epic} does not record it. Retitle the epic "
                      "or delete the branch", done.stderr)
        self.assertEqual([], self.comments(epic))
        self.assertNotIn("lap.area", self.shown(task).get("metadata") or {})

    def test_refuses_a_title_with_no_letters_or_digits(self):
        epic = self.create("?!", "--type=epic")
        task = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{task}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"the title of {epic} has no letters or digits to name its epic branch from", done.stderr)
        self.assertEqual([], self.comments(epic))


class HoldoutsTests(HandoffCase):
    def test_the_stored_holdouts_name_neither_their_app_nor_their_tasks_in_plain_text(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)

        self.write_holdouts(epic, [{"app": "shop", "tasks": [task]}])

        stored = (self.shown(epic).get("metadata") or {}).get("holdouts", "")
        self.assertNotEqual("", stored)
        self.assertNotIn("shop", stored)
        self.assertNotIn(task, stored)


if __name__ == "__main__":
    unittest.main()
