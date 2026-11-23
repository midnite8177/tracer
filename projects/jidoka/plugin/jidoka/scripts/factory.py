#!/usr/bin/env python3
"""Checks that this session can run the factory, and on an Antigravity host starts a lap's stage as a T3 thread.

`check` reports every failure at once. It makes the two checks below under Claude Code, and the three of the
Antigravity paragraph on an Antigravity host.

Under Claude Code the lap mod decides every lap worker's tool call. The plugin this script sits in is the one the
session loaded at startup, because the factory skill runs the script by a path relative to its own folder. Its
hooks/hooks.json must name the lap mod, ./lap_mod.ts, in its modules, and that file must exist. A session started
before jidoka's install loaded the version it found then, so the fix is a new session.

The host's config dir is $CLAUDE_CONFIG_DIR, else ~/.claude. There,
`claude plugin list --json` must list a plugin whose id starts with
`jidoka@` as enabled. The check runs claude in the caller's environment,
so claude reads the same config dir the message names.

An Antigravity host, which routes.host_of_environment decides, has no lap mod and no claude. There the profile guard
holds the lap workers' tool calls (ADR 0012), so the check is four: $T3_ACP_MCP_NODE must name the program that
calls T3's tools, at least one T3 Antigravity profile under ~/.t3/userdata/providers/antigravity must hold a jidoka
copy, and every profile that holds one must carry the guard in the copy's hooks.json, in the group that lap_guard_record.hook_group_of shapes and install.py writes. The manager's own thread must also run in T3's full-access mode, or Antigravity asks before each read of jidoka's files in the jidoka home.

The three modes below run only on an Antigravity host. Each names the lap or the pass by its worktree, and a `wait` or
`report` names the same --worktree, --scratch and --jidoka-home as the `start` it follows. t3_stage.py describes them.
A pass's worktree is the folder of its test cleanup, its tidy, its review or its fix; the validation worktree is the
folder of the validation worker and of the validation merge worker. A tidy batch names its own
scratch folder, the action's `scratch`, and a review lane a folder of its own inside the review's scratch folder, so
that the workers that share the worktree each have a thread and a state of their own.

  factory.py start --worktree <lap or pass worktree> [--scratch <folder>] --prompt <file> --tier <tier>
      Writes the guard record, launches the lap's stage, whichever the lap is at (research, build, app-check,
      spec-check or merge), as a thread titled `lap · <task title>` on the tier's route, with the file's text as its
      prompt, behind the instructions of the app check's agent or the Spec check's skill for those stages, and prints
      one JSON object: `thread`, `deadline` (epoch seconds), `wall_seconds`, and `wait` and `report`, the calls that
      follow. A pass's test cleanup, tidy batch, review lane or fix launches as a thread titled `lap · <epic title> ·
      <stage>`. The validation worktree's worker launches as `lap · <epic title> · holdouts` behind the validation
      agent's instructions, or as `lap · <epic title> · validation-merge`, as the epic records which is owed.
  factory.py wait --worktree <lap or pass worktree> [--scratch <folder>]
      One step of the wait, at most 45 seconds. Prints `state`, which is `running`, `ended` or `cut off`, the
      `thread`, the `deadline` and `next`, the call to make then. A stage past its deadline is interrupted, and ends
      cut off.
  factory.py report --worktree <lap or pass worktree> [--scratch <folder>]
      Reads the thread's last reply, writes the ledger rows of a lap's thread tokens, archives the thread, removes the
      guard record and prints `thread`, `cut_off` and `reply`. The record is removed once the read has answered, even
      when the archive fails, and a pass's record only once every thread of the worktree was reported. The scheduler's
      report of the same worker prices nothing again; for a pass it prices the thread its `--worker` names.

Exit codes:
  0  the checks passed, with one line on stdout; or the mode printed its object.
  1  a check failed, with every reason on stderr; or a mode failed, with its reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import lap_guard_record
import lap_record
import pass_support
import routes
import rules
import settings_reader
import t3_stage
import t3_worker
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, capture

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
LAP_MOD = "./lap_mod.ts"
JIDOKA_ID_PREFIX = "jidoka@"
DEFAULT_CONFIG_FOLDER = ".claude"
PLUGIN_NAME = "jidoka"
T3_USERDATA = Path(".t3") / "userdata"
ANTIGRAVITY_PROFILES = Path("providers") / "antigravity"
PROFILE_COPY = Path("config") / "plugins" / PLUGIN_NAME
HOOKS_FILE = "hooks.json"
STAGE_ERRORS = (t3_stage.StageError, t3_worker.T3Error, CommandError, routes.RouteError, lap_record.NotALapWorktree,
                rules.RulesError, settings_reader.SettingsError, pass_support.PassError, OSError)


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


def t3_profiles() -> Path:
    """The folder that holds the T3 Antigravity profiles, under the T3 userdata of the person running the check."""
    return Path.home() / T3_USERDATA / ANTIGRAVITY_PROFILES


def carries_guard(hooks_file: Path) -> bool:
    """True when the profile copy's hooks.json holds the guard's hook group, in the shape install.py writes."""
    try:
        held = json.loads(hooks_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    events = held.get(PLUGIN_NAME) if isinstance(held, dict) else None
    groups = events.get(lap_guard_record.HOOK_EVENT) if isinstance(events, dict) else None
    return isinstance(groups, list) and any(lap_guard_record.is_hook_group(group) for group in groups)


def copies_in(profiles: Path) -> list[Path]:
    """The profile folders under `profiles` that hold a jidoka copy, in name order."""
    if not profiles.is_dir():
        return []
    return sorted(profile for profile in profiles.iterdir() if (profile / PROFILE_COPY).is_dir())


def guard_problems(profiles: Path) -> list[str]:
    """Why the T3 Antigravity profiles do not hold a lap worker's calls to the lap lists: no profile has a jidoka copy,
    or a copy lacks the guard. A profile with no jidoka copy runs no factory, so it needs no guard."""
    copies = copies_in(profiles)
    if not copies:
        return [f"no T3 Antigravity profile under {profiles} holds a jidoka copy, so nothing would hold a lap "
                "worker's calls to the lap lists. Run install.py from your jidoka checkout, then start a new session "
                "and run /jidoka:factory again"]
    return [f"the jidoka copy in {profile} holds no profile guard, so a lap worker there would run any command. "
            "Run install.py from your jidoka checkout, then start a new session and run /jidoka:factory again"
            for profile in copies if not carries_guard(profile / PROFILE_COPY / HOOKS_FILE)]


def t3_tools_problem() -> str | None:
    """Why the launcher cannot call T3's tools from this session, or None when it can."""
    if t3_worker.node_command() is not None:
        return None
    return (f"{t3_worker.NODE_VARIABLE} is not set, so jidoka cannot call T3's tools to start a lap worker. Start the "
            "factory in a T3 thread of an Antigravity provider, which sets it, and run /jidoka:factory again")


def runtime_mode_problem() -> str | None:
    """Why the manager's thread cannot run the factory in its runtime mode, or None when it runs in full access.
    Antigravity asks before it reads a file outside the workspace, every jidoka skill reads its files in the jidoka
    home, and a lap thread can run in no higher mode than the manager's."""
    thread = routes.thread_of_environment()
    if thread is None:
        return None
    try:
        mode = t3_worker.runtime_mode(thread)
    except t3_worker.T3Error as error:
        return f"T3 did not say which mode this thread runs in ({error}), so jidoka cannot tell that a lap worker " \
               "will read its files without a prompt. Run /jidoka:factory again"
    if mode == t3_worker.FULL_ACCESS:
        return None
    return (f"this thread runs in {mode or 'an unnamed mode'}, and Antigravity then asks before it reads jidoka's own "
            "files, which no person answers in a lap. Start a new session, set it to Full access before its first "
            "message, and run /jidoka:factory again")


def check_antigravity() -> int:
    profiles = t3_profiles()
    tools = t3_tools_problem()
    problems = [problem for problem in (tools, *guard_problems(profiles),
                                        None if tools else runtime_mode_problem()) if problem]
    if problems:
        print("factory: the factory does not start:\n" + "\n".join(f"  {problem}" for problem in problems),
              file=sys.stderr)
        return 1
    print("factory: the profile guard is in the jidoka copy of " + ", ".join(str(profile) for profile
                                                                                 in copies_in(profiles)))
    return 0


def check_claude_code() -> int:
    folder = config_dir()
    problems = [problem for problem in (lap_mod_problem(PLUGIN_ROOT), enabled_problem(folder)) if problem]
    if problems:
        print("factory: the factory does not start:\n" + "\n".join(f"  {problem}" for problem in problems),
              file=sys.stderr)
        return 1
    print(f"factory: the lap mod is loaded from {PLUGIN_ROOT}, and {folder} has jidoka enabled")
    return 0


def run_stage(args: argparse.Namespace) -> int:
    """Runs `start`, `wait` or `report` for the lap, and prints what it returns."""
    host = routes.host_of_environment()
    if host != routes.ANTIGRAVITY_HOST:
        print(f"factory: {args.mode} starts a worker as a T3 thread, which only an Antigravity host does; this "
              "session is not one", file=sys.stderr)
        return 1
    try:
        home = settings_reader.jidoka_home(args.jidoka_home)
        worktree = Path(args.worktree)
        scratch = Path(args.scratch) if args.scratch else t3_stage.lap_scratch(worktree)
        if args.mode == "wait":
            printed = t3_stage.wait_step(worktree, scratch, home)
        else:
            main_tree = settings_reader.main_worktree(worktree, COMMAND_TIMEOUT_SECONDS)
            if args.mode == "start":
                printed = t3_stage.start(worktree, scratch, Path(args.prompt), args.tier, home, main_tree, host,
                                         PLUGIN_ROOT)
            else:
                printed = t3_stage.report(worktree, scratch, home, main_tree)
    except STAGE_ERRORS as error:
        print(f"factory: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="factory.py", description="Check that this session can run the "
                                                                     "factory, and run a lap's stage as a T3 thread.")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("check", help="check that the lap mod is loaded and the config dir has jidoka enabled; on an "
                                   "Antigravity host, that the profile copy carries the guard")
    starting = modes.add_parser("start", help="launch the lap's stage as a T3 thread")
    starting.add_argument("--prompt", required=True, help="the file that holds the stage worker's prompt")
    starting.add_argument("--tier", required=True, help="the tier whose route the thread runs on")
    waiting = modes.add_parser("wait", help="wait one step for the stage's run")
    reporting = modes.add_parser("report", help="read the stage's last reply and archive its thread")
    for sub in (starting, waiting, reporting):
        sub.add_argument("--worktree", required=True, help="the lap's worktree, or a pass's")
        sub.add_argument("--scratch", help="the scratch folder that holds the stage's state: a tidy batch's own; "
                                           "the worktree's scratch folder when left out")
        sub.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    if args.mode != "check":
        return run_stage(args)
    return check_antigravity() if routes.host_of_environment() == routes.ANTIGRAVITY_HOST else check_claude_code()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
