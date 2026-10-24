import json
import os
import re
import shutil
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
CONTEXT = Path("skills") / "context" / "context.py"

WITH_DEMO = "## What\nPrint a greeting.\n\n## Demo\nThe shop prints hello at startup.\n\n## Seams\nThe command line."
WITHOUT_DEMO = "## What\nPrint a farewell."
MAP = "## Destination\nThe shop takes payments."
QUESTION = "Which payment provider fits a shop this size?"
CLAUDE_MD_BYTES = 2048
TRACKER_DOC_BYTES = 3072
DOMAIN_DOC_BYTES = 5120


class SkillScriptCase(unittest.TestCase):
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
        fixture.add_stealth_beads(cls.repo)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def create_bead(cls, repo: Path, title: str, description: str, flags: list) -> str:
        created = fixture.run([cls.bd, "create", "--title", title, "--description", description,
                               *flags, "--json"], repo)
        return json.loads(created)["id"]

    def run_script(self, script: Path, args: list, home: str, cwd: Path) -> subprocess.CompletedProcess:
        # bd writes its event queue under HOME after it exits unless told not to, which races the removal of a temporary HOME.
        env = {**os.environ, "JIDOKA_HOME": str(self.home), "HOME": home, "BD_DISABLE_EVENT_FLUSH": "1"}
        return subprocess.run(["sh", str(LAUNCHER), str(script), *args], capture_output=True, text=True,
                              encoding="utf-8", env=env, cwd=cwd)


class ShopIssuesTests(SkillScriptCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.greeting = cls.create_bead(cls.repo, "Print the greeting", WITH_DEMO, ["--type=task"])
        cls.farewell = cls.create_bead(cls.repo, "Print the farewell", WITHOUT_DEMO, ["--type=task"])

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

    def test_issues_says_a_ready_bead_with_a_demo_line_is_ready_to_build(self):
        done = self.run_script(ISSUES, [self.greeting], os.environ["HOME"], self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"next: ready to build with /jidoka:bench {self.greeting}", done.stdout)


class AtlasIssuesTests(SkillScriptCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.atlas = cls.root / "atlas"
        fixture.init_repo(cls.atlas)
        fixture.add_stealth_beads(cls.atlas)
        cls.map = cls.create_bead(cls.atlas, "Take payments", MAP, ["--type=epic", "--labels=wayfinder:map"])
        cls.question = cls.create_bead(cls.atlas, "Pick a payment provider", QUESTION,
                                       ["--type=task", f"--parent={cls.map}", "--labels=wayfinder:research"])
        cls.receipt = cls.create_bead(cls.atlas, "Print the receipt", WITH_DEMO, ["--type=task", "--labels=bench"])

    def test_issues_sends_a_wayfinder_bead_to_the_wayfinder_with_its_map(self):
        done = self.run_script(ISSUES, [self.question], os.environ["HOME"], self.atlas)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"next: /jidoka:wayfinder {self.map}", done.stdout)
        self.assertNotIn("no Demo line", done.stdout)

    def test_issues_counts_a_bench_bead_as_needing_you(self):
        done = self.run_script(ISSUES, [], os.environ["HOME"], self.atlas)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"Print the receipt ({self.receipt}) · needs you ✓", done.stdout)
        self.assertRegex(done.stdout, r"\nready \d+ · blocked 0 · needs you 1")

    def test_issues_sends_a_bench_bead_to_the_bench(self):
        done = self.run_script(ISSUES, [self.receipt], os.environ["HOME"], self.atlas)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"next: needs you at the bench, /jidoka:bench {self.receipt}", done.stdout)


class DecisionLogTests(SkillScriptCase):
    def test_the_decision_log_gets_its_header_and_the_row_it_was_given_relative_to_the_repo(self):
        cells = ["build", "kept the old parser", "the new one drops comments", "commit 3a9f1c2", "tests green"]

        done = self.run_script(LOG, [".audit/greeting.tsv", *cells], os.environ["HOME"], self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        lines = (self.repo / ".audit" / "greeting.tsv").read_text(encoding="utf-8").splitlines()
        self.assertEqual("ts\tphase\tdecision\twhy\tevidence\tresult", lines[0])
        row = lines[1].split("\t")
        self.assertRegex(row[0], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(cells, row[1:])


class ContextFromAnInstalledPluginInARepoWithoutOneTests(SkillScriptCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.installed = cls.home / "plugins" / "9.9.9" / "jidoka"
        shutil.copytree(PLUGIN, cls.installed, ignore=shutil.ignore_patterns("__pycache__"))
        (cls.installed / "docs" / "issue-tracker.md").write_text("t" * (TRACKER_DOC_BYTES - 1) + "\n", encoding="utf-8")
        (cls.installed / "docs" / "domain.md").write_text("d" * (DOMAIN_DOC_BYTES - 1) + "\n", encoding="utf-8")
        cls.empty_home = cls.root / "empty-home"
        cls.empty_home.mkdir()

    def run_context(self, home: Path, repo: Path) -> subprocess.CompletedProcess:
        return self.run_script(self.installed / CONTEXT, ["--min", "0"], str(home), repo)

    def section(self, report: str, heading: str) -> list:
        """The rows under the heading that starts with the given text, up to the next blank line."""
        lines = report.splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith(heading))
        rows = []
        for line in lines[start + 1:]:
            if not line.strip():
                break
            rows.append(line)
        return rows

    def test_context_measures_the_claude_md_of_the_repo_it_runs_in(self):
        done = self.run_context(self.empty_home, self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(f"context for {self.repo}", done.stdout.splitlines()[0])
        claude_md_rows = [line for line in done.stdout.splitlines() if line.split()[-1:] == ["CLAUDE.md"]]
        self.assertEqual(1, len(claude_md_rows), done.stdout)
        self.assertRegex(claude_md_rows[0], r"^\s+2\.0 KB\s+1 lines\s")

    def test_context_finds_the_auto_memory_of_a_repo_whose_path_holds_dots_and_underscores(self):
        repo = self.root / "my_shop.v2"
        fixture.init_repo(repo)
        home = self.root / "memory-home"
        memory = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(repo)) / "memory"
        memory.mkdir(parents=True)
        (memory / "MEMORY.md").write_text("- [Spelling](spelling.md) — American spelling.\n", encoding="utf-8")

        done = self.run_context(home, repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("auto-memory MEMORY.md", done.stdout)

    def test_context_lists_every_skill_the_installed_plugin_carries_with_a_size(self):
        done = self.run_context(self.empty_home, self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        rows = self.section(done.stdout, "Each skill, loaded only when invoked")
        measured = [re.match(r"^\s+([\d.]+) KB\s+\d+ lines\s+≈\s*[\d,]+ tok  (.+?)(?:  ⚠)?$", row) for row in rows]
        sizes = {m.group(2): float(m.group(1)) for m in measured if m}
        carried = sorted(d.name for d in (self.installed / "skills").iterdir() if d.is_dir())
        self.assertEqual(carried, sorted(sizes), done.stdout)
        self.assertIn("bench", sizes)
        self.assertIn("context", sizes)
        self.assertEqual([], [name for name, kb in sizes.items() if kb <= 0], done.stdout)

    def test_context_heads_the_bench_section_with_the_plugins_tracker_and_domain_docs_and_the_skills_bench_loads(self):
        done = self.run_context(self.empty_home, self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        rows = self.section(done.stdout, "Added when /jidoka:bench runs")
        tracker = [row for row in rows if "issue-tracker.md" in row]
        domain = [row for row in rows if "domain.md" in row]
        self.assertEqual(1, len(tracker), done.stdout)
        self.assertRegex(tracker[0], r"^\s+3\.0 KB\s+1 lines\s.*tracker doc")
        self.assertEqual(1, len(domain), done.stdout)
        self.assertRegex(domain[0], r"^\s+5\.0 KB\s+1 lines\s.*domain doc")
        for skill in ("bench", "tdd", "unslop", "spec-check", "no-comments"):
            self.assertTrue(any(re.search(rf"\sskill {skill} \(\d+ files?\)$", row) for row in rows),
                            f"no row for skill {skill}:\n{done.stdout}")

    def test_context_measures_the_output_of_jidokas_session_start_hook_in_the_startup_section(self):
        done = self.run_context(self.empty_home, self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        rows = self.section(done.stdout, "Loads every session, before you type anything")
        hook = [row for row in rows if row.endswith("jidoka SessionStart hook output")]
        self.assertEqual(1, len(hook), done.stdout)
        self.assertGreater(float(hook[0].split()[0]), 0, done.stdout)
        self.assertNotIn("tracer", done.stdout.lower())

    def test_context_names_no_tracer_command_or_folder(self):
        done = self.run_context(self.empty_home, self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("tracer", done.stdout.lower())


if __name__ == "__main__":
    unittest.main()
