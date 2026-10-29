#!/usr/bin/env python3
"""What every page jidoka writes shares: the pages folder, the stylesheet, the document shell, the section, the slot
and the diagram.

question_page.py, handoff_page.py and gate_page.py import it and supply only their body sections. A page is one
self-contained HTML file in `<jidoka-home>/pages/<repo>/<kind>-<bead>.html`, never in the repo, and a later page of
the same kind for the same bead replaces it. The look is the stylesheet of the explain skill, inlined.
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from html import escape
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
STYLESHEET = SCRIPTS.parent / "skills" / "explain" / "page.css"
PAGES_FOLDER = "pages"
STEP_WIDTH = 320
STEP_LINE_CHARS = 38
LINE_HEIGHT = 18
STEP_PADDING = 10
ARROW_HEIGHT = 26


@dataclass(frozen=True)
class PageHead:
    """What names a page and heads it: its kind and bead make its file, `label` and `title` make the tab title, and
    `byline` is the line above the heading."""
    kind: str
    bead: str
    label: str
    byline: str
    title: str


def page_path(head: PageHead, home: Path, main_tree: Path) -> Path:
    return home / PAGES_FOLDER / main_tree.name / f"{head.kind}-{head.bead}.html"


def section(title: str, body: str, css: str) -> str:
    """A titled section of a page body; `body` is already escaped, and `css` is its class, or "" for none."""
    kind = f' class="{css}"' if css else ""
    return f"<section{kind}>\n<h2>{escape(title)}</h2>\n{body}\n</section>\n"


def slot(name: str, heading: str, text: str) -> str:
    """The section where jidoka-ui draws the panel that the slot `name` marks, with a line of text for a reader that
    has no jidoka-ui."""
    return (f'<section class="answer-slot" data-jidoka-slot="{escape(name)}">\n<h2>{escape(heading)}</h2>\n'
            f"<p>{escape(text)}</p>\n</section>\n")


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


def document(head: PageHead, body: str, stylesheet: str) -> str:
    """The HTML document: the head's label and title make the tab title, its byline is the line above the heading,
    and `body` holds the page's sections, already escaped."""
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{escape(head.label)}: {escape(head.title)}</title>\n<style>\n{stylesheet}</style>\n</head>\n'
            f'<body>\n<header>\n<p>{escape(head.byline)}</p>\n<h1>{escape(head.title)}</h1>\n</header>\n{body}'
            f'</body>\n</html>\n')


def write(head: PageHead, body: str, home: Path, main_tree: Path) -> Path:
    """Writes the page and returns its path; raises OSError when the stylesheet cannot be read or the file written."""
    stylesheet = STYLESHEET.read_text(encoding="utf-8")
    path = page_path(head, home, main_tree)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document(head, body, stylesheet), encoding="utf-8")
    return path
