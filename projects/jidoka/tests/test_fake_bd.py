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

import fake_bd  # noqa: E402
import jidoka_fixture as fixture  # noqa: E402

RUN_TIMEOUT_SECONDS = 120
SHOWN_FIELDS = ("id", "title", "status", "priority", "issue_type", "assignee", "labels", "metadata", "parent",
                "close_reason", "description")
LINK_FIELDS = ("id", "title", "status", "dependency_type")
LISTED_FIELDS = ("id", "title", "status", "priority", "issue_type", "assignee", "labels", "metadata", "parent",
                 "description", "close_reason", "dependency_count")
COMMENT_FIELDS = ("text", "author")
NOTE = "## What\nPrint the note.\n\n## Seams\nThe till's command line."
REPLACED = f"{NOTE}\n\n## Acceptance specs\n\n1. A shopper pays by card | and the till prints a receipt"
TESTS_BASE = "4e1d2c3b4a5968778695a4b3c2d1e0f9a8b7c6d5"
TESTS_COMMAND = '"/usr/bin/python3" "/tmp/runner.py" "/tmp/runs" -k test_card'
MISSING = "nope-1"
FAILING_STEPS = {"show a bead that does not exist", "claim a task another actor holds"}


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


def linked_worktree(repo: Path) -> Path:
    """A worktree of the repo beside it, which holds no .beads of its own."""
    worktree = repo.with_name(f"{repo.name}-side")
    fixture.run(["git", "worktree", "add", "-q", "-b", "side", str(worktree)], repo)
    return worktree


def kept(item: dict, fields: tuple) -> dict:
    return {key: item[key] for key in fields if key in item}


class Play:
    """Runs the bd commands that jidoka's scripts and the tests of those scripts call, in one repo and in a linked
    worktree of it, and keeps each output with its bead ids replaced by the role of the bead, so two bds' plays
    compare."""

    def __init__(self, bd: str, repo: Path, worktree: Path):
        self.bd = bd
        self.repo = repo
        self.worktree = worktree
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
        return self.call_in(self.repo, step, actor, *args)

    def call_in(self, cwd: Path, step: str, actor: str | None, *args: str) -> subprocess.CompletedProcess:
        env = {key: value for key, value in os.environ.items() if key != "BEADS_ACTOR"}
        if actor is not None:
            env["BEADS_ACTOR"] = actor
        env = fixture.environment_for(self.bd, env)
        done = subprocess.run([self.bd, *args], capture_output=True, text=True, encoding="utf-8", env=env,
                              cwd=cwd, timeout=RUN_TIMEOUT_SECONDS)
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
        self.calls[step] = Call(done.returncode, sorted(self.named([item["id"] for item in json.loads(done.stdout)])))

    def listed_beads(self, cwd: Path, step: str, *flags: str) -> None:
        done = self.call_in(cwd, step, "claude", "list", *flags, "--json")
        self.calls[step] = Call(done.returncode, sorted((self.named(kept(bead, LISTED_FIELDS))
                                                         for bead in json.loads(done.stdout)),
                                                        key=lambda bead: bead["id"]))

    def ready(self, step: str) -> None:
        done = self.call(step, "claude", "ready", "--json")
        self.calls[step] = Call(done.returncode, sorted(self.named([bead["id"] for bead in json.loads(done.stdout)])))

    def blocked(self, step: str) -> None:
        done = self.call(step, "claude", "blocked", "--json")
        self.calls[step] = Call(done.returncode,
                                sorted(([self.named(bead["id"]), sorted(self.named(bead["blocked_by"]))]
                                        for bead in json.loads(done.stdout))))

    def primed(self, step: str) -> None:
        done = self.call(step, "claude", "prime")
        self.calls[step] = Call(done.returncode, {"printed text": bool(done.stdout.strip())})

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
        found = self.create("create a task in the epic discovered from another", "found", "--title",
                            "Fix the rounding", "--type=task", "--parent", epic, "--description",
                            "Seen while reading the card", "--deps", f"discovered-from:{second}")
        self.show("show a task discovered from another", found)
        twice = self.create("create a task under the epic that names the epic in discovered-from too", "twice",
                            "--title", "Round the total", "--type=task", "--parent", epic, "--description",
                            "Seen while tidying the epic", "--deps", f"discovered-from:{epic}")
        self.show("show a task linked to its epic twice", twice)
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
        self.listed_beads(self.repo, "list the epics that carry a label", "--label", "factory", "--type", "epic",
                          "--limit", "0")
        self.call("label the closed task", "claude", "label", "add", first, "human")
        self.listed_beads(self.repo, "list the tasks that carry a label, closed ones left out", "--label", "human",
                          "--type", "task", "--limit", "0")
        self.call("mark the lap merged", "jidoka", "update", first, "--set-metadata", "lap.stage=merged")
        self.listed_beads(self.repo, "list the epic's children with their fields", "--parent", epic, "--all",
                          "--limit", "0")
        self.show("show a closed task and the task that waited on it", first, second)
        self.listed("list the children with a closed one", epic)
        self.show("show a bead that does not exist", MISSING)
        note = self.create("create a task with a description that waits on an open and a closed bead", "note",
                           "--title", "Print the note", "--type=task", "--description", NOTE,
                           f"--deps={second},{first}")
        loose = self.create("create a task outside the epic", "loose", "--title", "Sweep the floor",
                            "--type=task")
        self.call("claim a task", "Jeff Contract", "update", loose, "--claim")
        self.call("claim a task its actor already holds", "Jeff Contract", "update", loose, "--claim")
        self.call("claim a task another actor holds", "claude", "update", loose, "--claim")
        self.show("show a task with a description and a claimed task", note, loose)
        self.call("replace a task's description", "Jeff Contract", "update", note, f"--description={REPLACED}")
        self.show("show a task whose description was replaced", note)
        self.call("set two metadata keys", "Jeff Contract", "update", loose, "--set-metadata", "holdouts=abc",
                  "--set-metadata", "kept=1")
        self.call("unset a metadata key", "Jeff Contract", "update", loose, "--unset-metadata", "holdouts")
        self.show("show a bead whose metadata key was unset", loose)
        other = self.create("create a second epic", "other", "--title", "Print the receipts", "--type=epic")
        self.call("move a task to another epic", "Jeff Contract", "update", loose, f"--parent={other}")
        self.show("show a moved task and its new epic", loose, other)
        self.listed("list the second epic's children", other)
        self.listed_beads(self.repo, "list the open beads", "--status=open")
        self.listed_beads(self.repo, "list the beads in progress", "--status=in_progress")
        self.listed_beads(self.repo, "list the beads that are not closed")
        self.listed_beads(self.repo, "list every bead", "--all", "--limit", "0")
        self.listed_beads(self.worktree, "list the beads from a linked worktree")
        self.ready("list the ready beads")
        self.blocked("list the blocked beads")
        self.primed("prime a session")
        parked = self.create("create an epic with a label", "parked", "--title", "Park the till", "--type=epic",
                             "--labels", "human")
        self.create("create a task under an epic that carries a label", "inheriting", "--title", "Count the till",
                    "--type=task", "--parent", parked)
        self.create("create a task with a label of its own under an epic that carries a label", "mixed", "--title",
                    "Lock the till", "--type=task", "--parent", parked, "--labels", "urgent")
        self.show("show the tasks created under an epic that carries a label", f"{parked}.1", f"{parked}.2")
        return self


class FakeBdContractTests(unittest.TestCase):
    """The commands jidoka's scripts and their tests call, run once against real bd in a stealth beads workspace and
    once against the fake bd, so the fake those scripts' tests use cannot drift from bd."""

    @classmethod
    def setUpClass(cls):
        root = fixture.bd_folder(cls.addClassCleanup).resolve()
        real_repo, fake_repo = root / "real", root / "fake"
        committed_repo(real_repo)
        fixture.add_stealth_beads(real_repo)
        committed_repo(fake_repo)
        fake = fixture.add_fake_beads(fake_repo, root / "bin")
        cls.real = Play(fixture.real_tool("bd"), real_repo, linked_worktree(real_repo)).run()
        cls.fake = Play(str(fake), fake_repo, linked_worktree(fake_repo)).run()

    def assert_same(self, step: str) -> None:
        real, fake = self.real.calls[step], self.fake.calls[step]
        self.assertEqual(json.dumps(real.printed, sort_keys=True, indent=1),
                         json.dumps(fake.printed, sort_keys=True, indent=1), step)
        self.assertEqual(real.returncode, fake.returncode, step)

    def test_every_write_the_scripts_make_succeeds_on_both(self):
        self.assertEqual({step: call.returncode for step, call in self.real.calls.items() if call.printed is None
                          and step not in FAILING_STEPS},
                         {step: call.returncode for step, call in self.fake.calls.items() if call.printed is None
                          and step not in FAILING_STEPS})
        self.assertEqual({0}, {call.returncode for step, call in self.fake.calls.items()
                               if step not in FAILING_STEPS})

    def test_create_prints_the_new_bead_s_id(self):
        for step in ("create an epic", "create a task with a label and a priority", "create a task"):
            self.assert_same(step)

    def test_a_task_created_under_an_epic_starts_with_the_labels_of_the_epic_besides_its_own(self):
        for step in ("create a task under an epic that carries a label",
                     "create a task with a label of its own under an epic that carries a label",
                     "show the tasks created under an epic that carries a label"):
            self.assert_same(step)
        [inheriting, mixed] = self.fake.calls["show the tasks created under an epic that carries a label"].printed
        self.assertEqual(["human"], inheriting["labels"])
        self.assertEqual(["human", "urgent"], mixed["labels"])

    def test_a_task_s_id_is_its_epic_s_id_and_a_number(self):
        def children(play: Play) -> list[str]:
            [epic] = [bead for bead, role in play.roles.items() if role == "epic"]
            return sorted(bead.removeprefix(epic) for bead, role in play.roles.items() if role in ("first", "second"))

        self.assertEqual(children(self.real), children(self.fake))

    def test_show_prints_the_fields_the_scripts_read_metadata_typed_as_bd_types_it(self):
        self.assert_same("show the epic and its tasks")

    def test_a_metadata_key_that_was_unset_is_gone_and_the_others_stay(self):
        self.assert_same("show a bead whose metadata key was unset")
        [shown] = self.fake.calls["show a bead whose metadata key was unset"].printed
        self.assertEqual({"kept": 1}, shown["metadata"])

    def test_a_closed_task_shows_its_close_reason_and_the_task_that_waited_on_it_sees_it_closed(self):
        self.assert_same("show a closed task and the task that waited on it")

    def test_list_of_an_epic_s_children_prints_every_child_closed_ones_too(self):
        self.assert_same("list the epic's children")
        self.assert_same("list the children with a closed one")

    def test_list_of_an_epic_s_children_prints_each_child_with_its_fields_and_how_many_beads_it_waits_on(self):
        self.assert_same("list the epic's children with their fields")

    def test_comments_print_each_comment_s_text_and_author(self):
        self.assert_same("read an epic with no comments")
        self.assert_same("read a task's comments")

    def test_create_takes_a_description_and_the_beads_the_new_one_waits_on(self):
        self.assert_same("create a task with a description that waits on an open and a closed bead")
        self.assert_same("show a task with a description and a claimed task")

    def test_update_replaces_a_description_that_runs_over_several_lines(self):
        self.assert_same("show a task whose description was replaced")
        [shown] = self.fake.calls["show a task whose description was replaced"].printed
        self.assertEqual(REPLACED, shown["description"])

    def test_a_task_created_discovered_from_another_shows_the_link_and_waits_on_nothing(self):
        self.assert_same("create a task in the epic discovered from another")
        self.assert_same("show a task discovered from another")
        self.assertEqual("discovered-from", next(link["dependency_type"] for link in
                                                 self.fake.calls["show a task discovered from another"]
                                                 .printed[0]["dependencies"] if link["id"] == "second"))

    def test_a_task_under_the_epic_that_names_the_epic_in_discovered_from_too_keeps_only_its_parent_link(self):
        self.assert_same("create a task under the epic that names the epic in discovered-from too")
        self.assert_same("show a task linked to its epic twice")
        self.assertEqual([("parent-child", "epic")],
                         [(link["dependency_type"], link["id"]) for link in
                          self.fake.calls["show a task linked to its epic twice"].printed[0]["dependencies"]])

    def test_a_claim_takes_an_unclaimed_task_or_one_its_actor_holds_and_fails_on_another_actor_s(self):
        for step in ("claim a task", "claim a task its actor already holds", "claim a task another actor holds"):
            self.assert_same(step)
        self.assertNotEqual(0, self.fake.calls["claim a task another actor holds"].returncode)
        self.assert_same("show a task with a description and a claimed task")

    def test_a_task_moved_to_another_epic_keeps_its_id_and_sits_under_the_new_epic(self):
        self.assert_same("show a moved task and its new epic")
        self.assert_same("list the second epic's children")
        self.assertEqual(["loose"], self.fake.calls["list the second epic's children"].printed)

    def test_list_without_a_parent_prints_the_beads_of_the_status_asked_or_else_every_bead_not_closed(self):
        for step in ("list the open beads", "list the beads in progress", "list the beads that are not closed",
                     "list every bead"):
            self.assert_same(step)

    def test_list_with_a_label_and_a_type_prints_the_beads_not_closed_that_carry_the_label_and_have_the_type(self):
        for step in ("list the epics that carry a label", "list the tasks that carry a label, closed ones left out"):
            self.assert_same(step)
        self.assertEqual(1, len(self.fake.calls["list the epics that carry a label"].printed))
        self.assertEqual(1, len(self.fake.calls["list the tasks that carry a label, closed ones left out"].printed))

    def test_a_call_from_a_linked_worktree_reads_the_beads_of_the_main_checkout(self):
        self.assert_same("list the beads from a linked worktree")
        self.assertNotEqual([], self.fake.calls["list the beads from a linked worktree"].printed)

    def test_ready_prints_the_open_beads_that_wait_on_no_open_bead(self):
        self.assert_same("list the ready beads")

    def test_blocked_prints_each_bead_that_waits_on_an_open_bead_with_the_open_beads_it_waits_on(self):
        self.assert_same("list the blocked beads")

    def test_prime_prints_text_and_succeeds(self):
        self.assert_same("prime a session")
        self.assertEqual(Call(0, {"printed text": True}), self.fake.calls["prime a session"])

    def test_show_of_a_bead_that_does_not_exist_fails(self):
        self.assertNotEqual(0, self.real.calls["show a bead that does not exist"].returncode)
        self.assertNotEqual(0, self.fake.calls["show a bead that does not exist"].returncode)


class FakeBdInProcessTests(unittest.TestCase):
    """A test that sets its beads up through the fixture writes the store the fake bd reads, and gets the answers the
    fake bd as a process gives."""

    ACTOR = "Jeff Contract"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def workspace(self, name: str) -> tuple[Path, str]:
        """A committed repo called shop in a folder of its own, with its fake bd; returns the repo and the fake."""
        repo = self.root / name / "shop"
        committed_repo(repo)
        return repo, str(fixture.add_fake_beads(repo, self.root / name / "bin"))

    def as_process(self, fake: str, repo: Path, args: list[str]) -> str:
        return fixture.run_with_env([fake, *args], repo, {**os.environ, "BEADS_ACTOR": self.ACTOR})

    def as_fixture_call(self, fake: str, repo: Path, args: list[str]) -> str:
        return fixture.fake_beads_call(repo, args, self.ACTOR)

    def beads_set_up(self, call) -> dict[str, object]:
        """The calls that set up the beads of a scheduler test, answered by the call function; returns what the ones
        that print an id printed."""
        epic = json.loads(call(["create", "--title", "Take card payments", "--type=epic",
                                "--description", NOTE, "--labels", "factory", "--json"]))["id"]
        first = json.loads(call(["create", "--title", "Read the card", "--type=task", "--parent", epic,
                                 "--priority", "1", "--deps", epic, "--json"]))["id"]
        second = json.loads(call(["create", "--title", "Print the receipt", "--type=task", "--parent", epic,
                                  "--deps", f"discovered-from:{first}", "--json"]))["id"]
        call(["dep", "add", second, "--blocked-by", first])
        call(["label", "add", first, "human"])
        call(["label", "remove", first, "human"])
        call(["comment", first, "research brief: Files to change: till.txt"])
        call(["update", first, "--claim"])
        call(["update", second, "--set-metadata", "lap.area=till", "--set-metadata", "lap.tries=2",
              "--add-label", "urgent"])
        call(["update", epic, "--set-metadata", "pause=1", "--unset-metadata", "pause"])
        call(["close", first, "--reason", "built"])
        return {"epic": epic, "first": first, "second": second}

    def test_the_store_the_fixture_writes_is_the_store_the_fake_bd_writes(self):
        process_repo, process_fake = self.workspace("process")
        fixture_repo, fixture_fake = self.workspace("fixture")

        self.beads_set_up(lambda args: self.as_process(process_fake, process_repo, args))
        self.beads_set_up(lambda args: self.as_fixture_call(fixture_fake, fixture_repo, args))

        self.assertEqual(json.loads((process_repo / fake_bd.STORE).read_text(encoding="utf-8")),
                         json.loads((fixture_repo / fake_bd.STORE).read_text(encoding="utf-8")))

    def test_the_fake_bd_as_a_process_reads_the_beads_the_fixture_wrote_as_the_fixture_reads_them(self):
        repo, fake = self.workspace("reads")
        made = self.beads_set_up(lambda args: self.as_fixture_call(fake, repo, args))

        by_process = self.as_process(fake, repo, ["show", made["epic"], made["first"], made["second"], "--json"])
        by_fixture = self.as_fixture_call(fake, repo, ["show", made["epic"], made["first"], made["second"], "--json"])
        comments = json.loads(self.as_process(fake, repo, ["comments", made["first"], "--json"]))

        self.assertEqual(json.loads(by_process), json.loads(by_fixture))
        self.assertEqual([{"text": "research brief: Files to change: till.txt", "author": self.ACTOR}],
                         [kept(comment, COMMENT_FIELDS) for comment in comments])

    def test_a_call_answers_with_no_fake_bd_to_start(self):
        repo, fake = self.workspace("none")
        Path(fake).unlink()

        made = json.loads(self.as_fixture_call(fake, repo, ["create", "--title", "Read the card", "--json"]))

        self.assertEqual("shop-1", made["id"])

    def test_a_call_the_fake_fails_raises_and_leaves_the_store_as_it_was(self):
        repo, fake = self.workspace("fails")
        store = (repo / fake_bd.STORE).read_text(encoding="utf-8")

        with self.assertRaisesRegex(fixture.FixtureError, "no issue found matching 'shop-9'"):
            self.as_fixture_call(fake, repo, ["close", "shop-9", "--reason", "built"])
        with self.assertRaisesRegex(fixture.FixtureError, "does not answer bd delete"):
            self.as_fixture_call(fake, repo, ["delete", "shop-1"])

        self.assertEqual(store, (repo / fake_bd.STORE).read_text(encoding="utf-8"))


class FakeBdRefusalTests(unittest.TestCase):
    """The fake bd fails on a call the scripts do not make, so a new call cannot pass unchecked."""

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
        done = self.bd("delete", self.task, "--json")

        self.assertEqual(1, done.returncode)
        self.assertIn("delete", done.stderr)
        self.assertEqual(0, self.bd("show", self.task, "--json").returncode)

    def test_a_flag_the_scripts_do_not_pass_fails_naming_it(self):
        done = self.bd("update", self.task, "--assignee", "Jeff Contract", "--notes", "Seen at the till.")

        self.assertEqual(1, done.returncode)
        self.assertIn("--notes", done.stderr)
        self.assertNotIn("assignee", json.loads(self.bd("show", self.task, "--json").stdout)[0])

    def test_a_list_in_a_form_the_scripts_do_not_use_fails(self):
        done = self.bd("list", "--status=open", "--all", "--json")

        self.assertEqual(1, done.returncode)
        self.assertIn("list", done.stderr)

    def test_a_list_by_label_without_a_type_fails(self):
        done = self.bd("list", "--label", "factory", "--limit", "0", "--json")

        self.assertEqual(1, done.returncode)
        self.assertIn("--label", done.stderr)

    def test_show_without_json_fails(self):
        done = self.bd("show", self.task)

        self.assertEqual(1, done.returncode)
        self.assertIn("--json", done.stderr)

    def test_the_fake_records_each_call_it_answers_and_none_it_refuses(self):
        log = self.repo / ".beads" / "fake-bd-calls.jsonl"
        before = log.read_text(encoding="utf-8").splitlines() if log.exists() else []

        self.bd("show", self.task, "--json")
        self.bd("delete", self.task, "--json")
        self.bd("comment", self.task, "Seen at the till.")

        recorded = log.read_text(encoding="utf-8").splitlines()[len(before):]
        self.assertEqual([["show", self.task, "--json"], ["comment", self.task, "Seen at the till."]],
                         [json.loads(line) for line in recorded])

    def test_a_call_outside_a_repo_with_a_fake_beads_store_fails(self):
        done = subprocess.run([self.fake, "show", self.task, "--json"], capture_output=True, text=True,
                              encoding="utf-8", cwd=self.repo.parent, timeout=RUN_TIMEOUT_SECONDS)

        self.assertEqual(1, done.returncode)
        self.assertIn("store", done.stderr)


if __name__ == "__main__":
    unittest.main()
