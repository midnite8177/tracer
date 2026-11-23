"""The Antigravity account's quota, read from T3 and kept for the scheduler, and the shape of the file that holds it.

An Antigravity host under T3 has no lap mod to read the account's usage windows, but T3 reads them from Google and
lists them in the Antigravity provider's `usageLimits` in `server.getConfig` (ADR 0011). On each scheduler call whose
host is Antigravity, `refresh` reads that config through provider_status.py, with the token that setup issued, and
writes `<jidoka home>/usage/antigravity.json`:

  checkedAt  the second, since the epoch, at which T3 last read the quota from Google.
  buckets    for each bucket, its name and its `session` (five-hour) and `weekly` windows, each with `id`,
             `usedPercent`, `resetsAt` (a second since the epoch, or null) and `windowDurationMins` (or null). A
             bucket that has only one of the two keeps only that one.

T3 names a window `<bucket>-5h`, `<bucket>-weekly` or `<bucket>-quota` and gives it a kind. `refresh` leaves out a window
of any kind other than session or weekly.

Anything that is not a good reading is no reading: T3 not running, a refused token, a changed protocol, a config with
no usage limits, usage T3 calls unavailable, or a `checkedAt` more than ten minutes old, since T3 renews its reading
only while Antigravity takes turns. `refresh` then removes the file, so that no older reading outlives the cause, says
why on stderr and returns the cause as Unread. No reason ever holds the token. `read` is the one reader of the file, for the
scheduler's reserves and for status.py: it takes a file that is missing, of another shape or older than ten minutes
for none.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import home_files
import provider_status
import routes
import t3_token
from rules import is_number, is_whole

USAGE_FOLDER = "usage"
USAGE_FILE = f"{USAGE_FOLDER}/antigravity.json"
FRESH_SECONDS = 10 * 60
SESSION, WEEKLY = "session", "weekly"
KINDS = (SESSION, WEEKLY)
BUCKET_SUFFIX = re.compile(r"-(5h|weekly|quota)$")
MILLISECOND_EPOCH_FROM = 100_000_000_000


class NoReading(Exception):
    """T3 gave no usable reading of the quota. The reason is worded for the person who reads stderr and never holds
    the token or the ticket."""


class StaleReading(NoReading):
    """T3's reading is older than ten minutes. Its reason names the age, which differs on every call, so it is a cause
    of its own."""


STALE_CAUSE = "T3's reading of the Antigravity quota is more than ten minutes old"


@dataclass(frozen=True)
class Unread:
    """What `refresh` gives when there is no reading: the cause, worded to stay the same for as long as the same thing
    keeps T3 from giving a reading."""
    cause: str


def cause_of(error: Exception) -> str:
    return STALE_CAUSE if isinstance(error, StaleReading) else str(error)


@dataclass(frozen=True)
class Window:
    """One usage window of a bucket: how much of it is used, the second it resets and how long it is."""
    id: str
    used_percent: float
    resets_at: int | None
    duration_minutes: float | None

    def fields(self) -> dict:
        return {"id": self.id, "usedPercent": self.used_percent, "resetsAt": self.resets_at,
                "windowDurationMins": self.duration_minutes}


@dataclass(frozen=True)
class Bucket:
    """The windows of the part of the quota that one family of models draws on."""
    name: str
    session: Window | None
    weekly: Window | None


@dataclass(frozen=True)
class Reading:
    """The quota of the account at `checked_at`, a second since the epoch, in buckets."""
    checked_at: int
    buckets: tuple[Bucket, ...]

    def fields(self) -> dict:
        return {"checkedAt": self.checked_at,
                "buckets": {bucket.name: {kind: window.fields() for kind, window in
                                          ((SESSION, bucket.session), (WEEKLY, bucket.weekly)) if window is not None}
                            for bucket in self.buckets}}


def seconds_of(value: object) -> int | None:
    """The second since the epoch that a time of T3 names, an ISO text or a number of seconds or milliseconds, or
    None for anything else."""
    if is_number(value):
        return int(value / 1000) if value >= MILLISECOND_EPOCH_FROM else int(value)
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)).timestamp())


def window_of(raw: object) -> tuple[str, str, Window] | None:
    """The bucket, the kind and the window that one of T3's windows says, or None for a window of another kind or one
    that does not say how much of it is used."""
    if not isinstance(raw, dict) or raw.get("kind") not in KINDS:
        return None
    identifier, used = raw.get("id"), raw.get("usedPercent")
    if not isinstance(identifier, str) or not identifier or not is_number(used):
        return None
    minutes = raw.get("windowDurationMins")
    return (BUCKET_SUFFIX.sub("", identifier), raw["kind"],
            Window(identifier, float(used), seconds_of(raw.get("resetsAt")), float(minutes) if is_number(minutes)
                   else None))


def reading_in(config: object, now: int) -> Reading:
    """The reading that what `server.getConfig` returned holds. It raises NoReading for a config that has no usage
    limits for Antigravity, usage that T3 calls unavailable, a `checkedAt` that is no time or is older than ten
    minutes, and limits with no session or weekly window."""
    limits = provider_status.antigravity_entry(config).get("usageLimits")
    if not isinstance(limits, dict):
        raise NoReading("T3 holds no usage limits for the Antigravity provider")
    if limits.get("unavailable"):
        raise NoReading("T3 says the Antigravity usage is unavailable")
    checked_at = seconds_of(limits.get("checkedAt"))
    if checked_at is None:
        raise NoReading("T3's usage limits for Antigravity hold no checkedAt time")
    if now - checked_at > FRESH_SECONDS:
        raise StaleReading(f"T3 last checked the Antigravity quota {(now - checked_at) // 60} minutes ago")
    windows = limits.get("windows")
    named = [window_of(raw) for raw in windows] if isinstance(windows, list) else []
    kept: dict[str, dict[str, Window]] = {}
    for found in named:
        if found is not None:
            bucket, kind, window = found
            kept.setdefault(bucket, {})[kind] = window
    if not kept:
        raise NoReading("T3's usage limits for Antigravity hold no session or weekly window")
    return Reading(checked_at, tuple(Bucket(name, held.get(SESSION), held.get(WEEKLY)) for name, held in kept.items()))


def window_in(raw: object) -> Window | None:
    if not isinstance(raw, dict):
        return None
    identifier, used, resets_at, minutes = (raw.get("id"), raw.get("usedPercent"), raw.get("resetsAt"),
                                            raw.get("windowDurationMins"))
    if not isinstance(identifier, str) or not is_number(used):
        return None
    return Window(identifier, float(used), int(resets_at) if is_whole(resets_at) else None,
                  float(minutes) if is_number(minutes) else None)


def read(home: Path, now: int) -> Reading | None:
    """The reading `refresh` last wrote, or None for a missing file, one that cannot be read or has another shape, and
    one older than ten minutes."""
    try:
        raw = json.loads((home / USAGE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    checked_at = raw.get("checkedAt") if isinstance(raw, dict) else None
    buckets = raw.get("buckets") if isinstance(raw, dict) else None
    if not is_whole(checked_at) or now - checked_at > FRESH_SECONDS or not isinstance(buckets, dict):
        return None
    return Reading(checked_at, tuple(Bucket(str(name), window_in(held.get(SESSION)), window_in(held.get(WEEKLY)))
                                     for name, held in buckets.items() if isinstance(held, dict)))


def refresh(home: Path, port: int, timeout_seconds: float, now: int) -> Reading | Unread:
    """Reads the quota from the T3 server on the port within the timeout and writes it to the usage file, and returns
    it. When there is no reading it removes the file, says why on stderr and returns the cause as Unread."""
    try:
        token = t3_token.read_token(home)
        if token is None:
            raise NoReading(f"jidoka holds no T3 token; run {routes.slash_command('setup')} and confirm the token")
        reading = reading_in(provider_status.read_config(token, port, timeout_seconds), now)
        (home / USAGE_FOLDER).mkdir(parents=True, exist_ok=True)
        home_files.write_in_home(home, USAGE_FILE, json.dumps(reading.fields()) + "\n")
        return reading
    except (NoReading, provider_status.NoStatus, OSError) as error:
        print(f"scheduler: no Antigravity usage reading: {error}", file=sys.stderr)
        try:
            (home / USAGE_FILE).unlink(missing_ok=True)
        except OSError as unlink_error:
            print(f"scheduler: the Antigravity usage file was not removed: {unlink_error}", file=sys.stderr)
        return Unread(cause_of(error))
