#!/usr/bin/env python3
"""The page that sits beside a question on its bead.

park.py imports it. A page is one self-contained HTML file in
`<jidoka-home>/pages/<repo>/question-<task>.html`, never in the repo, and a later question on the same task replaces
it. The look is the stylesheet of the explain skill, inlined; the parts are listed in that skill's SKILL.md. The words
are the worker's, from the question report, and are escaped here. The bead's comment holds the same words in plain
text, so the page can fall behind it and the bead still wins.

The page marks a slot, `data-jidoka-slot="answer-panel"`, where jidoka-ui draws the answer panel.
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from html import escape
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
STYLESHEET = SCRIPTS.parent / "skills" / "explain" / "page.css"
PAGES_FOLDER = "pages"
ANSWER_SLOT = "answer-panel"
STEP_WIDTH = 320
STEP_LINE_CHARS = 38
LINE_HEIGHT = 18
STEP_PADDING = 10
ARROW_HEIGHT = 26
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


def page_path(home: Path, main_tree: Path, task: str) -> Path:
    return home / PAGES_FOLDER / main_tree.name / f"question-{task}.html"


def diagram(steps: tuple[str, ...], label: str) -> str:
    """The steps as boxes down one column, joined by arrows, in an inline SVG that the label names for a screen
    reader."""
    wrapped = [textwrap.wrap(step, STEP_LINE_CHARS) or [step] for step in steps]
    heights = [len(lines) * LINE_HEIGHT + 2 * STEP_PADDING for lines in wrapped]
    total = sum(heights) + ARROW_HEIGHT * (len(steps) - 1)
    parts = [f'<svg role="img" aria-label="{escape(label)}" viewBox="0 0 {STEP_WIDTH} {total}" '
             f'width="{STEP_WIDTH}">']
    top = 0
    for index, lines in enumerate(wrapped):
        height = heights[index]
        parts.append(f'<rect x="1" y="{top + 1}" width="{STEP_WIDTH - 2}" height="{height - 2}" rx="6"/>')
        for number, line in enumerate(lines):
            baseline = top + STEP_PADDING + LINE_HEIGHT * number + LINE_HEIGHT - 5
            parts.append(f'<text x="{STEP_WIDTH // 2}" y="{baseline}" text-anchor="middle">{escape(line)}</text>')
        top += height
        if index < len(wrapped) - 1:
            middle = STEP_WIDTH // 2
            parts.append(f'<path d="M{middle} {top} V{top + ARROW_HEIGHT - 6}"/>')
            parts.append(f'<polygon points="{middle - 5},{top + ARROW_HEIGHT - 8} {middle + 5},{top + ARROW_HEIGHT - 8} '
                         f'{middle},{top + ARROW_HEIGHT}"/>')
            top += ARROW_HEIGHT
    parts.append("</svg>")
    return "\n".join(parts)


def card_html(card: Card) -> str:
    kind = "option recommended" if card.recommended else "option"
    after = (f'\n<h4 class="next-label">What happens next</h4>\n<p class="next">{escape(card.next_step)}</p>'
             if card.next_step else "")
    return (f'<article class="{kind}">\n<h3>{escape(card.name)}</h3>\n'
            f'<p class="confidence">{card.confidence}% confident this is the right answer</p>{after}\n</article>')


def render(page: QuestionPage, stylesheet: str) -> str:
    shown = (f'<section class="shown">\n<h2>What the app shows</h2>\n<p>{escape(page.shown)}</p>\n</section>\n'
             if page.shown else "")
    why = (f'<section class="why">\n<h2>Why</h2>\n{diagram(page.why, WHY_LABEL)}\n</section>\n' if page.why else "")
    cards = "\n".join(card_html(card) for card in page.cards)
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>Question: {escape(page.title)}</title>\n<style>\n{stylesheet}</style>\n</head>\n<body>\n'
            f'<header>\n<p>Question on {escape(page.task)}</p>\n<h1>{escape(page.title)}</h1>\n</header>\n'
            f'<section class="in-short">\n<h2>In short</h2>\n<p>{escape(page.found)}</p>\n</section>\n'
            f'{shown}{why}'
            f'<section>\n<h2>The options</h2>\n<div class="options">\n{cards}\n</div>\n</section>\n'
            f'<section class="answer-slot" data-jidoka-slot="{ANSWER_SLOT}">\n<h2>Your answer</h2>\n'
            f'<p>jidoka-ui draws the answer panel here. The bead holds the question in plain text.</p>\n</section>\n'
            f'</body>\n</html>\n')


def write(page: QuestionPage, home: Path, main_tree: Path) -> Path:
    """Writes the page and returns its path; raises OSError when the stylesheet cannot be read or the file written."""
    stylesheet = STYLESHEET.read_text(encoding="utf-8")
    path = page_path(home, main_tree, page.task)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(page, stylesheet), encoding="utf-8")
    return path
