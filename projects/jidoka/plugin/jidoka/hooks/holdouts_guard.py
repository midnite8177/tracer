#!/usr/bin/env python3
"""Denies the holdouts script to every worker but the app check and validation.

Claude Code runs this before each Bash call and sends the call as JSON on
stdin. A call that runs `holdouts.py` from a worker whose `agent_type` is
neither `app-check` nor `validation`, with or without the `jidoka:` prefix,
is denied with a reason, so that no builder reads the text of a holdout. The
app check may run only `read` with `--task`, which prints the holdouts that
name its task. Every other call, and every call of the host's own session,
which has no `agent_id`, prints nothing and goes on. The guard stops
accidents, not a determined agent. Input that is not a call prints nothing,
because this hook must never stop a session's work.

`--host` names the host, `claude-code` or `antigravity`, and Claude Code's
hooks.json passes none, so `claude-code` is the default. install.py gives the
Antigravity command `--host antigravity`. Antigravity sends its own payload, a
`toolCall` with the tool's `name` and its `args`, with the `cwd` the call runs
in, and reads a `{"decision", "reason"}` answer. It names no worker, so the
guard acts only when `cwd` is inside a lap worktree, a folder directly under
the main checkout's `.worktrees`, and prints nothing elsewhere, as the
planning session and the host's own calls need the script. Inside a lap
worktree a `run_command` that runs `holdouts.py` is denied, and so is one whose
`CommandLine` is missing or is not a string, because a call that cannot be read
cannot be checked. The worktree's guard record (lap_guard_record.py) names the
worker, and it lets two reads through: the validation worker's `read <epic>`,
where the epic is the one its `validation-<epic>` worktree is named for, and
the app check's `read <epic> --task <task>`, where the task is the one its
`lap-<task>` worktree is named for. Every simple command of the call that names
the script must have that shape. An empty answer, `{}` or `null` would deny, so
a call that goes on prints nothing at all. A crash exits nonzero, which fails
closed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from shell_words import simple_commands

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPT = re.compile(r"(?<![\w.-])holdouts\.py(?![\w.-])")
READS_ONE_TASKS_HOLDOUTS = re.compile(r"(?<![\w.-])holdouts\.py\s+read\s+\S+\s+--task\s+\S+")
APP_CHECK = "app-check"
ALLOWED_AGENT_TYPES = {APP_CHECK, "validation"}
PLUGIN_PREFIX = "jidoka:"
CLAUDE_CODE = "claude-code"
ANTIGRAVITY = "antigravity"
CHECK_KIND = "check"
VALIDATION_STAGE = "holdouts"
VALIDATION_FOLDER_PREFIX = "validation-"
LAP_FOLDER_PREFIX = "lap-"

REASON = ("jidoka: holdouts are hidden from builders. Only the app check and validation read them, so this "
          "worker's call of the holdouts script is denied.")
APP_CHECK_REASON = ("jidoka: the app check reads only the holdouts that name its task. Run `holdouts.py read "
                    "<epic> --task <task>`; every other call of the holdouts script is denied.")
VALIDATION_REASON = ("jidoka: validation reads only its epic's holdouts. Run `holdouts.py read <epic>`; every other "
                     "call of the holdouts script is denied.")
UNREADABLE_REASON = ("jidoka: this command could not be read, so it cannot be checked against the rule that hides "
                     "holdouts from builders, and the call is denied.")


@dataclass(frozen=True)
class Call:
    """A call that runs a command, read once from the host's payload: the host that sent it, the command, which is
    None when the payload holds none that can be read, whether a worker made it, the worker's agent type without
    the plugin prefix, and the folder it ran in."""
    host: str
    command: str | None
    is_a_worker: bool
    agent_type: str
    cwd: str


def agent_type_of(event: dict) -> str:
    agent_type = event.get("agent_type")
    return agent_type.removeprefix(PLUGIN_PREFIX) if isinstance(agent_type, str) else ""


def antigravity_call(event: dict) -> Call | None:
    tool_call = event.get("toolCall")
    if not isinstance(tool_call, dict) or tool_call.get("name") != "run_command":
        return None
    args = tool_call.get("args")
    command = args.get("CommandLine") if isinstance(args, dict) else None
    cwd = event.get("cwd")
    return Call(ANTIGRAVITY, command if isinstance(command, str) else None, False, "",
                cwd if isinstance(cwd, str) else "")


def claude_call(event: dict) -> Call | None:
    if event.get("tool_name") != "Bash":
        return None
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return None
    return Call(CLAUDE_CODE, command, bool(event.get("agent_id")), agent_type_of(event), "")


def read_call(raw: str, host: str) -> Call | None:
    """The command-running call the payload holds, or None for input that is not one."""
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(event, dict):
        return None
    return antigravity_call(event) if host == ANTIGRAVITY else claude_call(event)


def in_a_lap_worktree(cwd: str) -> bool:
    """Whether cwd is a lap worktree or inside one: a folder directly under the `.worktrees` of a main checkout, the
    place jidoka makes every worktree of a lap."""
    sys.path.insert(0, str(PLUGIN / "scripts"))
    from commands import WORKTREE_FOLDER
    if not cwd or not Path(cwd).is_dir():
        return False
    folder = Path(cwd).resolve()
    return any(parent.parent.name == WORKTREE_FOLDER and (parent.parent.parent / ".git").is_dir()
               for parent in [folder, *folder.parents])


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def antigravity_deny(reason: str) -> dict:
    return {"decision": "deny", "reason": reason}


def check_record_in(cwd: str):
    """The guard record of the check worker whose worktree holds `cwd`, or None when the worktree has no record, an
    unreadable one or one of a lap worker."""
    sys.path.insert(0, str(PLUGIN / "scripts"))
    import lap_guard_record
    try:
        record = lap_guard_record.read_record(lap_guard_record.jidoka_home(), Path(cwd))
    except lap_guard_record.RecordError:
        return None
    return record if record is not None and record.kind == CHECK_KIND else None


def holdouts_arguments(words: list[str]) -> list[str] | None:
    """The words after the holdouts script in a simple command, or None when no word of it names the script."""
    return next((words[index + 1:] for index, word in enumerate(words) if SCRIPT.search(word)), None)


@dataclass(frozen=True)
class Reading:
    """What a check worker's worktree lets it read: the one list of arguments the holdouts script may get, as a
    validation worker's `read <epic>` or an app check's `read <epic> --task <task>`, and the reason that denies any
    other."""
    epic_only: bool
    name: str
    reason: str

    def allows(self, arguments: list[str]) -> bool:
        if self.epic_only:
            return arguments == ["read", self.name]
        return len(arguments) == 4 and arguments[0] == "read" and arguments[2:] == ["--task", self.name]


def reading_of(cwd: str) -> Reading | None:
    """The reading that the check worker in `cwd`'s worktree may do, or None when no check worker works there."""
    record = check_record_in(cwd)
    if record is None:
        return None
    folder = Path(record.worktree).name
    if record.stage == VALIDATION_STAGE and folder.startswith(VALIDATION_FOLDER_PREFIX):
        return Reading(True, folder.removeprefix(VALIDATION_FOLDER_PREFIX), VALIDATION_REASON)
    if record.stage == APP_CHECK and folder.startswith(LAP_FOLDER_PREFIX):
        return Reading(False, folder.removeprefix(LAP_FOLDER_PREFIX), APP_CHECK_REASON)
    return None


def antigravity_decision(call: Call) -> dict | None:
    if not in_a_lap_worktree(call.cwd):
        return None
    if call.command is None:
        return antigravity_deny(UNREADABLE_REASON)
    if not SCRIPT.search(call.command):
        return None
    reading = reading_of(call.cwd)
    parts = simple_commands(call.command)
    if reading is None:
        return antigravity_deny(REASON)
    if parts is None:
        return antigravity_deny(UNREADABLE_REASON)
    for words in parts:
        arguments = holdouts_arguments(words)
        if arguments is not None and not reading.allows(arguments):
            return antigravity_deny(reading.reason)
    return None


def claude_decision(call: Call) -> dict | None:
    if call.command is None or not (SCRIPT.search(call.command) and call.is_a_worker):
        return None
    if call.agent_type not in ALLOWED_AGENT_TYPES:
        return deny(REASON)
    if call.agent_type == APP_CHECK and not READS_ONE_TASKS_HOLDOUTS.search(call.command):
        return deny(APP_CHECK_REASON)
    return None


def decision(call: Call | None) -> dict | None:
    """The hook output that denies the call, or None when the call goes on."""
    if call is None:
        return None
    return antigravity_decision(call) if call.host == ANTIGRAVITY else claude_decision(call)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="holdouts_guard.py")
    parser.add_argument("--host", choices=[CLAUDE_CODE, ANTIGRAVITY], default=CLAUDE_CODE,
                        help="the host that runs the hook; Claude Code's hooks.json passes none")
    denied = decision(read_call(sys.stdin.read(), parser.parse_args(argv).host))
    if denied is not None:
        print(json.dumps(denied))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
