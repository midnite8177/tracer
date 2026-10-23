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
        fixture.build_bd_repo(cls.template)

    @classmethod
    def tearDownClass(cls):
        cls.template_dir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "jidoka-home"
        self.repo = self.root / "work" / "shop"
        self.repo.parent.mkdir()
        fixture.make_with_tracer(self.template, self.repo, self.REVISION)

    def tearDown(self):
        self.tmp.cleanup()

    def backups(self) -> list:
        return sorted((self.home / "untracer").glob("*/*"))

    def removed_paths(self, stdout: str) -> list:
        return [line[len("removed "):] for line in stdout.splitlines() if line.startswith("removed ")]


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
        for kept in "AGENTS.local.md", "CLAUDE.local.md", ".audit/":
            self.assertIn(kept, lines)

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

    def test_bds_workspace_hooks_and_marked_block_and_the_project_docs_are_unchanged(self):
        before = fixture.read_tree(self.repo)

        run_untracer(self.repo, self.home)

        after = fixture.read_tree(self.repo)
        untouched = [p for p in before if p.startswith((".beads/", ".git/hooks/", "docs/adr/", "apps/"))
                     or p in ("CLAUDE.md", "GLOSSARY.md", "GLOSSARY-MAP.md", ".claude/settings.json",
                              "AGENTS.local.md", "CLAUDE.local.md")
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
                         "apps/app/docs/adr/", "AGENTS.local.md (rules file", ".audit/",
                         "~/.claude/settings.json"):
            self.assertIn("  " + expected, text)

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


class BareRepoTests(unittest.TestCase):
    def test_a_git_repo_with_none_of_tracers_files_reports_that_and_writes_no_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "bare"
            repo.mkdir()
            fixture.run(["git", "init", "-q"], repo)
            home = Path(tmp) / "home"

            done = run_untracer(repo, home)

            self.assertEqual(0, done.returncode, done.stderr)
            self.assertIn("Nothing of tracer's was found", done.stdout)
            self.assertFalse(home.exists())


if __name__ == "__main__":
    unittest.main()
