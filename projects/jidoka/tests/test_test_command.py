import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

sys.path.insert(0, str(fixture.PROJECT / "plugin" / "jidoka" / "scripts"))

import commands  # noqa: E402

BASH_VARIABLE = "CLAUDE_CODE_GIT_BASH_PATH"
FILTER = "A|B's \"C\" $HOME"


class TestCommandShellTests(unittest.TestCase):
    """The Git Bash branch of running a test command, run here with the lookup's inputs passed in, because a Mac
    cannot take the Windows branch itself."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.git_root = self.root / "Git"
        (self.git_root / "cmd").mkdir(parents=True)
        self.git = str(self.git_root / "cmd" / "git.exe")
        self.script = self.root / "scripts" / "run-tests.sh"

    def add_bash(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return path

    def test_the_script_runs_through_the_bash_beside_git_by_a_path_with_forward_slashes(self):
        bash = self.add_bash(self.git_root / "bin" / "bash.exe")

        arguments = commands.git_bash_command(self.script, self.git, {})

        self.assertEqual([str(bash), self.script.as_posix()], arguments)

    def test_the_bash_is_two_folders_up_from_a_mingw_git(self):
        bash = self.add_bash(self.git_root / "bin" / "bash.exe")
        mingw = self.git_root / "mingw64" / "bin"
        mingw.mkdir(parents=True)

        arguments = commands.git_bash_command(self.script, str(mingw / "git.exe"), {})

        self.assertEqual([str(bash), self.script.as_posix()], arguments)

    def test_the_bash_that_claude_code_is_told_to_use_comes_first(self):
        self.add_bash(self.git_root / "bin" / "bash.exe")
        named = self.add_bash(self.root / "elsewhere" / "bash.exe")

        arguments = commands.git_bash_command(self.script, self.git, {BASH_VARIABLE: str(named)})

        self.assertEqual([str(named), self.script.as_posix()], arguments)

    def test_the_bash_beside_git_is_not_the_fallback_when_the_named_one_is_missing(self):
        self.add_bash(self.git_root / "bin" / "bash.exe")
        environ = {BASH_VARIABLE: str(self.root / "nowhere" / "bash.exe")}

        with self.assertRaises(commands.CommandError) as raised:
            commands.git_bash_command(self.script, self.git, environ)

        self.assertIn("Git Bash", str(raised.exception))

    def test_without_git_bash_the_tests_cannot_run(self):
        with self.assertRaises(commands.CommandError) as raised:
            commands.git_bash_command(self.script, self.git, {})

        self.assertIn("cannot run the tests", str(raised.exception))

    def test_without_git_on_the_path_and_without_a_named_bash_the_tests_cannot_run(self):
        with self.assertRaises(commands.CommandError):
            commands.git_bash_command(self.script, None, {})

    def test_the_script_holds_the_line_as_written(self):
        line = "dotnet test --filter " + shlex.quote(FILTER) + ' "x y"'

        script = commands.test_script(line, self.root)

        self.assertEqual(line + "\n", script.read_bytes().decode("utf-8"))

    @unittest.skipUnless(shutil.which("bash"), "needs bash")
    def test_a_filter_and_a_command_that_hold_both_kinds_of_quote_reach_a_program_run_through_that_bash_whole(self):
        bash = shutil.which("bash") or ""
        line = 'printf "%s|%s" "say \\"hi\\"" ' + shlex.quote(FILTER)
        script = commands.test_script(line, self.root)

        arguments = commands.git_bash_command(script, None, {BASH_VARIABLE: bash})
        done = subprocess.run(arguments, capture_output=True, text=True, encoding="utf-8")

        self.assertEqual('say "hi"|' + FILTER, done.stdout)


if __name__ == "__main__":
    unittest.main()
