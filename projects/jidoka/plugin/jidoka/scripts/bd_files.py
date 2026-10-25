"""What plain `bd init` writes outside .beads/, and how to tell bd's own text from a repo's.

bd marks its text in CLAUDE.md and AGENTS.md with comment lines such as
`<!-- BEGIN BEADS INTEGRATION ... -->` and `<!-- END BEADS INTEGRATION -->`,
one pair for each kind of block. When bd creates one of those files it also
writes stock text outside its blocks; the constants below are that text and
the hook files as bd 1.2.2 writes them. Text that differs from them in
anything but blank lines and trailing spaces counts as the repo's own, so a
newer bd's text reads as the repo's, and the file stays committed.
"""
from __future__ import annotations

import json
import re

RULES_FILES = ["CLAUDE.md", "AGENTS.md"]
SKILL_FOLDER = ".agents/skills/beads"
CLAUDE_SETTINGS = ".claude/settings.json"
CODEX_HOOKS = ".codex/hooks.json"
CODEX_CONFIG = ".codex/config.toml"
HOOK_FILES = [CLAUDE_SETTINGS, CODEX_HOOKS, CODEX_CONFIG]

BLOCK = re.compile(r"^<!-- BEGIN BEADS (?P<kind>[A-Z]+(?: [A-Z]+)*)\b[^\n]*\n.*?"
                   r"^<!-- END BEADS (?P=kind) -->[ \t]*(?:\n|\Z)(?:[ \t]*\n)*", re.MULTILINE | re.DOTALL)

CLAUDE_HEADER = """\
# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.
"""

CLAUDE_PLACEHOLDERS = """\
## Build & Test

_Add your build and test commands here_

```bash
# Example:
# npm install
# npm test
```

## Architecture Overview

_Add a brief overview of your project architecture_

## Conventions & Patterns

_Add your project-specific conventions here_
"""

AGENTS_STOCK = """\
# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd prime` for full workflow context.

> **Architecture in one line:** Issues live in a local Dolt database
> (`.beads/dolt/`); cross-machine sync uses `bd dolt push/pull` (a
> git-compatible protocol), stored under `refs/dolt/data` on your git
> remote — separate from `refs/heads/*` where your code lives.
> `.beads/issues.jsonl` is a passive export, not the wire protocol.
>
> See [SYNC_CONCEPTS.md](https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md)
> for the one-screen overview and anti-patterns (don't treat JSONL as the
> source of truth; don't `bd import` during normal operation; don't
> reach for third-party Dolt hosting before trying the default).

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work atomically
bd close <id>         # Complete work
bd dolt push          # Push beads data to remote
```

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var
"""

STOCK_RULES = {
    "CLAUDE.md": [CLAUDE_HEADER, f"{CLAUDE_HEADER}\n{CLAUDE_PLACEHOLDERS}"],
    "AGENTS.md": [AGENTS_STOCK],
}


def bd_hook(command: str, status: str, matcher: str | None) -> dict:
    entry: dict = {"hooks": [{"command": command, "statusMessage": status, "type": "command"}]}
    if matcher is not None:
        entry["matcher"] = matcher
    return entry


BD_HOOK_FILES = {
    CLAUDE_SETTINGS: {"hooks": {"SessionStart": [
        {"hooks": [{"command": "bd prime --hook-json", "type": "command"}], "matcher": ""}]}},
    CODEX_HOOKS: {"hooks": {
        "PostCompact": [bd_hook("bd codex-hook PostCompact", "Scheduling Beads context refresh", "manual|auto")],
        "PreCompact": [bd_hook("bd codex-hook PreCompact", "Checking Beads context", "manual|auto")],
        "SessionStart": [bd_hook("bd codex-hook SessionStart", "Loading Beads context", "startup|resume|clear")],
        "UserPromptSubmit": [bd_hook("bd codex-hook UserPromptSubmit", "Refreshing Beads context", None)],
    }},
}
CODEX_CONFIG_TEXT = "[features]\nhooks = true\n"


def has_blocks(text: str) -> bool:
    return BLOCK.search(text) is not None


def without_blocks(text: str) -> str:
    """The text with bd's blocks and the blank lines after each taken out, ending in one newline or empty."""
    left = BLOCK.sub("", text)
    return left.rstrip("\n") + "\n" if left.strip() else ""


def comparable(text: str) -> str:
    """The text with trailing spaces, blank lines at either end and repeated blank lines dropped."""
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(line for index, line in enumerate(lines) if line or lines[index - 1])


def is_stock_rules(name: str, text: str) -> bool:
    """True when the rules file holds nothing but bd's blocks and the stock text bd writes with them."""
    left = comparable(without_blocks(text))
    return left == "" or left in (comparable(stock) for stock in STOCK_RULES[name])


def is_bd_hook_file(path: str, text: str) -> bool:
    """True when the hook file holds bd's entries and nothing else."""
    if path == CODEX_CONFIG:
        return comparable(text) == comparable(CODEX_CONFIG_TEXT)
    try:
        return json.loads(text) == BD_HOOK_FILES[path]
    except ValueError:
        return False
