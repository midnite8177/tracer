import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_handoff as handoff  # noqa: E402

PAGE_LINK = re.compile(r"Page: (file://\S+)")
SCENARIO = handoff.SCENARIO


class HandoffPageCase(handoff.HandoffCase):
    """The handoff tests' fixture: a temporary git repo with the fake bd's beads and a temporary jidoka home."""

    def handed_off(self, *extra: str) -> tuple[str, list[str]]:
        epic, _ = self.new_epic()
        first, second = self.new_task_under(epic), self.new_task_under(epic)
        self.write_holdouts(epic, [{"app": "shop", "tasks": [first], "scenario": SCENARIO}])
        done = self.handoff("take", epic, "--area", f"{first}=till", "--area", f"{second}=receipts", *extra)
        self.assertEqual(0, done.returncode, done.stderr)
        return epic, [first, second]

    def page_of(self, epic: str) -> Path:
        [page] = [found for found in sorted((self.home / "pages").rglob("*.html")) if epic in found.name]
        return page

    def table_comment(self, epic: str) -> str:
        [table] = [comment["text"] for comment in self.comments(epic) if comment["text"].startswith("Handoff:")]
        return str(table)


class HandoffPageTests(HandoffPageCase):
    def test_a_handoff_writes_a_page_in_the_jidoka_home_and_none_in_the_repo(self):
        epic, _ = self.handed_off()

        page = self.page_of(epic)

        self.assertEqual(self.home / "pages" / "shop", page.parent)
        self.assertEqual("", fixture.run(["git", "status", "--porcelain"], self.repo))
        self.assertEqual([], list(self.repo.rglob("*.html")))

    def test_the_page_has_a_row_for_every_task_with_its_track_why_area_holdouts_and_state(self):
        epic, [first, second] = self.handed_off()

        html = self.page_of(epic).read_text(encoding="utf-8")

        rows = re.findall(r"(?s)<tr>(.*?)</tr>", html.split("The factory rules")[0])
        cells = [re.findall(r"<t[dh]>(.*?)</t[dh]>", row) for row in rows]
        self.assertEqual(["Task", "Track", "Why", "Area", "Holdouts", "State"], cells[0])
        self.assertEqual(
            [[f"{first} Read the card {self.count - 1}", "full", "named by 1 holdout", "till", "1", "open"],
             [f"{second} Read the card {self.count}", "simple", "no holdouts, one seam, no public API or type",
              "receipts", "0", "open"]],
            cells[1:])

    def test_a_flipped_track_shows_on_the_page_with_the_reason(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{task}=till", "--track", f"{task}=full")
        self.assertEqual(0, done.returncode, done.stderr)

        html = self.page_of(epic).read_text(encoding="utf-8")

        self.assertIn("<td>full</td>", html)
        self.assertIn("flipped by the human from simple: no holdouts, one seam, no public API or type", html)

    def test_the_page_shows_the_rules_of_the_preset_with_its_guidance(self):
        epic, _ = self.handed_off("--preset", "improvement-epic")

        html = self.page_of(epic).read_text(encoding="utf-8")

        rules = html.split("The factory rules")[1]
        self.assertIn("changes nothing a user sees", rules)

    def test_the_page_lists_each_setting_of_the_preset_with_its_value(self):
        epic, _ = self.handed_off("--preset", "bug-epic")

        html = self.page_of(epic).read_text(encoding="utf-8")

        rules = html.split("The factory rules")[1]
        self.assertIn("<td>discovered_bugs_into_epic</td><td><code>true</code></td>", rules)
        self.assertIn("<td>commits_on_main</td><td><code>&quot;per_task&quot;</code></td>", rules)

    def test_the_page_shows_the_rules_an_epic_already_held_when_no_preset_is_chosen(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)
        fixture.run([self.bd, "update", epic, "--set-metadata", "rules.passes=3"], self.repo)

        done = self.handoff("take", epic, "--area", f"{task}=till")
        self.assertEqual(0, done.returncode, done.stderr)

        rules = self.page_of(epic).read_text(encoding="utf-8").split("The factory rules")[1]
        self.assertIn("<td>passes</td><td><code>3</code></td>", rules)

    def test_an_epic_with_no_rules_says_the_repo_settings_apply(self):
        epic, _ = self.handed_off()

        rules = self.page_of(epic).read_text(encoding="utf-8").split("The factory rules")[1]

        self.assertIn("The epic sets no factory rules, so the repo settings apply.", rules)

    def test_a_page_is_self_contained_with_no_script_and_no_outside_link(self):
        epic, _ = self.handed_off("--preset", "bug-epic")

        html = self.page_of(epic).read_text(encoding="utf-8")

        self.assertNotIn("<script", html)
        self.assertNotRegex(html, r'(src|href)="https?://')
        self.assertIn("<style>", html)

    def test_markup_in_a_task_title_is_shown_as_text(self):
        epic, _ = self.new_epic()
        type(self).count += 1
        task = self.create("Read <b>the</b> card & more", "--type=task", "--parent", epic, "--description",
                           handoff.SEAMS)

        done = self.handoff("take", epic, "--area", f"{task}=till")
        self.assertEqual(0, done.returncode, done.stderr)

        html = self.page_of(epic).read_text(encoding="utf-8")
        self.assertIn("Read &lt;b&gt;the&lt;/b&gt; card &amp; more", html)
        self.assertNotIn("<b>the</b>", html)


class HandoffCommentTests(HandoffPageCase):
    def test_the_comment_links_the_page_it_sits_beside(self):
        epic, _ = self.handed_off()

        link = PAGE_LINK.search(self.table_comment(epic))

        self.assertIsNotNone(link)
        self.assertEqual(self.page_of(epic).as_uri(), link.group(1))

    def test_the_comment_still_holds_the_whole_table_in_plain_text(self):
        epic, [first, _] = self.handed_off()

        text = self.table_comment(epic)

        self.assertIn("| Task | Track | Why | Area | Holdouts | State |", text)
        self.assertIn(f"| {first} Read the card {self.count - 1} | full | named by 1 holdout | till | 1 | open |", text)
        self.assertNotIn("<", text)

    def test_the_printed_result_names_the_page(self):
        epic, _ = self.new_epic()
        task = self.new_task_under(epic)

        done = self.handoff("take", epic, "--area", f"{task}=till")

        self.assertEqual(self.page_of(epic).as_uri(), Path(json.loads(done.stdout)["page"]).as_uri())

    def test_a_rerun_replaces_the_page_and_posts_no_second_table(self):
        epic, [first, second] = self.handed_off()
        self.page_of(epic).write_text("stale\n", encoding="utf-8")
        fixture.run([self.bd, "label", "remove", epic, "factory"], self.repo)

        done = self.handoff("take", epic, "--area", f"{first}=till", "--area", f"{second}=receipts")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("<table>", self.page_of(epic).read_text(encoding="utf-8"))
        self.assertEqual(1, len(self.comments(epic)))


class HandoffPageRefusalTests(HandoffPageCase):
    def test_a_page_that_cannot_be_written_refuses_the_handoff_and_writes_nothing(self):
        epic, name = self.new_epic()
        task = self.new_task_under(epic)
        home = self.new_home(f"blocked-home-{self.count}")
        self.write_settings(home, [handoff.shop_app()])
        (home / "pages").write_text("in the way\n", encoding="utf-8")

        done = self.handoff_in(home, "take", epic, "--area", f"{task}=till")

        self.assertEqual(1, done.returncode)
        self.assertIn("the handoff page could not be written", done.stderr)
        self.assert_nothing_written(epic, [task], name)


if __name__ == "__main__":
    unittest.main()
