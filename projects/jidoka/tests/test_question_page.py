import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_permission_question as permission  # noqa: E402

QUESTION = "Should the receipt round to five cents like the till?"
FOUND = "The till already rounds to five cents and the task does not say whether receipts should."
SHOWN = "The receipt prints 4.97 while the till screen says 4.95."
WHY = ["The till rounds the total", "The receipt prints the unrounded sum", "The two totals differ"]
OPTIONS = [{"name": "round receipts too", "confidence": 60, "next": "The receipt prints 4.95 and the test pins it."},
           {"name": "print exact cents", "confidence": 35, "next": "The till screen shows the exact cents."}]
PAGE_LINK = re.compile(r"Page: (file://\S+)")


class QuestionPageCase(permission.PermissionCase):
    """A temporary git repo with the fake bd's beads and a temporary jidoka home, as the permission tests set up."""

    def plain_report(self, **changes: object) -> dict:
        return {"question": QUESTION, "found": FOUND, "options": OPTIONS, "recommended": "round receipts too", **changes}

    def ask_plain(self, task: str, **changes: object):
        scratch = self.root / f"scratch-{task}"
        scratch.mkdir(exist_ok=True)
        (scratch / "question.json").write_text(json.dumps(self.plain_report(**changes)), encoding="utf-8")
        return self.script(permission.PARK, "question", task, "--scratch", str(scratch), "--worktree",
                           str(self.repo / ".worktrees" / f"lap-{task}"), "--branch", f"lap/{task}", "--tries", "0")

    def asked_plain(self, **changes: object) -> str:
        _, task = self.new_task()
        done = self.ask_plain(task, **changes)
        self.assertEqual(0, done.returncode, done.stderr)
        return task

    def question_text(self, task: str) -> str:
        [question] = [comment for comment in self.comments(task) if str(comment["text"]).startswith("Question: ")]
        return str(question["text"])

    def page_of(self, task: str) -> Path:
        [page] = sorted((self.home / "pages").rglob("*.html"))
        self.assertIn(task, page.name)
        return page


class QuestionPageTests(QuestionPageCase):
    def test_a_question_gets_a_page_in_the_jidoka_home_and_none_in_the_repo(self):
        task = self.asked_plain()

        page = self.page_of(task)

        self.assertEqual(self.home / "pages" / "shop", page.parent)
        self.assertEqual("", fixture.run(["git", "status", "--porcelain"], self.repo))
        self.assertEqual([], list(self.repo.rglob("*.html")))

    def test_the_page_heading_is_the_question_and_not_the_title_of_the_bead(self):
        task = self.asked_plain()

        html = self.page_of(task).read_text(encoding="utf-8")

        self.assertEqual([QUESTION], re.findall(r"<h1>([^<]*)</h1>", html))
        self.assertNotIn("Read the card", html)

    def test_the_page_has_an_in_short_box_with_what_the_worker_found(self):
        page = self.page_of(self.asked_plain())

        html = page.read_text(encoding="utf-8")

        self.assertRegex(html, r'(?s)<section class="in-short">.*In short.*' + re.escape(FOUND) + r".*</section>")

    def test_the_page_has_one_card_per_option_with_its_confidence_and_what_happens_next(self):
        page = self.page_of(self.asked_plain())

        html = page.read_text(encoding="utf-8")

        cards = re.findall(r'(?s)<article class="option[^"]*">(.*?)</article>', html)
        self.assertEqual(2, len(cards))
        self.assertIn("round receipts too", cards[0])
        self.assertIn("60%", cards[0])
        self.assertIn("The receipt prints 4.95 and the test pins it.", cards[0])
        self.assertIn("print exact cents", cards[1])
        self.assertIn("35%", cards[1])
        self.assertIn("The till screen shows the exact cents.", cards[1])

    def test_the_card_of_the_recommended_option_is_marked(self):
        page = self.page_of(self.asked_plain())

        html = page.read_text(encoding="utf-8")

        marked = re.findall(r'<article class="option recommended">\s*<h3>([^<]*)</h3>', html)
        self.assertEqual(["round receipts too"], marked)

    def test_the_page_marks_a_slot_for_the_answer_panel(self):
        page = self.page_of(self.asked_plain())

        html = page.read_text(encoding="utf-8")

        self.assertEqual(1, html.count('data-jidoka-slot="answer-panel"'))

    def test_what_the_app_shows_and_the_steps_of_why_appear_on_the_page_as_the_worker_wrote_them(self):
        page = self.page_of(self.asked_plain(shown=SHOWN, why=WHY))

        html = page.read_text(encoding="utf-8")

        self.assertIn(SHOWN, html)
        diagram = re.search(r"(?s)<svg.*?</svg>", html)
        self.assertIsNotNone(diagram)
        for step in WHY:
            self.assertIn(step, diagram.group(0))

    def test_a_page_is_self_contained_with_no_script_and_no_outside_link(self):
        page = self.page_of(self.asked_plain(shown=SHOWN, why=WHY))

        html = page.read_text(encoding="utf-8")

        self.assertNotIn("<script", html)
        self.assertNotRegex(html, r'(src|href)="https?://')
        self.assertIn("<style>", html)

    def test_markup_in_the_worker_words_is_shown_as_text(self):
        page = self.page_of(self.asked_plain(found="Does <b>exact</b> & rounded differ?"))

        html = page.read_text(encoding="utf-8")

        self.assertIn("Does &lt;b&gt;exact&lt;/b&gt; &amp; rounded differ?", html)
        self.assertNotIn("<b>exact</b>", html)

    def test_a_page_is_written_for_a_permission_question_too(self):
        _, task = self.asked()

        self.assertIn(task, self.page_of(task).name)

    def test_asking_again_replaces_the_tasks_page(self):
        task = self.asked_plain()
        done = self.ask_plain(task, found="A different thing was found.")
        self.assertEqual(0, done.returncode, done.stderr)

        html = self.page_of(task).read_text(encoding="utf-8")

        self.assertIn("A different thing was found.", html)
        self.assertNotIn(FOUND, html)


class QuestionCommentTests(QuestionPageCase):
    def test_the_comment_links_the_page_it_sits_beside(self):
        task = self.asked_plain()

        link = PAGE_LINK.search(self.question_text(task))

        self.assertIsNotNone(link)
        self.assertEqual(self.page_of(task).as_uri(), link.group(1))

    def test_the_comment_opens_with_the_question_in_one_sentence(self):
        task = self.asked_plain()

        first_line = self.question_text(task).splitlines()[0]

        self.assertEqual(f"Question: {QUESTION}", first_line)

    def test_the_comment_carries_the_whole_question_without_the_page(self):
        task = self.asked_plain(shown=SHOWN, why=WHY)

        text = self.question_text(task)

        self.assertIn(FOUND, text)
        self.assertIn(f"What the app shows: {SHOWN}", text)
        self.assertIn("Why: " + " -> ".join(WHY), text)
        self.assertIn("- round receipts too (60%): The receipt prints 4.95 and the test pins it.", text)
        self.assertIn("- print exact cents (35%): The till screen shows the exact cents.", text)
        self.assertIn("Recommended: round receipts too (60%).", text)
        self.assertNotIn("<", text)

    def test_a_report_without_the_page_words_still_posts_and_names_each_option_with_its_confidence(self):
        task = self.asked_plain()

        text = self.question_text(task)

        self.assertIn("- round receipts too (60%): The receipt prints 4.95 and the test pins it.", text)
        self.assertIn("- print exact cents (35%): The till screen shows the exact cents.", text)
        self.assertNotIn("What the app shows", text)
        self.assertNotIn("Why:", text)
        self.assertEqual(2, self.page_of(task).read_text(encoding="utf-8").count('<article class="option'))


class QuestionMetadataTests(QuestionPageCase):
    def test_the_metadata_holds_the_question_sentence_and_what_happens_next_for_each_option(self):
        task = self.asked_plain()

        metadata = self.shown(task)["metadata"]

        self.assertEqual(QUESTION, metadata["question.sentence"])
        self.assertEqual([{"name": "round receipts too", "confidence": 60,
                           "next": "The receipt prints 4.95 and the test pins it."},
                          {"name": "print exact cents", "confidence": 35,
                           "next": "The till screen shows the exact cents."}], json.loads(metadata["question.options"]))
        self.assertEqual("round receipts too", metadata["question.recommended"])

    def test_a_question_after_a_permission_question_leaves_no_reason_for_the_refused_call(self):
        _, task = self.new_task()
        self.ask(task, why=["Lint fixes the import order."])

        done = self.ask_plain(task, why=WHY)

        self.assertEqual(0, done.returncode, done.stderr)
        metadata = self.shown(task)["metadata"]
        self.assertEqual(QUESTION, metadata["question.sentence"])
        self.assertNotIn("question.reason", metadata)


class QuestionPageRefusalTests(QuestionPageCase):
    def test_an_option_without_a_next_is_refused_and_posts_nothing(self):
        _, task = self.new_task()
        options = [OPTIONS[0], {"name": "print exact cents", "confidence": 35}]

        done = self.ask_plain(task, options=options)

        self.assertEqual(1, done.returncode)
        self.assertIn("next of the option print exact cents is missing", done.stderr)
        self.assertEqual([], self.comments(task))
        self.assertNotIn("human", self.shown(task).get("labels") or [])
        self.assertEqual([], list((self.home / "pages").rglob("*.html")))

    def test_steps_of_why_that_are_not_a_list_of_text_are_refused_and_park_and_write_nothing(self):
        _, task = self.new_task()

        done = self.ask_plain(task, why="because")

        self.assertEqual(1, done.returncode)
        self.assertIn("why must be a list of non-empty strings", done.stderr)
        self.assertEqual([], self.comments(task))
        self.assertEqual([], list((self.home / "pages").rglob("*.html")))

    def test_a_report_without_a_question_is_refused_and_parks_and_writes_nothing(self):
        _, task = self.new_task()
        scratch = self.root / f"scratch-{task}"
        scratch.mkdir()
        report = self.plain_report()
        del report["question"]
        (scratch / "question.json").write_text(json.dumps(report), encoding="utf-8")

        done = self.script(permission.PARK, "question", task, "--scratch", str(scratch), "--worktree",
                           str(self.repo / ".worktrees" / f"lap-{task}"), "--branch", f"lap/{task}", "--tries", "0")

        self.assertEqual(1, done.returncode)
        self.assertIn("question must be a non-empty string", done.stderr)
        self.assertEqual([], self.comments(task))
        self.assertEqual([], list((self.home / "pages").rglob("*.html")))

    def test_a_next_that_is_not_text_is_refused(self):
        _, task = self.new_task()
        options = [{"name": "a", "confidence": 60, "next": 7}, {"name": "b", "confidence": 40}]

        done = self.ask_plain(task, options=options, recommended="a")

        self.assertEqual(1, done.returncode)
        self.assertIn("next of an option must be a non-empty string", done.stderr)
        self.assertEqual([], self.comments(task))

    def test_a_page_that_cannot_be_written_refuses_the_question_and_parks_nothing(self):
        _, task = self.new_task()
        (self.home / "pages").write_text("in the way\n", encoding="utf-8")

        done = self.ask_plain(task)

        self.assertEqual(1, done.returncode)
        self.assertIn("the question page could not be written", done.stderr)
        self.assertEqual([], self.comments(task))
        self.assertNotIn("human", self.shown(task).get("labels") or [])


if __name__ == "__main__":
    unittest.main()
