import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import install  # noqa: E402
import jidoka_fixture as fixture  # noqa: E402
import test_skill_scripts as skill_scripts  # noqa: E402

PLUGIN = skill_scripts.PLUGIN
THREAD = "thread-of-a-t3-antigravity-session"
STARTUP = "Loads every session, before you type anything"
RULE_CAP_KB = 24
FAKE_HOOK = """\
import json, sys
event = json.load(sys.stdin)
if event.get("hook_event_name") != "SessionStart" or event.get("cwd") != sys.argv[1]:
    sys.exit(1)
text = "h" * 3071 + "\\n"
print(json.dumps({"injectSteps": [{"systemMessage": {"systemMessage": text}}]}))
"""


class ContextInAT3AntigravitySessionTests(skill_scripts.SkillScriptCase):
    """context.py run from the jidoka copy in a fake T3 Antigravity profile, in a T3 thread that exports no jidoka
    session, against a temp repo with the fake bd. The profile copy is the one install.py builds from a snapshot."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.snapshot = cls.home / "plugins" / "9.9.9"
        shutil.copytree(PLUGIN, cls.snapshot / "jidoka", ignore=shutil.ignore_patterns("__pycache__"))
        cls.t3_home = cls.root / "t3-home"
        cls.profile = cls.t3_home / ".t3" / "userdata" / "providers" / "antigravity" / "profile-a"
        (cls.profile / "config" / "plugins" / "weather" / "skills" / "forecast").mkdir(parents=True)
        (cls.profile / "config" / "plugins" / "weather" / "skills" / "forecast" / "SKILL.md").write_text(
            "---\nname: forecast\n---\n", encoding="utf-8")
        (cls.profile / "config" / "plugins" / "dormant").mkdir()
        (cls.profile / "config" / "config.json").write_text(json.dumps(
            {"theme": "dark", "plugins": {"weather": {"enabled": True}, "dormant": {"enabled": False}}}),
            encoding="utf-8")
        install.ensure_antigravity_copy(cls.snapshot, cls.home, cls.profile)
        install.enable_in_antigravity_config(cls.profile)
        cls.copy = cls.profile / "config" / "plugins" / "jidoka"

    def make_repo(self, name: str) -> Path:
        """A repo with a CLAUDE.md, whose folder holds fake-bd beads."""
        repo = self.root / name
        fixture.init_repo(repo)
        fixture.add_fake_beads(repo, self.bin)
        (repo / "CLAUDE.md").write_text("c" * 4095 + "\n", encoding="utf-8")
        return repo

    def write(self, path: Path, kilobytes: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("r" * (int(kilobytes * 1024) - 1) + "\n", encoding="utf-8")

    def run_context(self, cwd: Path) -> subprocess.CompletedProcess:
        env = {key: value for key, value in os.environ.items() if key != "JIDOKA_SESSION_ID"}
        env.update({"PATH": fixture.path_with(self.bin), "JIDOKA_HOME": str(self.home),
                    "T3CODE_THREAD_ID": THREAD, **fixture.home_variables(self.t3_home)})
        script = self.copy / "skills" / "jidoka-context" / "context.py"
        scripts = (self.snapshot / "jidoka" / "scripts").as_posix() + "/"
        return fixture.run_launcher(self.snapshot / "jidoka" / "bin" / "jidoka-run",
                                    [str(script), "--min", "0", "--scripts", scripts], None, env, cwd, None)

    def section(self, report: str, heading: str) -> list:
        lines = report.splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith(heading))
        rows = []
        for line in lines[start + 1:]:
            if not line.strip():
                break
            rows.append(line)
        return rows

    def test_counts_gemini_and_agents_files_from_the_cwd_up_to_the_repo_root_and_the_agents_rules(self):
        repo = self.make_repo("gemini-shop")
        self.write(repo / "GEMINI.md", 1)
        self.write(repo / "packages" / "AGENTS.md", 2)
        self.write(repo / "packages" / "app" / "GEMINI.md", 0.5)
        self.write(repo / ".agents" / "rules" / "style.md", 3)
        self.write(self.root / "AGENTS.md", 7)
        (repo / "packages" / "other").mkdir()
        self.write(repo / "packages" / "other" / "GEMINI.md", 9)

        done = self.run_context(repo / "packages" / "app")

        self.assertEqual(0, done.returncode, done.stderr)
        rows = self.section(done.stdout, STARTUP)
        counted = {re.sub(r"^.*tok  ", "", row): float(row.split()[0]) for row in rows}
        self.assertEqual({"packages/app/GEMINI.md": 0.5, "packages/AGENTS.md": 2.0, "GEMINI.md": 1.0,
                          ".agents/rules/style.md": 3.0}.items(),
                         {label: kb for label, kb in counted.items() if label.endswith(".md")}.items(), done.stdout)

    def test_caps_a_rule_file_at_24_kb(self):
        repo = self.make_repo("capped-shop")
        self.write(repo / "AGENTS.md", 30)

        done = self.run_context(repo)

        self.assertEqual(0, done.returncode, done.stderr)
        row = next(row for row in self.section(done.stdout, STARTUP) if "AGENTS.md" in row)
        self.assertRegex(row, rf"^\s+{RULE_CAP_KB}\.0 KB\s.*AGENTS\.md \(capped at {RULE_CAP_KB} KB\)")

    def test_counts_nothing_of_the_rules_past_a_budget_of_20k_tokens_for_all_of_them(self):
        repo = self.make_repo("budget-shop")
        for name in ("a", "b", "c", "d", "e"):
            self.write(repo / ".agents" / "rules" / f"{name}.md", 30)

        done = self.run_context(repo)

        self.assertEqual(0, done.returncode, done.stderr)
        rows = {re.search(r"rules/(\w)\.md", row).group(1): row
                for row in self.section(done.stdout, STARTUP) if "rules/" in row}
        for name in "abc":
            self.assertRegex(rows[name], rf"^\s+{RULE_CAP_KB}\.0 KB.*\(capped at {RULE_CAP_KB} KB\)(  ⚠)?$")
        self.assertRegex(rows["d"], r"^\s+6\.1 KB.*\(capped at 24 KB, cut to the 20k-token rule budget\)$")
        self.assertRegex(rows["e"], r"^\s+0\.0 KB.*\(capped at 24 KB, cut to the 20k-token rule budget\)$")

    def test_reports_claude_md_as_not_loaded(self):
        repo = self.make_repo("claude-shop")
        self.write(repo / "GEMINI.md", 1)

        done = self.run_context(repo)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([], [row for row in self.section(done.stdout, STARTUP) if row.endswith("CLAUDE.md")])
        not_loaded = self.section(done.stdout, "Not loaded here")
        self.assertTrue(any(row.strip().startswith("CLAUDE.md (4.0 KB in this repo): Antigravity reads GEMINI.md")
                            for row in not_loaded), done.stdout)

    def test_says_that_a_gemini_session_start_hook_never_reaches_a_t3_session(self):
        done = self.run_context(self.make_repo("gemini-hook-shop"))

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("A SessionStart hook in ~/.gemini never reaches a T3 session",
                      "\n".join(self.section(done.stdout, "Not loaded here")))

    def test_lists_the_plugins_the_profile_config_enables_and_not_the_ones_it_does_not(self):
        done = self.run_context(self.make_repo("plugins-shop"))

        self.assertEqual(0, done.returncode, done.stderr)
        rows = [row.strip() for row in self.section(done.stdout, "Plugins enabled in the profile's config.json")]
        self.assertEqual(["jidoka  (%d skills)" % len(list((self.copy / "skills").glob("*/SKILL.md"))),
                          "weather  (1 skills)"], rows)

    def test_measures_the_session_start_output_by_running_the_profile_hook_with_bd_prime_in_it(self):
        done = self.run_context(self.make_repo("hook-shop"))

        self.assertEqual(0, done.returncode, done.stderr)
        hook = [row for row in self.section(done.stdout, STARTUP)
                if row.endswith("jidoka SessionStart hook output (bd prime included)")]
        self.assertEqual(1, len(hook), f"{done.stdout}\n{done.stderr}")
        self.assertGreater(float(hook[0].split()[0]), 0)
        self.assertEqual([], [row for row in self.section(done.stdout, STARTUP) if "bd prime (SessionStart" in row])

    def test_measures_the_text_a_profile_hook_prints_for_an_antigravity_session_start_payload(self):
        repo = self.make_repo("fake-hook-shop")
        hook = self.root / "fake-session-start.py"
        hook.write_text(FAKE_HOOK, encoding="utf-8")
        hooks_file = self.copy / "hooks.json"
        original = hooks_file.read_text(encoding="utf-8")
        held = json.loads(original)
        held["jidoka"]["SessionStart"] = [{"type": "command", "timeout": 60,
                                           "command": f'"{sys.executable}" "{hook}" "{repo}"'}]
        hooks_file.write_text(json.dumps(held), encoding="utf-8")
        try:
            done = self.run_context(repo)
        finally:
            hooks_file.write_text(original, encoding="utf-8")

        self.assertEqual(0, done.returncode, done.stderr)
        row = next(row for row in self.section(done.stdout, STARTUP) if row.endswith("(bd prime included)"))
        self.assertRegex(row, r"^\s+3\.0 KB\s+2 lines\s")

    def test_names_the_skills_by_their_jidoka_names(self):
        done = self.run_context(self.make_repo("skills-shop"))

        self.assertEqual(0, done.returncode, done.stderr)
        names = [row.split("tok  ")[1].removesuffix("  ⚠")
                 for row in self.section(done.stdout, "Each skill, loaded only when invoked")[1:]]
        self.assertIn("jidoka-context", names)
        self.assertIn("jidoka-bench", names)
        self.assertEqual([], [name for name in names if not name.startswith("jidoka-")])
        self.assertIn("Added when /jidoka-bench runs", done.stdout)
        self.assertTrue(any(re.search(r"\sskill jidoka-tdd \(\d+ files?\)$", row)
                            for row in self.section(done.stdout, "Added when /jidoka-bench runs")), done.stdout)


if __name__ == "__main__":
    unittest.main()
