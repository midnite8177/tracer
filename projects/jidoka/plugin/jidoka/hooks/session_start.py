#!/usr/bin/env python3
"""Opens a session in a beads repo with jidoka's standing rules.

Claude Code runs this at every session start and sends the session as JSON on
stdin. In a repo that uses beads, the script prints the rules block and the
paths of the tracker doc and the domain doc that ship in the plugin. Anywhere
else it prints nothing. A failure also prints nothing, because this hook must
never keep a session from starting.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
GIT_TIMEOUT_SECONDS = 5

RULES = """\
jidoka rules for this repo, which uses beads.

- A jidoka skill's own subagents are authorized. When a jidoka skill's text says to run a subagent, that is the human's standing request. Do not pause to ask.
- Name beads by title, with the id in parentheses, never a bare id, in anything the human reads.
- Before you write prose a human reads (a summary, a spec, an ADR, a commit message, a doc), call the Skill tool with "unslop".
- Commit the work. Beads stealth mode covers the tracker only. Code, tests, GLOSSARY.md and ADRs are always committed.
- Bead ids and requirement ids never leave the tracker or the spec. Keep them out of code, comments, commit messages, docs, tests, logs and user-facing strings.
- Comments describe the code, never the work. No dates, history, or "fixed as part of". A comment says what the code does or why it has its shape.
- Tests assert runtime behavior. A test never inspects source text, project files or package manifests.
- Comment cleanup is requested work. Deleting and rewriting comments, doc comments and commented-out code in the files a task touched is intended. It never removes tests or assertions.
- jidoka works in four modes: Planning, Factory, Acceptance and Bench.
"""


def session_folder(raw: str) -> Path:
    """The folder the session starts in: the cwd the input names, else the process's own."""
    try:
        event = json.loads(raw)
    except ValueError:
        return Path.cwd()
    named = event.get("cwd") if isinstance(event, dict) else None
    if isinstance(named, str) and Path(named).is_dir():
        return Path(named)
    return Path.cwd()


def beads_folder_above(folder: Path) -> bool:
    """Looks for .beads from the folder up to the top of its repo, so a .beads in a parent folder such as the home folder does not count."""
    for parent in [folder, *folder.parents]:
        if (parent / ".beads").is_dir():
            return True
        if (parent / ".git").exists():
            return False
    return False


def main_checkout_has_beads(folder: Path) -> bool:
    """A stealth workspace keeps .beads in the main checkout only, so a linked worktree has to ask git where that is.

    The common dir is the main checkout's .git, and git may print it relative to the folder.
    """
    done = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=folder, capture_output=True,
                          text=True, encoding="utf-8", timeout=GIT_TIMEOUT_SECONDS)
    common = done.stdout.strip()
    if done.returncode != 0 or not common:
        return False
    main_checkout = (folder / common).resolve().parent
    return (main_checkout / ".beads").is_dir()


def is_beads_repo(folder: Path) -> bool:
    return beads_folder_above(folder) or main_checkout_has_beads(folder)


def announcement() -> str:
    return (f"{RULES}\n"
            "Read these before you explore the code or file work.\n"
            f"tracker doc: {DOCS / 'issue-tracker.md'}\n"
            f"domain doc: {DOCS / 'domain.md'}\n")


def start(raw: str) -> str:
    try:
        return announcement() if is_beads_repo(session_folder(raw)) else ""
    except Exception:
        return ""


def main() -> int:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except (OSError, ValueError):
        raw = ""
    text = start(raw)
    if text:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
