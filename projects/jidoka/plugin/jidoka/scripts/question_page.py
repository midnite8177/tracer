#!/usr/bin/env python3
"""The page that sits beside a question on its bead.

park.py imports it. The page has the question as its heading, then what the worker found, the section that says what
the app shows or what happened, why step by step, and a card for each option. The words are the worker's, from the
question report, except on a permission question, whose heading, situation line, steps and cards park.py writes; all
are escaped here. The bead's comment holds the same words in plain text, so the page can fall behind it and the bead
still wins. page.py says where a page lives and how it looks.

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
    """One option on the page: its heading, the word the human types to choose it (None when the heading is the
    answer), the worker's confidence in percent, what happens next and whether it is the one the worker recommends.
    `reason` is the worker's reasoning for its pick, None on every card but the recommended one of a permission
    question."""
    heading: str
    answer_word: str | None
    confidence: int
    next_step: str
    reason: str | None
    recommended: bool


@dataclass(frozen=True)
class QuestionPage:
    """What a question page shows. `question` is its heading, the question in one sentence, so the page says what it
    asks. `shown` is None and `why` is empty when there is neither, and `shown_label` is the heading of the `shown`
    section."""
    task: str
    question: str
    found: str
    shown_label: str
    shown: str | None
    why: tuple[str, ...]
    cards: tuple[Card, ...]


def card_html(card: Card) -> str:
    kind = "option recommended" if card.recommended else "option"
    reason = (f'\n<h4 class="next-label">Why the worker picks it</h4>\n<p class="reason">{escape(card.reason)}</p>'
              if card.reason is not None else "")
    word = (f'\n<p class="answer">Answer word to type: <code class="answer-word">{escape(card.answer_word)}</code></p>'
            if card.answer_word is not None else "")
    return (f'<article class="{kind}">\n<h3>{escape(card.heading)}</h3>\n'
            f'<p class="confidence">{card.confidence}% confident this is the right answer</p>\n'
            f'<h4 class="next-label">What happens next</h4>\n<p class="next">{escape(card.next_step)}</p>'
            f'{reason}{word}\n</article>')


def body(page: QuestionPage) -> str:
    shown = ("" if page.shown is None
             else shared.section(page.shown_label, f"<p>{escape(page.shown)}</p>", "shown"))
    why = shared.section("Why", shared.diagram(page.why, WHY_LABEL), "why") if page.why else ""
    cards = "\n".join(card_html(card) for card in page.cards)
    return (shared.section("In short", f"<p>{escape(page.found)}</p>", "in-short")
            + shown + why
            + shared.section("The options", f'<div class="options">\n{cards}\n</div>', "")
            + shared.slot(ANSWER_SLOT, "Your answer",
                          "jidoka-ui draws the answer panel here. The bead holds the question in plain text."))


def write(page: QuestionPage, home: Path, main_tree: Path) -> Path:
    """Writes the page and returns its path; raises OSError when the stylesheet cannot be read or the file written."""
    head = shared.PageHead(KIND, page.task, "Question", f"Question on {page.task}", page.question)
    return shared.write(head, body(page), home, main_tree)
