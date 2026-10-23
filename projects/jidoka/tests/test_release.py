import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

MANIFEST = Path("plugin") / "jidoka" / ".claude-plugin" / "plugin.json"


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "checkout"
        self.bin = self.root / "bin"
        fixture.build_checkout(self.repo)
        fixture.build_bin(self.bin, fixture.ALL_TOOLS, self.root / "calls.log", "")

    def tearDown(self):
        self.tmp.cleanup()

    def release(self, args: list):
        return fixture.run_script(self.repo, "release.py", args, fixture.script_env(self.bin, self.root))

    def version(self) -> str:
        return json.loads((self.repo / MANIFEST).read_text(encoding="utf-8"))["version"]

    def test_a_minor_bump_raises_the_plugin_version_and_makes_exactly_one_commit(self):
        before = fixture.commit_count(self.repo)

        done = self.release(["--bump", "minor"])

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("0.2.0", self.version())
        self.assertEqual(before + 1, fixture.commit_count(self.repo))
        self.assertEqual("Release jidoka plugin 0.2.0", fixture.run(["git", "log", "-1", "--format=%s"], self.repo).strip())
        self.assertIn("0.2.0", done.stdout)

    def test_the_release_commit_holds_only_the_manifest(self):
        self.release(["--bump", "patch"])

        changed = fixture.run(["git", "show", "--name-only", "--format=", "HEAD"], self.repo).split()
        self.assertEqual([MANIFEST.as_posix()], changed)

    def test_a_file_staged_outside_the_plugin_folder_stays_out_of_the_release_commit(self):
        (self.repo / "notes.txt").write_text("not ready\n", encoding="utf-8")
        fixture.run(["git", "add", "notes.txt"], self.repo)

        self.release(["--bump", "patch"])

        changed = fixture.run(["git", "show", "--name-only", "--format=", "HEAD"], self.repo).split()
        self.assertEqual([MANIFEST.as_posix()], changed)
        self.assertEqual("notes.txt", fixture.run(["git", "diff", "--cached", "--name-only"], self.repo).strip())

    def test_each_kind_of_bump_raises_the_matching_part_and_resets_the_ones_after_it(self):
        for kind, expected in [("patch", "0.1.1"), ("minor", "0.2.0"), ("major", "1.0.0")]:
            with self.subTest(bump=kind):
                done = self.release(["--bump", kind])

                self.assertEqual(0, done.returncode, done.stderr)
                self.assertEqual(expected, self.version())
                fixture.run(["git", "reset", "-q", "--hard", "HEAD~1"], self.repo)

    def test_an_explicit_version_is_written_as_given(self):
        done = self.release(["--version", "2.5.1"])

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("2.5.1", self.version())

    def test_other_manifest_keys_survive_the_bump(self):
        self.release(["--bump", "patch"])

        manifest = json.loads((self.repo / MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual("jidoka", manifest["name"])

    def test_an_uncommitted_change_in_the_plugin_folder_stops_the_release_and_is_named(self):
        (self.repo / "plugin" / "jidoka" / "notes.txt").write_text("scratch\n", encoding="utf-8")
        before = fixture.commit_count(self.repo)

        done = self.release(["--bump", "minor"])

        self.assertEqual(2, done.returncode)
        self.assertIn("plugin/jidoka/notes.txt", done.stderr)
        self.assertEqual("0.1.0", self.version())
        self.assertEqual(before, fixture.commit_count(self.repo))

    def test_a_version_that_is_not_higher_than_the_current_one_is_refused(self):
        before = fixture.commit_count(self.repo)

        for given in ["0.1.0", "0.0.9"]:
            with self.subTest(version=given):
                done = self.release(["--version", given])

                self.assertEqual(2, done.returncode)
                self.assertIn("higher", done.stderr)
        self.assertEqual(before, fixture.commit_count(self.repo))

    def test_a_version_that_is_not_three_numbers_is_refused(self):
        done = self.release(["--version", "1.2"])

        self.assertEqual(2, done.returncode)
        self.assertIn("1.2", done.stderr)
        self.assertEqual("0.1.0", self.version())

    def test_naming_both_a_bump_and_a_version_or_neither_is_refused(self):
        for args in [[], ["--bump", "minor", "--version", "1.0.0"]]:
            with self.subTest(args=args):
                done = self.release(args)

                self.assertEqual(2, done.returncode)
                self.assertEqual("0.1.0", self.version())

    def test_the_installer_accepts_the_checkout_straight_after_a_release(self):
        self.release(["--bump", "minor"])

        done = fixture.run_script(self.repo, "install.py",
                                  ["--jidoka-home", str(self.root / "home"), "--config-dir", str(self.root / "claude")],
                                  fixture.script_env(self.bin, self.root))

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("0.2.0", done.stdout)


if __name__ == "__main__":
    unittest.main()
