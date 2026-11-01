"""The record a running watcher keeps in the jidoka home, and the readers other scripts use to ask about it.

watch.py writes <jidoka-home>/watcher/<epic>.json when its watch begins, a JSON object with
  epic        the epic the watcher watches.
  pid         the watcher's process id.
  started     when that process began, as `processes.started_at` prints it, so that a process which later takes
              the same pid is not taken for the watcher. null when the start could not be read.
  session     the id of the session that started the watcher (JIDOKA_SESSION_ID), or null when it got none.
  time        the second the watch began, since the epoch.
  waits_for   what the watch began by finding, a WaitsFor: `parked`, the sorted ids of the beads that carry the
              human label. It lists none until the first snapshot of the beads lands. A watcher also ends on a new
              task, a merged task and room that frees for a ready task, whatever these hold.
The watcher removes the file when it exits. A watcher that was killed leaves it behind. `live_watcher` is the reader
that counts a record whose process is gone as no watcher; `read_record` alone does not.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import processes

WATCHER_FOLDER = "watcher"


@dataclass(frozen=True)
class WaitsFor:
    """The beads that carried the human label when the watch began: the ones whose label coming off ends the watch."""
    parked: frozenset[str]

    def fields(self) -> dict:
        return {"parked": sorted(self.parked)}


def parsed_waits_for(held: object) -> WaitsFor | None:
    """The WaitsFor that the stored object holds, or None when it is not the shape `WaitsFor.fields` writes."""
    if not isinstance(held, dict):
        return None
    parked = held.get("parked")
    if not isinstance(parked, list) or not all(isinstance(bead, str) for bead in parked):
        return None
    return WaitsFor(frozenset(parked))


@dataclass(frozen=True)
class WatcherRecord:
    epic: str
    pid: int
    started: str | None
    session: str | None
    time: int
    waits_for: WaitsFor


def record_path(home: Path, epic: str) -> Path:
    return home / WATCHER_FOLDER / f"{epic}.json"


def write_record(home: Path, record: WatcherRecord) -> None:
    """Writes the record through a temporary file beside it, so a reader never finds half of it."""
    path = record_path(home, record.epic)
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(f"{path.name}.tmp")
    scratch.write_text(json.dumps({"epic": record.epic, "pid": record.pid, "started": record.started,
                                   "session": record.session, "time": record.time,
                                   "waits_for": record.waits_for.fields()}), encoding="utf-8")
    os.replace(scratch, path)


def read_record(home: Path, epic: str) -> WatcherRecord | None:
    """The epic's record, or None when it is missing, unreadable or incomplete. The process it names may be gone."""
    try:
        held = json.loads(record_path(home, epic).read_text(encoding="utf-8"))
        named, pid, started = held["epic"], held["pid"], held["started"]
        session, time, waits_for = held["session"], held["time"], held["waits_for"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    waits = parsed_waits_for(waits_for)
    if (isinstance(named, str) and isinstance(pid, int) and isinstance(time, int)
            and isinstance(started, (str, type(None))) and isinstance(session, (str, type(None)))
            and waits is not None):
        return WatcherRecord(named, pid, started, session, time, waits)
    return None


def live_watcher(home: Path, epic: str) -> WatcherRecord | None:
    """The epic's record when the process it names runs and began when the record says, and None otherwise."""
    held = read_record(home, epic)
    if held is None or not processes.is_alive(held.pid):
        return None
    if held.started is not None and processes.started_at(held.pid) != held.started:
        return None
    return held


def remove_record(home: Path, epic: str, pid: int) -> None:
    """Deletes the epic's record when it names this pid, and leaves the record of another watcher of the epic."""
    held = read_record(home, epic)
    if held is not None and held.pid == pid:
        record_path(home, epic).unlink(missing_ok=True)
