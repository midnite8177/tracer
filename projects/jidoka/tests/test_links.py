import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

sys.path.insert(0, str(fixture.PROJECT / "plugin" / "jidoka" / "scripts"))

import beads_stealth  # noqa: E402
import links  # noqa: E402
import private_docs  # noqa: E402
import repo_settings  # noqa: E402

PRIVILEGE_NOT_HELD = 1314


def windows_error(code: int) -> OSError:
    """The error os.symlink raises on Windows. The test sets the winerror attribute by hand so a Mac can raise it."""
    error = OSError(code, "A required privilege is not held by the client")
    error.winerror = code
    return error


class RefusingSymlink:
    def __init__(self, error: OSError):
        self.error = error

    def __call__(self, *args, **kwargs):
        raise self.error


class LinksTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve()

    def with_symlink(self, replacement):
        original = os.symlink
        os.symlink = replacement
        self.addCleanup(setattr, os, "symlink", original)

    def test_an_account_without_the_right_to_link_is_refused_with_the_steps_to_turn_on_developer_mode(self):
        self.with_symlink(RefusingSymlink(windows_error(PRIVILEGE_NOT_HELD)))

        with self.assertRaises(links.LinkError) as refused:
            links.create(self.root / "link", self.root, True)

        self.assertIn("Developer Mode", str(refused.exception))
        self.assertIn(str(self.root / "link"), str(refused.exception))

    def test_any_other_failure_to_link_passes_through(self):
        self.with_symlink(RefusingSymlink(windows_error(5)))

        with self.assertRaises(OSError) as failed:
            links.create(self.root / "link", self.root, True)

        self.assertNotIsInstance(failed.exception, links.LinkError)

    def test_a_link_points_to_the_target_it_was_made_for_and_to_no_other(self):
        target = self.root / "adr"
        other = self.root / "other"
        target.mkdir()
        other.mkdir()
        links.create(self.root / "link", target, True)

        self.assertTrue(links.points_to(self.root / "link", target))
        self.assertFalse(links.points_to(self.root / "link", other))

    def test_a_link_whose_stored_target_has_the_long_path_prefix_points_to_the_target(self):
        target = self.root / "adr"
        target.mkdir()
        os.symlink("\\\\?\\" + str(target), self.root / "link")

        self.assertTrue(links.points_to(self.root / "link", target))


class RefusedLinksReachThePersonTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve()
        self.main_tree = self.root / "shop"
        self.worktree = self.root / "worktree"
        self.home = self.root / "home"
        fixture.init_repo(self.main_tree)
        (self.main_tree / "GLOSSARY.md").write_text("# shop\n", encoding="utf-8")
        (self.main_tree / "docs" / "adr").mkdir(parents=True)
        (self.main_tree / "docs" / "adr" / "0001-start.md").write_text("# 0001\n", encoding="utf-8")
        self.worktree.mkdir()
        settings = repo_settings.settings_path(self.home, self.main_tree)
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"glossary_and_adrs": "private", "glossary": "GLOSSARY.md",
                                        "adrs": "docs/adr"}), encoding="utf-8")
        original = os.symlink
        os.symlink = RefusingSymlink(windows_error(PRIVILEGE_NOT_HELD))
        self.addCleanup(setattr, os, "symlink", original)

    def test_sharing_private_docs_without_the_right_to_link_is_refused_naming_developer_mode_and_links_nothing(self):
        with self.assertRaises(private_docs.ClashError) as refused:
            private_docs.share(self.main_tree, self.worktree, self.home)

        self.assertIn("Developer Mode", str(refused.exception))
        self.assertEqual([], list(self.worktree.iterdir()))

    def test_a_beads_restore_without_the_right_to_link_exits_1_naming_developer_mode(self):
        def restore_a_link(main_tree: Path) -> list[str]:
            links.create(main_tree / "link", main_tree, True)
            return []

        original = beads_stealth.make_stealth
        beads_stealth.make_stealth = restore_a_link
        self.addCleanup(setattr, beads_stealth, "make_stealth", original)
        original_folder = Path.cwd()
        os.chdir(self.main_tree)
        self.addCleanup(os.chdir, original_folder)
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            code = beads_stealth.main([])

        self.assertEqual(1, code)
        self.assertIn("Developer Mode", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
