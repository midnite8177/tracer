#!/usr/bin/env python3
"""The page beside a proposal of acceptance specs on its epic.

spec_approval.py imports it. The page shows each proposed test case with its code on one side and, on the other, its
plain reading and its answer to the deletion question, then the interface table of what the protocol driver does not
offer yet. Every word comes from the proposal, and is escaped here. The comment that spec_approval.py posts holds the
same words in plain text, so the page can fall behind it and the bead still wins. page.py says where a page lives and
how it looks.

The page marks a slot, `data-jidoka-slot="answer-panel"`, where jidoka-ui draws the answer panel, the same panel that a
question page uses.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

import page as shared
from question_page import ANSWER_SLOT
from spec_cases import INTERFACE_COLUMNS, INTERFACE_LEAD, NO_INTERFACE, InterfaceRow, SpecCase

KIND = "spec-approval"


@dataclass(frozen=True)
class ProposedCase:
    """One test case as the page shows it: the case with the code of the spec that would be written for it."""
    case: SpecCase
    code: str


@dataclass(frozen=True)
class SpecApprovalPage:
    """What a spec approval page shows: the epic and its title, one entry for each proposed test case in the order of
    their numbers, and the rows of the interface table, empty when the driver offers everything."""
    epic: str
    title: str
    cases: tuple[ProposedCase, ...]
    interface: tuple[InterfaceRow, ...]


def case_html(number: int, proposed: ProposedCase) -> str:
    case = proposed.case
    code = (f'<div class="example">\n<h3>The spec</h3>\n<pre><code>{escape(proposed.code)}</code></pre>\n</div>')
    reading = (f'<div class="example">\n<h3>Plain reading</h3>\n<p class="reading">{escape(case.reading)}</p>\n'
               f'<h3>If this feature were deleted</h3>\n<p class="deletion">{escape(case.deletion)}</p>\n</div>')
    return (f'<article class="case">\n<h3>{number}. {escape(case.name)}</h3>\n'
            f'<div class="examples">\n{code}\n{reading}\n</div>\n</article>')


def interface_html(page: SpecApprovalPage) -> str:
    if not page.interface:
        return f"<p>{escape(NO_INTERFACE)}</p>"
    rows = "\n".join("<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in
                                       (row.interface, row.shape, ", ".join(str(user) for user in row.cases)))
                     + "</tr>" for row in page.interface)
    headers = "".join(f"<th>{escape(column)}</th>" for column in INTERFACE_COLUMNS)
    return (f"<p>{escape(INTERFACE_LEAD)}</p>\n<table>\n<thead><tr>{headers}</tr></thead>\n<tbody>\n{rows}\n"
            "</tbody>\n</table>")


def body(page: SpecApprovalPage) -> str:
    cases = "\n".join(case_html(number, proposed) for number, proposed in enumerate(page.cases, start=1))
    count = len(page.cases)
    short = (f"{count} test case{'s' if count != 1 else ''} proposed for {page.epic}. Read the code of each beside its "
             "plain reading, then approve them or ask back below.")
    return (shared.section("In short", f"<p>{escape(short)}</p>", "in-short")
            + shared.section("The test cases", cases, "cases")
            + shared.section("The interface table", interface_html(page), "interface")
            + shared.slot(ANSWER_SLOT, "Your answer",
                          "jidoka-ui draws the answer panel here. The bead holds the proposal in plain text."))


def write(page: SpecApprovalPage, home: Path, main_tree: Path) -> Path:
    """Writes the page and returns its path; raises OSError when the stylesheet cannot be read or the file written."""
    head = shared.PageHead(KIND, page.epic, "Spec approval", f"Acceptance specs proposed for {page.epic}", page.title)
    return shared.write(head, body(page), home, main_tree)
