"""Adds lines to the repo's git exclude file, and takes them out again, keeping every other byte of the file."""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from commands import run


def exclude_file(main_tree: Path) -> Path:
    """The repo's info/exclude, which a linked worktree shares with the main one."""
    named = run(["git", "rev-parse", "--git-path", "info/exclude"], main_tree, None).strip()
    return (main_tree / named).resolve()


def exclude_line(path: str, folder: bool) -> str:
    """The line that hides one path at the repo root, and not a path of the same name further down.

    A folder's line ends in a slash, so it hides only a folder. Git matches the line whether or not the path exists
    yet, so the line also hides a folder written later.
    """
    line = f"/{PurePosixPath(path)}"
    return f"{line}/" if folder else line


def read(file: Path) -> str:
    if not file.is_file():
        return ""
    with open(file, encoding="utf-8", newline="") as handle:
        return handle.read()


def add(file: Path, lines: list[str]) -> list[str]:
    """Appends each line the file does not hold yet, and returns the lines it appended."""
    text = read(file)
    held = {line.strip() for line in text.splitlines()}
    missing = [line for line in dict.fromkeys(lines) if line not in held]
    if not missing:
        return []
    file.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if text == "" or text.endswith("\n") else "\n"
    with open(file, "a", encoding="utf-8", newline="") as handle:
        handle.write(separator + "".join(f"{line}\n" for line in missing))
    return missing


def remove(file: Path, lines: list[str]) -> list[str]:
    """Takes out every line of the file that is one of the lines, and returns the lines it took out."""
    held = read(file).splitlines(keepends=True)
    kept = [line for line in held if line.rstrip("\r\n") not in lines]
    if len(kept) == len(held):
        return []
    with open(file, "w", encoding="utf-8", newline="") as handle:
        handle.write("".join(kept))
    found = {line.rstrip("\r\n") for line in held}
    return [line for line in dict.fromkeys(lines) if line in found]
