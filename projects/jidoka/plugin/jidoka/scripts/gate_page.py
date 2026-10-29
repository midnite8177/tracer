#!/usr/bin/env python3
"""The page the human reads at the acceptance gate, the review guide of an epic.

`gate_page.py <epic> --guide <file>` writes one self-contained HTML file, `<jidoka-home>/pages/<repo>/gate-<epic>.html`,
never in the repo, and prints its path. A later run for the same epic replaces it. The epic must be open, await
acceptance (`gate.awaits_acceptance`: `gate.state` waiting, or parked at the pass cap with open tasks) and record an
epic branch that exists. The look is the stylesheet of the explain skill, inlined, and the parts are listed in that
skill's SKILL.md. The gate comment holds the record in plain text, so the page can fall behind it and the bead still
wins.

The guide is a JSON object the worker of the gate writes: `in_short`, a non-empty string, and optional `before` and
`after`, strings that show an example before and after the epic; `how`, a list of short steps that explain how the
change works; `steps`, a list of numbered steps that reach the change in the running app; and `unchecked`, a list of
what no test or holdout checked. Every other part is read from git, bd, the repo settings and the jidoka home.

The page reads top to bottom: In short, Before and after, How it works, What changed, Evidence, Assumptions, Design
findings, Tests removed, What nothing checked, Cost, Merge danger and Decide. What changed lists every file the epic
branch changes from main, and each file opens its real diff in a unified or a split layout. Evidence holds the
validation figures, the worktree of the epic branch, each app's build and run commands and the guide's steps.
Assumptions are numbered as the gate comment numbers them, and list the public API changes and the beads found outside
the epic after them, all read by gate_items.py. Decide marks `data-jidoka-slot="decide-panel"`, where jidoka-ui draws
Merge and Drop. Send back runs in /jidoka:accept.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  the page was written; its path is printed.
  1  refused or failed, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from html import escape
from pathlib import Path

import cleanup
import design_findings
import diff_view
import gate_items
import question_page
import repo_settings
import review
import validation
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, capture, metadata_of, read_bead, run, worktree_list
from epic_branch import required_head
from epic_reader import EPIC_TYPE, EpicReadError, recorded_branch, validated_head
from epics import is_closed
from gate import awaits_acceptance, branch_moved_since_validation, main_moved_since_validation, merged_commits
from land import changed_paths, edited_paths, main_checkout
from pass_support import MAIN_BRANCH, PassError
from worktrees import stage_worktree

DECIDE_SLOT = "decide-panel"
WORKTREE_PREFIX = "gate-"


class GatePageError(Exception):
    """A reason the script writes no page, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Guide:
    """The words the worker of the gate writes for the page."""
    in_short: str
    before: str
    after: str
    how: tuple[str, ...]
    steps: tuple[str, ...]
    unchecked: tuple[str, ...]


@dataclass(frozen=True)
class AppCommands:
    """How the human builds and runs one app; `run` is "" when the app has no run command."""
    name: str
    build: str
    run: str


@dataclass(frozen=True)
class Checkout:
    """Where the human looks at the epic branch: a worktree path, and the command that cuts it when no worktree has
    the branch out yet ("" when one does)."""
    path: Path
    cut_with: str


@dataclass(frozen=True)
class GatePage:
    """What the gate page shows: the epic and its guide, then what the scripts read from git, bd and the settings."""
    epic: str
    title: str
    branch: str
    head: str
    guide: Guide
    commits: tuple[str, ...]
    files: tuple[diff_view.FileDiff, ...]
    evidence: tuple[str, ...]
    checkout: Checkout
    apps: tuple[AppCommands, ...]
    items: gate_items.GateItems
    open_findings: tuple[dict, ...]
    low_findings: tuple[review.Finding, ...]
    removals: tuple[cleanup.Removal, ...]
    hand_run: tuple[validation.HandRunGroup, ...]
    cost: tuple[str, ...]
    danger: tuple[str, ...]


def page_path(home: Path, main_tree: Path, epic: str) -> Path:
    return home / question_page.PAGES_FOLDER / main_tree.name / f"gate-{epic}.html"


def texts_of(value: object, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(each, str) and each.strip() for each in value):
        raise GatePageError(f"{name} must be a list of non-empty strings")
    return tuple(each.strip() for each in value)


def text_of(value: object, name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise GatePageError(f"{name} must be a non-empty string")
    return value.strip()


def read_guide(path: Path) -> Guide:
    """The guide in the file; raises GatePageError when the file is missing, is not a JSON object, or holds a part of
    the wrong shape."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GatePageError(f"the guide {path} cannot be read as JSON: {error}") from error
    if not isinstance(data, dict):
        raise GatePageError(f"the guide {path} must hold a JSON object")
    in_short = text_of(data.get("in_short"), "in_short")
    if not in_short:
        raise GatePageError("the guide needs an in_short: a non-empty string")
    return Guide(in_short, text_of(data.get("before"), "before"), text_of(data.get("after"), "after"),
                 texts_of(data.get("how"), "how"), texts_of(data.get("steps"), "steps"),
                 texts_of(data.get("unchecked"), "unchecked"))


def epic_waiting_at_the_gate(epic: str, main_tree: Path) -> tuple[dict, str, str]:
    """The epic's bead, its epic branch and the head of that branch; raises GatePageError when the epic does not await
    acceptance, as the gate script reads it."""
    shown = read_bead(epic, main_tree)
    if shown.get("issue_type") != EPIC_TYPE:
        raise GatePageError(f"{epic} is not an epic")
    if is_closed(shown) or not awaits_acceptance(shown, main_tree):
        raise GatePageError(f"{epic} does not wait at the acceptance gate, so it has no gate page")
    branch = recorded_branch(shown)
    if not branch:
        raise GatePageError(f"{epic} records no epic branch")
    return shown, branch, required_head(branch, main_tree, GatePageError)


def changed_files(head: str, main_tree: Path) -> tuple[diff_view.FileDiff, ...]:
    done = capture(["git", "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "--no-renames",
                    f"{MAIN_BRANCH}...{head}"], main_tree, None)
    if done.returncode != 0:
        raise GatePageError(f"git diff failed: {done.stderr.strip()}")
    return tuple(diff_view.parse(done.stdout))


def evidence_lines(shown: dict) -> tuple[str, ...]:
    metadata = metadata_of(shown)
    runs = metadata.get(validation.RUNS_KEY)
    if not runs:
        return ()
    figures = [f"{each.suite.app}: {each.suite.command}, {each.figures()}" for each in validation.runs_of(runs)]
    return (f"Validation of {validated_head(metadata)} ended {metadata.get(validation.RESULT_KEY) or 'unknown'}: "
            f"{metadata.get(validation.TESTS_KEY, '?')} tests in {metadata.get(validation.SECONDS_KEY, '?')} s.",
            *figures)


def checkout_of(epic: str, branch: str, main_tree: Path) -> Checkout:
    for tree in worktree_list(main_tree):
        if tree.branch == branch:
            return Checkout(tree.path, "")
    path = stage_worktree(WORKTREE_PREFIX, epic, main_tree)
    return Checkout(path, f'git -C "{main_tree}" worktree add "{path}" {branch}')


def settings_of(home: Path, main_tree: Path) -> dict:
    return repo_settings.load(repo_settings.settings_path(home, main_tree))


def apps_of(settings: dict) -> tuple[AppCommands, ...]:
    apps = settings.get("apps")
    listed = apps if isinstance(apps, list) else []
    return tuple(AppCommands(str(app.get("name") or ""), str(app.get("build") or ""), str(app.get("run") or ""))
                 for app in listed if isinstance(app, dict))


def paths_main_changed(head: str, main_tree: Path) -> set[str]:
    base = run(["git", "merge-base", MAIN_BRANCH, head], main_tree, None).strip()
    listed = run(["git", "diff", "--name-only", "--no-renames", "-z", base, MAIN_BRANCH], main_tree, None)
    return {path for path in listed.split("\0") if path}


def danger_lines(shown: dict, branch: str, head: str, main_tree: Path) -> tuple[str, ...]:
    """What could go wrong when the epic lands: main or the epic branch moved since validation, files both sides
    changed, and uncommitted edits in main's checkout over files the epic changed."""
    checkout = main_checkout(main_tree)
    metadata = metadata_of(shown)
    epic_paths = changed_paths(MAIN_BRANCH, head, checkout)
    lines = []
    if main_moved_since_validation(metadata, main_tree):
        lines.append("Main holds commits that validation did not check. Merge rebuilds the epic on main and runs "
                     "the full suite again.")
    if branch_moved_since_validation(metadata, branch, main_tree):
        lines.append("The epic branch moved past the commit validation checked, as a restored test moves it. Merge "
                     "runs the full suite again.")
    if not lines:
        lines.append("Main has not moved since validation. The epic branch holds the commit validation checked.")
    both = sorted(epic_paths & paths_main_changed(head, main_tree))
    if both:
        lines.append(f"Main and the epic both changed {', '.join(both)}; the rebuild can conflict there.")
    edited = sorted(epic_paths & edited_paths(checkout))
    if edited:
        lines.append(f"Uncommitted edits in the main checkout touch {', '.join(edited)}. Merge waits until they are "
                     "committed or set aside.")
    return tuple(lines)


def cost_lines(shown: dict) -> tuple[str, ...]:
    seconds = metadata_of(shown).get(validation.SECONDS_KEY)
    if seconds is None:
        return ("No validation time is recorded on this epic.",)
    return (f"Validation took {seconds} s.",)


def gather(epic: str, guide: Guide, home: Path, main_tree: Path) -> GatePage:
    """Reads everything the page shows; raises GatePageError when the epic does not wait at the gate."""
    shown, branch, head = epic_waiting_at_the_gate(epic, main_tree)
    files = changed_files(head, main_tree)
    settings = settings_of(home, main_tree)
    findings = design_findings.ranked_findings([each.path for each in files], main_tree)
    return GatePage(epic, str(shown.get("title") or epic), branch, head, guide,
                    tuple(merged_commits(head, main_tree)), files, evidence_lines(shown),
                    checkout_of(epic, branch, main_tree), apps_of(settings),
                    gate_items.gate_items(epic, str(shown.get("title") or ""), main_tree), tuple(findings),
                    tuple(review.stored_findings(shown, review.LOW_KEY)), tuple(cleanup.removed_before(shown)),
                    tuple(validation.hand_run_groups(settings)), cost_lines(shown),
                    danger_lines(shown, branch, head, main_tree))


def paragraph(text: str) -> str:
    return f"<p>{escape(text)}</p>"


def bullets(items: tuple[str, ...] | list[str]) -> str:
    return "<ul>\n" + "\n".join(f"<li>{escape(each)}</li>" for each in items) + "\n</ul>"


def section(title: str, body: str, css: str) -> str:
    kind = f' class="{css}"' if css else ""
    return f"<section{kind}>\n<h2>{escape(title)}</h2>\n{body}\n</section>\n"


def example(label: str, text: str) -> str:
    return f'<div class="example"><h3>{escape(label)}</h3>\n<pre>{escape(text)}</pre></div>'


def before_and_after(guide: Guide) -> str:
    if not guide.before and not guide.after:
        return paragraph("The worker gave no example.")
    return ('<div class="examples">\n' + "\n".join(example(label, text) for label, text in
                                                    (("Before", guide.before), ("After", guide.after)) if text)
            + "\n</div>")


def how_it_works(guide: Guide) -> str:
    if not guide.how:
        return paragraph("The worker gave no steps.")
    return question_page.diagram(guide.how, "How the change works, step by step")


def file_html(file: diff_view.FileDiff) -> str:
    counts = f'<span class="add">+{file.added}</span> <span class="del">-{file.removed}</span>'
    if file.status == diff_view.BINARY:
        body = paragraph("Git cannot show a binary file as text.")
    elif not file.hunks:
        body = paragraph("The file's content did not change.")
    else:
        body = f"{diff_view.unified(file)}\n{diff_view.split(file)}"
    return (f'<details class="file" data-path="{escape(file.path, quote=True)}">\n'
            f'<summary><span class="path">{escape(file.path)}</span> <span class="status">{file.status}</span> '
            f'{counts}</summary>\n{body}\n</details>')


def what_changed(page: GatePage) -> str:
    commits = bullets(page.commits) if page.commits else paragraph("The epic branch holds no commit that main lacks.")
    toggle = ('<div class="layout"><input type="radio" name="diff-layout" id="layout-unified" checked>'
              '<label for="layout-unified">Unified</label>'
              '<input type="radio" name="diff-layout" id="layout-split"><label for="layout-split">Split</label></div>')
    files = "\n".join(file_html(each) for each in page.files) or paragraph("No file differs from main.")
    return (f"<h3>Commits</h3>\n{commits}\n<h3>{len(page.files)} files</h3>\n{toggle}\n{files}")


def code(text: str) -> str:
    return f"<code>{escape(text)}</code>"


def run_the_change(page: GatePage) -> str:
    cut = f"<li>Cut it: {code(page.checkout.cut_with)}</li>\n" if page.checkout.cut_with else ""
    commands = "".join(f"<tr><td>{escape(app.name)}</td><td>{code(app.build) if app.build else 'none'}</td>"
                       f"<td>{code(app.run) if app.run else 'none'}</td></tr>" for app in page.apps)
    table = (f"<table class=\"commands\"><tr><th>App</th><th>Build</th><th>Run</th></tr>{commands}</table>"
             if commands else paragraph("The repo settings record no app."))
    steps = ("<ol class=\"steps\">\n" + "\n".join(f"<li>{escape(each)}</li>" for each in page.guide.steps)
             + "\n</ol>") if page.guide.steps else paragraph("The worker gave no steps to reach the change.")
    return (f"<h3>Run the change</h3>\n<ul>\n{cut}<li>Worktree: <span class=\"worktree\">{escape(str(page.checkout.path))}"
            f"</span></li>\n</ul>\n{table}\n<h3>Steps to reach the change</h3>\n{steps}")


def evidence(page: GatePage) -> str:
    figures = bullets(page.evidence) if page.evidence else paragraph("No validation is recorded on the epic.")
    return f"{figures}\n{run_the_change(page)}"


def assumptions(page: GatePage) -> str:
    """The assumptions numbered as the gate comment numbers them, which `gate wrong` takes, then the public API
    changes and the open beads found outside the epic."""
    items = page.items
    if not items.assumptions:
        parts = [paragraph("No worker recorded an assumption.")]
    else:
        listed = "\n".join(f"<li>{escape(each.row())}</li>" for each in items.assumptions)
        parts = [f'<ol class="assumptions">\n{listed}\n</ol>']
    if items.api_changes:
        parts.append("<h3>Public API changes</h3>\n" + bullets([each.row() for each in items.api_changes]))
    if items.outside:
        parts.append("<h3>Found outside the epic, still open</h3>\n" + bullets(
            [f"{each.bead} {each.title}, found in {each.found_in}" for each in items.outside]))
    return "\n".join(parts)


def design_findings_html(page: GatePage) -> str:
    if not page.open_findings and not page.low_findings:
        return paragraph("No design finding is open in the files the epic changed, and no review finding of low "
                         "confidence was kept.")
    parts = []
    if page.open_findings:
        parts.append("<h3>Open in the files the epic changed</h3>\n" + bullets(
            [f"{each['bead']} {each['file']}: {each['title']} (sightings: {each['sightings']})"
             for each in page.open_findings]))
    if page.low_findings:
        parts.append("<h3>Review findings of low confidence, never fixed</h3>\n" + bullets(
            [f"{each.lane}, {each.file}:{each.line}: {each.title}. {each.note}" for each in page.low_findings]))
    return "\n".join(parts)


def tests_removed(page: GatePage) -> str:
    if not page.removals:
        return paragraph("The test cleanup removed no test.")
    rows = "".join(f"<tr><td>{escape(each.test)}</td><td>{escape(each.file)}</td><td>{escape(each.covered_by)}</td>"
                   "</tr>" for each in page.removals)
    return f"<table><tr><th>Test</th><th>File</th><th>Covered by</th></tr>{rows}</table>"


def unchecked(page: GatePage) -> str:
    parts = []
    if page.guide.unchecked:
        parts.append(bullets(page.guide.unchecked))
    if page.hand_run:
        parts.append("<h3>Hand-run tests, which validation never runs</h3>\n" + bullets(
            [f"{each.app}, {each.name}: {each.reason}. Run {each.command}" for each in page.hand_run]))
    return "\n".join(parts) or paragraph("The worker named nothing that went unchecked, and no hand-run tests are "
                                         "recorded.")


def decide() -> str:
    return (f'<section class="answer-slot" data-jidoka-slot="{DECIDE_SLOT}">\n<h2>Decide</h2>\n'
            "<p>jidoka-ui draws Merge and Drop here. Send back runs in /jidoka:accept. "
            "The bead holds the gate comment in plain text.</p>\n"
            "</section>\n")


def render(page: GatePage, stylesheet: str) -> str:
    body = "".join([
        section("In short", paragraph(page.guide.in_short), "in-short"),
        section("Before and after", before_and_after(page.guide), ""),
        section("How it works", how_it_works(page.guide), "why"),
        section("What changed", what_changed(page), "changed"),
        section("Evidence", evidence(page), ""),
        section("Assumptions", assumptions(page), ""),
        section("Design findings", design_findings_html(page), ""),
        section("Tests removed", tests_removed(page), ""),
        section("What nothing checked", unchecked(page), ""),
        section("Cost", bullets(page.cost), ""),
        section("Merge danger", bullets(page.danger), ""),
        decide()])
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>Acceptance gate: {escape(page.title)}</title>\n<style>\n{stylesheet}</style>\n</head>\n<body>\n'
            f'<header>\n<p>Acceptance gate for {escape(page.epic)} on {escape(page.branch)} at '
            f'{escape(page.head[:12])}</p>\n<h1>{escape(page.title)}</h1>\n</header>\n{body}</body>\n</html>\n')


def write(page: GatePage, home: Path, main_tree: Path) -> Path:
    """Writes the page and returns its path; raises OSError when the stylesheet cannot be read or the file written."""
    stylesheet = question_page.STYLESHEET.read_text(encoding="utf-8")
    path = page_path(home, main_tree, page.epic)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(page, stylesheet), encoding="utf-8")
    return path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gate_page.py", description="Write the review guide of an epic that waits "
                                                                      "at the acceptance gate.")
    parser.add_argument("epic")
    parser.add_argument("--guide", required=True, help="the JSON file of the words the gate worker wrote")
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = repo_settings.jidoka_home(args.jidoka_home)
        page = gather(args.epic, read_guide(Path(args.guide)), home, main_tree)
        print(write(page, home, main_tree))
    except (GatePageError, EpicReadError, CommandError, PassError, repo_settings.SettingsError, OSError) as error:
        print(f"gate page: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
