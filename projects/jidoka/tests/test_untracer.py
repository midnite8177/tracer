import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import tracer_fixture as fixture  # noqa: E402

SCRIPT = HERE.parent / "untracer.py"


def run_untracer(repo: Path, home: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--jidoka-home", str(home)],
        capture_output=True, text=True, encoding="utf-8")


class UntracerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "jidoka-home"

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_folder_that_is_not_a_git_repo_is_refused_and_nothing_is_written(self):
        folder = self.root / "plain"
        folder.mkdir()
        (folder / "docs").mkdir()
        (folder / "docs" / "tracer.md").write_text("Seed revision 42\n", encoding="utf-8")

        done = run_untracer(folder, self.home)

        self.assertEqual(2, done.returncode)
        self.assertIn("not a git repository", done.stderr)
        self.assertTrue((folder / "docs" / "tracer.md").is_file())
        self.assertFalse(self.home.exists())

    def test_a_git_folder_that_is_a_file_is_refused_and_nothing_is_written(self):
        folder = self.root / "worktree"
        folder.mkdir()
        (folder / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
        (folder / "docs").mkdir()
        (folder / "docs" / "tracer.md").write_text("Seed revision 42\n", encoding="utf-8")

        done = run_untracer(folder, self.home)

        self.assertEqual(2, done.returncode)
        self.assertIn("not a git repository", done.stderr)
        self.assertTrue((folder / "docs" / "tracer.md").is_file())
        self.assertFalse(self.home.exists())

    def test_a_file_that_is_not_utf8_stops_the_run_with_a_message_before_anything_changes(self):
        folder = self.root / "repo"
        (folder / ".git" / "info").mkdir(parents=True)
        (folder / ".git" / "info" / "exclude").write_bytes(b"docs/tracer.md\n\xff\xfe\n")
        (folder / "docs").mkdir()
        (folder / "docs" / "tracer.md").write_text("Seed revision 42\n", encoding="utf-8")

        done = run_untracer(folder, self.home)

        self.assertEqual(2, done.returncode)
        self.assertNotIn("Traceback", done.stderr)
        self.assertTrue((folder / "docs" / "tracer.md").is_file())
        self.assertFalse(self.home.exists())

    def test_the_backup_goes_under_the_users_jidoka_folder_when_no_home_is_given(self):
        folder = self.root / "repo"
        (folder / ".git").mkdir(parents=True)
        (folder / "docs").mkdir()
        (folder / "docs" / "tracer.md").write_text("Seed revision 42\n", encoding="utf-8")
        env = {**os.environ, "HOME": str(self.root), "USERPROFILE": str(self.root)}

        done = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(folder)],
                              capture_output=True, text=True, encoding="utf-8", env=env)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertTrue((self.root / ".jidoka" / "untracer").is_dir())
        self.assertFalse((folder / "docs" / "tracer.md").exists())


class InstalledRepoTests(unittest.TestCase):
    REVISION = 42
    template: Path

    @classmethod
    def setUpClass(cls):
        cls.template_dir = tempfile.TemporaryDirectory()
        cls.template = Path(cls.template_dir.name) / "repo"
        cls.build_template()

    @classmethod
    def build_template(cls) -> None:
        fixture.build_fake_bd_repo(cls.template, cls.template.parent / "bin")

    @classmethod
    def tearDownClass(cls):
        cls.template_dir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "jidoka-home"
        self.repo = self.root / "work" / "shop"
        self.repo.parent.mkdir()
        self.install()

    def install(self) -> None:
        fixture.make_with_tracer(self.template, self.repo, self.REVISION)

    def tearDown(self):
        self.tmp.cleanup()

    def backups(self) -> list:
        return sorted((self.home / "untracer").glob("*/*"))

    def removed_paths(self, stdout: str) -> list:
        return [line[len("removed "):] for line in stdout.splitlines() if line.startswith("removed ")]


class RealBdTemplate:
    """Builds the template with the real bd, for the tests that check the bytes bd writes: its hooks, its marked block
    in CLAUDE.md, its info/exclude heading and its workspace."""

    @classmethod
    def build_template(cls) -> None:
        fixture.build_bd_repo(cls.template)


class RemovalTests(InstalledRepoTests):
    def test_it_prints_the_plan_and_then_removes_tracers_files(self):
        before = fixture.read_tree(self.repo)
        tracer_paths = [p for p in before if p.startswith((".claude/skills/tracer/", "docs/agents/"))
                        or p in ("docs/tracer.md", "docs/tracer-adopt-notes.md",
                                 ".claude/statusline.py", ".claude/statusline.sh")]
        self.assertGreater(len(tracer_paths), 10)

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        for path in tracer_paths:
            self.assertFalse((self.repo / path).exists(), path)
        out = done.stdout.splitlines()
        self.assertIn("Will delete:", out)
        self.assertIn("Will keep:", out)
        self.assertLess(out.index("Will delete:"), out.index("Will keep:"))
        first_removed = next(i for i, line in enumerate(out) if line.startswith("removed "))
        self.assertLess(out.index("Will keep:"), first_removed)
        planned = out[out.index("Will delete:") + 1:out.index("Will keep:")]
        for path in (".claude/skills/tracer/", "docs/agents/", "docs/tracer.md",
                     "docs/tracer-adopt-notes.md", ".claude/statusline.py", ".claude/statusline.sh"):
            self.assertIn("  " + path, planned)

    def test_every_removed_or_edited_file_has_a_byte_identical_copy_in_the_backup(self):
        before = fixture.read_tree(self.repo)

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        after = fixture.read_tree(self.repo)
        changed = [p for p in before if before[p] != after.get(p)]
        self.assertIn("docs/tracer.md", changed)
        self.assertIn(".claude/skills/tracer/.claude-plugin/plugin.json", changed)
        self.assertIn(".claude/settings.local.json", changed)
        self.assertIn(".git/info/exclude", changed)
        backups = self.backups()
        self.assertEqual(1, len(backups))
        saved = fixture.read_tree(backups[0])
        self.assertEqual(sorted(changed), sorted(saved))
        for path in changed:
            self.assertEqual(before[path], saved[path], path)
        self.assertIn(str(backups[0]), done.stdout)

    def test_the_backup_lives_under_the_jidoka_home_in_a_folder_for_this_repo(self):
        run_untracer(self.repo, self.home)

        (backup,) = self.backups()
        self.assertEqual(self.home / "untracer", backup.parent.parent)
        self.assertTrue(backup.parent.name.startswith("shop-"))

    def test_the_status_line_key_goes_and_the_rest_of_the_settings_file_stays(self):
        run_untracer(self.repo, self.home)

        settings = json.loads((self.repo / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
        self.assertEqual({"permissions": {"allow": ["Bash(bd:*)"]}, "env": {"EXAMPLE": "1"}}, settings)

    def test_a_settings_file_left_with_no_keys_stays_as_an_empty_object(self):
        (self.repo / ".claude" / "settings.local.json").write_text(
            '{"statusLine": {"type": "command", "command": "x"}}\n', encoding="utf-8")

        run_untracer(self.repo, self.home)

        settings = json.loads((self.repo / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
        self.assertEqual({}, settings)

    def test_docs_tracer_md_is_the_last_thing_removed(self):
        done = run_untracer(self.repo, self.home)

        removed = self.removed_paths(done.stdout)
        self.assertEqual("docs/tracer.md", removed[-1])
        self.assertEqual(1, removed.count("docs/tracer.md"))
        self.assertGreater(len(removed), 4)
        self.assertEqual("edited .git/info/exclude", done.stdout.splitlines()[-2])

    def test_a_settings_file_that_is_not_json_stops_the_run_before_anything_changes(self):
        (self.repo / ".claude" / "settings.local.json").write_text("{not json", encoding="utf-8")
        before = fixture.read_tree(self.repo)

        done = run_untracer(self.repo, self.home)

        self.assertEqual(2, done.returncode)
        self.assertIn("not valid JSON", done.stderr)
        self.assertEqual(before, fixture.read_tree(self.repo))
        self.assertFalse(self.home.exists())

    def test_an_exclude_block_without_its_heading_loses_only_tracers_known_lines(self):
        exclude = self.repo / ".git" / "info" / "exclude"
        exclude.write_text(
            (self.template / ".git" / "info" / "exclude").read_text(encoding="utf-8")
            + "\ndocs/agents/\ndocs/tracer.md\nmy-own-note.txt\nAGENTS.local.md\n", encoding="utf-8")

        run_untracer(self.repo, self.home)

        lines = exclude.read_text(encoding="utf-8").splitlines()
        self.assertNotIn("docs/agents/", lines)
        self.assertNotIn("docs/tracer.md", lines)
        self.assertIn("my-own-note.txt", lines)
        self.assertIn("AGENTS.local.md", lines)
        self.assertIn(".beads/", lines)

    def test_a_header_over_only_tracers_known_lines_goes_with_them(self):
        exclude = self.repo / ".git" / "info" / "exclude"
        template_exclude = (self.template / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        exclude.write_text(template_exclude + "\n# Local tracer files\ndocs/agents/\ndocs/tracer.md\n"
                           + "\n# My notes\nmy-own-note.txt\n", encoding="utf-8")

        run_untracer(self.repo, self.home)

        after = exclude.read_text(encoding="utf-8")
        self.assertTrue(after.startswith(template_exclude))
        lines = after.splitlines()
        for gone in "# Local tracer files", "docs/agents/", "docs/tracer.md":
            self.assertNotIn(gone, lines)
        for kept in "# My notes", "my-own-note.txt":
            self.assertIn(kept, lines)

    def test_a_header_left_alone_by_an_earlier_run_goes_on_the_next_run(self):
        run_untracer(self.repo, self.home)
        exclude = self.repo / ".git" / "info" / "exclude"
        before = exclude.read_text(encoding="utf-8")
        exclude.write_text(before + "\n# Local tracer files\n", encoding="utf-8")

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("  .git/info/exclude (remove tracer's lines)", section(done.stdout, "Will edit:"))
        self.assertEqual(before.rstrip("\n"), exclude.read_text(encoding="utf-8").rstrip("\n"))

    def test_a_header_over_a_line_of_your_own_stays_with_that_line(self):
        exclude = self.repo / ".git" / "info" / "exclude"
        template_exclude = (self.template / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        exclude.write_text(template_exclude + "\n# Local tracer files\ndocs/tracer.md\nmy-own-note.txt\n",
                           encoding="utf-8")

        run_untracer(self.repo, self.home)

        self.assertEqual(template_exclude + "\n# Local tracer files\nmy-own-note.txt\n",
                         exclude.read_text(encoding="utf-8"))

    def test_a_tracer_header_over_lines_untracer_keeps_is_reworded_and_a_second_run_leaves_it(self):
        exclude = self.repo / ".git" / "info" / "exclude"
        template_exclude = (self.template / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        exclude.write_text(template_exclude + "\n# tracer machinery (stealth adoption)\n.claude/skills/tracer/\n"
                           + "docs/agents/\ndocs/tracer.md\nAGENTS.local.md\n.audit/\n", encoding="utf-8")

        first = run_untracer(self.repo, self.home)
        reworded = exclude.read_text(encoding="utf-8")
        again = run_untracer(self.repo, self.home)

        self.assertEqual(template_exclude + "\n# Local agent files\nAGENTS.local.md\n.audit/\n", reworded)
        self.assertIn("  .git/info/exclude (remove tracer's lines, and reword tracer's heading to # Local agent files)",
                      section(first.stdout, "Will edit:"))
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertIn("Nothing of tracer's was found", again.stdout)
        self.assertEqual(reworded, exclude.read_text(encoding="utf-8"))

    def test_a_second_run_finds_nothing_and_leaves_the_first_backup_alone(self):
        run_untracer(self.repo, self.home)
        (first,) = self.backups()
        saved = fixture.read_tree(first)

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Nothing of tracer's was found", done.stdout)
        self.assertNotIn("removed ", done.stdout)
        self.assertEqual([first], self.backups())
        self.assertEqual(saved, fixture.read_tree(first))

    def test_running_again_after_a_reinstall_keeps_both_backups(self):
        run_untracer(self.repo, self.home)
        (first,) = self.backups()
        fixture.install_tracer(self.repo, self.REVISION)

        run_untracer(self.repo, self.home)

        self.assertEqual(2, len(self.backups()))
        self.assertIn(first, self.backups())
        self.assertIn("docs/tracer.md", fixture.read_tree(first))


class BdWrittenRemovalTests(RealBdTemplate, InstalledRepoTests):
    def test_the_exclude_file_loses_tracers_machinery_and_keeps_bds_blocks_and_the_rules_file_lines(self):
        exclude = self.repo / ".git" / "info" / "exclude"
        template_exclude = (self.template / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertIn("# Beads stealth mode", template_exclude)

        run_untracer(self.repo, self.home)

        after = exclude.read_text(encoding="utf-8")
        self.assertTrue(after.startswith(template_exclude))
        lines = after.splitlines()
        for gone in fixture.EXCLUDE_HEADING, ".claude/skills/tracer/", ".claude/statusline.py", \
                ".claude/statusline.sh", "docs/agents/", "docs/tracer.md", "docs/tracer-adopt-notes.md":
            self.assertNotIn(gone, lines)
        for kept in "# Local agent files", "AGENTS.local.md", "CLAUDE.local.md", ".audit/":
            self.assertIn(kept, lines)

    def test_bds_workspace_hooks_and_marked_block_and_the_project_docs_are_unchanged(self):
        before = fixture.read_tree(self.repo)

        run_untracer(self.repo, self.home)

        after = fixture.read_tree(self.repo)
        untouched = [p for p in before if p.startswith((".beads/", ".git/hooks/", "docs/adr/", "apps/"))
                     or p in ("CLAUDE.md", "GLOSSARY.md", "GLOSSARY-MAP.md", ".claude/settings.json")
                     or p.startswith(".audit/")]
        self.assertGreater(len([p for p in untouched if p.startswith(".beads/")]), 0)
        self.assertGreater(len([p for p in untouched if p.startswith(".git/hooks/pre-commit")]), 0)
        self.assertIn("BEGIN BEADS INTEGRATION", before["CLAUDE.md"].decode("utf-8"))
        for path in untouched:
            self.assertEqual(before[path], after[path], path)
        listed = subprocess.run(["bd", "list", "--json"], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(0, listed.returncode, listed.stderr)
        self.assertEqual(["Carry on"], [bead["title"] for bead in json.loads(listed.stdout)])

    def test_the_plan_names_each_kept_item_the_repo_has(self):
        done = run_untracer(self.repo, self.home)

        out = done.stdout.splitlines()
        after_heading = out[out.index("Will keep:") + 1:]
        kept = []
        for line in after_heading:
            if not line.startswith("  "):
                break
            kept.append(line)
        text = "\n".join(kept)
        for expected in (".beads/", ".git/hooks/pre-commit", "CLAUDE.md (bd's marked block)",
                         "GLOSSARY-MAP.md", "GLOSSARY.md", "apps/app/GLOSSARY.md", "docs/adr/",
                         "apps/app/docs/adr/", ".audit/",
                         "~/.claude/settings.json"):
            self.assertIn("  " + expected, text)


class RevisionThirtyEightTests(InstalledRepoTests):
    REVISION = 38

    def test_it_removes_an_older_install_the_same_way(self):
        seed = (self.repo / "docs" / "tracer.md").read_text(encoding="utf-8")
        self.assertIn("Seed revision 38", seed)

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("docs/tracer.md", self.removed_paths(done.stdout)[-1])
        self.assertFalse((self.repo / ".claude" / "skills" / "tracer").exists())
        self.assertFalse((self.repo / "docs" / "agents").exists())
        saved = fixture.read_tree(self.backups()[0])
        self.assertIn("Seed revision 38", saved["docs/tracer.md"].decode("utf-8"))


OWN_LINES = "\n## Build\n\nRun make check before a commit.\n"
TEST_GATE_FULL = "- **Test gate: full.**"
TEST_GATE_TARGETED = "- **Test gate: targeted.**"
TEST_GATE_RULE = (
    "- **Test gate: full.** What \"the tests\" means before a commit. `full`\n"
    "  runs the whole suite once at the end of a build. `targeted` runs the\n"
    "  tests that cover the changed code: the test files or classes the\n"
    "  diff's seams reach, plus any test that references a changed public\n"
    "  type, using the project's filter syntax (for example\n"
    "  `dotnet test <project> --filter \"FullyQualifiedName~<Class>\"`,\n"
    "  `pytest <paths>`, `ctest -R <regex>`), with the exact commands\n"
    "  recorded in the close reason; the full suite is then CI's job on push.\n"
    "  Choose `targeted` when the full suite takes long enough to dominate an\n"
    "  implement run. Build or typecheck stays whole-project either way.\n"
    "  Edit this line to change the gate; `implement` and its build subagent\n"
    "  read it.\n")
TEST_GATE_LAST_LINE = "  read it.\n"
REFER_BY_NAME = ("**Refer by name.** In anything the human reads, name beads by title, with\n"
                 "the id in parentheses, never a bare id.\n")
REFER_BY_NAME_CHANGED = REFER_BY_NAME.replace("by title", "by their title")
DOMAIN_DOCS_SEED = "- **Domain docs**: see `docs/agents/domain.md`."
DOMAIN_DOCS_CHANGED = "- **Domain docs**: see `docs/domain.md`."
READER_TWO_LINES = "*Reader: the agent. Written for a fresh context that has read nothing\nelse.*"
READER_ONE_LINE = "*Reader: the agent. Written for a fresh context that has read nothing else.*"


def section(stdout: str, heading: str) -> list:
    lines = stdout.splitlines()
    if heading not in lines:
        return []
    found = []
    for line in lines[lines.index(heading) + 1:]:
        if not line.startswith("  "):
            break
        found.append(line)
    return found


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo)


class RulesFileTests(InstalledRepoTests):
    def append(self, name: str, text: str) -> None:
        path = self.repo / name
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")

    def prepend(self, name: str, text: str) -> None:
        path = self.repo / name
        path.write_text(text + path.read_text(encoding="utf-8"), encoding="utf-8")

    def replace(self, name: str, old: str, new: str) -> None:
        path = self.repo / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")

    def read(self, name: str) -> str:
        return (self.repo / name).read_text(encoding="utf-8")


class StealthRulesTests(RulesFileTests):
    def setUp(self):
        super().setUp()
        self.append("AGENTS.local.md", OWN_LINES)
        self.prepend("CLAUDE.local.md", "Use American spelling.\n\n")

    def test_your_own_lines_take_the_place_of_the_import_line_and_agents_local_md_is_gone(self):
        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertFalse((self.repo / "AGENTS.local.md").exists())
        self.assertEqual("Use American spelling.\n\n## Build\n\nRun make check before a commit.\n",
                         self.read("CLAUDE.local.md"))

    def test_the_report_lists_your_own_lines_before_anything_changes(self):
        done = run_untracer(self.repo, self.home)

        own = section(done.stdout, "Your own lines:")
        self.assertTrue(any(line.endswith("Run make check before a commit.") for line in own), own)
        self.assertTrue(any(line.startswith("  AGENTS.local.md:") for line in own), own)
        out = done.stdout.splitlines()
        first_change = next(i for i, line in enumerate(out) if line.startswith(("removed ", "edited ")))
        self.assertLess(out.index("Your own lines:"), first_change)

    def test_a_tracer_line_you_changed_is_kept_with_the_whole_rule_it_sits_in(self):
        self.replace("AGENTS.local.md", TEST_GATE_FULL, TEST_GATE_TARGETED)

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(
            "Use American spelling.\n\n" + TEST_GATE_RULE.replace(TEST_GATE_FULL, TEST_GATE_TARGETED)
            + "\n## Build\n\nRun make check before a commit.\n",
            self.read("CLAUDE.local.md"))
        changed = section(done.stdout, "Tracer rules you changed (kept whole):")
        self.assertEqual(1, len(changed), changed)
        self.assertIn(TEST_GATE_TARGETED, changed[0])

    def test_a_tracer_line_you_rewrote_keeps_the_whole_rule_it_sits_in_and_the_rule_is_listed_once(self):
        rewritten = "  read it, and so does the nightly job that our CI team runs.\n"
        self.replace("AGENTS.local.md", TEST_GATE_RULE, TEST_GATE_RULE.replace(TEST_GATE_LAST_LINE, rewritten))

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(
            "Use American spelling.\n\n" + TEST_GATE_RULE.replace(TEST_GATE_LAST_LINE, rewritten)
            + "\n## Build\n\nRun make check before a commit.\n",
            self.read("CLAUDE.local.md"))
        changed = section(done.stdout, "Tracer rules you changed (kept whole):")
        self.assertEqual(1, len(changed), changed)
        self.assertIn(TEST_GATE_FULL, changed[0])
        self.assertFalse(any("nightly job" in line for line in section(done.stdout, "Your own lines:")))

    def test_a_line_of_your_own_added_inside_a_tracer_rule_keeps_the_whole_rule(self):
        added = "  Our CI runs the full suite on every push.\n"
        self.replace("AGENTS.local.md", TEST_GATE_RULE, TEST_GATE_RULE + added)

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(
            "Use American spelling.\n\n" + TEST_GATE_RULE + added + "\n## Build\n\nRun make check before a commit.\n",
            self.read("CLAUDE.local.md"))
        changed = section(done.stdout, "Tracer rules you changed (kept whole):")
        self.assertEqual(1, len(changed), changed)
        self.assertIn(TEST_GATE_FULL, changed[0])

    def test_a_tracer_line_you_changed_outside_a_rule_keeps_the_whole_paragraph_it_sits_in(self):
        self.replace("AGENTS.local.md", REFER_BY_NAME, REFER_BY_NAME_CHANGED)

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(
            "Use American spelling.\n\n" + REFER_BY_NAME_CHANGED + "\n## Build\n\nRun make check before a commit.\n",
            self.read("CLAUDE.local.md"))
        changed = section(done.stdout, "Tracer rules you changed (kept whole):")
        self.assertEqual(1, len(changed), changed)
        self.assertIn("**Refer by name.**", changed[0])

    def test_a_tracer_line_you_changed_at_the_end_of_block_one_is_kept_and_reported(self):
        self.replace("AGENTS.local.md", DOMAIN_DOCS_SEED, DOMAIN_DOCS_CHANGED)

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(
            "Use American spelling.\n\n" + DOMAIN_DOCS_CHANGED + "\n\n## Build\n\nRun make check before a commit.\n",
            self.read("CLAUDE.local.md"))
        changed = section(done.stdout, "Tracer rules you changed (kept whole):")
        self.assertEqual(1, len(changed), changed)
        self.assertIn(DOMAIN_DOCS_CHANGED, changed[0])
        self.assertFalse(any(DOMAIN_DOCS_CHANGED in line for line in section(done.stdout, "Your own lines:")))

    def test_a_tracer_line_you_deleted_from_inside_a_rule_keeps_the_rest_of_the_rule(self):
        deleted = "  `dotnet test <project> --filter \"FullyQualifiedName~<Class>\"`,\n"
        shortened = TEST_GATE_RULE.replace(deleted, "")
        self.assertEqual(11, len(shortened.splitlines()))
        self.replace("AGENTS.local.md", TEST_GATE_RULE, shortened)

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(
            "Use American spelling.\n\n" + shortened + "\n## Build\n\nRun make check before a commit.\n",
            self.read("CLAUDE.local.md"))
        changed = section(done.stdout, "Tracer rules you changed (kept whole):")
        self.assertEqual(1, len(changed), changed)
        self.assertIn(TEST_GATE_FULL, changed[0])

    def test_a_tracer_rule_you_deleted_whole_keeps_none_of_its_neighbors(self):
        self.replace("AGENTS.local.md", TEST_GATE_RULE, "")

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("Use American spelling.\n\n## Build\n\nRun make check before a commit.\n",
                         self.read("CLAUDE.local.md"))
        self.assertEqual([], section(done.stdout, "Tracer rules you changed (kept whole):"))

    def test_a_tracer_paragraph_you_deleted_whole_keeps_none_of_its_neighbors(self):
        self.replace("AGENTS.local.md", REFER_BY_NAME + "\n", "")

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("Use American spelling.\n\n## Build\n\nRun make check before a commit.\n",
                         self.read("CLAUDE.local.md"))
        self.assertEqual([], section(done.stdout, "Tracer rules you changed (kept whole):"))

    def test_tracer_text_left_with_no_seed_copy_and_no_mark_is_listed_and_left_alone(self):
        (self.repo / "docs" / "tracer.md").unlink()
        agents = self.repo / "AGENTS.local.md"
        agents.write_text("## Build\n\nRun make check before a commit.\n\n" + TEST_GATE_RULE, encoding="utf-8")
        before = agents.read_bytes()
        (self.repo / "CLAUDE.local.md").write_text("Use American spelling.\n", encoding="utf-8")

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], section(done.stdout, "Refused:"))
        self.assertEqual(before, agents.read_bytes())
        self.assertEqual("Use American spelling.\n", self.read("CLAUDE.local.md"))
        self.assertEqual([f"  AGENTS.local.md:{5 + n}: {' '.join(line.split())}"
                          for n, line in enumerate(TEST_GATE_RULE.splitlines())],
                         section(done.stdout, "Tracer text with no seed copy (left):"))
        self.assertEqual([], section(done.stdout, "Lines that still name tracer (left):"))

    def test_a_kept_line_that_still_names_tracer_is_listed_and_left(self):
        self.append("AGENTS.local.md", "\nSee projects/tracer-ui for the UI.\n")

        done = run_untracer(self.repo, self.home)

        self.assertIn("See projects/tracer-ui for the UI.", self.read("CLAUDE.local.md"))
        named = section(done.stdout, "Lines that still name tracer (left):")
        self.assertEqual(1, len(named), named)
        self.assertIn("See projects/tracer-ui for the UI.", named[0])

    def test_a_reader_line_written_on_one_line_counts_as_tracers(self):
        self.replace("AGENTS.local.md", READER_TWO_LINES, READER_ONE_LINE)

        run_untracer(self.repo, self.home)

        self.assertEqual("Use American spelling.\n\n## Build\n\nRun make check before a commit.\n",
                         self.read("CLAUDE.local.md"))


class StealthRulesRevisionFortyOneTests(StealthRulesTests):
    REVISION = 41


class StealthRulesRevisionThirtyEightTests(StealthRulesTests):
    REVISION = 38


class RulesPlacementTests(RulesFileTests):
    def setUp(self):
        super().setUp()
        self.append("AGENTS.local.md", OWN_LINES)

    def test_an_excluded_claude_md_without_bds_block_goes_once_its_own_lines_move(self):
        (self.repo / "CLAUDE.md").write_text(
            "Use American spelling.\n\n" + self.read("CLAUDE.local.md"), encoding="utf-8")
        (self.repo / "CLAUDE.local.md").unlink()
        self.append(".git/info/exclude", "CLAUDE.md\n")

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertFalse((self.repo / "CLAUDE.md").exists())
        self.assertEqual("Use American spelling.\n\n## Build\n\nRun make check before a commit.\n",
                         self.read("CLAUDE.local.md"))

    def test_a_line_that_names_tracer_in_a_rules_file_the_run_leaves_alone_is_listed(self):
        (self.repo / "AGENTS.md").write_text("# Notes\n\nSee projects/tracer-ui for the UI.\n", encoding="utf-8")
        fixture.commit(self.repo, ["AGENTS.md"], "Add notes")
        before = self.read("AGENTS.md")

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(before, self.read("AGENTS.md"))
        self.assertIn("  AGENTS.md:3: See projects/tracer-ui for the UI.",
                      section(done.stdout, "Lines that still name tracer (left):"))

    def test_tracer_text_in_a_file_git_neither_tracks_nor_ignores_is_listed_and_left(self):
        self.prepend("CLAUDE.md", "@AGENTS.local.md\n\n")
        before = self.read("CLAUDE.md")

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(before, self.read("CLAUDE.md"))
        self.assertIn("  CLAUDE.md:1: @AGENTS.local.md", section(done.stdout, "Could not place (left):"))
        self.assertEqual("## Build\n\nRun make check before a commit.\n", self.read("CLAUDE.local.md"))

    def test_a_single_line_of_your_own_that_equals_a_line_of_tracers_is_kept(self):
        self.prepend("CLAUDE.local.md", "## House rules\n\nNo force pushes.\n\n")

        run_untracer(self.repo, self.home)

        self.assertEqual("## House rules\n\nNo force pushes.\n\n## Build\n\nRun make check before a commit.\n",
                         self.read("CLAUDE.local.md"))

    def test_a_missing_seed_copy_leaves_the_rules_files_and_names_the_reason(self):
        (self.repo / "docs" / "tracer.md").unlink()
        before = fixture.read_tree(self.repo)

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        after = fixture.read_tree(self.repo)
        for name in ("AGENTS.local.md", "CLAUDE.local.md"):
            self.assertEqual(before[name], after[name], name)
        refused = section(done.stdout, "Refused:")
        self.assertIn("  AGENTS.local.md (docs/tracer.md is missing)", refused)
        self.assertIn("  CLAUDE.local.md (docs/tracer.md is missing)", refused)
        self.assertFalse((self.repo / ".claude" / "skills" / "tracer").exists())

    def test_an_edited_seed_copy_leaves_the_rules_files_and_the_seed_copy_and_names_the_reason(self):
        self.append("docs/tracer.md", "\nA note of my own.\n")
        before = fixture.read_tree(self.repo)

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        after = fixture.read_tree(self.repo)
        for name in ("AGENTS.local.md", "CLAUDE.local.md", "docs/tracer.md"):
            self.assertEqual(before[name], after[name], name)
        refused = section(done.stdout, "Refused:")
        self.assertIn("  AGENTS.local.md (docs/tracer.md differs from seed revision 42)", refused)
        self.assertFalse((self.repo / "docs" / "agents").exists())

    def test_a_seed_copy_of_a_revision_it_does_not_know_leaves_the_rules_files(self):
        self.replace("docs/tracer.md", "Seed revision 42 ", "Seed revision 99 ")
        before = fixture.read_tree(self.repo)

        done = run_untracer(self.repo, self.home)

        after = fixture.read_tree(self.repo)
        self.assertEqual(before["AGENTS.local.md"], after["AGENTS.local.md"])
        self.assertIn("  AGENTS.local.md (docs/tracer.md is seed revision 99, which untracer does not know)",
                      section(done.stdout, "Refused:"))


class BdWrittenRulesPlacementTests(RealBdTemplate, RulesFileTests):
    def setUp(self):
        super().setUp()
        self.append("AGENTS.local.md", OWN_LINES)

    def test_an_excluded_claude_md_keeps_only_bds_block_and_its_own_lines_move_to_claude_local_md(self):
        bd_claude = self.read("CLAUDE.md")
        begin = bd_claude.index("<!-- BEGIN BEADS INTEGRATION")
        end = bd_claude.index("\n", bd_claude.index("<!-- END BEADS INTEGRATION")) + 1
        bd_header, bd_block, bd_footer = bd_claude[:begin], bd_claude[begin:end], bd_claude[end:]
        self.prepend("CLAUDE.md", "Use American spelling.\n\n" + self.read("CLAUDE.local.md") + "\n")
        (self.repo / "CLAUDE.local.md").unlink()
        self.append(".git/info/exclude", "CLAUDE.md\n")

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(bd_block, self.read("CLAUDE.md"))
        self.assertEqual(
            "Use American spelling.\n\n## Build\n\nRun make check before a commit.\n\n"
            + bd_header + bd_footer.lstrip("\n"),
            self.read("CLAUDE.local.md"))
        self.assertFalse((self.repo / "AGENTS.local.md").exists())


class CommittedRulesTests(RealBdTemplate, RulesFileTests):
    REVISION = 41

    def install(self) -> None:
        fixture.make_with_committed_tracer(self.template, self.repo, self.REVISION)
        self.append("AGENTS.md", OWN_LINES)
        fixture.commit(self.repo, ["AGENTS.md"], "Add a rule of my own")

    def test_a_committed_file_keeps_your_own_lines_in_place_and_the_change_is_staged_not_committed(self):
        head = git(self.repo, "rev-parse", "HEAD")
        bd_claude = (self.template / "CLAUDE.md").read_text(encoding="utf-8")

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(head, git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual("## Build\n\nRun make check before a commit.\n", self.read("AGENTS.md"))
        self.assertEqual("@AGENTS.md\n\n" + bd_claude, self.read("CLAUDE.md"))
        self.assertEqual(["AGENTS.md", "CLAUDE.md"], git(self.repo, "diff", "--cached", "--name-only").split())
        self.assertEqual([], git(self.repo, "diff", "--name-only", "--", "AGENTS.md", "CLAUDE.md").split())
        self.assertFalse((self.repo / "CLAUDE.local.md").exists())


class BareRepoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "bare"
        self.repo.mkdir()
        fixture.run(["git", "init", "-q"], self.repo)
        self.home = Path(self.tmp.name) / "home"

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_git_repo_with_none_of_tracers_files_reports_that_and_writes_no_backup(self):
        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Nothing of tracer's was found", done.stdout)
        self.assertFalse(self.home.exists())

    def test_a_rules_file_that_still_imports_agents_local_md_is_refused_for_the_missing_seed_copy(self):
        claude_local = self.repo / "CLAUDE.local.md"
        claude_local.write_text("@AGENTS.local.md\n\nUse American spelling.\n", encoding="utf-8")

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("Nothing of tracer's was found", done.stdout)
        self.assertEqual(["  CLAUDE.local.md (docs/tracer.md is missing)"], section(done.stdout, "Refused:"))
        self.assertEqual("@AGENTS.local.md\n\nUse American spelling.\n", claude_local.read_text(encoding="utf-8"))

    def test_a_leftover_exclude_line_is_removed_and_a_rules_file_without_tracers_mark_is_left_unrefused(self):
        exclude = self.repo / ".git" / "info" / "exclude"
        exclude.write_text(exclude.read_text(encoding="utf-8") + "\ndocs/agents/\n", encoding="utf-8")
        claude_local = self.repo / "CLAUDE.local.md"
        claude_local.write_text("Use American spelling.\n", encoding="utf-8")

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("docs/agents/", exclude.read_text(encoding="utf-8").splitlines())
        self.assertEqual([], section(done.stdout, "Refused:"))
        self.assertEqual("Use American spelling.\n", claude_local.read_text(encoding="utf-8"))

    def test_an_unmarked_tracer_rule_as_the_only_leftover_is_listed_in_a_plan_and_nothing_changes(self):
        agents = self.repo / "AGENTS.local.md"
        agents.write_text("## Build\n\nRun make check before a commit.\n\n" + TEST_GATE_RULE, encoding="utf-8")
        before = agents.read_bytes()

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("Nothing of tracer's was found", done.stdout)
        self.assertIn(f"Plan for {self.repo.resolve()}", done.stdout)
        self.assertEqual([f"  AGENTS.local.md:{5 + n}: {' '.join(line.split())}"
                          for n, line in enumerate(TEST_GATE_RULE.splitlines())],
                         section(done.stdout, "Tracer text with no seed copy (left):"))
        self.assertFalse(any(line.startswith(("removed ", "edited ", "Backup:")) for line in done.stdout.splitlines()))
        self.assertEqual(before, agents.read_bytes())
        self.assertFalse(self.home.exists())

    def test_an_agents_heading_over_the_reader_line_is_refused_for_the_missing_seed_copy(self):
        agents_local = self.repo / "AGENTS.local.md"
        text = "# AGENTS\n\n" + READER_TWO_LINES + "\n\n" + OWN_LINES
        agents_local.write_text(text, encoding="utf-8")

        done = run_untracer(self.repo, self.home)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("Nothing of tracer's was found", done.stdout)
        self.assertEqual(["  AGENTS.local.md (docs/tracer.md is missing)"], section(done.stdout, "Refused:"))
        self.assertEqual(text, agents_local.read_text(encoding="utf-8"))


class FixtureTests(unittest.TestCase):
    def test_the_agents_local_md_built_for_revision_42_matches_the_hand_checked_copy(self):
        expected = (fixture.FIXTURES / "agents-local-42.md").read_bytes()

        self.assertEqual(expected, fixture.block_one(42).encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
