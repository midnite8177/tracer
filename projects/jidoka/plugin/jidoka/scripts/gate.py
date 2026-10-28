#!/usr/bin/env python3
"""The acceptance gate's script: it writes the human's decision on an epic that waits at the gate.

`merge <epic> --message <text>` lands the epic on local main. The epic must
carry the factory and human labels, record its epic branch and have the
gate.state waiting. The message is the one commit's message, written in the
style of the repo's log, and it names no bead.

Behind the merge lock, the one land.py and the merge gate take, the script
rebuilds the epic as one commit on main's head, in a detached worktree at
.worktrees/landing-<epic>. When main is not an ancestor of the commit
validation checked, main moved since validation, and the script runs the
full suite from the repo settings on the rebuilt commit. A red run posts a
comment on the epic with the failing commands, leaves the epic at the gate
and changes nothing else. A rebuild that conflicts with main does the same.

Uncommitted edits in main's checkout that touch files the epic changed make
the script wait: it prints the files and exits 3 before it changes anything,
and running it again once the edits are gone goes on. It fast-forwards
local main with git merge --ff-only. It never pushes.

Then, as the git user, it records gate.decision=merge and gate.landed=<sha>
on the epic, closes the epic with the commit in the reason, retires the
epic's holdouts by removing their metadata key, removes the
factory and human labels, removes the worktrees and branches of the epic's
laps and the epic branch. Each step runs on its own, so one failure stops no
other. The epic branch stays while the epic is open. A rerun on an epic
that records gate.landed repeats these steps.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka. After exit 0,
4 or 5 the script lists each app's hand-run tests, as land.py does.

Exit codes:
  0  landed and closed; the sha is printed.
  1  refused or failed before the fast-forward, with main unchanged.
  2  a usage error.
  3  waiting on uncommitted edits in main's checkout.
  4  main has the commit but a closing step failed; the sha is printed.
  5  the full suite failed on the rebuilt commit, and the epic is back at the
     gate.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import cleanup
import lap_record
import repo_settings
import review
from commands import (COMMAND_TIMEOUT_SECONDS, FACTORY_LABEL, HUMAN_LABEL, MAIN_REF, CommandError, bd_show, capture,
                      env_as_git_user, labels_of, metadata_of, read_bead, run, worktree_list)
from epic_branch import branch_head, required_head
from epic_reader import BRANCH_KEY, EPIC_TYPE, EpicReadError, child_ids, recorded_branch, shown_beads, validated_head
from epics import GATE_STATE_KEY, WAITING, at_the_gate, is_closed
from holdouts import HOLDOUTS_KEY
from land import (FULL_SUITE_FAILED_EXIT_CODE, PARTLY_LANDED_EXIT_CODE, WAITING_ON_EDITS_EXIT_CODE, FullSuiteFailed,
                  LandingError, LandingSettings, WaitingOnEdits, acquire_lock, attempt, landing_settings,
                  main_checkout, merge_lock, print_hand_run, refuse_bad_message, refuse_overlapping_edits,
                  release_lock, run_full_suite, subject)
from merge_gate import contains
from pass_support import MAIN_BRANCH, park_epic
from report_text import tail_of
from worktrees import cut_detached, remove_worktree, stage_worktree

GATE_COMMENT_HEADING = "Acceptance gate:"
DECISION_KEY = "gate.decision"
LANDED_KEY = "gate.landed"
MERGE = "merge"
WORKTREE_PREFIX = "landing-"


class GateError(Exception):
    """A reason the script writes nothing more, worded for the person who reads stderr."""


class BackAtTheGate(Exception):
    """A landing that cannot go on, with the comment that tells the human why the epic waits again."""

    def __init__(self, comment: str, exit_code: int) -> None:
        super().__init__(comment)
        self.comment = comment
        self.exit_code = exit_code


@dataclass(frozen=True)
class EpicAtTheGate:
    """The epic at the gate: its id, its epic branch, and what the gate recorded on it."""
    id: str
    branch: str
    metadata: dict
    labels: list[str]
    closed: bool

    @property
    def landed(self) -> str:
        return str(self.metadata.get(LANDED_KEY) or "")


@dataclass(frozen=True)
class Landed:
    """The commit that is on main, and the closing steps that did not succeed."""
    sha: str
    failed_steps: list[str]


def epic_at_the_gate(epic: str, main_tree: Path) -> EpicAtTheGate:
    shown = read_bead(epic, main_tree)
    labels = labels_of(shown)
    found = EpicAtTheGate(epic, recorded_branch(shown), metadata_of(shown), labels, is_closed(shown))
    if found.landed:
        return found
    if shown.get("issue_type") != EPIC_TYPE:
        raise GateError(f"{epic} is not an epic")
    if FACTORY_LABEL not in labels or HUMAN_LABEL not in labels or not at_the_gate(shown):
        raise GateError(f"{epic} does not wait at the acceptance gate: it needs the {FACTORY_LABEL} and "
                        f"{HUMAN_LABEL} labels and {GATE_STATE_KEY}={WAITING}")
    if not found.branch:
        raise GateError(f"{epic} records no epic branch as its {BRANCH_KEY} metadata")
    required_head(found.branch, main_tree, GateError)
    return found


def merged_commits(branch_head: str, main_tree: Path) -> list[str]:
    """One line for each commit the epic branch holds that main lacks, merge commits left out, oldest first."""
    listed = run(["git", "log", "--no-merges", "--reverse", "--format=%h %s", f"{MAIN_BRANCH}..{branch_head}"],
                 main_tree, None)
    return listed.splitlines()


def reach_the_gate(epic: str, branch: str, validated_head: str, figures: list[str], hand_run: list[str],
                   main_tree: Path) -> None:
    """Puts the epic at the acceptance gate: one comment that starts with the heading and lists the commits the epic
    branch holds that main lacks, the validation's figures, the tests the test cleanup removed, the review's findings
    of low confidence and the hand-run lines, then gate.state waiting and the human label, last, so a labeled epic
    always has its comment."""
    shown = bd_show(epic, main_tree)
    notes = [*cleanup.removed_lines(shown), *review.low_confidence_lines(shown)] if shown is not None else []
    lines = [f"{GATE_COMMENT_HEADING} {epic} waits for the human, on the epic branch {branch} at {validated_head}.",
             "", "Merged into the epic branch:", *(f"- {commit}" for commit in merged_commits(validated_head, main_tree)),
             "", *figures, *notes, *hand_run]
    park_epic(epic, "\n".join(lines), {GATE_STATE_KEY: WAITING}, main_tree)


def main_moved_since_validation(epic: EpicAtTheGate, main_tree: Path) -> bool:
    """True when main holds a commit that the commit validation checked lacks, or when no validation is recorded."""
    validated = validated_head(epic.metadata)
    return not validated or not contains(MAIN_REF, validated, main_tree)


def rebuild_on_main(epic: EpicAtTheGate, message: str, home: Path, main_tree: Path) -> tuple[Path, str]:
    """Cuts a worktree at main's head, squashes the epic branch into one commit there; returns it and the commit."""
    path = stage_worktree(WORKTREE_PREFIX, epic.id, main_tree)
    if path.exists():
        remove_worktree(path, main_tree)
    cut_detached(path, MAIN_REF, home, main_tree)
    try:
        squashed = capture(["git", "merge", "--squash", f"refs/heads/{epic.branch}"], path, None)
        if squashed.returncode != 0:
            conflicts = sorted(run(["git", "diff", "--name-only", "--diff-filter=U"], path, None).split())
            raise BackAtTheGate(f"Landing {epic.id} was refused: merging {epic.branch} onto main conflicts in "
                                f"{', '.join(conflicts) or 'files git does not name'}. Merge main into the epic "
                                "branch by hand and run the gate again.", 1)
        if capture(["git", "diff", "--cached", "--quiet"], path, None).returncode == 0:
            raise GateError(f"{epic.branch} holds nothing that main lacks, so there is nothing to land")
        run(["git", "commit", "-q", "-m", message], path, None)
        sha = run(["git", "rev-parse", "HEAD"], path, None).strip()
    except (BackAtTheGate, GateError, CommandError):
        remove_worktree(path, main_tree)
        raise
    return path, sha


def validate_again(epic: EpicAtTheGate, worktree: Path, settings: LandingSettings) -> None:
    try:
        run_full_suite(settings.full_suite, worktree)
    except FullSuiteFailed as failed:
        lines = [f"Landing {epic.id} was refused: main moved since validation, and the full suite failed on the "
                 f"epic rebuilt on main. {epic.id} waits at the gate again."]
        for failure in failed.failures:
            lines += ["", f"`{failure.command}` exited {failure.exit_code}. The end of its output:", "",
                      tail_of(failure.output)]
        raise BackAtTheGate("\n".join(lines), FULL_SUITE_FAILED_EXIT_CODE) from failed


def fast_forward_main(epic: EpicAtTheGate, sha: str, checkout: Path) -> None:
    refuse_overlapping_edits(epic.branch, checkout)
    run(["git", "merge", "--ff-only", sha], checkout, None)


def land_on_main(epic: EpicAtTheGate, message: str, settings: LandingSettings, home: Path, checkout: Path,
                 main_tree: Path) -> str:
    """Rebuilds the epic as one commit on main's head, reruns the suite if main moved, and fast-forwards main."""
    refuse_overlapping_edits(epic.branch, checkout)
    moved = main_moved_since_validation(epic, main_tree)
    worktree, sha = rebuild_on_main(epic, message, home, main_tree)
    try:
        if moved:
            validate_again(epic, worktree, settings)
        fast_forward_main(epic, sha, checkout)
    finally:
        remove_worktree(worktree, main_tree)
    return sha


def lap_branches(epic: EpicAtTheGate, main_tree: Path) -> list[str]:
    """The branch of every lap the epic's beads opened, from the lap metadata and the lap/<bead> naming."""
    ids = child_ids(epic.id, main_tree)
    names = {f"{lap_record.LAP_BRANCH_PREFIX}{bead}" for bead in ids}
    for bead in shown_beads(ids, main_tree):
        recorded = lap_record.branch_of(metadata_of(bead))
        if recorded:
            names.add(str(recorded))
    return sorted(names)


def remove_branches(epic: EpicAtTheGate, main_tree: Path) -> None:
    names = lap_branches(epic, main_tree) + [epic.branch]
    for tree in worktree_list(main_tree):
        if tree.branch in names:
            run(["git", "worktree", "remove", "--force", str(tree.path)], main_tree, None)
    for name in names:
        if branch_head(name, main_tree) is not None:
            run(["git", "branch", "-D", name], main_tree, None)


def close_out(epic: EpicAtTheGate, message: str, sha: str, main_tree: Path) -> Landed:
    """Records the decision, closes the epic and removes its labels and branches, each step on its own."""
    env = env_as_git_user(main_tree)
    failed: list[str] = []
    attempt("bd update", ["bd", "update", epic.id, "--set-metadata", f"{DECISION_KEY}={MERGE}",
                          "--set-metadata", f"{LANDED_KEY}={sha}"], main_tree, env, failed)
    closed = epic.closed or attempt("bd close", ["bd", "close", epic.id, "--reason", f"{sha}: {subject(message)}"],
                                    main_tree, env, failed)
    if HOLDOUTS_KEY in epic.metadata:
        attempt("retire the holdouts", ["bd", "update", epic.id, "--unset-metadata", HOLDOUTS_KEY], main_tree, env,
                failed)
    for label in (FACTORY_LABEL, HUMAN_LABEL):
        if label in epic.labels:
            attempt(f"bd label remove {label}", ["bd", "label", "remove", epic.id, label], main_tree, env, failed)
    if closed:
        try:
            remove_branches(epic, main_tree)
        except CommandError as error:
            failed.append(f"remove the lap and epic branches: {error}")
    return Landed(sha, failed)


def merge(epic_id: str, message: str, home: Path, main_tree: Path) -> tuple[Landed, LandingSettings]:
    checkout = main_checkout(main_tree)
    epic = epic_at_the_gate(epic_id, main_tree)
    refuse_bad_message(message, epic.id, checkout)
    settings = landing_settings(checkout, home)
    lock = merge_lock(home)
    acquire_lock(lock)
    try:
        sha = epic.landed or land_on_main(epic, message, settings, home, checkout, main_tree)
        return close_out(epic, message, sha, main_tree), settings
    finally:
        release_lock(lock)


def send_back(epic_id: str, back: BackAtTheGate, main_tree: Path) -> None:
    run(["bd", "comment", epic_id, back.comment], main_tree, env_as_git_user(main_tree))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gate.py", description="Write the human's decision on an epic at the "
                                                                 "acceptance gate.")
    modes = parser.add_subparsers(dest="mode", required=True)
    merging = modes.add_parser("merge", help="land the epic on local main as one commit")
    merging.add_argument("epic")
    merging.add_argument("--message", required=True, help="the commit message, which names no bead")
    merging.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = repo_settings.jidoka_home(args.jidoka_home)
        landed, settings = merge(args.epic, args.message, home, main_tree)
    except WaitingOnEdits as waiting:
        print(f"gate: {waiting}. Main is unchanged and {args.epic} waits at the gate. Commit or set aside:")
        for name in waiting.files:
            print(f"  {name}")
        return WAITING_ON_EDITS_EXIT_CODE
    except BackAtTheGate as back:
        try:
            send_back(args.epic, back, main_tree)
        except CommandError as error:
            print(f"gate: could not post the comment on {args.epic}: {error}", file=sys.stderr)
        print(f"gate: {back.comment}", file=sys.stderr)
        return back.exit_code
    except (GateError, EpicReadError, LandingError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"gate: {error}", file=sys.stderr)
        return 1
    print(landed.sha)
    if landed.failed_steps:
        print("gate: main has the commit, but these steps failed. Run the same command again to repeat them.",
              file=sys.stderr)
        for step in landed.failed_steps:
            print(f"  {step}", file=sys.stderr)
        print_hand_run(settings.hand_run, sys.stderr)
        return PARTLY_LANDED_EXIT_CODE
    print_hand_run(settings.hand_run, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
