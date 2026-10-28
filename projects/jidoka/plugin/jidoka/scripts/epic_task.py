"""Filing a task: in the epic, a child of the epic with the track and the area the scheduler needs to open its lap, or
outside every epic, a bead with no parent that a bench or a later epic takes up."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import lap_record
from commands import created_id, env_as_factory, run

DISCOVERED_FROM = "discovered-from"


@dataclass(frozen=True)
class NewTask:
    """The words and the placement of a task before it exists: its title, its description with the Demo and Seams
    sections, the area it touches and its track. Four strings that a caller must not swap travel as one record."""
    title: str
    description: str
    area: str
    track: str


def file_task(epic: str, task: NewTask, found_in: str | None, env: dict[str, str], main_tree: Path) -> str:
    """Files a task in the epic, linked discovered-from to the bead it was found in when there is one, and returns its
    id. The bead is written under the actor of `env`, which the caller chooses."""
    origin = [] if found_in is None else ["--deps", f"{DISCOVERED_FROM}:{found_in}"]
    created = run(["bd", "create", "--title", task.title, "--description", task.description, "--type=task",
                   "--parent", epic, *origin, "--json"], main_tree, env)
    filed = created_id(created)
    run(["bd", "update", filed, *lap_record.assigning(task.track, task.area)], main_tree, env)
    return filed


def file_outside(title: str, description: str, found_in: str | None, labels: list[str], main_tree: Path) -> str:
    """Files a task with no parent and no area, so no lap takes it, linked discovered-from to the bead it was found in
    when there is one and carrying the labels, and returns its id."""
    env = env_as_factory()
    origin = [] if found_in is None else ["--deps", f"{DISCOVERED_FROM}:{found_in}"]
    tagged = ["--labels", ",".join(labels)] if labels else []
    created = run(["bd", "create", "--title", title, "--description", description, "--type=task", *tagged, *origin,
                   "--json"], main_tree, env)
    return created_id(created)
