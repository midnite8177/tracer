import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402


def committed_repo(repo: Path) -> None:
    fixture.init_repo(repo)
    (repo / "README.md").write_text("shop\n", encoding="utf-8")
    fixture.git_commit_all(repo, "Start")


def titles(repo: Path) -> list[str]:
    return [bead["title"] for bead in json.loads(fixture.run(["bd", "list", "--json"], repo) or "[]")]


class StealthBeadsTests(unittest.TestCase):
    def test_two_repos_given_the_stealth_beads_workspace_keep_their_own_beads_and_a_clean_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            shop, kiosk = Path(tmp) / "shop", Path(tmp) / "kiosk"
            committed_repo(shop)
            committed_repo(kiosk)

            fixture.add_stealth_beads(shop)
            fixture.add_stealth_beads(kiosk)
            fixture.run(["bd", "create", "--title=Print the receipt", "--type=task"], shop)

            self.assertEqual(["Print the receipt"], titles(shop))
            self.assertEqual([], titles(kiosk))
            self.assertEqual("", fixture.run(["git", "status", "--porcelain", "--untracked-files=all"], shop))


if __name__ == "__main__":
    unittest.main()
