import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import test_scheduler  # noqa: E402

DESIGN_SCRIPT = test_scheduler.PLUGIN / "scripts" / "design_findings.py"


def problem(title: str, file: str = "till.py", line: int = 7, note: str = "It mixes pricing with printing.") -> dict:
    return {"file": file, "line": line, "title": title, "note": note}


class DesignFindingsTests(test_scheduler.SchedulerCase):
    def setUp(self):
        self.reports = self.root / "reports"
        self.reports.mkdir(exist_ok=True)
        self.started_with = {each["id"] for each in self.every_design_bead()}

    def file_report(self, epic: str, *problems: dict) -> subprocess.CompletedProcess:
        report = self.reports / f"{epic}.json"
        report.write_text(json.dumps(list(problems)), encoding="utf-8")
        return self.launch(DESIGN_SCRIPT, epic, str(report))

    def settled(self, epic: str, *problems: dict) -> list[dict]:
        done = self.file_report(epic, *problems)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def design_beads(self) -> list[dict]:
        """The open design beads this test filed: those the store held beyond the ones it started with."""
        return [each for each in self.every_design_bead() if each["id"] not in self.started_with]

    def every_design_bead(self) -> list[dict]:
        return json.loads(fixture.run([self.bd, "list", "--label", "design", "--type", "task", "--limit", "0",
                                       "--json"], self.repo))

    def sightings(self, bead: str) -> list[str]:
        return [each["text"] for each in self.comments(bead)]

    def test_a_problem_in_old_code_becomes_one_design_bead_outside_the_epic(self):
        epic = self.new_epic()

        [filed] = self.settled(epic, problem("Pricing and printing share a function"))

        [bead] = self.design_beads()
        self.assertEqual(filed["bead"], bead["id"])
        self.assertTrue(filed["new"])
        self.assertIn("design", self.shown(filed["bead"])["labels"])
        self.assertNotIn("parent", self.shown(filed["bead"]))
        self.assertEqual("open", bead["status"])
        self.assertIn("till.py", bead["title"])

    def test_a_problem_met_again_keeps_the_link_to_the_epic_that_filed_it(self):
        first, second = self.new_epic(), self.new_epic()
        [filed] = self.settled(first, problem("Discounts are applied after tax"))

        self.settled(second, problem("Discounts are applied after tax"))

        self.assertEqual({("discovered-from", first)}, self.links_of(filed["bead"]))

    def test_two_problems_become_two_beads(self):
        epic = self.new_epic()

        self.settled(epic, problem("Receipts know the tax table"), problem("The till reads the clock"))

        self.assertEqual(2, len(self.design_beads()))

    def test_two_epics_that_meet_the_same_problem_share_one_bead_with_two_sightings(self):
        first, second = self.new_epic(), self.new_epic()
        [filed] = self.settled(first, problem("Shared helper hides a global"))

        [again] = self.settled(second, problem("shared  HELPER hides a global", line=40))

        self.assertEqual(filed["bead"], again["bead"])
        self.assertFalse(again["new"])
        self.assertEqual(2, again["sightings"])
        [bead] = self.design_beads()
        sightings = self.sightings(bead["id"])
        self.assertEqual(2, len(sightings))
        self.assertIn(first, sightings[0])
        self.assertIn(second, sightings[1])
        self.assertIn("till.py:40", sightings[1])

    def test_the_same_title_in_another_file_is_another_problem(self):
        epic = self.new_epic()

        first = self.settled(epic, problem("Hidden global", file="a.py"))
        second = self.settled(epic, problem("Hidden global", file="b.py"))

        self.assertNotEqual(first[0]["bead"], second[0]["bead"])

    def test_a_report_that_names_one_problem_twice_counts_one_sighting(self):
        epic = self.new_epic()

        [filed] = self.settled(epic, problem("Twice named"), problem("Twice named", line=9))

        self.assertEqual(1, filed["sightings"])

    def test_a_closed_design_finding_is_not_met_again_but_filed_anew(self):
        epic = self.new_epic()
        [filed] = self.settled(epic, problem("Closed later"))
        fixture.run([self.bd, "close", filed["bead"], "--reason", "fixed"], self.repo)

        [again] = self.settled(epic, problem("Closed later"))

        self.assertNotEqual(filed["bead"], again["bead"])
        self.assertTrue(again["new"])

    def test_an_unusable_report_writes_nothing(self):
        epic = self.new_epic()

        done = self.file_report(epic, problem("Fine"), {"file": "till.py", "line": 0, "title": "No line", "note": "x"})

        self.assertEqual(1, done.returncode)
        self.assertIn("line", done.stderr)
        self.assertEqual([], self.design_beads())

    def open_findings(self, *files: str) -> list[dict]:
        done = self.launch(DESIGN_SCRIPT, "--open", *files)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def test_open_findings_come_most_sighted_first(self):
        first, second, third = self.new_epic(), self.new_epic(), self.new_epic()
        [once] = self.settled(first, problem("Seen once", file="a.py"))
        [thrice] = self.settled(first, problem("Seen thrice", file="b.py"))
        self.settled(second, problem("Seen thrice", file="b.py"))
        self.settled(third, problem("Seen thrice", file="b.py"))

        listed = [(each["bead"], each["sightings"]) for each in self.open_findings()
                  if each["bead"] in (once["bead"], thrice["bead"])]

        self.assertEqual([(thrice["bead"], 3), (once["bead"], 1)], listed)

    def test_open_findings_can_be_limited_to_the_files_an_epic_changes(self):
        epic = self.new_epic()
        [kept] = self.settled(epic, problem("In the changed file", file="changed.py"))
        self.settled(epic, problem("In another file", file="other.py"))

        listed = self.open_findings("changed.py")

        self.assertEqual([kept["bead"]], [each["bead"] for each in listed])
        self.assertEqual("changed.py", listed[0]["file"])

    def test_a_closed_finding_is_not_listed(self):
        epic = self.new_epic()
        [filed] = self.settled(epic, problem("Fixed since", file="gone.py"))
        fixture.run([self.bd, "close", filed["bead"], "--reason", "fixed"], self.repo)

        self.assertEqual([], self.open_findings("gone.py"))


if __name__ == "__main__":
    unittest.main()
