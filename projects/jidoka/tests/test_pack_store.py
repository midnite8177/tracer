import json
import os
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
PACK_STORE = PLUGIN / "scripts" / "pack_store.py"

RUN_TIMEOUT_SECONDS = 120
JOURNAL_BYTES = 1000
INDEX_BYTES = 24


class PackStoreTests(unittest.TestCase):
    """The shop repo with the fake bd first on the script's PATH and a Dolt store of known size under its .beads."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.repo = cls.root / "shop"
        fixture.init_repo(cls.repo)
        (cls.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(cls.repo, "Start")
        cls.bin = cls.root / "bin"
        cls.bd = str(fixture.add_fake_beads(cls.repo, cls.bin))
        noms = cls.repo / ".beads" / "embeddeddolt" / "shop" / ".dolt" / "noms"
        noms.mkdir(parents=True)
        (noms / "journal").write_bytes(b"j" * JOURNAL_BYTES)
        (noms / "journal.idx").write_bytes(b"i" * INDEX_BYTES)
        cls.worktree = cls.root / "shop-side"
        fixture.run(["git", "worktree", "add", "-q", "-b", "side", str(cls.worktree)], cls.repo)
        home = cls.root / "jidoka-home"
        home.mkdir()
        (home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        cls.env = {**os.environ, "PATH": fixture.path_with(cls.bin), "JIDOKA_HOME": str(home)}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def pack(self, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
        return fixture.run_launcher(LAUNCHER, [str(PACK_STORE)], None, env, cwd, RUN_TIMEOUT_SECONDS)

    def test_a_pack_from_a_linked_worktree_runs_gc_keeping_every_bead_and_prints_the_main_store_s_size(self):
        done = self.pack(self.worktree, self.env)

        self.assertEqual(0, done.returncode, done.stderr)
        size = JOURNAL_BYTES + INDEX_BYTES
        self.assertEqual({"before": size, "after": size}, json.loads(done.stdout))
        self.assertEqual(["gc", "--skip-decay", "--force"], fixture.fake_beads_calls(self.repo)[-1])

    def test_a_gc_that_fails_exits_1_with_bd_s_reason(self):
        refusing = self.root / "refusing-gc"
        refusing.mkdir(exist_ok=True)
        fixture.write_executable(refusing / "bd", "\n".join([
            f"#!{sys.executable}",
            "import sys",
            "print('the store is locked', file=sys.stderr)",
            "sys.exit(1)",
            ""]))

        done = self.pack(self.repo, {**self.env, "PATH": fixture.path_with(refusing)})

        self.assertEqual(1, done.returncode)
        self.assertIn("the store is locked", done.stderr)
        self.assertEqual("", done.stdout)


if __name__ == "__main__":
    unittest.main()
