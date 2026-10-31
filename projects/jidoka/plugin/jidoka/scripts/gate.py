#!/usr/bin/env python3
"""The acceptance gate's script: it writes the human's decisions on an epic that waits at the gate.

`merge <epic> --message <text>` lands the epic on local main. The epic must
carry the factory and human labels, record its epic branch and have the
gate.state waiting. The message is the one commit's message, written in the
style of the repo's log, and it names no bead.

An epic parked at its pass cap, with the human label and the question the cap asks, and open tasks, can be merged
too, and its open tasks move to a new epic that carries no factory label, as open_tasks.py describes. Under the
epic's commits_on_main rule per_task, the rebuild makes a commit of each task, as task_commits.py describes, each
with its task's message, in place of the one commit; the message given then only words the epic's close reason.

Behind the merge lock, the one land.py and the merge gate take, the script
rebuilds the epic as one commit on main's head, in a detached worktree at
.worktrees/landing-<epic>. When main is not an ancestor of the commit
validation checked, or the epic branch moved past it, the script runs the
full suite from the repo settings on the rebuilt commit. A red run posts a
comment on the epic with the failing commands, and a rebuild that conflicts with main posts a comment that names the
conflicting files. Main and the epic branch stay as they were. An epic at the gate then leaves it: the script takes
gate.state and the human label off, so the next call of the scheduler finds the epic finished and runs validation,
which merges main into the epic branch, through the merge worker when that conflicts, runs the holdouts again and
brings the epic back to the gate. The pass count, the test cleanup and the tidy are not reset, because the epic branch
did not change. An epic parked at the pass cap stays parked with its comment.

Uncommitted edits in main's checkout that touch files the epic changed make
the script wait. It prints the files and exits 3 before it changes anything,
and running it again once the edits are gone goes on. It fast-forwards
local main with git merge --ff-only. It never pushes.

Then, as the git user, it records gate.decision=merge and gate.landed=<sha>
on the epic, closes the epic with the commit in the reason, retires the
epic's holdouts by removing their metadata key, removes the
factory and human labels, removes the worktrees and branches of the epic's
laps and the epic branch. Each step runs on its own, so one failure stops no
other. The epic branch stays while the epic is open. A rerun on an epic
that records gate.landed repeats these steps.

The other decisions leave the epic at the gate, and each refuses an epic that
does not wait there or that landed. Each is written as the git user.

`wrong <epic> <number> --why <text>` marks an assumption wrong. The gate
comment numbers the assumptions, and the script posts the assumption and the
human's reason on the bead that recorded it.

`items <epic>` writes nothing. It prints, as JSON, what wrong, restore, keep-finding and close-finding name, for an epic that waits at the
gate: `assumptions`, each with its `number` in the gate comment, the `bead` that recorded it, that bead's `title` and
its `text`; `removed`, each test the test cleanup removed, with its `file` and the test or spec that covers it
(`covered_by`); and `outside`, each open bead found outside the epic, with its `title` and the bead it was found in
(`found_in`). The epic is refused as the decisions refuse it.

`restore <epic> <test> [--file <file>]` puts a test that the test cleanup
removed back on the epic branch as one commit of its own, takes it out of the
epic's cleanup.removed and posts a comment that names the commit, as
gate_restore.py says. The merge then runs the full suite again, because the
epic branch moved past the commit validation checked.

`keep-finding <epic> <bead>` and `close-finding <epic> <bead>` take an open
bead the gate lists as found outside the epic. Keep leaves it open with a
comment that names the epic; close closes it with a reason that names the
epic. Neither changes its labels or its parent.

`send-back <epic> --note <text>... --proposals <file>` sends the epic back with one note for each problem, as
gate_send_back.py says. A note is pinned to a diff line when it reads `<file>:<line>: <text>`. The proposals file is the
send-back worker's list, one proposal for each note. The script files each as a task in the epic, with the Demo and
Seams lines, the area and the track it proposes, comments on the epic, records gate.decision=send-back, takes
gate.state and the human label off, starts the pass count again, and takes cleanup.state and tidy.state off, so the next
call of the scheduler runs the new tasks and the pass cleans and tidies again. A proposal list that does not answer
each note once files nothing.

`drop <epic>` closes the epic without landing it, records gate.decision=drop, ends the laps still open on its tasks,
and removes the factory and human labels. The epic branch stays.

An epic whose human label comes off with no decision is parked again by the scheduler, as gate_guard.py says.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka. After exit 0,
4 or 5 the merge lists each app's hand-run tests, as land.py does.

Exit codes:
  0  landed and closed, and the sha is printed; or the decision is written.
  1  refused or failed before the fast-forward, with main unchanged and nothing written; or the decision is refused,
     and nothing is written.
  2  a usage error.
  3  waiting on uncommitted edits in main's checkout.
  4  main has the commit but a closing step failed; the sha is printed.
  5  the rebuild was refused, because it conflicts with main or because the full suite failed on the rebuilt commit.
     Main is unchanged and the refusal is a comment on the epic. An epic at the gate goes back to validation, and an
     epic parked at the pass cap stays parked.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cleanup
import gate_drop
import gate_restore
import gate_send_back
import lap_record
import pass_ledger
import settings_reader
import rules
import t3_wake
from acceptance import branch_and_head_at_the_gate, moved_since_validation
from commands import (COMMAND_TIMEOUT_SECONDS, FACTORY_LABEL, HUMAN_LABEL, MAIN_REF, CommandError, capture,
                      env_as_git_user, labels_of, metadata_of, read_bead, run, set_metadata, unset_metadata,
                      worktree_list)
from epic_branch import branch_head, required_head
from epic_reader import EpicReadError, child_ids, recorded_branch, shown_beads
from epics import GATE_STATE_KEY, WAITING, is_closed
from gate_items import assumption, numbered_assumptions, outside_of
from holdouts import HOLDOUTS_KEY
from land import (FULL_SUITE_FAILED_EXIT_CODE, PARTLY_LANDED_EXIT_CODE, WAITING_ON_EDITS_EXIT_CODE, FullSuiteFailed,
                  LandingError, LandingSettings, WaitingOnEdits, acquire_lock, attempt, landing_settings,
                  main_checkout, merge_lock, print_hand_run, refuse_bad_message, refuse_overlapping_edits,
                  release_lock, run_full_suite, subject)
from open_tasks import move_open_tasks
from pass_support import PassError
from report_text import tail_of
from task_commits import commit_per_task
from worktrees import cut_detached, remove_worktree, stage_worktree, unmerged_files

DECISION_KEY = "gate.decision"
LANDED_KEY = "gate.landed"
MERGE = "merge"
WRONG = "wrong"
RESTORE = "restore"
ITEMS = "items"
KEEP_FINDING = "keep-finding"
CLOSE_FINDING = "close-finding"
SEND_BACK = "send-back"
DROP = "drop"
WRONG_PREFIX = "Assumption marked wrong at the acceptance gate: "
WORKTREE_PREFIX = "landing-"
TURNED_BACK_EXIT_CODE = FULL_SUITE_FAILED_EXIT_CODE


class GateError(Exception):
    """A reason the script writes nothing more, worded for the person who reads stderr."""


class RebuildRefused(Exception):
    """A rebuild of the epic on main that cannot land: what went wrong in one sentence, the lines that show it, the
    exit code the script ends with, and where the epic goes. An epic at the gate goes back to validation, which catches
    up with main; one parked at the pass cap stays parked, and the advice says what the human does."""

    def __init__(self, cause: str, details: list[str], exit_code: int, leaves_the_gate: bool,
                 parked_advice: str) -> None:
        super().__init__(cause)
        self.cause = cause
        self.details = details
        self.exit_code = exit_code
        self.leaves_the_gate = leaves_the_gate
        self.parked_advice = parked_advice

    def described(self, epic: str, outcome: str) -> str:
        return "\n".join([f"Landing {epic} was refused: {self.cause}. {outcome}", *self.details])

    def comment(self, epic: str) -> str:
        """The comment for the epic: what refused the landing and where the epic goes, then the details."""
        if self.leaves_the_gate:
            return self.described(epic, f"{epic} leaves the acceptance gate. Its pass runs validation again, which "
                                        "merges main into the epic branch, runs the holdouts again and brings the "
                                        "epic back to the gate.")
        return self.described(epic, f"{epic} stays parked. {self.parked_advice}")

    def unwritten(self, epic: str, error: CommandError) -> str:
        """The refusal as the script prints it when writing it on the epic failed. The comment, the gate state and the
        human label may each be written or not."""
        return self.described(epic, f"Turning {epic} back failed ({error}), so check its comments, its gate state and "
                                    "its human label.")


@dataclass(frozen=True)
class EpicAtTheGate:
    """The epic at the gate: its id, its title, its epic branch, what the gate recorded on it, and its rule for the
    commits that land on main."""
    id: str
    title: str
    branch: str
    metadata: dict
    labels: list[str]
    closed: bool
    commits_on_main: str

    @property
    def landed(self) -> str:
        return str(self.metadata.get(LANDED_KEY) or "")

    @property
    def waits_at_the_gate(self) -> bool:
        """True for an epic at the gate, false for one parked at the pass cap."""
        return self.metadata.get(GATE_STATE_KEY) == WAITING


@dataclass(frozen=True)
class Landed:
    """The commit that is on main, and the closing steps that did not succeed."""
    sha: str
    failed_steps: list[str]


def epic_at_the_gate(epic: str, main_tree: Path) -> EpicAtTheGate:
    shown = read_bead(epic, main_tree)
    labels = labels_of(shown)
    found = EpicAtTheGate(epic, str(shown.get("title") or ""), recorded_branch(shown), metadata_of(shown), labels,
                          is_closed(shown), rules.of_epic(shown).commits_on_main)
    if found.landed:
        return found
    branch_and_head_at_the_gate(epic, shown, main_tree, GateError)
    if FACTORY_LABEL not in labels or HUMAN_LABEL not in labels:
        raise GateError(f"{epic} does not wait at the acceptance gate: it needs the {FACTORY_LABEL} and "
                        f"{HUMAN_LABEL} labels")
    return found


def rebuild_on_main(epic: EpicAtTheGate, message: str, home: Path, main_tree: Path) -> tuple[Path, str]:
    """Cuts a worktree at main's head, squashes the epic branch into one commit there, or into a commit of each task
    under the per_task rule; returns the worktree and the last commit."""
    path = stage_worktree(WORKTREE_PREFIX, epic.id, main_tree)
    if path.exists():
        remove_worktree(path, main_tree)
    cut_detached(path, MAIN_REF, home, main_tree)
    try:
        squashed = capture(["git", "merge", "--squash", f"refs/heads/{epic.branch}"], path, None)
        if squashed.returncode != 0:
            conflicts = sorted(unmerged_files(path))
            raise RebuildRefused(f"merging {epic.branch} onto main conflicts in "
                                 f"{', '.join(conflicts) or 'files git does not name'}", [], TURNED_BACK_EXIT_CODE,
                                 epic.waits_at_the_gate,
                                 "Merge main into the epic branch by hand and run the gate again.")
        if capture(["git", "diff", "--cached", "--quiet"], path, None).returncode == 0:
            raise GateError(f"{epic.branch} holds nothing that main lacks, so there is nothing to land")
        if epic.commits_on_main == rules.PER_TASK:
            sha = commit_per_task(epic.id, epic.branch, path, main_tree, GateError)
        else:
            run(["git", "commit", "-q", "-m", message], path, None)
            sha = run(["git", "rev-parse", "HEAD"], path, None).strip()
    except (RebuildRefused, GateError, CommandError):
        remove_worktree(path, main_tree)
        raise
    return path, sha


def validate_again(epic: EpicAtTheGate, worktree: Path, settings: LandingSettings) -> None:
    try:
        run_full_suite(settings.full_suite, worktree)
    except FullSuiteFailed as failed:
        details: list[str] = []
        for failure in failed.failures:
            details += ["", f"`{failure.command}` exited {failure.exit_code}. The end of its output:", "",
                        tail_of(failure.output)]
        raise RebuildRefused("main or the epic branch moved since validation, and the full suite failed on the "
                             "epic rebuilt on main", details, TURNED_BACK_EXIT_CODE, epic.waits_at_the_gate,
                             "Make the failing commands pass on the epic branch, then run the gate again."
                             ) from failed


def fast_forward_main(epic: EpicAtTheGate, sha: str, checkout: Path) -> None:
    refuse_overlapping_edits(epic.branch, checkout)
    run(["git", "merge", "--ff-only", sha], checkout, None)


def land_on_main(epic: EpicAtTheGate, message: str, settings: LandingSettings, home: Path, checkout: Path,
                 main_tree: Path) -> str:
    """Rebuilds the epic as one commit on main's head, reruns the suite if main or the epic branch moved since
    validation, and fast-forwards main."""
    refuse_overlapping_edits(epic.branch, checkout)
    moved = moved_since_validation(epic.metadata, epic.branch, main_tree)
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


def release_from_factory(epic: EpicAtTheGate, home: Path, main_tree: Path, env: dict[str, str]) -> list[str]:
    """Takes the factory and human labels off the epic and forgets its T3 record and waker, as landing or dropping the
    epic does, and returns the label steps that failed."""
    failed: list[str] = []
    for label in (FACTORY_LABEL, HUMAN_LABEL):
        if label in epic.labels:
            attempt(f"bd label remove {label}", ["bd", "label", "remove", epic.id, label], main_tree, env, failed)
    t3_wake.forget(home, epic.id)
    return failed


def close_out(epic: EpicAtTheGate, message: str, sha: str, home: Path, main_tree: Path) -> Landed:
    """Records the decision, closes the epic and removes its labels and branches, each step on its own."""
    env = env_as_git_user(main_tree)
    failed: list[str] = []
    attempt("bd update", ["bd", "update", epic.id, "--set-metadata", f"{DECISION_KEY}={MERGE}",
                          "--set-metadata", f"{LANDED_KEY}={sha}"], main_tree, env, failed)
    try:
        move_open_tasks(epic.id, env, main_tree)
    except (CommandError, EpicReadError) as error:
        failed.append(f"move the open tasks to a new epic: {error}")
    closed = epic.closed or attempt("bd close", ["bd", "close", epic.id, "--reason", f"{sha}: {subject(message)}"],
                                    main_tree, env, failed)
    if HOLDOUTS_KEY in epic.metadata:
        attempt("retire the holdouts", ["bd", "update", epic.id, "--unset-metadata", HOLDOUTS_KEY], main_tree, env,
                failed)
    failed += release_from_factory(epic, home, main_tree, env)
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
        landed = close_out(epic, message, sha, home, main_tree)
        return landed, settings
    finally:
        release_lock(lock)


def turn_back(epic_id: str, refused: RebuildRefused, main_tree: Path) -> str:
    """Posts the refusal on the epic and returns the comment.

    An epic at the gate leaves it: its gate state and human label come off, so the scheduler's next call finds it
    finished and runs validation, which catches up with main. Its pass count, test cleanup and tidy stay as they are,
    because the epic branch did not change. An epic parked at the pass cap stays parked.
    """
    comment = refused.comment(epic_id)
    env = env_as_git_user(main_tree)
    run(["bd", "comment", epic_id, comment], main_tree, env)
    if refused.leaves_the_gate:
        run(["bd", "update", epic_id, *unset_metadata(GATE_STATE_KEY)], main_tree, env)
        run(["bd", "label", "remove", epic_id, HUMAN_LABEL], main_tree, env)
    return comment


def epic_waiting(epic_id: str, main_tree: Path) -> EpicAtTheGate:
    """The epic at the gate, which takes a decision short of the merge only until it lands."""
    epic = epic_at_the_gate(epic_id, main_tree)
    if epic.landed:
        raise GateError(f"{epic_id} landed on main as {epic.landed}, so the gate takes no other decision on it")
    return epic


def shown_items(epic_id: str, main_tree: Path) -> str:
    """The assumptions, the removed tests and the beads found outside the epic, as JSON, for the decisions that name
    them."""
    epic = epic_waiting(epic_id, main_tree)
    return json.dumps({
        "epic": epic.id,
        "assumptions": [{"number": number, "bead": each.bead, "title": each.title, "text": each.text}
                        for number, each in numbered_assumptions(epic.id, epic.title, main_tree)],
        "removed": [each.fields() for each in cleanup.removed_before(read_bead(epic.id, main_tree))],
        "outside": [{"bead": each.bead, "title": each.title, "found_in": each.found_in}
                    for each in outside_of(epic.id, main_tree)]})


def mark_wrong(epic_id: str, number: int, why: str, main_tree: Path) -> str:
    """Posts the human's word that the assumption the gate numbers so is wrong, on the bead that made it."""
    epic = epic_waiting(epic_id, main_tree)
    chosen = assumption(epic.id, epic.title, number, main_tree, GateError)
    run(["bd", "comment", chosen.bead, f"{WRONG_PREFIX}{chosen.text}\n\n{why}"], main_tree,
        env_as_git_user(main_tree))
    return f"Assumption {number} of {epic.id} is marked wrong on {chosen.bead}."


def finding_outside(epic_id: str, bead: str, main_tree: Path) -> EpicAtTheGate:
    epic = epic_waiting(epic_id, main_tree)
    if bead not in {each.bead for each in outside_of(epic.id, main_tree)}:
        raise GateError(f"{bead} is no open bead found outside {epic.id}, so the gate leaves it as it is")
    return epic


def keep_finding(epic_id: str, bead: str, main_tree: Path) -> str:
    epic = finding_outside(epic_id, bead, main_tree)
    run(["bd", "comment", bead, f"Kept open by the human at the acceptance gate of {epic.id}."], main_tree,
        env_as_git_user(main_tree))
    return f"{bead} stays open."


def close_finding(epic_id: str, bead: str, main_tree: Path) -> str:
    epic = finding_outside(epic_id, bead, main_tree)
    run(["bd", "close", bead, "--reason", f"Closed by the human at the acceptance gate of {epic.id}."], main_tree,
        env_as_git_user(main_tree))
    return f"{bead} is closed."


def restore_test(epic_id: str, test: str, file: str | None, home: Path, main_tree: Path) -> str:
    """Puts a test the test cleanup removed back on the epic branch, and takes it out of cleanup.removed."""
    epic = epic_waiting(epic_id, main_tree)
    shown = read_bead(epic.id, main_tree)
    removals = cleanup.removed_before(shown)
    removal = gate_restore.removal_named(removals, test, file)
    head = required_head(epic.branch, main_tree, GateError)
    restored = gate_restore.restore(removal, removals, gate_restore.EpicHead(epic.id, epic.branch, head), home,
                                    main_tree)
    kept = [each.fields() for each in removals if each != removal]
    env = env_as_git_user(main_tree)
    run(["bd", "update", epic.id, *set_metadata((cleanup.REMOVED_KEY, json.dumps(kept)))], main_tree, env)
    run(["bd", "comment", epic.id, f"Restored at the acceptance gate: {removal.test} ({removal.file}) is back on "
                                   f"{epic.branch} in the commit {restored}. Validation never ran it, so the merge "
                                   "runs the full suite again."], main_tree, env)
    return restored


def send_epic_back(epic_id: str, notes: list[str], proposals: Path, main_tree: Path) -> str:
    """Files a task for each note, and takes the epic off the gate with its pass count started again."""
    epic = epic_waiting(epic_id, main_tree)
    kept = gate_send_back.notes_of(notes)
    env = env_as_git_user(main_tree)
    filed = gate_send_back.file_tasks(epic.id, kept, gate_send_back.proposals_for(kept, proposals), env, main_tree)
    run(["bd", "comment", epic.id, gate_send_back.comment_of(epic.id, filed)], main_tree, env)
    run(["bd", "update", epic.id, *set_metadata((DECISION_KEY, SEND_BACK)), *unset_metadata(GATE_STATE_KEY),
         *pass_ledger.restarted_pass()], main_tree, env)
    run(["bd", "label", "remove", epic.id, HUMAN_LABEL], main_tree, env)
    return gate_send_back.printed_lines(epic.id, filed)


def drop_epic(epic_id: str, home: Path, main_tree: Path) -> str:
    """Closes the epic without landing it, ends the laps still open on its tasks, and keeps its epic branch."""
    epic = epic_waiting(epic_id, main_tree)
    env = env_as_git_user(main_tree)
    run(["bd", "update", epic.id, *set_metadata((DECISION_KEY, DROP))], main_tree, env)
    ended = gate_drop.end_laps(epic.id, main_tree)
    run(["bd", "close", epic.id, "--reason", f"Dropped at the acceptance gate. The epic branch {epic.branch} stays."],
        main_tree, env)
    failed = release_from_factory(epic, home, main_tree, env)
    if failed:
        raise CommandError("; ".join(failed))
    laps = f" The laps of {', '.join(ended)} ended." if ended else ""
    return f"{epic.id} is dropped and closed.{laps} Its epic branch {epic.branch} stays until you delete it."


def decide(args: argparse.Namespace, home: Path, main_tree: Path) -> str:
    """Writes one of the gate's decisions short of the merge and returns the line that says what changed."""
    if args.mode == SEND_BACK:
        return send_epic_back(args.epic, args.note, Path(args.proposals), main_tree)
    if args.mode == DROP:
        return drop_epic(args.epic, home, main_tree)
    if args.mode == ITEMS:
        return shown_items(args.epic, main_tree)
    if args.mode == WRONG:
        return mark_wrong(args.epic, args.number, args.why, main_tree)
    if args.mode == KEEP_FINDING:
        return keep_finding(args.epic, args.bead, main_tree)
    if args.mode == CLOSE_FINDING:
        return close_finding(args.epic, args.bead, main_tree)
    return restore_test(args.epic, args.test, args.file, home, main_tree)


def run_decision(args: argparse.Namespace) -> int:
    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = settings_reader.jidoka_home(args.jidoka_home)
        print(decide(args, home, main_tree))
    except (GateError, gate_restore.RestoreError, gate_send_back.SendBackError, PassError, EpicReadError, CommandError,
            settings_reader.SettingsError, rules.RulesError, OSError) as error:
        print(f"gate: {error}", file=sys.stderr)
        return 1
    return 0


def parsed_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="gate.py", description="Write the human's decision on an epic at the "
                                                                 "acceptance gate.")
    modes = parser.add_subparsers(dest="mode", required=True)
    merging = modes.add_parser(MERGE, help="land the epic on local main as one commit")
    merging.add_argument("epic")
    merging.add_argument("--message", required=True, help="the commit message, which names no bead")
    listing = modes.add_parser(ITEMS, help="print the assumptions, removed tests and findings the decisions name")
    listing.add_argument("epic")
    wrong = modes.add_parser(WRONG, help="mark an assumption the gate comment lists wrong")
    wrong.add_argument("epic")
    wrong.add_argument("number", type=int, help="the assumption's number in the gate comment")
    wrong.add_argument("--why", required=True, help="what is wrong with it, in the human's words")
    restoring = modes.add_parser(RESTORE, help="put a test the test cleanup removed back on the epic branch")
    restoring.add_argument("epic")
    restoring.add_argument("test", help="the test as the Tests removed table names it")
    restoring.add_argument("--file", help="the file the test was removed from, when two removed tests share a name")
    keeping = modes.add_parser(KEEP_FINDING, help="keep a bead found outside the epic open")
    closing = modes.add_parser(CLOSE_FINDING, help="close a bead found outside the epic")
    for finding in (keeping, closing):
        finding.add_argument("epic")
        finding.add_argument("bead")
    sending_back = modes.add_parser(SEND_BACK, help="send the epic back with a note for each problem")
    sending_back.add_argument("epic")
    sending_back.add_argument("--note", action="append", default=[], help="one problem, as `<file>:<line>: <text>` "
                                                                          "when pinned to a diff line; repeat it")
    sending_back.add_argument("--proposals", required=True, help="the send-back worker's JSON list, one proposal "
                                                                 "for each note")
    dropping = modes.add_parser(DROP, help="close the epic without landing it and keep its epic branch")
    dropping.add_argument("epic")
    for mode in (merging, listing, wrong, restoring, keeping, closing, sending_back, dropping):
        mode.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parsed_arguments(argv)
    if args.mode != MERGE:
        return run_decision(args)
    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = settings_reader.jidoka_home(args.jidoka_home)
        landed, settings = merge(args.epic, args.message, home, main_tree)
    except WaitingOnEdits as waiting:
        print(f"gate: {waiting}. Main is unchanged and {args.epic} waits at the gate. Commit or set aside:")
        for name in waiting.files:
            print(f"  {name}")
        return WAITING_ON_EDITS_EXIT_CODE
    except RebuildRefused as refused:
        try:
            comment = turn_back(args.epic, refused, main_tree)
        except CommandError as error:
            comment = refused.unwritten(args.epic, error)
        print(f"gate: {comment}", file=sys.stderr)
        return refused.exit_code
    except (GateError, EpicReadError, LandingError, CommandError, settings_reader.SettingsError, rules.RulesError,
            PassError, OSError) as error:
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
