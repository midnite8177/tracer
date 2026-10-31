"""The count of an epic's passes, what ending a pass resets, and the cap on the count.

Review, validation and the scheduler all act on the end of a pass, and none of them names a key of another stage.
A pass ends red, at a red full suite or a red holdout, or clean, when the epic goes to the acceptance gate. A red end
calls `end_pass`, which counts the pass once and takes the test cleanup's and the tidy's state off the epic, so the
next pass starts with both again. A clean end calls `end_clean_pass`, which counts the pass the same way and leaves
the test cleanup's and the tidy's state as they are. A settled review counts its pass early, with `counted_by_review`,
and flags it; the pass's end then finds the flag, takes it off and counts nothing, so the one pass is never counted
twice, and the next pass starts with no flag. A pass with no file to review has no review to count it, and its end
counts it, so such an epic still reaches the cap. Only a red validation or a send back at the gate starts a pass past
the first, because a review files its large findings outside the epic.

A send back at the gate restarts the pass with `restarted_pass`. The count starts again, and the test cleanup's and the
tidy's state come off, so the next pass cleans and tidies again. The review needs no reset, because it runs whenever the
epic's files changed since its head.

The pass count is capped at three. An epic that holds open tasks after its third pass would start a fourth.
`parks_at_the_cap` says so, and `park_at_the_cap` parks the epic with a question instead, and records the count in
`pass.asked` so that each pass past the cap asks once. Taking the human label off runs the next pass. The human can
land the parked epic instead: `asked_at_the_cap` tells the gate script the epic waits on that question.
Everything here writes to bd with BEADS_ACTOR set to jidoka.
"""
from __future__ import annotations

from pathlib import Path

import cleanup
import park
import tidy
from commands import env_as_factory, metadata_of, read_bead, run, set_metadata, unset_metadata
from pass_support import PassError, count_of

PASSES_KEY = "review.passes"
REVIEWED_KEY = "review.reviewed"
ASKED_KEY = "pass.asked"
PASS_CAP = 3
NEXT_PASS = "Run another pass"
LAND = "Land what the epic holds"


def counted_by_review(shown: dict) -> list[str]:
    """The metadata a settled review writes to count its pass and to flag that the pass has been counted."""
    return set_metadata((PASSES_KEY, count_of(shown, PASSES_KEY) + 1), (REVIEWED_KEY, 1))


def counted_at_the_end(epic: str, main_tree: Path) -> list[str]:
    """The metadata that counts the epic's pass at its end, unless its review already did, and then takes the
    review's flag off, so the next pass starts unreviewed."""
    shown = read_bead(epic, main_tree)
    if metadata_of(shown).get(REVIEWED_KEY):
        return unset_metadata(REVIEWED_KEY)
    return set_metadata((PASSES_KEY, count_of(shown, PASSES_KEY) + 1))


def end_pass(epic: str, main_tree: Path) -> None:
    """Ends the epic's pass red: counts it, and takes the test cleanup's and the tidy's state off the epic, so the
    next pass starts with a test cleanup and a tidy."""
    counted = counted_at_the_end(epic, main_tree)
    run(["bd", "update", epic, *unset_metadata(cleanup.STATE_KEY, tidy.STATE_KEY), *counted], main_tree,
        env_as_factory())


def end_clean_pass(epic: str, main_tree: Path) -> None:
    """Ends the epic's pass clean, on its way to the acceptance gate: counts it, and leaves the test cleanup's and the
    tidy's state as they are."""
    run(["bd", "update", epic, *counted_at_the_end(epic, main_tree)], main_tree, env_as_factory())


def restarted_pass() -> list[str]:
    """The metadata a send back at the acceptance gate takes off the epic: its passes are counted from none, so the
    cap asks again only after three more, and the test cleanup's and the tidy's state go, so the next pass starts with
    both."""
    return unset_metadata(PASSES_KEY, ASKED_KEY, cleanup.STATE_KEY, tidy.STATE_KEY)


def parks_at_the_cap(shown: dict, has_open_tasks: bool) -> bool:
    """True when the epic would start a pass past the cap, and has not asked about this one yet."""
    passes = count_of(shown, PASSES_KEY)
    return has_open_tasks and passes >= PASS_CAP and passes > count_of(shown, ASKED_KEY)


def asked_at_the_cap(shown: dict) -> bool:
    """True when the epic's passes have reached the cap and it asked about the next one, so it waits on the human's
    answer."""
    passes = count_of(shown, PASSES_KEY)
    return passes >= PASS_CAP and passes == count_of(shown, ASKED_KEY)


def question_of(epic: str, passes: int) -> park.Question:
    """The question the pass cap asks: one sentence, what the epic holds, and an option for each way on, each with its
    next step."""
    found = (f"{epic} has been through {passes} passes, the pass cap is {PASS_CAP}, and it still holds open tasks, so "
             "the factory parked it before the next pass.")
    options = (park.Option(NEXT_PASS, 60, "Take the human label off the epic to run the next pass."),
               park.Option(LAND, 40, f"Run /jidoka:accept {epic} to land what the epic holds, which moves its open "
                                     "tasks to a new epic."))
    return park.plain_question(f"Should {epic} run a pass past the pass cap?", found, options, NEXT_PASS)


def park_at_the_cap(epic: str, shown: dict, home: Path, main_tree: Path) -> None:
    """Parks the epic with a question, instead of starting a pass past the cap."""
    passes = count_of(shown, PASSES_KEY)
    park.park_epic_on_question(epic, question_of(epic, passes), {ASKED_KEY: str(passes)}, home, main_tree)
