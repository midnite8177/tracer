"""What the scripts that run a worker as a T3 child task share: the record `start` leaves, the reading of it back in
`finish`, and the checks every child's run must pass.

A T3 child runs in the main checkout or in a checkout of its own, outside the lap's worktree, so a script that starts
one records a fingerprint of the main checkout and a wall clock beside the route and the reply path. Each script keeps
what is its own: the route it accepts, the task it sends, and how it reads the reply and records the outcome.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import clock
import routes
from commands import run

CHILD = "the T3 child"
START_FIELDS = {"epic": str, "route": dict, "reply": str, "started": int, "wall_seconds": int, "main": str}


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


def record_start(child: ChildStart, main_tree: Path, own_fields: dict, delegate_task: dict) -> dict:
    """Clears the last reply, writes the start record with `own_fields` among the shared ones, and returns what
    `start` prints: the `delegate_task` arguments, the `reply` path, the `wall_seconds` and the `deadline`."""
    started = clock.now()
    child.reply_file.unlink(missing_ok=True)
    child.state_file.parent.mkdir(parents=True, exist_ok=True)
    state = {"epic": child.epic, "route": child.route.as_dict(), "reply": str(child.reply_file), "started": started,
             "wall_seconds": child.wall_seconds, "main": fingerprint(main_tree), **own_fields}
    child.state_file.write_text(json.dumps(state), encoding="utf-8")
    return {"delegate_task": delegate_task, "reply": state["reply"], "wall_seconds": child.wall_seconds,
            "deadline": started + child.wall_seconds}


def started_state(state_file: Path, own_fields: dict[str, type], what: str) -> dict:
    """The start record `record_start` wrote, which must hold the shared fields and `own_fields`, each of its type.
    `what` names the run in the error: a lane or a batch."""
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ChildError(f"{state_file} was not read, so the {what} never started: {error}") from error
    kinds = {**START_FIELDS, **own_fields}
    if not (isinstance(state, dict) and all(isinstance(state.get(name), kind) for name, kind in kinds.items())):
        raise ChildError(f"{state_file} does not hold the start of a {what}")
    return state


def check_child_run(state: dict, seconds: int, main_tree: Path, main_must_hold: str) -> str:
    """The child's reply, when the run kept the wall clock, left the main checkout as `start` saw it and left a reply
    that is not blank. `main_must_hold` says why the main checkout must not change, to finish the error."""
    if seconds > state["wall_seconds"]:
        raise WallClockExceeded(f"{CHILD} ran past the wall clock of {state['wall_seconds']} seconds")
    if fingerprint(main_tree) != state["main"]:
        raise ChildError(f"the main checkout {main_tree} changed while the child ran, and {main_must_hold}")
    reply = Path(state["reply"])
    text = reply.read_text(encoding="utf-8", errors="replace") if reply.is_file() else ""
    if not text.strip():
        raise ChildError(f"{CHILD} left no reply at {reply}")
    return text
