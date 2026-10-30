#!/usr/bin/env python3
"""Starts a detached waker when T3 ends the session of a manager whose epic the factory still holds.

Claude Code runs this at every session end and sends the session and the reason it ended as JSON on stdin. T3
releases an idle host with the reason `other`; any other reason starts nothing. For that reason the hook hands the
session to `t3_wake.start_wakers`, which starts `t3_wake.py wait` for each epic that a manager of this session
recorded a T3 thread for, that the factory still holds and that has no waker running, and returns at once. A
session with no recorded thread, an epic that is no longer held and an epic with a waker running start nothing. A failure prints nothing and exits 0, because this hook must never keep a
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
    reason = event.get("reason") if isinstance(event, dict) else None
    if not isinstance(session, str) or not session:
        return
    folder = Path(named) if isinstance(named, str) and Path(named).is_dir() else Path.cwd()
    sys.path.insert(0, str(PLUGIN / "scripts"))
    import repo_settings
    import t3_wake
    if not t3_wake.releases_host(reason):
        return
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
