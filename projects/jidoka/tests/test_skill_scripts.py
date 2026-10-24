import json
import os
import re
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
SKILLS = PLUGIN / "skills"
ISSUES = SKILLS / "issues" / "issues.py"
LOG = SKILLS / "show-me-your-work" / "scripts" / "log.py"
BUDGET = SKILLS / "budget" / "budget.py"

WITH_DEMO = "## What\nPrint a greeting.\n\n## Demo\nThe shop prints hello at startup.\n\n## Seams\nThe command line."
WITHOUT_DEMO = "## What\nPrint a farewell."
MAP = "## Destination\nThe shop takes payments."
QUESTION = "Which payment provider fits a shop this size?"
CLAUDE_MD_BYTES = 2048


class SkillScriptTests(unittest.TestCase):
    """Runs each script a skill carries the way the skill names it: sh, the launcher, then the script, from inside the repo."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.home = cls.root / "jidoka-home"
        cls.home.mkdir()
        (cls.home / "python").write_text(sys.executable + "\n", encoding="utf-8")

        cls.repo = cls.root / "shop"
        fixture.init_repo(cls.repo)
        (cls.repo / "CLAUDE.md").write_text("x" * (CLAUDE_MD_BYTES - 1) + "\n", encoding="utf-8")
        fixture.git_commit_all(cls.repo, "Start")
        cls.bd = fixture.real_tool("bd")
        fixture.run([cls.bd, "init", "--stealth", "--non-interactive"], cls.repo)
        cls.greeting = cls.create_bead(cls.repo, "Print the greeting", WITH_DEMO, ["--type=task"])
        cls.farewell = cls.create_bead(cls.repo, "Print the farewell", WITHOUT_DEMO, ["--type=task"])

        cls.atlas = cls.root / "atlas"
        fixture.init_repo(cls.atlas)
        fixture.run([cls.bd, "init", "--stealth", "--non-interactive"], cls.atlas)
        cls.map = cls.create_bead(cls.atlas, "Take payments", MAP, ["--type=epic", "--labels=wayfinder:map"])
        cls.question = cls.create_bead(cls.atlas, "Pick a payment provider", QUESTION,
                                       ["--type=task", f"--parent={cls.map}", "--labels=wayfinder:research"])
        cls.receipt = cls.create_bead(cls.atlas, "Print the receipt", WITH_DEMO, ["--type=task", "--labels=bench"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def create_bead(cls, repo: Path, title: str, description: str, flags: list) -> str:
        created = fixture.run([cls.bd, "create", "--title", title, "--description", description,
                               *flags, "--json"], repo)
        return json.loads(created)["id"]

    def run_script(self, script: Path, args: list, home: str, cwd: Path) -> subprocess.CompletedProcess:
        env = {**os.environ, "JIDOKA_HOME": str(self.home), "HOME": home}
        return subprocess.run(["sh", str(LAUNCHER), str(script), *args], capture_output=True, text=True,
                              encoding="utf-8", env=env, cwd=cwd)

    def test_issues_lists_the_ready_beads_on_the_board(self):
        done = self.run_script(ISSUES, [], os.environ["HOME"], self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"Print the greeting ({self.greeting}) · ready ✓", done.stdout)
        self.assertIn(f"Print the farewell ({self.farewell}) · ready · no demo", done.stdout)
        self.assertIn("ready 2 · blocked 0 · needs you 0", done.stdout)

    def test_issues_shows_one_bead_with_its_description(self):
        done = self.run_script(ISSUES, [self.greeting], os.environ["HOME"], self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertTrue(done.stdout.startswith(f"Print the greeting  ({self.greeting})\n"), done.stdout)
        self.assertIn("The shop prints hello at startup.", done.stdout)

    def test_issues_sends_a_bead_without_a_demo_line_back_to_jidoka_planning(self):
        done = self.run_script(ISSUES, [self.farewell], os.environ["HOME"], self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("next: no Demo line — /jidoka:grill-with-docs or /jidoka:to-tickets before implementing",
                      done.stdout)

    def test_issues_sends_a_wayfinder_bead_to_the_wayfinder_with_its_map(self):
        done = self.run_script(ISSUES, [self.question], os.environ["HOME"], self.atlas)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"next: /jidoka:wayfinder {self.map}", done.stdout)
        self.assertNotIn("no Demo line", done.stdout)

    def test_issues_says_a_ready_bead_with_a_demo_line_is_ready_to_build(self):
        done = self.run_script(ISSUES, [self.greeting], os.environ["HOME"], self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"next: ready to build with /jidoka:bench {self.greeting}", done.stdout)

    def test_issues_counts_a_bench_bead_as_needing_you(self):
        done = self.run_script(ISSUES, [], os.environ["HOME"], self.atlas)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"Print the receipt ({self.receipt}) · needs you ✓", done.stdout)
        self.assertRegex(done.stdout, r"\nready \d+ · blocked 0 · needs you 1")

    def test_issues_sends_a_bench_bead_to_the_bench(self):
        done = self.run_script(ISSUES, [self.receipt], os.environ["HOME"], self.atlas)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"next: needs you at the bench, /jidoka:bench {self.receipt}", done.stdout)

    def test_the_decision_log_gets_its_header_and_the_row_it_was_given_relative_to_the_repo(self):
        cells = ["build", "kept the old parser", "the new one drops comments", "commit 3a9f1c2", "tests green"]

        done = self.run_script(LOG, [".audit/greeting.tsv", *cells], os.environ["HOME"], self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        lines = (self.repo / ".audit" / "greeting.tsv").read_text(encoding="utf-8").splitlines()
        self.assertEqual("ts\tphase\tdecision\twhy\tevidence\tresult", lines[0])
        row = lines[1].split("\t")
        self.assertRegex(row[0], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(cells, row[1:])

    def test_budget_measures_the_claude_md_of_the_repo_it_runs_in(self):
        empty_home = self.root / "empty-home"
        empty_home.mkdir(exist_ok=True)

        done = self.run_script(BUDGET, ["--min", "0"], str(empty_home), self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"context budget for {self.repo}", done.stdout)
        claude_md_rows = [line for line in done.stdout.splitlines() if line.split()[-1:] == ["CLAUDE.md"]]
        self.assertEqual(1, len(claude_md_rows), done.stdout)
        self.assertRegex(claude_md_rows[0], r"^\s+2\.0 KB\s+1 lines\s")

    def test_budget_finds_the_auto_memory_of_a_repo_whose_path_holds_dots_and_underscores(self):
        repo = self.root / "my_shop.v2"
        fixture.init_repo(repo)
        home = self.root / "memory-home"
        memory = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(repo)) / "memory"
        memory.mkdir(parents=True)
        (memory / "MEMORY.md").write_text("- [Spelling](spelling.md) — American spelling.\n", encoding="utf-8")

        done = self.run_script(BUDGET, ["--min", "0"], str(home), repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("auto-memory MEMORY.md", done.stdout)


if __name__ == "__main__":
    unittest.main()
