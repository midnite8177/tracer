#!/usr/bin/env python3
"""Proposes this machine's routes, budget default and reserves, and writes them once the human has confirmed.

`propose` looks at the machine and prints one JSON object, and writes nothing:
  found      the path of each harness on the PATH, or null: `claude` and `codex`.
  accounts   how each harness bills, `subscription` or `api_key`. A harness bills by API key when its key
             variable is set: ANTHROPIC_API_KEY for claude, OPENAI_API_KEY or CODEX_API_KEY for codex. Codex is
             listed only when it is found; claude is always listed, because it is the host.
  routes     a route for each tier. The second tier runs in codex when it is found, else on the native route of the
             tier, and every other tier runs on its native route.
  budget     the default budget of an epic, in dollars at list price: 50 when the claude account is a subscription,
             and 20 when it bills by API key, where the dollars are real.
  reserves   0.2 for the claude account when it is on a subscription, because only a subscription has a usage window
             to hold back, and the lap mod reads the usage of the claude account alone. An account on an API key
             has none, and no reserve is proposed for codex.
  recorded   the routes, budget and reserves the settings hold now, each null when they hold none.

`write --confirmed` reads a JSON object on stdin with `routes`, `budget` and `reserves`, the proposal as the human
confirmed or edited it, checks all three before it writes any, and puts them into <jidoka-home>/settings.json. Every
other key of the settings stays as it is, and the routes replace the stored ones whole. The flag is required: the
manager passes it only after the human said yes. A proposal that fails a check is refused and nothing is written.

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

import repo_settings
import routes
import rules

SUBSCRIPTION = "subscription"
API_KEY = "api_key"
KEY_VARIABLES = {routes.NATIVE_HARNESS: ["ANTHROPIC_API_KEY"],
                 routes.CODEX_HARNESS: ["OPENAI_API_KEY", "CODEX_API_KEY"]}
SUBSCRIPTION_BUDGET = 50
API_KEY_BUDGET = 20
SUBSCRIPTION_RESERVE = 0.2
OWNED_KEYS = ("routes", "budget", "reserves")


class SetupError(Exception):
    """A proposal or settings that setup refuses, worded for the person who reads stderr."""


def billing_of(harness: str) -> str:
    return API_KEY if any(os.environ.get(name) for name in KEY_VARIABLES[harness]) else SUBSCRIPTION


def propose(home: Path) -> dict:
    found = {harness: shutil.which(harness) for harness in (routes.NATIVE_HARNESS, routes.CODEX_HARNESS)}
    accounts = {harness: billing_of(harness) for harness, path in found.items()
                if harness == routes.NATIVE_HARNESS or path is not None}
    recorded = routes.settings_in(home)
    claude_billing = accounts[routes.NATIVE_HARNESS]
    return {
        "found": found,
        "accounts": accounts,
        "routes": routes.default_routes(found[routes.CODEX_HARNESS] is not None),
        "budget": SUBSCRIPTION_BUDGET if claude_billing == SUBSCRIPTION else API_KEY_BUDGET,
        "reserves": {routes.NATIVE_HARNESS: SUBSCRIPTION_RESERVE} if claude_billing == SUBSCRIPTION else {},
        "recorded": {key: recorded.get(key) for key in OWNED_KEYS},
    }


def check_route(tier: str, route: object) -> None:
    if not isinstance(route, dict) or not rules.is_text(route.get("harness")):
        raise SetupError(f"the route of the tier {tier!r} needs a harness")
    for field in ("model", "version", "effort"):
        if route.get(field) is not None and not rules.is_text(route[field]):
            raise SetupError(f"the {field} of the route of the tier {tier!r} must be text or null")


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
    return {key: confirmed[key] for key in OWNED_KEYS}


def write(confirmed: object, home: Path) -> dict:
    owned = check(confirmed)
    settings = {**routes.settings_in(home), **owned}
    routes.write_in_home(home, routes.SETTINGS_FILE, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    return owned


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="setup.py", description="Propose this machine's routes, budget default "
                                                                   "and reserves, and write them once confirmed.")
    modes = parser.add_subparsers(dest="mode", required=True)
    proposing = modes.add_parser("propose", help="print the proposal and write nothing")
    proposing.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    writing = modes.add_parser("write", help="write the confirmed proposal, read as JSON on stdin")
    writing.add_argument("--confirmed", action="store_true", required=True,
                         help="the human confirmed the proposal")
    writing.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        home = repo_settings.jidoka_home(args.jidoka_home)
        if args.mode == "propose":
            print(json.dumps(propose(home), indent=2))
        else:
            try:
                confirmed = json.loads(sys.stdin.read())
            except ValueError as error:
                raise SetupError(f"the proposal on stdin is not JSON: {error}") from error
            print(json.dumps(write(confirmed, home), indent=2))
    except (SetupError, routes.RouteError, OSError) as error:
        print(f"setup: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
