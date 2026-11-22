#!/usr/bin/env python3
"""Proposes this machine's routes, budget default, reserves and lap limit, and writes them once confirmed.

`propose [--t3-catalog <file>]` looks at the machine and prints one JSON object, and writes nothing. The file is
T3's catalog as `orchestrator_capabilities` prints it, saved by the setup skill under T3; without it the proposal
is the one for a machine outside T3. A file that cannot be read as JSON is refused. The proposal is for the host the
script runs under, which routes.host_of_environment decides, and the routes in it are that host's table.
  host       `claude-code` or `antigravity`.
  found     the path of each harness on the PATH, or null: `claude` and `codex`.
  accounts   how each harness bills, `subscription` or `api_key`. A harness bills by API key when its key
             variable is set: ANTHROPIC_API_KEY for claude, OPENAI_API_KEY or CODEX_API_KEY for codex. Codex is
             listed only when it is found; claude is always listed, because it is the host.
  routes     a route for each tier. The second tier runs on t3 Codex when --t3-catalog names a Codex provider
             that can run a child task: on gpt-6.1-sol when the provider lists it, else on the first model it
             lists, at high effort when that model offers it, else at its default effort. Else it runs in codex
             when that is found, else on the native route of the tier. Every other tier runs on its native route.
             Under Antigravity the table is built from the catalog's Antigravity provider and never holds one of its
             Claude models: light and local run on the Hydrogen model at medium thought, standard on Neon at high,
             and deep on Carbon when the catalog lists it, else on Neon at xhigh, each as a native route, a t3 route
             with the driver `antigravity` whose model is the catalog's model id and whose effort is its thought level.
             The second tier is the route it has on Claude Code from the catalog and the PATH, else the deep route. A
             tier whose model the catalog lacks has no route.
  budget    the default budget of an epic, in dollars at list price: 50 when the claude account is a subscription,
             and 20 when it bills by API key, where the dollars are real.
  reserves   0.2 for the claude account when it is on a subscription, because only a subscription has a usage window
             to hold back, and the lap mod reads the usage of the claude account alone. An account on an API key
             has none, and no reserve is proposed for codex.
  lap_limit  the most open laps the machine allows: it caps every epic's laps, and the laps of all the running
             epics together. The one the settings hold, else 4.
  recorded   the routes, budget, reserves and lap limit the settings hold now, each null when they hold none.

`write --confirmed` reads a JSON object on stdin with `routes`, `budget`, `reserves` and `lap_limit`, the proposal as
the human confirmed or edited it, checks all four before it writes any, and puts them into <jidoka-home>/settings.json.
Every other key of the settings stays as it is, and the routes replace the stored table of the host whole, `routes`
for Claude Code and `antigravity_routes` for Antigravity, leaving the other host's table as it is. A route on codex or
t3 is refused for a tier that has a stage which writes; routes.READ_ONLY_HARNESSES gives the reason for each. A t3
route needs a provider, a model and an effort. A lap limit that is not a whole number above zero is refused. The flag
is required: the manager passes it only after the human said yes. A proposal that fails a check is refused and
nothing is written.

A t3 route whose `driver` is `opencode` is the one t3 route a tier that writes can have, and only the tier whose
writing stage is the tidy alone: the tidy's batches run as T3 children in auto-accept-edits mode, where the edit tool
goes through and a shell command waits for an approval. T3 reaches OpenCode through the provider the route names, so
setup looks for nothing of OpenCode on this machine and touches none of its config. The proposal never offers one; the
human chooses it.

`propose` also prints `t3_token`: the proposal to issue T3's read-only token, for provider status. It holds the
`command` that issues it (`t3 auth session issue --scope orchestration:read --label jidoka --ttl <long>`), `warning`
and `reads_every_thread`, because the scope can read every thread of T3, the `file` that would hold the token, and
`recorded`, whether the home holds one already. `t3` is the command's path on the PATH, or null.

`issue-token --confirmed` runs that command and saves what it prints in <jidoka-home>/t3-token, readable by the user
alone, replacing a token saved before. It prints the file's path and never the token. The flag is required: the
manager passes it only after the human said yes, and without it nothing is issued. A failed command, or one that
prints no token, saves nothing and exits 1. The t3 command is $T3CODE_CLI_PATH, else `t3` on the PATH.

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
import t3_token
import texts

SUBSCRIPTION = "subscription"
API_KEY = "api_key"
KEY_VARIABLES = {routes.NATIVE_HARNESS: ["ANTHROPIC_API_KEY"],
                 routes.CODEX_HARNESS: ["OPENAI_API_KEY", "CODEX_API_KEY"]}
SUBSCRIPTION_BUDGET = 50
API_KEY_BUDGET = 20
SUBSCRIPTION_RESERVE = 0.2
ROUTES_KEY = "routes"
OWNED_KEYS = (ROUTES_KEY, "budget", "reserves", "lap_limit")
T3_CODEX_MODEL = "gpt-6.1-sol"
T3_CODEX_EFFORT = "high"
T3_EFFORT_OPTIONS = ("reasoningEffort", "effort", "variant", "thinkingLevel", "thoughtLevel")
ANTIGRAVITY_TIER_MODELS = (("light", "hydrogen", "medium"), ("local", "hydrogen", "medium"),
                           ("standard", "neon", "high"))
ANTIGRAVITY_DEEP = (("carbon", "xhigh"), ("neon", "xhigh"))


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


def effort_of(model: dict, wanted: str) -> str:
    """The effort a t3 route proposes on the model: the wanted one when the model offers it, else the model's default
    effort, else the first it offers. A model that lists no efforts gets the wanted one, because T3 accepts any model
    of its catalog."""
    option = effort_option(model)
    values = option.get("values")
    efforts = [each for each in values if texts.is_text(each)] if isinstance(values, list) else []
    if not efforts or wanted in efforts:
        return wanted
    default = option.get("default")
    return default if default in efforts else efforts[0]


def t3_effort_of(model: dict) -> str:
    return effort_of(model, T3_CODEX_EFFORT)


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
    """The route of each tier on Claude Code. The second tier runs on t3 when the catalog offers a Codex provider
    that can run a child task, else in codex when it is found, else on its native route. Every other tier runs on its
    native route."""
    proposed = routes.default_routes(codex_found)
    on_t3 = t3_codex_route(catalog)
    if on_t3 is not None:
        proposed[routes.SECOND_TIER] = on_t3
    return proposed


def antigravity_models_of(catalog: object) -> tuple[str, list[dict]] | None:
    """The instance id and the models of the first Antigravity provider of the catalog, or None when it lists none.
    The provider need not run child tasks, because a lap worker on it is a thread."""
    providers = catalog.get("providers") if isinstance(catalog, dict) else None
    for provider in providers if isinstance(providers, list) else []:
        if (isinstance(provider, dict) and provider.get("driverKind") == routes.ANTIGRAVITY_DRIVER
                and texts.is_text(provider.get("providerInstanceId"))):
            models = provider.get("models")
            return provider["providerInstanceId"], [each for each in models if isinstance(each, dict)
                                                    and texts.is_text(each.get("id"))
                                                    ] if isinstance(models, list) else []
    return None


def antigravity_route(provider: str, models: list[dict], family: str, wanted: str) -> routes.Route | None:
    """A native Antigravity route on the first model whose id names the Gemini family, at the wanted thought level or
    the nearest the model offers, or None when the catalog lists none. A Claude model of the catalog never matches."""
    for model in models:
        if family in model["id"].lower() and "claude" not in model["id"].lower():
            return routes.Route(routes.T3_HARNESS, model["id"], None, effort_of(model, wanted), provider,
                                routes.ANTIGRAVITY_DRIVER)
    return None


def antigravity_routes(codex_found: bool, catalog: object) -> dict[str, routes.Route]:
    """The route of each tier on Antigravity: light and local on Hydrogen at medium, standard on Neon at high, deep
    on Carbon when the catalog lists it, else Neon at xhigh. The second tier is the route it has on Claude Code, on
    t3 Codex or in codex, and else the deep route. A tier whose model the catalog does not list has no route."""
    proposed: dict[str, routes.Route] = {}
    found = antigravity_models_of(catalog)
    if found is not None:
        provider, models = found
        for tier, family, wanted in ANTIGRAVITY_TIER_MODELS:
            route = antigravity_route(provider, models, family, wanted)
            if route is not None:
                proposed[tier] = route
        for family, wanted in ANTIGRAVITY_DEEP:
            route = antigravity_route(provider, models, family, wanted)
            if route is not None:
                proposed["deep"] = route
                break
    second = t3_codex_route(catalog) or (routes.default_routes(True)[routes.SECOND_TIER] if codex_found else None)
    if second is not None:
        proposed[routes.SECOND_TIER] = second
    elif "deep" in proposed:
        proposed[routes.SECOND_TIER] = proposed["deep"]
    return proposed


def propose(home: Path, catalog: object, host: str) -> dict:
    found = {harness: shutil.which(harness) for harness in (routes.NATIVE_HARNESS, routes.CODEX_HARNESS)}
    accounts = {harness: billing_of(harness) for harness, path in found.items()
                if harness == routes.NATIVE_HARNESS or path is not None}
    recorded = machine_settings.settings_in(home)
    claude_billing = accounts[routes.NATIVE_HARNESS]
    codex_found = found[routes.CODEX_HARNESS] is not None
    on_host = (antigravity_routes(codex_found, catalog) if host == routes.ANTIGRAVITY_HOST
               else proposed_routes(codex_found, catalog))
    return {
        "host": host,
        "found": found,
        "accounts": accounts,
        "routes": {tier: route.as_dict() for tier, route in on_host.items()},
        "budget": SUBSCRIPTION_BUDGET if claude_billing == SUBSCRIPTION else API_KEY_BUDGET,
        "reserves": {machine_settings.CLAUDE_ACCOUNT: SUBSCRIPTION_RESERVE} if claude_billing == SUBSCRIPTION else {},
        "lap_limit": rules.machine_lap_limit(home),
        "recorded": {key: recorded.get(routes.table_key(host) if key == ROUTES_KEY else key)
                     for key in OWNED_KEYS},
        "t3_token": proposed_token(home),
    }


def proposed_token(home: Path) -> dict:
    """What setup proposes for T3's read-only token: the command that issues it, the scope's reach, which setup says
    aloud before the human confirms, and whether the home holds a token already. The token itself is never in it."""
    t3 = shutil.which(t3_token.t3_command())
    return {
        "scope": t3_token.SCOPE,
        "label": t3_token.LABEL,
        "ttl": t3_token.TTL,
        "command": t3_token.issue_command(t3 or t3_token.t3_command()),
        "t3": t3,
        "reads_every_thread": True,
        "warning": f"The {t3_token.SCOPE} scope is the narrowest that serves T3's provider status, and it can also "
                   "read every thread in T3.",
        "file": str(t3_token.token_path(home)),
        "recorded": t3_token.read_token(home) is not None,
    }


def issue_token(home: Path) -> Path:
    """Issues the read-only token through the t3 command and saves it in the home, returning the file's path."""
    return t3_token.save_token(home, t3_token.issue(t3_token.t3_command()))


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


def write(confirmed: object, home: Path, host: str) -> dict:
    owned = check(confirmed)
    table = routes.table_key(host)
    settings = {**machine_settings.settings_in(home), **{key: value for key, value in owned.items()
                                                           if key != ROUTES_KEY},
                table: owned[ROUTES_KEY]}
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
    issuing = modes.add_parser("issue-token", help="issue T3's read-only token and save it in the jidoka home")
    issuing.add_argument("--confirmed", action="store_true", required=True,
                         help="the human confirmed that setup issues the token")
    issuing.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        home = settings_reader.jidoka_home(args.jidoka_home)
        if args.mode == "issue-token":
            print(json.dumps({"saved": str(issue_token(home)), "scope": t3_token.SCOPE, "label": t3_token.LABEL},
                             indent=2))
        elif args.mode == "propose":
            catalog = read_catalog(Path(args.t3_catalog)) if args.t3_catalog else None
            print(json.dumps(propose(home, catalog, routes.host_of_environment()), indent=2))
        else:
            try:
                confirmed = json.loads(sys.stdin.read())
            except ValueError as error:
                raise SetupError(f"the proposal on stdin is not JSON: {error}") from error
            print(json.dumps(write(confirmed, home, routes.host_of_environment()), indent=2))
    except (SetupError, routes.RouteError, machine_settings.MachineSettingsError, t3_token.TokenError,
            OSError) as error:
        print(f"setup: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
