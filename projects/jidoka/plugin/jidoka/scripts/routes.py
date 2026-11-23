"""The routes a machine records for its tiers, and the native route each tier falls back to.

A route is a JSON object with `harness`, `model`, `version` and `effort`. The machine settings keep one table of them
for each host, in <jidoka-home>/settings.json: Claude Code's under `routes` and Antigravity's under
`antigravity_routes`. A route on the harness `t3` also holds `provider`, the T3 provider instance that runs
the child task, and may hold `driver` and `effort_option`, the name of the option that sets the effort on its model.
`Route` parses and checks one, including the fields that a harness requires, so
that every script meets the same error for a recorded route that is incomplete. Native means the host's own
harness, `claude`. A tier's native route is the one setup
proposes for it when no other harness is on the machine, so a stage that falls back keeps the model its tier asked
for. A tier with no row there falls back to the host's own model and effort, which null values stand for.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from machine_settings import MachineSettingsError, settings_in, settings_path
from texts import is_text, text_or_none

NATIVE_HARNESS = "claude"
CODEX_HARNESS = "codex"
T3_HARNESS = "t3"
T3_REQUIRED_FIELDS = ("provider", "model", "effort")
OPENCODE_DRIVER = "opencode"
ANTIGRAVITY_DRIVER = "antigravity"
EFFORT_OPTIONS = {OPENCODE_DRIVER: "variant", ANTIGRAVITY_DRIVER: "thought_level"}
DEFAULT_EFFORT_OPTION = "effort"
EFFORT_OPTION_FIELD = "effort_option"
CLAUDE_CODE_HOST = "claude-code"
ANTIGRAVITY_HOST = "antigravity"
ROUTE_TABLES = {CLAUDE_CODE_HOST: "routes", ANTIGRAVITY_HOST: "antigravity_routes"}
SLASH_PREFIXES = {CLAUDE_CODE_HOST: "/jidoka:", ANTIGRAVITY_HOST: "/jidoka-"}
SESSION_VARIABLE = "JIDOKA_SESSION_ID"
THREAD_VARIABLE = "T3CODE_THREAD_ID"
CODEX_PROGRAM = "codex"
HARNESS_PROGRAMS = {CODEX_HARNESS: CODEX_PROGRAM}
RERUN = "Run install.py from your jidoka checkout to record this machine's routes"
SECOND_TIER = "second"


def thread_of_environment() -> str | None:
    """The T3 thread of a manager whose host has no lap mod, which a beater keeps fresh. None when
    $JIDOKA_SESSION_ID is set, since a host that exports a session has the lap mod beat for it, and when no thread
    is set."""
    if os.environ.get(SESSION_VARIABLE):
        return None
    return os.environ.get(THREAD_VARIABLE) or None


def host_of_environment() -> str:
    """The host the caller runs under, the one place jidoka decides it: Antigravity when `thread_of_environment`
    names a T3 thread, which is when $T3CODE_THREAD_ID is set and $JIDOKA_SESSION_ID is not, else Claude Code. The
    routes of a host's own table follow it."""
    return ANTIGRAVITY_HOST if thread_of_environment() is not None else CLAUDE_CODE_HOST


def slash_command(skill: str) -> str:
    """The slash command that runs the jidoka skill, as the host of `host_of_environment` spells it: `/jidoka:<skill>`
    under Claude Code, where the plugin namespaces its skills, and `/jidoka-<skill>` under Antigravity, whose profile
    copy has no namespace. A message that tells the human to run a skill builds the command here, so that the human
    can paste it as printed."""
    return SLASH_PREFIXES[host_of_environment()] + skill


def table_key(host: str) -> str:
    """The key of the machine settings that holds the route table of the host."""
    return ROUTE_TABLES[host]


class RouteError(Exception):
    """Settings that cannot answer a question about a route, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Route:
    """How one tier runs: the harness, and the model, version and effort on it, where a null stands for the harness's
    own default. A t3 route also names the `provider` that runs the child task, and may name the `driver` kind of that
    provider. The fields that a harness requires are checked where the route is parsed, so that no script holds half
    a route."""
    harness: str
    model: str | None
    version: str | None
    effort: str | None
    provider: str | None
    driver: str | None
    recorded_effort_option: str | None

    @staticmethod
    def parse(tier: str, recorded: object) -> Route:
        """The route that the JSON object holds for the tier, or a RouteError that says what it lacks."""
        if not isinstance(recorded, dict) or not is_text(recorded.get("harness")):
            raise RouteError(f"the route of the tier {tier!r} needs a harness")
        for field in ("model", "version", "effort", EFFORT_OPTION_FIELD):
            if recorded.get(field) is not None and not is_text(recorded[field]):
                raise RouteError(f"the {field} of the route of the tier {tier!r} must be text or null")
        if recorded["harness"] == T3_HARNESS:
            for field in T3_REQUIRED_FIELDS:
                if not is_text(recorded.get(field)):
                    raise RouteError(f"the t3 route of the tier {tier!r} needs a {field}")
        return Route(recorded["harness"], text_or_none(recorded.get("model")), text_or_none(recorded.get("version")),
                     text_or_none(recorded.get("effort")), text_or_none(recorded.get("provider")),
                     text_or_none(recorded.get("driver")), text_or_none(recorded.get(EFFORT_OPTION_FIELD)))

    @property
    def effort_option(self) -> str:
        """The key under which a thread's or child task's model selection carries this route's effort. It is the
        option name the route records from T3's catalog, because each model names its own: Codex takes
        `reasoningEffort`, Claude `effort`, OpenCode `variant`, Antigravity `thought_level`. A route that records none
        falls back to the one its driver implies, and else to `effort`. Every launcher builds its selection from
        it."""
        if self.recorded_effort_option is not None:
            return self.recorded_effort_option
        return EFFORT_OPTIONS.get(self.driver or "", DEFAULT_EFFORT_OPTION)

    @property
    def is_opencode(self) -> bool:
        """Whether this is a t3 route whose provider is an OpenCode one, which `driver` names with the driver kind of
        T3's catalog."""
        return self.harness == T3_HARNESS and self.driver == OPENCODE_DRIVER

    @property
    def is_antigravity(self) -> bool:
        """Whether this is a t3 route whose driver is `antigravity`: a T3 Antigravity thread, which is the native
        route of an Antigravity host, its model the catalog's model id and its effort that model's thought level."""
        return self.harness == T3_HARNESS and self.driver == ANTIGRAVITY_DRIVER

    @property
    def is_native(self) -> bool:
        """Whether this route runs in the harness of a host's own provider: claude under Claude Code, a T3
        Antigravity thread under Antigravity."""
        return self.harness == NATIVE_HARNESS or self.is_antigravity

    def refusal(self, tier: str) -> str | None:
        """Why this route cannot serve the tier under the factory's own stage tiers, or None when it can. A native
        Antigravity route serves every tier, a t3 OpenCode route follows `opencode_refusal`, and any other route
        follows `writing_refusal`."""
        if self.is_antigravity:
            return None
        return opencode_refusal(tier) if self.is_opencode else writing_refusal(tier, self.harness, {})

    def as_dict(self) -> dict:
        """The JSON object of the settings: the four fields every route holds, and `provider`, `driver` and the
        recorded effort option when the route names them."""
        named = {"provider": self.provider, "driver": self.driver, EFFORT_OPTION_FIELD: self.recorded_effort_option}
        return {"harness": self.harness, "model": self.model, "version": self.version, "effort": self.effort,
                **{field: value for field, value in named.items() if value is not None}}


def native(model: str | None, version: str | None, effort: str | None) -> Route:
    return Route(NATIVE_HARNESS, model, version, effort, None, None, None)


NATIVE_ROUTES: dict[str, Route] = {
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


def writing_refusal(tier: str, harness: str, stage_tiers: dict[str, str]) -> str | None:
    """Why a route on the harness cannot serve the tier because a stage that writes runs on it, or None when it can.
    A harness that is not in READ_ONLY_HARNESSES serves any tier."""
    reason = READ_ONLY_HARNESSES.get(harness)
    writing = writing_stages_on(tier, stage_tiers)
    if reason is None or not writing:
        return None
    return f"{reason}, so the {tier} tier cannot run on {harness}: {', '.join(writing)} write on it"


OPENCODE_STAGE = "tidy"


def opencode_refusal(tier: str) -> str | None:
    """Why a t3 OpenCode route cannot serve the tier, or None when it can. The tier may take the route because its
    only writing stage is the tidy, whose T3 child has its shell held for approval by T3's auto-accept-edits mode."""
    writing = writing_stages_on(tier, {})
    if writing == [OPENCODE_STAGE]:
        return None
    on_it = f"{', '.join(writing)} write on it" if writing else f"the {OPENCODE_STAGE} does not run on it"
    return f"a t3 OpenCode route runs the {OPENCODE_STAGE} alone, so the {tier} tier cannot run on it: {on_it}"


def native_route_of(tier: str) -> Route:
    return NATIVE_ROUTES.get(tier, HOST_OWN_ROUTE)


def missing_program(harness: str, which: Callable[[str], str | None]) -> str | None:
    """The program that the harness starts and that `which` cannot find, or None. The host runs its own harness and
    T3 runs the child task of a t3 route, so only a codex route starts a program of its own."""
    program = HARNESS_PROGRAMS.get(harness)
    return program if program is not None and which(program) is None else None


def default_routes(codex_found: bool) -> dict[str, Route]:
    """The route of each tier on a machine: the second tier runs in codex when it is found, else on its native route,
    and every other tier runs on its native route."""
    defaults = dict(NATIVE_ROUTES)
    if codex_found:
        defaults[SECOND_TIER] = Route(CODEX_HARNESS, None, None, None, None, None, None)
    return defaults


def recorded_route(tier: str, home: Path, host: str) -> Route:
    """The route the machine records for the tier in the host's table; a home without settings, without that tier,
    or with a route that lacks a field its harness requires, is an error."""
    path = settings_path(home)
    if not path.is_file():
        raise RouteError(f"{path} does not exist. {RERUN}")
    try:
        recorded = settings_in(home).get(table_key(host))
    except MachineSettingsError as error:
        raise RouteError(str(error)) from error
    found = recorded.get(tier) if isinstance(recorded, dict) else None
    if not isinstance(found, dict) or not found.get("harness"):
        raise RouteError(f"{path} holds no route for the tier {tier!r}. {RERUN}")
    return Route.parse(tier, found)


def recorded_route_here(tier: str, home: Path) -> Route:
    """The route the machine records for the tier in the table of the host the caller runs under."""
    return recorded_route(tier, home, host_of_environment())
