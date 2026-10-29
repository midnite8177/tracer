#!/usr/bin/env python3
"""The page that sits beside a question on its bead.

park.py imports it. The page shows the options of a question: what the worker found, what the app shows, why step by
step, and a card for each option. The words are the worker's, from the question report, and are escaped here. The
bead's comment holds the same words in plain text, so the page can fall behind it and the bead still wins. page.py
says where a page lives and how it looks.

The page marks a slot, `data-jidoka-slot="answer-panel"`, where jidoka-ui draws the answer panel.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

import page as shared

KIND = "question"
ANSWER_SLOT = "answer-panel"
WHY_LABEL = "Why, step by step"


@dataclass(frozen=True)
class Card:
    """One option on the page: the worker's confidence in percent, what happens next ("" when the worker gave none)
    and whether it is the one the worker recommends."""
    name: str
    confidence: int
    next_step: str
    recommended: bool


@dataclass(frozen=True)
class QuestionPage:
    """What a question page shows. `shown` is "" and `why` is empty when the worker gave neither."""
    task: str
    title: str
    found: str
    shown: str
    why: tuple[str, ...]
    cards: tuple[Card, ...]


def card_html(card: Card) -> str:
    kind = "option recommended" if card.recommended else "option"
    after = (f'\n<h4 class="next-label">What happens next</h4>\n<p class="next">{escape(card.next_step)}</p>'
             if card.next_step else "")
    return (f'<article class="{kind}">\n<h3>{escape(card.name)}</h3>\n'
            f'<p class="confidence">{card.confidence}% confident this is the right answer</p>{after}\n</article>')


def body(page: QuestionPage) -> str:
    shown = shared.section("What the app shows", f"<p>{escape(page.shown)}</p>", "shown") if page.shown else ""
    why = shared.section("Why", shared.diagram(page.why, WHY_LABEL), "why") if page.why else ""
    cards = "\n".join(card_html(card) for card in page.cards)
    return (shared.section("In short", f"<p>{escape(page.found)}</p>", "in-short")
            + shown + why
            + shared.section("The options", f'<div class="options">\n{cards}\n</div>', "")
            + shared.slot(ANSWER_SLOT, "Your answer",
                          "jidoka-ui draws the answer panel here. The bead holds the question in plain text."))


def write(page: QuestionPage, home: Path, main_tree: Path) -> Path:
    """Writes the page and returns its path; raises OSError when the stylesheet cannot be read or the file written."""
    head = shared.PageHead(KIND, page.task, "Question", f"Question on {page.task}", page.title)
    return shared.write(head, body(page), home, main_tree)
