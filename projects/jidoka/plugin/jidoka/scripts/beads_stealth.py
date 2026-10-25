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
Every untracked file stays on disk and gets an info/exclude line, so bd
keeps every bead. The script refuses, naming the paths, while the index
holds staged changes to other files, so its changes are the only staged
ones. It also refuses while a rules file it would edit has changes that are
not staged.

In a clone that pulled the commit holding that removal, it writes back the
files the commit untracked, from the commit before it, and only those
missing on disk, then excludes them all. With no .beads/ at all it runs
`bd init --stealth --non-interactive`. A run that finds nothing to do writes
nothing and says the workspace is already in stealth mode. It never commits,
never rewrites git history and never reruns bd init on an existing
workspace. The repo's .gitignore and core.hooksPath stay as they are.

Exit codes:
  0  the workspace is in stealth mode.
  1  it refused, or a git or bd command failed, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import bd_files
import repo_settings
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, capture, run

WORKSPACE = ".beads"


class StealthError(Exception):
    """A reason the script changes nothing, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Switch:
    untracked: list[str]
    rewritten_rules: dict[str, str]
    kept_hook_files: list[str]


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


def exclude_line(path: str) -> str:
    """The info/exclude line that hides an untracked path, anchored at the repo root except for the workspace."""
    return f"{WORKSPACE}/" if path == WORKSPACE else f"/{path}/" if path == bd_files.SKILL_FOLDER else f"/{path}"


def plan_switch(main_tree: Path) -> Switch:
    untracked = [WORKSPACE]
    rewritten_rules: dict[str, str] = {}
    kept_hook_files: list[str] = []
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
        if not bd_files.has_blocks(staged) and not (on_disk and bd_files.has_blocks(on_disk)):
            continue
        if on_disk != staged:
            raise StealthError(f"{path} holds bd's blocks and changes that are not staged, and the switch "
                               f"edits it. Stage, stash or undo the changes to {path} first")
        if bd_files.is_stock_rules(path, staged):
            untracked.append(path)
        else:
            rewritten_rules[path] = bd_files.without_blocks(staged)
    return Switch(untracked, rewritten_rules, kept_hook_files)


def refuse_other_staged_changes(main_tree: Path, touched: list[str]) -> None:
    staged = run(["git", "diff", "--cached", "--name-only", "-z"], main_tree, None).split("\0")
    others = [path for path in staged
              if path and not any(path == own or path.startswith(f"{own}/") for own in touched)]
    if others:
        raise StealthError("the index holds staged changes outside the files the switch changes, and the switch "
                           "stages only its own changes. Commit or unstage these first:\n"
                           + "\n".join(f"  {path}" for path in others))


def exclude_file(main_tree: Path) -> Path:
    """The repo's info/exclude, which a linked worktree shares with the main one."""
    named = run(["git", "rev-parse", "--git-path", "info/exclude"], main_tree, None).strip()
    return (main_tree / named).resolve()


def exclude(main_tree: Path, paths: list[str]) -> list[str]:
    file = exclude_file(main_tree)
    text = file.read_text(encoding="utf-8") if file.is_file() else ""
    held = {line.strip() for line in text.splitlines()}
    missing = [line for line in dict.fromkeys(map(exclude_line, paths)) if line not in held]
    if not missing:
        return []
    file.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if text == "" or text.endswith("\n") else "\n"
    with open(file, "a", encoding="utf-8", newline="") as handle:
        handle.write(separator + "".join(f"{line}\n" for line in missing))
    return [f"added {', '.join(missing)} to {file}"]


def switch(main_tree: Path) -> list[str]:
    plan = plan_switch(main_tree)
    refuse_other_staged_changes(main_tree, plan.untracked + list(plan.rewritten_rules))
    run(["git", "rm", "-r", "-q", "--cached", "--", *plan.untracked], main_tree, None)
    done = [f"untracked {', '.join(exclude_line(path).lstrip('/') for path in plan.untracked)} and staged the "
            "removal; the files stay on disk, and the commit is yours"]
    for path, text in plan.rewritten_rules.items():
        with open(main_tree / path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        run(["git", "add", "--", path], main_tree, None)
        done.append(f"took bd's blocks out of {path} and staged the edit")
    done += [f"still committed with bd's entries: {path}" for path in plan.kept_hook_files]
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


def make_stealth(main_tree: Path) -> list[str]:
    """Brings the workspace into stealth mode and returns one line for each thing it did."""
    if tracked_files(main_tree, WORKSPACE):
        return switch(main_tree)
    done = restore(main_tree)
    if not (main_tree / WORKSPACE).exists():
        run(["bd", "init", "--stealth", "--non-interactive"], main_tree, None)
        return [f"made a stealth beads workspace in {main_tree / WORKSPACE}"]
    done += exclude(main_tree, [WORKSPACE])
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
