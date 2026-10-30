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

import jidoka_fixture as fixture

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
    """Runs each script a skill carries the way the skill names it: sh, the launcher, then the script, from inside the repo,
    with the fake bd first on the PATH. Everything sits below a user folder that holds a .beads, as the temporary folder
    of a user who runs bd does."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        user_folder = Path(cls.tmp.name).resolve() / "user"
        (user_folder / ".beads").mkdir(parents=True)
        cls.root = user_folder / "work"
        cls.root.mkdir()
        cls.home = cls.root / "jidoka-home"
        cls.home.mkdir()
        (cls.home / "python").write_text(sys.executable + "\n", encoding="utf-8")

        cls.repo = cls.root / "shop"
        fixture.init_repo(cls.repo)
        (cls.repo / "CLAUDE.md").write_text("x" * (CLAUDE_MD_BYTES - 1) + "\n", encoding="utf-8")
        fixture.git_commit_all(cls.repo, "Start")
        cls.bin = cls.root / "bin"
        cls.bd = str(fixture.add_fake_beads(cls.repo, cls.bin))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def create_bead(cls, repo: Path, title: str, description: str, flags: list) -> str:
        created = fixture.run([cls.bd, "create", "--title", title, "--description", description,
                               *flags, "--json"], repo)
        return json.loads(created)["id"]

    def run_script(self, script: Path, args: list, home: str, cwd: Path) -> subprocess.CompletedProcess:
        env = {**os.environ, "PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
               **fixture.home_variables(home)}
        return fixture.run_launcher(LAUNCHER, [str(script), *args], None, env, cwd, None)


class ShopIssuesTests(SkillScriptCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.greeting = cls.create_bead(cls.repo, "Print the greeting", WITH_DEMO, ["--type=task"])
        cls.farewell = cls.create_bead(cls.repo, "Print the farewell", WITHOUT_DEMO, ["--type=task"])
        cls.goodbye = cls.create_bead(cls.repo, "Wave goodbye", WITH_DEMO, ["--type=task", f"--deps={cls.greeting}"])

    def test_issues_lists_the_ready_beads_on_the_board(self):
        done = self.run_script(ISSUES, [], str(Path.home()), self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"Print the greeting ({self.greeting}) · ready ✓", done.stdout)
        self.assertIn(f"Print the farewell ({self.farewell}) · ready · no demo", done.stdout)
        self.assertIn("ready 2 · blocked 1 · needs you 0", done.stdout)

    def test_issues_shows_one_bead_with_its_description(self):
        done = self.run_script(ISSUES, [self.greeting], str(Path.home()), self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertTrue(done.stdout.startswith(f"Print the greeting  ({self.greeting})\n"), done.stdout)
        self.assertIn("The shop prints hello at startup.", done.stdout)

    def test_issues_sends_a_bead_without_a_demo_line_back_to_jidoka_planning(self):
        done = self.run_script(ISSUES, [self.farewell], str(Path.home()), self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("next: no Demo line — /jidoka:grill-with-docs or /jidoka:to-tickets before implementing",
                      done.stdout)

    def test_issues_says_a_ready_bead_with_a_demo_line_is_ready_to_build(self):
        done = self.run_script(ISSUES, [self.greeting], str(Path.home()), self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"next: ready to build with /jidoka:bench {self.greeting}", done.stdout)

    def test_issues_sends_a_blocked_bead_to_its_blocker(self):
        done = self.run_script(ISSUES, [self.goodbye], str(Path.home()), self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"next: look at the blocker first ({self.greeting})", done.stdout)

    def test_issues_reports_no_failed_bd_call_on_the_board_a_bead_page_or_a_search(self):
        for args in [[], [self.greeting], [self.goodbye], ["greeting"]]:
            with self.subTest(args=args):
                done = self.run_script(ISSUES, args, str(Path.home()), self.repo)

                self.assertEqual(0, done.returncode, done.stderr)
                self.assertEqual("", done.stderr)

    def run_issues_under_a_locale_that_reads_only_ascii(self, args: list, bin_dir: Path) -> subprocess.CompletedProcess:
        """Runs issues.py as a Windows console does, where text read from a child process is decoded with a code page
        that is not UTF-8."""
        env = {**os.environ, "PATH": fixture.path_with(bin_dir), "JIDOKA_HOME": str(self.home),
               **fixture.home_variables(str(Path.home())), "LC_ALL": "C", "LANG": "C",
               "PYTHONCOERCECLOCALE": "0", "PYTHONUTF8": "0"}
        return fixture.run_launcher(LAUNCHER, [str(ISSUES), *args], None, env, self.repo, None)

    def test_issues_shows_a_bead_whose_title_holds_characters_the_console_code_page_lacks(self):
        """The bd here prints the em dash as the UTF-8 bytes that real bd prints; the fake bd escapes it to ASCII."""
        bead = ('[{"id":"shop-9","title":"Print the greeting \\342\\200\\224 twice","status":"open",'
                '"issue_type":"task","priority":2}]')
        bin_dir = self.root / "bd-with-an-em-dash"
        bin_dir.mkdir()
        fixture.write_executable(bin_dir / "bd", "#!/bin/sh\n"
                                 f"case \"$1 $2\" in\n  'list --status=open'|'ready --json'|show*) printf '{bead}' ;;\n"
                                 "  *) printf '[]' ;;\nesac\n")

        for args in [[], ["shop-9"]]:
            with self.subTest(args=args):
                done = self.run_issues_under_a_locale_that_reads_only_ascii(args, bin_dir)

                self.assertEqual(0, done.returncode, done.stderr)
                self.assertEqual("", done.stderr)
                self.assertIn("Print the greeting — twice", done.stdout)

    def test_issues_never_points_a_ready_unplanned_or_blocked_bead_at_a_tracer_command(self):
        for args in [[], [self.greeting], [self.farewell], [self.goodbye]]:
            with self.subTest(args=args):
                done = self.run_script(ISSUES, args, str(Path.home()), self.repo)

                self.assertEqual(0, done.returncode, done.stderr)
                self.assertNotIn("/tracer:", done.stdout)


class AtlasIssuesTests(SkillScriptCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.atlas = cls.root / "atlas"
        fixture.init_repo(cls.atlas)
        fixture.add_fake_beads(cls.atlas, cls.bin)
        cls.map = cls.create_bead(cls.atlas, "Take payments", MAP, ["--type=epic", "--labels=wayfinder:map"])
        cls.question = cls.create_bead(cls.atlas, "Pick a payment provider", QUESTION,
                                       ["--type=task", f"--parent={cls.map}", "--labels=wayfinder:research"])
        cls.receipt = cls.create_bead(cls.atlas, "Print the receipt", WITH_DEMO, ["--type=task", "--labels=bench"])

    def test_issues_sends_a_wayfinder_bead_to_the_wayfinder_with_its_map(self):
        done = self.run_script(ISSUES, [self.question], str(Path.home()), self.atlas)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"next: /jidoka:wayfinder {self.map}", done.stdout)
        self.assertNotIn("no Demo line", done.stdout)

    def test_issues_counts_a_bench_bead_as_needing_you(self):
        done = self.run_script(ISSUES, [], str(Path.home()), self.atlas)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"Print the receipt ({self.receipt}) · needs you ✓", done.stdout)
        self.assertRegex(done.stdout, r"\nready \d+ · blocked 0 · needs you 1")

    def test_issues_sends_a_bench_bead_to_the_bench(self):
        done = self.run_script(ISSUES, [self.receipt], str(Path.home()), self.atlas)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"next: needs you at the bench, /jidoka:bench {self.receipt}", done.stdout)

    def test_issues_never_points_at_a_tracer_command(self):
        views = [[], [self.receipt], [self.question], ["--label", "wayfinder:research"], ["bench"], ["receipt"]]
        for args in views:
            with self.subTest(args=args):
                done = self.run_script(ISSUES, args, str(Path.home()), self.atlas)

                self.assertEqual(0, done.returncode, done.stderr)
                self.assertNotIn("/tracer:", done.stdout)


class DecisionLogTests(SkillScriptCase):
    def test_the_decision_log_gets_its_header_and_the_row_it_was_given_relative_to_the_repo(self):
        cells = ["build", "kept the old parser", "the new one drops comments", "commit 3a9f1c2", "tests green"]

        done = self.run_script(LOG, [".audit/greeting.tsv", *cells], str(Path.home()), self.repo)

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
        self.assertEqual(1, len(hook), f"{done.stdout}\n{done.stderr}")
        self.assertGreater(float(hook[0].split()[0]), 0, f"{done.stdout}\n{done.stderr}")
        self.assertNotIn("tracer", done.stdout.lower())

    def run_context_with_only(self, cmd: Path, plugin: Path) -> subprocess.CompletedProcess:
        env = {**os.environ, "PATH": str(cmd), "JIDOKA_HOME": str(self.home),
               **fixture.home_variables(self.empty_home)}
        return fixture.run_launcher(LAUNCHER, [str(plugin / CONTEXT), "--min", "0"], None, env, self.repo, None)

    def git_for_windows_without_sh_on_the_path(self) -> Path:
        """The cmd folder of a Git for Windows laid out on disk: git and bd in it, and sh in usr/bin two folders
        above git, so that no PATH entry reaches sh."""
        layout = self.root / "git-for-windows"
        cmd, usr_bin = layout / "cmd", layout / "usr" / "bin"
        cmd.mkdir(parents=True, exist_ok=True)
        usr_bin.mkdir(parents=True, exist_ok=True)
        fixture.write_forwarder(cmd / "git", [fixture.real_tool("git")])
        fixture.write_forwarder(cmd / "bd", [sys.executable, str(Path(fixture.fake_bd.__file__).resolve())])
        fixture.write_forwarder(usr_bin / ("sh" if fixture.WINDOWS else "sh.exe"), [fixture.real_shell()])
        return cmd

    def test_context_measures_the_hook_when_sh_is_not_on_the_path_but_sits_beside_git(self):
        cmd = self.git_for_windows_without_sh_on_the_path()

        done = self.run_context_with_only(cmd, self.installed)

        self.assertEqual(0, done.returncode, done.stderr)
        rows = self.section(done.stdout, "Loads every session, before you type anything")
        hook = [row for row in rows if row.endswith("jidoka SessionStart hook output")]
        self.assertEqual(1, len(hook), f"{done.stdout}\n{done.stderr}")
        self.assertGreater(float(hook[0].split()[0]), 0, f"{done.stdout}\n{done.stderr}")

    def test_context_says_on_stderr_that_it_found_no_sh_for_the_hook_when_none_is_on_the_path_or_beside_git(self):
        cmd = self.git_for_windows_without_sh_on_the_path()
        for sh in (cmd.parent / "usr" / "bin").iterdir():
            sh.unlink()

        done = self.run_context_with_only(cmd, self.installed)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("jidoka SessionStart hook output", done.stdout)
        self.assertIn("jidoka SessionStart hook", done.stderr)
        self.assertIn("no sh", done.stderr)

    def test_context_names_the_command_the_exit_code_and_the_stderr_of_a_hook_that_fails(self):
        failing = self.root / "failing-plugin" / "jidoka"
        shutil.copytree(self.installed, failing, ignore=shutil.ignore_patterns("__pycache__"))
        (failing / "hooks" / "session_start.py").write_text(
            "import sys\nsys.stderr.write('the hook broke\\n')\nsys.exit(1)\n", encoding="utf-8")

        done = self.run_script(failing / CONTEXT, ["--min", "0"], str(self.empty_home), self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("jidoka SessionStart hook output", done.stdout)
        self.assertIn("jidoka SessionStart hook", done.stderr)
        self.assertIn("session_start.py", done.stderr)
        self.assertIn("exit code 1", done.stderr)
        self.assertIn("the hook broke", done.stderr)

    def test_context_measures_the_output_of_bd_prime_in_the_startup_section(self):
        done = self.run_context(self.empty_home, self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        rows = self.section(done.stdout, "Loads every session, before you type anything")
        prime = [row for row in rows if row.endswith("bd prime (SessionStart hook output)")]
        self.assertEqual(1, len(prime), done.stdout)
        self.assertRegex(prime[0], r"≈\s*[1-9][\d,]* tok", done.stdout)

    def run_context_under_a_locale_that_reads_only_ascii(self, repo: Path, bin_dir: Path) -> subprocess.CompletedProcess:
        """Runs context.py as a Windows console does, where text read from a child process is decoded with a code page
        that is not UTF-8."""
        env = {**os.environ, "PATH": fixture.path_with(bin_dir), "JIDOKA_HOME": str(self.home),
               **fixture.home_variables(self.empty_home), "LC_ALL": "C", "LANG": "C",
               "PYTHONCOERCECLOCALE": "0", "PYTHONUTF8": "0"}
        return fixture.run_launcher(LAUNCHER, [str(self.installed / CONTEXT), "--min", "0"], None, env, repo, None)

    def test_context_measures_the_output_of_bd_prime_when_it_holds_characters_the_console_code_page_lacks(self):
        bin_dir = self.root / "bd-with-a-check-mark"
        bin_dir.mkdir()
        fixture.write_executable(bin_dir / "bd", "#!/bin/sh\nprintf '# Beads Workflow \\342\\234\\223\\n'\n")

        done = self.run_context_under_a_locale_that_reads_only_ascii(self.repo, bin_dir)

        self.assertEqual(0, done.returncode, done.stderr)
        rows = self.section(done.stdout, "Loads every session, before you type anything")
        prime = [row for row in rows if row.endswith("bd prime (SessionStart hook output)")]
        self.assertEqual(1, len(prime), done.stdout)

    def test_context_names_the_repo_whose_folder_holds_characters_the_console_code_page_lacks(self):
        repo = self.root / "café"
        fixture.init_repo(repo)

        done = self.run_context_under_a_locale_that_reads_only_ascii(repo, self.bin)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(f"context for {repo}", done.stdout.splitlines()[0])

    def test_context_names_no_tracer_command_or_folder(self):
        done = self.run_context(self.empty_home, self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("tracer", done.stdout.lower())


if __name__ == "__main__":
    unittest.main()
