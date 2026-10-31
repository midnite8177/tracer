"""Reads an epic and its tasks from bd, and holds the checks that stay true for as long as the factory holds the epic.

The handoff script and the scheduler both read an epic this way, and the scripts that watch epics read its children
through it. It also holds the recorded branch and the validated head of an epic. Each script that runs the
held-epic checks passes its own `Rerun`, so a refusal names the script the reader ran.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import holdouts
import settings_reader
from commands import bd_list, is_labeled_for_human, metadata_of, read_bead, run
from lap_record import area_of, open_lap

BRANCH_KEY = "factory.branch"
VALIDATED_HEAD_KEY = "validation.head"
BLOCKING = "blocks"
CLOSED = "closed"
EPIC_TYPE = "epic"
ONBOARD = "/jidoka:onboard"


class EpicReadError(Exception):
    """A reason an epic cannot be read from bd, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Rerun:
    """How a script that makes the held-epic checks words its advice to run it again on the epic that holds a
    task."""
    on_the_holding_epic: str


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    status: str
    description: str


@dataclass(frozen=True)
class Epic:
    """The epic as the scripts read it: the bead itself, every bead it holds, and its tasks among them."""
    shown: dict
    children: tuple[dict, ...]
    tasks: tuple[Task, ...]

    @property
    def id(self) -> str:
        return str(self.shown["id"])

    @property
    def branch(self) -> str:
        return recorded_branch(self.shown)

    @property
    def task_beads(self) -> list[dict]:
        """Every bead the epic holds that is not an epic, closed or open, as bd shows it."""
        return [child for child in self.children if child.get("issue_type") != EPIC_TYPE]

    @property
    def open_task_beads(self) -> list[dict]:
        """The beads of the epic's open tasks, as bd shows them."""
        open_ids = {task.id for task in self.tasks}
        return [child for child in self.children if str(child["id"]) in open_ids]

    @property
    def ready_task_beads(self) -> list[dict]:
        """The beads of the epic's open tasks that a lap could open for: no open lap, no assignee, no human label, an
        area, and no open bead they wait on."""
        return [task for task in self.open_task_beads if is_ready(task)]

    @property
    def labeled_task_ids(self) -> set[str]:
        """The ids of the epic's open tasks that carry the human label."""
        return {str(task["id"]) for task in self.open_task_beads if is_labeled_for_human(task)}


def waits_on_open_bead(task: dict) -> bool:
    return any(isinstance(link, dict) and link.get("dependency_type") == BLOCKING and link.get("status") != CLOSED
               for link in task.get("dependencies") or [])


def is_unclaimed(task: dict) -> bool:
    """A lap could open for the task but for its area and the beads it waits on: it has no open lap, no assignee and
    no human label."""
    return open_lap(task) is None and not task.get("assignee") and not is_labeled_for_human(task)


def is_ready(task: dict) -> bool:
    return is_unclaimed(task) and bool(area_of(metadata_of(task))) and not waits_on_open_bead(task)


def by_priority(task: dict) -> tuple[int, str]:
    """The order laps open in: bd priority, then id."""
    priority = task.get("priority")
    return (priority if isinstance(priority, int) else sys.maxsize, str(task["id"]))


def validated_head(metadata: dict) -> str:
    """The commit of the epic branch that validation checked, or an empty string when none is recorded."""
    return str(metadata.get(VALIDATED_HEAD_KEY) or "")


def shown_beads(ids: list[str], main_tree: Path) -> list[dict]:
    if not ids:
        return []
    output = run(["bd", "show", *ids, "--json"], main_tree, None)
    try:
        parsed = json.loads(output)
    except ValueError as error:
        raise EpicReadError(f"bd show did not print JSON: {output.strip()[:200]!r}") from error
    if not isinstance(parsed, list):
        raise EpicReadError("bd show printed JSON that is not a list")
    return [bead for bead in parsed if isinstance(bead, dict)]


def child_ids(epic: str, main_tree: Path) -> list[str]:
    return [str(item["id"]) for item in bd_list(["--parent", epic, "--all", "--limit", "0"], main_tree)
            if item.get("id")]


def read_epic(shown: dict, main_tree: Path) -> Epic:
    """The epic whose bead is already shown, with every bead it holds read once."""
    children = tuple(shown_beads(child_ids(str(shown["id"]), main_tree), main_tree))
    tasks = tuple(Task(str(child["id"]), str(child.get("title") or ""), str(child.get("status") or ""),
                       str(child.get("description") or ""))
                  for child in children
                  if child.get("status") != CLOSED and child.get("issue_type") != EPIC_TYPE)
    return Epic(shown, children, tasks)


class NotAnEpic(EpicReadError):
    """A bead that was read as an epic and is another kind of bead."""

    def __init__(self, bead: str, issue_type: str) -> None:
        super().__init__(f"{bead} is a {issue_type or 'bead'}, not an epic")


def shown_epic(bead: str, main_tree: Path) -> dict:
    """The epic as bd shows it; raises NotAnEpic for a bead of another kind."""
    shown = read_bead(bead, main_tree)
    if shown.get("issue_type") != EPIC_TYPE:
        raise NotAnEpic(bead, str(shown.get("issue_type") or ""))
    return shown


def epic_of(bead: str, main_tree: Path, rerun: Rerun) -> Epic:
    try:
        shown = shown_epic(bead, main_tree)
    except NotAnEpic as error:
        raise EpicReadError(f"{error}. {rerun.on_the_holding_epic}") from error
    return read_epic(shown, main_tree)


def recorded_branch(shown: dict) -> str:
    """The epic branch that the epic bead records, or an empty string when it records none."""
    return str(metadata_of(shown).get(BRANCH_KEY) or "")


def waiting_problems(epic: Epic) -> list[str]:
    """The blocking edges from the epic or one of its tasks to an open bead outside the epic."""
    inside = {epic.id, *(str(child["id"]) for child in epic.children)}
    task_ids = {task.id for task in epic.tasks}
    waiters = [epic.shown, *(child for child in epic.children if str(child["id"]) in task_ids)]
    problems = []
    for waiter in waiters:
        for link in waiter.get("dependencies") or []:
            if (isinstance(link, dict) and link.get("dependency_type") == BLOCKING
                    and str(link.get("id")) not in inside and link.get("status") != CLOSED):
                problems.append(f"{waiter['id']} waits on {link['id']} ({link.get('title') or 'no title'}), an "
                                f"open bead outside {epic.id}. Close {link['id']}, move it into the epic, or "
                                f"remove the dependency with bd dep remove {waiter['id']} {link['id']}")
    return problems


def nested_epic_problems(epic: Epic) -> list[str]:
    return [f"{epic.id} holds {child['id']}, which is an epic. An epic holds only tasks: move {child['id']} "
            "out of it, or make it a task" for child in epic.children if child.get("issue_type") == EPIC_TYPE]


def settings_problems(settings: settings_reader.Settings) -> list[str]:
    try:
        untested = settings.untested_apps()
    except settings_reader.SettingsError as error:
        return [str(error)]
    problems = [f"the app {app} has no test command, so the factory cannot test its work. Build a test project "
                f"for it at the bench, then run {ONBOARD} to record its command" for app in untested]
    try:
        settings.full_suite()
    except settings_reader.SettingsError as error:
        problems.append(str(error))
    return problems


def holdout_problems(epic: Epic, epic_holdouts: list[holdouts.Holdout]) -> list[str]:
    inside = {str(child["id"]) for child in epic.children}
    return [f"a holdout of the app {holdout.app} names {task}, which is not a task of {epic.id}. Move {task} "
            "into the epic, or take it out of the holdout"
            for holdout in epic_holdouts for task in holdout.tasks if task not in inside]


def way_in_problems(settings: settings_reader.Settings, epic_holdouts: list[holdouts.Holdout]) -> list[str]:
    apps = {app.name: app for app in settings.apps}
    held = list(dict.fromkeys(holdout.app for holdout in epic_holdouts))
    problems = [f"a holdout reaches the app {name}, which the repo settings do not list. Run {ONBOARD} to "
                "record it with its way in" for name in held if name not in apps]
    for name, app in apps.items():
        has = [kind for kind, present in (("holdouts", name in held), ("acceptance specs", app.acceptance))
               if present]
        if has and app.way_in is None:
            problems.append(f"the app {name} has {' and '.join(has)} but no way in, so no app check can reach "
                            f"it. Run {ONBOARD} to record how a person or a program reaches it")
    return problems


def problems_while_held(epic: Epic, settings: settings_reader.Settings) -> list[str]:
    """The checks that hold for as long as the factory holds the epic."""
    try:
        epic_holdouts = holdouts.of_epic(epic.shown)
        unreadable = []
    except holdouts.HoldoutsError as error:
        epic_holdouts, unreadable = [], [f"{error}. Write the epic's holdouts again"]
    return [*waiting_problems(epic), *nested_epic_problems(epic), *settings_problems(settings),
            *unreadable, *holdout_problems(epic, epic_holdouts), *way_in_problems(settings, epic_holdouts)]
