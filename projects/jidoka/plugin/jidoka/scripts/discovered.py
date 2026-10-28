"""Files the work a lap or a pass discovers, and blocks a lap's task on the discovered task it cannot finish without.

The scheduler imports it; no command line runs it. A worker never files a
bead. A stage that found work ends with a discovered-work report, the JSON
file `discovered.json` in its worktree's scratch folder: a list of findings,
each with
  title        the new bead's title.
  description  what was seen and where.
  placement    where it goes: `blocks`, `epic` or `outside`.
  task         optional, and only on a `blocks` finding: the id of a task the epic already holds that the lap's task
               cannot finish without. The lap's task then waits on that task and the finding files nothing.
`blocks` is work inside the epic that the lap's task cannot finish without,
so only a lap's report holds it.
`epic` is work inside the epic that acceptance would reject the epic without.
`outside` is everything else, and the new bead has no parent.

A lap's finding is linked discovered-from to the lap's task. A pass's
finding inside the epic is the epic's child and has no other link, because
bd keeps one link per pair of beads; outside the epic it is linked
discovered-from to the epic. A bead inside the epic gets an area and the
simple track, so it is a task the factory takes once it is ready. A task
that cannot finish waits on each `blocks` task, new or named by `task`. The lap ends blocked:
stage `blocked`, status open, no assignee and no `human` label, so it is
ready again, with a new lap on its kept worktree and branch, once every
task it waits on is closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import lap_outcomes
import lap_record
from commands import BeadNotCreated, bd_list, env_as_factory, run
from epic_task import NewTask, file_outside, file_task
from report_text import parsed_report

DISCOVERED_REPORT = "discovered.json"
BLOCKED_PREFIX = "Blocked: "
BLOCKS = "blocks"
EPIC = "epic"
OUTSIDE = "outside"
PLACEMENTS = (BLOCKS, EPIC, OUTSIDE)


class DiscoveryError(Exception):
    """A reason a discovered-work report cannot be filed, worded for the worker that writes the next one."""


@dataclass(frozen=True)
class Finding:
    """One piece of discovered work, and where it goes. `task` is the id of a task the epic already holds, for a
    `blocks` finding that names one instead of asking for a new bead; None otherwise."""
    title: str
    description: str
    placement: str
    task: str | None


@dataclass(frozen=True)
class Filed:
    """A finding and the id of the bead it became."""
    bead: str
    finding: Finding


def text_of(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiscoveryError(f"{what} must be a non-empty string")
    return value.strip()


def finding_of(value: object) -> Finding:
    if not isinstance(value, dict):
        raise DiscoveryError("each finding must be an object with a title, a description and a placement")
    placement = value.get("placement")
    if placement not in PLACEMENTS:
        raise DiscoveryError(f"the placement of a finding must be one of {', '.join(PLACEMENTS)}, not {placement!r}")
    task = text_of(value["task"], "the task of a finding") if "task" in value else None
    if task is not None and placement != BLOCKS:
        raise DiscoveryError(f"a finding names a task only when its placement is {BLOCKS}, not {placement}")
    return Finding(text_of(value.get("title"), "the title of a finding"),
                   text_of(value.get("description"), "the description of a finding"), placement, task)


def read_findings(scratch: Path) -> list[Finding]:
    """The findings in the scratch folder; none when the stage left no report, and DiscoveryError when it is
    unusable."""
    path = scratch / DISCOVERED_REPORT
    if not path.exists():
        return []
    report = parsed_report(path, f"the discovered-work report {path}", DiscoveryError)
    if not isinstance(report, list):
        raise DiscoveryError(f"the discovered-work report {path} must be a JSON list of findings")
    return [finding_of(item) for item in report]


def blockers_in(findings: list[Finding]) -> list[Finding]:
    return [finding for finding in findings if finding.placement == BLOCKS]


def file_finding(finding: Finding, found_in: str, area: str, epic: str, main_tree: Path) -> Filed:
    """Creates the bead for one finding, linked discovered-from to the bead it was found in unless that bead is its
    parent; inside the epic it also gets the area.

    bd keeps one link per pair of beads, so a finding inside the epic that the epic itself found keeps only the
    parent-child link, which already says where it came from.
    """
    try:
        if finding.placement != OUTSIDE:
            origin = None if found_in == epic else found_in
            task = NewTask(finding.title, finding.description, area, lap_record.SIMPLE_TRACK)
            return Filed(file_task(epic, task, origin, env_as_factory(), main_tree), finding)
        return Filed(file_outside(finding.title, finding.description, found_in, [], main_tree), finding)
    except BeadNotCreated as error:
        raise DiscoveryError(f"bd create did not print the new bead's id: {error.printed.strip()[:200]!r}") from error


def file_findings(findings: list[Finding], found_in: str, area: str, epic: str, main_tree: Path) -> list[Filed]:
    return [file_finding(finding, found_in, area, epic, main_tree) for finding in findings]


def other_tasks_of(epic: str, found_in: str, main_tree: Path) -> set[str]:
    """The ids of the tasks the epic holds, closed ones included, other than the task a finding was found in."""
    return {str(bead.get("id")) for bead in bd_list(["--parent", epic, "--all", "--limit", "0"], main_tree)
            if bead.get("issue_type") != "epic" and str(bead.get("id")) != found_in}


def file_blockers(findings: list[Finding], found_in: str, area: str, epic: str, main_tree: Path) -> list[Filed]:
    """Files each finding, except a blocking one that names a task: that finding becomes the named task instead of a
    new bead. The epic's tasks are read once, and only when a finding names one. A name that is not another task of
    the epic refuses the report, and nothing is filed."""
    named = {finding.task for finding in findings if finding.task is not None}
    unknown = sorted(named - other_tasks_of(epic, found_in, main_tree)) if named else []
    if unknown:
        raise DiscoveryError(f"the epic holds no task {', '.join(unknown)} other than {found_in}, so a finding cannot "
                             "name it as its task")
    return [Filed(finding.task, finding) if finding.task is not None
            else file_finding(finding, found_in, area, epic, main_tree) for finding in findings]


def clear_report(scratch: Path) -> None:
    (scratch / DISCOVERED_REPORT).unlink(missing_ok=True)


def block(task: str, tries: int, blockers: list[Filed], worktree: Path, branch: str, main_tree: Path) -> None:
    """Makes the task wait on each blocker and ends its lap blocked, under the actor jidoka."""
    env = env_as_factory()
    for filed in blockers:
        run(["bd", "dep", "add", task, "--blocked-by", filed.bead], main_tree, env)
    waiting = "; ".join(f"{filed.bead} ({filed.finding.title})" for filed in blockers)
    run(["bd", "comment", task, f"{BLOCKED_PREFIX}the task cannot finish without {waiting}. The worktree {worktree} "
                                f"and the branch {branch} keep the work. The task gets a new lap once "
                                f"{'it' if len(blockers) == 1 else 'they'} merge."], main_tree, env)
    run(["bd", "update", task, *lap_record.resting_with_tries(lap_outcomes.BLOCKED, tries)], main_tree, env)
