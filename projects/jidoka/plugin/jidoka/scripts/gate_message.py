"""The commit message proposed at the acceptance gate, kept in a text file beside the gate page.

/jidoka:accept proposes the message in the chat, where it is lost when the session ends or the merge is refused. The
file keeps the last proposal, so a later /jidoka:accept starts from it and the gate page shows it where it can be
copied. `gate.py message` writes and prints it, gate_page.py shows it, and a landing or a drop removes it.
"""
from __future__ import annotations

from pathlib import Path

import page

PAGE_KIND = "gate"
NAME = "message"


def path_of(epic: str, home: Path, main_tree: Path) -> Path:
    return page.text_beside(PAGE_KIND, epic, NAME, home, main_tree)


def saved(epic: str, home: Path, main_tree: Path) -> str:
    """The message saved for the epic, or "" when none is."""
    path = path_of(epic, home, main_tree)
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def save(epic: str, message: str, home: Path, main_tree: Path) -> None:
    path = path_of(epic, home, main_tree)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(message, encoding="utf-8")


def forget(epic: str, home: Path, main_tree: Path) -> None:
    path_of(epic, home, main_tree).unlink(missing_ok=True)
