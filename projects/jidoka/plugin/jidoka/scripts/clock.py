"""The second the scripts take as now.

It is the machine's clock, unless JIDOKA_NOW holds a whole number of seconds since the epoch, which stands
in for the clock so that a test can move through a back-off without waiting. The scripts that compare a
time with now read it here. A script that waits holds a Clock from `from_environment` and sleeps on it: under a
stand-in clock a sleep moves that Clock forward by the seconds it was asked for and waits for none of them.
"""
from __future__ import annotations

import os
import time

NOW_VARIABLE = "JIDOKA_NOW"


def _stand_in() -> int | None:
    faked = os.environ.get(NOW_VARIABLE, "").strip()
    try:
        return int(faked) if faked else None
    except ValueError:
        return None


class Clock:
    """A clock that a script waits on. Under a stand-in second it holds how long the script has slept, so that the
    time it reads moves only with its own sleeps."""

    def __init__(self, stand_in: int | None) -> None:
        self._stand_in = stand_in
        self._slept_seconds = 0

    def now(self) -> int:
        """The current second since the epoch."""
        if self._stand_in is None:
            return int(time.time())
        return self._stand_in + self._slept_seconds

    def sleep(self, seconds: int) -> None:
        """Waits the seconds, or under a stand-in clock moves now forward by them."""
        if self._stand_in is None:
            time.sleep(seconds)
        else:
            self._slept_seconds += seconds


def from_environment() -> Clock:
    """A Clock that reads the machine's clock, or the second JIDOKA_NOW holds."""
    return Clock(_stand_in())


def now() -> int:
    """The current second since the epoch, for a script that never waits."""
    return from_environment().now()
