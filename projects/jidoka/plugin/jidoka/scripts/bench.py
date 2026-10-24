#!/usr/bin/env python3
"""Starts, ends and releases bench work on one bead, and prints the route of a tier.

Run it from inside any checkout of the repo. The bench works under the git
user.name of the repo: the script claims the bead and writes its comments
with BEADS_ACTOR set to that name, whatever BEADS_ACTOR the caller has.

`start <bead>` refuses an epic, which covers milestones and maps, a task
under an epic that carries the factory label, and a bead someone else has
claimed. It makes the bead's worktree at <main checkout>/.worktrees/<slug>
on the branch bench/<slug>, cut from main's head, and only then claims the
bead, so a failed worktree step leaves the bead unclaimed. The slug comes
from the bead's title. The script adds `.worktrees/` to the repo's
info/exclude, so the worktree never shows in the main checkout's git
status. It records the branch, the worktree and the sha the branch was cut
from as the bead's bench.branch, bench.worktree and bench.start metadata,
and a later start reuses them while the recorded branch exists. It posts
`bench started at <sha> on <branch>` and prints the bead, branch, worktree
and start sha as one JSON object.

`end <bead> <outcome>` posts `bench ended: <outcome>` on the bead.

`release <bead>` sets the bead open with no assignee. It leaves the
worktree, the branch, their commits and the bench metadata for the next
start.

`route <tier>` prints the tier's route from <jidoka-home>/settings.json as
one JSON object. The home is --jidoka-home, else $JIDOKA_HOME, else
~/.jidoka.

Exit codes:
  0  success.
  1  it refused, or a git or bd command failed, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import repo_settings
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, bd_show, capture, head_of, run, worktree_list

MAIN_REF = "refs/heads/main"
WORKTREE_FOLDER = ".worktrees"
BRANCH_PREFIX = "bench/"
SLUG_LIMIT = 50
CONTAINER_TYPES = {"epic"}
FACTORY_LABEL = "factory"


class BenchError(Exception):
    """A reason the script does nothing more, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Bead:
    """The fields of a bead that the bench reads, with an empty string for one the bead lacks."""
    id: str
    title: str
    issue_type: str
    assignee: str
    labels: tuple[str, ...]
    parent: str
    recorded_branch: str
    recorded_worktree: str
    recorded_start: str


@dataclass(frozen=True)
class Workspace:
    """The branch and worktree of one bead's bench work, and the main sha the branch was cut from."""
    branch: str
    worktree: Path
    start: str


def slug(title: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return words[:SLUG_LIMIT].rstrip("-")


def parent_of(shown: dict) -> str:
    """The bead's parent id, from bd's parent field or else its parent-child dependency."""
    if shown.get("parent"):
        return str(shown["parent"])
    for link in shown.get("dependencies") or []:
        if isinstance(link, dict) and link.get("dependency_type") == "parent-child" and link.get("id"):
            return str(link["id"])
    return ""


def bead_of(bead: str, main_tree: Path) -> Bead:
    shown = bd_show(bead, main_tree)
    if shown is None:
        raise BenchError(f"bd show printed nothing usable for {bead}")
    metadata = shown.get("metadata") or {}
    return Bead(id=str(shown.get("id") or bead),
                title=str(shown.get("title") or ""),
                issue_type=str(shown.get("issue_type") or ""),
                assignee=str(shown.get("assignee") or ""),
                labels=tuple(str(label) for label in shown.get("labels") or []),
                parent=parent_of(shown),
                recorded_branch=str(metadata.get("bench.branch") or ""),
                recorded_worktree=str(metadata.get("bench.worktree") or ""),
                recorded_start=str(metadata.get("bench.start") or ""))


def env_as_git_user(main_tree: Path) -> dict[str, str]:
    """The environment bd runs in, with BEADS_ACTOR set to the repo's git user.name."""
    name = capture(["git", "config", "user.name"], main_tree, None).stdout.strip()
    if not name:
        raise BenchError(f"git config user.name is not set in {main_tree}, and the bench claims beads "
                         "under that name. Set it with git config user.name \"<your name>\"")
    return {**os.environ, "BEADS_ACTOR": name}


def exists(ref: str, main_tree: Path) -> bool:
    return head_of(ref, main_tree) is not None


def main_head(main_tree: Path) -> str:
    head = head_of(MAIN_REF, main_tree)
    if head is None:
        raise BenchError("the repo has no main branch to cut the bench branch from")
    return head


def hide_worktrees(main_tree: Path) -> None:
    common = run(["git", "rev-parse", "--git-common-dir"], main_tree, None).strip()
    exclude = (main_tree / common).resolve() / "info" / "exclude"
    line = f"{WORKTREE_FOLDER}/"
    text = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    if line in (held.strip() for held in text.splitlines()):
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if text == "" or text.endswith("\n") else "\n"
    with open(exclude, "a", encoding="utf-8", newline="") as handle:
        handle.write(f"{separator}{line}\n")


def worktree_branches(main_tree: Path) -> dict[Path, str]:
    """Each worktree of the repo, with the branch it has checked out, or an empty string when it has none."""
    return {tree.path.resolve(): tree.branch for tree in worktree_list(main_tree)}


def planned_workspace(bead: Bead, main_tree: Path) -> Workspace:
    """The workspace the bead's metadata records, or a new one named from its title."""
    if (bead.recorded_branch and bead.recorded_worktree and bead.recorded_start
            and exists(f"refs/heads/{bead.recorded_branch}", main_tree)):
        return Workspace(bead.recorded_branch, Path(bead.recorded_worktree), bead.recorded_start)
    name = slug(bead.title)
    if not name:
        raise BenchError(f"the title of {bead.id} has no letters or digits to name its branch from")
    branch = f"{BRANCH_PREFIX}{name}"
    if exists(f"refs/heads/{branch}", main_tree):
        raise BenchError(f"the branch {branch} already exists and {bead.id} does not record it. "
                         "Retitle the bead or delete the branch")
    return Workspace(branch, main_tree / WORKTREE_FOLDER / name, main_head(main_tree))


def make_worktree(workspace: Workspace, main_tree: Path) -> None:
    checked_out = worktree_branches(main_tree)
    path = workspace.worktree.resolve()
    if path in checked_out:
        if checked_out[path] != workspace.branch:
            raise BenchError(f"{path} has {checked_out[path] or 'no branch'} checked out, not {workspace.branch}")
        return
    if path.exists():
        raise BenchError(f"{path} exists and is not a worktree of the repo. Move it aside and start again")
    if exists(f"refs/heads/{workspace.branch}", main_tree):
        run(["git", "worktree", "add", "-q", str(path), workspace.branch], main_tree, None)
    else:
        run(["git", "worktree", "add", "-q", "-b", workspace.branch, str(path), workspace.start], main_tree, None)


def refuse_factory_epic(bead: Bead, main_tree: Path) -> None:
    if not bead.parent:
        return
    epic = bead_of(bead.parent, main_tree)
    if FACTORY_LABEL in epic.labels:
        raise BenchError(f"{bead.id} is under {epic.id}, which carries the {FACTORY_LABEL} label. Work on a "
                         "factory epic merges into the epic's branch, and the bench only lands on main")


def start(bead_id: str, main_tree: Path) -> Workspace:
    bead = bead_of(bead_id, main_tree)
    if bead.issue_type in CONTAINER_TYPES:
        raise BenchError(f"{bead.id} is an epic, which holds work and is never built. Bench one of its tasks")
    refuse_factory_epic(bead, main_tree)
    env = env_as_git_user(main_tree)
    if bead.assignee and bead.assignee != env["BEADS_ACTOR"]:
        raise BenchError(f"{bead.id} is claimed by {bead.assignee}. Bench it after they release it")
    workspace = planned_workspace(bead, main_tree)
    hide_worktrees(main_tree)
    make_worktree(workspace, main_tree)
    run(["bd", "update", bead.id, "--claim"], main_tree, env)
    run(["bd", "update", bead.id,
         "--set-metadata", f"bench.branch={workspace.branch}",
         "--set-metadata", f"bench.worktree={workspace.worktree}",
         "--set-metadata", f"bench.start={workspace.start}"], main_tree, env)
    run(["bd", "comment", bead.id, f"bench started at {workspace.start} on {workspace.branch}"], main_tree, env)
    return workspace


def end(bead: str, outcome: str, main_tree: Path) -> None:
    if not outcome.strip():
        raise BenchError("the outcome is empty")
    env = env_as_git_user(main_tree)
    run(["bd", "comment", bead, f"bench ended: {outcome}"], main_tree, env)


def release(bead: str, main_tree: Path) -> None:
    env = env_as_git_user(main_tree)
    run(["bd", "update", bead, "--status=open", "--assignee="], main_tree, env)


def route(tier: str, home: Path) -> dict:
    path = home / "settings.json"
    rerun = "Run install.py from your jidoka checkout to record this machine's routes"
    if not path.is_file():
        raise BenchError(f"{path} does not exist. {rerun}")
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise BenchError(f"{path} is not valid JSON: {error}") from error
    routes = settings.get("routes") if isinstance(settings, dict) else None
    found = routes.get(tier) if isinstance(routes, dict) else None
    if not isinstance(found, dict) or not found.get("harness"):
        raise BenchError(f"{path} holds no route for the tier {tier!r}. {rerun}")
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="bench.py", description="Start, end or release bench work on a bead, "
                                                                   "or print a tier's route.")
    modes = parser.add_subparsers(dest="mode", required=True)
    starting = modes.add_parser("start", help="claim the bead and make or reuse its worktree")
    starting.add_argument("bead")
    ending = modes.add_parser("end", help="post the outcome of the bench work on the bead")
    ending.add_argument("bead")
    ending.add_argument("outcome")
    releasing = modes.add_parser("release", help="set the bead open with no assignee, keeping its worktree")
    releasing.add_argument("bead")
    routing = modes.add_parser("route", help="print the route of a tier")
    routing.add_argument("tier")
    routing.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        if args.mode == "route":
            print(json.dumps(route(args.tier, repo_settings.jidoka_home(args.jidoka_home))))
            return 0
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        if args.mode == "start":
            workspace = start(args.bead, main_tree)
            print(json.dumps({"bead": args.bead, "branch": workspace.branch,
                              "worktree": str(workspace.worktree), "start": workspace.start}))
        elif args.mode == "end":
            end(args.bead, args.outcome, main_tree)
        else:
            release(args.bead, main_tree)
    except (BenchError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"bench: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
