#!/usr/bin/env python3
"""Prints the session that a retrospective, or the audit of a decision log, reads.

Usage:
  retro.py                          this session: in a T3 session, the thread $T3CODE_THREAD_ID names, else the newest
                                    Claude Code log of the repo
  retro.py <session id | log path>  that Claude Code log

A T3 session is the host that routes.thread_of_environment names: $T3CODE_THREAD_ID is set and $JIDOKA_SESSION_ID is not.
Its report is t3_thread's reading of the thread, with the reading of each child thread under it, so the worker threads of
a lap or of the accept skill are part of the report. An item line ends with the time T3 last updated the item, and a tool
item whose Antigravity step carried tokens shows them before it. Lines that begin `Note:` say which source the reader
fell back from.

A Claude Code log is a .jsonl file in `<$CLAUDE_CONFIG_DIR or ~/.claude>/projects/<encoded folder>/`, where the encoded
folder is the working folder with every character other than a letter or digit turned into `-`. The report is the path
and the last records of the log, each cut short; the path is there so that the reader can go further back.

It exits 1 with the reason on stderr when there is nothing to read.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import claude_project
import routes
import t3_thread
from prices import Tokens

CONFIG_VARIABLE = "CLAUDE_CONFIG_DIR"
TAIL_RECORDS = 60
FIELD_LIMIT = 600
CLAUDE_FOLDER = ".claude"
PROJECTS_FOLDER = "projects"
LOG_SUFFIX = ".jsonl"


def short(text: str, limit: int) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[:limit] + "..."


def tokens_text(tokens: Tokens) -> str:
    return (f"input {tokens.input}, output {tokens.output}, cache read {tokens.cache_read}, "
            f"cache write {tokens.cache_write}")


def tokens_line(run: t3_thread.ThreadRun) -> str:
    return "no tokens read" if run.tokens is None else tokens_text(run.tokens)


def item_line(item: t3_thread.ThreadItem) -> str:
    parts = [f"{item.ordinal}. {item.kind}"]
    if item.tool is not None and item.tool != item.kind:
        parts.append(item.tool)
    for label, value in (("text", item.text), ("arguments", item.arguments), ("result", item.result),
                         ("error", item.error)):
        if value:
            parts.append(f"{label}: {short(value, FIELD_LIMIT)}")
    if item.tokens is not None:
        parts.append(f"tokens: {tokens_text(item.tokens)}")
    if item.updated_at:
        parts.append(f"at: {item.updated_at}")
    return " | ".join(parts)


def thread_report(thread: str, seen: set[str]) -> list[str]:
    """The lines of the thread's reading, then those of each child thread it has not yet shown. It raises NoThread
    when the thread cannot be read; a child that cannot be is a line of the report."""
    seen.add(thread)
    reading = t3_thread.read_thread(thread)
    lines = [f'Thread {reading.thread} "{reading.title}"']
    lines += [f"Note: {note}" for note in reading.notes]
    lines.append("Runs")
    lines += [f"  {run.run} {run.status} {run.model or 'no model'}: {tokens_line(run)}" for run in reading.runs]
    lines.append("Items")
    lines += [f"  {item_line(item)}" for item in reading.items]
    lines.append("Child threads")
    lines += [f'  {child.thread} "{child.title}" ({child.relationship or "no relationship"})'
              for child in reading.children]
    for child in reading.children:
        if child.thread in seen:
            continue
        try:
            lines += ["", *thread_report(child.thread, seen)]
        except t3_thread.NoThread as error:
            lines += ["", f"Child thread {child.thread} could not be read: {error}"]
    return lines


def claude_projects() -> Path:
    named = os.environ.get(CONFIG_VARIABLE, "").strip()
    return (Path(named).expanduser() if named else Path.home() / CLAUDE_FOLDER) / PROJECTS_FOLDER


def newest(logs: list[Path]) -> Path | None:
    return max(logs, key=lambda log: (log.stat().st_mtime, log.name), default=None)


def find_log(argument: str | None) -> Path:
    """The Claude Code log the argument names: a path, a session id, or with no argument the newest log of the folder
    the script runs in. It raises FileNotFoundError, worded for stderr, when there is none."""
    projects = claude_projects()
    if argument is not None and (argument.endswith(LOG_SUFFIX) or Path(argument).is_file()):
        named = Path(argument).expanduser()
        if not named.is_file():
            raise FileNotFoundError(f"no session log at {named}")
        return named
    if argument is not None:
        found = newest(list(projects.glob(f"*/{argument}{LOG_SUFFIX}")))
        if found is None:
            raise FileNotFoundError(f"no session log {argument}{LOG_SUFFIX} under {projects}")
        return found
    cwd = os.getcwd()
    folder = claude_project.folder_of(projects, cwd)
    found = newest(list(folder.glob(f"*{LOG_SUFFIX}"))) if folder is not None else None
    if found is None:
        raise FileNotFoundError(f"no session log under {folder or projects / claude_project.folder_name_of(cwd)}")
    return found


def block_text(block: object) -> str | None:
    if isinstance(block, str):
        return block
    if not isinstance(block, dict):
        return None
    kind = block.get("type")
    if kind == "text":
        return str(block.get("text", ""))
    if kind == "tool_use":
        return f"tool_use {block.get('name', '')} {json.dumps(block.get('input', {}))}"
    if kind == "tool_result":
        content = block.get("content")
        pieces = content if isinstance(content, list) else [content]
        return "tool_result " + " ".join(piece for piece in map(block_text, pieces) if piece)
    return None


def record_line(line: str) -> str | None:
    """One log record as `role: text`, or None for a line that is not JSON or has no message to show."""
    try:
        record = json.loads(line)
    except ValueError:
        return None
    message = record.get("message") if isinstance(record, dict) else None
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    blocks = content if isinstance(content, list) else [content]
    text = " ".join(piece for piece in map(block_text, blocks) if piece)
    return f"{message.get('role', record.get('type', ''))}: {short(text, FIELD_LIMIT)}" if text else None


def claude_report(log: Path) -> list[str]:
    shown = [text for text in map(record_line, log.read_text(encoding="utf-8", errors="replace").splitlines())
             if text is not None]
    return [f"Session log {log}", f"Last {min(TAIL_RECORDS, len(shown))} of {len(shown)} records", *shown[-TAIL_RECORDS:]]


def main(arguments: list[str]) -> int:
    if len(arguments) > 1:
        print("usage: retro.py [session id | log path]", file=sys.stderr)
        return 2
    argument = arguments[0] if arguments else None
    thread = routes.thread_of_environment()
    try:
        if argument is None and thread is not None:
            print("\n".join(thread_report(thread, set())))
        else:
            print("\n".join(claude_report(find_log(argument))))
    except (t3_thread.NoThread, FileNotFoundError) as error:
        print(f"retro: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    sys.exit(main(sys.argv[1:]))
