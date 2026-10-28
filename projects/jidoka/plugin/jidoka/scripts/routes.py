"""The routes a machine records for its tiers, the native route each tier falls back to, and the reader of the machine
settings file that holds them.

A route is a JSON object with `harness`, `model`, `version` and `effort`, kept under `routes` in
<jidoka-home>/settings.json. Native means the host's own harness, `claude`. A tier's native route is the one setup
proposes for it when no other harness is on the machine, so a stage that falls back keeps the model its tier asked
for. A tier with no row there falls back to the host's own model and effort, which null values stand for.

The settings file also holds the default budget and the reserves, and the installer's own keys. The one reader and the
one writer of that file, and of the other files jidoka keeps whole in its home, are here, so that every script
meets the same error for a file it cannot read.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

NATIVE_HARNESS = "claude"
CODEX_HARNESS = "codex"
SETTINGS_FILE = "settings.json"
RERUN = "Run install.py from your jidoka checkout to record this machine's routes"
SECOND_TIER = "second"

T = TypeVar("T")


def native(model: str | None, version: str | None, effort: str | None) -> dict:
    return {"harness": NATIVE_HARNESS, "model": model, "version": version, "effort": effort}


NATIVE_ROUTES: dict[str, dict] = {
    "light": native("haiku", "5.5", "medium"),
    "standard": native("sonnet", "5.5", "high"),
    "deep": native("opus", "5.5", "high"),
    SECOND_TIER: native("opus", "5.5", "high"),
    "local": native("sonnet", "5.5", "medium"),
}
HOST_OWN_ROUTE = native(None, None, None)


class RouteError(Exception):
    """Settings that cannot answer a question about a route, worded for the person who reads stderr."""


def native_route_of(tier: str) -> dict:
    return dict(NATIVE_ROUTES.get(tier, HOST_OWN_ROUTE))


def default_routes(codex_found: bool) -> dict[str, dict]:
    """The route of each tier on a machine: the second tier runs in codex when it is found, else on its native route,
    and every other tier runs on its native route."""
    defaults = {tier: native_route_of(tier) for tier in NATIVE_ROUTES}
    if codex_found:
        defaults[SECOND_TIER] = {"harness": CODEX_HARNESS, "model": None, "version": None, "effort": None}
    return defaults


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
        raise RouteError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(settings, dict):
        raise RouteError(f"{path} does not hold a JSON object")
    return settings


def recorded_route(tier: str, home: Path) -> dict:
    """The route the machine records for the tier; a home without settings, or without that tier, is an error."""
    path = settings_path(home)
    if not path.is_file():
        raise RouteError(f"{path} does not exist. {RERUN}")
    recorded = settings_in(home).get("routes")
    found = recorded.get(tier) if isinstance(recorded, dict) else None
    if not isinstance(found, dict) or not found.get("harness"):
        raise RouteError(f"{path} holds no route for the tier {tier!r}. {RERUN}")
    return found


def machine_default(home: Path, key: str, noun: str, valid: Callable[[object], T | None]) -> T | None:
    """What `valid` makes of the machine settings' value under the key, or None when it makes nothing of it.
    Settings that cannot be read give none, and a line on stderr that names the noun."""
    try:
        return valid(settings_in(home).get(key))
    except RouteError as error:
        print(f"scheduler: the machine's default {noun} was not read: {error}", file=sys.stderr)
        return None


def write_in_home(home: Path, name: str, text: str) -> None:
    """Replaces the file of the home whole, so that a reader running beside this one never reads half of it."""
    home.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=home, prefix=f"{Path(name).stem}-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, home / name)
    except OSError:
        Path(temporary).unlink(missing_ok=True)
        raise
