#!/usr/bin/env python3
"""The page that sits beside the handoff comment on an epic.

handoff.py imports it. The page shows the table of the epic's tasks and the epic's factory rules. Every word comes from
the table and the rules the handoff writes, and is escaped here. The handoff comment holds the same table in plain
text, so the page can fall behind it and the bead still wins. page.py says where a page lives and how it looks.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

import page as shared

KIND = "handoff"
NO_RULES = "The epic sets no factory rules, so the repo settings apply."


@dataclass(frozen=True)
class Row:
    """One task of the table: its title, its track and the reasons for it, its area, how many holdouts name it, the
    acceptance specs it makes pass and its state."""
    task: str
    title: str
    track: str
    why: str
    area: str
    holdouts: int
    specs: tuple[str, ...]
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


def row_html(row: Row) -> str:
    cells = (f"{row.task} {row.title}", row.track, row.why, row.area, str(row.holdouts), ", ".join(row.specs),
             row.state)
    return "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in cells) + "</tr>"


def tasks_table(page: HandoffPage) -> str:
    heads = ("Task", "Track", "Why", "Area", "Holdouts", "Specs", "State")
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


def body(page: HandoffPage) -> str:
    return (shared.section("The tasks", tasks_table(page), "tasks")
            + shared.section("The factory rules", rules_html(page), "rules"))


def write(page: HandoffPage, home: Path, main_tree: Path) -> Path:
    """Writes the page and returns its path; raises OSError when the stylesheet cannot be read or the file written."""
    head = shared.PageHead(KIND, page.epic, "Handoff", f"Handoff of {page.epic} on {page.branch}", page.title)
    return shared.write(head, body(page), home, main_tree)
