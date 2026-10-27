"""What an epic records while the factory waits on the clock, and the back-off it waits by.

The scheduler imports it; no command line runs it. A usage limit, an outage, a billing error or an auth
failure pauses the epic: nothing new starts until the pause's `until`, and then the laps go on by themselves.
Each retry that meets the same trouble waits longer: 5, 15 and 30 minutes, then an hour every time. The epic's
`pause` metadata holds a JSON object with `cause`, `since` (the second the pause began), `until` (the second
the next retry may start) and `retries` (how many retries have failed). A worker that ends without the trouble,
once `until` has passed, ends the pause.

A billing error and an auth failure wait on the human, so each is notified at once. An outage is notified once
it has lasted an hour. A usage limit waits on the reset and is never notified.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from commands import env_as_factory, run

PAUSE_KEY = "pause"
USAGE_LIMIT = "usage-limit"
OUTAGE = "outage"
BILLING = "billing"
AUTH = "auth"
CAUSES = [USAGE_LIMIT, OUTAGE, BILLING, AUTH]
BACKOFF_SECONDS = (5 * 60, 15 * 60, 30 * 60)
HOURLY_SECONDS = 60 * 60
OUTAGE_NOTIFIED_AFTER_SECONDS = 60 * 60
WORDS = {USAGE_LIMIT: "a usage limit", OUTAGE: "an outage", BILLING: "a billing error", AUTH: "an auth failure"}


def wait_seconds(retries: int) -> int:
    """How long to wait after the given number of failed retries: the first wait follows none."""
    return BACKOFF_SECONDS[retries] if retries < len(BACKOFF_SECONDS) else HOURLY_SECONDS


@dataclass(frozen=True)
class Pause:
    """The epic's pause as its metadata records it."""
    cause: str
    since: int
    until: int
    retries: int

    def is_waiting(self, now: int) -> bool:
        return now < self.until

    def needs_human(self, now: int) -> bool:
        """True when the trouble is one only the human clears, or an outage that has lasted an hour."""
        return (self.cause in (BILLING, AUTH)
                or (self.cause == OUTAGE and now - self.since >= OUTAGE_NOTIFIED_AFTER_SECONDS))

    def fields(self, now: int) -> dict:
        return {"cause": self.cause, "since": self.since, "until": self.until, "retries": self.retries,
                "wait_seconds": max(0, self.until - now)}


def held_by(epic: dict) -> Pause | None:
    """The pause the epic's metadata holds, or None when it holds none or nothing usable."""
    metadata = epic.get("metadata")
    held = metadata.get(PAUSE_KEY) if isinstance(metadata, dict) else None
    if isinstance(held, str) and held.strip():
        try:
            held = json.loads(held)
        except ValueError:
            return None
    if not isinstance(held, dict):
        return None
    try:
        cause = str(held["cause"])
        return Pause(cause, int(held["since"]), int(held["until"]), int(held["retries"])) if cause in CAUSES else None
    except (KeyError, TypeError, ValueError):
        return None


def after_trouble(held: Pause | None, cause: str, now: int) -> Pause:
    """The pause once a worker has met the trouble at `now`.

    The first trouble starts a pause. Trouble that another lap met while the pause waits changes nothing, and
    trouble that a retry meets lengthens the wait.
    """
    if held is None:
        return Pause(cause, now, now + wait_seconds(0), 0)
    if held.is_waiting(now):
        return held
    retries = held.retries + 1
    return Pause(cause, held.since, now + wait_seconds(retries), retries)


def write(epic: str, pause: Pause, main_tree: Path) -> None:
    written = json.dumps({"cause": pause.cause, "since": pause.since, "until": pause.until,
                          "retries": pause.retries}, sort_keys=True)
    run(["bd", "update", epic, "--set-metadata", f"{PAUSE_KEY}={written}"], main_tree, env_as_factory())


def clear(epic: str, main_tree: Path) -> None:
    run(["bd", "update", epic, "--set-metadata", f"{PAUSE_KEY}="], main_tree, env_as_factory())
