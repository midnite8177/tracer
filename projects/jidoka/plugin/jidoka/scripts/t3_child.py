"""What the scripts that run a worker as a T3 child task share: the record `start` leaves, the reading of it back in
`finish`, and the checks every child's run must pass.

A T3 child runs in the main checkout or in a checkout of its own, outside the lap's worktree, so a script that starts
one records a fingerprint of the main checkout and a wall clock beside the route and the reply path. Each script keeps
what is its own: the route it accepts, the task it sends, the fields it adds to the record, and how it reads the reply
and records the outcome.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, Protocol, TypeVar

import clock
import routes
from commands import run

CHILD = "the T3 child"


class ChildError(Exception):
    """A reason the child's run failed, worded for the person who reads stderr."""


class WallClockExceeded(ChildError):
    """The child ran past the stage's wall clock."""


def fingerprint(main_tree: Path) -> str:
    """What the main checkout holds: the commit it is on, every path git reports as changed or untracked, and the size
    and modification time of each, so that a file edited again after it was already changed shows."""
    head = run(["git", "rev-parse", "HEAD"], main_tree, None).strip()
    status = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], main_tree, None)
    digest = hashlib.sha256(f"{head}\0{status}".encode("utf-8", errors="replace"))
    for entry in status.split("\0"):
        if len(entry) < 4:
            continue
        path = main_tree / entry[3:]
        try:
            stat = path.stat()
            digest.update(f"{entry[3:]}\0{stat.st_size}\0{stat.st_mtime_ns}\0".encode("utf-8", errors="replace"))
        except OSError:
            digest.update(f"{entry[3:]}\0gone\0".encode("utf-8", errors="replace"))
    return digest.hexdigest()


@dataclass(frozen=True)
class ChildStart:
    """What every start of a T3 child names for itself: where the start record and the reply go, the epic, the route
    the child runs on and the wall clock it gets."""
    state_file: Path
    reply_file: Path
    epic: str
    route: routes.Route
    wall_seconds: int


class OwnFields(Protocol):
    """The fields a script adds to the start record, which it writes as a JSON object."""

    def to_record(self) -> dict: ...


Own = TypeVar("Own", bound=OwnFields)


@dataclass(frozen=True)
class NoOwnFields:
    """The own fields of a script that adds nothing to the start record."""

    def to_record(self) -> dict:
        return {}

    @staticmethod
    def of(record: dict) -> NoOwnFields:
        return NoOwnFields()


@dataclass(frozen=True)
class Started(Generic[Own]):
    """The start record, written and read back by this one type: the shared fields, each of its type, and `own`, the
    fields that the script which started the child added, typed by that script and kept under their own key."""
    epic: str
    route: routes.Route
    reply: Path
    started: int
    wall_seconds: int
    fingerprint: str
    own: Own

    def to_record(self) -> dict:
        """The JSON object `parse` reads back."""
        return {"epic": self.epic, "route": self.route.as_dict(), "reply": str(self.reply), "started": self.started,
                "wall_seconds": self.wall_seconds, "fingerprint": self.fingerprint, "own": self.own.to_record()}

    @staticmethod
    def parse(record: object, own_of: Callable[[dict], Own | None]) -> Started[Own] | None:
        """The start that the JSON value holds, or None when a shared field or an own field is missing or mistyped.
        `own_of` reads the own fields from the object under `own` and returns None for one that lacks them."""
        if not isinstance(record, dict):
            return None
        shared = {"epic": str, "reply": str, "started": int, "wall_seconds": int, "fingerprint": str}
        if not all(isinstance(record.get(name), kind) for name, kind in shared.items()):
            return None
        try:
            route = routes.Route.parse(CHILD, record.get("route"))
        except routes.RouteError:
            return None
        held = record.get("own")
        own = own_of(held) if isinstance(held, dict) else None
        if own is None:
            return None
        return Started(record["epic"], route, Path(record["reply"]), record["started"], record["wall_seconds"],
                       record["fingerprint"], own)

    def elapsed(self) -> int:
        """The seconds from the start to now, never negative."""
        return max(0, clock.now() - self.started)


def record_start(child: ChildStart, main_tree: Path, own: Own, delegate_task: dict) -> dict:
    """Clears the last reply, writes the start record with the fields of `own`, and returns what `start` prints: the
    `delegate_task` arguments, the `reply` path, the `wall_seconds` and the `deadline`."""
    started = clock.now()
    child.reply_file.unlink(missing_ok=True)
    child.state_file.parent.mkdir(parents=True, exist_ok=True)
    state = Started(child.epic, child.route, child.reply_file, started, child.wall_seconds, fingerprint(main_tree), own)
    child.state_file.write_text(json.dumps(state.to_record()), encoding="utf-8")
    return {"delegate_task": delegate_task, "reply": str(child.reply_file), "wall_seconds": child.wall_seconds,
            "deadline": started + child.wall_seconds}


def started_state(state_file: Path, own_of: Callable[[dict], Own | None], what: str) -> Started[Own]:
    """The start record `record_start` wrote, read back as a `Started`. `own_of` reads the script's own fields, and
    `what` names the run in the error: a lane or a batch."""
    try:
        record = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ChildError(f"{state_file} was not read, so the {what} never started: {error}") from error
    started = Started.parse(record, own_of)
    if started is None:
        raise ChildError(f"{state_file} does not hold the start of a {what}")
    return started


def check_child_run(state: Started, seconds: int, main_tree: Path, main_must_hold: str) -> str:
    """The child's reply, when the run kept the wall clock, left the main checkout as `start` saw it and left a reply
    that is not blank. `main_must_hold` says why the main checkout must not change, to finish the error."""
    if seconds > state.wall_seconds:
        raise WallClockExceeded(f"{CHILD} ran past the wall clock of {state.wall_seconds} seconds")
    if fingerprint(main_tree) != state.fingerprint:
        raise ChildError(f"the main checkout {main_tree} changed while the child ran, and {main_must_hold}")
    text = state.reply.read_text(encoding="utf-8", errors="replace") if state.reply.is_file() else ""
    if not text.strip():
        raise ChildError(f"{CHILD} left no reply at {state.reply}")
    return text
