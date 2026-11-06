"""The reader and the writer of the machine settings file, <jidoka-home>/settings.json.

The file holds the routes of the tiers, the default budget, the reserves, the lap limit and the installer's own keys.
Every script reads and writes it here, the installer included, so that every script meets the same error for a file it
cannot read, and a reader running beside a writer never finds half of the file.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import home_files

SETTINGS_FILE = "settings.json"
CLAUDE_ACCOUNT = "claude"
"""The account that the host's own harness bills, the key of its reserve in the settings and the name of its usage
file."""

T = TypeVar("T")


class MachineSettingsError(Exception):
    """A machine settings file that cannot be read, worded for the person who reads stderr."""


def settings_path(home: Path) -> Path:
    return home / SETTINGS_FILE


def settings_in(home: Path) -> dict:
    """The machine settings object, or an empty one when the home has no settings file."""
    path = settings_path(home)
    if not path.is_file():
        return {}
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise MachineSettingsError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(settings, dict):
        raise MachineSettingsError(f"{path} does not hold a JSON object")
    return settings


def write_settings(home: Path, settings: dict) -> None:
    """Replaces the machine settings file with the settings, whole."""
    home_files.write_in_home(home, SETTINGS_FILE, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")


def machine_default(home: Path, key: str, noun: str, read_value: Callable[[object], T | None]) -> T | None:
    """What `read_value` makes of the machine settings' value under the key, or None when it makes nothing of it.
    Settings that cannot be read give none, and a line on stderr that names the noun."""
    try:
        return read_value(settings_in(home).get(key))
    except MachineSettingsError as error:
        print(f"scheduler: the machine's default {noun} was not read: {error}", file=sys.stderr)
        return None
