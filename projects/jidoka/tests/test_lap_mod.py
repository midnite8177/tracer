import re
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
KIT_TIMEOUT_SECONDS = 300


class LapModTests(unittest.TestCase):
    def test_the_lap_mods_own_tests_pass_under_the_mod_test_kit(self):
        claude = shutil.which("claude")
        self.assertIsNotNone(claude, "`claude` is not on the PATH, and the lap mod's tests run under it")
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "jidoka"
            shutil.copytree(PLUGIN, copy, symlinks=True)

            done = subprocess.run([str(claude), "plugin", "test", str(copy)], capture_output=True, text=True,
                                  encoding="utf-8", timeout=KIT_TIMEOUT_SECONDS)

        output = done.stdout + done.stderr
        self.assertEqual(0, done.returncode, output)
        ran = re.search(r"Ran (\d+) tests?", output)
        self.assertIsNotNone(ran, output)
        self.assertGreater(int(ran.group(1)) if ran else 0, 0, output)


if __name__ == "__main__":
    unittest.main()
