"""The command line that starts one of the plugin's scripts through its launcher, bin/jidoka-run.

A worker's call to a script, a note that tells the host what to run and the lap list that allows the call all name the
launcher and the script by absolute path, so they take the words from here.
"""
from __future__ import annotations

import shlex
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
LAUNCHER = SCRIPTS.parent / "bin" / "jidoka-run"


def command_for(script: str) -> str:
    """The words a call to the plugin's script starts with: `sh`, the launcher and the script, by absolute path."""
    return f"sh {shlex.quote(LAUNCHER.as_posix())} {shlex.quote((SCRIPTS / script).as_posix())}"


def run_specs_command() -> str:
    """The words a build worker's call to run_specs.py starts with, as the lap list allows them."""
    return command_for("run_specs.py")
