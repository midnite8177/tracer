#!/usr/bin/env python3
"""Opens a session in a beads repo with jidoka's standing rules.

The host runs this at every session start and sends the session as JSON on
stdin. `--host` names the host, `claude-code` or `antigravity`, and Claude
Code's hooks.json passes none, so `claude-code` is the default. In a repo that
uses beads, the script prints the rules block and the
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

Under Claude Code, in every repo, it also appends `export JIDOKA_SESSION_ID=<the session's id>` to the env file in
$CLAUDE_ENV_FILE, which Claude Code sources before each call the session makes, so that the scheduler can tell which
session a manager runs in.

Antigravity runs the same hook from its profile copy, and install.py gives the command `--host antigravity`. The
script then prints one JSON object whose `injectSteps` hold the same text as a system message, and it adds the output
of `bd prime` to the text, because a hook in ~/.gemini never reaches a T3 session. It writes no env file. Outside a
beads repo it prints nothing, as it does for Claude Code. The text names each skill and slash command as the host
does, `jidoka:onboard` and `/jidoka:onboard` under Claude Code, `jidoka-onboard` and `/jidoka-onboard` under
Antigravity, whose profile copy has no plugin namespace.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
DOCS = PLUGIN / "docs"
GIT_TIMEOUT_SECONDS = 5
BD_PRIME_TIMEOUT_SECONDS = 20

RULES = """\
jidoka rules for this repo, which uses beads.

- A jidoka skill's own subagents are authorized. When a jidoka skill's text says to run a subagent, that is the human's standing request. Do not pause to ask.
- Name beads by title, with the id in parentheses, never a bare id, in anything the human reads.
- Before you write prose a human reads (a summary, a spec, an ADR, a commit message, a doc), load the UNSLOP_SKILL skill.
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

ONBOARDING = "jidoka has no settings for this repo on this machine. Run ONBOARD_COMMAND to record them.\n"


@dataclass(frozen=True)
class Host:
    """What differs between the hosts that run this hook: the prefix of a jidoka skill's name, the form of the
    hook's answer, whether the text carries `bd prime`, and whether the session's id is exported."""
    skill_prefix: str
    answer: Callable[[str], str]
    adds_bd_prime: bool
    exports_session: bool

    def skill(self, name: str) -> str:
        """The name the host knows a jidoka skill by."""
        return f"{self.skill_prefix}{name}"

    def slash_command(self, name: str) -> str:
        return f"/{self.skill(name)}"


def plain_text(text: str) -> str:
    return text


def injected_steps(text: str) -> str:
    """The answer Antigravity reads from a SessionStart hook: the text as a system message in the session."""
    return json.dumps({"injectSteps": [{"systemMessage": {"systemMessage": text}}]})


CLAUDE_CODE = "claude-code"
ANTIGRAVITY = "antigravity"
HOSTS = {CLAUDE_CODE: Host("jidoka:", plain_text, adds_bd_prime=False, exports_session=True),
         ANTIGRAVITY: Host("jidoka-", injected_steps, adds_bd_prime=True, exports_session=False)}


def read_event(raw: str) -> dict:
    """The session the host sent, or an empty one when the input is not a JSON object."""
    try:
        event = json.loads(raw)
    except ValueError:
        return {}
    return event if isinstance(event, dict) else {}


def session_folder(event: dict) -> Path:
    """The folder the session starts in: the cwd the event names, else the process's own."""
    named = event.get("cwd")
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


def settings_reader():
    scripts_on_path()
    import settings_reader as script
    return script


def main_tree_of(folder: Path) -> Path | None:
    """The main worktree, or None when git cannot name one.

    Without a main worktree there is no settings key, so the hook leaves out the onboarding line.
    """
    script = settings_reader()
    try:
        return script.main_worktree(folder, GIT_TIMEOUT_SECONDS)
    except script.SettingsError:
        return None


def is_beads_repo(folder: Path, main_tree: Path | None) -> bool:
    """A stealth workspace keeps .beads in the main worktree only, so a linked worktree has to look there."""
    return beads_folder_above(folder) or (main_tree is not None and (main_tree / ".beads").is_dir())


def settings_file(main_tree: Path) -> Path:
    script = settings_reader()
    return script.settings_path(script.jidoka_home(None), main_tree)


def commit_rule(main_tree: Path | None) -> str:
    """The committed wording unless readable repo settings keep the glossary and ADRs private."""
    if main_tree is None:
        return COMMITTED_RULE
    try:
        script = settings_reader()
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
        script = settings_reader()
        conflicts = script.load(settings_file(main_tree)).get(script.RULE_CONFLICTS, [])
        if not conflicts or script.rule_conflicts_problems(conflicts):
            return ""
        lines = [CONFLICT_LINE.format(**conflict) for conflict in conflicts]
    except Exception:
        return ""
    return "\n" + "\n".join([CONFLICTS_HEADING, *lines]) + "\n"


def announcement(main_tree: Path | None, host: Host) -> str:
    rules = RULES.replace("COMMIT_RULE", commit_rule(main_tree)).replace("UNSLOP_SKILL", host.skill("unslop"))
    return (f"{rules}{rule_conflicts(main_tree)}\n"
            "Read these before you explore the code or file work.\n"
            f"tracker doc: {DOCS / 'issue-tracker.md'}\n"
            f"domain doc: {DOCS / 'domain.md'}\n")


def stopped_factories(main_tree: Path | None, host: Host) -> str:
    """One line for each epic the factory stopped on, naming the command that resumes it as the host spells it, or
    nothing when none stopped or the epics cannot be read."""
    if main_tree is None:
        return ""
    try:
        script = settings_reader()
        import clock
        import resume
        stopped = resume.stopped_epics(script.jidoka_home(None), main_tree, clock.now())
        resume_command = host.slash_command("factory")
        return "".join(f"\n{epic.line().replace(resume.FACTORY_COMMAND, resume_command)}\n" for epic in stopped)
    except Exception:
        return ""


def export_session(event: dict) -> None:
    """Exports the session's id to the calls the session makes, through the env file Claude Code names.

    The scheduler records the id in the heartbeat of the epic its manager claims, so that no other session beats it.
    Without an env file or an id there is nothing to export, and a failure here keeps nothing from starting.
    """
    try:
        env_file = os.environ.get("CLAUDE_ENV_FILE")
        session = event.get("session_id")
        if not env_file or not isinstance(session, str) or not session:
            return
        scripts_on_path()
        import heartbeat
        with open(env_file, "a", encoding="utf-8") as file:
            file.write(f"export {heartbeat.SESSION_VARIABLE}={shlex.quote(session)}\n")
    except Exception:
        return


def bd_prime(folder: Path) -> str:
    """What `bd prime` prints in the folder, or nothing when bd is missing, fails or runs past the timeout."""
    try:
        done = subprocess.run(["bd", "prime"], cwd=folder, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=BD_PRIME_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def start(event: dict, host: Host) -> str:
    try:
        folder = session_folder(event)
        main_tree = main_tree_of(folder)
        if not is_beads_repo(folder, main_tree):
            return ""
        text = announcement(main_tree, host)
        if main_tree is not None and not settings_file(main_tree).is_file():
            text += ONBOARDING.replace("ONBOARD_COMMAND", host.slash_command("onboard"))
        text += stopped_factories(main_tree, host)
        if host.adds_bd_prime:
            prime = bd_prime(folder)
            if prime.strip():
                text += f"\n{prime}"
        return text
    except Exception:
        return ""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="session_start.py")
    parser.add_argument("--host", choices=sorted(HOSTS), default=CLAUDE_CODE,
                        help="the host that runs the hook; Claude Code's hooks.json passes none")
    host = HOSTS[parser.parse_args(argv).host]
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except (OSError, ValueError):
        raw = ""
    event = read_event(raw)
    if host.exports_session:
        export_session(event)
    text = start(event, host)
    if text:
        sys.stdout.buffer.write(host.answer(text).encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
