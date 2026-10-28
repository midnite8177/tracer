#!/usr/bin/env python3
"""Decides whether a stage whose route failed reruns on the native route, and records that it did.

`fallback <bead> <stage> <tier> --run <mark>` is called by the manager when the worker of a stage on the tier's route
failed. The bead is the task of a lap's stage, or the epic for a stage of a pass. The mark names the run of the stage:
the lap's number, or the pass's number. It prints one JSON object. `{"rerun": true, "route": {...}}` carries the
native route to rerun the stage on; the script has recorded that on the bead as the metadata `route.native.<stage>`,
holding the mark, and posted a comment. `{"rerun": false, "why": "..."}` says the stage stays failed, either because
the tier's route already runs natively or because this run of the stage already fell back. A new mark is a new run,
so it may fall back again. The script writes nothing when the stage does not rerun, and counts nothing against a
cap: the failed route is no try.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  it printed an answer.
  1  it refused, or a bd command failed, with the reason on stderr; a refusal writes nothing.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import repo_settings
import routes
from commands import (COMMAND_TIMEOUT_SECONDS, CommandError, bd_show, env_as_factory, metadata_of, run,
                      set_metadata)

KEY_PREFIX = "route.native."


def fallback(bead: str, stage: str, tier: str, mark: str, home: Path, main_tree: Path) -> dict:
    failed = routes.recorded_route(tier, home)
    if failed["harness"] == routes.NATIVE_HARNESS:
        return {"rerun": False, "why": f"the {tier} route already runs on {routes.NATIVE_HARNESS}, so there is "
                                       "no native route to fall back to"}
    shown = bd_show(bead, main_tree)
    if shown is None:
        raise CommandError(f"bd show printed nothing usable for {bead}")
    key = f"{KEY_PREFIX}{stage}"
    if str(metadata_of(shown).get(key) or "") == mark:
        return {"rerun": False, "why": f"the {stage} stage already fell back to {routes.NATIVE_HARNESS} in run "
                                       f"{mark}"}
    native = routes.native_route_of(tier)
    env = env_as_factory()
    run(["bd", "comment", bead, f"{stage} reruns on {routes.NATIVE_HARNESS}: the {tier} route on "
                               f"{failed['harness']} failed"], main_tree, env)
    run(["bd", "update", bead, *set_metadata((key, mark))], main_tree, env)
    return {"rerun": True, "route": native}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="route.py", description="Decide whether a failed route reruns on native.")
    modes = parser.add_subparsers(dest="mode", required=True)
    falling = modes.add_parser("fallback", help="rerun a stage whose route failed on the tier's native route")
    falling.add_argument("bead")
    falling.add_argument("stage")
    falling.add_argument("tier")
    falling.add_argument("--run", required=True, help="the lap's number, or the pass's number")
    falling.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = repo_settings.jidoka_home(args.jidoka_home)
        print(json.dumps(fallback(args.bead, args.stage, args.tier, args.run, home, main_tree)))
    except (routes.RouteError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"route: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
