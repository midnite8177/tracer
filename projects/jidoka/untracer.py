#!/usr/bin/env python3
"""Takes tracer's files out of one repo and keeps a backup of every original.

The backup goes to <jidoka-home>/untracer/<repo-key>/<timestamp>/ before
anything changes, and the script never asks for confirmation. It keeps bd's
workspace, hooks and marked block, the glossaries and the ADRs.

The rules files lose the lines adopt wrote from docs/tracer.md, matched as
runs of lines with whitespace ignored, and keep every other line as the
repo's own. A rule or paragraph of tracer's that the repo edited, added to
or deleted a line from stays whole as the repo left it, so no kept line is
a piece of a sentence. A stealth
file's own lines move into CLAUDE.local.md in place of the import line, and
bd's marked block stays where it is. A committed file keeps its own lines in
place, and the script stages the change and never commits it. When
docs/tracer.md is not a seed revision this script knows byte for byte, or is
missing while a rules file still holds tracer's import line or AGENTS
heading, the script refuses the rules files and leaves them and
docs/tracer.md alone. With docs/tracer.md missing and no such mark, the
script changes no rules file and lists the lines that still match a seed
revision it knows, whose runs tracer-seed-runs.json beside it holds. When
that text is all it finds, it prints the plan and changes nothing.
Otherwise docs/tracer.md goes last, because it is the file that says what
tracer installed.
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
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
LOCAL_AGENT_FILES_HEADING = "# Local agent files"

BD_BLOCK_MARKER = "BEGIN BEADS INTEGRATION"
BD_BLOCK_END = "END BEADS INTEGRATION"
RULES_FILES = ["AGENTS.md", "CLAUDE.md", "AGENTS.local.md", "CLAUDE.local.md"]
AUDIT_DIR = ".audit/"
EXCLUDE_LINES_KEPT = frozenset({*RULES_FILES, AUDIT_DIR})
STEALTH_AGENTS = "AGENTS.local.md"
STEALTH_CLAUDE = "CLAUDE.local.md"
SHARED_AGENTS = "AGENTS.md"
SHARED_CLAUDE = "CLAUDE.md"
STEALTH_IMPORT = "@AGENTS.local.md"
SHARED_IMPORT = "@AGENTS.md"

SEED_HASHES = {
    38: "aa935726840a84c547f35367f9c86d15b002777d047f082cf4498bd8f4e6e0dd",
    41: "8d9632167c2b63ab0ba80f8a56dc38c989b7d0ce16ecc5b8fb7854978e3cd4a5",
    42: "961054abbdc94e638ac8b326f3191e5842314dafd5f1d92c9917aceec70de6f6",
}
SEED_REVISION = re.compile(r"^Seed revision (\d+) ")
KNOWN_SEED_RUNS = Path(__file__).resolve().parent / "tracer-seed-runs.json"
BLOCK_ONE_HEADING = "# Block 1 — AGENTS.md core"
BLOCK_TWO_PREFIX = "# Block 2"
AGENTS_HEADING = "# AGENTS"
READER_LINE = "*Reader: the agent. Written for a fresh context that has read nothing else.*"
COMMENT_CLEANUP_START = "Comment cleanup is requested work in this repository"
CHANGED_LINE_SIMILARITY = 0.6
MIN_LINES_TO_CLAIM_A_RUN = 2
SKIPPED_WHEN_SEARCHING = {".git", ".beads", ".claude", "node_modules"}

USER_SETTINGS = "~/.claude/settings.json"


class UntracerError(Exception):
    pass


@dataclass(frozen=True)
class Edit:
    path: str
    summary: str


@dataclass(frozen=True)
class RulesChange:
    """A rules file's new text, or None when the file goes; stage is set for a file git tracks."""
    path: str
    text: str | None
    stage: bool
    summary: str


@dataclass(frozen=True)
class RulesReport:
    own: list[str]
    changed: list[str]
    names_tracer: list[str]
    unplaced: list[str]
    refused: list[str]
    without_seed: list[str]

    @classmethod
    def empty(cls) -> "RulesReport":
        return cls([], [], [], [], [], [])


@dataclass(frozen=True)
class Plan:
    repo: Path
    deletions: list[str]
    edits: list[Edit]
    rules: list[RulesChange]
    report: RulesReport
    keeps: list[str]


class SeedRefused(Exception):
    pass


@dataclass(frozen=True)
class Unit:
    """One line of a rules file, or the Reader line when it is wrapped over two."""
    number: int
    text: str
    key: str
    in_bd_block: bool


class LineKind(Enum):
    TRACER = "tracer"
    CHANGED = "changed"
    OWN = "own"
    STEALTH_IMPORT = "stealth import"
    SHARED_IMPORT = "shared import"
    BD = "bd"


class Place(Enum):
    """Where a rules file lives: kept out of git, committed, or neither tracked nor ignored."""
    STEALTH = "stealth"
    COMMITTED = "committed"
    UNPLACED = "unplaced"


OWN_KINDS = frozenset({LineKind.OWN, LineKind.CHANGED})
TRACER_TEXT = frozenset({LineKind.TRACER, LineKind.CHANGED, LineKind.STEALTH_IMPORT, LineKind.SHARED_IMPORT})
MOVE_MARKS = frozenset({LineKind.TRACER, LineKind.CHANGED, LineKind.STEALTH_IMPORT})
GROUPED_KINDS = frozenset({LineKind.TRACER, LineKind.CHANGED, LineKind.OWN})
BD_ONLY = frozenset({LineKind.BD})
SEED_TEXT_KINDS = frozenset({LineKind.TRACER, LineKind.CHANGED})
IMPORT_KINDS = {STEALTH_IMPORT: LineKind.STEALTH_IMPORT, SHARED_IMPORT: LineKind.SHARED_IMPORT}
GAP = None


@dataclass(frozen=True)
class Line:
    """One unit of a rules file and its kind; follows_deletion is set when seed lines the repo deleted sat above it."""
    number: int
    text: str
    key: str
    kind: LineKind
    follows_deletion: bool


@dataclass(frozen=True)
class RulesFile:
    name: str
    place: Place
    text: str
    lines: list[Line]


@dataclass(frozen=True)
class MovedLines:
    """The text bound for CLAUDE.local.md, or None when nothing moves, and the files that gave it own lines."""
    text: str | None
    from_files: tuple[str, ...]


@dataclass(frozen=True)
class ClaudeRewrite:
    """A CLAUDE file's new text, and whether the moved lines took the place of its stealth import line."""
    text: str
    took_moved: bool


def read_text(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def lines_under_comment(keys: list[str], start: int) -> list[str]:
    """The lines below the comment at start, up to the next blank line or comment line."""
    block = []
    for key in keys[start + 1:]:
        if key.strip() == "" or key.startswith("#"):
            break
        block.append(key)
    return block


def names_tracer(key: str) -> bool:
    return key != LOCAL_AGENT_FILES_HEADING and (key == EXCLUDE_HEADING or "tracer" in key.lower())


def is_spent_tracer_heading(key: str, block: list[str]) -> bool:
    """True for a comment over only tracer's known lines, or a comment naming tracer whose lines are already gone."""
    holds_only_known_lines = all(entry in EXCLUDE_LINES_REMOVED for entry in block)
    return holds_only_known_lines and (bool(block) or names_tracer(key))


def is_dropped_tracer_heading(key: str, block: list[str]) -> bool:
    """True for tracer's known heading over any lines, or a spent tracer heading."""
    return key == EXCLUDE_HEADING or is_spent_tracer_heading(key, block)


def is_tracer_heading_over_kept_lines(key: str, block: list[str]) -> bool:
    """True for a comment naming tracer over lines tracer wrote that untracer keeps, and no line of the user's."""
    kept = [entry for entry in block if entry not in EXCLUDE_LINES_REMOVED]
    return names_tracer(key) and bool(kept) and all(entry in EXCLUDE_LINES_KEPT for entry in kept)


def exclude_without_tracer(text: str) -> str:
    """The exclude file without tracer's known lines and spent headings, and with tracer's other headings reworded."""
    lines = text.splitlines(keepends=True)
    keys = [line.rstrip("\r\n") for line in lines]
    kept = []
    for index, (line, key) in enumerate(zip(lines, keys)):
        if key in EXCLUDE_LINES_REMOVED:
            continue
        if key.startswith("#"):
            block = lines_under_comment(keys, index)
            if is_tracer_heading_over_kept_lines(key, block):
                kept.append(LOCAL_AGENT_FILES_HEADING + line[len(key):])
                continue
            if is_dropped_tracer_heading(key, block):
                continue
        kept.append(line)
    return "".join(kept)


def exclude_edit_summary(text: str, new: str) -> str:
    reworded = new.splitlines().count(LOCAL_AGENT_FILES_HEADING) > text.splitlines().count(LOCAL_AGENT_FILES_HEADING)
    return "remove tracer's lines" + (f", and reword tracer's heading to {LOCAL_AGENT_FILES_HEADING}" if reworded else "")


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
    if (repo / ".audit").is_dir():
        keeps.append(AUDIT_DIR)
    if (repo / ".claude" / "settings.json").is_file():
        keeps.append(".claude/settings.json")
    keeps.append(f"{USER_SETTINGS} (user-wide, never touched)")
    return keeps


def normalize(line: str) -> str:
    return " ".join(line.split())


def significant(key: str) -> bool:
    return key != "" and not key.startswith("```")


def load_seed(repo: Path) -> list[list[str]]:
    """Returns the runs of lines adopt writes from the seed copy, whitespace-normalized.

    Raises SeedRefused when the copy is missing, names no seed revision, names
    a revision this script does not know, or differs from that revision's bytes.
    """
    path = repo / SEED_COPY
    if not path.is_file():
        raise SeedRefused(f"{SEED_COPY} is missing")
    data = path.read_bytes()
    lines = data.decode("utf-8", "replace").splitlines()
    match = SEED_REVISION.match(lines[2]) if len(lines) > 2 else None
    if match is None:
        raise SeedRefused(f"{SEED_COPY} names no seed revision on its third line")
    revision = int(match.group(1))
    if revision not in SEED_HASHES:
        raise SeedRefused(f"{SEED_COPY} is seed revision {revision}, which untracer does not know")
    if hashlib.sha256(data).hexdigest() != SEED_HASHES[revision]:
        raise SeedRefused(f"{SEED_COPY} differs from seed revision {revision}")
    return [block_one_run(lines), comment_cleanup_run(lines)]


def block_one_run(lines: list[str]) -> list[str]:
    """The AGENTS heading, the Reader line, then Block 1 below the paragraph that tells adopt what to write."""
    start = lines.index(BLOCK_ONE_HEADING) + 1
    end = next(i for i in range(start, len(lines)) if lines[i].startswith(BLOCK_TWO_PREFIX))
    body = [normalize(line) for line in lines[start:end]]
    while body and body[0] == "":
        body.pop(0)
    body = body[body.index(""):] if "" in body else []
    while body and body[-1] in ("", "---"):
        body.pop()
    return [AGENTS_HEADING, "", READER_LINE, *body]


def comment_cleanup_run(lines: list[str]) -> list[str]:
    start = next(i for i, line in enumerate(lines) if line.strip().startswith(COMMENT_CLEANUP_START))
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "```")
    return [normalize(line) for line in lines[start:end]]


def read_units(text: str) -> list[Unit]:
    lines = text.splitlines(keepends=True)
    units = []
    in_bd_block = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if BD_BLOCK_MARKER in line:
            in_bd_block = True
        wrapped = index + 1 < len(lines) and normalize(line) != "" and normalize(lines[index + 1]) != ""
        if not in_bd_block and wrapped and normalize(line + " " + lines[index + 1]) == READER_LINE:
            units.append(Unit(index + 1, line + lines[index + 1], READER_LINE, False))
            index += 2
            continue
        units.append(Unit(index + 1, line, normalize(line), in_bd_block))
        if BD_BLOCK_END in line:
            in_bd_block = False
        index += 1
    return units


def unmatchable_key(index: int) -> str:
    """A key that no seed line equals, so the diff never claims an import line or a line of bd's block."""
    return f"\0{index}"


def first_kind(unit: Unit) -> LineKind:
    if unit.in_bd_block:
        return LineKind.BD
    return IMPORT_KINDS.get(unit.key, LineKind.OWN)


def replaced_pairs(before_claimed: bool, after_claimed: bool, at_edge: bool,
                   seed_span: range, file_span: range) -> list[tuple[int, int]]:
    """Pairs the seed lines a replace dropped with the file lines in their place, counted from a claimed side.

    A replace between two claimed runs, or at the run's edge beside one, is a
    stretch of tracer's lines the repo edited. Anywhere else it is the repo's own.
    """
    if before_claimed and (after_claimed or at_edge):
        return list(zip(seed_span, file_span))
    if after_claimed and at_edge:
        return list(zip(reversed(seed_span), reversed(file_span)))
    return []


def classify(units: list[Unit], runs: list[list[str]]) -> list[Line]:
    """Marks each unit as tracer's, a tracer line the repo changed, the repo's own, an import line or bd's."""
    kinds = [first_kind(unit) for unit in units]
    follows_deletion = [False] * len(units)
    keys = [unit.key if kinds[i] is LineKind.OWN else unmatchable_key(i) for i, unit in enumerate(units)]
    for run in runs:
        opcodes = difflib.SequenceMatcher(None, run, keys, autojunk=False).get_opcodes()
        claimed = [tag == "equal" and sum(significant(key) for key in run[i1:i2]) >= MIN_LINES_TO_CLAIM_A_RUN
                   for tag, i1, i2, _, _ in opcodes]
        last = len(opcodes) - 1
        for n, (tag, i1, i2, j1, j2) in enumerate(opcodes):
            if claimed[n]:
                for j in range(j1, j2):
                    kinds[j] = LineKind.TRACER
            elif tag == "delete" and 0 < n < last and claimed[n - 1] and claimed[n + 1]:
                follows_deletion[j1] = True
            elif tag == "replace":
                before_claimed = n > 0 and claimed[n - 1]
                after_claimed = n < last and claimed[n + 1]
                at_edge = n in (0, last)
                for i, j in replaced_pairs(before_claimed, after_claimed, at_edge, range(i1, i2), range(j1, j2)):
                    similar = difflib.SequenceMatcher(None, run[i], keys[j]).ratio() >= CHANGED_LINE_SIMILARITY
                    if kinds[j] is LineKind.OWN and significant(keys[j]) and similar:
                        kinds[j] = LineKind.CHANGED
    return [Line(unit.number, unit.text, unit.key, kind, deleted_above)
            for unit, kind, deleted_above in zip(units, kinds, follows_deletion)]


def rules_and_paragraphs(lines: list[Line]) -> list[list[int]]:
    """Groups the indexes of the text lines into rules and paragraphs.

    A rule is a line that starts with "- " and the indented lines below it,
    because a list of rules has no blank lines between its rules. Any other
    line belongs to the paragraph that blank lines bound. A blank line, an
    import line or a line of bd's block ends the group above it.
    """
    groups = []
    current = []
    in_rule = False
    for index, line in enumerate(lines):
        if line.kind not in GROUPED_KINDS or line.key == "":
            if current:
                groups.append(current)
            current, in_rule = [], False
            continue
        starts_rule = line.text.startswith("- ")
        indented = line.text[:1] in (" ", "\t")
        if current and (starts_rule or (in_rule and not indented)):
            groups.append(current)
            current = []
        if not current:
            in_rule = starts_rule
        current.append(index)
    if current:
        groups.append(current)
    return groups


def changed_whole(lines: list[Line], group: list[int]) -> bool:
    """True for a rule or paragraph the repo changed.

    It holds a tracer line the repo changed, a line of the repo's own among
    tracer's, or a gap between two of its lines where the repo deleted
    tracer's lines.
    """
    kinds = {lines[i].kind for i in group}
    own_among_tracers = LineKind.TRACER in kinds and any(
        lines[i].kind is LineKind.OWN and significant(lines[i].key) for i in group)
    deleted_inside = any(lines[i].follows_deletion for i in group[1:])
    return LineKind.CHANGED in kinds or own_among_tracers or deleted_inside


def keep_changed_rules_whole(lines: list[Line]) -> list[Line]:
    """Marks every line of a changed rule or paragraph as changed, so it is kept whole and never as a fragment."""
    kinds = [line.kind for line in lines]
    for group in rules_and_paragraphs(lines):
        if changed_whole(lines, group):
            for i in group:
                kinds[i] = LineKind.CHANGED
    return [replace(line, kind=kind) for line, kind in zip(lines, kinds)]


def join_kept(tokens: list) -> str:
    """Joins kept lines; a GAP marks removed lines, and blank lines left doubled or dangling by a gap go."""
    out = []
    after_gap = False
    for token in tokens:
        if token is GAP:
            after_gap = True
            continue
        blank = token.strip() == ""
        if blank and after_gap and (not out or out[-1].strip() == ""):
            continue
        if not blank:
            after_gap = False
        out.append(token if token.endswith("\n") else token + "\n")
    if after_gap:
        while out and out[-1].strip() == "":
            out.pop()
    return "".join(out)


def git_succeeds(repo: Path, args: list[str]) -> bool:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True)
    return done.returncode == 0


def rules_places(repo: Path) -> dict[str, Place]:
    """Places each rules file present; AGENTS.md and CLAUDE.md are stealth only when git ignores them."""
    places = {}
    for name in [STEALTH_AGENTS, SHARED_AGENTS, STEALTH_CLAUDE, SHARED_CLAUDE]:
        if not (repo / name).is_file():
            continue
        if name in (STEALTH_AGENTS, STEALTH_CLAUDE):
            places[name] = Place.STEALTH
        elif git_succeeds(repo, ["ls-files", "--error-unmatch", "--", name]):
            places[name] = Place.COMMITTED
        elif git_succeeds(repo, ["check-ignore", "-q", "--", name]):
            places[name] = Place.STEALTH
        else:
            places[name] = Place.UNPLACED
    return places


def kept_text(lines: list[Line], kept: frozenset[LineKind]) -> str:
    return join_kept([line.text if line.kind in kept else GAP for line in lines])


def rewrite_claude(lines: list[Line], kept: frozenset[LineKind], moved: str | None) -> ClaudeRewrite:
    """Keeps the lines of the kept kinds; the moved lines, when given, take the place of the first stealth import."""
    tokens = []
    took_moved = False
    for line in lines:
        if line.kind in kept:
            tokens.append(line.text)
        elif line.kind is LineKind.STEALTH_IMPORT and moved is not None and not took_moved:
            tokens += [GAP, *moved.splitlines(keepends=True), GAP]
            took_moved = True
        else:
            tokens.append(GAP)
    return ClaudeRewrite(join_kept(tokens), took_moved)


def moves_out(rules_file: RulesFile) -> bool:
    """A stealth AGENTS file always gives up its own lines; a stealth CLAUDE.md does when it holds tracer's text."""
    if rules_file.place is not Place.STEALTH:
        return False
    if rules_file.name in (STEALTH_AGENTS, SHARED_AGENTS):
        return True
    return rules_file.name == SHARED_CLAUDE and any(line.kind in MOVE_MARKS for line in rules_file.lines)


def kinds_kept_in_claude(files: dict[str, RulesFile]) -> frozenset[LineKind]:
    """The repo's own lines, and the @AGENTS.md import while AGENTS.md keeps something to import."""
    agents = files.get(SHARED_AGENTS)
    if agents is None or agents.place is Place.STEALTH:
        return OWN_KINDS
    if agents.place is Place.COMMITTED and kept_text(agents.lines, OWN_KINDS | BD_ONLY).strip() == "":
        return OWN_KINDS
    return OWN_KINDS | {LineKind.SHARED_IMPORT}


def analyze_rules_files(repo: Path, runs: list[list[str]], places: dict[str, Place]) -> dict[str, RulesFile]:
    files = {}
    for name, place in places.items():
        text = read_text(repo / name)
        files[name] = RulesFile(name, place, text, keep_changed_rules_whole(classify(read_units(text), runs)))
    return files


def moved_lines(files: dict[str, RulesFile], claude_kinds: frozenset[LineKind]) -> MovedLines:
    blocks = []
    from_files = []
    for name in (STEALTH_AGENTS, SHARED_AGENTS):
        if name in files and moves_out(files[name]):
            own = kept_text(files[name].lines, OWN_KINDS)
            if own:
                blocks.append(own)
                from_files.append(name)
    agents_own = "\n".join(blocks) if blocks else None
    claude = files.get(SHARED_CLAUDE)
    if claude is None or not moves_out(claude):
        return MovedLines(agents_own, tuple(from_files))
    rewrite = rewrite_claude(claude.lines, claude_kinds, agents_own)
    pieces = [] if rewrite.took_moved or agents_own is None else [agents_own]
    if rewrite.text:
        pieces.append(rewrite.text)
    if kept_text(claude.lines, OWN_KINDS):
        from_files.append(SHARED_CLAUDE)
    return MovedLines("\n".join(pieces) if pieces else None, tuple(from_files))


def new_rules_texts(files: dict[str, RulesFile], claude_kinds: frozenset[LineKind],
                    moved: MovedLines) -> dict[str, str]:
    """Maps each rules file the run may change to its new text, CLAUDE.local.md first.

    CLAUDE.local.md comes first so that apply writes the moved lines before it
    changes the files they came from.
    """
    texts = {}
    local = files.get(STEALTH_CLAUDE)
    if local is not None:
        rewrite = rewrite_claude(local.lines, claude_kinds | BD_ONLY, moved.text)
        text = rewrite.text
        if not rewrite.took_moved and moved.text is not None:
            text += ("\n" if text else "") + moved.text
        texts[STEALTH_CLAUDE] = text
    elif moved.text is not None:
        texts[STEALTH_CLAUDE] = moved.text
    for name in (STEALTH_AGENTS, SHARED_AGENTS, SHARED_CLAUDE):
        rules_file = files.get(name)
        if rules_file is None or rules_file.place is Place.UNPLACED:
            continue
        if moves_out(rules_file):
            texts[name] = kept_text(rules_file.lines, BD_ONLY)
        elif name == SHARED_AGENTS:
            texts[name] = kept_text(rules_file.lines, OWN_KINDS | BD_ONLY)
        else:
            texts[name] = kept_text(rules_file.lines, claude_kinds | BD_ONLY)
    return texts


def rules_changes(files: dict[str, RulesFile], texts: dict[str, str], moved: MovedLines) -> list[RulesChange]:
    changes = []
    for name, new in texts.items():
        rules_file = files.get(name)
        if rules_file is None:
            sources = " and ".join(moved.from_files)
            changes.append(RulesChange(name, new, False, f"create it with your own lines from {sources}"))
            continue
        if new == rules_file.text:
            continue
        text = new if new.strip() != "" else None
        stage = rules_file.place is Place.COMMITTED
        staged = ", then stage the change" if stage else ""
        if moves_out(rules_file):
            summary = (f"your own lines move to {STEALTH_CLAUDE}" if name in moved.from_files
                       else "nothing of your own is in it")
            if text is not None:
                summary += "; bd's marked block stays"
        elif text is None:
            summary = f"nothing of your own is left{staged}"
        else:
            summary = f"remove tracer's lines{staged}"
        changes.append(RulesChange(name, text, stage, summary))
    return changes


def changed_rule_entry(rules_file: RulesFile, group: list[int]) -> str:
    """Names a changed rule or paragraph by its line numbers and its first line."""
    first, last = rules_file.lines[group[0]], rules_file.lines[group[-1]]
    numbers = str(first.number) if first is last else f"{first.number}-{last.number}"
    return f"{rules_file.name}:{numbers}: {first.key}"


def report_rules(files: dict[str, RulesFile], touched: set[str]) -> RulesReport:
    """Lists own lines and changed rules for the files the run changes, and lines that name tracer in every placed file."""
    own, changed, names_tracer, unplaced = [], [], [], []
    for rules_file in files.values():
        for line in rules_file.lines:
            entry = f"{rules_file.name}:{line.number}: {line.key}"
            if rules_file.place is Place.UNPLACED:
                if line.kind in TRACER_TEXT:
                    unplaced.append(entry)
                continue
            if line.kind in OWN_KINDS and "tracer" in line.key.lower():
                names_tracer.append(entry)
            if rules_file.name in touched and line.kind is LineKind.OWN and significant(line.key):
                own.append(entry)
        if rules_file.place is not Place.UNPLACED and rules_file.name in touched:
            changed += [changed_rule_entry(rules_file, group) for group in rules_and_paragraphs(rules_file.lines)
                        if all(rules_file.lines[i].kind is LineKind.CHANGED for i in group)]
    return RulesReport(own, changed, names_tracer, unplaced, [], [])


def plan_rules(repo: Path, runs: list[list[str]], places: dict[str, Place]) -> tuple[list[RulesChange], RulesReport]:
    files = analyze_rules_files(repo, runs, places)
    claude_kinds = kinds_kept_in_claude(files)
    moved = moved_lines(files, claude_kinds)
    changes = rules_changes(files, new_rules_texts(files, claude_kinds, moved), moved)
    return changes, report_rules(files, {change.path for change in changes})


def holds_tracers_mark(text: str) -> bool:
    """True for the stealth import line, or the AGENTS heading with the Reader line as the next line that is not blank."""
    keys = [unit.key for unit in read_units(text) if not unit.in_bd_block and unit.key != ""]
    if STEALTH_IMPORT in keys:
        return True
    return any(key == AGENTS_HEADING and following == READER_LINE for key, following in zip(keys, keys[1:]))


def known_seed_runs() -> list[list[list[str]]]:
    """The runs of each seed revision in SEED_HASHES, from the copy kept beside this script."""
    data = json.loads(read_text(KNOWN_SEED_RUNS))
    return [data[str(revision)] for revision in sorted(SEED_HASHES)]


def seed_text_left(repo: Path, placed: list[str]) -> list[str]:
    """Lists each line of the placed rules files that matches the text of a seed revision untracer knows."""
    entries = []
    every_revision = known_seed_runs()
    for name in placed:
        units = read_units(read_text(repo / name))
        matched = {index for runs in every_revision
                   for index, line in enumerate(classify(units, runs)) if line.kind in SEED_TEXT_KINDS}
        entries += [f"{name}:{units[index].number}: {units[index].key}" for index in sorted(matched)]
    return entries


def plan_rules_or_refuse(repo: Path) -> tuple[list[RulesChange], RulesReport]:
    """Plans the rules files against the seed copy.

    With no seed copy, it refuses them only while one holds tracer's mark.
    With neither, it changes nothing and lists the lines that still match a
    seed revision it knows.
    """
    places = rules_places(repo)
    placed = [name for name, place in places.items() if place is not Place.UNPLACED]
    marked = any(holds_tracers_mark(read_text(repo / name)) for name in placed)
    if not (repo / SEED_COPY).is_file() and not marked:
        return [], replace(RulesReport.empty(), without_seed=seed_text_left(repo, placed))
    try:
        runs = load_seed(repo)
    except SeedRefused as refusal:
        return [], replace(RulesReport.empty(), refused=[f"{name} ({refusal})" for name in placed])
    return plan_rules(repo, runs, places)


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
        new = exclude_without_tracer(text)
        if new != text:
            edits.append(Edit(EXCLUDE_FILE, exclude_edit_summary(text, new)))
    rules, report = plan_rules_or_refuse(repo)
    keeps = find_keeps(repo)
    if (repo / SEED_COPY).is_file():
        if report.refused:
            keeps.append(f"{SEED_COPY} (the rules files were refused)")
        else:
            deletions.append(SEED_COPY)
    return Plan(repo, deletions, edits, rules, report, keeps)


def print_plan(plan: Plan) -> None:
    print(f"Plan for {plan.repo}")
    print("Will delete:")
    for path in plan.deletions:
        print(f"  {path}")
    for change in plan.rules:
        if change.text is None:
            print(f"  {change.path} ({change.summary})")
    print("Will edit:")
    for edit in plan.edits:
        print(f"  {edit.path} ({edit.summary})")
    for change in plan.rules:
        if change.text is not None:
            print(f"  {change.path} ({change.summary})")
    print("Will keep:")
    for path in plan.keeps:
        print(f"  {path}")
    for heading, entries in [
        ("Your own lines:", plan.report.own),
        ("Tracer rules you changed (kept whole):", plan.report.changed),
        ("Lines that still name tracer (left):", plan.report.names_tracer),
        ("Could not place (left):", plan.report.unplaced),
        ("Refused:", plan.report.refused),
        ("Tracer text with no seed copy (left):", plan.report.without_seed),
    ]:
        if entries:
            print(heading)
            for entry in entries:
                print(f"  {entry}")


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
    for path in [*plan.deletions, *(edit.path for edit in plan.edits), *(change.path for change in plan.rules)]:
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


def rewrite_exclude(repo: Path) -> None:
    path = repo / EXCLUDE_FILE
    write_text(path, exclude_without_tracer(read_text(path)))
    print(f"edited {EXCLUDE_FILE}")


def git(repo: Path, args: list[str]) -> None:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise UntracerError(f"git {' '.join(args)} failed: {done.stderr.strip()}")


def apply_rules_change(repo: Path, change: RulesChange) -> None:
    if change.text is None:
        if change.stage:
            git(repo, ["rm", "-q", "--", change.path])
        else:
            (repo / change.path).unlink()
        print(f"removed {change.path}")
    else:
        write_text(repo / change.path, change.text)
        if change.stage:
            git(repo, ["add", "--", change.path])
        print(f"edited {change.path}")
    if change.stage:
        print(f"staged {change.path}")


def apply(plan: Plan) -> None:
    repo = plan.repo
    for path in plan.deletions:
        if path != SEED_COPY:
            remove_path(repo, path)
    for change in plan.rules:
        apply_rules_change(repo, change)
    for edit in plan.edits:
        if edit.path == SETTINGS_LOCAL:
            drop_status_line(repo)
        else:
            rewrite_exclude(repo)
    if SEED_COPY in plan.deletions:
        remove_path(repo, SEED_COPY)


def untrace(repo: Path, jidoka_home: Path) -> None:
    if not (repo / ".git").is_dir():
        raise UntracerError(f"{repo} is not a git repository")
    plan = find_plan(repo)
    has_work = bool(plan.deletions or plan.edits or plan.rules or plan.report.refused)
    if not has_work and not plan.report.without_seed:
        print(f"Nothing of tracer's was found in {repo}.")
        return
    print_plan(plan)
    if not has_work:
        return
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
