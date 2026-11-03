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
CHANGES = [("Only the workers on this group of tasks may run make lint", "epic", 50),
           ("Every worker in this repo may run make lint", "repo", 30),
           ("Every worker in every repo on this machine may run make lint", "built-in", 5),
           ("Nothing changes, and no worker may run make lint", "none", 15)]
JIDOKA_WORDS = ["lap", "epic's", "built-in list", "lists"]


def report(**changes: object) -> dict:
    options = [{"name": "epic", "confidence": 50}, {"name": "repo", "confidence": 30},
               {"name": "built-in", "confidence": 5}, {"name": "none", "confidence": 15}]
    return {"found": FOUND, "call": CALL, "pattern": PATTERN, "cause": "off-lists", "options": options,
            "recommended": "epic", **changes}


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

    def test_the_comment_leads_each_option_with_the_change_it_makes_and_says_what_the_worker_does_with_the_call(self):
        _, task = self.asked()

        [question] = [comment for comment in self.comments(task) if str(comment["text"]).startswith("Question: ")]
        lines = [line for line in str(question["text"]).splitlines() if line.startswith("- ")]

        self.assertEqual(4, len(lines))
        for line, (change, name, percent) in zip(lines, CHANGES):
            self.assertTrue(line.startswith(f"- {change} ({percent}%)."), line)
            self.assertIn(f"Answer word: {name}.", line)
            self.assertIn("The worker starts again", line)
            self.assertIn("the call", line)
            self.assertNotIn(CALL, line)

    def test_the_comment_names_the_refused_call_once(self):
        _, task = self.asked()

        [question] = [comment for comment in self.comments(task) if str(comment["text"]).startswith("Question: ")]

        self.assertEqual(1, str(question["text"]).count(CALL))

    def test_the_metadata_holds_the_question_sentence_and_what_happens_next_for_each_answer(self):
        _, task = self.asked()

        metadata = self.shown(task)["metadata"]

        self.assertEqual("May lap workers run make lint?", metadata["question.sentence"])
        self.assertEqual([
            {"name": "epic", "confidence": 50,
             "next": "The worker starts again and runs the call. Workers on other groups of tasks are still refused "
                     "make lint."},
            {"name": "repo", "confidence": 30,
             "next": "The worker starts again and runs the call, and so does every later worker in this repo, "
                     "whatever its group of tasks."},
            {"name": "built-in", "confidence": 5,
             "next": "The worker starts again and runs the call, and so does every later worker in every repo on "
                     "this machine."},
            {"name": "none", "confidence": 15,
             "next": "The worker starts again with every permission as it was, so the call is still refused. It "
                     "reads your comment and carries on without it."}], json.loads(metadata["question.options"]))

    def test_the_metadata_holds_the_workers_reason_for_the_refused_call_in_its_own_words(self):
        _, task = self.new_task()

        done = self.ask(task, why=["Lint fixes the import order.", "The build fails without it."])

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("Lint fixes the import order. The build fails without it.",
                         self.shown(task)["metadata"]["question.reason"])

    def test_a_permission_question_without_a_why_leaves_no_reason_from_an_earlier_question(self):
        _, task = self.new_task()
        self.ask(task, why=["Lint fixes the import order."])

        done = self.ask(task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("question.reason", self.shown(task)["metadata"])

    def test_the_change_and_the_next_step_of_each_option_need_no_jidoka_vocabulary(self):
        _, task = self.asked()

        [question] = [comment for comment in self.comments(task) if str(comment["text"]).startswith("Question: ")]
        lines = [line for line in str(question["text"]).splitlines() if line.startswith("- ")]
        html = unescape(next((self.home / "pages").rglob("*.html")).read_text(encoding="utf-8"))
        cards = re.findall(r'(?s)<article class="option[^"]*">(.*?)</article>', html)

        for words in [*lines, *cards]:
            for word in JIDOKA_WORDS:
                self.assertNotIn(word, words)

    def test_the_page_card_of_each_option_leads_with_the_change_and_shows_the_answer_word_apart(self):
        _, task = self.asked()

        html = next((self.home / "pages").rglob("*.html")).read_text(encoding="utf-8")
        cards = re.findall(r'(?s)<article class="option[^"]*">(.*?)</article>', html)

        self.assertEqual(4, len(cards))
        for card, (change, name, percent) in zip(cards, CHANGES):
            self.assertEqual([change], [unescape(heading) for heading in re.findall(r"<h3>([^<]*)</h3>", card)])
            self.assertEqual([name], re.findall(r'<code class="answer-word">([^<]*)</code>', card))
            self.assertIn(f"{percent}%", card)
            self.assertRegex(card, r"(?s)What happens next.*The worker starts again")

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


class PermissionSituationTests(PermissionCase):
    RM_CALL = "rm ../shared/SessionReader.cs"
    RAW_DENIAL = ("Permission to use Bash denied by plugin jidoka: jidoka: `rm ../shared/SessionReader.cs` deletes "
                  "outside the lap's worktree.")
    REASONS = ["The file has no caller left.", "Deleting it is the smallest change."]
    SITUATION = ("The worker tried to delete ../shared/SessionReader.cs with rm. Workers may delete only inside "
                 "their worktree, so the task stopped.")
    LAP_MOD_WORDS = ["denied by plugin", "off jidoka", "lap mod", "lists"]

    def asked_rm(self) -> tuple[str, str]:
        _, task = self.new_task()
        done = self.ask(task, call=self.RM_CALL, pattern="rm", cause="outside-worktree", shown=self.RAW_DENIAL,
                        why=self.REASONS, found="The build deletes a file that nothing reads.")
        self.assertEqual(0, done.returncode, done.stderr)
        return task, next((self.home / "pages").rglob("*.html")).read_text(encoding="utf-8")

    def question_text(self, task: str) -> str:
        [question] = [comment for comment in self.comments(task) if str(comment["text"]).startswith("Question: ")]
        return str(question["text"])

    def test_the_page_says_what_the_worker_tried_and_that_workers_may_not_run_it(self):
        _, html = self.asked_rm()

        self.assertIn(self.SITUATION, unescape(html))

    def test_the_page_shows_no_raw_denial_and_none_of_the_lap_mods_words(self):
        _, html = self.asked_rm()

        for word in self.LAP_MOD_WORDS:
            self.assertNotIn(word, unescape(html))

    def test_the_diagram_shows_the_task_the_call_the_denial_and_the_park_in_four_steps(self):
        task, html = self.asked_rm()

        diagram = re.search(r"(?s)<svg.*?</svg>", html).group(0)
        words = " ".join(unescape(line) for line in re.findall(r"<text[^>]*>([^<]*)</text>", diagram))

        self.assertEqual(4, diagram.count("<rect"))
        for step in [task, self.RM_CALL, "denied", "parked"]:
            self.assertIn(step, words)

    def test_the_workers_reasons_for_its_pick_are_on_the_recommended_card_only(self):
        _, html = self.asked_rm()

        cards = re.findall(r'(?s)<article class="option[^"]*">(.*?)</article>', html)

        self.assertIn("option recommended", re.findall(r'<article class="([^"]*)">', html)[0])
        for reason in self.REASONS:
            self.assertIn(reason, cards[0])
            self.assertEqual(1, html.count(reason))

    def test_the_comment_holds_the_situation_and_the_reasons_and_none_of_the_lap_mods_words(self):
        task, _ = self.asked_rm()

        text = self.question_text(task)

        self.assertIn(self.SITUATION, text)
        for reason in self.REASONS:
            self.assertIn(reason, text)
        for word in self.LAP_MOD_WORDS:
            self.assertNotIn(word, text)

    def test_a_delete_whose_paths_cannot_be_told_says_so_and_not_that_workers_may_not_run_rm(self):
        _, task = self.new_task()

        done = self.ask(task, call="rm src/*.cs", pattern="rm", cause="unreadable-delete")

        self.assertEqual(0, done.returncode, done.stderr)
        text = self.question_text(task)
        self.assertIn("The worker tried to delete src/*.cs with rm. Workers may delete only paths they name one by "
                      "one inside their worktree, so the task stopped.", text)
        self.assertNotIn("Workers may not run rm", text)

    def test_the_targets_of_a_delete_stop_at_the_separator_even_when_it_is_glued_to_a_word(self):
        _, task = self.new_task()

        done = self.ask(task, call="rm /tmp/a.txt; ls /tmp", pattern="rm", cause="outside-worktree")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("The worker tried to delete /tmp/a.txt with rm.", self.question_text(task))

    def test_a_report_with_no_cause_or_an_unknown_one_is_refused_and_parks_nothing(self):
        _, task = self.new_task()
        no_cause = report()
        del no_cause["cause"]
        scratch = self.root / f"scratch-{task}"
        scratch.mkdir(exist_ok=True)
        (scratch / "question.json").write_text(json.dumps(no_cause), encoding="utf-8")
        missing = self.script(PARK, "question", task, "--scratch", str(scratch), "--worktree", str(self.repo),
                              "--branch", f"lap/{task}", "--tries", "0")

        unknown = self.ask(task, cause="because")

        self.assertEqual(1, missing.returncode)
        self.assertIn("cause must be a non-empty string", missing.stderr)
        self.assertEqual(1, unknown.returncode)
        self.assertIn("cause must be one of", unknown.stderr)
        self.assertEqual([], self.comments(task))

    def test_a_call_that_deletes_nothing_is_told_as_the_command_the_worker_ran(self):
        _, task = self.new_task()

        done = self.ask(task)

        self.assertEqual(0, done.returncode, done.stderr)
        html = unescape(next((self.home / "pages").rglob("*.html")).read_text(encoding="utf-8"))
        self.assertIn("The worker tried to run `cd packages/till && make lint --fix`. Workers may not run make lint, "
                      "so the task stopped.", html)
        self.assertIn("The worker tried to run make lint. Workers may not run make lint, so the task stopped.",
                      self.question_text(task))


class PermissionAnswerTests(PermissionCase):
    def test_an_answer_naming_the_epic_adds_the_pattern_to_the_epics_rules(self):
        epic, task = self.asked()
        self.human_answers(task, "Epic, please.")

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
        self.human_answers(task, "built-in: put it on the list for every repo.")

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

    def test_a_comment_that_only_mentions_a_list_word_after_its_first_word_is_none(self):
        epic, task = self.asked()
        self.human_answers(task, "Don't run it, the repo has a script for that, and the epic needs no lint.")

        done = self.answer(task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual({"task": task, "list": "none", "pattern": PATTERN, "changed": False}, json.loads(done.stdout))
        self.assertNotIn(PATTERN, self.settings_shown()["worker_commands"])
        self.assertNotIn("extra_commands", self.rules_shown(epic)["settings"])

    def test_a_list_word_that_only_starts_a_longer_word_names_no_list(self):
        epic, task = self.asked()
        self.human_answers(task, "Repository settings are out of scope, so none.")

        done = self.answer(task)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("none", json.loads(done.stdout)["list"])

    def test_an_answer_that_names_two_lists_writes_nothing(self):
        epic, task = self.asked()
        self.human_answers(task, "epic", "repo, either")

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
