"""The review, the stage of a pass after the tidy, and the fix that follows it.

The scheduler calls `to_run` once every task of an epic is closed and the tidy is done. The review covers the diff
from its fixed point to the epic branch's head: the merge base with main on the epic's first review, and after that
the head the last review covered, kept in the epic's `review.head` metadata, so a pass after a red validation or a
send back reviews only the work that came since. When main was merged into the epic branch since that head, the
review's `base` is that head merged with main's side of the merge, so the diff holds none of main's hunks. Its files
are the files the epic added or changed outside every acceptance folder that also changed since the fixed point;
with none, the pass owes no review. The review cuts a detached worktree at .worktrees/review-<epic> from the epic
branch's head and hands the scheduler one `review` action for each lane that runs, so the manager starts their
workers side by side. Each lane's worker writes its findings to `review-<lane>.json` in the worktree's scratch
folder: a JSON list of {"file", "line", "title", "note", "size", "confidence"}, where size is small, medium or large
and confidence is high, medium or low. A lane that finds nothing writes an empty list.

The Comments, Standards and Spec lanes run on every review and read the files that changed since the fixed point.
The Design lane runs only on the epic's first review. A settled review that held it sets the epic's
`review.designed`, and later reviews leave it out, because it finds a refactor in almost any code it reads and on
every pass would keep the epic from settling. Its `files` are every module the epic touched, which it reads whole,
and its action carries `hints`: the functions lizard_hints.py found added or grown past the repo's limits since the
fixed point. `settle` adds a finding of low confidence to the Design lane's for each hint, so the gate lists it and
nothing fixes it, files it or holds the pass.

`settle` takes the reports of the lanes that ran at once, and refuses, writing nothing, when one is missing or
unusable. A finding of low confidence is never fixed: it joins the epic's `review.low`, which the gate comment lists.
A small or medium finding of high or medium confidence goes to the one fix worker, as the `fix` action, kept in
`review.fixes` until the fix settles. A large finding becomes an open task outside the epic, linked discovered-from
to it, for a bench or a later epic, filed when the review settles; the epic keeps only the tasks it was planned
with. The settled review records the head it covered as `review.head` and counts its pass through pass_ledger.py.

The fix worker, on the standard tier, fixes those findings in a detached worktree at .worktrees/fix-<epic> and
commits nothing. `settle_fix` refuses, writing nothing, when the worktree changed a path outside the epic's files, or
is gone or at another head than the worker started from. Otherwise it commits the change as one commit, "Review
fixes", fast-forwards the epic branch to it under the merge lock, and moves `review.head` to it, so no later review
covers the fixes again and the pass owes no other review. Validation then runs everything.

Everything here writes to bd with BEADS_ACTOR set to jidoka.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import lizard_hints
import pass_ledger
import pass_support
from bench import WORKTREE_FOLDER
from caps import metadata_of
from commands import FACTORY_ACTOR, SCRATCH_FOLDER, bd_show, capture, env_as_factory, head_of, run, set_metadata, \
    unset_metadata
from discovered import DISCOVERED_FROM
from pass_support import (MAIN_BRANCH, PassError, Stage, StageToRun, accepts_any_change, created_id, epic_files,
                          every_file, located_texts, remove_worktree, shortened_title, worktree_at)

COMMENTS = "comments"
STANDARDS = "standards"
SPEC = "spec"
DESIGN = "design"
DIFF_LANES = (COMMENTS, STANDARDS, SPEC)
LANES = (*DIFF_LANES, DESIGN)
SMALL, MEDIUM, LARGE = "small", "medium", "large"
SIZES = (SMALL, MEDIUM, LARGE)
HIGH, LOW = "high", "low"
CONFIDENCES = (HIGH, MEDIUM, LOW)
REVIEW_ACTION = "review"
FIX_ACTION = "fix"
REVIEW_PREFIX = "review-"
FIX_PREFIX = "fix-"
REPORT_PREFIX = "review-"
FIX_COMMIT_MESSAGE = "Review fixes"
HEAD_KEY = "review.head"
LOW_KEY = "review.low"
FIXES_KEY = "review.fixes"
DESIGNED_KEY = "review.designed"


class ReviewError(PassError):
    """A reason the review or the fix writes nothing more, worded for the person who reads stderr."""


FIX_STAGE = Stage(name="fix", action=FIX_ACTION, prefix=FIX_PREFIX, state_key=None, commit_message=FIX_COMMIT_MESSAGE,
                  allowed_kind="files the epic added or changed", files_key="files", wants=every_file, report=None,
                  error=ReviewError)


@dataclass(frozen=True)
class Finding:
    """One thing a review lane found at a line of a file, with how much work its fix is and how sure the lane is."""
    lane: str
    file: str
    line: int
    title: str
    note: str
    size: str
    confidence: str

    @property
    def is_unsure(self) -> bool:
        return self.confidence == LOW

    @property
    def is_fixable(self) -> bool:
        return not self.is_unsure and self.size != LARGE

    @property
    def is_large(self) -> bool:
        return not self.is_unsure and self.size == LARGE

    def fields(self) -> dict:
        return {"lane": self.lane, "file": self.file, "line": self.line, "title": self.title, "note": self.note,
                "size": self.size, "confidence": self.confidence}


@dataclass(frozen=True)
class ReviewToRun:
    """The review the lanes make: the lanes that run, the fixed point and the head it covers, its worktree, the files
    that changed since the fixed point, which the diff lanes read, the modules the epic touched, which the Design lane
    reads whole, and the lizard hints for the functions that grew since the fixed point, empty when the Design lane
    does not run."""
    epic: str
    lanes: tuple[str, ...]
    branch: str
    base: str
    head: str
    worktree: Path
    files: list[str]
    modules: list[str]
    hints: list[lizard_hints.Hint]

    def report(self, lane: str) -> Path:
        return self.worktree / SCRATCH_FOLDER / f"{REPORT_PREFIX}{lane}.json"

    def actions(self) -> list[dict]:
        return [self.action(lane) for lane in self.lanes]

    def action(self, lane: str) -> dict:
        printed = {"action": REVIEW_ACTION, "lane": lane, "epic": self.epic, "branch": self.branch,
                   "base": self.base, "head": self.head, "worktree": str(self.worktree),
                   "scratch": str(self.worktree / SCRATCH_FOLDER), "report": str(self.report(lane)),
                   "files": self.files}
        if lane == DESIGN:
            printed["files"] = self.modules
            printed["hints"] = [each.fields() for each in self.hints]
        return printed

    def hint_findings(self) -> list[Finding]:
        """The Design lane's findings for the hints: of low confidence, so the gate lists them and nothing fixes or
        files them."""
        return [Finding(DESIGN, each.file, each.line, f"Lizard hint: {each.name} passes the {each.metric} limit",
                        hint_note(each), MEDIUM, LOW) for each in self.hints]


@dataclass(frozen=True)
class Reviewed:
    """What a settled review did: the head it covered, the findings it sent to the fix worker, the tasks it filed
    and the findings it left for the gate."""
    head: str
    fixes: list[Finding]
    filed: list[str]
    unsure: list[Finding]

    def fields(self) -> dict:
        return {"head": self.head, "fixes": [each.fields() for each in self.fixes], "filed": self.filed,
                "low": [each.fields() for each in self.unsure]}


@dataclass(frozen=True)
class FixToRun:
    """The fix a worker makes: the commit it starts from, its worktree and the files it may touch, and the findings."""
    stage: StageToRun
    findings: list[Finding]

    def fields(self) -> dict:
        return {**self.stage.fields(), "findings": [each.fields() for each in self.findings]}


@dataclass(frozen=True)
class Fixed:
    """What a settled fix did: the commit the epic branch now ends with, and the files it changed."""
    head: str
    changed: list[str]

    def fields(self) -> dict:
        return {"head": self.head, "changed": self.changed}


def finding_of(lane: str, value: object, where: str) -> Finding:
    texts, line = located_texts(value, where, "a file, line, title, note, size and confidence")
    size = value.get("size")
    if size not in SIZES:
        raise ReviewError(f"the size of {where} must be one of {', '.join(SIZES)}, not {size!r}")
    confidence = value.get("confidence")
    if confidence not in CONFIDENCES:
        raise ReviewError(f"the confidence of {where} must be one of {', '.join(CONFIDENCES)}, not {confidence!r}")
    return Finding(lane, texts["file"], line, texts["title"], texts["note"], size, confidence)


def stored_findings(shown: dict, key: str) -> list[Finding]:
    """The findings the epic's metadata keeps under the key; empty when it keeps none."""
    value = metadata_of(shown).get(key)
    if value in (None, ""):
        return []
    try:
        listed = json.loads(value) if isinstance(value, str) else value
        if not isinstance(listed, list):
            raise TypeError("not a list")
        return [finding_of(str(each["lane"]), each, f"a finding in {key}") for each in listed]
    except (ValueError, KeyError, TypeError, ReviewError, PassError) as error:
        raise ReviewError(f"the {key} metadata of the epic cannot be read: {error!r}") from error


def low_confidence_lines(shown: dict) -> list[str]:
    """The gate comment's list of the review findings of low confidence, which no fix touched, or no line when
    none."""
    rows = [f"- {each.lane}, {each.file}:{each.line}: {each.title}. {each.note}"
            for each in stored_findings(shown, LOW_KEY)]
    if not rows:
        return []
    return ["", "Review findings of low confidence, which were never fixed:", *rows]


def as_json(findings: list[Finding]) -> str:
    return json.dumps([each.fields() for each in findings])


def lane_findings(report: Path, lane: str) -> list[Finding]:
    try:
        listed = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReviewError(f"the {lane} lane's report {report} is missing or is not JSON ({error}), so nothing was "
                          "written") from error
    if not isinstance(listed, list):
        raise ReviewError(f"the {lane} lane's report {report} is not a JSON list, so nothing was written")
    return [finding_of(lane, each, f"finding {number} of the {lane} lane's report") for number, each in
            enumerate(listed, 1)]


def branch_head(branch: str, main_tree: Path) -> str:
    head = head_of(f"refs/heads/{branch}", main_tree)
    if head is None:
        raise ReviewError(f"the epic branch {branch} does not exist")
    return head


def fixed_point(shown: dict, head: str, main_tree: Path) -> str:
    """The head the last review covered, or the merge base with main for the epic's first review, or when the
    recorded head is no longer behind the epic branch."""
    reviewed = str(metadata_of(shown).get(HEAD_KEY) or "")
    if reviewed and capture(["git", "merge-base", "--is-ancestor", reviewed, head], main_tree, None).returncode == 0:
        return reviewed
    return run(["git", "merge-base", MAIN_BRANCH, head], main_tree, None).strip()


def own_work_base(base: str, head: str, main_tree: Path) -> str:
    """The commit a diff to the head shows only the epic's own work against. When main was merged into the epic
    branch since the base, it is the base merged with the main commit that merge brought in, so main's hunks cancel
    out of the diff; otherwise, or when that merge conflicts, it is the base."""
    mainline = run(["git", "merge-base", MAIN_BRANCH, head], main_tree, None).strip()
    if capture(["git", "merge-base", "--is-ancestor", mainline, base], main_tree, None).returncode == 0:
        return base
    merged = capture(["git", "merge-tree", "--write-tree", base, mainline], main_tree, None)
    if merged.returncode != 0:
        return base
    return run(["git", "-c", f"user.name={FACTORY_ACTOR}", "-c", f"user.email={FACTORY_ACTOR}@localhost", "commit-tree",
                merged.stdout.strip(), "-p", base, "-p", mainline, "-m", f"{base} with {MAIN_BRANCH}"],
               main_tree, None).strip()


def review_owed(epic: str, shown: dict, branch: str, settings: dict, main_tree: Path) -> ReviewToRun | None:
    """The review this pass still owes, over which lanes, base and files, or None when the epic's files hold no change
    since the fixed point or a fix is still owed. The Design lane and its hints are left out once a review that held
    them has settled. It cuts no worktree: the path in the result is where one belongs."""
    if stored_findings(shown, FIXES_KEY):
        return None
    head = branch_head(branch, main_tree)
    base = own_work_base(fixed_point(shown, head, main_tree), head, main_tree)
    since = set(run(["git", "diff", "--name-only", base, head], main_tree, None).splitlines())
    modules = epic_files(head, settings, main_tree)
    files = [path for path in modules if path in since]
    if not files:
        return None
    path = main_tree / WORKTREE_FOLDER / f"{REVIEW_PREFIX}{epic}"
    if metadata_of(shown).get(DESIGNED_KEY):
        return ReviewToRun(epic, DIFF_LANES, branch, base, head, path, files, modules, [])
    hints = lizard_hints.hints_between(base, head, files, lizard_hints.limits_of(settings), main_tree)
    return ReviewToRun(epic, LANES, branch, base, head, path, files, modules, hints)


def to_run(epic: str, shown: dict, branch: str, settings: dict, home: Path, main_tree: Path) -> ReviewToRun | None:
    """The review this pass still owes, with its worktree cut at the epic branch's head for the lanes' workers."""
    owed = review_owed(epic, shown, branch, settings, main_tree)
    if owed is not None:
        worktree_at(owed.worktree, owed.head, home, main_tree)
    return owed


def hint_note(hint: lizard_hints.Hint) -> str:
    grew = "is new" if hint.was is None else f"grew from {hint.was}"
    return f"{hint.name} {grew}, to a {hint.metric} of {hint.value} against the limit of {hint.limit}."


def fix_owed(epic: str, shown: dict, branch: str, settings: dict, main_tree: Path) -> FixToRun | None:
    """The fix the last review left owed, or None when it left nothing to fix. It cuts no worktree: the path in the
    result is where one belongs."""
    findings = stored_findings(shown, FIXES_KEY)
    if not findings:
        return None
    head = branch_head(branch, main_tree)
    return FixToRun(StageToRun(FIX_STAGE, epic, branch, head, FIX_STAGE.worktree_of(epic, main_tree),
                               epic_files(head, settings, main_tree)), findings)


def fix_to_run(epic: str, shown: dict, branch: str, settings: dict, home: Path, main_tree: Path) -> FixToRun | None:
    """The fix the last review left owed, with its worktree cut at the epic branch's head for the fix worker."""
    owed = fix_owed(epic, shown, branch, settings, main_tree)
    if owed is not None:
        worktree_at(owed.stage.worktree, owed.stage.head, home, main_tree)
    return owed


def task_title(finding: Finding) -> str:
    return shortened_title(f"{finding.title} in {finding.file}")


def task_description(epic: str, finding: Finding) -> str:
    return "\n".join(["## What", "",
                      f"The {finding.lane} lane of the review of the epic {epic} found this at "
                      f"{finding.file}:{finding.line}, and sized it large, with {finding.confidence} confidence, so it "
                      "was filed outside the epic:", "", f"{finding.title}: {finding.note}", "",
                      "## Demo", "", f"The code in {finding.file} no longer has this problem, and the tests that "
                      "reach it pass.", "", "## Seams", "", f"The code in {finding.file}, through the tests that "
                      "reach it."])


def file_large(epic: str, large: list[Finding], main_tree: Path) -> list[str]:
    """Files a task outside the epic for each large finding, linked discovered-from to the epic, for a bench or a
    later epic. It has no area, so no lap of this epic takes it."""
    env = env_as_factory()
    return [created_id(run(["bd", "create", "--title", task_title(each), "--description", task_description(epic, each),
                            "--type=task", "--deps", f"{DISCOVERED_FROM}:{epic}", "--json"], main_tree, env))
            for each in large]


def review_comment(owed: ReviewToRun, findings: list[Finding], fixes: list[Finding], large: list[Finding],
                   unsure: list[Finding]) -> str:
    lines = [f"Review of {owed.base}..{owed.head} over {len(owed.files)} files: {len(findings)} findings, "
             f"{len(fixes)} for the fix worker, {len(large)} large filed outside the epic, {len(unsure)} of low "
             "confidence for the gate."]
    lines += [f"- {each.lane}, {each.size}, {each.confidence}: {each.file}:{each.line} {each.title}"
              for each in findings]
    return "\n".join(lines)


def settle(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Reviewed:
    """Takes the reports of the lanes that ran: sends the findings to fix to the fix worker, keeps the unsure ones
    for the gate, and files the large ones outside the epic."""
    shown = bd_show(epic, main_tree)
    if shown is None:
        raise ReviewError(f"bd show printed nothing usable for {epic}")
    owed = review_owed(epic, shown, branch, settings, main_tree)
    if owed is None:
        raise ReviewError(f"{epic} waits on no review, so nothing was written")
    findings = [finding for lane in owed.lanes for finding in lane_findings(owed.report(lane), lane)]
    findings += owed.hint_findings()
    fixes = [each for each in findings if each.is_fixable]
    large = [each for each in findings if each.is_large]
    unsure = [each for each in findings if each.is_unsure]
    kept_unsure = stored_findings(shown, LOW_KEY) + unsure
    remove_worktree(owed.worktree, main_tree)
    env = env_as_factory()
    run(["bd", "comment", epic, review_comment(owed, findings, fixes, large, unsure)], main_tree, env)
    owed_fix = set_metadata((FIXES_KEY, as_json(fixes))) if fixes else []
    designed = set_metadata((DESIGNED_KEY, 1)) if DESIGN in owed.lanes else []
    run(["bd", "update", epic, *set_metadata((HEAD_KEY, owed.head)), *pass_ledger.counted_by_review(shown),
         *set_metadata((LOW_KEY, as_json(kept_unsure))), *owed_fix, *designed], main_tree, env)
    return Reviewed(owed.head, fixes, file_large(epic, large, main_tree), unsure)


def settle_fix(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Fixed:
    """Commits what the fix worker left as one commit on the epic branch, and moves the review's fixed point past
    it."""
    shown = bd_show(epic, main_tree)
    if shown is None:
        raise ReviewError(f"bd show printed nothing usable for {epic}")
    owed = fix_owed(epic, shown, branch, settings, main_tree)
    if owed is None:
        raise ReviewError(f"{epic} waits on no fix, so nothing was written")
    pass_support.refuse_a_lost_worktree(owed.stage)
    settled = pass_support.settle_worktree(owed.stage, accepts_any_change, home, main_tree)
    env = env_as_factory()
    run(["bd", "comment", epic, fix_comment(settled.changed, settled.head)], main_tree, env)
    run(["bd", "update", epic, *set_metadata((HEAD_KEY, settled.head)), *unset_metadata(FIXES_KEY)], main_tree, env)
    return Fixed(settled.head, settled.changed)


def fix_comment(changed: list[str], head: str) -> str:
    if not changed:
        return f"The review's fix changed no file, and the epic branch stays at {head}."
    return "\n".join([f"The review's fix changed {len(changed)} files, in the commit {head}:",
                      *(f"- {path}" for path in changed)])
