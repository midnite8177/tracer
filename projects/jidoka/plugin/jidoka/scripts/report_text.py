"""The text of a stage's report and of what it writes to bd: the JSON file a worker writes, the fields of one finding, a
title cut to length, and the tail of a command's output."""
from __future__ import annotations

import json
from pathlib import Path

TITLE_LIMIT = 80
OUTPUT_TAIL_LINES = 40
TEXT_FIELDS = ("file", "title", "note")
LEAST_LINE = 1


class ReportError(Exception):
    """A finding in a report that lacks a field or holds one of the wrong shape, worded for the worker that writes the
    next report."""


def tail_of(output: str) -> str:
    """The last lines of a command's output, which is where a failure says what went wrong."""
    return "\n".join(output.strip().splitlines()[-OUTPUT_TAIL_LINES:])


def shortened_title(text: str) -> str:
    """The text cut to TITLE_LIMIT characters, with an ellipsis where it was cut."""
    return text if len(text) <= TITLE_LIMIT else f"{text[:TITLE_LIMIT - 3].rstrip()}..."


def listed_report(path: Path, what: str, error: type[Exception]) -> list:
    """The JSON list in the report file. A file that is missing or is not JSON, or JSON that is not a list, raises the
    caller's error, worded around `what`, the words that name the report."""
    try:
        listed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as cause:
        raise error(f"{what} is missing or is not JSON ({cause}), so nothing was written") from cause
    if not isinstance(listed, list):
        raise error(f"{what} is not a JSON list, so nothing was written")
    return listed


def parsed_report(path: Path, what: str, error: type[Exception]) -> object:
    """The JSON value in the report file. A file that cannot be read, or is not JSON, raises the caller's error, worded
    around `what`, the words that name the report."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as cause:
        raise error(f"{what} cannot be read: {cause}") from cause
    except ValueError as cause:
        raise error(f"{what} is not JSON: {cause}") from cause


def located_texts(value: object, where: str, shape: str) -> tuple[dict[str, str], int]:
    """The file, title and note, trimmed, and the line of one finding in a report.

    `where` names the finding in a refusal, and `shape` lists the fields its object must hold. A finding that lacks
    one raises ReportError.
    """
    if not isinstance(value, dict):
        raise ReportError(f"{where} must be an object with {shape}")
    texts = {}
    for field in TEXT_FIELDS:
        text = value.get(field)
        if not isinstance(text, str) or not text.strip():
            raise ReportError(f"{where} must name its {field}")
        texts[field] = text.strip()
    line = value.get("line")
    if not isinstance(line, int) or isinstance(line, bool) or line < LEAST_LINE:
        raise ReportError(f"the line of {where} must be a whole number from {LEAST_LINE}, not {line!r}")
    return texts, line
