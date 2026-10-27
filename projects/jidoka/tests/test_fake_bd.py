import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

RUN_TIMEOUT_SECONDS = 120
SHOWN_FIELDS = ("id", "title", "status", "priority", "issue_type", "assignee", "labels", "metadata", "parent",
                "close_reason", "description")
LINK_FIELDS = ("id", "title", "status", "dependency_type")
COMMENT_FIELDS = ("text", "author")
TESTS_BASE = "4e1d2c3b4a5968778695a4b3c2d1e0f9a8b7c6d5"
TESTS_COMMAND = '"/usr/bin/python3" "/tmp/runner.py" "/tmp/runs" -k test_card'
MISSING = "nope-1"


@dataclass(frozen=True)
class Call:
    """One bd call of the play, with what it printed brought to the fields the scripts read."""
    returncode: int
    printed: object


def committed_repo(repo: Path) -> None:
    fixture.init_repo(repo)
    fixture.run(["git", "config", "user.name", "Jeff Contract"], repo)
    (repo / "README.md").write_text("shop\n", encoding="utf-8")
    fixture.git_commit_all(repo, "Start")


def kept(item: dict, fields: tuple) -> dict:
    return {key: item[key] for key in fields if key in item}


class Play:
    """Runs the bd commands that scheduler.py, handoff.py, targeted_tests.py and merge_gate.py call, in one repo,
    and keeps each output with its bead ids replaced by the role of the bead, so two bds' plays compare."""

    def __init__(self, bd: str, repo: Path):
        self.bd = bd
        self.repo = repo
        self.roles: dict[str, str] = {}
        self.calls: dict[str, Call] = {}

    def named(self, value: object) -> object:
        if isinstance(value, str):
            return self.roles.get(value, value)
        if isinstance(value, list):
            return [self.named(item) for item in value]
        if isinstance(value, dict):
            return {key: self.named(item) for key, item in value.items()}
        return value

    def call(self, step: str, actor: str | None, *args: str) -> subprocess.CompletedProcess:
        env = {key: value for key, value in os.environ.items() if key != "BEADS_ACTOR"}
        if actor is not None:
            env["BEADS_ACTOR"] = actor
        done = subprocess.run([self.bd, *args], capture_output=True, text=True, encoding="utf-8", env=env,
                              cwd=self.repo, timeout=RUN_TIMEOUT_SECONDS)
        self.calls[step] = Call(done.returncode, None)
        return done

    def create(self, step: str, role: str, *flags: str) -> str:
        done = self.call(step, "claude", "create", *flags, "--json")
        created = json.loads(done.stdout)
        self.roles[created["id"]] = role
        self.calls[step] = Call(done.returncode, self.named({"id": created["id"]}))
        return created["id"]

    def show(self, step: str, *ids: str) -> None:
        done = self.call(step, "claude", "show", *ids, "--json")
        shown = [{**kept(bead, SHOWN_FIELDS),
                  "dependencies": sorted((kept(link, LINK_FIELDS) for link in bead.get("dependencies") or []),
                                         key=lambda link: (link["dependency_type"], link["id"]))}
                 for bead in json.loads(done.stdout)] if done.returncode == 0 else None
        self.calls[step] = Call(done.returncode, self.named(shown))

    def listed(self, step: str, parent: str) -> None:
        done = self.call(step, "claude", "list", "--parent", parent, "--all", "--limit", "0", "--json")
        self.calls[step] = Call(done.returncode, self.named(sorted(item["id"] for item in json.loads(done.stdout))))

    def comments(self, step: str, bead: str) -> None:
        done = self.call(step, "claude", "comments", bead, "--json")
        self.calls[step] = Call(done.returncode,
                                self.named([kept(comment, COMMENT_FIELDS) for comment in json.loads(done.stdout)]))

    def run(self) -> "Play":
        epic = self.create("create an epic", "epic", "--title", "Take card payments", "--type=epic")
        first = self.create("create a task with a label and a priority", "first", "--title", "Read the card",
                            "--type=task", "--parent", epic, "--labels", "human", "--priority", "1")
        second = self.create("create a task", "second", "--title", "Print the receipt", "--type=task",
                             "--parent", epic)
        self.call("make a task wait on another", "claude", "dep", "add", second, "--blocked-by", first)
        self.listed("list the epic's children", epic)
        self.call("hand off the tasks", "Jeff Contract", "update", first, "--set-metadata", "lap.track=simple",
                  "--set-metadata", "lap.area=till")
        self.call("record the epic branch", "Jeff Contract", "update", epic, "--set-metadata",
                  "factory.branch=epic/take-card-payments")
        self.comments("read an epic with no comments", epic)
        self.call("post the task table", "Jeff Contract", "comment", epic, "Handoff: the factory takes the epic.")
        self.call("add the factory label", "Jeff Contract", "label", "add", epic, "factory")
        self.call("take a label off", "claude", "label", "remove", first, "human")
        self.call("claim a task", "claude", "update", second, "--assignee=Jeff Contract")
        self.call("open a lap", "jidoka", "update", first, "--status=in_progress", "--assignee=jidoka",
                  "--set-metadata", "lap.number=1", "--set-metadata", "lap.stage=build",
                  "--set-metadata", "lap.tries=0", "--set-metadata", "lap.workspace=/tmp/shop/.worktrees/lap",
                  "--set-metadata", "lap.slot=1", "--set-metadata", "lap.branch=lap/first")
        self.call("record the targeted tests", "jidoka", "update", first,
                  "--set-metadata", f"tests.command={TESTS_COMMAND}", "--set-metadata", f"tests.base={TESTS_BASE}",
                  "--set-metadata", "tests.result=pass")
        self.call("post a comment as jidoka", "jidoka", "comment", first, "Build try 1 of 3 failed: red.")
        self.call("post a comment with no actor", None, "comment", first, "Looked at it.")
        self.call("park a task", "jidoka", "update", second, "--status=open", "--assignee=", "--add-label=human",
                  "--set-metadata", "lap.stage=parked", "--set-metadata", "lap.tries=3")
        self.show("show the epic and its tasks", epic, first, second)
        self.comments("read a task's comments", first)
        self.call("close a task", "jidoka", "close", first, "--reason", f"{TESTS_BASE}: merged into epic/take")
        self.call("mark the lap merged", "jidoka", "update", first, "--set-metadata", "lap.stage=merged")
        self.show("show a closed task and the task that waited on it", first, second)
        self.listed("list the children with a closed one", epic)
        self.show("show a bead that does not exist", MISSING)
        return self


class FakeBdContractTests(unittest.TestCase):
    """The commands the scheduler, the targeted tests and the merge gate call, run once against real bd in a stealth
    beads workspace and once against the fake bd, so the fake those scripts' tests use cannot drift from bd."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name).resolve()
        real_repo, fake_repo = root / "real", root / "fake"
        committed_repo(real_repo)
        fixture.add_stealth_beads(real_repo)
        committed_repo(fake_repo)
        fake = fixture.add_fake_beads(fake_repo, root / "bin")
        cls.real = Play(fixture.real_tool("bd"), real_repo).run()
        cls.fake = Play(str(fake), fake_repo).run()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def assert_same(self, step: str) -> None:
        real, fake = self.real.calls[step], self.fake.calls[step]
        self.assertEqual(json.dumps(real.printed, sort_keys=True, indent=1),
                         json.dumps(fake.printed, sort_keys=True, indent=1), step)
        self.assertEqual(real.returncode, fake.returncode, step)

    def test_every_write_the_scripts_make_succeeds_on_both(self):
        self.assertEqual({step: call.returncode for step, call in self.real.calls.items() if call.printed is None
                          and step != "show a bead that does not exist"},
                         {step: call.returncode for step, call in self.fake.calls.items() if call.printed is None
                          and step != "show a bead that does not exist"})
        self.assertEqual({0}, {call.returncode for step, call in self.fake.calls.items()
                               if step != "show a bead that does not exist"})

    def test_create_prints_the_new_bead_s_id(self):
        for step in ("create an epic", "create a task with a label and a priority", "create a task"):
            self.assert_same(step)

    def test_a_task_s_id_is_its_epic_s_id_and_a_number(self):
        def children(play: Play) -> list[str]:
            [epic] = [bead for bead, role in play.roles.items() if role == "epic"]
            return sorted(bead.removeprefix(epic) for bead, role in play.roles.items() if role != "epic")

        self.assertEqual(children(self.real), children(self.fake))

    def test_show_prints_the_fields_the_scripts_read_metadata_typed_as_bd_types_it(self):
        self.assert_same("show the epic and its tasks")

    def test_a_closed_task_shows_its_close_reason_and_the_task_that_waited_on_it_sees_it_closed(self):
        self.assert_same("show a closed task and the task that waited on it")

    def test_list_of_an_epic_s_children_prints_every_child_closed_ones_too(self):
        self.assert_same("list the epic's children")
        self.assert_same("list the children with a closed one")

    def test_comments_print_each_comment_s_text_and_author(self):
        self.assert_same("read an epic with no comments")
        self.assert_same("read a task's comments")

    def test_show_of_a_bead_that_does_not_exist_fails(self):
        self.assertNotEqual(0, self.real.calls["show a bead that does not exist"].returncode)
        self.assertNotEqual(0, self.fake.calls["show a bead that does not exist"].returncode)


class FakeBdRefusalTests(unittest.TestCase):
    """The fake bd fails loudly on a call the scripts do not make, so a new call cannot pass unchecked."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name).resolve()
        cls.repo = root / "shop"
        committed_repo(cls.repo)
        cls.fake = str(fixture.add_fake_beads(cls.repo, root / "bin"))
        cls.task = json.loads(fixture.run([cls.fake, "create", "--title", "Read the card", "--type=task", "--json"],
                                          cls.repo))["id"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def bd(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.fake, *args], capture_output=True, text=True, encoding="utf-8", cwd=self.repo,
                              timeout=RUN_TIMEOUT_SECONDS)

    def test_a_subcommand_the_scripts_do_not_call_fails_naming_it(self):
        done = self.bd("ready", "--json")

        self.assertEqual(1, done.returncode)
        self.assertIn("ready", done.stderr)

    def test_a_flag_the_scripts_do_not_pass_fails_naming_it(self):
        done = self.bd("update", self.task, "--claim")

        self.assertEqual(1, done.returncode)
        self.assertIn("--claim", done.stderr)
        self.assertNotIn("assignee", json.loads(self.bd("show", self.task, "--json").stdout)[0])

    def test_show_without_json_fails(self):
        done = self.bd("show", self.task)

        self.assertEqual(1, done.returncode)
        self.assertIn("--json", done.stderr)

    def test_a_call_outside_a_repo_with_a_fake_beads_store_fails(self):
        done = subprocess.run([self.fake, "show", self.task, "--json"], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.repo.parent, timeout=RUN_TIMEOUT_SECONDS)

        self.assertEqual(1, done.returncode)
        self.assertIn("store", done.stderr)


if __name__ == "__main__":
    unittest.main()
