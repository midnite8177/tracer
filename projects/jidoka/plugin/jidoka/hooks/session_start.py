#!/usr/bin/env python3
"""Opens a session in a beads repo with jidoka's standing rules.

Claude Code runs this at every session start and sends the session as JSON on
stdin. In a repo that uses beads, the script prints the rules block and the
paths of the tracker doc and the domain doc that ship in the plugin, and a
line saying to run onboarding when jidoka's home holds no settings for the
repo. The commit rule says the glossary and ADRs stay uncommitted when the
repo settings keep them private, and that they are always committed
otherwise, also when the settings are missing or cannot be read. After the
rules it lists each rule conflict the repo settings record, the repo's rule
winning over the jidoka rule it quotes, and lists none when it cannot read
them. Last it names each epic the factory stopped on with work left, one line with the epic's title and id and
the command that resumes it, and names none when it cannot read the epics. Anywhere else it prints nothing. A failure also prints nothing,
because this hook must never keep a session from starting.

In every repo it also appends `export JIDOKA_SESSION_ID=<the session's id>` to the env file in $CLAUDE_ENV_FILE,
which Claude Code sources before each call the session makes, so that the scheduler can tell which session a
manager runs in.
"""
from __future__ import annotations

import json
import os
import shlex
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
COMMIT_RULE
- Bead ids and requirement ids never leave the tracker or the spec. Keep them out of code, comments, commit messages, docs, tests, logs and user-facing strings.
- Comments describe the code, never the work. No dates, history, or "fixed as part of". A comment says what the code does or why it has its shape.
- Tests assert runtime behavior. A test never inspects source text, project files or package manifests.
- Comment cleanup is requested work. Deleting and rewriting comments, doc comments and commented-out code in the files a task touched is intended. It never removes tests or assertions.
- jidoka works in four modes: Planning, Factory, Acceptance and Bench.
"""

COMMITTED_RULE = ("- Commit the work. Beads stealth mode covers the tracker only. "
                  "Code, tests, GLOSSARY.md and ADRs are always committed.")
PRIVATE_RULE = ("- Commit the work. Beads stealth mode covers the tracker only. Code and tests are "
                "committed. {glossary} and the ADRs in {adrs} stay uncommitted in this repo, hidden by its git "
                "exclude file. Never stage them.")

CONFLICTS_HEADING = "This repo's rules win over jidoka's where they conflict:"
CONFLICT_LINE = '- {written_in}: "{repo_rule}" It wins over jidoka\'s rule "{overrules}"'

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
    """Looks for .beads from the folder up to the top of its repo, so a .beads in a parent folder such as the home
    folder does not count. Outside any repo it looks at the folder alone, because a walk would reach the drive root."""
    chain = [folder, *folder.parents]
    top = next((index for index, parent in enumerate(chain) if (parent / ".git").exists()), 0)
    return any((parent / ".beads").is_dir() for parent in chain[:top + 1])


def scripts_on_path() -> None:
    """Puts the plugin's scripts folder on the import path, so the scripts are imported inside the hook's functions
    and a broken import prints nothing."""
    scripts = str(PLUGIN / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)


def repo_settings():
    scripts_on_path()
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


def settings_file(main_tree: Path) -> Path:
    script = repo_settings()
    return script.settings_path(script.jidoka_home(None), main_tree)


def commit_rule(main_tree: Path | None) -> str:
    """The committed wording unless readable repo settings keep the glossary and ADRs private."""
    if main_tree is None:
        return COMMITTED_RULE
    try:
        script = repo_settings()
        settings = script.load(settings_file(main_tree))
        glossary, adrs = settings.get("glossary"), settings.get("adrs")
        private = settings.get(script.GLOSSARY_AND_ADRS) == script.PRIVATE
        if private and isinstance(glossary, str) and isinstance(adrs, str):
            return PRIVATE_RULE.format(glossary=glossary, adrs=adrs)
    except Exception:
        pass
    return COMMITTED_RULE


def rule_conflicts(main_tree: Path | None) -> str:
    """The repo's rules that win over jidoka's, or nothing when the repo settings record none or cannot be read."""
    if main_tree is None:
        return ""
    try:
        script = repo_settings()
        conflicts = script.load(settings_file(main_tree)).get(script.RULE_CONFLICTS, [])
        if not conflicts or script.rule_conflicts_problems(conflicts):
            return ""
        lines = [CONFLICT_LINE.format(**conflict) for conflict in conflicts]
    except Exception:
        return ""
    return "\n" + "\n".join([CONFLICTS_HEADING, *lines]) + "\n"


def announcement(main_tree: Path | None) -> str:
    return (f"{RULES.replace('COMMIT_RULE', commit_rule(main_tree))}{rule_conflicts(main_tree)}\n"
            "Read these before you explore the code or file work.\n"
            f"tracker doc: {DOCS / 'issue-tracker.md'}\n"
            f"domain doc: {DOCS / 'domain.md'}\n")


def stopped_factories(main_tree: Path | None) -> str:
    """One line for each epic the factory stopped on, naming the command that resumes it, or nothing when none
    stopped or the epics cannot be read."""
    if main_tree is None:
        return ""
    try:
        script = repo_settings()
        import clock
        import resume
        stopped = resume.stopped_epics(script.jidoka_home(None), main_tree, clock.now())
    except Exception:
        return ""
    return "".join(f"\n{epic.line()}\n" for epic in stopped)


def export_session(raw: str) -> None:
    """Exports the session's id to the calls the session makes, through the env file Claude Code names.

    The scheduler records the id in the heartbeat of the epic its manager claims, so that no other session beats it.
    Without an env file or an id there is nothing to export, and a failure here keeps nothing from starting.
    """
    try:
        env_file = os.environ.get("CLAUDE_ENV_FILE")
        event = json.loads(raw)
        session = event.get("session_id") if isinstance(event, dict) else None
        if not env_file or not isinstance(session, str) or not session:
            return
        scripts_on_path()
        import heartbeat
        with open(env_file, "a", encoding="utf-8") as file:
            file.write(f"export {heartbeat.SESSION_VARIABLE}={shlex.quote(session)}\n")
    except Exception:
        return


def start(raw: str) -> str:
    try:
        folder = session_folder(raw)
        main_tree = main_tree_of(folder)
        if not is_beads_repo(folder, main_tree):
            return ""
        text = announcement(main_tree)
        if main_tree is not None and not settings_file(main_tree).is_file():
            text += ONBOARDING
        return text + stopped_factories(main_tree)
    except Exception:
        return ""


def main() -> int:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except (OSError, ValueError):
        raw = ""
    export_session(raw)
    text = start(raw)
    if text:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
