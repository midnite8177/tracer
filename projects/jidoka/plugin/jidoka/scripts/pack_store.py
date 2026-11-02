#!/usr/bin/env python3
"""Packs the repo's beads store with bd's garbage collection, keeping every bead and every commit.

Each bd write appends to the store's chunk journal, and bd reads the whole
journal each time it opens the store, so a growing journal slows every bd
call. `bd gc` packs the journal into archive files. Plain `bd gc` also
deletes the beads closed longest ago; --skip-decay keeps them. bd serializes
the calls to the store, so a pack is safe while a factory works.

Run it from inside any checkout of the repo. It prints the store's size in
bytes before and after the pack as one JSON object, {"before": ...,
"after": ...}. The store is the Dolt folder under the main checkout's
.beads, embeddeddolt or dolt; a repo with neither prints 0 for both.

Exit codes:
  0  packed.
  1  bd gc failed, or the folder is not inside a git repo, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import settings_reader
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, run

STORE_FOLDERS = ("embeddeddolt", "dolt")
GC = ["bd", "gc", "--skip-decay", "--force"]


@dataclass(frozen=True)
class Packed:
    """The store's size in bytes before and after one pack."""
    before: int
    after: int

    def fields(self) -> dict:
        return {"before": self.before, "after": self.after}


def file_bytes(path: Path) -> int:
    """A file's size, or 0 for one that a running bd removed after the walk listed it."""
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def store_bytes(main_tree: Path) -> int:
    beads = main_tree / ".beads"
    return sum(file_bytes(Path(folder) / name)
               for store in STORE_FOLDERS
               for folder, _, names in os.walk(beads / store)
               for name in names)


def pack_store(main_tree: Path) -> Packed:
    """Raises CommandError when bd gc fails."""
    before = store_bytes(main_tree)
    run(GC, main_tree, None)
    return Packed(before, store_bytes(main_tree))


def main(argv: list[str]) -> int:
    argparse.ArgumentParser(prog="pack_store.py", description="Pack the repo's beads store, keeping every bead "
                                                              "and every commit.").parse_args(argv)
    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        packed = pack_store(main_tree)
    except (CommandError, settings_reader.SettingsError) as error:
        print(f"pack_store: {error}", file=sys.stderr)
        return 1
    print(json.dumps(packed.fields()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
