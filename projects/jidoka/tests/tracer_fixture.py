"""Builds throwaway repos that carry a tracer install, for the untracer tests.

The plugin's native files come from tests/fixtures/installed, and the seed
copy at docs/tracer.md from tests/fixtures/tracer-seed-<revision>.md. The
rules files hold what adopt writes from that seed: the `# AGENTS` heading,
the Reader line and Block 1, the import line and the comment-cleanup
paragraph. The statusline.sh, adopt notes,
settings file and upstream skills are written by hand as stand-ins. Nothing
is cloned or fetched.
"""
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import jidoka_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"
INSTALLED = FIXTURES / "installed"

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
    seed_file: str
    plugin_version: str


REVISIONS = {
    42: Revision(42, "tracer-seed-42.md", "1.3.1+tracer.42"),
    41: Revision(41, "tracer-seed-41.md", "1.3.1+tracer.41"),
    38: Revision(38, "tracer-seed-38.md", "1.3.0-pre.d81f3a1+tracer.38"),
}

BLOCK_ONE_HEADING = "# Block 1 — AGENTS.md core"
READER_LINES = "*Reader: the agent. Written for a fresh context that has read nothing\nelse.*\n"
COMMENT_CLEANUP_START = "Comment cleanup is requested work in this repository"


def run(args: list, cwd: Path) -> str:
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise FixtureError(f"{' '.join(args)} failed in {cwd}: {done.stderr.strip()}")
    return done.stdout


def seed_bytes(revision: int) -> bytes:
    return (FIXTURES / REVISIONS[revision].seed_file).read_bytes()


def block_one(revision: int) -> str:
    """The AGENTS file adopt writes from the seed: heading, Reader line, then Block 1 below its opening paragraph."""
    lines = seed_bytes(revision).decode("utf-8").splitlines()
    start = lines.index(BLOCK_ONE_HEADING) + 1
    end = next(i for i in range(start, len(lines)) if lines[i].startswith("# Block 2"))
    body = lines[start:end]
    while body[0] == "":
        body.pop(0)
    body = body[body.index(""):]
    while body[-1] in ("", "---"):
        body.pop()
    return "# AGENTS\n\n" + READER_LINES + "\n".join(body) + "\n"


def comment_cleanup_paragraph(revision: int) -> str:
    lines = seed_bytes(revision).decode("utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith(COMMENT_CLEANUP_START))
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "```")
    return "".join(line.strip() + "\n" for line in lines[start:end])


def native_files() -> list:
    """The installed files' paths relative to INSTALLED, in posix form."""
    paths = sorted(path.relative_to(INSTALLED).as_posix() for path in INSTALLED.rglob("*") if path.is_file())
    if not paths:
        raise FixtureError(f"no installed files under {INSTALLED}")
    return paths


def target_of(relative: str) -> str:
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
    """Writes the files a stealth adopt leaves in a repo at the given seed revision."""
    install_machinery(repo, revision)
    write_text(repo, "AGENTS.local.md", block_one(revision))
    write_text(repo, "CLAUDE.local.md", "@AGENTS.local.md\n\n" + comment_cleanup_paragraph(revision))


def install_committed_tracer(repo: Path, revision: int) -> None:
    """Writes the files a normal adopt leaves at the given seed revision and commits AGENTS.md and CLAUDE.md.

    CLAUDE.md starts with the import line and the comment-cleanup paragraph and
    keeps whatever the repo's CLAUDE.md already held below them.
    """
    install_machinery(repo, revision)
    write_text(repo, "AGENTS.md", block_one(revision))
    claude = repo / "CLAUDE.md"
    before = claude.read_text(encoding="utf-8") if claude.is_file() else ""
    write_text(repo, "CLAUDE.md", "@AGENTS.md\n\n" + comment_cleanup_paragraph(revision) + "\n" + before)
    commit(repo, ["AGENTS.md", "CLAUDE.md"], "Install tracer")


def commit(repo: Path, paths: list, message: str) -> None:
    run(["git", "add", "--", *paths], repo)
    run(["git", "commit", "-q", "--no-verify", "-m", message], repo)


def install_machinery(repo: Path, revision: int) -> None:
    """Writes the files of tracer's install that are not rules files."""
    rev = REVISIONS[revision]
    for relative in native_files():
        write_bytes(repo, target_of(relative), (INSTALLED / relative).read_bytes())
    write_bytes(repo, "docs/tracer.md", seed_bytes(revision))
    write_text(repo, ".claude/skills/tracer/.claude-plugin/plugin.json",
               json.dumps({"name": "tracer", "version": rev.plugin_version}, indent=2) + "\n")
    write_text(repo, ".claude/skills/tracer/skills/tdd/SKILL.md", "# tdd\n\nStand-in for the upstream skill.\n")
    write_text(repo, ".claude/skills/tracer/skills/grilling/SKILL.md", "# grilling\n\nStand-in for the upstream skill.\n")
    write_text(repo, ".claude/statusline.sh", "#!/bin/sh\necho tracer\n")
    write_text(repo, "docs/tracer-adopt-notes.md", "# Adopt notes\n\nWhat adopt did here.\n")
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
    jidoka_fixture.add_stealth_beads(repo)
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


def make_with_committed_tracer(template: Path, destination: Path, revision: int) -> None:
    shutil.copytree(template, destination, symlinks=True)
    install_committed_tracer(destination, revision)


def read_tree(root: Path) -> dict:
    """Maps each file under root to its bytes, keyed by relative posix path."""
    found = {}
    for folder, _, names in os.walk(root):
        for name in names:
            path = Path(folder) / name
            found[path.relative_to(root).as_posix()] = path.read_bytes()
    return found
