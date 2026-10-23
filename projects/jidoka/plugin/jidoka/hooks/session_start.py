#!/usr/bin/env python3
"""Opens a session in a beads repo with jidoka's standing rules.

Claude Code runs this at every session start and sends the session as JSON on
stdin. In a repo that uses beads, the script prints the rules block and the
paths of the tracker doc and the domain doc that ship in the plugin, and a
line saying to run onboarding when jidoka's home holds no settings for the
repo. Anywhere else it prints nothing. A failure also prints nothing,
because this hook must never keep a session from starting.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
DOCS = PLUGIN / "docs"
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

ONBOARDING = "jidoka has no settings for this repo on this machine. Run /jidoka:onboard to record them.\n"


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


def repo_settings():
    """The settings script, imported inside start() so that a broken import prints nothing."""
    scripts = str(PLUGIN / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import repo_settings as script
    return script


def main_tree_of(folder: Path) -> Path | None:
    """The main worktree, or None when git cannot name one.

    Without a main worktree there is no settings key, so the hook leaves out the onboarding line.
    """
    script = repo_settings()
    try:
        return script.main_worktree(folder, GIT_TIMEOUT_SECONDS)
    except script.SettingsError:
        return None


def is_beads_repo(folder: Path, main_tree: Path | None) -> bool:
    """A stealth workspace keeps .beads in the main worktree only, so a linked worktree has to look there."""
    return beads_folder_above(folder) or (main_tree is not None and (main_tree / ".beads").is_dir())


def has_settings(main_tree: Path) -> bool:
    script = repo_settings()
    return script.settings_path(script.jidoka_home(None), main_tree).is_file()


def announcement() -> str:
    return (f"{RULES}\n"
            "Read these before you explore the code or file work.\n"
            f"tracker doc: {DOCS / 'issue-tracker.md'}\n"
            f"domain doc: {DOCS / 'domain.md'}\n")


def start(raw: str) -> str:
    try:
        folder = session_folder(raw)
        main_tree = main_tree_of(folder)
        if not is_beads_repo(folder, main_tree):
            return ""
        if main_tree is not None and not has_settings(main_tree):
            return announcement() + ONBOARDING
        return announcement()
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
