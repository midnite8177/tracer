#!/usr/bin/env python3
"""Raises the plugin's version and commits the change, nothing else.

The version lives in one place, the plugin's own manifest, and the
installer reads it from there. The script refuses while the plugin folder
has uncommitted changes, so the release commit holds only the bump.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys

from install import PLUGIN_FOLDER, PLUGIN_MANIFEST, InstallerError, git_run, read_version, refuse_if_dirty

VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_version(text: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.match(text)
    if match is None:
        raise InstallerError(f"{text!r} is not a version of three numbers, such as 1.4.0")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def bumped(current: tuple[int, int, int], kind: str) -> tuple[int, int, int]:
    major, minor, patch = current
    if kind == "major":
        return major + 1, 0, 0
    if kind == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def release(bump: str | None, version: str | None) -> str:
    git = shutil.which("git")
    if git is None:
        raise InstallerError("`git` is missing from the PATH")
    refuse_if_dirty(git, PLUGIN_FOLDER)
    current = parse_version(read_version(PLUGIN_FOLDER))
    new = bumped(current, bump) if bump is not None else parse_version(version or "")
    if new <= current:
        raise InstallerError(f"the new version must be higher than the current {'.'.join(map(str, current))}")
    text = ".".join(str(part) for part in new)
    manifest = PLUGIN_FOLDER / PLUGIN_MANIFEST
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["version"] = text
    manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    committed = git_run(git, PLUGIN_FOLDER, ["commit", "-m", f"Release jidoka plugin {text}", "--", str(manifest)])
    if committed.returncode != 0:
        raise InstallerError(f"git commit failed: {committed.stderr.strip() or committed.stdout.strip()}")
    return text


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="release.py", description="Raise the plugin version and commit it.")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--bump", choices=["major", "minor", "patch"], help="raise one part of the current version")
    choice.add_argument("--version", help="set the version, which must be higher than the current one")
    args = parser.parse_args(argv)
    try:
        print(release(args.bump, args.version))
    except (InstallerError, OSError, ValueError) as err:
        print(f"release.py: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
