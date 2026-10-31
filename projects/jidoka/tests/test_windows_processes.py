import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

SCRIPTS = fixture.PROJECT / "plugin" / "jidoka" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import windows_processes  # noqa: E402
from windows_processes import Entry  # noqa: E402

RUN_TIMEOUT_SECONDS = 120

IMPORT_WITHOUT_POSIX_MODULES = """
import importlib, sys
from importlib.abc import MetaPathFinder

LACKING = {"fcntl", "pwd", "grp", "resource", "termios", "tty", "pty", "syslog", "curses", "readline", "posix"}


class Refuse(MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name.split(".")[0] in LACKING:
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return None


sys.meta_path.insert(0, Refuse())
sys.path.insert(0, sys.argv[1])
for module in sys.argv[2:]:
    importlib.import_module(module)
"""


class ScriptsImportWithoutPosixModulesTests(unittest.TestCase):
    def test_every_script_imports_where_the_modules_windows_lacks_are_missing(self):
        modules = sorted(path.stem for path in SCRIPTS.glob("*.py"))

        done = subprocess.run([sys.executable, "-I", "-c", IMPORT_WITHOUT_POSIX_MODULES, str(SCRIPTS), *modules],
                              capture_output=True, text=True, encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS)

        self.assertEqual(0, done.returncode, done.stderr)


class OrphanProcessTests(unittest.TestCase):
    def test_a_process_whose_parent_is_not_running_is_an_orphan(self):
        table = {10: Entry(parent=4, created=100), 20: Entry(parent=10, created=200), 30: Entry(parent=99, created=300)}

        self.assertEqual([30], windows_processes.orphans_of({**table, 4: Entry(parent=4, created=1)}))

    def test_a_process_whose_parent_id_went_to_a_younger_process_is_an_orphan(self):
        table = {10: Entry(parent=0, created=500), 20: Entry(parent=10, created=200)}

        self.assertEqual([20], windows_processes.orphans_of({**table, 0: Entry(parent=0, created=1)}))

    def test_a_process_whose_start_cannot_be_read_is_left_alone_while_its_parent_runs(self):
        table = {10: Entry(parent=0, created=None), 20: Entry(parent=10, created=200), 0: Entry(parent=0, created=1)}

        self.assertEqual([], windows_processes.orphans_of(table))


class DescendantTests(unittest.TestCase):
    def test_the_processes_a_process_started_are_its_descendants_at_any_depth(self):
        table = {10: Entry(parent=1, created=100), 20: Entry(parent=10, created=200),
                 30: Entry(parent=20, created=300), 40: Entry(parent=1, created=400)}

        self.assertEqual([20, 30], windows_processes.descendants_of(table, 10))

    def test_a_process_whose_parent_id_went_to_a_younger_process_is_not_a_descendant(self):
        table = {10: Entry(parent=1, created=500), 20: Entry(parent=10, created=200)}

        self.assertEqual([], windows_processes.descendants_of(table, 10))

    def test_a_process_that_is_not_in_the_table_has_no_descendants(self):
        self.assertEqual([], windows_processes.descendants_of({20: Entry(parent=10, created=200)}, 10))


if __name__ == "__main__":
    unittest.main()
