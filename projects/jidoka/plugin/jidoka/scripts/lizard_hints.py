#!/usr/bin/env python3
"""Lists the functions a range of commits added or grew past the repo's lizard limits, as hints.

`lizard_hints.py BASE HEAD [FILE ...]` prints a JSON list of {"file", "line", "name", "metric", "value", "limit",
"was"} for each function of each file at HEAD that passes a limit and either did not exist at BASE or measured less
there. A function that was already past a limit at BASE and did not grow is not listed. "was" is the measure at BASE,
or null when the function is new. With no FILE, the files are those the range added or changed. The limits are the
repo settings' `lizard_limits`, read from the repo of the cwd: "ccn" is cyclomatic complexity, "length" the lines a
function spans, "arguments" its parameter count.

A hint is a lead for the Design lane and never gates: a file lizard cannot read, in a language it does not know, or
that is not text, yields no hint, and the script exits 0 whatever it finds. The lizard it loads is the copy in
vendor/lizard, which needs only Python's standard library and reads Python, C#, TypeScript and JavaScript among others.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import settings_reader
from commands import CommandError, capture, run

VENDORED_LIZARD = Path(__file__).resolve().parent.parent / "vendor" / "lizard"
sys.path.insert(0, str(VENDORED_LIZARD))

import lizard  # noqa: E402

CCN, LENGTH, ARGUMENTS = settings_reader.LIZARD_METRICS
METRICS = settings_reader.LIZARD_METRICS


@dataclass(frozen=True)
class Hint:
    """A function whose measure passes a limit and grew in the range: where it is, which measure, and what it was."""
    file: str
    line: int
    name: str
    metric: str
    value: int
    limit: int
    was: int | None

    def fields(self) -> dict:
        return {"file": self.file, "line": self.line, "name": self.name, "metric": self.metric, "value": self.value,
                "limit": self.limit, "was": self.was}


def limits_of(settings: dict) -> dict[str, int]:
    """The repo's limits, with the default for each measure the settings leave out."""
    stored = settings.get(settings_reader.LIZARD_LIMITS)
    return {**settings_reader.DEFAULT_LIZARD_LIMITS, **(stored if isinstance(stored, dict) else {})}


def measures_of(file: str, source: str) -> dict[str, dict]:
    """Each function of the source by name, with its first line and its measures; the largest of those that share
    a name. A source lizard cannot read has none."""
    try:
        found = lizard.analyze_file.analyze_source_code(file, source).function_list
    except Exception:  # noqa: BLE001 - a hint never stops a pass, whatever lizard chokes on
        return {}
    measured: dict[str, dict] = {}
    for function in found:
        values = {CCN: function.cyclomatic_complexity, LENGTH: function.length,
                  ARGUMENTS: function.parameter_count}
        held = measured.get(function.name)
        if held is None:
            measured[function.name] = {"line": function.start_line, **values}
        else:
            measured[function.name] = {"line": held["line"], **{key: max(held[key], values[key]) for key in METRICS}}
    return measured


def source_at(revision: str, file: str, cwd: Path) -> str | None:
    """The file's text at the revision, or None when the revision holds no such file."""
    done = capture(["git", "show", f"{revision}:{file}"], cwd, None)
    return done.stdout if done.returncode == 0 else None


def hints_between(base: str, head: str, files: list[str], limits: dict[str, int], cwd: Path) -> list[Hint]:
    """The hints for the files, in file order and then by line."""
    hints = []
    for file in files:
        now_source = source_at(head, file, cwd)
        if now_source is None:
            continue
        before_source = source_at(base, file, cwd)
        before = measures_of(file, before_source) if before_source is not None else {}
        for name, now in measures_of(file, now_source).items():
            earlier = before.get(name)
            for metric in METRICS:
                if now[metric] > limits[metric] and (earlier is None or now[metric] > earlier[metric]):
                    hints.append(Hint(file, now["line"], name, metric, now[metric], limits[metric],
                                      None if earlier is None else earlier[metric]))
    return sorted(hints, key=lambda each: (each.file, each.line, each.metric))


def changed_files(base: str, head: str, cwd: Path) -> list[str]:
    return run(["git", "diff", "--name-only", "--diff-filter=AM", base, head], cwd, None).splitlines()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="lizard_hints.py", description=__doc__.split("\n")[0])
    parser.add_argument("base", help="the commit the range starts after")
    parser.add_argument("head", help="the commit the range ends at")
    parser.add_argument("files", nargs="*", help="the files to measure; the files the range changed when none")
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    cwd = Path.cwd()
    try:
        main_tree = settings_reader.main_worktree(cwd, settings_reader.GIT_TIMEOUT_SECONDS)
        settings = settings_reader.read_settings(settings_reader.jidoka_home(args.jidoka_home), main_tree)
        files = args.files or changed_files(args.base, args.head, cwd)
        hints = hints_between(args.base, args.head, files, limits_of(settings), cwd)
    except (settings_reader.SettingsError, CommandError, OSError) as error:
        print(f"lizard_hints: {error}", file=sys.stderr)
        return 1
    print(json.dumps([each.fields() for each in hints], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
