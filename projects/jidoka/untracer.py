#!/usr/bin/env python3
"""Takes tracer's files out of one repo and keeps a backup of every original.

The backup goes to <jidoka-home>/untracer/<repo-key>/<timestamp>/ before
anything changes, and the script never asks for confirmation. It keeps bd's
workspace, hooks and marked block, the glossaries, the ADRs and the rules
files. docs/tracer.md goes last, because it is the file that says what
tracer installed.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PLUGIN_DIR = ".claude/skills/tracer/"
AGENTS_DOCS_DIR = "docs/agents/"
ADOPT_NOTES = "docs/tracer-adopt-notes.md"
STATUSLINE_FILES = [".claude/statusline.py", ".claude/statusline.sh"]
SEED_COPY = "docs/tracer.md"
SETTINGS_LOCAL = ".claude/settings.local.json"
EXCLUDE_FILE = ".git/info/exclude"

EXCLUDE_HEADING = "# tracer machinery (stealth)"
EXCLUDE_LINES_REMOVED = [PLUGIN_DIR, *STATUSLINE_FILES, AGENTS_DOCS_DIR, SEED_COPY, ADOPT_NOTES]

BD_BLOCK_MARKER = "BEGIN BEADS INTEGRATION"
RULES_FILES = ["AGENTS.md", "CLAUDE.md", "AGENTS.local.md", "CLAUDE.local.md"]
SKIPPED_WHEN_SEARCHING = {".git", ".beads", ".claude", "node_modules"}

USER_SETTINGS = "~/.claude/settings.json"


class UntracerError(Exception):
    pass


@dataclass(frozen=True)
class Edit:
    path: str
    summary: str


@dataclass(frozen=True)
class Plan:
    repo: Path
    deletions: list[str]
    edits: list[Edit]
    keeps: list[str]


def read_text(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def strip_tracer_exclude_lines(text: str) -> str:
    dropped = {EXCLUDE_HEADING, *EXCLUDE_LINES_REMOVED}
    kept = [line for line in text.splitlines(keepends=True) if line.rstrip("\r\n") not in dropped]
    return "".join(kept)


def parse_settings(path: Path) -> dict:
    try:
        data = json.loads(read_text(path))
    except ValueError as err:
        raise UntracerError(f"{path} is not valid JSON: {err}") from err
    if not isinstance(data, dict):
        raise UntracerError(f"{path} does not hold a JSON object")
    return data


def contains_bd_block(path: Path) -> bool:
    return path.is_file() and BD_BLOCK_MARKER in read_text(path)


def find_keeps(repo: Path) -> list[str]:
    keeps = []
    if (repo / ".beads").is_dir():
        keeps.append(".beads/")
    hooks = repo / ".git" / "hooks"
    if hooks.is_dir():
        for hook in sorted(hooks.iterdir()):
            if hook.is_file() and not hook.name.endswith(".sample") and contains_bd_block(hook):
                keeps.append(f".git/hooks/{hook.name} (bd's hook)")
    for name in RULES_FILES:
        if contains_bd_block(repo / name):
            keeps.append(f"{name} (bd's marked block)")
    if (repo / "GLOSSARY-MAP.md").is_file():
        keeps.append("GLOSSARY-MAP.md")
    glossaries, adrs = [], []
    for folder, subfolders, names in os.walk(repo):
        subfolders[:] = sorted(d for d in subfolders if d not in SKIPPED_WHEN_SEARCHING)
        relative = Path(folder).relative_to(repo).as_posix()
        prefix = "" if relative == "." else relative + "/"
        if "GLOSSARY.md" in names:
            glossaries.append(prefix + "GLOSSARY.md")
        if Path(folder).name == "adr" and Path(folder).parent.name == "docs":
            adrs.append(prefix)
    keeps += sorted(glossaries) + sorted(adrs)
    for name in RULES_FILES:
        if (repo / name).is_file():
            keeps.append(f"{name} (rules file, left for the next step)")
    if (repo / ".audit").is_dir():
        keeps.append(".audit/")
    if (repo / ".claude" / "settings.json").is_file():
        keeps.append(".claude/settings.json")
    keeps.append(f"{USER_SETTINGS} (user-wide, never touched)")
    return keeps


def find_plan(repo: Path) -> Plan:
    deletions = [path for path in [PLUGIN_DIR, AGENTS_DOCS_DIR] if (repo / path).is_dir()]
    deletions += [path for path in [ADOPT_NOTES, *STATUSLINE_FILES] if (repo / path).is_file()]
    edits = []
    settings = repo / SETTINGS_LOCAL
    if settings.is_file() and "statusLine" in parse_settings(settings):
        edits.append(Edit(SETTINGS_LOCAL, "remove the statusLine key"))
    exclude = repo / EXCLUDE_FILE
    if exclude.is_file():
        text = read_text(exclude)
        if strip_tracer_exclude_lines(text) != text:
            edits.append(Edit(EXCLUDE_FILE, "remove tracer's lines"))
    if (repo / SEED_COPY).is_file():
        deletions.append(SEED_COPY)
    return Plan(repo, deletions, edits, find_keeps(repo))


def print_plan(plan: Plan) -> None:
    print(f"Plan for {plan.repo}")
    print("Will delete:")
    for path in plan.deletions:
        print(f"  {path}")
    print("Will edit:")
    for edit in plan.edits:
        print(f"  {edit.path} ({edit.summary})")
    print("Will keep:")
    for path in plan.keeps:
        print(f"  {path}")


def repo_key(repo: Path) -> str:
    digest = hashlib.sha256(str(repo).encode("utf-8")).hexdigest()[:8]
    return f"{repo.name}-{digest}"


def files_under(repo: Path, relative: str) -> list[str]:
    path = repo / relative
    if path.is_file():
        return [relative]
    found = []
    for folder, _, names in os.walk(path):
        for name in names:
            found.append((Path(folder) / name).relative_to(repo).as_posix())
    return sorted(found)


def back_up(plan: Plan, jidoka_home: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = jidoka_home / "untracer" / repo_key(plan.repo) / stamp
    originals = []
    for path in [*plan.deletions, *(edit.path for edit in plan.edits)]:
        originals += files_under(plan.repo, path)
    for relative in originals:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plan.repo / relative, target)
    return destination


def remove_path(repo: Path, relative: str) -> None:
    path = repo / relative
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    print(f"removed {relative}")


def drop_status_line(repo: Path) -> None:
    path = repo / SETTINGS_LOCAL
    data = parse_settings(path)
    del data["statusLine"]
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"edited {SETTINGS_LOCAL}")


def drop_exclude_lines(repo: Path) -> None:
    path = repo / EXCLUDE_FILE
    write_text(path, strip_tracer_exclude_lines(read_text(path)))
    print(f"edited {EXCLUDE_FILE}")


def apply(plan: Plan) -> None:
    repo = plan.repo
    for path in plan.deletions:
        if path != SEED_COPY:
            remove_path(repo, path)
    for edit in plan.edits:
        if edit.path == SETTINGS_LOCAL:
            drop_status_line(repo)
        else:
            drop_exclude_lines(repo)
    if SEED_COPY in plan.deletions:
        remove_path(repo, SEED_COPY)


def untrace(repo: Path, jidoka_home: Path) -> None:
    if not (repo / ".git").is_dir():
        raise UntracerError(f"{repo} is not a git repository")
    plan = find_plan(repo)
    if not plan.deletions and not plan.edits:
        print(f"Nothing of tracer's was found in {repo}.")
        return
    print_plan(plan)
    backup = back_up(plan, jidoka_home)
    print(f"Backup: {backup}")
    apply(plan)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="untracer.py", description="Remove tracer's files from one repo.")
    parser.add_argument("--repo", required=True, help="the repo to take tracer out of")
    parser.add_argument("--jidoka-home", default="~/.jidoka", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    try:
        untrace(Path(args.repo).resolve(), Path(args.jidoka_home).expanduser().resolve())
    except (UntracerError, OSError, ValueError) as err:
        print(f"untracer: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
