"""The Spec lane of a review as a worker outside the host runs it: the lane's value, its prompt, its report and its
ledger row.

A lane that runs outside the host, in codex or in a T3 child task, reads a worktree and writes nothing. The script
that started it writes the lane's report from the worker's last message: a JSON list of findings, read as the review's
settle reads a native lane's report. A message that settle would refuse is a failed run, and no report is left for it.
Each such script keeps only how it starts its worker; what the worker is told and what the run records are here.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

import clock
import ledger
import review
import routes
from prices import Tokens

FENCED_BLOCK = re.compile(r"```[A-Za-z]*\s*\n(.*?)```", re.DOTALL)
REVIEW_STAGE = "review"
LANE_TIER = routes.SECOND_TIER
CODE_REVIEW_SKILL = Path("skills") / "code-review" / "SKILL.md"


class LaneError(Exception):
    """A reason the lane's run failed, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Lane:
    """The Spec lane's action as the manager passes it: where it reads and writes, and what it reads."""
    epic: str
    worktree: Path
    report: Path
    base: str
    head: str
    files: list[str]
    docs: list[str]


def prompt_of(lane: Lane, epic: dict, plugin: Path, no_writes: str, outside_worktree: bool) -> str:
    """The task the worker gets. `no_writes` is the sentence that tells it what it may not write. A worker whose
    working folder is not the worktree gets the files by absolute path and runs git on the worktree with `-C`."""
    docs = "\n".join(f"- {each}" for each in lane.docs) or "- none"
    files = "\n".join(f"- {lane.worktree / each if outside_worktree else each}" for each in lane.files)
    git = f"git -C {lane.worktree}" if outside_worktree else "git"
    where = ([f"The code to review is in the worktree {lane.worktree}. Your own working folder is not that "
              "worktree, so read each file by the absolute path below, and run git as `git -C` on the worktree.", ""]
             if outside_worktree else [])
    return "\n".join([
        f"You are the Spec lane of the review of the epic {lane.epic}. The run is unattended: ask nothing. "
        f"{no_writes}",
        "",
        *where,
        f"Read {plugin / CODE_REVIEW_SKILL} and run its unattended mode for the spec lane alone, over "
        f"`{git} diff {lane.base} {lane.head} -- {' '.join(lane.files)}`, limited to these files:",
        files,
        "",
        "The house rules and the glossary are at these paths:",
        docs,
        "",
        f"The epic, {epic.get('title') or lane.epic}:",
        str(epic.get("description") or ""),
        "",
        "End your reply with a JSON list and nothing after it: one object for each finding, with the keys \"file\", "
        f"\"line\", \"title\", \"note\", \"size\" ({', '.join(review.SIZES)}) and \"confidence\" "
        f"({', '.join(review.CONFIDENCES)}). Write [] when you find nothing."])


def record(home: Path, main_tree: Path, epic: str, route: dict, harness: str, tokens: Tokens, seconds: int,
           outcome: str) -> None:
    """Writes the one ledger row of a lane's run on the epic: stage `review`, the second tier, the harness, the
    route's model and effort, the tokens the worker used and the wall time."""
    model, effort = ledger.text_or_none(route.get("model")), ledger.text_or_none(route.get("effort"))
    ran = ledger.Ran(tokens, harness, model, effort)
    where = replace(ledger.Where.of_pass(REVIEW_STAGE), wall_seconds=seconds)
    ledger.record_ran_or_say(home, main_tree, epic, where, ledger.Worker(None, LANE_TIER, False), ran, outcome,
                             clock.now())


def findings_text(message: str, worker: str) -> str:
    """The JSON list in the worker's last message: the whole message, else its last fenced block, else the text from
    its first bracket to its last."""
    candidates = [message.strip(), *reversed([each.strip() for each in FENCED_BLOCK.findall(message)])]
    if "[" in message and "]" in message:
        candidates.append(message[message.index("["):message.rindex("]") + 1])
    for each in candidates:
        try:
            if isinstance(json.loads(each), list):
                return each
        except ValueError:
            continue
    raise LaneError(f"{worker}'s last message holds no JSON list of findings")


def write_report(report: Path, message: str, worker: str) -> int:
    """Writes the report from the message and returns the number of findings; leaves no report when the review's
    settle would refuse it."""
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(findings_text(message, worker), encoding="utf-8")
    try:
        return len(review.lane_findings(report, review.SPEC))
    except review.ReviewError as error:
        report.unlink(missing_ok=True)
        raise LaneError(f"{worker}'s findings are not a usable report: {error}") from error
