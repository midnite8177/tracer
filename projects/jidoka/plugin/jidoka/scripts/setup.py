#!/usr/bin/env python3
"""Proposes this machine's routes, budget default, reserves and lap limit, and writes them once confirmed.

`propose [--t3-catalog <file>]` looks at the machine and prints one JSON object, and writes nothing. The file is
T3's catalog as `orchestrator_capabilities` prints it, saved by the setup skill under T3; without it the proposal
is the one for a machine outside T3. A file that cannot be read as JSON is refused.
  found      the path of each harness on the PATH, or null: `claude` and `codex`.
  accounts   how each harness bills, `subscription` or `api_key`. A harness bills by API key when its key
             variable is set: ANTHROPIC_API_KEY for claude, OPENAI_API_KEY or CODEX_API_KEY for codex. Codex is
             listed only when it is found; claude is always listed, because it is the host.
  routes     a route for each tier. The second tier runs on t3 Codex when --t3-catalog names a Codex provider
             that can run a child task: on gpt-6.1-sol when the provider lists it, else on the first model it
             lists, at high effort when that model offers it, else at its default effort. Else it runs in codex
             when that is found, else on the native route of the tier. Every other tier runs on its native route.
  budget     the default budget of an epic, in dollars at list price: 50 when the claude account is a subscription,
             and 20 when it bills by API key, where the dollars are real.
  reserves   0.2 for the claude account when it is on a subscription, because only a subscription has a usage window
             to hold back, and the lap mod reads the usage of the claude account alone. An account on an API key
             has none, and no reserve is proposed for codex.
  lap_limit  the most open laps the machine allows: it caps every epic's laps, and the laps of all the running
             epics together. The one the settings hold, else 4.
  recorded   the routes, budget, reserves and lap limit the settings hold now, each null when they hold none.

`write --confirmed` reads a JSON object on stdin with `routes`, `budget`, `reserves` and `lap_limit`, the proposal as
the human confirmed or edited it, checks all four before it writes any, and puts them into <jidoka-home>/settings.json.
Every other key of the settings stays as it is, and the routes replace the stored ones whole. A route on codex or
t3 is refused for a tier that has a stage which writes; routes.READ_ONLY_HARNESSES gives the reason for each. A t3
route needs a provider, a model and an effort. A lap limit that is not a whole number above zero is refused. The flag
is required: the manager passes it only after the human said yes. A proposal that fails a check is refused and
nothing is written.

A t3 route whose `driver` is `opencode` is the one t3 route a tier that writes can have, and only the tier whose
writing stage is the tidy alone: the tidy's batches run as T3 children in auto-accept-edits mode, where the edit tool
goes through and a shell command waits for an approval. T3 reaches OpenCode through the provider the route names, so
setup looks for nothing of OpenCode on this machine and touches none of its config. The proposal never offers one; the
human chooses it.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  success.
  1  it refused, with the reason on stderr; a refusal writes nothing.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import machine_settings
import settings_reader
import routes
import rules
import texts

SUBSCRIPTION = "subscription"
API_KEY = "api_key"
KEY_VARIABLES = {routes.NATIVE_HARNESS: ["ANTHROPIC_API_KEY"],
                 routes.CODEX_HARNESS: ["OPENAI_API_KEY", "CODEX_API_KEY"]}
SUBSCRIPTION_BUDGET = 50
API_KEY_BUDGET = 20
SUBSCRIPTION_RESERVE = 0.2
OWNED_KEYS = ("routes", "budget", "reserves", "lap_limit")
T3_CODEX_MODEL = "gpt-6.1-sol"
T3_CODEX_EFFORT = "high"
T3_EFFORT_OPTIONS = ("reasoningEffort", "effort", "variant")


class SetupError(Exception):
    """A proposal or settings that setup refuses, worded for the person who reads stderr."""


def billing_of(harness: str) -> str:
    return API_KEY if any(os.environ.get(name) for name in KEY_VARIABLES[harness]) else SUBSCRIPTION


def read_catalog(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SetupError(f"the T3 catalog {path} cannot be read as JSON: {error}") from error


def effort_option(model: dict) -> dict:
    """The option of a catalog model that sets its effort, or an empty one when the model has none."""
    options = model.get("options")
    for each in options if isinstance(options, list) else []:
        if isinstance(each, dict) and each.get("id") in T3_EFFORT_OPTIONS:
            return each
    return {}


def t3_effort_of(model: dict) -> str:
    """The effort a t3 route proposes on the model: high when the model offers it, else the model's default effort,
    else the first it offers. A model that lists no efforts gets high, because T3 accepts any model of its catalog."""
    option = effort_option(model)
    values = option.get("values")
    efforts = [each for each in values if texts.is_text(each)] if isinstance(values, list) else []
    if not efforts or T3_CODEX_EFFORT in efforts:
        return T3_CODEX_EFFORT
    default = option.get("default")
    return default if default in efforts else efforts[0]


def t3_model_of(provider: dict) -> dict:
    """The catalog model a t3 route proposes on the provider: gpt-6.1-sol when the provider lists it, else the first
    model it lists. A provider that lists none gets gpt-6.1-sol, because T3 accepts any model of its catalog."""
    models = provider.get("models")
    listed = [each for each in models if isinstance(each, dict) and texts.is_text(each.get("id"))
              ] if isinstance(models, list) else []
    for each in listed:
        if each["id"] == T3_CODEX_MODEL:
            return each
    return listed[0] if listed else {"id": T3_CODEX_MODEL}


def t3_codex_route(catalog: object) -> routes.Route | None:
    """The route for the second tier under T3, or None when the catalog offers no Codex provider that can run a
    child task. The catalog is the object T3's orchestrator_capabilities prints: a `providers` list whose entries
    hold `providerInstanceId`, `driverKind`, `canRunChildTask` and `models`, each model with its `id` and its
    `options`."""
    providers = catalog.get("providers") if isinstance(catalog, dict) else None
    if not isinstance(providers, list):
        return None
    for provider in providers:
        if (isinstance(provider, dict) and provider.get("driverKind") == routes.CODEX_HARNESS
                and provider.get("canRunChildTask") is True and texts.is_text(provider.get("providerInstanceId"))):
            model = t3_model_of(provider)
            return routes.Route(routes.T3_HARNESS, model["id"], None, t3_effort_of(model),
                                provider["providerInstanceId"], None)
    return None


def proposed_routes(codex_found: bool, catalog: object) -> dict[str, routes.Route]:
    """The route of each tier. The second tier runs on t3 when the catalog offers a Codex provider that can run a
    child task, else in codex when it is found, else on its native route. Every other tier runs on its native
    route."""
    proposed = routes.default_routes(codex_found)
    on_t3 = t3_codex_route(catalog)
    if on_t3 is not None:
        proposed[routes.SECOND_TIER] = on_t3
    return proposed


def propose(home: Path, catalog: object) -> dict:
    found = {harness: shutil.which(harness) for harness in (routes.NATIVE_HARNESS, routes.CODEX_HARNESS)}
    accounts = {harness: billing_of(harness) for harness, path in found.items()
                if harness == routes.NATIVE_HARNESS or path is not None}
    recorded = machine_settings.settings_in(home)
    claude_billing = accounts[routes.NATIVE_HARNESS]
    return {
        "found": found,
        "accounts": accounts,
        "routes": {tier: route.as_dict() for tier, route
                   in proposed_routes(found[routes.CODEX_HARNESS] is not None, catalog).items()},
        "budget": SUBSCRIPTION_BUDGET if claude_billing == SUBSCRIPTION else API_KEY_BUDGET,
        "reserves": {machine_settings.CLAUDE_ACCOUNT: SUBSCRIPTION_RESERVE} if claude_billing == SUBSCRIPTION else {},
        "lap_limit": rules.machine_lap_limit(home),
        "recorded": {key: recorded.get(key) for key in OWNED_KEYS},
    }


def check_route(tier: str, recorded: object) -> None:
    refusal = routes.Route.parse(tier, recorded).refusal(tier)
    if refusal:
        raise SetupError(refusal)


def check(confirmed: object) -> dict:
    if not isinstance(confirmed, dict):
        raise SetupError("the proposal is not a JSON object")
    for key in OWNED_KEYS:
        if key not in confirmed:
            raise SetupError(f"the proposal holds no {key}")
    if not isinstance(confirmed["routes"], dict) or not confirmed["routes"]:
        raise SetupError("routes must be an object of tier names to routes")
    for tier, route in confirmed["routes"].items():
        check_route(tier, route)
    if not rules.is_dollars(confirmed["budget"]):
        raise SetupError("budget must be a number of dollars above zero")
    if not rules.is_map_of(confirmed["reserves"], rules.is_share):
        raise SetupError("reserves must be an object of account names to a share above 0 and below 1")
    if not rules.is_positive_whole(confirmed["lap_limit"]):
        raise SetupError("lap_limit must be a whole number above zero")
    return {key: confirmed[key] for key in OWNED_KEYS}


def write(confirmed: object, home: Path) -> dict:
    owned = check(confirmed)
    settings = {**machine_settings.settings_in(home), **owned}
    machine_settings.write_settings(home, settings)
    return owned


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="setup.py", description="Propose this machine's routes, budget default, "
                                                                   "reserves and lap limit, and write them once "
                                                                   "confirmed.")
    modes = parser.add_subparsers(dest="mode", required=True)
    proposing = modes.add_parser("propose", help="print the proposal and write nothing")
    proposing.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    proposing.add_argument("--t3-catalog", help="a file that holds the JSON that T3's orchestrator_capabilities "
                                                "printed; pass it only under T3")
    writing = modes.add_parser("write", help="write the confirmed proposal, read as JSON on stdin")
    writing.add_argument("--confirmed", action="store_true", required=True,
                         help="the human confirmed the proposal")
    writing.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        home = settings_reader.jidoka_home(args.jidoka_home)
        if args.mode == "propose":
            catalog = read_catalog(Path(args.t3_catalog)) if args.t3_catalog else None
            print(json.dumps(propose(home, catalog), indent=2))
        else:
            try:
                confirmed = json.loads(sys.stdin.read())
            except ValueError as error:
                raise SetupError(f"the proposal on stdin is not JSON: {error}") from error
            print(json.dumps(write(confirmed, home), indent=2))
    except (SetupError, routes.RouteError, machine_settings.MachineSettingsError, OSError) as error:
        print(f"setup: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
