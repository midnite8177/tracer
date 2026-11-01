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
HOLDOUTS_GUARD = PLUGIN / "hooks" / "holdouts_guard.py"

RUN_TIMEOUT_SECONDS = 120
JEFF = "Jeff Handoff"
PRESETS = {"bug-epic": {"settings": {"discovered_bugs_into_epic": True, "commits_on_main": "per_task"},
                        "guidance": ""},
           "improvement-epic": {"settings": {}, "guidance": "changes nothing a user sees"}}
SCENARIO = "A shopper pays 5.00 with a card and the till prints receipt 1."
SPEC = "## Problem Statement\nA shopper cannot pay by card.\n\n## Solution\nThe till takes a card and prints `receipt 1`."
OUT_OF_SCOPE = "## Out of Scope\nRefunds and tips."
SEAMS = "## What\nTake a card.\n\n## Demo\nThe till takes a card.\n\n## Seams\nThe till's command line.\n"


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


def shop_app() -> dict:
    return {"name": "shop", "kind": "program", "way_in": "its command line", "build": "make", "run": None,
            "test": "make test", "test_target": "-k <name>", "test_full": None, "hand_run": []}


class HandoffCase(unittest.TestCase):
    """The shop repo, onboarded in one jidoka home, with the fake bd first on its scripts' PATH, and the helpers of
    the handoff script tests."""

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
        cls.bin = cls.root / "bin"
        cls.bd = str(fixture.add_fake_beads(cls.repo, cls.bin))
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
        fixture.write_repo_settings(cls.repo, home, settings)

    def create(self, title: str, *flags: str) -> str:
        return json.loads(fixture.run([self.bd, "create", "--title", title, *flags, "--json"], self.repo))["id"]

    def new_epic(self) -> tuple[str, str]:
        """A new epic's id and the slug its title gives the epic branch."""
        type(self).count += 1
        return (self.create(f"Take card payments {self.count}!", "--type=epic", "--description", OUT_OF_SCOPE),
                f"take-card-payments-{self.count}")

    def new_task_under(self, epic: str) -> str:
        type(self).count += 1
        return self.create(f"Read the card {self.count}", "--type=task", "--parent", epic, "--description", SEAMS)

    def caller_env(self, home: Path) -> dict[str, str]:
        return {**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(home), "BEADS_ACTOR": "claude"}

    def handoff(self, *args: str) -> subprocess.CompletedProcess:
        return self.handoff_in(self.home, *args)

    def handoff_in(self, home: Path, *args: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(HANDOFF), *args], None, self.caller_env(home), self.repo,
                                    RUN_TIMEOUT_SECONDS)

    def holdouts(self, mode: str, epic: str, stdin: str = "") -> subprocess.CompletedProcess:
        return self.holdouts_in(self.home, mode, epic, stdin)

    def holdouts_in(self, home: Path, mode: str, epic: str, stdin: str) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(HOLDOUTS), mode, epic], stdin, self.caller_env(home), self.repo,
                                    RUN_TIMEOUT_SECONDS)

    def write_holdouts(self, epic: str, holdouts: list) -> None:
        done = self.holdouts("write", epic, stdin=json.dumps(holdouts))
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
        self.assertIn("| Task | Track | Why | Area | Holdouts | Specs | State |", table)
        self.assertIn(f"| {first} Read the card {self.count - 1} | simple | no holdouts, one seam, no public API "
                      "or type | till | 0 |  | open |", table)
        self.assertIn(f"| {second} Read the card {self.count} | simple | no holdouts, one seam, no public API "
                      "or type | receipts | 0 |  | open |", table)

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


class HandoffPresetTests(HandoffCase):
    def rule_metadata(self, epic: str) -> dict:
        return {key: value for key, value in (self.shown(epic).get("metadata") or {}).items()
                if key.startswith("rules.")}

    def test_taking_with_the_improvement_epic_preset_writes_its_rules_with_one_comment_each_before_the_label(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{task}=till", "--preset", "improvement-epic")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({"rules.guidance": '"changes nothing a user sees"'}, self.rule_metadata(epic))
        texts = [comment["text"] for comment in self.comments(epic)]
        rule_lines = [text for text in texts if text.startswith("Factory rules:")]
        self.assertEqual(1, len(rule_lines))
        self.assertTrue(all("\n" not in line for line in rule_lines))
        self.assertIn("factory", self.shown(epic).get("labels", []))

    def test_taking_without_a_preset_writes_no_rules(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{task}=till")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({}, self.rule_metadata(epic))

    def test_a_preset_outside_the_two_offered_is_a_usage_error_and_writes_nothing(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{task}=till", "--preset", "feature-epic")

        self.assertEqual(2, done.returncode)
        self.assert_nothing_written(epic, [task], name)

    def test_a_rerun_after_a_failure_before_the_label_posts_no_second_comment_for_a_rule_it_already_wrote(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)
        first = self.handoff("take", epic, "--area", f"{task}=till", "--preset", "bug-epic")
        self.assertEqual(0, first.returncode, first.stderr)
        fixture.run([self.bd, "label", "remove", epic, "factory"], self.repo)

        done = self.handoff("take", epic, "--area", f"{task}=till", "--preset", "bug-epic")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(3, len(self.comments(epic)))


class HandoffCheckTests(HandoffCase):
    def test_check_prints_the_epic_branch_and_each_task_with_its_seams_and_writes_nothing(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)

        done = self.handoff("check", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({"epic": epic, "title": f"Take card payments {self.count - 1}!", "branch": f"epic/{name}",
                          "tasks": [{"id": task, "title": f"Read the card {self.count}", "status": "open",
                                     "seams": "The till's command line.", "demo": "The till takes a card.",
                                     "missing": [], "track": "simple",
                                     "why": "no holdouts, one seam, no public API or type", "holdouts": 0,
                                     "specs": []}],
                          "spec_task": "",
                          "presets": PRESETS},
                         json.loads(done.stdout))
        self.assert_nothing_written(epic, [task], name)


class HandoffReadsEachBeadOnceTests(HandoffCase):
    """The fake bd records each call it answers, and the epic here holds two tasks."""

    def calls_of(self, *args: str) -> tuple[subprocess.CompletedProcess, list[list[str]]]:
        before = len(fixture.fake_beads_calls(self.repo))
        done = self.handoff(*args)
        return done, fixture.fake_beads_calls(self.repo)[before:]

    def test_a_check_of_a_two_task_epic_reads_every_bead_at_most_once_between_writes_to_it(self):
        epic, _ = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)

        done, made = self.calls_of("check", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([first, second], [task["id"] for task in json.loads(done.stdout)["tasks"]])
        self.assertEqual([], fixture.repeated_reads(made))

    def test_a_take_of_a_two_task_epic_with_a_preset_reads_every_bead_at_most_once_between_writes_to_it(self):
        epic, _ = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)

        done, made = self.calls_of("take", epic, "--area", f"{first}=till", "--area", f"{second}=receipts",
                                   "--preset", "bug-epic")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], fixture.repeated_reads(made))


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


class HandoffTrackTests(HandoffCase):
    def task_described(self, epic: str, description: str) -> str:
        type(self).count += 1
        return self.create(f"Read the card {self.count}", "--type=task", "--parent", epic, "--description",
                           description)

    def checked_task(self, epic: str, task: str) -> dict:
        done = self.handoff("check", epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return next(row for row in json.loads(done.stdout)["tasks"] if row["id"] == task)

    def test_a_task_a_holdout_names_is_proposed_on_the_full_track_with_the_reason_and_the_rest_on_simple(self):
        epic, _ = self.new_epic()
        held, other = self.new_task_under(epic), self.new_task_under(epic)
        self.write_holdouts(epic, [{"app": "shop", "tasks": [held], "scenario": SCENARIO}])

        done = self.handoff("take", epic, "--area", f"{held}=till", "--area", f"{other}=receipts")

        self.assertEqual(0, done.returncode, done.stderr)
        table = self.comments(epic)[0]["text"]
        self.assertIn(f"| {held} Read the card {self.count - 1} | full | named by 1 holdout | till | 1 |  | open |",
                      table)
        self.assertIn(f"| {other} Read the card {self.count} | simple | no holdouts, one seam, no public API or "
                      "type | receipts | 0 |  | open |", table)
        self.assertEqual("full", self.shown(held)["metadata"]["lap.track"])
        self.assertEqual("simple", self.shown(other)["metadata"]["lap.track"])
        self.assertNotIn(SCENARIO, table)

    def test_check_proposes_the_full_track_for_a_task_that_a_holdout_names_and_counts_its_holdouts(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)
        self.write_holdouts(epic, [{"app": "shop", "tasks": [task], "scenario": SCENARIO},
                                   {"app": "shop", "tasks": [task], "scenario": "A shopper cancels."}])

        row = self.checked_task(epic, task)

        self.assertEqual(("full", "named by 2 holdouts", 2), (row["track"], row["why"], row["holdouts"]))

    def test_a_seams_section_that_names_two_seams_proposes_the_full_track(self):
        epic, _ = self.new_epic()
        task = self.task_described(epic, "## Demo\nThe till takes a card.\n\n## Seams\n- The till's command line\n"
                                         "- The receipt printer\n")

        row = self.checked_task(epic, task)

        self.assertEqual(("full", "its Seams line names 2 seams"), (row["track"], row["why"]))

    def test_a_task_with_no_seams_section_proposes_the_full_track_and_is_listed_as_missing_it(self):
        epic, _ = self.new_epic()
        task = self.task_described(epic, "## Demo\nThe till takes a card.\n")

        row = self.checked_task(epic, task)

        self.assertEqual(("full", "no Seams line", ["seams"]), (row["track"], row["why"], row["missing"]))

    def test_a_task_with_no_demo_section_is_listed_as_missing_it_and_keeps_the_simple_track(self):
        epic, _ = self.new_epic()
        task = self.task_described(epic, "## Seams\nThe till's command line.\n")

        row = self.checked_task(epic, task)

        self.assertEqual(("simple", ["demo"]), (row["track"], row["missing"]))

    def test_a_task_with_neither_section_is_listed_as_missing_both(self):
        epic, _ = self.new_epic()
        task = self.task_described(epic, "Take a card.")

        row = self.checked_task(epic, task)

        self.assertEqual(["demo", "seams"], row["missing"])

    def test_a_task_that_changes_a_public_api_is_never_proposed_on_the_simple_track(self):
        epic, _ = self.new_epic()
        task = self.task_described(epic, "## What\nAdd a public type, Receipt, to the library.\n\n## Demo\n"
                                         "A caller prints a receipt.\n\n## Seams\nThe library's tests.\n")

        row = self.checked_task(epic, task)

        self.assertEqual(("full", "its text names a public API or type"), (row["track"], row["why"]))

    def test_a_seams_section_that_names_the_public_api_as_its_one_seam_does_not_make_the_task_full(self):
        epic, _ = self.new_epic()
        task = self.task_described(epic, "## Demo\nA caller prints a receipt.\n\n## Seams\nThe library's public "
                                         "API.\n")

        row = self.checked_task(epic, task)

        self.assertEqual("simple", row["track"])

    def test_every_reason_for_the_full_track_is_given(self):
        epic, _ = self.new_epic()
        task = self.task_described(epic, "## What\nChange the public API.\n")
        self.write_holdouts(epic, [{"app": "shop", "tasks": [task], "scenario": SCENARIO}])

        row = self.checked_task(epic, task)

        self.assertEqual("named by 1 holdout; its text names a public API or type; no Seams line", row["why"])

    def test_the_human_flips_a_row_and_the_table_and_the_metadata_say_so(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{task}=till", "--track", f"{task}=full")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("full", self.shown(task)["metadata"]["lap.track"])
        self.assertIn("| full | flipped by the human from simple: no holdouts, one seam, no public API or type |",
                      self.comments(epic)[0]["text"])
        self.assertEqual("full", json.loads(done.stdout)["tasks"][0]["track"])

    def test_a_flip_to_the_track_already_proposed_keeps_the_rules_reason(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{task}=till", "--track", f"{task}=simple")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("| simple | no holdouts, one seam, no public API or type |", self.comments(epic)[0]["text"])

    def test_take_refuses_a_track_that_is_neither_simple_nor_full_and_writes_nothing(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{task}=till", "--track", f"{task}=slow")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"--track {task}=slow gives the track slow. Use simple or full", done.stderr)
        self.assert_nothing_written(epic, [task], name)

    def test_take_refuses_a_track_for_a_bead_that_is_not_a_task_of_the_epic_and_writes_nothing(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        stranger = self.create("Sweep the floor", "--type=task")

        done = self.handoff("take", epic, "--area", f"{task}=till", "--track", f"{stranger}=full")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"names {stranger}, which is not a task of {epic}", done.stderr)
        self.assert_nothing_written(epic, [task], name)


class HandoffOutOfScopeTests(HandoffCase):
    def epic_described(self, description: str) -> tuple[str, str]:
        type(self).count += 1
        return (self.create(f"Take card payments {self.count}!", "--type=epic", "--description", description),
                f"take-card-payments-{self.count}")

    def test_an_empty_out_of_scope_section_stops_the_handoff_and_says_what_to_write(self):
        epic, name = self.epic_described("## Problem Statement\nA shopper cannot pay.\n\n## Out of Scope\n\n"
                                         "## Notes\nNone.\n")
        task = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{task}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"the Out of Scope section of the spec of {epic} is empty. Say what the epic leaves out, "
                      f"with bd update {epic} --description", done.stderr)
        self.assert_nothing_written(epic, [task], name)

    def test_a_spec_with_no_out_of_scope_section_stops_the_handoff_and_says_what_to_add(self):
        epic, name = self.epic_described("## Problem Statement\nA shopper cannot pay.\n")
        task = self.new_task_under(epic)

        done = self.handoff("check", epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"the spec of {epic} has no Out of Scope section. Add one that says what the epic leaves "
                      f"out, with bd update {epic} --description", done.stderr)
        self.assert_nothing_written(epic, [task], name)

    def test_an_epic_with_no_description_stops_the_handoff(self):
        epic = self.create("Take cards", "--type=epic")
        self.new_task_under(epic)

        done = self.handoff("check", epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("has no Out of Scope section", done.stderr)

    def test_an_out_of_scope_section_in_any_case_that_says_something_passes(self):
        epic, _ = self.epic_described("## Solution\nTake cards.\n\n## out of scope\nRefunds.\n")
        self.new_task_under(epic)

        done = self.handoff("check", epic)

        self.assertEqual(0, done.returncode, done.stderr)

    def test_an_out_of_scope_line_that_says_something_passes(self):
        epic, _ = self.epic_described("Take cards. Out of scope: refunds and tips.")
        self.new_task_under(epic)

        done = self.handoff("check", epic)

        self.assertEqual(0, done.returncode, done.stderr)

    def test_an_out_of_scope_section_that_ends_the_description_empty_stops_the_handoff(self):
        epic, _ = self.epic_described("## Solution\nTake cards.\n\n## Out of Scope")
        self.new_task_under(epic)

        done = self.handoff("check", epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("Out of Scope section of the spec", done.stderr)
        self.assertIn("is empty", done.stderr)


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
        self.assertIn("no settings for ", done.stderr)
        self.assertIn(". Run /jidoka:onboard to record them", done.stderr)
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
        self.write_holdouts(epic, [{"app": "shop", "tasks": [task, outside], "scenario": SCENARIO}])

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
        self.write_holdouts(epic, [{"app": "shop", "tasks": [task], "scenario": SCENARIO}])

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
        self.write_holdouts(epic, [{"app": "kiosk", "tasks": [task], "scenario": SCENARIO}])

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
        epic = self.create("?!", "--type=epic", "--description", OUT_OF_SCOPE)
        task = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{task}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn(f"the title of {epic} has no letters or digits to name its epic branch from", done.stderr)
        self.assertEqual([], self.comments(epic))


class HoldoutsTests(HandoffCase):
    def test_the_stored_holdouts_name_neither_their_app_nor_their_tasks_in_plain_text(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)

        self.write_holdouts(epic, [{"app": "shop", "tasks": [task], "scenario": SCENARIO}])

        stored = (self.shown(epic).get("metadata") or {}).get("holdouts", "")
        self.assertNotEqual("", stored)
        self.assertNotIn("shop", stored)
        self.assertNotIn(task, stored)
        self.assertNotIn("pays", stored)

    def test_bd_show_prints_the_holdouts_only_as_the_compressed_key(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)

        self.write_holdouts(epic, [{"app": "shop", "tasks": [task], "scenario": SCENARIO}])

        printed = fixture.run([self.bd, "show", epic, "--json"], self.repo)
        self.assertEqual(["holdouts"], list(self.shown(epic)["metadata"]))
        self.assertNotIn(SCENARIO, printed)
        self.assertNotIn("receipt", printed)

    def test_holdouts_read_back_as_they_were_written(self):
        epic, _ = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        written = [{"app": "shop", "tasks": [first], "scenario": SCENARIO},
                   {"app": "shop", "tasks": [first, second], "scenario": "A shopper returns item 7 for 3.50."}]
        self.write_holdouts(epic, written)

        done = self.holdouts("read", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(written, json.loads(done.stdout))

    def test_reading_for_a_task_prints_only_the_holdouts_that_name_it_with_their_numbers_among_all(self):
        epic, _ = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        written = [{"app": "shop", "tasks": [first], "scenario": SCENARIO},
                   {"app": "shop", "tasks": [second], "scenario": "A shopper returns item 7 for 3.50."},
                   {"app": "shop", "tasks": [first, second], "scenario": "A shopper cancels and is charged nothing."}]
        self.write_holdouts(epic, written)

        done = fixture.run_launcher(LAUNCHER, [str(HOLDOUTS), "read", epic, "--task", second], None,
                                    self.caller_env(self.home), self.repo, RUN_TIMEOUT_SECONDS)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([{"holdout": 2, **written[1]}, {"holdout": 3, **written[2]}], json.loads(done.stdout))
        self.assertNotIn(SCENARIO, done.stdout)

    def test_writing_again_replaces_the_holdouts_the_epic_held(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)
        self.write_holdouts(epic, [{"app": "shop", "tasks": [task], "scenario": SCENARIO}])
        replacement = [{"app": "shop", "tasks": [task], "scenario": "A shopper cancels and nothing is charged."}]
        self.write_holdouts(epic, replacement)

        done = self.holdouts("read", epic)

        self.assertEqual(replacement, json.loads(done.stdout))

    def test_an_epic_with_no_holdouts_reads_as_an_empty_list(self):
        epic, _ = self.new_epic()

        done = self.holdouts("read", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], json.loads(done.stdout))

    def test_a_holdout_with_no_scenario_is_refused_and_nothing_is_stored(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)

        done = self.holdouts("write", epic, stdin=json.dumps([{"app": "shop", "tasks": [task]}]))

        self.assertEqual(1, done.returncode)
        self.assertIn("holdout 0 is not an object with an app name, a list of task ids and a scenario", done.stderr)
        self.assertNotIn("holdouts", self.shown(epic).get("metadata") or {})

    def test_a_holdout_that_names_no_task_is_refused_and_nothing_is_stored(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)
        holdouts = [{"app": "shop", "tasks": [task], "scenario": SCENARIO},
                    {"app": "shop", "tasks": [], "scenario": "A shopper pays 2.00 and gets receipt 2."}]

        done = self.holdouts("write", epic, stdin=json.dumps(holdouts))

        self.assertEqual(1, done.returncode)
        self.assertIn("holdout 1 names no task. Name the tasks it exercises", done.stderr)
        self.assertNotIn("holdouts", self.shown(epic).get("metadata") or {})

    def test_holdouts_that_are_not_json_are_refused(self):
        epic, _ = self.new_epic()

        done = self.holdouts("write", epic, stdin="not json")

        self.assertEqual(1, done.returncode)
        self.assertIn("the input is not valid JSON", done.stderr)

    def test_metadata_that_is_not_holdouts_cannot_be_read(self):
        epic, _ = self.new_epic()
        fixture.run([self.bd, "update", epic, "--set-metadata", "holdouts=plain text"], self.repo)

        done = self.holdouts("read", epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("the holdouts metadata cannot be read", done.stderr)


class HoldoutsBriefTests(HandoffCase):
    def test_the_brief_holds_the_epics_spec_and_none_of_its_tasks(self):
        epic = self.create("Take card payments", "--type=epic", "--description", SPEC)
        task = self.new_task_under(epic)

        done = self.holdouts("brief", epic)

        self.assertEqual(0, done.returncode, done.stderr)
        brief = json.loads(done.stdout)
        self.assertEqual((epic, "Take card payments", SPEC), (brief["epic"], brief["title"], brief["spec"]))
        self.assertNotIn(task, done.stdout)
        self.assertNotIn("Read the card", done.stdout)
        self.assertNotIn("The till takes a card.", done.stdout)

    def test_the_brief_lists_each_app_with_its_way_in_and_its_acceptance_specs(self):
        home = self.new_home("brief-home")
        covered = {**shop_app(), "name": "kiosk", "acceptance": "specs/kiosk"}
        self.write_settings(home, [shop_app(), covered])
        epic = self.create("Take card payments", "--type=epic", "--description", SPEC)

        done = self.holdouts_in(home, "brief", epic, "")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([{"name": "shop", "way_in": "its command line", "acceptance": None},
                          {"name": "kiosk", "way_in": "its command line", "acceptance": "specs/kiosk"}],
                         json.loads(done.stdout)["apps"])

    def test_the_brief_stores_no_holdout(self):
        epic = self.create("Take card payments", "--type=epic", "--description", SPEC)

        self.holdouts("brief", epic)

        self.assertNotIn("holdouts", self.shown(epic).get("metadata") or {})


class HoldoutsGuardTests(HandoffCase):
    def guard(self, call: dict) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(HOLDOUTS_GUARD)], json.dumps(call), self.caller_env(self.home),
                                    self.repo, RUN_TIMEOUT_SECONDS)

    def script_call(self, arguments: str = "read tracer-1", **who: str) -> dict:
        command = f"{LAUNCHER} {HOLDOUTS} {arguments}"
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}, **who}

    def assert_denied(self, done: subprocess.CompletedProcess) -> None:
        self.assertEqual(0, done.returncode, done.stderr)
        decision = json.loads(done.stdout)["hookSpecificOutput"]
        self.assertEqual("PreToolUse", decision["hookEventName"])
        self.assertEqual("deny", decision["permissionDecision"])
        self.assertIn("holdouts", decision["permissionDecisionReason"])

    def assert_goes_on(self, done: subprocess.CompletedProcess) -> None:
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)

    def test_a_builder_s_call_of_the_script_is_denied(self):
        self.assert_denied(self.guard(self.script_call(agent_id="a1", agent_type="builder")))

    def test_a_lap_worker_with_no_agent_type_is_denied(self):
        self.assert_denied(self.guard(self.script_call(agent_id="a1")))

    def test_the_app_check_may_read_the_holdouts_that_name_its_task(self):
        reading = "read tracer-1 --task tracer-2"

        self.assert_goes_on(self.guard(self.script_call(reading, agent_id="a2", agent_type="app-check")))
        self.assert_goes_on(self.guard(self.script_call(reading, agent_id="a2", agent_type="jidoka:app-check")))

    def test_the_app_check_may_not_read_every_holdout_or_write_any(self):
        for arguments in ("read tracer-1", "write tracer-1", "brief tracer-1"):
            for agent_type in ("app-check", "jidoka:app-check"):
                self.assert_denied(self.guard(self.script_call(arguments, agent_id="a2", agent_type=agent_type)))

    def test_validation_may_run_the_script(self):
        self.assert_goes_on(self.guard(self.script_call(agent_id="a3", agent_type="validation")))
        self.assert_goes_on(self.guard(self.script_call(agent_id="a3", agent_type="jidoka:validation")))

    def test_the_host_session_may_run_the_script(self):
        self.assert_goes_on(self.guard(self.script_call()))

    def test_a_builder_s_other_commands_go_on(self):
        call = {"tool_name": "Bash", "tool_input": {"command": "make test"}, "agent_id": "a1",
                "agent_type": "builder"}

        self.assert_goes_on(self.guard(call))

    def test_a_builder_s_call_of_another_tool_goes_on(self):
        call = {"tool_name": "Read", "tool_input": {"file_path": "README.md"}, "agent_id": "a1",
                "agent_type": "builder"}

        self.assert_goes_on(self.guard(call))

    def test_a_script_that_only_ends_in_the_same_letters_goes_on(self):
        call = {"tool_name": "Bash", "tool_input": {"command": "python3 myholdouts.py"}, "agent_id": "a1",
                "agent_type": "builder"}

        self.assert_goes_on(self.guard(call))

    def test_input_that_is_not_a_call_goes_on(self):
        done = fixture.run_launcher(LAUNCHER, [str(HOLDOUTS_GUARD)], "not json", self.caller_env(self.home),
                                    self.repo, RUN_TIMEOUT_SECONDS)

        self.assert_goes_on(done)


if __name__ == "__main__":
    unittest.main()
