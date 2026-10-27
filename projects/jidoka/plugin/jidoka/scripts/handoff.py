#!/usr/bin/env python3
"""Hands an epic to the factory, once the epic passes the checks of its form.

Run it from inside any checkout of the repo. The epic's tasks are its
children that are neither closed nor epics.

`check <epic>` makes the checks and writes nothing. It prints the epic, the
name of its epic branch and its tasks as one JSON object, each task with
its title, status, the text of its Seams section and of its Demo section,
`missing`, the sections among "demo" and "seams" that its description lacks,
the track the rule below proposes, `why`, the reasons for that track, and
`holdouts`, how many holdouts name it. The human and the skill agree an area
for each task from its Seams, and propose a Demo and a Seams section for each
task that lacks one. It also prints `presets`, the factory rules of the
bug-epic and improvement-epic presets, for the human to choose from.

The track rule: a task is proposed on the simple track when no holdout names
it, its Seams section holds one line or one bullet, and the rest of its
description names no public API or type. Any other task is proposed on the
full track, with every reason that applies. A holdout that names a task
stands for the behavior a holdout or user would see.

`take <epic> --area <task>=<area> ... [--track <task>=<track> ...] [--preset
<preset>]` makes the same checks, and also refuses a task with no area, an
--area or --track that names a bead that is not one of the epic's tasks, and
a track that is neither simple nor full. Each --track flips the proposed
track of one task. Then it writes, with BEADS_ACTOR set to the repo's git
user.name: `lap.track` and `lap.area=<area>` in each task's metadata,
the epic branch's name as the epic's `factory.branch` metadata, the epic
branch itself, cut from main's head, one comment on the epic that holds the
task table, and last the factory label. An epic without the label has not
been handed off, and a rerun of `take` finishes the job: it reuses the
branch the epic records and posts no second table. With --preset, rules.py's
write sets the preset's factory rules just before the label, one comment for
each setting that changes. It prints the epic, the
branch, the commit the branch is at and the tasks as one JSON object. It
starts nothing.

The checks, each refusal saying what to do, all reported at once:
  the epic or one of its tasks waits on an open bead outside the epic;
  the epic holds an epic;
  the epic has no tasks;
  the repo has no repo settings on this machine;
  an app has no test command, or the repo has no full suite;
  a holdout names a task outside the epic;
  the epic already carries the factory label;
  an app that has holdouts or acceptance specs has no way in;
  the epic's spec has no Out of Scope section, or an empty one.
It also refuses a title with no letters or digits to name the epic branch
from, an epic branch that exists and that the epic does not record, and a
repo with no main branch.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  success.
  1  it refused, or a git or bd command failed, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import holdouts
import repo_settings
import rules
from bench import FACTORY_LABEL, MAIN_REF, slug
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, bd_show, env_as_git_user, head_of, run

BRANCH_PREFIX = "epic/"
BRANCH_KEY = "factory.branch"
TRACK = "simple"
FULL_TRACK = "full"
TRACKS = (TRACK, FULL_TRACK)
TABLE_HEADING = "Handoff:"
BLOCKING = "blocks"
CLOSED = "closed"
EPIC_TYPE = "epic"
ONBOARD = "/jidoka:onboard"
OUT_OF_SCOPE_SECTION = re.compile(r"^#{1,6}[ \t]*Out[ \t]+of[ \t]+Scope[ \t]*:?[ \t]*(?:\n|\Z)(.*?)(?=^#{1,2}[ \t]|\Z)",
                                  re.MULTILINE | re.DOTALL | re.IGNORECASE)
OUT_OF_SCOPE_LINE = re.compile(r"\bOut[ \t]+of[ \t]+scope(?:\*\*)?[ \t]*:(?:\*\*)?[ \t]*\S", re.IGNORECASE)
SEAM_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
PUBLIC_API = re.compile(r"\bpublic[ \t]+(?:APIs?|types?|interfaces?|members?|class(?:es)?|methods?)\b",
                        re.IGNORECASE)


class HandoffError(Exception):
    """A reason the script writes nothing more, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Rerun:
    """How a script that makes the shared checks words its advice to run it again: on the epic that holds a
    task, and after onboarding. Each script passes its own, so a refusal names the script the reader ran."""
    on_the_holding_epic: str
    after_onboarding: str


RERUN = Rerun(on_the_holding_epic="Hand off the epic that holds it", after_onboarding="hand the epic off")


def section_of(description: str, name: str) -> str:
    """The text of the description's `## <name>` section, or an empty string when it has none."""
    found = re.search(rf"^##[ \t]*{re.escape(name)}[ \t]*\n(.*?)(?=^##[ \t]|\Z)", description,
                      re.MULTILINE | re.DOTALL)
    return found.group(1).strip() if found else ""


@dataclass(frozen=True)
class Task:
    """One of the epic's tasks, with its description."""
    id: str
    title: str
    status: str
    description: str

    @property
    def seams(self) -> str:
        return section_of(self.description, "Seams")

    @property
    def demo(self) -> str:
        return section_of(self.description, "Demo")

    @property
    def missing(self) -> list[str]:
        return [name for name, text in (("demo", self.demo), ("seams", self.seams)) if not text]


@dataclass(frozen=True)
class Proposal:
    """The track the rule gives a task, with every reason it gives it."""
    track: str
    why: str


@dataclass(frozen=True)
class Epic:
    """The epic as handoff reads it: the bead itself, every bead it holds, and its tasks among them."""
    shown: dict
    children: tuple[dict, ...]
    tasks: tuple[Task, ...]

    @property
    def id(self) -> str:
        return str(self.shown["id"])


def shown_beads(ids: list[str], main_tree: Path) -> list[dict]:
    if not ids:
        return []
    output = run(["bd", "show", *ids, "--json"], main_tree, None)
    try:
        parsed = json.loads(output)
    except ValueError as error:
        raise HandoffError(f"bd show did not print JSON: {output.strip()[:200]!r}") from error
    if not isinstance(parsed, list):
        raise HandoffError("bd show printed JSON that is not a list")
    return [bead for bead in parsed if isinstance(bead, dict)]


def child_ids(epic: str, main_tree: Path) -> list[str]:
    output = run(["bd", "list", "--parent", epic, "--all", "--limit", "0", "--json"], main_tree, None)
    try:
        parsed = json.loads(output)
    except ValueError as error:
        raise HandoffError(f"bd list did not print JSON: {output.strip()[:200]!r}") from error
    if not isinstance(parsed, list):
        raise HandoffError("bd list printed JSON that is not a list")
    return [str(item["id"]) for item in parsed if isinstance(item, dict) and item.get("id")]


def epic_of(bead: str, main_tree: Path, rerun: Rerun) -> Epic:
    shown = bd_show(bead, main_tree)
    if shown is None:
        raise HandoffError(f"bd show printed nothing usable for {bead}")
    if shown.get("issue_type") != EPIC_TYPE:
        raise HandoffError(f"{bead} is a {shown.get('issue_type') or 'bead'}, not an epic. "
                           f"{rerun.on_the_holding_epic}")
    children = tuple(shown_beads(child_ids(bead, main_tree), main_tree))
    tasks = tuple(Task(str(child["id"]), str(child.get("title") or ""), str(child.get("status") or ""),
                       str(child.get("description") or ""))
                  for child in children
                  if child.get("status") != CLOSED and child.get("issue_type") != EPIC_TYPE)
    return Epic(shown, children, tasks)


def recorded_branch(epic: Epic) -> str:
    return str((epic.shown.get("metadata") or {}).get(BRANCH_KEY) or "")


def planned_branch(epic: Epic, main_tree: Path) -> tuple[str, list[str]]:
    """The epic branch's name, and the reasons it cannot be cut."""
    recorded = recorded_branch(epic)
    if recorded:
        return recorded, []
    name = slug(str(epic.shown.get("title") or ""))
    if not name:
        return "", [f"the title of {epic.id} has no letters or digits to name its epic branch from. "
                    "Retitle the epic"]
    branch = f"{BRANCH_PREFIX}{name}"
    if head_of(f"refs/heads/{branch}", main_tree) is not None:
        return branch, [f"the branch {branch} already exists and {epic.id} does not record it. "
                        "Retitle the epic or delete the branch"]
    return branch, []


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


def no_task_problems(epic: Epic) -> list[str]:
    if epic.tasks:
        return []
    return [f"{epic.id} holds no open tasks. Add its tasks with bd create --parent {epic.id}, then hand it off"]


def out_of_scope_problems(epic: Epic) -> list[str]:
    """The spec is the epic's description, and it must say what the epic leaves out."""
    spec = str(epic.shown.get("description") or "")
    heading = OUT_OF_SCOPE_SECTION.search(spec)
    if OUT_OF_SCOPE_LINE.search(spec) is not None:
        return []
    if heading is None:
        return [f"the spec of {epic.id} has no Out of Scope section. Add one that says what the epic leaves "
                f"out, with bd update {epic.id} --description"]
    if not heading.group(1).strip():
        return [f"the Out of Scope section of the spec of {epic.id} is empty. Say what the epic leaves out, "
                f"with bd update {epic.id} --description"]
    return []


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


def problems_of(epic: Epic, branch_problems: list[str], home: Path, main_tree: Path) -> list[str]:
    """Every reason the epic cannot go to the factory, in the order of the checks."""
    settings = repo_settings.load(repo_settings.settings_path(home, main_tree))
    problems = [*problems_while_held(epic, settings, RERUN), *no_task_problems(epic),
                *out_of_scope_problems(epic)]
    if FACTORY_LABEL in (epic.shown.get("labels") or []):
        problems.append(f"{epic.id} already carries the {FACTORY_LABEL} label, so the factory holds it. Start "
                        f"it with /jidoka:factory {epic.id}")
    if head_of(MAIN_REF, main_tree) is None:
        problems.append("the repo has no main branch to cut the epic branch from")
    return problems + branch_problems


def refuse(epic: Epic, problems: list[str]) -> None:
    if problems:
        raise HandoffError(f"{epic.id} cannot go to the factory, and nothing was written:\n"
                           + "\n".join(f"  {problem}" for problem in problems))


def areas_of(given: list[str], epic: Epic) -> tuple[dict[str, str], list[str]]:
    """The area of each task from the --area arguments, and the problems with them."""
    task_ids = [task.id for task in epic.tasks]
    areas: dict[str, str] = {}
    problems = []
    for argument in given:
        bead, _, area = argument.partition("=")
        bead, area = bead.strip(), area.strip()
        if bead not in task_ids:
            problems.append(f"--area {argument} names {bead or 'no bead'}, which is not a task of {epic.id}. "
                            "Give areas only to the epic's tasks")
        elif area:
            areas[bead] = area
    problems += [f"{task} has no area. Pass --area {task}=<area>" for task in task_ids if task not in areas]
    return areas, problems


def holdout_counts(epic: Epic) -> dict[str, int]:
    """How many of the epic's holdouts name each task. Holdouts that cannot be read count as none, and
    problems_while_held already reports them."""
    try:
        named = [task for holdout in holdouts.of_epic(epic.shown) for task in holdout.tasks]
    except holdouts.HoldoutsError:
        return {}
    return {task: named.count(task) for task in set(named)}


def seam_count(seams: str) -> int:
    """A seam is one line or one bullet of a Seams section."""
    return sum(1 for line in seams.splitlines() if SEAM_BULLET.sub("", line).strip())


def propose(task: Task, held: int) -> Proposal:
    """The track the rule gives a task. The rule is the same for every task, so that a script can check it."""
    reasons = []
    if held:
        reasons.append(f"named by {held} holdout{'' if held == 1 else 's'}")
    if PUBLIC_API.search(task.description.replace(task.seams, "")):
        reasons.append("its text names a public API or type")
    seams = seam_count(task.seams)
    if seams == 0:
        reasons.append("no Seams line")
    elif seams > 1:
        reasons.append(f"its Seams line names {seams} seams")
    if reasons:
        return Proposal(FULL_TRACK, "; ".join(reasons))
    return Proposal(TRACK, "no holdouts, one seam, no public API or type")


def proposals_of(epic: Epic) -> dict[str, Proposal]:
    held = holdout_counts(epic)
    return {task.id: propose(task, held.get(task.id, 0)) for task in epic.tasks}


def tracks_of(given: list[str], epic: Epic, proposed: dict[str, Proposal]) -> tuple[dict[str, Proposal], list[str]]:
    """Each task's track after the human's --track flips, and the problems with the flips."""
    tracks = dict(proposed)
    problems = []
    for argument in given:
        bead, _, track = argument.partition("=")
        bead, track = bead.strip(), track.strip()
        if bead not in proposed:
            problems.append(f"--track {argument} names {bead or 'no bead'}, which is not a task of {epic.id}. "
                            "Flip the tracks of the epic's tasks only")
        elif track not in TRACKS:
            problems.append(f"--track {argument} gives the track {track or 'nothing'}. Use {TRACK} or {FULL_TRACK}")
        elif track != proposed[bead].track:
            tracks[bead] = Proposal(track, f"flipped by the human from {proposed[bead].track}: "
                                           f"{proposed[bead].why}")
    return tracks, problems


def cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def table(epic: Epic, branch: str, areas: dict[str, str], tracks: dict[str, Proposal],
          held: dict[str, int]) -> str:
    rows = [f"| {cell(f'{task.id} {task.title}')} | {tracks[task.id].track} | {cell(tracks[task.id].why)} | "
            f"{cell(areas[task.id])} | {held.get(task.id, 0)} | {task.status} |" for task in epic.tasks]
    return "\n".join([f"{TABLE_HEADING} the factory takes {epic.id} on the epic branch {branch}.", "",
                      "| Task | Track | Why | Area | Holdouts | State |", "|---|---|---|---|---|---|", *rows])


def has_table(epic: Epic, main_tree: Path) -> bool:
    output = run(["bd", "comments", epic.id, "--json"], main_tree, None)
    try:
        comments = json.loads(output or "[]") or []
    except ValueError as error:
        raise HandoffError(f"bd comments did not print JSON: {output.strip()[:200]!r}") from error
    return any(isinstance(comment, dict) and str(comment.get("text") or "").startswith(TABLE_HEADING)
               for comment in comments)


def check(bead: str, home: Path, main_tree: Path) -> dict:
    epic = epic_of(bead, main_tree, RERUN)
    branch, branch_problems = planned_branch(epic, main_tree)
    refuse(epic, problems_of(epic, branch_problems, home, main_tree))
    proposed, held = proposals_of(epic), holdout_counts(epic)
    return {"epic": epic.id, "title": str(epic.shown.get("title") or ""), "branch": branch,
            "tasks": [{"id": task.id, "title": task.title, "status": task.status, "seams": task.seams,
                       "demo": task.demo, "missing": task.missing, "track": proposed[task.id].track,
                       "why": proposed[task.id].why, "holdouts": held.get(task.id, 0)}
                      for task in epic.tasks],
            "presets": rules.PRESETS}


def take(bead: str, given_areas: list[str], given_tracks: list[str], preset: str | None, home: Path,
         main_tree: Path) -> dict:
    epic = epic_of(bead, main_tree, RERUN)
    branch, branch_problems = planned_branch(epic, main_tree)
    areas, area_problems = areas_of(given_areas, epic)
    tracks, track_problems = tracks_of(given_tracks, epic, proposals_of(epic))
    refuse(epic, problems_of(epic, branch_problems, home, main_tree) + area_problems + track_problems)
    env = env_as_git_user(main_tree)
    for task in epic.tasks:
        run(["bd", "update", task.id, "--set-metadata", f"lap.track={tracks[task.id].track}",
             "--set-metadata", f"lap.area={areas[task.id]}"], main_tree, env)
    run(["bd", "update", epic.id, "--set-metadata", f"{BRANCH_KEY}={branch}"], main_tree, env)
    if head_of(f"refs/heads/{branch}", main_tree) is None:
        run(["git", "branch", branch, MAIN_REF], main_tree, None)
    held = holdout_counts(epic)
    if not has_table(epic, main_tree):
        run(["bd", "comment", epic.id, table(epic, branch, areas, tracks, held)], main_tree, env)
    if preset is not None:
        repo_limit = rules.repo_lap_limit(repo_settings.load(repo_settings.settings_path(home, main_tree)))
        rules.write_settings(epic.id, rules.PRESETS[preset], repo_limit, main_tree)
    run(["bd", "label", "add", epic.id, FACTORY_LABEL], main_tree, env)
    return {"epic": epic.id, "branch": branch, "start": head_of(f"refs/heads/{branch}", main_tree),
            "tasks": [{"id": task.id, "title": task.title, "track": tracks[task.id].track,
                       "why": tracks[task.id].why, "area": areas[task.id], "holdouts": held.get(task.id, 0),
                       "status": task.status} for task in epic.tasks]}


def main(argv: list[str]) -> int:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("epic")
    shared.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    parser = argparse.ArgumentParser(prog="handoff.py", description="Check an epic's form, or hand it to the "
                                                                    "factory.")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("check", parents=[shared], help="make the checks and print the epic's tasks")
    taking = modes.add_parser("take", parents=[shared], help="make the checks and hand the epic to the factory")
    taking.add_argument("--area", action="append", default=[], metavar="TASK=AREA",
                        help="the area of one task; give one for every task")
    taking.add_argument("--track", action="append", default=[], metavar="TASK=TRACK",
                        help="flip the proposed track of one task to simple or full")
    taking.add_argument("--preset", choices=sorted(rules.PRESETS),
                        help="the factory rules to give the epic; leave it out to give none")
    args = parser.parse_args(argv)

    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = repo_settings.jidoka_home(args.jidoka_home)
        if args.mode == "check":
            printed = check(args.epic, home, main_tree)
        else:
            printed = take(args.epic, args.area, args.track, args.preset, home, main_tree)
    except (HandoffError, CommandError, repo_settings.SettingsError, holdouts.HoldoutsError, rules.RulesError,
            OSError) as error:
        print(f"handoff: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
