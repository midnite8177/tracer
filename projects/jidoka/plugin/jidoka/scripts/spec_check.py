"""Reads the outcome block of a Spec check worker from the lap's scratch folder.

The scheduler imports it; no command line runs it. A Spec check worker ends
by writing its outcome block, as the spec-check skill defines it, to the
file `spec-check.json` in the lap's scratch folder. A `send back` block holds
at least one finding, each with a `kind` (`missing` or `extra`), a `file`,
a 1-based `line`, the `bead` line it rests on and a one-line `note`. A
`cannot judge` block holds a `reason`. A `pass` block needs no file.

A finding is kept on the task as JSON, so the next build reads it, and is
worded for the task's comment by `describe`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

SPEC_CHECK_REPORT = "spec-check.json"
PASS = "pass"
SEND_BACK = "send back"
CANNOT_JUDGE = "cannot judge"
MISSING = "missing"
EXTRA = "extra"
KINDS = (MISSING, EXTRA)
LEAST_LINE = 1


class SpecCheckError(Exception):
    """A reason the outcome block cannot be used, worded for the worker that writes the next one."""


@dataclass(frozen=True)
class Finding:
    """One place where the diff does not match its task: work the task asks for and the diff lacks, or work the diff
    adds that the task does not ask for."""
    kind: str
    file: str
    line: int
    bead: str
    note: str


def read_report(scratch: Path, outcome: str) -> dict:
    """The outcome block in the scratch folder, which must hold the outcome the worker reported."""
    path = scratch / SPEC_CHECK_REPORT
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise SpecCheckError(f"the Spec check's outcome block {path} cannot be read: {error}") from error
    except ValueError as error:
        raise SpecCheckError(f"the Spec check's outcome block {path} is not JSON: {error}") from error
    if not isinstance(report, dict):
        raise SpecCheckError(f"the Spec check's outcome block {path} must be a JSON object")
    if report.get("outcome") != outcome:
        raise SpecCheckError(f"the outcome block {path} holds the outcome {report.get('outcome')!r}, not {outcome!r}")
    return report


def text_of(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecCheckError(f"{what} must be a non-empty string")
    return value.strip()


def finding_of(value: object) -> Finding:
    if not isinstance(value, dict):
        raise SpecCheckError("each finding must be an object with a kind, file, line, bead and note")
    line = value.get("line")
    if not isinstance(line, int) or isinstance(line, bool) or line < LEAST_LINE:
        raise SpecCheckError(f"the line of a finding must be a whole number from {LEAST_LINE}, not {line!r}")
    kind = value.get("kind")
    if kind not in KINDS:
        raise SpecCheckError(f"the kind of a finding must be one of {', '.join(KINDS)}, not {kind!r}")
    return Finding(kind, text_of(value.get("file"), "the file of a finding"), line,
                   text_of(value.get("bead"), "the bead of a finding"),
                   text_of(value.get("note"), "the note of a finding"))


def read_findings(scratch: Path) -> list[Finding]:
    """The findings of a `send back` block; raises SpecCheckError when the block is missing or unusable."""
    raw = read_report(scratch, SEND_BACK).get("findings")
    if not isinstance(raw, list) or not raw:
        raise SpecCheckError(f"a {SEND_BACK} block must hold at least one finding")
    return [finding_of(item) for item in raw]


def read_reason(scratch: Path) -> str:
    """The reason of a `cannot judge` block; raises SpecCheckError when the block is missing or unusable."""
    return text_of(read_report(scratch, CANNOT_JUDGE).get("reason"), "reason")


def clear_report(scratch: Path) -> None:
    (scratch / SPEC_CHECK_REPORT).unlink(missing_ok=True)


def as_json(findings: list[Finding]) -> str:
    return json.dumps([asdict(finding) for finding in findings])


def from_stored(stored: object) -> list[dict]:
    """The findings a task's metadata holds, as the build action prints them; empty when it holds none."""
    if isinstance(stored, list):
        return [item for item in stored if isinstance(item, dict)]
    if not isinstance(stored, str) or not stored.strip():
        return []
    try:
        parsed = json.loads(stored)
    except ValueError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def describe(findings: list[Finding]) -> str:
    return "\n".join(f"- {finding.kind} work, {finding.file}:{finding.line}: {finding.note} (task line: "
                     f"{finding.bead})" for finding in findings)
