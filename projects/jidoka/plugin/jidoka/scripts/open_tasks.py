"""Moves the tasks an epic still holds open, when it lands, to a new epic that planning takes up.

An epic parked at its pass cap can be landed with tasks still open. They cannot stay under a closed epic, so they
move to a new epic with no `factory` label, which holds them until the human hands it off. The old epic records the
new one under `gate.open_tasks_epic`, so a rerun moves what is left to the same epic and makes no second one.
"""
from __future__ import annotations

from pathlib import Path

from commands import created_id, metadata_of, read_bead, run
from epic_reader import read_epic

OPEN_TASKS_EPIC_KEY = "gate.open_tasks_epic"


def new_epic_for(epic: dict, env: dict[str, str], main_tree: Path) -> str:
    """The epic that holds the old epic's open tasks: the one it recorded, else a new one, recorded at once."""
    recorded = str(metadata_of(epic).get(OPEN_TASKS_EPIC_KEY) or "")
    if recorded:
        return recorded
    old = str(epic["id"])
    created = run(["bd", "create", "--title", f"{epic.get('title') or old}, the tasks left open", "--type=epic",
                   "--description", f"The tasks of {old} that were still open when it landed at its pass cap.\n\n"
                   f"## Out of Scope\n\nThe work {old} put on main.", "--json"], main_tree, env)
    new = created_id(created)
    run(["bd", "update", old, "--set-metadata", f"{OPEN_TASKS_EPIC_KEY}={new}"], main_tree, env)
    return new


def move_open_tasks(epic_id: str, env: dict[str, str], main_tree: Path) -> None:
    """Moves each open task of the epic to its epic for open tasks, made on the first move."""
    shown = read_bead(epic_id, main_tree)
    tasks = read_epic(shown, main_tree).tasks
    if not tasks:
        return
    new = new_epic_for(shown, env, main_tree)
    for task in tasks:
        run(["bd", "update", task.id, f"--parent={new}"], main_tree, env)
