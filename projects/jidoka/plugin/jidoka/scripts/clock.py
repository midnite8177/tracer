"""The second the scripts take as now.

It is the machine's clock, unless JIDOKA_NOW holds a whole number of seconds since the epoch, which stands
in for the clock so that a test can move through a back-off without waiting. The scripts that compare a
time with now read it here.
"""
from __future__ import annotations

import os
import time

NOW_VARIABLE = "JIDOKA_NOW"


def now() -> int:
    """The current second since the epoch."""
    faked = os.environ.get(NOW_VARIABLE, "").strip()
    try:
        return int(faked) if faked else int(time.time())
    except ValueError:
        return int(time.time())
