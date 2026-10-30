import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from html import unescape
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
PARK = PLUGIN / "scripts" / "park.py"
RULES = PLUGIN / "scripts" / "rules.py"
LAP_LISTS = PLUGIN / "scripts" / "lap_lists.py"
SETTINGS_SCRIPT = PLUGIN / "scripts" / "repo_settings.py"

RUN_TIMEOUT_SECONDS = 120
HUMAN = "Pat Human"
CALL = "cd packages/till && make lint --fix"
PATTERN = "make lint"
FOUND = "The build needs make lint, and the lap mod denied it."
ANSWERS = ["epic", "repo", "built-in", "none"]
CHANGES = [("Only this epic's laps may run make lint", "epic", 50),
           ("Every lap in this repo may run make lint", "repo", 30),
           ("Every lap in every repo on this machine may run make lint", "built-in", 5),
           ("No list changes, and no lap may run make lint", "none", 15)]


def report(**changes: object) -> dict:
    options = [{"name": "epic", "confidence": 50}, {"name": "repo", "confidence": 30},
               {"name": "built-in", "confidence": 5}, {"name": "none", "confidence": 15}]
    return {"found": FOUND, "call": CALL, "pattern": PATTERN, "options": options, "recommended": "epic", **changes}


class PermissionCase(unittest.TestCase):
    """A temporary git repo with the fake bd's beads and repo settings, and a temporary jidoka home."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "shop"
        fixture.init_repo(self.repo)
        fixture.run(["git", "config", "user.name", HUMAN], self.repo)
        (self.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Start")
        fixture.run(["git", "branch", "-M", "main"], self.repo)
        self.bin = self.root / "bin"
        self.fake_bd = str(fixture.add_fake_beads(self.repo, self.bin))
        self.home = self.root / "jidoka-home"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        settings = {"lap_test_scope": "targeted", "worker_commands": ["make build"], "slot_use": None,
                    "lap_limit": 2,
                    "apps": [{"name": "shop", "kind": "program", "way_in": "its command line", "build": "make",
                              "run": None, "test": "make test", "test_target": "T=<name>", "test_full": None,
                              "hand_run": [], "acceptance": None}]}
        fixture.write_repo_settings(self.repo, self.home, settings)

    def script(self, script: Path, *args: str, stdin: str | None = None,
               cwd: Path | None = None) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(script), *args], stdin,
                                    {**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
                                     "BEADS_ACTOR": HUMAN}, cwd or self.repo, RUN_TIMEOUT_SECONDS)

    def bd(self, *args: str) -> str:
        return fixture.run([self.fake_bd, *args], self.repo)

    def create(self, title: str, *flags: str) -> str:
        return json.loads(self.bd("create", "--title", title, *flags, "--json"))["id"]

    def new_task(self) -> tuple[str, str]:
        epic = self.create("Take card payments", "--type=epic")
        return epic, self.create("Read the card", "--type=task", "--parent", epic)

    def shown(self, bead: str) -> dict:
        return json.loads(self.bd("show", bead, "--json"))[0]

    def comments(self, bead: str) -> list[dict]:
        return json.loads(self.bd("comments", bead, "--json") or "[]") or []

    def ask(self, task: str, **changes: object) -> subprocess.CompletedProcess:
        scratch = self.root / f"scratch-{task}"
        scratch.mkdir(exist_ok=True)
        (scratch / "question.json").write_text(json.dumps(report(**changes)), encoding="utf-8")
        return self.script(PARK, "question", task, "--scratch", str(scratch), "--worktree",
                           str(self.repo / ".worktrees" / f"lap-{task}"), "--branch", f"lap/{task}", "--tries", "0")

    def asked(self) -> tuple[str, str]:
        epic, task = self.new_task()
        done = self.ask(task)
        self.assertEqual(0, done.returncode, done.stderr)
        return epic, task

    def human_answers(self, task: str, *comments: str) -> None:
        for comment in comments:
            self.bd("comment", task, comment)
        self.bd("label", "remove", task, "human")

    def answer(self, task: str) -> subprocess.CompletedProcess:
        return self.script(PARK, "answer", task)

    def settings_shown(self) -> dict:
        return json.loads(self.script(SETTINGS_SCRIPT, "show").stdout)

    def rules_shown(self, epic: str) -> dict:
        return json.loads(self.script(RULES, "show", epic).stdout)

    def built_in_additions(self) -> list[str]:
        path = self.home / "built_in_commands.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def lap_worktree(self, task: str) -> Path:
        worktree = self.repo / ".worktrees" / f"lap-{task}"
        if not worktree.exists():
            fixture.run(["git", "worktree", "add", "-q", "-b", f"lap/{task}", str(worktree)], self.repo)
        return worktree

    def lap_commands(self, task: str) -> list[str]:
        done = self.script(RULES, "lap-commands", cwd=self.lap_worktree(task))
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def lap_list(self, task: str) -> list:
        done = self.script(LAP_LISTS, "lap", cwd=self.lap_worktree(task))
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)


class PermissionQuestionTests(PermissionCase):
    def test_the_question_names_the_denied_call_the_pattern_and_the_four_answers(self):
        _, task = self.asked()

        [question] = [comment for comment in self.comments(task) if str(comment["text"]).startswith("Question: ")]
        text = str(question["text"])
        self.assertIn(FOUND, text)
        self.assertIn(f"`{CALL}`", text)
        self.assertIn(f"`{PATTERN}`", text)
        for name in ANSWERS:
            self.assertIn(f"Answer word: {name}.", text)
        self.assertIn("Recommended: epic (50%).", text)
        shown = self.shown(task)
        self.assertEqual(["human"], shown["labels"])
        self.assertEqual((CALL, PATTERN), (shown["metadata"]["question.call"], shown["metadata"]["question.pattern"]))

    def test_jidoka_writes_the_question_from_the_denial_for_the_page_heading_and_the_comments_first_line(self):
        _, task = self.asked()

        [question] = [comment for comment in self.comments(task) if str(comment["text"]).startswith("Question: ")]
        html = next((self.home / "pages").rglob("*.html")).read_text(encoding="utf-8")

        self.assertEqual("Question: May lap workers run make lint?", str(question["text"]).splitlines()[0])
        self.assertEqual(["May lap workers run make lint?"], re.findall(r"<h1>([^<]*)</h1>", html))

    def test_the_comment_leads_each_option_with_the_change_it_makes_and_says_what_the_next_lap_does(self):
        _, task = self.asked()

        [question] = [comment for comment in self.comments(task) if str(comment["text"]).startswith("Question: ")]
        lines = [line for line in str(question["text"]).splitlines() if line.startswith("- ")]

        self.assertEqual(4, len(lines))
        for line, (change, name, percent) in zip(lines, CHANGES):
            self.assertTrue(line.startswith(f"- {change} ({percent}%)."), line)
            self.assertIn(f"Answer word: {name}.", line)
            self.assertIn("The next lap", line)
            self.assertIn(PATTERN, line)

    def test_the_page_card_of_each_option_leads_with_the_change_and_shows_the_answer_word_apart(self):
        _, task = self.asked()

        html = next((self.home / "pages").rglob("*.html")).read_text(encoding="utf-8")
        cards = re.findall(r'(?s)<article class="option[^"]*">(.*?)</article>', html)

        self.assertEqual(4, len(cards))
        for card, (change, name, percent) in zip(cards, CHANGES):
            self.assertEqual([change], [unescape(heading) for heading in re.findall(r"<h3>([^<]*)</h3>", card)])
            self.assertEqual([name], re.findall(r'<code class="answer-word">([^<]*)</code>', card))
            self.assertIn(f"{percent}%", card)
            self.assertRegex(card, r"(?s)What happens next.*The next lap")

    def test_a_next_the_worker_wrote_on_a_permission_option_does_not_replace_the_change_or_the_next_lap(self):
        _, task = self.new_task()
        options = [{"name": name, "confidence": 30, "next": "Worker words."} for name in ANSWERS]

        done = self.ask(task, options=options)

        self.assertEqual(0, done.returncode, done.stderr)
        html = next((self.home / "pages").rglob("*.html")).read_text(encoding="utf-8")
        self.assertNotIn("Worker words.", html)

    def test_a_pattern_whose_words_are_not_in_the_call_is_refused_and_parks_nothing(self):
        _, task = self.new_task()

        done = self.ask(task, pattern="make test")

        self.assertEqual(1, done.returncode)
        self.assertIn("the words of pattern must appear in call", done.stderr)
        self.assertEqual([], self.comments(task))
        self.assertNotIn("human", self.shown(task).get("labels") or [])

    def test_a_pattern_that_chains_commands_is_refused(self):
        _, task = self.new_task()

        done = self.ask(task, pattern="cd packages/till && make lint")

        self.assertEqual(1, done.returncode)
        self.assertIn("pattern must be one simple command", done.stderr)
        self.assertEqual([], self.comments(task))

    def test_options_other_than_the_four_answers_are_refused(self):
        _, task = self.new_task()

        done = self.ask(task, options=[{"name": "epic", "confidence": 60}, {"name": "repo", "confidence": 40}])

        self.assertEqual(1, done.returncode)
        self.assertIn("the options of a permission question must be the four answers", done.stderr)
        self.assertEqual([], self.comments(task))


class PermissionAnswerTests(PermissionCase):
    def test_an_answer_naming_the_epic_adds_the_pattern_to_the_epics_rules(self):
        epic, task = self.asked()
        self.human_answers(task, "The epic's list, please.")

        done = self.answer(task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({"task": task, "list": "epic", "pattern": PATTERN, "changed": True}, json.loads(done.stdout))
        self.assertEqual([PATTERN], self.rules_shown(epic)["settings"]["extra_commands"])
        self.assertNotIn(PATTERN, self.settings_shown()["worker_commands"])
        self.assertNotIn(PATTERN, self.built_in_additions())

    def test_an_answer_naming_the_repo_adds_the_pattern_to_the_repo_settings_worker_commands(self):
        epic, task = self.asked()
        self.human_answers(task, "repo")

        done = self.answer(task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("repo", json.loads(done.stdout)["list"])
        self.assertEqual(["make build", PATTERN], self.settings_shown()["worker_commands"])
        self.assertNotIn("extra_commands", self.rules_shown(epic)["settings"])

    def test_an_answer_naming_the_built_in_list_adds_the_pattern_to_the_homes_additions(self):
        epic, task = self.asked()
        self.human_answers(task, "Put it on the built-in list.")

        done = self.answer(task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("built-in", json.loads(done.stdout)["list"])
        self.assertIn(PATTERN, self.built_in_additions())
        self.assertNotIn("extra_commands", self.rules_shown(epic)["settings"])

    def test_without_a_comment_the_recommended_list_gets_the_pattern(self):
        epic, task = self.asked()
        self.human_answers(task)

        done = self.answer(task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("epic", json.loads(done.stdout)["list"])
        self.assertEqual([PATTERN], self.rules_shown(epic)["settings"]["extra_commands"])

    def test_answering_twice_changes_the_list_once(self):
        epic, task = self.asked()
        self.human_answers(task, "repo")
        self.answer(task)

        again = self.answer(task)

        self.assertEqual(0, again.returncode, again.stderr)
        self.assertFalse(json.loads(again.stdout)["changed"])
        self.assertEqual(1, self.settings_shown()["worker_commands"].count(PATTERN))

    def test_an_answer_that_names_no_list_is_none_and_writes_no_list(self):
        epic, task = self.asked()
        self.human_answers(task, "I deleted the file myself, add rm to no list.")

        done = self.answer(task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({"task": task, "list": "none", "pattern": PATTERN, "changed": False}, json.loads(done.stdout))
        self.assertNotIn("extra_commands", self.rules_shown(epic)["settings"])
        self.assertNotIn(PATTERN, self.settings_shown()["worker_commands"])
        self.assertNotIn(PATTERN, self.built_in_additions())

    def test_an_answer_naming_none_writes_no_list(self):
        epic, task = self.asked()
        self.human_answers(task, "none")

        done = self.answer(task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("none", json.loads(done.stdout)["list"])
        self.assertNotIn("extra_commands", self.rules_shown(epic)["settings"])

    def test_without_a_comment_a_recommended_none_writes_no_list(self):
        epic, task = self.new_task()
        self.assertEqual(0, self.ask(task, recommended="none").returncode)
        self.human_answers(task)

        done = self.answer(task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("none", json.loads(done.stdout)["list"])
        self.assertNotIn("extra_commands", self.rules_shown(epic)["settings"])

    def test_an_answer_that_names_two_lists_writes_nothing(self):
        epic, task = self.asked()
        self.human_answers(task, "epic or repo, either")

        done = self.answer(task)

        self.assertEqual(1, done.returncode)
        self.assertIn("the answer must name at most one list", done.stderr)
        self.assertNotIn("extra_commands", self.rules_shown(epic)["settings"])
        self.assertNotIn(PATTERN, self.settings_shown()["worker_commands"])
        self.assertNotIn(PATTERN, self.built_in_additions())

    def test_a_later_question_that_is_no_permission_question_leaves_nothing_to_apply(self):
        _, task = self.asked()
        scratch = self.root / f"scratch-{task}"
        (scratch / "question.json").write_text(json.dumps({
            "question": "Should receipts round?", "found": "Round receipts?", "recommended": "yes",
            "options": [{"name": "yes", "confidence": 60, "next": "Receipts round."},
                        {"name": "no", "confidence": 40, "next": "Receipts keep cents."}]}), encoding="utf-8")
        parked = self.script(PARK, "question", task, "--scratch", str(scratch), "--worktree",
                             str(self.repo), "--branch", f"lap/{task}", "--tries", "0")
        self.assertEqual(0, parked.returncode, parked.stderr)
        self.human_answers(task, "epic")

        done = self.answer(task)

        self.assertEqual(1, done.returncode)
        self.assertIn("was no permission question", done.stderr)

    def test_a_task_never_asked_has_no_answer_to_apply(self):
        _, task = self.new_task()

        done = self.answer(task)

        self.assertEqual(1, done.returncode)
        self.assertIn("was no permission question", done.stderr)


class NextLapCommandsTests(PermissionCase):
    def test_the_lap_mod_is_given_the_epics_additions_after_the_epic_list_is_chosen(self):
        epic, task = self.asked()
        other_epic, other_task = self.new_task()
        self.assertEqual([], self.lap_commands(task))
        self.human_answers(task, "epic")

        self.answer(task)

        self.assertEqual([PATTERN], self.lap_commands(task))
        self.assertEqual([], self.lap_commands(other_task))

    def test_the_lap_mod_is_given_the_built_in_additions_in_every_epic(self):
        _, task = self.asked()
        _, other_task = self.new_task()
        self.human_answers(task, "built-in")

        self.answer(task)

        self.assertIn(PATTERN, self.lap_list(task))
        self.assertIn(PATTERN, self.lap_list(other_task))

    def test_a_folder_that_is_no_lap_worktree_prints_nothing_and_refuses(self):
        done = self.script(RULES, "lap-commands")

        self.assertEqual(1, done.returncode)
        self.assertIn("is not a lap worktree", done.stderr)
        self.assertEqual("", done.stdout)


if __name__ == "__main__":
    unittest.main()
