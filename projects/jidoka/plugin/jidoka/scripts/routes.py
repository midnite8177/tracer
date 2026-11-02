"""The routes a machine records for its tiers, the native route each tier falls back to, and the reader of the machine
settings file that holds them.

A route is a JSON object with `harness`, `model`, `version` and `effort`, kept under `routes` in
<jidoka-home>/settings.json. A route on the harness `t3` also holds `provider`, the T3 provider instance that runs
the child task. Native means the host's own harness, `claude`. A tier's native route is the one setup
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
T3_HARNESS = "t3"
CODEX_PROGRAM = "codex"
HARNESS_PROGRAMS = {CODEX_HARNESS: CODEX_PROGRAM}
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


WRITING_STAGE_TIERS: tuple[tuple[str, str], ...] = (
    ("build", "standard"),
    ("build", "deep"),
    ("merge", "deep"),
    ("test-cleanup", "deep"),
    ("tidy", "local"),
    ("fix", "standard"),
)


def writing_stages_on(tier: str, stage_tiers: dict[str, str]) -> list[str]:
    """The stages that change files and run on the tier. Each stage runs on the tier the factory skill gives it,
    except a stage the epic's stage_tiers moves, which runs on the tier named there."""
    stages: list[str] = []
    for stage, default_tier in WRITING_STAGE_TIERS:
        if stage_tiers.get(stage, default_tier) == tier and stage not in stages:
            stages.append(stage)
    return stages


READ_ONLY_HARNESSES: dict[str, str] = {
    CODEX_HARNESS: "codex exec runs read-only review only",
    T3_HARNESS: ("T3 starts a child task in the main checkout or in a checkout of its own, never in a lap's "
                 "worktree, and the lap mod does not guard it"),
}


def writing_refusal(tier: str, harness: object, stage_tiers: dict[str, str]) -> str | None:
    """Why a route on the harness cannot serve the tier because a stage that writes runs on it, or None when it can.
    A harness that is not in READ_ONLY_HARNESSES serves any tier."""
    reason = READ_ONLY_HARNESSES.get(harness) if isinstance(harness, str) else None
    writing = writing_stages_on(tier, stage_tiers)
    if reason is None or not writing:
        return None
    return f"{reason}, so the {tier} tier cannot run on {harness}: {', '.join(writing)} write on it"


OPENCODE_DRIVER = "opencode"
OPENCODE_STAGE = "tidy"


def is_opencode_route(route: object) -> bool:
    """Whether the route is a t3 route whose provider is an OpenCode one, which `driver` names with the driver kind
    of T3's catalog."""
    return (isinstance(route, dict) and route.get("harness") == T3_HARNESS
            and route.get("driver") == OPENCODE_DRIVER)


def opencode_refusal(tier: str) -> str | None:
    """Why a t3 OpenCode route cannot serve the tier, or None when it can. The tier may take the route because its
    only writing stage is the tidy, whose T3 child has its shell held for approval by T3's auto-accept-edits mode."""
    writing = writing_stages_on(tier, {})
    if writing == [OPENCODE_STAGE]:
        return None
    on_it = f"{', '.join(writing)} write on it" if writing else f"the {OPENCODE_STAGE} does not run on it"
    return f"a t3 OpenCode route runs the {OPENCODE_STAGE} alone, so the {tier} tier cannot run on it: {on_it}"


class RouteError(Exception):
    """Settings that cannot answer a question about a route, worded for the person who reads stderr."""


def native_route_of(tier: str) -> dict:
    return dict(NATIVE_ROUTES.get(tier, HOST_OWN_ROUTE))


def missing_program(route: dict, which: Callable[[str], str | None]) -> str | None:
    """The program that the route's harness starts and that `which` cannot find, or None. The host runs its own
    harness and T3 runs the child task of a t3 route, so only a codex route starts a program of its own."""
    program = HARNESS_PROGRAMS.get(str(route.get("harness")))
    return program if program is not None and which(program) is None else None


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
