"""A lap worker as a T3 thread: the one module that launches, waits on, reads, interrupts and archives it.

An Antigravity host has no tool of its own that starts a worker (ADR 0012), so the factory's scripts call T3's MCP
tools themselves, through the `acp-mcp-call` command of the T3 program that runs the manager's thread, as that thread.
T3 names the program in $T3_ACP_MCP_NODE and, unless it is a standalone executable, its entry point in
$T3_ACP_MCP_ENTRYPOINT. A call is `<node> [<entrypoint>] acp-mcp-call <tool> <arguments as JSON>` with
ELECTRON_RUN_AS_NODE=1, and the tool's result is the JSON the command prints.

No function here deletes a thread. T3 offers to delete the worktree along with a thread it deletes, and the lap's
worktree outlives every stage (ADR 0012), so a stage's thread is archived.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import routes
from texts import is_text

NODE_VARIABLE = "T3_ACP_MCP_NODE"
ENTRYPOINT_VARIABLE = "T3_ACP_MCP_ENTRYPOINT"
ELECTRON_VARIABLE = "ELECTRON_RUN_AS_NODE"
CALL_COMMAND = "acp-mcp-call"
CALL_TIMEOUT_SECONDS = 120
LAUNCH_ATTEMPTS = 2
WAIT_STEP_MILLISECONDS = 45_000
READ_LIMIT = 20
READ_CHARACTERS = 20_000
TITLE_PREFIX = "lap · "
EXISTING_WORKTREE = "existing_worktree"


class T3Error(Exception):
    """A call to T3 that failed, worded for the person who reads stderr."""


def node_command() -> list[str] | None:
    """The words that start the T3 program for a call, or None when the session has no $T3_ACP_MCP_NODE."""
    node = os.environ.get(NODE_VARIABLE, "").strip()
    if not node:
        return None
    entry = os.environ.get(ENTRYPOINT_VARIABLE, "").strip()
    return [node, entry] if entry else [node]


def result_of(printed: str, tool: str) -> dict:
    """The tool's result object from what the command printed: the object whose `structuredContent` holds it, or the
    JSON in the first text of its `content`, or the printed object itself. An empty print is an empty result."""
    if not printed.strip():
        return {}
    try:
        held = json.loads(printed)
    except ValueError as error:
        raise T3Error(f"{tool} printed no JSON: {printed.strip()[:200]}") from error
    if not isinstance(held, dict):
        raise T3Error(f"{tool} printed JSON that is not an object")
    if held.get("isError") is True:
        raise T3Error(f"{tool} answered with an error: {printed.strip()[:200]}")
    if isinstance(held.get("structuredContent"), dict):
        return held["structuredContent"]
    content = held.get("content")
    if isinstance(content, list):
        for item in content:
            text = item.get("text") if isinstance(item, dict) else None
            try:
                inner = json.loads(text) if isinstance(text, str) else None
            except ValueError:
                inner = None
            if isinstance(inner, dict):
                return inner
    return held


def call(tool: str, arguments: dict) -> dict:
    """Calls the T3 tool as the manager's thread and returns its result object."""
    node = node_command()
    if node is None:
        raise T3Error(f"{NODE_VARIABLE} is not set, so T3's tools cannot be called")
    command = [*node, CALL_COMMAND, tool, json.dumps(arguments)]
    try:
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env={**os.environ, ELECTRON_VARIABLE: "1"}, timeout=CALL_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        raise T3Error(f"{tool} could not run: {error}") from error
    if done.returncode != 0:
        raise T3Error(f"{tool} exited {done.returncode}: {(done.stderr.strip() or done.stdout.strip())[:200]}")
    return result_of(done.stdout, tool)


def title_of(task_title: str) -> str:
    """The title of a lap's thread, the task's title behind `lap · `, so a person can skip the thread in the sidebar.
    It names no bead id."""
    return f"{TITLE_PREFIX}{task_title}"


def model_selection(route: routes.Route) -> dict:
    """The thread's model selection. It holds the route's provider instance, its model and, when the route has one, its
    effort under the key the route's provider takes."""
    selection: dict = {"instanceId": str(route.provider), "model": str(route.model)}
    if route.effort is not None:
        selection["options"] = {route.effort_option: route.effort}
    return selection


def launch(title: str, message: str, worktree: Path, selection: dict, client_request_id: str) -> str:
    """Starts a top-level thread in the existing worktree, with the message as its first prompt, and returns its id.
    A failed call is made once more with the same client request id, which T3 answers with the thread the first call
    made when that one got through."""
    arguments = {"title": title, "message": message, "modelSelection": selection,
                 "workspaceStrategy": {"type": EXISTING_WORKTREE, "worktreePath": str(worktree)},
                 "clientRequestId": client_request_id}
    failure = T3Error("t3_thread_launch was not tried")
    for _ in range(LAUNCH_ATTEMPTS):
        try:
            result = call("t3_thread_launch", arguments)
        except T3Error as error:
            failure = error
            continue
        thread = result.get("threadId")
        if is_text(thread):
            return thread
        failure = T3Error("t3_thread_launch named no threadId")
    raise failure


def is_running_after_wait(thread: str) -> bool:
    """Waits for the thread's run for at most one step, and returns True when the step ended with the run still going."""
    result = call("t3_thread_wait", {"threadId": thread, "timeoutMs": WAIT_STEP_MILLISECONDS})
    return result.get("timedOut") is True


def interrupt(thread: str, reason: str) -> None:
    """Stops the thread's running turn. A stop is no deletion: the thread and its worktree stay."""
    call("t3_thread_interrupt", {"threadId": thread, "stop": True, "reason": reason})


def last_reply(thread: str) -> str:
    """The text of the thread's newest assistant message, or an empty string when it has none."""
    result = call("t3_thread_read", {"threadId": thread, "view": "messages", "limit": READ_LIMIT,
                                     "maxCharsPerItem": READ_CHARACTERS})
    messages = result.get("messages")
    for message in messages if isinstance(messages, list) else []:
        if isinstance(message, dict) and message.get("role") == "assistant" and is_text(message.get("text")):
            return message["text"]
    return ""


def archive(thread: str) -> None:
    """Archives the thread, which hides it from the sidebar and keeps it and its worktree."""
    call("t3_thread_organize", {"threadId": thread, "action": "archive"})
