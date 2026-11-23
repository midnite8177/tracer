"""The guard record, the file that tells the profile guard a worktree is a lap and what that lap's worker may run.

An Antigravity host has no lap mod, so a hook in T3's Antigravity profile guards the lap workers there. The hook
loads in every T3 Antigravity session and must tell a lap from any other session without running a script on a call,
so each lap worktree has a record in the jidoka home, written before its worker starts and read by the hook alone.

The record is <jidoka-home>/lap-guards/<worktree name>-<digest>.json, where the digest comes from the worktree's
resolved path, so the hook finds it from a folder inside the worktree by asking for each folder above that folder.
The file is a JSON object with `worktree` (the resolved path), `kind` (`lap` or `check`, the lap mod's kinds of
worker), `stage` (the lap's stage, as lap_record.py names it) and `commands` (what `lap_lists.py <kind>` prints for
the worker, whole, and for a check worker also the launcher calls of the holdouts and app scripts, which the lap mod
lets a check worker run apart from the list) and `barred` (a list of the acceptance folders the worker may not write
in, each as `lap_protected.py` prints it, or null when they could not be read). The home is $JIDOKA_HOME, else ~/.jidoka.

The factory's launcher writes the record before it starts the worker and removes it when the stage ends. The module
imports only the standard library, home_files.py and settings_reader.py, so a hook can load it quickly.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import home_files
import settings_reader

FOLDER = "lap-guards"
LAP = "lap"
CHECK = "check"
KINDS = (LAP, CHECK)
HOOK_EVENT = "PreToolUse"
HOOK_MATCHER = "*"
HOOK_SCRIPT = "profile_guard.py"
MISSING = object()


def hook_group_of(command: str, timeout_seconds: int) -> dict:
    """The hook group of an Antigravity profile copy's hooks.json whose one handler runs `command`, the profile guard's
    command line. install.py writes it and factory.py looks for it, so the two share this shape. It matches every tool,
    because the guard denies a tool it does not know."""
    return {"matcher": HOOK_MATCHER, "hooks": [{"type": "command", "command": command, "timeout": timeout_seconds}]}


def is_hook_group(group: object) -> bool:
    """True when the group matches every tool and has a handler that runs the profile guard."""
    if not isinstance(group, dict) or group.get("matcher") != HOOK_MATCHER:
        return False
    handlers = group.get("hooks")
    return isinstance(handlers, list) and any(
        isinstance(handler, dict) and HOOK_SCRIPT in str(handler.get("command") or "") for handler in handlers)


class RecordError(Exception):
    """A record exists for a worktree but cannot be read as one."""


@dataclass(frozen=True)
class GuardRecord:
    """What a lap worker's guard needs: the worktree, the kind of worker, the lap's stage, the commands the worker
    may run, in the form `lap_lists.py` prints them, and the acceptance folders the worker may not write in, in the
    form `lap_protected.py` prints them: a list that is empty for a check worker and for a folder that holds no
    task's lap, and None when the folders could not be read, which denies every write."""
    worktree: str
    kind: str
    stage: str
    commands: list
    barred: list[str] | None


def record_path(home: Path, worktree: Path) -> Path:
    resolved = worktree.resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:8]
    return home / FOLDER / f"{resolved.name}-{digest}.json"


def write_record(home: Path, record: GuardRecord) -> None:
    """Writes the record for its worktree, whole, replacing the one the worktree had."""
    path = record_path(home, Path(record.worktree))
    stored = {"worktree": str(Path(record.worktree).resolve()), "kind": record.kind, "stage": record.stage,
              "commands": record.commands, "barred": record.barred}
    home_files.write_in_home(path.parent, path.name, json.dumps(stored))


def remove_record(home: Path, worktree: Path) -> None:
    """Removes the worktree's record, so that no list holds a session in the worktree; a worktree with none is no
    error."""
    record_path(home, worktree).unlink(missing_ok=True)


def jidoka_home() -> Path:
    return settings_reader.jidoka_home(None)


def read_record(home: Path, folder: Path) -> GuardRecord | None:
    """The record of the worktree that holds `folder`, or None when no folder from `folder` up to the root has one.
    Raises RecordError for a record that is not a readable one."""
    for candidate in [folder.resolve(), *folder.resolve().parents]:
        path = record_path(home, candidate)
        if path.is_file():
            return parse(path)
    return None


def parse(path: Path) -> GuardRecord:
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RecordError(f"{path} cannot be read: {error}") from error
    if not isinstance(stored, dict):
        raise RecordError(f"{path} is not a JSON object")
    worktree, kind, stage, commands = (stored.get(key) for key in ("worktree", "kind", "stage", "commands"))
    if not isinstance(worktree, str) or not isinstance(stage, str) or kind not in KINDS \
            or not isinstance(commands, list):
        raise RecordError(f"{path} lacks a worktree, a kind of lap or check, a stage or a list of commands")
    barred = stored.get("barred", MISSING)
    if barred is not None and (not isinstance(barred, list) or not all(isinstance(item, str) for item in barred)):
        raise RecordError(f"{path} lacks `barred`, a list of folders or null when they could not be read")
    return GuardRecord(worktree=worktree, kind=kind, stage=stage, commands=commands, barred=barred)
