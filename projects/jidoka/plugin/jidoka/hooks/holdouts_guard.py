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
"""
from __future__ import annotations

import json
import re
import sys

SCRIPT = re.compile(r"(?<![\w.-])holdouts\.py(?![\w.-])")
READS_ONE_TASKS_HOLDOUTS = re.compile(r"(?<![\w.-])holdouts\.py\s+read\s+\S+\s+--task\s+\S+")
APP_CHECK = "app-check"
ALLOWED_AGENT_TYPES = {APP_CHECK, "validation"}
PLUGIN_PREFIX = "jidoka:"

REASON = ("jidoka: holdouts are hidden from builders. Only the app check and validation read them, so this "
          "worker's call of the holdouts script is denied.")
APP_CHECK_REASON = ("jidoka: the app check reads only the holdouts that name its task. Run `holdouts.py read "
                    "<epic> --task <task>`; every other call of the holdouts script is denied.")


def runs_the_script(call: object) -> bool:
    if not isinstance(call, dict) or call.get("tool_name") != "Bash":
        return False
    tool_input = call.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    return isinstance(command, str) and SCRIPT.search(command) is not None


def is_a_worker(call: dict) -> bool:
    return bool(call.get("agent_id"))


def agent_type_of(call: dict) -> str:
    agent_type = call.get("agent_type")
    return agent_type.removeprefix(PLUGIN_PREFIX) if isinstance(agent_type, str) else ""


def may_read_holdouts(call: dict) -> bool:
    return agent_type_of(call) in ALLOWED_AGENT_TYPES


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def decision(raw: str) -> dict | None:
    """The hook output that denies the call, or None when the call goes on."""
    try:
        call = json.loads(raw)
    except ValueError:
        return None
    if not (runs_the_script(call) and is_a_worker(call)):
        return None
    if not may_read_holdouts(call):
        return deny(REASON)
    if agent_type_of(call) == APP_CHECK and not READS_ONE_TASKS_HOLDOUTS.search(call["tool_input"]["command"]):
        return deny(APP_CHECK_REASON)
    return None


def main() -> int:
    denied = decision(sys.stdin.read())
    if denied is not None:
        print(json.dumps(denied))
    return 0


if __name__ == "__main__":
    sys.exit(main())
