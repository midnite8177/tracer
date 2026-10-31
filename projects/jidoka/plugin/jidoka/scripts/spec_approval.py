#!/usr/bin/env python3
"""Shows the human a proposal of acceptance specs on its epic, and reads their answer back.

`post <epic>` reads one JSON object on stdin, `{"cases": [...], "interface": [...]}`, in the shape that spec_cases.py
writes, except that each case also carries `code`, the code of the spec that would be written for it. It refuses a
proposal that spec_cases.py would refuse and a case with no code. It writes the proposal's page
(spec_approval_page.py) in the jidoka home, then comments on the epic with the proposal in plain text and the page's
link, puts the `human` label on the epic and sets its metadata `question.options` to the two answers, `Approve` and
`Ask back`, with no recommendation. The proposal comment is posted as jidoka. jidoka-ui serves the page beside the
epic and draws its answer panel from that metadata, so a press on an answer comments it on the epic and takes the label
off. It prints `{"epic", "page"}`. A page that cannot be written refuses the post before any bead changes. Posting
again replaces the page and asks again.

`answer <epic>` prints `{"epic", "waiting", "replies"}`: whether the epic still carries the human label, and the
comments by anyone but jidoka since the latest proposal comment, oldest first. The human has answered when `waiting` is
false. A reply of `Approve` is an approval; `Ask back` and any other reply say what the human wants changed.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  success.
  1  it refused, or a bd command failed, with the reason on stderr; a refusal changes no bead.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import park
import settings_reader
import spec_approval_page
import spec_cases
from commands import (COMMAND_TIMEOUT_SECONDS, FACTORY_ACTOR, HUMAN_LABEL, CommandError, bd_comments,
                      env_as_factory, is_labeled_for_human, read_bead, run, set_metadata, unset_metadata)
from epic_reader import EpicReadError, shown_epic
from spec_approval_page import ProposedCase

PROPOSAL_PREFIX = "Spec approval: "
APPROVE, ASK_BACK = "Approve", "Ask back"


class SpecApprovalError(Exception):
    """A proposal that cannot be shown or an answer that cannot be read, worded for the person who reads stderr."""


def proposal_of(raw: str) -> tuple[list[ProposedCase], list[spec_cases.InterfaceRow]]:
    """The proposal on stdin as cases with their code and interface rows; raises spec_cases.SpecCasesError for what
    spec_cases.py refuses too, and SpecApprovalError for a case with no code."""
    proposal = spec_cases.parsed_proposal(raw)
    proposed = []
    for number, (case, written) in enumerate(zip(proposal.cases, proposal.given_cases), start=1):
        code = written.get("code")
        if not (isinstance(code, str) and any(character.isalnum() for character in code)):
            raise SpecApprovalError(f"case {number} has no code. Write the spec's code for every case")
        proposed.append(ProposedCase(case, code.rstrip()))
    return proposed, proposal.interface


def fenced(code: str) -> str:
    fence = "```"
    while fence in code:
        fence += "`"
    return f"{fence}\n{code}\n{fence}"


def comment_of(epic: str, proposed: list[ProposedCase], interface: list[spec_cases.InterfaceRow], page: Path) -> str:
    """The proposal in plain text; the page adds the side-by-side layout and no fact."""
    cases = spec_cases.rendered([item.case for item in proposed], interface)
    codes = "\n\n".join(f"{number}. {item.case.name}\n{fenced(item.code)}"
                        for number, item in enumerate(proposed, start=1))
    return (f"{PROPOSAL_PREFIX}{len(proposed)} test cases proposed for {epic}\n\n{cases}\n\n### Code\n\n{codes}\n\n"
            f"Page: {page.as_uri()}\n\n"
            f"Press {APPROVE} or {ASK_BACK} in the answer panel. The {HUMAN_LABEL} label on {epic} comes off with "
            "the answer.")


def post(epic: str, raw: str, home: Path, main_tree: Path) -> dict:
    proposed, interface = proposal_of(raw)
    shown = shown_epic(epic, main_tree)
    title = f"Approve the acceptance specs of {shown.get('title') or epic}"
    try:
        page = spec_approval_page.write(spec_approval_page.SpecApprovalPage(epic, title, tuple(proposed),
                                                                           tuple(interface)), home, main_tree)
    except OSError as error:
        raise SpecApprovalError(f"the spec approval page could not be written: {error}") from error
    env = env_as_factory()
    run(["bd", "comment", epic, comment_of(epic, proposed, interface, page)], main_tree, env)
    options = json.dumps([{"name": name, "confidence": park.LEAST_CONFIDENCE} for name in (APPROVE, ASK_BACK)])
    run(["bd", "update", epic, f"--add-label={HUMAN_LABEL}", *set_metadata((park.OPTIONS_KEY, options)),
         *unset_metadata(park.RECOMMENDED_KEY)], main_tree, env)
    return {"epic": epic, "page": str(page)}


def answer(epic: str, main_tree: Path) -> dict:
    comments = bd_comments(epic, main_tree)
    posted = [index for index, comment in enumerate(comments)
              if comment.get("author") == FACTORY_ACTOR and str(comment.get("text") or "").startswith(PROPOSAL_PREFIX)]
    if not posted:
        raise SpecApprovalError(f"{epic} holds no spec approval. Post the proposal with spec_approval.py post {epic}")
    replies = [str(comment.get("text") or "").strip() for comment in comments[posted[-1] + 1:]
               if comment.get("author") != FACTORY_ACTOR]
    return {"epic": epic, "waiting": is_labeled_for_human(read_bead(epic, main_tree)),
            "replies": [reply for reply in replies if reply]}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="spec_approval.py", description="Show the human a proposal of acceptance "
                                                                         "specs, or read their answer.")
    modes = parser.add_subparsers(dest="mode", required=True)
    posting = modes.add_parser("post", help="show the JSON proposal on stdin on the epic")
    posting.add_argument("epic")
    posting.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    answering = modes.add_parser("answer", help="print whether the human answered, and what they said")
    answering.add_argument("epic")
    args = parser.parse_args(argv)
    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        printed = (post(args.epic, sys.stdin.read(), settings_reader.jidoka_home(args.jidoka_home), main_tree)
                   if args.mode == "post" else answer(args.epic, main_tree))
    except (SpecApprovalError, spec_cases.SpecCasesError, EpicReadError, CommandError, settings_reader.SettingsError,
            OSError) as error:
        print(f"spec_approval: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
