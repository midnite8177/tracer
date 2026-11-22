"""The read-only token that jidoka holds for T3's local server, and the T3 command that issues it.

The token lives in <jidoka-home>/t3-token, readable by the user alone. `orchestration:read` is the narrowest scope
that serves `server.getConfig`, and it can read every thread of T3 too, so setup says so before it issues one and
issues nothing until the human confirms (ADR 0011). Nothing here prints the token. A caller that reports an
outcome names the file.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from t3_wake import t3_command

TOKEN_FILE = "t3-token"
SCOPE = "orchestration:read"
LABEL = "jidoka"
TTL = "365d"
ISSUE_TIMEOUT_SECONDS = 60
OWNER_ONLY = 0o600


class TokenError(Exception):
    """A token that could not be issued or saved, worded for the person who reads stderr. It never holds the token."""


def token_path(home: Path) -> Path:
    return home / TOKEN_FILE


def issue_command(t3: str) -> list[str]:
    return [t3, "auth", "session", "issue", "--scope", SCOPE, "--label", LABEL, "--ttl", TTL, "--token-only"]


def read_token(home: Path) -> str | None:
    """The saved token, or None when the file is missing, unreadable or empty."""
    try:
        held = token_path(home).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return held or None


def save_token(home: Path, token: str) -> Path:
    """Replaces the token file whole with a file that only its owner can read, and returns its path. The file is
    made private before it takes the path, so no reader ever finds the token in a file that others can read."""
    home.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=home, prefix=f"{TOKEN_FILE}-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(token + "\n")
        os.chmod(temporary, OWNER_ONLY)
        os.replace(temporary, token_path(home))
    except OSError:
        Path(temporary).unlink(missing_ok=True)
        raise
    return token_path(home)


def token_in(output: str) -> str | None:
    """The token in what `t3 auth session issue --token-only` printed: one line that holds no space. Anything else,
    such as the report the command prints without --token-only, is no token."""
    text = output.strip()
    return text if text and len(text.split()) == 1 else None


def issue(t3: str) -> str:
    """Runs the T3 command that issues the read-only token and returns the token it printed."""
    try:
        done = subprocess.run(issue_command(t3), capture_output=True, text=True, encoding="utf-8",
                              timeout=ISSUE_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        raise TokenError(f"t3 auth session issue could not run: {error}") from error
    if done.returncode != 0:
        raise TokenError(f"t3 auth session issue exited {done.returncode}")
    token = token_in(done.stdout)
    if token is None:
        raise TokenError("t3 auth session issue printed no token")
    return token
