"""The words a worker's report ends a stage with, and the error that stops a scheduler call.

An outcome is what `scheduler.py report` takes after `--outcome`. `BLOCKED` is also the stage a lap rests at when its
worker ended with that outcome, so one word names both. The module imports only spec_check.py, so any script can
import it without a cycle.
"""
from __future__ import annotations

import spec_check

DONE = "done"
FAILED = "failed"
CUT_OFF = "cut off"
QUESTION = "question"
SEND_BACK = "send back"
BLOCKED = "blocked"
PASS = spec_check.PASS
CANNOT_JUDGE = spec_check.CANNOT_JUDGE


class SchedulerError(Exception):
    """A reason the script writes nothing more, worded for the person who reads stderr."""
