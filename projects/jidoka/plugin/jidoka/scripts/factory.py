#!/usr/bin/env python3
"""Checks that this session can run the factory with the lap mod deciding every lap worker's tool call.

`check` makes two checks and reports every failure at once.

The plugin this script sits in is the one the session loaded at startup,
because the factory skill runs the script by a path relative to its own
folder. Its hooks/hooks.json must name the lap mod, ./lap_mod.ts, in its
modules, and that file must exist. A session started before jidoka's
install loaded the version it found then, so the fix is a new session.

The host's config dir is $CLAUDE_CONFIG_DIR, else ~/.claude. There,
`claude plugin list --json` must list a plugin whose id starts with
`jidoka@` as enabled. The check runs claude in the caller's environment,
so claude reads the same config dir the message names.

Exit codes:
  0  both checks passed, with one line on stdout.
  1  a check failed, with every reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from commands import CommandError, capture

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
LAP_MOD = "./lap_mod.ts"
JIDOKA_ID_PREFIX = "jidoka@"
DEFAULT_CONFIG_FOLDER = ".claude"


def why_no_lap_mod(hooks_folder: Path) -> str | None:
    """Why the hooks folder does not load the lap mod, or None when it does."""
    hooks = hooks_folder / "hooks.json"
    lap_mod = (hooks_folder / LAP_MOD).resolve()
    if not hooks.is_file():
        return f"{hooks} does not exist"
    try:
        settings = json.loads(hooks.read_text(encoding="utf-8"))
    except ValueError as error:
        return f"{hooks} is not valid JSON: {error}"
    modules = settings.get("modules") if isinstance(settings, dict) else None
    if not isinstance(modules, list) or not any(
            isinstance(module, str) and (hooks_folder / module).resolve() == lap_mod for module in modules):
        return f"{hooks} names no {LAP_MOD} in its modules"
    if not lap_mod.is_file():
        return f"{lap_mod} does not exist"
    return None


def lap_mod_problem(root: Path) -> str | None:
    """The refusal for a plugin at root that does not load the lap mod, or None when it does."""
    why = why_no_lap_mod(root / "hooks")
    if why is None:
        return None
    return (f"this session runs the jidoka plugin at {root}, whose hooks do not load the lap mod: {why}. Lap "
            "workers would wait on permission prompts. Start a new session, which loads the installed jidoka, "
            "and run /jidoka:factory again")


def config_dir() -> Path:
    named = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(named) if named else Path.home() / DEFAULT_CONFIG_FOLDER


def enabled_problem(folder: Path) -> str | None:
    """Why claude does not show jidoka enabled in the config dir, or None when it does."""
    claude = shutil.which("claude")
    if claude is None:
        return (f"claude is not on the PATH, so the check cannot tell whether {folder} has jidoka enabled. Put "
                "claude on the PATH and run /jidoka:factory again")
    try:
        listed = capture([claude, "plugin", "list", "--json"], Path.cwd(), None)
    except CommandError as error:
        return f"claude plugin list --json failed under {folder}: {error}"
    if listed.returncode != 0:
        return f"claude plugin list --json failed under {folder}: {listed.stderr.strip() or listed.stdout.strip()}"
    try:
        plugins = json.loads(listed.stdout)
    except ValueError:
        plugins = None
    if not isinstance(plugins, list):
        return f"claude plugin list --json printed no list of plugins under {folder}"
    jidoka = [plugin for plugin in plugins
              if isinstance(plugin, dict) and str(plugin.get("id") or "").startswith(JIDOKA_ID_PREFIX)]
    if any(plugin.get("enabled") is True for plugin in jidoka):
        return None
    why = "jidoka is installed there but disabled" if jidoka else "claude lists no jidoka plugin there"
    return (f"{folder} does not have jidoka enabled, because {why}. Run install.py --config-dir {folder} from "
            "your jidoka checkout, then start a new session and run /jidoka:factory again")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="factory.py", description="Check that this session can run the "
                                                                     "factory.")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("check", help="check that the lap mod is loaded and the config dir has jidoka enabled")
    parser.parse_args(argv)

    folder = config_dir()
    problems = [problem for problem in (lap_mod_problem(PLUGIN_ROOT), enabled_problem(folder)) if problem]
    if problems:
        print("factory: the factory does not start:\n" + "\n".join(f"  {problem}" for problem in problems),
              file=sys.stderr)
        return 1
    print(f"factory: the lap mod is loaded from {PLUGIN_ROOT}, and {folder} has jidoka enabled")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
