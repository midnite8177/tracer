"""Builds throwaway repos that carry a tracer install, for the untracer tests.

The plugin's native files and the seed copy at docs/tracer.md come from this
repository's git history. The statusline.sh, adopt notes, settings file and
upstream skills are written by hand as stand-ins. Nothing is cloned or
fetched.
"""
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

INSTALLED = "projects/tracer-seed/src/installed"

EXCLUDE_HEADING = "# tracer machinery (stealth)"
EXCLUDE_MACHINERY = [
    ".claude/skills/tracer/",
    ".claude/statusline.py",
    ".claude/statusline.sh",
    "docs/agents/",
    "docs/tracer.md",
    "AGENTS.local.md",
    "CLAUDE.local.md",
    "docs/tracer-adopt-notes.md",
    ".audit/",
]


class FixtureError(Exception):
    pass


@dataclass(frozen=True)
class Revision:
    number: int
    seed_commit: str
    seed_path: str
    native_commit: str
    plugin_version: str


REVISIONS = {
    42: Revision(42, "03be712", "docs/seeds/tracer/tracer.md", "4ed3390", "1.3.1+tracer.42"),
    38: Revision(38, "d5674c3", "docs/seeds/tracer/tracer.md", "4ed3390", "1.3.0-pre.d81f3a1+tracer.38"),
}


def run(args: list, cwd: Path) -> str:
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise FixtureError(f"{' '.join(args)} failed in {cwd}: {done.stderr.strip()}")
    return done.stdout


def git_show(commit: str, path: str) -> bytes:
    done = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPO_ROOT, capture_output=True)
    if done.returncode != 0:
        raise FixtureError(
            f"cannot read {path} at {commit} from the git history of {REPO_ROOT}: "
            f"{done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout


def native_files(commit: str) -> list:
    listing = run(["git", "ls-tree", "-r", "--name-only", commit, INSTALLED], REPO_ROOT)
    paths = [line for line in listing.splitlines() if line]
    if not paths:
        raise FixtureError(f"no installed files at {commit} in the git history of {REPO_ROOT}")
    return paths


def target_of(source_path: str) -> str:
    relative = source_path[len(INSTALLED) + 1:]
    if relative.startswith("plugin/"):
        return ".claude/skills/tracer/" + relative[len("plugin/"):]
    if relative == "statusline.py":
        return ".claude/statusline.py"
    return relative


def write_bytes(root: Path, relative: str, data: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_text(root: Path, relative: str, text: str) -> None:
    write_bytes(root, relative, text.encode("utf-8"))


def install_tracer(repo: Path, revision: int) -> None:
    """Writes the files tracer's adopt leaves in a repo at the given seed revision."""
    rev = REVISIONS[revision]
    for source in native_files(rev.native_commit):
        write_bytes(repo, target_of(source), git_show(rev.native_commit, source))
    write_bytes(repo, "docs/tracer.md", git_show(rev.seed_commit, rev.seed_path))
    write_text(repo, ".claude/skills/tracer/.claude-plugin/plugin.json",
               json.dumps({"name": "tracer", "version": rev.plugin_version}, indent=2) + "\n")
    write_text(repo, ".claude/skills/tracer/skills/tdd/SKILL.md", "# tdd\n\nStand-in for the upstream skill.\n")
    write_text(repo, ".claude/skills/tracer/skills/grilling/SKILL.md", "# grilling\n\nStand-in for the upstream skill.\n")
    write_text(repo, ".claude/statusline.sh", "#!/bin/sh\necho tracer\n")
    write_text(repo, "docs/tracer-adopt-notes.md", "# Adopt notes\n\nWhat adopt did here.\n")
    write_text(repo, "AGENTS.local.md", "# AGENTS\n\nTracer's rules.\n")
    write_text(repo, "CLAUDE.local.md", "@AGENTS.local.md\n")
    write_text(repo, ".audit/trail.tsv", "step\tresult\n")
    write_text(repo, ".claude/settings.local.json", json.dumps({
        "permissions": {"allow": ["Bash(bd:*)"]},
        "statusLine": {"type": "command", "command": "python3 .claude/statusline.py", "refreshInterval": 1},
        "env": {"EXAMPLE": "1"},
    }, indent=2) + "\n")
    with open(repo / ".git" / "info" / "exclude", "a", encoding="utf-8", newline="") as fh:
        fh.write("\n" + EXCLUDE_HEADING + "\n" + "\n".join(EXCLUDE_MACHINERY) + "\n")


def build_bd_repo(repo: Path) -> None:
    """Makes a git repo with a real stealth bd workspace, bd's hooks and marked block, and project docs."""
    repo.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q"], repo)
    run(["git", "config", "user.email", "fixture@example.com"], repo)
    run(["git", "config", "user.name", "Fixture"], repo)
    run(["bd", "init", "--stealth", "--non-interactive"], repo)
    run(["bd", "setup", "claude", "--stealth"], repo)
    run(["bd", "hooks", "install"], repo)
    run(["bd", "create", "--title=Carry on", "--type=task"], repo)
    write_text(repo, "GLOSSARY-MAP.md", "# Glossary map\n\n- app: apps/app/GLOSSARY.md\n")
    write_text(repo, "GLOSSARY.md", "# Glossary\n\n**Widget**: a thing.\n")
    write_text(repo, "apps/app/GLOSSARY.md", "# App glossary\n\n**Gadget**: another thing.\n")
    write_text(repo, "docs/adr/0001-choose-a-thing.md", "# 0001 Choose a thing\n\nChosen.\n")
    write_text(repo, "apps/app/docs/adr/0001-app-choice.md", "# 0001 App choice\n\nChosen.\n")


def make_with_tracer(template: Path, destination: Path, revision: int) -> None:
    shutil.copytree(template, destination, symlinks=True)
    install_tracer(destination, revision)


def read_tree(root: Path) -> dict:
    """Maps each file under root to its bytes, keyed by relative posix path."""
    found = {}
    for folder, _, names in os.walk(root):
        for name in names:
            path = Path(folder) / name
            found[path.relative_to(root).as_posix()] = path.read_bytes()
    return found
