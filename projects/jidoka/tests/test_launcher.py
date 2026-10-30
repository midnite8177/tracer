import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

LAUNCHER = fixture.PROJECT / "plugin" / "jidoka" / "bin" / "jidoka-run"


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "jidoka-home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def launch(self, args: list, env: dict) -> subprocess.CompletedProcess:
        return subprocess.run(fixture.launch_command(LAUNCHER, args), capture_output=True, text=True,
                              encoding="utf-8", env=env)

    def record(self, python: str) -> None:
        (self.home / "python").write_text(python + "\n", encoding="utf-8")

    def env(self) -> dict:
        return {"PATH": os.environ["PATH"], "JIDOKA_HOME": str(self.home), "HOME": str(self.root),
                **fixture.system_variables(os.environ, fixture.WINDOWS)}

    def test_it_runs_the_script_with_the_recorded_python_and_passes_the_arguments_through(self):
        recorded = self.root / "recorded-python"
        fixture.write_executable(recorded, '#!/bin/sh\necho "recorded python ran: $@"\n')
        self.record(str(recorded))

        done = self.launch(["scheduler.py", "--epic", "e1"], self.env())

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("recorded python ran: scheduler.py --epic e1\n", done.stdout)

    def test_the_exit_status_of_the_script_is_the_exit_status_of_the_launcher(self):
        script = self.root / "exits.py"
        script.write_text("import sys\nsys.exit(7)\n", encoding="utf-8")
        self.record(sys.executable)

        done = self.launch([str(script)], self.env())

        self.assertEqual(7, done.returncode)

    def test_it_reads_the_recorded_python_from_the_jidoka_folder_in_home_when_no_jidoka_home_is_set(self):
        (self.root / ".jidoka").mkdir()
        (self.root / ".jidoka" / "python").write_text(sys.executable + "\n", encoding="utf-8")
        script = self.root / "hello.py"
        script.write_text("print('hello')\n", encoding="utf-8")
        env = {"PATH": os.environ["PATH"], "HOME": str(self.root)}

        done = self.launch([str(script)], env)

        self.assertEqual("hello\n", done.stdout)

    def test_it_says_to_run_the_installer_when_nothing_is_recorded(self):
        done = self.launch(["scheduler.py"], self.env())

        self.assertNotEqual(0, done.returncode)
        self.assertIn("install.py", done.stderr)
        self.assertEqual("", done.stdout)

    def test_it_says_to_run_the_installer_when_the_recorded_file_is_empty(self):
        (self.home / "python").write_text("", encoding="utf-8")

        done = self.launch(["scheduler.py"], self.env())

        self.assertNotEqual(0, done.returncode)
        self.assertIn("install.py", done.stderr)

    def test_it_says_to_run_the_installer_when_the_recorded_python_is_gone(self):
        self.record(str(self.root / "no-such-python"))

        done = self.launch(["scheduler.py"], self.env())

        self.assertNotEqual(0, done.returncode)
        self.assertIn("install.py", done.stderr)

    def test_it_prints_its_usage_when_it_is_given_no_script(self):
        self.record(sys.executable)

        done = self.launch([], self.env())

        self.assertNotEqual(0, done.returncode)
        self.assertIn("usage", done.stderr)


if __name__ == "__main__":
    unittest.main()
