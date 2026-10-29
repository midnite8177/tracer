#!/usr/bin/env python3
"""Starts a detached waker when T3 ends the session of a manager whose epic the factory still holds.

Claude Code runs this at every session end and sends the session as JSON on stdin. It hands the session to
`t3_wake.start_wakers`, which starts `t3_wake.py wait` for each epic that a manager of this session recorded a T3
thread for, and that the factory still holds, and returns at once. A session with no recorded thread, and an epic
that is no longer held, start nothing. A failure prints nothing and exits 0, because this hook must never keep a
session from ending.

$JIDOKA_WAKE_INTERVAL_SECONDS sets how often the waker reads the beads, 30 seconds when unset.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]


def start_wakers(raw: str) -> None:
    event = json.loads(raw)
    session = event.get("session_id") if isinstance(event, dict) else None
    named = event.get("cwd") if isinstance(event, dict) else None
    if not isinstance(session, str) or not session:
        return
    folder = Path(named) if isinstance(named, str) and Path(named).is_dir() else Path.cwd()
    sys.path.insert(0, str(PLUGIN / "scripts"))
    import repo_settings
    import t3_wake
    t3_wake.start_wakers(repo_settings.jidoka_home(None), session, folder)


def main() -> int:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        start_wakers(raw)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
