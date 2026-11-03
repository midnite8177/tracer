import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import test_permission_question as permission  # noqa: E402
import test_spec_cases as spec_cases_tests  # noqa: E402

SPEC_APPROVAL = permission.PARK.parent / "spec_approval.py"
PAYS = spec_cases_tests.PAYS
REFUNDS = spec_cases_tests.REFUNDS
PAYS_CODE = 'def test_a_shopper_pays_by_card(till):\n    till.run("pay", "--card", "5.00")\n    assert "receipt 1" in till.output'
REFUNDS_CODE = 'def test_a_shopper_refunds(till):\n    till.run("refund", "1")\n    assert "0.00 owed" in till.output'
CASES = [{**spec_cases_tests.CASES[0], "code": PAYS_CODE}, {**spec_cases_tests.CASES[1], "code": REFUNDS_CODE}]
PROPOSAL = {"cases": CASES, "interface": spec_cases_tests.INTERFACE}
PAGE_LINK = re.compile(r"Page: (file://\S+)")


class SpecApprovalCase(permission.PermissionCase):
    """A temporary git repo with the fake bd's beads and a temporary jidoka home, with an epic to propose specs on."""

    def setUp(self):
        super().setUp()
        self.epic = self.create("Take card payments", "--type=epic")

    def spec_approval(self, mode: str, epic: str, stdin: str | None = None) -> subprocess.CompletedProcess:
        return self.script(SPEC_APPROVAL, mode, epic, stdin=stdin)

    def posted(self, proposal: object = PROPOSAL) -> dict:
        done = self.spec_approval("post", self.epic, json.dumps(proposal))
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def answered(self) -> dict:
        done = self.spec_approval("answer", self.epic)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def page_html(self) -> str:
        [page] = sorted((self.home / "pages").rglob("*.html"))
        return page.read_text(encoding="utf-8")

    def proposal_comment(self) -> str:
        [proposal] = [comment for comment in self.comments(self.epic) if str(comment["text"]).startswith("Spec approval: ")]
        return str(proposal["text"])


class SpecApprovalPageTests(SpecApprovalCase):
    def test_the_page_sits_in_the_jidoka_home_beside_the_epic_and_none_is_written_in_the_repo(self):
        printed = self.posted()

        self.assertEqual(str(self.home / "pages" / "shop" / f"spec-approval-{self.epic}.html"), printed["page"])
        self.assertEqual([], list(self.repo.rglob("*.html")))

    def test_each_case_shows_its_code_beside_its_plain_reading_and_its_deletion_answer(self):
        self.posted()

        html = self.page_html()

        cases = re.findall(r'(?s)<article class="case">(.*?)</article>', html)
        self.assertEqual(2, len(cases))
        self.assertIn(f"1. {PAYS}", cases[0])
        self.assertRegex(cases[0], r'(?s)The spec</h3>\s*<pre><code>def test_a_shopper_pays_by_card.*?</code></pre>.*'
                                   r'Plain reading</h3>\s*<p class="reading">Pay 5.00 by card and the till prints '
                                   r'receipt 1.</p>')
        self.assertIn("No. Without card payment there is no receipt, so the spec fails.", cases[0])
        self.assertIn(f"2. {REFUNDS}", cases[1])
        self.assertIn("Refund the card payment and the till shows 0.00 owed.", cases[1])

    def test_the_page_shows_the_interface_table(self):
        self.posted()

        html = self.page_html()

        self.assertIn("<td>Pay by card</td><td>`till pay --card &lt;amount&gt;`</td><td>1, 2</td>", html)
        self.assertIn("<td>Refund a payment</td><td>`till refund &lt;receipt&gt;`</td><td>2</td>", html)

    def test_an_empty_interface_table_says_the_driver_offers_everything(self):
        self.posted({"cases": CASES, "interface": []})

        html = self.page_html()

        self.assertIn("The protocol driver already offers everything the test cases need.", html)
        self.assertNotIn("<table>", html)

    def test_the_page_marks_one_slot_for_the_answer_panel(self):
        self.posted()

        self.assertEqual(1, self.page_html().count('data-jidoka-slot="answer-panel"'))

    def test_markup_in_the_code_is_shown_as_text(self):
        self.posted({"cases": [{**CASES[0], "code": 'assert "<b>5.00</b>" & ok'}], "interface": []})

        html = self.page_html()

        self.assertIn("assert &quot;&lt;b&gt;5.00&lt;/b&gt;&quot; &amp; ok", html)
        self.assertNotIn("<b>5.00</b>", html)

    def test_the_page_is_self_contained_with_no_script_and_no_outside_link(self):
        self.posted()

        html = self.page_html()

        self.assertNotIn("<script", html)
        self.assertNotRegex(html, r'(src|href)="https?://')

    def test_posting_again_replaces_the_page(self):
        self.posted()

        self.posted({"cases": CASES[:1], "interface": []})

        html = self.page_html()
        self.assertIn(PAYS, html)
        self.assertNotIn(REFUNDS, html)


class SpecApprovalBeadTests(SpecApprovalCase):
    def test_the_epic_carries_the_human_label_and_the_two_answers_for_the_answer_panel(self):
        self.posted()

        shown = self.shown(self.epic)

        self.assertIn("human", shown["labels"])
        self.assertEqual(["Approve", "Ask back"],
                         [option["name"] for option in json.loads(shown["metadata"]["question.options"])])
        self.assertNotIn("question.recommended", shown["metadata"])

    def test_the_metadata_holds_the_question_and_what_happens_next_for_each_answer(self):
        self.posted()

        metadata = self.shown(self.epic)["metadata"]

        self.assertEqual("Do these 2 acceptance specs say what Take card payments must do?",
                         metadata["question.sentence"])
        self.assertEqual([{"name": "Approve",
                           "next": "The specs go on the epic's spec task, and the factory writes them as the epic's "
                                   "tests."},
                          {"name": "Ask back",
                           "next": "You say what to change, and a new proposal comes back for you to approve."}],
                         json.loads(metadata["question.options"]))
        self.assertNotIn("question.reason", metadata)

    def test_a_proposal_of_one_spec_asks_about_that_one_spec(self):
        self.posted({"cases": CASES[:1], "interface": []})

        self.assertEqual("Does this acceptance spec say what Take card payments must do?",
                         self.shown(self.epic)["metadata"]["question.sentence"])

    def test_the_comment_holds_the_cases_the_code_and_the_interface_table_in_plain_text_and_links_the_page(self):
        printed = self.posted()

        text = self.proposal_comment()

        self.assertTrue(text.startswith(f"Spec approval: 2 test cases proposed for {self.epic}"), text)
        self.assertIn(f"1. {PAYS}\n   - Plain reading: Pay 5.00 by card and the till prints receipt 1.\n"
                      "   - If this feature were deleted: No. Without card payment there is no receipt, so the spec "
                      "fails.", text)
        self.assertIn(f"1. {PAYS}\n```\n{PAYS_CODE}\n```", text)
        self.assertIn("| Pay by card | `till pay --card <amount>` | 1, 2 |", text)
        self.assertEqual(printed["page"], url2pathname(urlparse(PAGE_LINK.search(text).group(1)).path))
        self.assertNotIn("<", text.replace("<amount>", "").replace("<receipt>", ""))

    def test_code_that_holds_a_fence_is_fenced_by_a_longer_one(self):
        self.posted({"cases": [{**CASES[0], "code": "text = '''\n```\n'''"}], "interface": []})

        self.assertIn("````\ntext = '''\n```\n'''\n````", self.proposal_comment())

    def test_the_description_and_the_other_fields_of_the_epic_stay_as_they_were(self):
        before = self.shown(self.epic)

        self.posted()

        after = self.shown(self.epic)
        self.assertEqual((before.get("title"), before.get("description"), before["status"]),
                         (after.get("title"), after.get("description"), after["status"]))


class SpecApprovalAnswerTests(SpecApprovalCase):
    def test_a_proposal_nobody_answered_is_waiting_with_no_replies(self):
        self.posted()

        self.assertEqual({"epic": self.epic, "waiting": True, "replies": []}, self.answered())

    def test_a_press_on_an_answer_is_the_reply_and_the_label_coming_off_ends_the_wait(self):
        self.posted()
        self.human_answers(self.epic, "Approve")

        self.assertEqual({"epic": self.epic, "waiting": False, "replies": ["Approve"]}, self.answered())

    def test_every_comment_of_the_human_since_the_proposal_is_a_reply_in_order(self):
        self.posted()
        self.human_answers(self.epic, "Ask back", "Case 2 should pay 7.50.")

        self.assertEqual(["Ask back", "Case 2 should pay 7.50."], self.answered()["replies"])

    def test_a_reply_before_the_latest_proposal_is_not_an_answer_to_it(self):
        self.posted()
        self.human_answers(self.epic, "Ask back")

        self.posted({"cases": CASES[:1], "interface": []})

        self.assertEqual({"epic": self.epic, "waiting": True, "replies": []}, self.answered())

    def test_an_epic_with_no_proposal_has_no_answer_to_read(self):
        done = self.spec_approval("answer", self.epic)

        self.assertEqual(1, done.returncode)
        self.assertIn(f"{self.epic} holds no spec approval", done.stderr)


class SpecApprovalRefusalTests(SpecApprovalCase):
    def refused(self, stdin: str, reason: str) -> None:
        done = self.spec_approval("post", self.epic, stdin)

        self.assertEqual(1, done.returncode)
        self.assertIn(reason, done.stderr)
        self.assertEqual([], self.comments(self.epic))
        self.assertNotIn("human", self.shown(self.epic).get("labels") or [])
        self.assertEqual([], list((self.home / "pages").rglob("*.html")))

    def test_a_case_with_no_code_is_refused_and_nothing_is_written(self):
        self.refused(json.dumps({"cases": [spec_cases_tests.CASES[0]], "interface": []}), "case 1 has no code")

    def test_a_case_that_the_spec_cases_script_would_refuse_is_refused(self):
        self.refused(json.dumps({"cases": [{**CASES[0], "deletion": " "}], "interface": []}),
                     "case 1 is not an object with a name")

    def test_input_that_is_not_json_is_refused(self):
        self.refused("not json", "not valid JSON")

    def test_input_without_an_interface_list_is_refused(self):
        self.refused(json.dumps({"cases": CASES}), 'an object with "cases" and "interface"')

    def test_a_bead_that_is_not_an_epic_is_refused(self):
        task = self.create("Read the card", "--type=task", "--parent", self.epic)

        done = self.spec_approval("post", task, json.dumps(PROPOSAL))

        self.assertEqual(1, done.returncode)
        self.assertIn("not an epic", done.stderr)
        self.assertEqual([], self.comments(task))

    def test_a_page_that_cannot_be_written_refuses_the_post_and_changes_no_bead(self):
        (self.home / "pages").write_text("in the way\n", encoding="utf-8")

        done = self.spec_approval("post", self.epic, json.dumps(PROPOSAL))

        self.assertEqual(1, done.returncode)
        self.assertIn("the spec approval page could not be written", done.stderr)
        self.assertEqual([], self.comments(self.epic))
        self.assertNotIn("human", self.shown(self.epic).get("labels") or [])


if __name__ == "__main__":
    unittest.main()
