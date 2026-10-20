#!/usr/bin/env python3
"""Generates the tracer seed from the sources under src/.

seed.json lists the fragments in seed order and holds the values that
appear in several places in the seed. A fragment may open with
maintainer notes, ended by a line reading `<!-- seed -->`; the notes never
reach the seed. A line `{{include <path>}}` is replaced by the file at
that path under src/, byte for byte. `{{revision}}`, `{{date}}`,
`{{upstream_pin}}`, `{{bd_version}}` and `{{plugin_version}}` are filled
from seed.json.

Usage: build.py           write the seed to the output path in seed.json
       build.py --check   exit 1 when the committed seed differs from the sources
"""
import json
import re
import sys
from pathlib import Path

NOTES_END = "<!-- seed -->\n"
INCLUDE = re.compile(r"^\{\{include (\S+)\}\}\n", re.MULTILINE)
CHANGELOG_ENTRY = re.compile(r"^# Changelog\n.*?^- \*\*(\d+)\*\*", re.MULTILINE | re.DOTALL)


class SeedError(Exception):
    pass


def read(path: Path) -> str:
    if not path.is_file():
        raise SeedError(f"missing source file: {path}")
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def without_notes(text: str) -> str:
    head, sep, rest = text.partition(NOTES_END)
    return rest if sep else head


def placeholders(config: dict) -> dict:
    pin = config["upstream_pin"]
    return {
        "revision": str(config["revision"]),
        "date": config["date"],
        "upstream_pin": pin,
        "bd_version": config["bd_version"],
        "plugin_version": f"{pin.lstrip('v')}+tracer.{config['revision']}",
    }


def render(project: Path, config: dict) -> str:
    src = project / "src"
    fragments_dir = src / "fragments"
    listed = [fragments_dir / name for name in config["fragments"]]

    on_disk = set(fragments_dir.rglob("*.md"))
    unlisted = sorted(str(p.relative_to(fragments_dir).as_posix()) for p in on_disk - set(listed))
    if unlisted:
        raise SeedError("fragments not listed in seed.json: " + ", ".join(unlisted))

    included = set()

    def expand(match: "re.Match[str]") -> str:
        path = src / match.group(1)
        included.add(path)
        return read(path)

    text = "".join(INCLUDE.sub(expand, without_notes(read(p))) for p in listed)

    orphans = sorted(str(p.relative_to(src).as_posix())
                     for p in set(f for f in (src / "installed").rglob("*") if f.is_file()) - included)
    if orphans:
        raise SeedError("installed files no fragment includes: " + ", ".join(orphans))

    for key, value in placeholders(config).items():
        text = text.replace("{{" + key + "}}", value)

    entry = CHANGELOG_ENTRY.search(text)
    if entry is None or entry.group(1) != str(config["revision"]):
        found = entry.group(1) if entry else "none"
        raise SeedError(f"the first changelog entry ({found}) does not match revision {config['revision']}")
    return text


def first_difference(a: str, b: str) -> int:
    for number, (left, right) in enumerate(zip(a.splitlines(), b.splitlines()), start=1):
        if left != right:
            return number
    return min(len(a.splitlines()), len(b.splitlines())) + 1


def main(argv: list) -> int:
    project = Path(__file__).resolve().parent
    config = json.loads(read(project / "seed.json"))
    output = (project / config["output"]).resolve()
    try:
        text = render(project, config)
    except SeedError as error:
        print(f"build.py: {error}", file=sys.stderr)
        return 2

    if argv == ["--check"]:
        committed = read(output) if output.is_file() else ""
        if committed == text:
            print(f"{output.name} matches the sources")
            return 0
        print(f"{output} differs from the sources, first at line {first_difference(committed, text)}; "
              "run build.py", file=sys.stderr)
        return 1
    if argv:
        print(__doc__, file=sys.stderr)
        return 2

    with open(output, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    print(f"wrote {output} (revision {config['revision']}, {len(text.encode('utf-8'))} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
