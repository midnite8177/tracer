import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

import build  # noqa: E402

CHANGELOG = "# Changelog\n\n- **7**: latest.\n- **6**: earlier.\n"


class SourceTree:
    def __init__(self, root: Path):
        self.root = root

    def write(self, relative: str, text: str) -> None:
        path = self.root / "src" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def config(self, fragments: list) -> dict:
        return {"revision": 7, "date": "2026-01-02", "upstream_pin": "v2.0.1",
                "bd_version": "9.9.9", "output": "seed.md", "fragments": fragments}


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tree = SourceTree(Path(self.tmp.name))
        self.tree.write("fragments/zz-changelog.md", CHANGELOG)

    def tearDown(self):
        self.tmp.cleanup()

    def render(self, *fragments: str) -> str:
        return build.render(self.tree.root, self.tree.config(list(fragments) + ["zz-changelog.md"]))

    def test_the_committed_seed_matches_what_the_sources_build(self):
        config = json.loads((PROJECT / "seed.json").read_text(encoding="utf-8"))
        with open((PROJECT / config["output"]).resolve(), encoding="utf-8", newline="") as fh:
            committed = fh.read()
        self.assertEqual(committed, build.render(PROJECT, config))

    def test_notes_above_the_seed_marker_never_reach_the_seed(self):
        self.tree.write("fragments/a.md", "Why this is so.\n\n<!-- seed -->\n# A\n")
        self.assertEqual("# A\n" + CHANGELOG, self.render("a.md"))

    def test_a_fragment_without_the_marker_reaches_the_seed_whole(self):
        self.tree.write("fragments/a.md", "# A\n\nBody.\n")
        self.assertEqual("# A\n\nBody.\n" + CHANGELOG, self.render("a.md"))

    def test_an_include_line_becomes_the_file_byte_for_byte(self):
        self.tree.write("installed/tool.py", "print('x')\r\n\n")
        self.tree.write("fragments/a.md", "```python\n{{include installed/tool.py}}\n```\n")
        self.assertEqual("```python\nprint('x')\r\n\n```\n" + CHANGELOG, self.render("a.md"))

    def test_fragments_join_in_the_order_seed_json_lists_them(self):
        self.tree.write("fragments/a.md", "A\n")
        self.tree.write("fragments/b.md", "B\n")
        self.assertEqual("B\nA\n" + CHANGELOG, self.render("b.md", "a.md"))

    def test_placeholders_take_their_values_from_seed_json(self):
        self.tree.write("fragments/a.md",
                        "{{revision}} {{date}} {{upstream_pin}} {{bd_version}} {{plugin_version}}\n")
        self.assertEqual("7 2026-01-02 v2.0.1 9.9.9 2.0.1+tracer.7\n" + CHANGELOG, self.render("a.md"))

    def test_a_fragment_missing_from_seed_json_stops_the_build(self):
        self.tree.write("fragments/forgotten.md", "lost\n")
        with self.assertRaisesRegex(build.SeedError, "forgotten.md"):
            self.render()

    def test_an_installed_file_that_no_fragment_includes_stops_the_build(self):
        self.tree.write("installed/orphan.py", "pass\n")
        with self.assertRaisesRegex(build.SeedError, "installed/orphan.py"):
            self.render()

    def test_an_include_of_a_missing_file_stops_the_build(self):
        self.tree.write("fragments/a.md", "{{include installed/nowhere.md}}\n")
        with self.assertRaisesRegex(build.SeedError, "nowhere.md"):
            self.render("a.md")

    def test_a_changelog_that_does_not_open_with_the_revision_stops_the_build(self):
        self.tree.write("fragments/zz-changelog.md", "# Changelog\n\n- **6**: earlier.\n")
        with self.assertRaisesRegex(build.SeedError, r"\(6\).*revision 7"):
            self.render()


if __name__ == "__main__":
    unittest.main()
