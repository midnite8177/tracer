#!/usr/bin/env python3
"""Puts the beads workspace of the repo's main worktree in stealth mode, so git never sees it.

Run it from inside any checkout of the repo; it works on the main worktree,
whose .beads/ is the workspace every worktree reads. It takes no arguments.

With a .beads/ that git tracks, the switch takes the workspace and what plain
`bd init` commits beside it out of git, and leaves its changes staged for the
owner to commit:
  - .beads/ and .agents/skills/beads/ are untracked with `git rm -r --cached`.
  - .claude/settings.json, .codex/hooks.json and .codex/config.toml are
    untracked when they hold bd's entries alone. A file that holds anything
    else stays committed, and the script names it.
  - CLAUDE.md and AGENTS.md lose bd's marked blocks, and the edit is staged.
    One that then holds only bd's stock text, or nothing, is untracked whole.
    A block whose BEGIN line is gone runs from the last `## Beads Issue
    Tracker` heading above its END line. One with no such heading stays,
    and the script names the file.
Every untracked file stays on disk and gets an info/exclude line, so bd
keeps every bead. The script refuses, naming the paths, while the index
holds staged changes to other files, so its changes are the only staged
ones. It also refuses while a rules file it would edit has changes that are
not staged.

In a clone that pulled the commit holding that removal, it writes back the
files the commit untracked, from the commit before it, and only those
missing on disk, then excludes them all. When git does not track the
workspace and it has no beads database, the script runs `bd bootstrap
--yes` if origin holds Dolt data at refs/dolt/data. Without that data it
makes no database, since bootstrap would make an empty one, and prints the
commands that push the beads from the machine that has them. With no .beads/ at all
it runs `bd init --stealth --non-interactive`. A run that finds nothing to
do writes nothing and says the workspace is already in stealth mode. It
never pushes Dolt data, never commits, never rewrites git history and
never reruns bd init on an existing workspace. The repo's .gitignore and
core.hooksPath stay as they are.

Exit codes:
  0  the workspace is in stealth mode.
  1  it refused, or a git or bd command failed, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import bd_files
import git_exclude
import repo_settings
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, capture, run

WORKSPACE = ".beads"
DOLT_DATA = "refs/dolt/data"


class StealthError(Exception):
    """A reason the script changes nothing, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Switch:
    untracked: list[str]
    rewritten_rules: dict[str, str]
    kept_hook_files: list[str]
    kept_rules: list[str]


def tracked_files(main_tree: Path, path: str) -> list[str]:
    return run(["git", "ls-files", "--", path], main_tree, None).splitlines()


def blob(main_tree: Path, revision_path: str) -> bytes:
    """The bytes git holds for `<revision>:<path>`, or for `:<path>` in the index, with no newline translation."""
    try:
        done = subprocess.run(["git", "show", revision_path], cwd=main_tree, capture_output=True,
                              timeout=COMMAND_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        raise CommandError(f"git show {revision_path} could not run: {error}") from error
    if done.returncode != 0:
        raise CommandError(f"git show {revision_path} failed: {done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout


def staged_text(main_tree: Path, path: str) -> str:
    return blob(main_tree, f":{path}").decode("utf-8", errors="replace")


def disk_text(main_tree: Path, path: str) -> str | None:
    file = main_tree / path
    if not file.is_file():
        return None
    with open(file, encoding="utf-8", errors="replace", newline="") as handle:
        return handle.read()


def stealth_line(path: str) -> str:
    """The exclude line for a path the switch untracks.

    The workspace keeps the unanchored line that bd init writes, so a workspace bd made is already excluded.
    """
    if path == WORKSPACE:
        return f"{WORKSPACE}/"
    return git_exclude.exclude_line(path, folder=path == bd_files.SKILL_FOLDER)


def plan_switch(main_tree: Path) -> Switch:
    untracked = [WORKSPACE]
    rewritten_rules: dict[str, str] = {}
    kept_hook_files: list[str] = []
    kept_rules: list[str] = []
    if tracked_files(main_tree, bd_files.SKILL_FOLDER):
        untracked.append(bd_files.SKILL_FOLDER)
    for path in bd_files.HOOK_FILES:
        if not tracked_files(main_tree, path):
            continue
        texts = [staged_text(main_tree, path), disk_text(main_tree, path)]
        if all(text is not None and bd_files.is_bd_hook_file(path, text) for text in texts):
            untracked.append(path)
        else:
            kept_hook_files.append(path)
    for path in bd_files.RULES_FILES:
        if not tracked_files(main_tree, path):
            continue
        staged, on_disk = staged_text(main_tree, path), disk_text(main_tree, path)
        if bd_files.has_end_line(bd_files.without_blocks(staged)):
            kept_rules.append(path)
        if not bd_files.has_blocks(staged) and not (on_disk and bd_files.has_blocks(on_disk)):
            continue
        if on_disk != staged:
            raise StealthError(f"{path} holds bd's blocks and changes that are not staged, and the switch "
                               f"edits it. Stage, stash or undo the changes to {path} first")
        if bd_files.is_stock_rules(path, staged):
            untracked.append(path)
        else:
            rewritten_rules[path] = bd_files.without_blocks(staged)
    return Switch(untracked, rewritten_rules, kept_hook_files, kept_rules)


def refuse_other_staged_changes(main_tree: Path, touched: list[str]) -> None:
    staged = run(["git", "diff", "--cached", "--name-only", "-z"], main_tree, None).split("\0")
    others = [path for path in staged
              if path and not any(path == own or path.startswith(f"{own}/") for own in touched)]
    if others:
        raise StealthError("the index holds staged changes outside the files the switch changes, and the switch "
                           "stages only its own changes. Commit or unstage these first:\n"
                           + "\n".join(f"  {path}" for path in others))


def exclude(main_tree: Path, paths: list[str]) -> list[str]:
    file = git_exclude.exclude_file(main_tree)
    added = git_exclude.add(file, [stealth_line(path) for path in paths])
    return [f"added {', '.join(added)} to {file}"] if added else []


def switch(main_tree: Path) -> list[str]:
    plan = plan_switch(main_tree)
    refuse_other_staged_changes(main_tree, plan.untracked + list(plan.rewritten_rules))
    run(["git", "rm", "-r", "-q", "--cached", "--", *plan.untracked], main_tree, None)
    done = [f"untracked {', '.join(stealth_line(path).lstrip('/') for path in plan.untracked)} and staged the "
            "removal; the files stay on disk, and the commit is yours"]
    for path, text in plan.rewritten_rules.items():
        with open(main_tree / path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        run(["git", "add", "--", path], main_tree, None)
        done.append(f"took bd's blocks out of {path} and staged the edit")
    done += [f"still committed with bd's entries: {path}" for path in plan.kept_hook_files]
    done += [f"still committed with bd's blocks: {path}" for path in plan.kept_rules]
    return done + exclude(main_tree, plan.untracked)


def switch_commit(main_tree: Path) -> str | None:
    """The commit that took the workspace out of git: the latest that deleted files under it and left none tracked."""
    found = capture(["git", "log", "-1", "--format=%H", "--diff-filter=D", "--", WORKSPACE], main_tree, None)
    commit = found.stdout.strip() if found.returncode == 0 else ""
    if not commit or run(["git", "ls-tree", "-r", "--name-only", commit, "--", WORKSPACE], main_tree, None).strip():
        return None
    return commit


def untracked_root(path: str) -> str:
    for folder in (WORKSPACE, bd_files.SKILL_FOLDER):
        if path.startswith(f"{folder}/"):
            return folder
    return path


def write_blob(main_tree: Path, commit: str, mode: str, path: str) -> None:
    content = blob(main_tree, f"{commit}:{path}")
    target = main_tree / path
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode == "120000":
        os.symlink(content.decode("utf-8"), target)
        return
    target.write_bytes(content)
    if mode == "100755":
        target.chmod(0o755)


def restore(main_tree: Path) -> list[str]:
    """Writes back the files the switch commit untracked that this checkout lacks, and excludes all of them."""
    commit = switch_commit(main_tree)
    if commit is None:
        return []
    handled = [WORKSPACE, bd_files.SKILL_FOLDER, *bd_files.HOOK_FILES, *bd_files.RULES_FILES]
    deleted = [path for path in run(["git", "diff", "--name-only", "-z", "--diff-filter=D", f"{commit}^", commit,
                                     "--", *handled], main_tree, None).split("\0") if path]
    missing = [path for path in deleted if not os.path.lexists(main_tree / path)]
    done = []
    if missing:
        listing = run(["git", "ls-tree", "-z", f"{commit}^", "--", *missing], main_tree, None).split("\0")
        modes = {entry.split("\t", 1)[1]: entry.split(" ", 1)[0] for entry in listing if entry}
        for path in missing:
            write_blob(main_tree, f"{commit}^", modes[path], path)
        done.append(f"restored {len(missing)} files that {commit[:12]} took out of git, from the commit "
                    f"before it: {', '.join(missing)}")
    return done + exclude(main_tree, [untracked_root(path) for path in deleted])


def has_database(main_tree: Path) -> bool:
    """Whether bd finds a beads database in the workspace; `bd where --json` names one only when it exists."""
    return "database_path" in json.loads(run(["bd", "where", "--json"], main_tree, None))


def fetch_database(main_tree: Path) -> list[str]:
    """Makes the workspace's database from the Dolt data on origin, or says how to put it there.

    Without Dolt data on origin, bd bootstrap would make an empty database, so the script makes none.
    """
    if not run(["git", "ls-remote", "origin", DOLT_DATA], main_tree, None).strip():
        url = run(["git", "remote", "get-url", "origin"], main_tree, None).strip()
        return [f"there is no beads database in {main_tree / WORKSPACE}, and origin holds no Dolt data to make "
                f"one from. On the machine that has the beads, run `bd dolt remote add origin {url}` and "
                "`bd dolt push`, then run this script here again"]
    run(["bd", "bootstrap", "--yes"], main_tree, None)
    beads = json.loads(run(["bd", "list", "--all", "--limit", "0", "--json"], main_tree, None) or "[]")
    return [f"made the beads database from the Dolt data on origin with bd bootstrap; bd now lists "
            f"{len(beads)} beads"]


def make_stealth(main_tree: Path) -> list[str]:
    """Brings the workspace into stealth mode and returns one line for each thing it did."""
    if tracked_files(main_tree, WORKSPACE):
        return switch(main_tree)
    done = restore(main_tree)
    if not (main_tree / WORKSPACE).exists():
        run(["bd", "init", "--stealth", "--non-interactive"], main_tree, None)
        return [f"made a stealth beads workspace in {main_tree / WORKSPACE}"]
    done += exclude(main_tree, [WORKSPACE])
    if not has_database(main_tree):
        return done + fetch_database(main_tree)
    return done or [f"the beads workspace in {main_tree / WORKSPACE} is already in stealth mode"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="beads_stealth.py",
                                     description="Put the beads workspace of the repo of the cwd in stealth mode.")
    parser.parse_args(argv)
    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        for line in make_stealth(main_tree):
            print(line)
    except (StealthError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"beads_stealth: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
