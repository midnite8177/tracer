"""Reads an epic and its tasks from bd, and holds the checks that stay true for as long as the factory holds the epic.

The handoff script and the scheduler both read an epic this way, and the scripts that watch epics read its children
through it. Each script that runs the held-epic checks passes its own `Rerun`, so a refusal names the script the reader
ran.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import holdouts
from commands import bd_show, run

BRANCH_KEY = "factory.branch"
BLOCKING = "blocks"
CLOSED = "closed"
EPIC_TYPE = "epic"
ONBOARD = "/jidoka:onboard"


class EpicReadError(Exception):
    """A reason an epic cannot be read from bd, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Rerun:
    """How a script that makes the held-epic checks words its advice to run it again: on the epic that holds a
    task, and after onboarding."""
    on_the_holding_epic: str
    after_onboarding: str


@dataclass(frozen=True)
class Task:
    """One of the epic's tasks, with its description."""
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
    def task_beads(self) -> list[dict]:
        """Every bead the epic holds that is not an epic, closed or open, as bd shows it."""
        return [child for child in self.children if child.get("issue_type") != EPIC_TYPE]

    @property
    def open_task_beads(self) -> list[dict]:
        """The beads of the epic's open tasks, as bd shows them."""
        open_ids = {task.id for task in self.tasks}
        return [child for child in self.children if str(child["id"]) in open_ids]


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
    output = run(["bd", "list", "--parent", epic, "--all", "--limit", "0", "--json"], main_tree, None)
    try:
        parsed = json.loads(output)
    except ValueError as error:
        raise EpicReadError(f"bd list did not print JSON: {output.strip()[:200]!r}") from error
    if not isinstance(parsed, list):
        raise EpicReadError("bd list printed JSON that is not a list")
    return [str(item["id"]) for item in parsed if isinstance(item, dict) and item.get("id")]


def read_epic(shown: dict, main_tree: Path) -> Epic:
    """The epic whose bead is already shown, with every bead it holds read once."""
    children = tuple(shown_beads(child_ids(str(shown["id"]), main_tree), main_tree))
    tasks = tuple(Task(str(child["id"]), str(child.get("title") or ""), str(child.get("status") or ""),
                       str(child.get("description") or ""))
                  for child in children
                  if child.get("status") != CLOSED and child.get("issue_type") != EPIC_TYPE)
    return Epic(shown, children, tasks)


def epic_of(bead: str, main_tree: Path, rerun: Rerun) -> Epic:
    shown = bd_show(bead, main_tree)
    if shown is None:
        raise EpicReadError(f"bd show printed nothing usable for {bead}")
    if shown.get("issue_type") != EPIC_TYPE:
        raise EpicReadError(f"{bead} is a {shown.get('issue_type') or 'bead'}, not an epic. "
                            f"{rerun.on_the_holding_epic}")
    return read_epic(shown, main_tree)


def recorded_branch(epic: Epic) -> str:
    return str((epic.shown.get("metadata") or {}).get(BRANCH_KEY) or "")


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


def settings_problems(settings: dict, rerun: Rerun) -> list[str]:
    if not settings:
        return [f"the repo has no repo settings on this machine. Run {ONBOARD}, then {rerun.after_onboarding}"]
    untested, full_suite = settings.get("untested_apps"), settings.get("full_suite")
    if not (isinstance(untested, list) and isinstance(full_suite, list)):
        return [f"the repo settings lack untested_apps or full_suite. Run {ONBOARD} again to record them"]
    problems = [f"the app {app} has no test command, so the factory cannot test its work. Build a test project "
                f"for it at the bench, then run {ONBOARD} to record its command" for app in untested]
    if not full_suite:
        problems.append(f"the repo settings hold no full suite. Run {ONBOARD} to record a test command")
    return problems


def holdout_problems(epic: Epic, epic_holdouts: list[holdouts.Holdout]) -> list[str]:
    inside = {str(child["id"]) for child in epic.children}
    return [f"a holdout of the app {holdout.app} names {task}, which is not a task of {epic.id}. Move {task} "
            "into the epic, or take it out of the holdout"
            for holdout in epic_holdouts for task in holdout.tasks if task not in inside]


def way_in_problems(settings: dict, epic_holdouts: list[holdouts.Holdout]) -> list[str]:
    apps = {app.get("name"): app for app in settings.get("apps") or [] if isinstance(app, dict)}
    held = list(dict.fromkeys(holdout.app for holdout in epic_holdouts))
    problems = [f"a holdout reaches the app {name}, which the repo settings do not list. Run {ONBOARD} to "
                "record it with its way in" for name in held if name not in apps]
    for name, app in apps.items():
        has = [kind for kind, present in (("holdouts", name in held), ("acceptance specs", app.get("acceptance")))
               if present]
        if has and app.get("way_in") is None:
            problems.append(f"the app {name} has {' and '.join(has)} but no way in, so no app check can reach "
                            f"it. Run {ONBOARD} to record how a person or a program reaches it")
    return problems


def problems_while_held(epic: Epic, settings: dict, rerun: Rerun) -> list[str]:
    """The checks that hold for as long as the factory holds the epic."""
    try:
        epic_holdouts = holdouts.of_epic(epic.shown)
        unreadable = []
    except holdouts.HoldoutsError as error:
        epic_holdouts, unreadable = [], [f"{error}. Write the epic's holdouts again"]
    return [*waiting_problems(epic), *nested_epic_problems(epic), *settings_problems(settings, rerun),
            *unreadable, *holdout_problems(epic, epic_holdouts), *way_in_problems(settings, epic_holdouts)]
