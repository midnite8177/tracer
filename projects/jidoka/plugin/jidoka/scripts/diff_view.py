"""A git diff read into files, hunks and lines, and drawn as HTML twice: unified and split.

The gate page (gate_page.py) shows each changed file's real diff. Git prints one text, so this module reads it
once into `FileDiff` values and draws each file in both layouts. A page has no script, so a stylesheet rule shows
one layout and hides the other. Every word of the diff is escaped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from itertools import zip_longest

ADDED = "added"
DELETED = "deleted"
MODIFIED = "modified"
BINARY = "binary"
CONTEXT_LINE = " "
ADDED_LINE = "+"
REMOVED_LINE = "-"
HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
LINE_CLASSES = {ADDED_LINE: "add", REMOVED_LINE: "del"}
SAME_LINE_CLASS = "same"
BACKSLASH = ord("\\")
OCTAL_DIGITS = "01234567"
ESCAPES = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}


@dataclass(frozen=True)
class DiffLine:
    """One line of a hunk: its kind, its number in the old file (0 for an added line) and in the new file (0 for a
    removed line), and its text without the leading kind character."""
    kind: str
    old_number: int
    new_number: int
    text: str


@dataclass(frozen=True)
class Hunk:
    """The header git printed for a run of changed lines, and the lines."""
    header: str
    lines: tuple[DiffLine, ...]


@dataclass(frozen=True)
class FileDiff:
    """The diff of one file: its path, whether it was added, deleted, changed or is binary, and its hunks."""
    path: str
    status: str
    hunks: tuple[Hunk, ...]

    @property
    def added(self) -> int:
        return self.count(ADDED_LINE)

    @property
    def removed(self) -> int:
        return self.count(REMOVED_LINE)

    def count(self, kind: str) -> int:
        return sum(1 for hunk in self.hunks for line in hunk.lines if line.kind == kind)


def unquote(text: str) -> str:
    """The path inside the double quotes git puts around a path that holds a double quote, a backslash or a control
    character, with its C-style escapes undone."""
    data = text[1:-1].encode("utf-8")
    out = bytearray()
    position = 0
    while position < len(data):
        if data[position] != BACKSLASH:
            out.append(data[position])
            position += 1
        elif chr(data[position + 1]) in OCTAL_DIGITS:
            out.append(int(data[position + 1:position + 4], 8))
            position += 4
        else:
            escaped = chr(data[position + 1])
            out += ESCAPES.get(escaped, escaped).encode("utf-8")
            position += 2
    return out.decode("utf-8", errors="replace")


def header_path(header: str) -> str:
    """The path in a `diff --git a/<path> b/<path>` header, which names one path twice when git is told not to
    detect renames. The parser reads this header and no other line, so a binary file, an empty file and a mode change
    name their path as a file with hunks does. A quoted path is `"a/<path>" "b/<path>"`; any other is the unquoted
    pair, where the path is half of what follows the two prefixes."""
    both = header[len("diff --git "):]
    if both.startswith('"'):
        return unquote(both[:both.index('" "') + 1])[2:]
    return both[2:2 + (len(both) - 5) // 2]


class FileBuilder:
    """A file diff under construction while its lines are read."""

    def __init__(self, header: str) -> None:
        self.path = header_path(header)
        self.status = MODIFIED
        self.hunks: list[Hunk] = []
        self.header = ""
        self.lines: list[DiffLine] = []
        self.old_number = 0
        self.new_number = 0

    def close_hunk(self) -> None:
        if self.header:
            self.hunks.append(Hunk(self.header, tuple(self.lines)))
        self.header = ""
        self.lines = []

    def start_hunk(self, line: str, found: re.Match) -> None:
        self.close_hunk()
        self.header = line
        self.old_number = int(found.group(1))
        self.new_number = int(found.group(2))

    def add_line(self, line: str) -> None:
        kind = line[:1] or CONTEXT_LINE
        text = line[1:]
        if kind == ADDED_LINE:
            self.lines.append(DiffLine(kind, 0, self.new_number, text))
            self.new_number += 1
        elif kind == REMOVED_LINE:
            self.lines.append(DiffLine(kind, self.old_number, 0, text))
            self.old_number += 1
        elif kind == CONTEXT_LINE:
            self.lines.append(DiffLine(kind, self.old_number, self.new_number, text))
            self.old_number += 1
            self.new_number += 1

    def read(self, line: str) -> None:
        found = HUNK_HEADER.match(line)
        if found:
            self.start_hunk(line, found)
        elif self.header:
            self.add_line(line)
        elif line.startswith("new file mode"):
            self.status = ADDED
        elif line.startswith("deleted file mode"):
            self.status = DELETED
        elif line.startswith("Binary files") or line.startswith("GIT binary patch"):
            self.status = BINARY

    def done(self) -> FileDiff:
        self.close_hunk()
        return FileDiff(self.path, self.status, tuple(self.hunks))


def parse(diff: str) -> list[FileDiff]:
    """The files in the text `git diff --no-renames` printed, in the order git printed them."""
    files: list[FileDiff] = []
    current: FileBuilder | None = None
    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            if current is not None:
                files.append(current.done())
            current = FileBuilder(line)
        elif current is not None:
            current.read(line)
    if current is not None:
        files.append(current.done())
    return files


def css_class(line: DiffLine) -> str:
    return LINE_CLASSES.get(line.kind, SAME_LINE_CLASS)


def number_cell(number: int) -> str:
    return f"<i>{number}</i>" if number else "<i></i>"


def unified(file: FileDiff) -> str:
    """The file's hunks as one column of lines: removed lines, then added lines, each with its numbers."""
    rows = []
    for hunk in file.hunks:
        rows.append(f'<span class="hunk">{escape(hunk.header)}</span>')
        for line in hunk.lines:
            rows.append(f'<span class="{css_class(line)}">{number_cell(line.old_number)}{number_cell(line.new_number)}'
                        f'{escape(line.kind)}{escape(line.text)}</span>')
    return f'<div class="unified"><pre>{"".join(rows)}</pre></div>'


def paired(lines: tuple[DiffLine, ...]) -> list[tuple[DiffLine | None, DiffLine | None]]:
    """The hunk's lines as rows of an old side and a new side: a context line fills both, and a run of removed
    lines sits beside the run of added lines that follows it."""
    rows: list[tuple[DiffLine | None, DiffLine | None]] = []
    removed: list[DiffLine] = []
    added: list[DiffLine] = []

    def flush() -> None:
        rows.extend(zip_longest(removed, added))
        removed.clear()
        added.clear()

    for line in lines:
        if line.kind == REMOVED_LINE:
            if added:
                flush()
            removed.append(line)
        elif line.kind == ADDED_LINE:
            added.append(line)
        else:
            flush()
            rows.append((line, line))
    flush()
    return rows


def side(line: DiffLine | None, side_name: str, number: int) -> str:
    if line is None:
        return f'<td class="no"></td><td class="{side_name} empty"></td>'
    return f'<td class="no">{number}</td><td class="{side_name} {css_class(line)}">{escape(line.text)}</td>'


def split(file: FileDiff) -> str:
    """The file's hunks as a table with the old file on the left and the new file on the right."""
    rows = []
    for hunk in file.hunks:
        rows.append(f'<tr class="hunk"><td colspan="4">{escape(hunk.header)}</td></tr>')
        for old, new in paired(hunk.lines):
            rows.append(f'<tr>{side(old, "old", old.old_number if old else 0)}'
                        f'{side(new, "new", new.new_number if new else 0)}</tr>')
    return f'<div class="split-view"><table class="split">{"".join(rows)}</table></div>'
