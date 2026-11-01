import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture
import test_design_findings
import test_gate
import test_scheduler
import test_validation

GATE_PAGE = test_scheduler.PLUGIN / "scripts" / "gate_page.py"
SECTIONS = ["In short", "Before and after", "How it works", "What changed", "Evidence", "Assumptions",
            "Design findings", "Tests removed", "What nothing checked", "Cost", "Merge danger", "Decide"]
IN_SHORT = "Customers pay by card at the till, and the receipt shows the card's last four digits."
BEFORE = "Pay 5.00 by card.\nThe till says: card not supported."
AFTER = "Pay 5.00 by card.\nThe till prints: PAID CARD ****1234"
HOW = ["The till reads the card", "The till charges it once", "The receipt shows the last four digits"]
STEPS = ["Build the shop app", "Start the till", "Pay 5.00 by card and read the receipt"]
UNCHECKED = ["A card the bank declines"]
MENU_BEFORE = "espresso 2.50\nlatte 3.00\nmocha 3.50\n"
MENU_AFTER = "espresso 2.50\nlatte 3.25\nmocha 3.50\ntea 2.00\n"


def guide(**changes: object) -> dict:
    return {"in_short": IN_SHORT, "before": BEFORE, "after": AFTER, "how": HOW, "steps": STEPS,
            "unchecked": UNCHECKED, **changes}


def section_of(html: str, title: str) -> str:
    found = re.search(r"(?s)<h2>" + re.escape(title) + r"</h2>(.*?)</section>", html)
    assert found is not None, f"no section {title}"
    return found.group(1)


class GatePageCase(test_gate.GateCase):
    """The shop repo with an epic at the gate whose branch changes a file, adds one and deletes one, run as processes
    with the fake bd's beads, a temporary jidoka home and real git."""

    def epic_with_changes(self) -> tuple[str, str, str, str]:
        """An epic at the gate; returns the epic, its task, its branch and the number that names its files."""
        number = self.count + 1000
        type(self).count += 1
        (self.repo / f"menu-{number}.txt").write_text(MENU_BEFORE, encoding="utf-8")
        (self.repo / f"old-{number}.txt").write_text("retired\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, f"Add the menu {number}")
        epic, task, branch = self.epic_at_the_gate()
        tree = self.root / f"edit-{number}"
        test_scheduler.git(self.repo, "worktree", "add", "-q", str(tree), branch)
        (tree / f"menu-{number}.txt").write_text(MENU_AFTER, encoding="utf-8")
        (tree / f"old-{number}.txt").unlink()
        fixture.git_commit_all(tree, "Change the menu")
        test_scheduler.git(self.repo, "worktree", "remove", "--force", str(tree))
        return epic, task, branch, str(number)

    def write_guide(self, name: str, **changes: object) -> Path:
        path = self.root / f"{name}.json"
        path.write_text(json.dumps(guide(**changes)), encoding="utf-8")
        return path

    def page_for(self, epic: str, **changes: object) -> str:
        done = self.launch(GATE_PAGE, epic, "--guide", str(self.write_guide("guide", **changes)))
        self.assertEqual(0, done.returncode, done.stderr)
        return Path(done.stdout.strip()).read_text(encoding="utf-8")

    def file_block(self, html: str, name: str) -> str:
        found = re.search(r'(?s)<details class="file" data-path="' + re.escape(name) + r'">(.*?)</details>', html)
        self.assertIsNotNone(found, f"no diff for {name}")
        return found.group(1)


class GatePageFileTests(GatePageCase):
    def test_the_page_is_written_in_the_jidoka_home_and_never_in_the_repo(self):
        epic, *_ = self.epic_with_changes()

        done = self.launch(GATE_PAGE, epic, "--guide", str(self.write_guide("guide")))

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(self.home / "pages" / "shop" / f"gate-{epic}.html", Path(done.stdout.strip()))
        self.assertTrue(Path(done.stdout.strip()).is_file())
        self.assertEqual("", test_gate.git(self.repo, "status", "--porcelain"))
        self.assertEqual([], list(self.repo.rglob("*.html")))

    def test_the_page_is_self_contained_with_no_script_and_no_outside_link(self):
        epic, *_ = self.epic_with_changes()

        html = self.page_for(epic)

        self.assertNotIn("<script", html)
        self.assertNotRegex(html, r'(src|href)="https?://')
        self.assertIn("<style>", html)

    def test_running_it_again_replaces_the_page(self):
        epic, *_ = self.epic_with_changes()
        self.page_for(epic)

        html = self.page_for(epic, in_short="A second reading of the same epic.")

        self.assertIn("A second reading of the same epic.", html)
        self.assertNotIn(IN_SHORT, html)
        self.assertEqual(1, len(list((self.home / "pages" / "shop").glob(f"gate-{epic}.html"))))


class GatePageReadsEachBeadOnceTests(GatePageCase):
    def test_a_page_for_an_epic_of_two_tasks_reads_every_bead_at_most_once_between_writes_to_it(self):
        epic, *_ = self.epic_with_changes()
        self.new_task_under(epic)
        guide_file = self.write_guide("guide")
        before = len(fixture.fake_beads_calls(self.repo))

        done = self.launch(GATE_PAGE, epic, "--guide", str(guide_file))

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], fixture.repeated_reads(fixture.fake_beads_calls(self.repo)[before:]))


class GuideSectionTests(GatePageCase):
    def test_in_short_holds_the_gate_workers_words_and_markup_in_them_is_shown_as_text(self):
        epic, *_ = self.epic_with_changes()

        html = self.page_for(epic, in_short="Does <b>card</b> & cash both work?")

        self.assertRegex(section_of(html, "In short"), r"Does &lt;b&gt;card&lt;/b&gt; &amp; cash both work\?")
        self.assertNotIn("<b>card</b>", html)

    def test_before_and_after_show_the_two_examples_side_by_side(self):
        epic, *_ = self.epic_with_changes()

        html = self.page_for(epic)

        examples = re.findall(r'(?s)<div class="example"><h3>([^<]*)</h3>\s*<pre>(.*?)</pre>', section_of(
            html, "Before and after"))
        self.assertEqual([("Before", BEFORE), ("After", AFTER)], examples)

    def test_how_it_works_draws_the_steps_as_a_diagram(self):
        epic, *_ = self.epic_with_changes()

        html = self.page_for(epic)

        diagram = re.search(r"(?s)<svg.*?</svg>", section_of(html, "How it works"))
        self.assertIsNotNone(diagram)
        for step in HOW:
            self.assertIn(step, diagram.group(0))

    def test_a_guide_with_only_an_in_short_still_gives_every_section_a_reason_for_being_empty(self):
        epic, *_ = self.epic_with_changes()
        path = self.root / "bare.json"
        path.write_text(json.dumps({"in_short": IN_SHORT}), encoding="utf-8")

        done = self.launch(GATE_PAGE, epic, "--guide", str(path))

        self.assertEqual(0, done.returncode, done.stderr)
        html = Path(done.stdout.strip()).read_text(encoding="utf-8")
        self.assertEqual(SECTIONS, re.findall(r"<h2>([^<]*)</h2>", html))
        self.assertIn("The worker gave no example.", html)
        self.assertIn("The worker gave no steps.", html)


class ChangedFilesTests(GatePageCase):
    def test_every_file_the_epic_changes_lists_with_its_status_and_its_counts_of_lines(self):
        epic, task, _, number = self.epic_with_changes()

        html = section_of(self.page_for(epic), "What changed")

        listed = re.findall(r'<details class="file" data-path="([^"]*)">\s*<summary><span class="path">[^<]*</span> '
                            r'<span class="status">(\w+)</span> <span class="add">\+(\d+)</span> '
                            r'<span class="del">-(\d+)</span>', html)
        self.assertEqual({(f"menu-{number}.txt", "modified", "2", "1"), (f"old-{number}.txt", "deleted", "0", "1"),
                          (f"{task}.txt", "added", "1", "0")}, set(listed))

    def test_the_commits_the_epic_adds_to_main_are_listed(self):
        epic, *_ = self.epic_with_changes()

        html = section_of(self.page_for(epic), "What changed")

        self.assertIn("Change the menu", html)

    def test_a_file_opens_its_real_diff_in_the_unified_layout(self):
        epic, _, _, number = self.epic_with_changes()

        block = self.file_block(self.page_for(epic), f"menu-{number}.txt")

        unified = re.search(r'(?s)<div class="unified"><pre>(.*?)</pre></div>', block)
        self.assertIsNotNone(unified)
        lines = re.findall(r'<span class="(add|del|same)">(?:<i>\d*</i>){2}(.)([^<]*)</span>', unified.group(1))
        self.assertEqual([("same", " ", "espresso 2.50"), ("del", "-", "latte 3.00"), ("add", "+", "latte 3.25"),
                          ("same", " ", "mocha 3.50"), ("add", "+", "tea 2.00")], lines)
        self.assertIn('<span class="hunk">@@ -1,3 +1,4 @@</span>', unified.group(1))

    def test_a_file_opens_its_real_diff_in_the_split_layout_with_each_removed_line_beside_the_line_that_replaces_it(
            self):
        epic, _, _, number = self.epic_with_changes()

        block = self.file_block(self.page_for(epic), f"menu-{number}.txt")

        split = re.search(r'(?s)<table class="split">(.*?)</table>', block)
        self.assertIsNotNone(split)
        rows = re.findall(r'<tr><td class="no">(\d*)</td><td class="old (\w+)(?: empty)?">([^<]*)</td>'
                          r'<td class="no">(\d*)</td><td class="new (\w+)(?: empty)?">([^<]*)</td></tr>',
                          split.group(1))
        self.assertEqual([("1", "same", "espresso 2.50", "1", "same", "espresso 2.50"),
                          ("2", "del", "latte 3.00", "2", "add", "latte 3.25"),
                          ("3", "same", "mocha 3.50", "3", "same", "mocha 3.50"),
                          ("", "empty", "", "4", "add", "tea 2.00")], rows)

    def test_a_deleted_file_shows_every_line_as_removed_and_an_added_file_every_line_as_added(self):
        epic, task, _, number = self.epic_with_changes()
        html = self.page_for(epic)

        deleted = self.file_block(html, f"old-{number}.txt")
        added = self.file_block(html, f"{task}.txt")

        self.assertIn('<span class="del"><i>1</i><i></i>-retired</span>', deleted)
        self.assertIn('<span class="add"><i></i><i>1</i>+built</span>', added)

    def test_both_layouts_are_in_the_page_and_a_radio_pair_picks_the_one_shown(self):
        epic, _, _, number = self.epic_with_changes()

        html = self.page_for(epic)

        self.assertIn('<input type="radio" name="diff-layout" id="layout-unified" checked>', html)
        self.assertIn('<input type="radio" name="diff-layout" id="layout-split">', html)
        self.assertIn(":has(#layout-split:checked)", html)
        block = self.file_block(html, f"menu-{number}.txt")
        self.assertEqual(1, block.count('class="unified"'))
        self.assertEqual(1, block.count('class="split"'))

    def test_markup_in_a_changed_file_is_shown_as_text(self):
        epic, _, branch, _ = self.epic_with_changes()
        tree = self.root / "markup-edit"
        test_scheduler.git(self.repo, "worktree", "add", "-q", str(tree), branch)
        (tree / "page.html").write_text("<script>alert(1)</script>\n", encoding="utf-8")
        fixture.git_commit_all(tree, "Add a page")
        test_scheduler.git(self.repo, "worktree", "remove", "--force", str(tree))

        html = self.page_for(epic)

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", self.file_block(html, "page.html"))
        self.assertNotIn("<script", html)

    def files_added_and_listed(self, names: list) -> list:
        """Commits a file for each name on the epic branch, and gives the data-path of each file the page lists."""
        epic, _, branch, _ = self.epic_with_changes()
        tree = self.root / "named-edit"
        test_scheduler.git(self.repo, "worktree", "add", "-q", str(tree), branch)
        for name in names:
            (tree / name).write_text("named\n", encoding="utf-8")
        fixture.git_commit_all(tree, "Add files with names git may quote")
        test_scheduler.git(self.repo, "worktree", "remove", "--force", str(tree))

        return re.findall(r'<details class="file" data-path="([^"]*)">', self.page_for(epic))

    def test_a_file_whose_name_holds_an_ampersand_or_a_letter_beyond_ascii_is_listed_under_its_real_name(self):
        listed = self.files_added_and_listed(["fish & chips.txt", "café.txt"])

        self.assertIn("fish &amp; chips.txt", listed)
        self.assertIn("café.txt", listed)

    @unittest.skipIf(fixture.WINDOWS, "a Windows file name cannot hold a double quote or a backslash")
    def test_a_file_whose_name_holds_a_double_quote_or_a_backslash_is_listed_under_its_real_name(self):
        listed = self.files_added_and_listed(['say "hi".txt', "back\\slash.txt"])

        self.assertIn("say &quot;hi&quot;.txt", listed)
        self.assertIn("back\\slash.txt", listed)


class EvidenceTests(GatePageCase):
    def test_evidence_holds_the_validation_figures_the_epic_recorded(self):
        epic, *_ = self.epic_with_changes()
        head = self.metadata(epic)["validation.head"]

        evidence = section_of(self.page_for(epic), "Evidence")

        self.assertIn(f"Validation of {head} ended pass", evidence)
        self.assertRegex(evidence, r"shop: .*exit code 0, \d+ tests, \d+ skipped")

    def test_evidence_names_the_worktree_and_how_to_cut_it_when_no_worktree_has_the_epic_branch_out(self):
        epic, _, branch, _ = self.epic_with_changes()
        path = self.repo / ".worktrees" / f"gate-{epic}"

        evidence = section_of(self.page_for(epic), "Evidence")

        self.assertIn(f'<span class="worktree">{path}</span>', evidence)
        self.assertIn(f"worktree add &quot;{path}&quot; {branch}", evidence)

    def test_evidence_names_the_worktree_that_has_the_epic_branch_out_and_cuts_no_other(self):
        epic, _, branch, _ = self.epic_with_changes()
        tree = self.root / "reviewing"
        test_scheduler.git(self.repo, "worktree", "add", "-q", str(tree), branch)
        self.addCleanup(lambda: test_scheduler.git(self.repo, "worktree", "remove", "--force", str(tree)))

        evidence = section_of(self.page_for(epic), "Evidence")

        self.assertIn(f'<span class="worktree">{tree}</span>', evidence)
        self.assertNotIn("worktree add", evidence)

    def test_evidence_lists_each_apps_build_and_run_commands_and_the_guides_numbered_steps(self):
        epic, *_ = self.epic_with_changes()

        evidence = section_of(self.page_for(epic), "Evidence")

        self.assertRegex(evidence, r"<tr><td>shop</td><td><code>make</code></td><td>none</td></tr>")
        steps = re.findall(r"<li>([^<]*)</li>", re.search(r'(?s)<ol class="steps">(.*?)</ol>', evidence).group(1))
        self.assertEqual(STEPS, steps)


class RecordSectionTests(GatePageCase):
    def comment_on(self, bead: str, text: str) -> None:
        self.bd_here("comment", bead, text)

    def test_assumptions_lists_each_one_a_worker_recorded_on_the_epic_or_its_tasks_in_the_gates_order(self):
        epic, task, *_ = self.epic_with_changes()
        self.comment_on(task, "assumption: the card reader answers within a second")
        self.comment_on(epic, "assumption: only one till is open")
        self.comment_on(task, "a comment that is not one")

        section = section_of(self.page_for(epic), "Assumptions")

        self.assertEqual([f"{epic} {self.shown(epic)['title']}: only one till is open",
                          f"{task} {self.shown(task)['title']}: the card reader answers within a second"],
                         re.findall(r"<li>([^<]*)</li>", re.search(r'(?s)<ol class="assumptions">(.*?)</ol>',
                                                                   section).group(1)))
        self.assertNotIn("not one", section)

    def test_a_comment_whose_prefix_differs_in_case_is_no_assumption_as_the_gate_comment_reads_it(self):
        epic, *_ = self.epic_with_changes()
        self.comment_on(epic, "Assumption: only one till is open")

        self.assertIn("No worker recorded an assumption.", section_of(self.page_for(epic), "Assumptions"))

    def test_assumptions_lists_the_public_api_changes_and_the_open_beads_found_outside_the_epic(self):
        epic, task, *_ = self.epic_with_changes()
        self.comment_on(task, "public API change: the till takes a card parameter")
        found = self.create("Round the tax the same way", "--type=task", "--deps", f"discovered-from:{task}")

        section = section_of(self.page_for(epic), "Assumptions")

        self.assertIn(f"{task} {self.shown(task)['title']}: the till takes a card parameter", section)
        self.assertIn(f"{found} Round the tax the same way, found in {task}", section)

    def test_assumptions_says_so_when_no_worker_recorded_one(self):
        epic, *_ = self.epic_with_changes()

        self.assertIn("No worker recorded an assumption.", section_of(self.page_for(epic), "Assumptions"))

    def test_tests_removed_is_a_table_of_the_deletions_the_cleanup_recorded(self):
        epic, *_ = self.epic_with_changes()
        removed = [{"test": "test_a", "file": "tests/test_a.py", "covered_by": "test_b"}]
        self.bd_here("update", epic, "--set-metadata", f"cleanup.removed={json.dumps(removed)}")

        section = section_of(self.page_for(epic), "Tests removed")

        self.assertIn("<tr><td>test_a</td><td>tests/test_a.py</td><td>test_b</td></tr>", section)

    def test_tests_removed_says_so_when_the_cleanup_removed_none(self):
        epic, *_ = self.epic_with_changes()

        self.assertIn("The test cleanup removed no test.", section_of(self.page_for(epic), "Tests removed"))

    def test_design_findings_lists_the_open_ones_in_the_files_the_epic_changed_and_the_low_confidence_ones(self):
        epic, _, _, number = self.epic_with_changes()
        report = self.root / "design-report.json"
        report.write_text(json.dumps([test_design_findings.problem("The menu knows the prices", f"menu-{number}.txt"),
                                      test_design_findings.problem("Unrelated", "elsewhere.txt")]), encoding="utf-8")
        filed = self.launch(test_design_findings.DESIGN_SCRIPT, epic, str(report))
        self.assertEqual(0, filed.returncode, filed.stderr)
        low = [{"lane": "design", "file": "till.py", "line": 9, "title": "Long function", "note": "It grew.",
                "size": "medium", "confidence": "low"}]
        self.bd_here("update", epic, "--set-metadata", f"review.low={json.dumps(low)}")

        section = section_of(self.page_for(epic), "Design findings")

        self.assertIn(f"menu-{number}.txt: The menu knows the prices in menu-{number}.txt (sightings: 1)", section)
        self.assertNotIn("Unrelated", section)
        self.assertIn("design, till.py:9: Long function. It grew.", section)

    def test_what_nothing_checked_holds_the_guides_list_and_the_hand_run_tests(self):
        epic, *_ = self.epic_with_changes()

        section = section_of(self.page_for(epic), "What nothing checked")

        self.assertIn("A card the bank declines", section)
        self.assertIn(f"shop, window tests: {test_validation.HAND_RUN_REASON}. Run {test_validation.HAND_RUN_COMMAND}",
                      section)

    def test_cost_gives_the_seconds_validation_recorded_and_says_so_when_there_are_none(self):
        epic, *_ = self.epic_with_changes()
        seconds = test_validation.recorded_validation.read(self.metadata(epic)).seconds
        self.assertIn(f"Validation took {seconds} s.", section_of(self.page_for(epic), "Cost"))
        self.bd_here("update", epic, "--unset-metadata", "validation.runs")

        self.assertIn("No validation time is recorded on this epic.", section_of(self.page_for(epic), "Cost"))


class MergeDangerTests(GatePageCase):
    def test_main_and_the_epic_branch_that_have_not_moved_since_validation_are_said_to_be_still(self):
        epic, *_ = self.epic_at_the_gate()

        section = section_of(self.page_for(epic), "Merge danger")

        self.assertIn("Main has not moved since validation.", section)
        self.assertNotIn("Merge runs the full suite again", section)

    def test_main_that_moved_since_validation_says_merge_runs_the_full_suite_again(self):
        epic, *_ = self.epic_with_changes()
        (self.repo / "later.txt").write_text("later\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Add later")

        section = section_of(self.page_for(epic), "Merge danger")

        self.assertIn("Main holds commits that validation did not check", section)

    def test_an_epic_branch_that_moved_past_the_validated_commit_says_merge_runs_the_full_suite_again(self):
        epic, *_ = self.epic_with_changes()

        section = section_of(self.page_for(epic), "Merge danger")

        self.assertIn("The epic branch moved past the commit validation checked", section)
        self.assertNotIn("Main has not moved since validation.", section)

    def test_a_file_that_main_and_the_epic_both_changed_is_named(self):
        epic, _, _, number = self.epic_with_changes()
        (self.repo / f"menu-{number}.txt").write_text("espresso 2.75\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Raise the espresso")

        section = section_of(self.page_for(epic), "Merge danger")

        self.assertIn(f"Main and the epic both changed menu-{number}.txt", section)

    def test_uncommitted_edits_in_main_over_a_file_the_epic_changed_are_named(self):
        epic, _, _, number = self.epic_with_changes()
        edited = self.repo / f"menu-{number}.txt"
        edited.write_text("edited by hand\n", encoding="utf-8")
        self.addCleanup(lambda: test_scheduler.git(self.repo, "checkout", "--", f"menu-{number}.txt"))

        section = section_of(self.page_for(epic), "Merge danger")

        self.assertIn(f"Uncommitted edits in the main checkout touch menu-{number}.txt", section)


class DecideTests(GatePageCase):
    def test_decide_marks_one_slot_for_the_panel_that_jidoka_ui_draws(self):
        epic, *_ = self.epic_with_changes()

        html = self.page_for(epic)

        self.assertEqual(1, html.count('data-jidoka-slot="decide-panel"'))
        self.assertIn('<section class="answer-slot" data-jidoka-slot="decide-panel">\n<h2>Decide</h2>', html)

    def test_the_decide_placeholder_names_merge_and_drop_and_says_send_back_runs_in_accept(self):
        epic, *_ = self.epic_with_changes()

        html = self.page_for(epic)

        self.assertIn("jidoka-ui draws Merge and Drop here.", html)
        self.assertIn("/jidoka:accept", html)
        self.assertNotIn("Merge and Send back", html)


class RefusalTests(GatePageCase):
    def test_an_epic_that_does_not_wait_at_the_gate_gets_no_page(self):
        epic = self.new_epic()

        done = self.launch(GATE_PAGE, epic, "--guide", str(self.write_guide("guide")))

        self.assertEqual(1, done.returncode)
        self.assertIn("does not wait at the acceptance gate", done.stderr)
        self.assertEqual([], list((self.home / "pages").rglob(f"gate-{epic}.html")))

    def test_a_guide_without_an_in_short_is_refused_and_writes_nothing(self):
        epic, *_ = self.epic_with_changes()

        done = self.launch(GATE_PAGE, epic, "--guide", str(self.write_guide("guide", in_short="")))

        self.assertEqual(1, done.returncode)
        self.assertIn("in_short must be a non-empty string", done.stderr)
        self.assertEqual([], list((self.home / "pages").rglob(f"gate-{epic}.html")))

    def test_steps_that_are_not_a_list_of_text_are_refused(self):
        epic, *_ = self.epic_with_changes()

        done = self.launch(GATE_PAGE, epic, "--guide", str(self.write_guide("guide", steps="open the till")))

        self.assertEqual(1, done.returncode)
        self.assertIn("steps must be a list of non-empty strings", done.stderr)

    def test_a_missing_guide_is_refused(self):
        epic, *_ = self.epic_with_changes()

        done = self.launch(GATE_PAGE, epic, "--guide", str(self.root / "nowhere.json"))

        self.assertEqual(1, done.returncode)
        self.assertIn("cannot be read as JSON", done.stderr)


if __name__ == "__main__":
    unittest.main()
