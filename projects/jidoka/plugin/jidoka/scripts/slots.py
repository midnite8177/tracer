"""The machine's one record of which open lap holds which slot, shared by every running epic under a lock.

The record is <jidoka-home>/slots.json, a JSON object with `slots`, a list of holds of two kinds. A lap's is
`{"kind": "lap", "epic", "task", "slot", "repo", "area"}`, one for each open lap that a scheduler call recorded, with
the repo's main checkout and the lap's area; an entry with no kind is a lap's. A validation's is `{"kind":
"validation", "epic", "slot"}`: it names no task, repo or area, and it takes no part in the area rule. The lock is
<jidoka-home>/slots.lock. Slot numbers are unique on the machine, so two repos whose slot use picks overlapping ports
never clash. Areas are not shared that far: two laps in one area never run together across the running epics of one
repo, and epics of two repos never share an area.

A scheduler call takes its epic's slots through `share`. Under the lock the call drops each entry whose epic's
heartbeat is no longer fresh, because a handed-off epic with no manager holds no slot, replaces its own epic's
entries with the laps the epic holds now, which frees the slot and the area of a lap that ended, places the epic's
candidate laps beside what the other running epics hold, and records them. The record is written before the lap is
opened, so a second epic's call that follows sees the slot taken.

Every running epic, one whose heartbeat is fresh, keeps at least one slot: an epic with no lap may open one while the
machine is under its limit, and an epic with a lap opens another only while a slot stays free for each other running
epic that holds none. The rest go first come. `Machine.place` holds those rules, the lowest free slot and the area
rule, so the scheduler, which sorts the candidates, and the watcher, which asks whether any would open, ask the same
question.

An epic in validation holds no lap, so it takes slots through `hold_free`, runs one acceptance spec on each, and gives
them back through `release`. `Machine.free_for_validation` holds the rule for how many: the slots no other running
epic holds, less one kept free for each other running epic that holds none, and at least one for the validating epic.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

import file_lock
import heartbeat
import routes
from lap_record import Lap

SLOTS_FILE = "slots.json"
SLOTS_LOCK = "slots.lock"
FIRST_SLOT = 1
LAP_KIND = "lap"
VALIDATION_KIND = "validation"


def repo_key(main_tree: Path) -> str:
    """How the record names a repo: its main checkout."""
    return str(main_tree)


@dataclass(frozen=True)
class Claim:
    """One open lap's hold on a slot of the machine."""
    epic: str
    task: str
    slot: int
    repo: str
    area: str

    def is_in(self, main_tree: Path) -> bool:
        """True when the lap belongs to the repo whose main checkout this is."""
        return self.repo == repo_key(main_tree)


@dataclass(frozen=True)
class Hold:
    """An epic in validation's hold on a slot, where it runs one acceptance spec. It holds no lap, so it names no task,
    repo or area, and the area rule leaves it out."""
    epic: str
    slot: int

    @property
    def task(self) -> str:
        """No task: a reader that prints the epic and task of every held slot prints none for a validation's."""
        return ""


@dataclass(frozen=True)
class Standing:
    """Where one epic stands on the machine at one second: the jidoka home that holds the record, the epic, the main
    checkout of its repo, the machine's lap limit and the second. They travel together through every read of the
    record beside the epic."""
    home: Path
    epic: str
    main_tree: Path
    limit: int
    now: int


@dataclass(frozen=True)
class Candidate:
    """A ready task that a lap may open for, with its area."""
    task: str
    area: str


@dataclass(frozen=True)
class Placement:
    """A candidate that fits, with the slot its lap takes."""
    task: str
    area: str
    slot: int


@dataclass(frozen=True)
class Machine:
    """What the machine holds beside one epic: the machine's lap limit, the slots the other running epics hold, the
    areas that the other running epics of the same repo hold, and how many running epics hold no slot and so keep
    one free."""
    limit: int
    taken: frozenset[int]
    areas: frozenset[str]
    running_without_a_slot: int

    def has_room(self, own: int) -> bool:
        """True when an epic that holds `own` laps may open one more: the first lap needs only a free slot, a later
        one leaves a slot free for each running epic that holds none."""
        reserved = 0 if own == 0 else self.running_without_a_slot
        return len(self.taken) + own + reserved < self.limit

    def place(self, held: list[Lap], candidates: list[Candidate], epic_limit: int) -> list[Placement]:
        """The candidates that fit beside the epic's open laps and the machine, in the order given: within the
        epic's limit and the machine's, one per area across the repo's running epics, each on the lowest slot that
        no open lap on the machine holds. Placing stops at the first candidate that finds no room."""
        areas = {lap.area for lap in held} | self.areas
        taken = {lap.slot for lap in held} | self.taken
        placed: list[Placement] = []
        for candidate in candidates:
            own = len(held) + len(placed)
            if own >= epic_limit or not self.has_room(own):
                break
            if candidate.area in areas:
                continue
            slot = next(number for number in itertools.count(FIRST_SLOT) if number not in taken)
            placed.append(Placement(candidate.task, candidate.area, slot))
            areas.add(candidate.area)
            taken.add(slot)
        return placed

    def free_for_validation(self) -> list[int]:
        """The slots an epic in validation takes, lowest first: the ones no other running epic holds, less one kept free
        for each other running epic that holds none, though always at least one, because the validating epic holds no
        lap and so is owed a slot even when the machine is full."""
        count = max(1, self.limit - len(self.taken) - self.running_without_a_slot)
        return list(itertools.islice((number for number in itertools.count(FIRST_SLOT) if number not in self.taken),
                                     count))


def record_path(home: Path) -> Path:
    return home / SLOTS_FILE


def holder_of(entry: dict) -> Claim | Hold:
    if entry.get("kind") == VALIDATION_KIND:
        return Hold(str(entry["epic"]), int(entry["slot"]))
    return Claim(str(entry["epic"]), str(entry["task"]), int(entry["slot"]), str(entry["repo"]), str(entry["area"]))


def entry_of(holder: Claim | Hold) -> dict:
    if isinstance(holder, Hold):
        return {"kind": VALIDATION_KIND, "epic": holder.epic, "slot": holder.slot}
    return {"kind": LAP_KIND, "epic": holder.epic, "task": holder.task, "slot": holder.slot, "repo": holder.repo,
            "area": holder.area}


def read(home: Path) -> list[Claim | Hold]:
    """The holds on record; a record that is missing or cannot be read holds none."""
    try:
        return [holder_of(each) for each in json.loads(record_path(home).read_text(encoding="utf-8"))["slots"]]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []


def write(home: Path, holders: list[Claim | Hold]) -> None:
    routes.write_in_home(home, SLOTS_FILE, json.dumps({"slots": [entry_of(each) for each in holders]}))


def live(home: Path, now: int) -> list[Claim | Hold]:
    """The holds of the epics whose heartbeat is fresh, by slot."""
    return sorted((each for each in read(home) if heartbeat.is_fresh(home, each.epic, now)),
                  key=lambda each: (each.slot, each.epic))


def machine_beside(standing: Standing) -> tuple[Machine, list[Claim | Hold]]:
    """The machine as the epic sees it, and the live holds of the other running epics, by slot."""
    beside = [each for each in live(standing.home, standing.now) if each.epic != standing.epic]
    holders = {each.epic for each in beside}
    running = [each for each in heartbeat.fresh_epics(standing.home, standing.now) if each != standing.epic]
    without_a_slot = len([each for each in running if each not in holders])
    areas = frozenset(each.area for each in beside if isinstance(each, Claim) and each.is_in(standing.main_tree))
    return Machine(standing.limit, frozenset(each.slot for each in beside), areas, without_a_slot), beside


def hold_free(standing: Standing) -> list[int]:
    """Records, under the lock, a hold on each slot `Machine.free_for_validation` gives the epic, and returns their
    numbers, lowest first. The holds stop the other epics from opening a lap over the specs, and `release` takes them
    off."""
    with file_lock.exclusive(standing.home / SLOTS_LOCK):
        machine, beside = machine_beside(standing)
        numbers = machine.free_for_validation()
        write(standing.home, beside + [Hold(standing.epic, number) for number in numbers])
    return numbers


def release(home: Path, epic: str) -> None:
    """Takes off the holds `hold_free` recorded for the epic."""
    with file_lock.exclusive(home / SLOTS_LOCK):
        write(home, [each for each in read(home) if not (isinstance(each, Hold) and each.epic == epic)])


def share(standing: Standing, held: list[Lap], candidates: list[Candidate], epic_limit: int) -> list[Placement]:
    """Places the epic's candidate laps beside the machine's, under the lock, and records them with the laps it holds.

    `held` are the epic's open laps, which replace its entries on record. `candidates` come in the order the epic
    prefers, and `epic_limit` is the most laps the epic runs at once.
    """
    with file_lock.exclusive(standing.home / SLOTS_LOCK):
        machine, beside = machine_beside(standing)
        placed = machine.place(held, candidates, epic_limit)
        repo = repo_key(standing.main_tree)
        write(standing.home, beside + [Claim(standing.epic, lap.task, lap.slot, repo, lap.area) for lap in held]
              + [Claim(standing.epic, each.task, each.slot, repo, each.area) for each in placed])
    return placed
