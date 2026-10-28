#!/usr/bin/env python3
"""The page that sits beside the handoff comment on an epic.

handoff.py imports it. A page is one self-contained HTML file in `<jidoka-home>/pages/<repo>/handoff-<epic>.html`,
never in the repo, and a later handoff of the same epic replaces it. The look is the stylesheet of the explain skill,
inlined; the parts are listed in that skill's SKILL.md. Every word comes from the table and the rules the handoff
writes, and is escaped here. The handoff comment holds the same table in plain text, so the page can fall behind it and
the bead still wins.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

import question_page

NO_RULES = "The epic sets no factory rules, so the repo settings apply."


@dataclass(frozen=True)
class Row:
    """One task of the table: its title, its track and the reasons for it, its area, how many holdouts name it and
    its state."""
    task: str
    title: str
    track: str
    why: str
    area: str
    holdouts: int
    state: str


@dataclass(frozen=True)
class HandoffPage:
    """What a handoff page shows: the epic and its branch, one row for each task, the epic's factory rules as setting
    names to JSON text, and its guidance, or an empty string when it has none."""
    epic: str
    title: str
    branch: str
    rows: tuple[Row, ...]
    settings: tuple[tuple[str, str], ...]
    guidance: str


def page_path(home: Path, main_tree: Path, epic: str) -> Path:
    return home / question_page.PAGES_FOLDER / main_tree.name / f"handoff-{epic}.html"


def row_html(row: Row) -> str:
    cells = (f"{row.task} {row.title}", row.track, row.why, row.area, str(row.holdouts), row.state)
    return "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in cells) + "</tr>"


def tasks_table(page: HandoffPage) -> str:
    heads = ("Task", "Track", "Why", "Area", "Holdouts", "State")
    return ("<table>\n<thead><tr>" + "".join(f"<th>{head}</th>" for head in heads) + "</tr></thead>\n<tbody>\n"
            + "\n".join(row_html(row) for row in page.rows) + "\n</tbody>\n</table>")


def settings_html(page: HandoffPage) -> str:
    if not page.settings:
        return ""
    rows = "\n".join(f"<tr><td>{escape(name)}</td><td><code>{escape(value)}</code></td></tr>"
                     for name, value in page.settings)
    return f"<table>\n<thead><tr><th>Setting</th><th>Value</th></tr></thead>\n<tbody>\n{rows}\n</tbody>\n</table>"


def rules_html(page: HandoffPage) -> str:
    if not page.settings and not page.guidance:
        return f"<p>{escape(NO_RULES)}</p>"
    guidance = f'<h3>Guidance</h3>\n<p class="guidance">{escape(page.guidance)}</p>' if page.guidance else ""
    return "\n".join(part for part in (settings_html(page), guidance) if part)


def render(page: HandoffPage, stylesheet: str) -> str:
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>Handoff: {escape(page.title)}</title>\n<style>\n{stylesheet}</style>\n</head>\n<body>\n'
            f'<header>\n<p>Handoff of {escape(page.epic)} on {escape(page.branch)}</p>\n'
            f'<h1>{escape(page.title)}</h1>\n</header>\n'
            f'<section class="tasks">\n<h2>The tasks</h2>\n{tasks_table(page)}\n</section>\n'
            f'<section class="rules">\n<h2>The factory rules</h2>\n{rules_html(page)}\n</section>\n'
            f'</body>\n</html>\n')


def write(page: HandoffPage, home: Path, main_tree: Path) -> Path:
    """Writes the page and returns its path; raises OSError when the stylesheet cannot be read or the file written."""
    stylesheet = question_page.STYLESHEET.read_text(encoding="utf-8")
    path = page_path(home, main_tree, page.epic)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(page, stylesheet), encoding="utf-8")
    return path
