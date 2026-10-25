import json
import os
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
STEALTH_SCRIPT = PLUGIN / "scripts" / "beads_stealth.py"
BD_ALONE_FILES = [".agents/skills/beads/SKILL.md", ".agents/skills/beads/agents/openai.yaml",
                  ".claude/settings.json", ".codex/config.toml", ".codex/hooks.json"]
BD_ALONE_EXCLUDES = ["/.agents/skills/beads/", "/.claude/settings.json", "/.codex/config.toml",
                     "/.codex/hooks.json"]


def committed_repo(repo: Path) -> None:
    fixture.init_repo(repo)
    (repo / "README.md").write_text("shop\n", encoding="utf-8")
    fixture.git_commit_all(repo, "Start")


def titles(repo: Path) -> list[str]:
    return sorted(bead["title"] for bead in json.loads(fixture.run(["bd", "list", "--json"], repo) or "[]"))


def status(repo: Path) -> str:
    return fixture.run(["git", "status", "--porcelain", "--untracked-files=all"], repo)


def tracked_beads(repo: Path) -> list[str]:
    return fixture.run(["git", "ls-files", "--", ".beads"], repo).splitlines()


def exclude_lines(repo: Path) -> list[str]:
    return (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()


class BeadsStealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "jidoka-home"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        self.repo = self.root / "shop"
        committed_repo(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def env(self) -> dict:
        return {"PATH": os.environ["PATH"], "JIDOKA_HOME": str(self.home), "HOME": str(self.home)}

    def switch(self, cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run([str(LAUNCHER), str(STEALTH_SCRIPT)], capture_output=True, text=True,
                              encoding="utf-8", env=self.env(), cwd=cwd)

    def test_a_repo_without_beads_gets_a_stealth_workspace_and_git_status_shows_no_beads_files(self):
        done = self.switch(self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertTrue((self.repo / ".beads").is_dir())
        fixture.run(["bd", "create", "--title=Print the receipt", "--type=task"], self.repo)
        self.assertEqual(["Print the receipt"], titles(self.repo))
        self.assertEqual("", status(self.repo))

    def test_a_tracked_workspace_is_untracked_excluded_and_staged_and_bd_still_reads_every_bead(self):
        fixture.add_committed_beads(self.repo)
        for title in ("Print the receipt", "Weigh the parcel"):
            fixture.run(["bd", "create", f"--title={title}", "--type=task"], self.repo)
        tracked = tracked_beads(self.repo)
        commits = fixture.commit_count(self.repo)

        done = self.switch(self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotEqual([], tracked)
        self.assertEqual(sorted(f"D  {path}" for path in tracked), sorted(status(self.repo).splitlines()))
        self.assertEqual([], tracked_beads(self.repo))
        self.assertIn(".beads/", exclude_lines(self.repo))
        self.assertTrue(all((self.repo / path).is_file() for path in tracked))
        self.assertEqual(commits, fixture.commit_count(self.repo))
        self.assertEqual(["Print the receipt", "Weigh the parcel"], titles(self.repo))

    def test_what_bd_init_commits_and_bd_alone_wrote_is_untracked_excluded_and_staged(self):
        fixture.add_committed_bd_init(self.repo)
        fixture.run(["bd", "create", "--title=Print the receipt", "--type=task"], self.repo)
        workspace = tracked_beads(self.repo)
        gitignore = (self.repo / ".gitignore").read_bytes()
        untracked = workspace + BD_ALONE_FILES + ["AGENTS.md", "CLAUDE.md"]

        done = self.switch(self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(sorted(f"D  {path}" for path in untracked), sorted(status(self.repo).splitlines()))
        self.assertTrue(all((self.repo / path).is_file() for path in untracked))
        for line in [".beads/", *BD_ALONE_EXCLUDES, "/AGENTS.md", "/CLAUDE.md"]:
            self.assertIn(line, exclude_lines(self.repo))
        self.assertEqual(gitignore, (self.repo / ".gitignore").read_bytes())
        self.assertEqual([".gitignore", "README.md"], fixture.run(["git", "ls-files"], self.repo).splitlines())
        self.assertEqual(["Print the receipt"], titles(self.repo))

    def test_rules_files_with_the_repos_own_text_lose_bds_blocks_and_a_mixed_hook_file_stays_committed(self):
        fixture.add_committed_bd_init(self.repo)
        claude = self.repo / "CLAUDE.md"
        claude.write_text("# Shop rules\n\nShip on Fridays.\n\n" + claude.read_text(encoding="utf-8"),
                          encoding="utf-8", newline="")
        settings_file = self.repo / ".claude" / "settings.json"
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
        settings["hooks"]["Stop"] = [{"hooks": [{"command": "make lint", "type": "command"}]}]
        settings_file.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        fixture.git_commit_all(self.repo, "Add the shop's rules")
        settings_before = settings_file.read_bytes()

        done = self.switch(self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("still committed with bd's entries: .claude/settings.json", done.stdout)
        lines = status(self.repo).splitlines()
        self.assertIn("M  CLAUDE.md", lines)
        self.assertIn("D  AGENTS.md", lines)
        self.assertFalse(any(".claude/settings.json" in line for line in lines), lines)
        self.assertEqual(settings_before, settings_file.read_bytes())
        text = claude.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Shop rules\n\nShip on Fridays.\n\n# Project Instructions"), text)
        self.assertNotIn("BEADS", text)
        self.assertNotIn("bd prime", text)
        self.assertIn("## Build & Test", text)
        self.assertEqual(text, fixture.run(["git", "show", ":CLAUDE.md"], self.repo))
        self.assertNotIn("/CLAUDE.md", exclude_lines(self.repo))
        self.assertNotIn("/.claude/settings.json", exclude_lines(self.repo))

    def test_refuses_naming_the_paths_when_the_index_holds_staged_changes_outside_the_switchs_files(self):
        fixture.add_committed_bd_init(self.repo)
        (self.repo / "README.md").write_text("shop and kiosk\n", encoding="utf-8")
        (self.repo / "NOTES.md").write_text("open at nine\n", encoding="utf-8")
        fixture.run(["git", "add", "README.md", "NOTES.md"], self.repo)
        tracked = tracked_beads(self.repo)
        exclude_before = exclude_lines(self.repo)

        done = self.switch(self.repo)

        self.assertEqual(1, done.returncode)
        self.assertIn("README.md", done.stderr)
        self.assertIn("NOTES.md", done.stderr)
        self.assertEqual(tracked, tracked_beads(self.repo))
        self.assertEqual(exclude_before, exclude_lines(self.repo))

    def test_a_second_switch_changes_nothing_and_says_the_workspace_is_already_stealth(self):
        fixture.add_committed_bd_init(self.repo)
        claude = self.repo / "CLAUDE.md"
        claude.write_text("Ship on Fridays.\n\n" + claude.read_text(encoding="utf-8"), encoding="utf-8")
        fixture.git_commit_all(self.repo, "Add the shop's rules")
        fixture.run(["bd", "create", "--title=Print the receipt", "--type=task"], self.repo)
        first = self.switch(self.repo)
        disk = {path: (self.repo / path).read_bytes() for path in [*BD_ALONE_FILES, "AGENTS.md", "CLAUDE.md"]}
        index = fixture.run(["git", "ls-files", "--stage"], self.repo)
        status_before = status(self.repo)
        exclude = (self.repo / ".git" / "info" / "exclude").read_bytes()

        done = self.switch(self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("already", done.stdout)
        self.assertEqual(index, fixture.run(["git", "ls-files", "--stage"], self.repo))
        self.assertEqual(status_before, status(self.repo))
        self.assertEqual(exclude, (self.repo / ".git" / "info" / "exclude").read_bytes())
        self.assertEqual(disk, {path: (self.repo / path).read_bytes() for path in disk})
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertIn("M  CLAUDE.md", status_before.splitlines())
        self.assertEqual(["Print the receipt"], titles(self.repo))

    def test_refuses_while_a_rules_file_holding_bds_blocks_has_changes_that_are_not_staged(self):
        fixture.add_committed_bd_init(self.repo)
        with open(self.repo / "CLAUDE.md", "a", encoding="utf-8") as handle:
            handle.write("Ship on Fridays.\n")
        tracked = tracked_beads(self.repo)

        done = self.switch(self.repo)

        self.assertEqual(1, done.returncode)
        self.assertIn("CLAUDE.md", done.stderr)
        self.assertEqual(tracked, tracked_beads(self.repo))
        self.assertEqual([" M CLAUDE.md"], status(self.repo).splitlines())

    def test_another_clone_that_pulls_the_switch_gets_back_what_it_untracked_and_keeps_a_clean_status(self):
        fixture.add_committed_bd_init(self.repo)
        claude = self.repo / "CLAUDE.md"
        claude.write_text("Ship on Fridays.\n\n" + claude.read_text(encoding="utf-8"), encoding="utf-8")
        fixture.git_commit_all(self.repo, "Add the shop's rules")
        fixture.run(["bd", "create", "--title=Print the receipt", "--type=task"], self.repo)
        restored = tracked_beads(self.repo) + BD_ALONE_FILES
        clone = self.root / "shop-clone"
        fixture.run(["git", "clone", "-q", str(self.repo), str(clone)], self.root)
        shutil.copytree(self.repo / ".beads" / "embeddeddolt", clone / ".beads" / "embeddeddolt", symlinks=True)
        self.switch(self.repo)
        fixture.run(["git", "commit", "-q", "-m", "Keep the beads out of git"], self.repo)
        fixture.run(["git", "pull", "-q", "--ff-only"], clone)
        (clone / "AGENTS.md").write_text("The clone's own notes.\n", encoding="utf-8")
        missing_after_pull = [path for path in restored if not (clone / path).exists()]

        done = self.switch(clone)
        again = self.switch(clone)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertIn("already", again.stdout)
        self.assertEqual(sorted(restored), sorted(missing_after_pull))
        for path in restored:
            self.assertEqual(fixture.run(["git", "show", f"HEAD~1:{path}"], clone),
                             (clone / path).read_text(encoding="utf-8"), path)
        self.assertTrue(os.access(clone / ".beads" / "hooks" / "pre-commit", os.X_OK))
        self.assertEqual("The clone's own notes.\n", (clone / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(fixture.run(["git", "show", "HEAD:CLAUDE.md"], clone),
                         (clone / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertEqual("", status(clone))
        for line in [".beads/", *BD_ALONE_EXCLUDES, "/AGENTS.md"]:
            self.assertIn(line, exclude_lines(clone))
        self.assertEqual(["Print the receipt"], titles(clone))

    def test_a_stealth_workspace_is_left_as_it_is(self):
        fixture.add_stealth_beads(self.repo)
        fixture.run(["bd", "create", "--title=Print the receipt", "--type=task"], self.repo)
        exclude = (self.repo / ".git" / "info" / "exclude").read_bytes()

        done = self.switch(self.repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("already", done.stdout)
        self.assertEqual(exclude, (self.repo / ".git" / "info" / "exclude").read_bytes())
        self.assertEqual("", status(self.repo))
        self.assertEqual(["Print the receipt"], titles(self.repo))

    def test_a_switch_run_from_a_linked_worktree_untracks_the_main_worktrees_workspace(self):
        fixture.add_committed_beads(self.repo)
        tracked = tracked_beads(self.repo)
        worktree = self.root / "shop-feature"
        fixture.run(["git", "worktree", "add", "-q", "-b", "feature", str(worktree)], self.repo)

        done = self.switch(worktree)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(sorted(f"D  {path}" for path in tracked), sorted(status(self.repo).splitlines()))
        self.assertIn(".beads/", exclude_lines(self.repo))


if __name__ == "__main__":
    unittest.main()
