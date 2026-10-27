"""The review, the stage of a pass after the tidy, and the fix that follows it.

The scheduler calls `to_run` once every task of an epic is closed and the tidy is done. The review covers the diff
from its fixed point to the epic branch's head: the merge base with main on the epic's first review, and after that
the head the last review covered, kept in the epic's `review.head` metadata, so a pass after a send back or a large
finding reviews only the work that came since. Its files are the files the epic added or changed outside every
acceptance folder that also changed since the fixed point; with none, the pass owes no review. The review cuts a
detached worktree at .worktrees/review-<epic> from the epic branch's head and hands the scheduler one `review` action
for each lane, Comments, Standards, Spec and Design, so the manager starts their workers side by side. Each lane's
worker writes its findings to `review-<lane>.json` in the worktree's scratch folder: a JSON list of {"file", "line",
"title", "note", "size", "confidence"}, where size is small, medium or large and confidence is high, medium or low.
A lane that finds nothing writes an empty list.

The three diff lanes read the files that changed since the fixed point. The Design lane's `files` are instead every
module the epic touched, which it reads whole, and its action carries `hints`: the functions lizard_hints.py found
added or grown past the repo's limits since the fixed point. `settle` adds a finding of low confidence to the Design
lane's for each hint, so the gate lists it and nothing fixes it, files it or holds the pass.

`settle` takes the four reports at once, and refuses, writing nothing, when one is missing or unusable. A finding
of low confidence is never fixed: it joins the epic's `review.low`, which the gate comment lists. A small or medium
finding of high or medium confidence goes to the one fix worker, as the `fix` action, kept in `review.fixes` until
the fix settles. A large finding becomes a task in the epic for the next pass, filed once the fix settles, or at once
when there is nothing to fix; filing one takes `cleanup.state` and `tidy.state` off the epic, so the next pass cleans
and tidies again. The settled review records the head it covered as `review.head` and counts itself in
`review.passes`.

The fix worker, on the standard tier, fixes those findings in a detached worktree at .worktrees/fix-<epic> and commits
nothing. `settle_fix` refuses, writing nothing, when the worktree changed a path outside the epic's files. Otherwise
it commits the change as one commit, "Review fixes", fast-forwards the epic branch to it under the merge lock, and
moves `review.head` to it, so no later review covers the fixes again. Validation then runs everything.

The pass count is capped at three. An epic that holds open tasks after its third review would start a fourth pass:
`parks_at_the_cap` says so, and `park_at_the_cap` parks the epic with a question instead, and records the count in
`pass.asked` so that each pass past the cap asks once. Taking the human label off runs the next pass.
Everything here writes to bd with BEADS_ACTOR set to jidoka.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cleanup
import git_exclude
import lizard_hints
import park
import private_docs
import tidy
from bench import WORKTREE_FOLDER, hide_worktrees
from commands import bd_show, capture, env_as_factory, head_of, run
from validation import (CLEANUP_STATE_KEY, LOW_KEY, MAIN_BRANCH, SCRATCH_FOLDER, TIDY_STATE_KEY, TITLE_LIMIT,
                        file_task, move_epic_branch, remove_worktree)

COMMENTS = "comments"
STANDARDS = "standards"
SPEC = "spec"
DESIGN = "design"
LANES = (COMMENTS, STANDARDS, SPEC, DESIGN)
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
PASSES_KEY = "review.passes"
FIXES_KEY = "review.fixes"
LARGE_KEY = "review.large"
ASKED_KEY = "pass.asked"
PASS_CAP = 3
TEXT_FIELDS = ("file", "title", "note")
LEAST_LINE = 1
NEXT_PASS = "Run another pass"
DROP = "Drop the epic"


class ReviewError(Exception):
    """A reason the review or the fix writes nothing more, worded for the person who reads stderr."""


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
    """The review the lanes make: the fixed point and the head it covers, its worktree, the files that changed since
    the fixed point, which the diff lanes read, the modules the epic touched, which the Design lane reads whole, and
    the lizard hints for the functions that grew since the fixed point."""
    epic: str
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
        return [self.action(lane) for lane in LANES]

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
    """The fix a worker makes: the commit it starts from, its worktree, the files it may touch, and the findings."""
    epic: str
    branch: str
    head: str
    worktree: Path
    files: list[str]
    findings: list[Finding]

    def fields(self) -> dict:
        return {"action": FIX_ACTION, "epic": self.epic, "branch": self.branch, "head": self.head,
                "worktree": str(self.worktree), "scratch": str(self.worktree / SCRATCH_FOLDER), "files": self.files,
                "findings": [each.fields() for each in self.findings]}


@dataclass(frozen=True)
class Fixed:
    """What a settled fix did: the commit the epic branch now ends with, the files it changed, and the tasks filed
    for the review's large findings."""
    head: str
    changed: list[str]
    filed: list[str]

    def fields(self) -> dict:
        return {"head": self.head, "changed": self.changed, "filed": self.filed}


def metadata_of(shown: dict) -> dict:
    metadata = shown.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def count_of(shown: dict, key: str) -> int:
    value = metadata_of(shown).get(key)
    try:
        return int(value) if value not in (None, "") else 0
    except (TypeError, ValueError) as error:
        raise ReviewError(f"the {key} metadata of the epic is not a whole number: {value!r}") from error


def finding_of(lane: str, value: object, where: str) -> Finding:
    if not isinstance(value, dict):
        raise ReviewError(f"{where} must be an object with a file, line, title, note, size and confidence")
    texts = {}
    for field in TEXT_FIELDS:
        text = value.get(field)
        if not isinstance(text, str) or not text.strip():
            raise ReviewError(f"{where} must name its {field}")
        texts[field] = text.strip()
    line = value.get("line")
    if not isinstance(line, int) or isinstance(line, bool) or line < LEAST_LINE:
        raise ReviewError(f"the line of {where} must be a whole number from {LEAST_LINE}, not {line!r}")
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
    except (ValueError, KeyError, TypeError, ReviewError) as error:
        raise ReviewError(f"the {key} metadata of the epic cannot be read: {error!r}") from error


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


def worktree_at(path: Path, head: str, home: Path, main_tree: Path) -> None:
    """Cuts the detached worktree at the head, again when it holds another commit, with its scratch folder."""
    if path.is_dir() and head_of("HEAD", path) != head:
        remove_worktree(path, main_tree)
    if not path.is_dir():
        capture(["git", "worktree", "prune"], main_tree, None)
        hide_worktrees(main_tree)
        run(["git", "worktree", "add", "-q", "--detach", str(path), head], main_tree, None)
        try:
            private_docs.share(main_tree, path.resolve(), home)
        except private_docs.ClashError as error:
            remove_worktree(path, main_tree)
            raise ReviewError(str(error)) from error
    git_exclude.add(git_exclude.exclude_file(main_tree), [git_exclude.exclude_line(SCRATCH_FOLDER, True)])
    (path / SCRATCH_FOLDER).mkdir(exist_ok=True)


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


def to_run(epic: str, shown: dict, branch: str, settings: dict, home: Path, main_tree: Path) -> ReviewToRun | None:
    """The review this pass still owes, or None when the epic's files hold no change since the fixed point or a fix
    is still owed."""
    if stored_findings(shown, FIXES_KEY):
        return None
    head = branch_head(branch, main_tree)
    base = fixed_point(shown, head, main_tree)
    since = set(run(["git", "diff", "--name-only", base, head], main_tree, None).splitlines())
    modules = tidy.epic_files(head, settings, main_tree)
    files = [path for path in modules if path in since]
    if not files:
        return None
    path = main_tree / WORKTREE_FOLDER / f"{REVIEW_PREFIX}{epic}"
    worktree_at(path, head, home, main_tree)
    hints = lizard_hints.hints_between(base, head, files, lizard_hints.limits_of(settings), main_tree)
    return ReviewToRun(epic, branch, base, head, path, files, modules, hints)


def hint_note(hint: lizard_hints.Hint) -> str:
    grew = "is new" if hint.was is None else f"grew from {hint.was}"
    return f"{hint.name} {grew}, to a {hint.metric} of {hint.value} against the limit of {hint.limit}."


def fix_to_run(epic: str, shown: dict, branch: str, settings: dict, home: Path, main_tree: Path) -> FixToRun | None:
    """The fix the last review left owed, or None when it left nothing to fix."""
    findings = stored_findings(shown, FIXES_KEY)
    if not findings:
        return None
    head = branch_head(branch, main_tree)
    path = main_tree / WORKTREE_FOLDER / f"{FIX_PREFIX}{epic}"
    worktree_at(path, head, home, main_tree)
    return FixToRun(epic, branch, head, path, tidy.epic_files(head, settings, main_tree), findings)


def task_title(finding: Finding) -> str:
    title = f"{finding.title} in {finding.file}"
    return title if len(title) <= TITLE_LIMIT else f"{title[:TITLE_LIMIT - 3].rstrip()}..."


def task_description(finding: Finding) -> str:
    return "\n".join(["## What", "",
                      f"The {finding.lane} lane of the review found this at {finding.file}:{finding.line}, and sized "
                      f"it large, with {finding.confidence} confidence:", "", f"{finding.title}: {finding.note}", "",
                      "## Demo", "", f"The next review's {finding.lane} lane no longer finds it in {finding.file}.",
                      "", "## Seams", "", f"The code in {finding.file}, through the tests that reach it."])


def file_large(epic: str, large: list[Finding], main_tree: Path) -> list[str]:
    """Files a task in the epic for each large finding, in the area of the file it names, and starts the next pass
    over with a test cleanup and a tidy."""
    if not large:
        return []
    filed = [file_task(epic, task_title(each), task_description(each), each.file, main_tree) for each in large]
    run(["bd", "update", epic, "--unset-metadata", CLEANUP_STATE_KEY, "--unset-metadata", TIDY_STATE_KEY],
        main_tree, env_as_factory())
    return filed


def review_comment(owed: ReviewToRun, findings: list[Finding], fixes: list[Finding], large: list[Finding],
                   unsure: list[Finding]) -> str:
    lines = [f"Review of {owed.base}..{owed.head} over {len(owed.files)} files: {len(findings)} findings, "
             f"{len(fixes)} for the fix worker, {len(large)} large for the next pass, {len(unsure)} of low "
             "confidence for the gate."]
    lines += [f"- {each.lane}, {each.size}, {each.confidence}: {each.file}:{each.line} {each.title}"
              for each in findings]
    return "\n".join(lines)


def settle(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Reviewed:
    """Takes the four lanes' reports: sends the findings to fix to the fix worker, keeps the unsure ones for the
    gate, and files the large ones when nothing waits to be fixed."""
    shown = bd_show(epic, main_tree)
    if shown is None:
        raise ReviewError(f"bd show printed nothing usable for {epic}")
    owed = to_run(epic, shown, branch, settings, home, main_tree)
    if owed is None:
        raise ReviewError(f"{epic} waits on no review, so nothing was written")
    findings = [finding for lane in LANES for finding in lane_findings(owed.report(lane), lane)]
    findings += owed.hint_findings()
    fixes = [each for each in findings if each.is_fixable]
    large = [each for each in findings if each.is_large]
    unsure = [each for each in findings if each.is_unsure]
    kept_unsure = stored_findings(shown, LOW_KEY) + unsure
    remove_worktree(owed.worktree, main_tree)
    env = env_as_factory()
    run(["bd", "comment", epic, review_comment(owed, findings, fixes, large, unsure)], main_tree, env)
    owed_fix = (["--set-metadata", f"{FIXES_KEY}={as_json(fixes)}", "--set-metadata", f"{LARGE_KEY}={as_json(large)}"]
                if fixes else [])
    run(["bd", "update", epic, "--set-metadata", f"{HEAD_KEY}={owed.head}",
         "--set-metadata", f"{PASSES_KEY}={count_of(shown, PASSES_KEY) + 1}",
         "--set-metadata", f"{LOW_KEY}={as_json(kept_unsure)}", *owed_fix], main_tree, env)
    filed = [] if fixes else file_large(epic, large, main_tree)
    return Reviewed(owed.head, fixes, filed, unsure)


def settle_fix(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Fixed:
    """Commits what the fix worker left as one commit on the epic branch, moves the review's fixed point past it,
    and files the review's large findings."""
    shown = bd_show(epic, main_tree)
    if shown is None:
        raise ReviewError(f"bd show printed nothing usable for {epic}")
    owed = fix_to_run(epic, shown, branch, settings, home, main_tree)
    if owed is None:
        raise ReviewError(f"{epic} waits on no fix, so nothing was written")
    large = stored_findings(shown, LARGE_KEY)
    changed = cleanup.changed_paths(owed.worktree)
    stray = [path for path in changed if path not in owed.files]
    if stray:
        raise ReviewError(f"the fix changed paths that are not files the epic added or changed: {', '.join(stray)}, "
                          "so nothing was written")
    head = owed.head
    if changed:
        run(["git", "commit", "--quiet", "--message", FIX_COMMIT_MESSAGE], owed.worktree, env_as_factory())
        head = head_of("HEAD", owed.worktree) or owed.head
        move_epic_branch(branch, owed.head, head, home, main_tree)
    remove_worktree(owed.worktree, main_tree)
    env = env_as_factory()
    run(["bd", "comment", epic, fix_comment(changed, head)], main_tree, env)
    run(["bd", "update", epic, "--set-metadata", f"{HEAD_KEY}={head}", "--unset-metadata", FIXES_KEY,
         "--unset-metadata", LARGE_KEY], main_tree, env)
    return Fixed(head, changed, file_large(epic, large, main_tree))


def fix_comment(changed: list[str], head: str) -> str:
    if not changed:
        return f"The review's fix changed no file, and the epic branch stays at {head}."
    return "\n".join([f"The review's fix changed {len(changed)} files, in the commit {head}:",
                      *(f"- {path}" for path in changed)])


def parks_at_the_cap(shown: dict, has_open_tasks: bool) -> bool:
    """True when the epic would start a pass past the cap, and has not asked about this one yet."""
    passes = count_of(shown, PASSES_KEY)
    return has_open_tasks and passes >= PASS_CAP and passes > count_of(shown, ASKED_KEY)


def park_at_the_cap(epic: str, shown: dict, main_tree: Path) -> None:
    """Parks the epic with a question, instead of starting a pass past the cap."""
    passes = count_of(shown, PASSES_KEY)
    options = [{"name": NEXT_PASS, "confidence": 60}, {"name": DROP, "confidence": 40}]
    text = "\n".join([f"{park.QUESTION_PREFIX}{epic} has been through {passes} passes, the pass cap is {PASS_CAP}, "
                      "and it still holds open tasks, so the factory parked it before the next pass.", "",
                      *(f"- {each['name']} ({each['confidence']}%)" for each in options), "",
                      f"Recommended: {NEXT_PASS}. Take the human label off the epic to run it."])
    env = env_as_factory()
    run(["bd", "comment", epic, text], main_tree, env)
    run(["bd", "update", epic, "--set-metadata", f"{ASKED_KEY}={passes}",
         "--set-metadata", f"{park.OPTIONS_KEY}={json.dumps(options)}",
         "--set-metadata", f"{park.RECOMMENDED_KEY}={NEXT_PASS}", f"--add-label={park.HUMAN_LABEL}"], main_tree, env)
