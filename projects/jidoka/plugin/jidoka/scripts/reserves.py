"""The reserves: the share of each usage window of the account that the factory leaves unused.

The scheduler imports it; no command line runs it. The lap mod reads the account's usage windows when the manager
calls the scheduler and writes them to `<jidoka home>/usage/claude.json`, so the file holds the reading of the account
the host runs on at that call. jidoka never chooses the account; it reads the file afresh on every call and takes a
reading older than ten minutes for none. A reading holds `read_at` (a second since the epoch) and, for each window the
account has, `five_hour` and `seven_day` with `used_percent` and `resets_at` (a second since the epoch). An account on
an API key has no window, and a window that has reset holds nothing back.

The reserve of the account is a share, the epic's `reserves` rule for `claude`, else the machine settings' `reserves`
for `claude`, and it holds for both windows. An account with neither keeps 10% of the five-hour window free and 25% of
the seven-day window.

Past its reserve, the five-hour window pauses the epic on the cause `reserve` until the reset, as pause.py describes:
no stage starts and no lap opens. A reading that shows the window back under its reserve, or reset, clears the pause,
and a pause a worker's trouble began is left alone.

Past its reserve, the seven-day window starts no new stage, and once no stage runs the epic parks with a question that
gives the projection of the window at its pace so far and three choices. The question is asked once for
each window: the epic's `reserve.asked` metadata holds the reset second of the window it asked about, so taking the
human label off goes on into the reserve until that window resets.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import park
import pause
from commands import env_as_factory, metadata_of, run
from epics import state_of
import routes
from rules import is_map_of, is_number, is_share, is_whole, of_epic

RESERVES_KEY = "reserves"
USAGE_FOLDER = "usage"
ACCOUNT = "claude"
FRESH_SECONDS = 10 * 60
FIVE_HOUR_SECONDS = 5 * 60 * 60
SEVEN_DAY_SECONDS = 7 * 24 * 60 * 60
DEFAULT_FIVE_HOUR_RESERVE_PERCENT = 10
DEFAULT_SEVEN_DAY_RESERVE_PERCENT = 25
MINIMUM_ELAPSED_SECONDS = 60
ASKED_KEY = "reserve.asked"
RESUMES_WHEN = "the human label comes off"
WAIT = "Wait for the reset"
GO_ON = "Go on into the reserve"
LAND = "Land what the epic holds"


@dataclass(frozen=True)
class Window:
    """One usage window of the account: how much of it is used, when it resets, how long it is, and the share of it
    that the factory leaves unused."""
    name: str
    used_percent: float
    resets_at: int
    length_seconds: int
    reserve_percent: float

    def is_past_reserve(self, now: int) -> bool:
        return self.resets_at > now and self.used_percent > 100 - self.reserve_percent

    @property
    def reason(self) -> str:
        """What the epic did, in words that follow its id."""
        return f"passed the reserve of its {self.name} usage window, {self.used_percent:g}% used"

    def projected_percent(self, now: int) -> float:
        """The share of the window used at its reset, were the rest of the window used at the pace so far."""
        elapsed = max(self.length_seconds - (self.resets_at - now), MINIMUM_ELAPSED_SECONDS)
        return self.used_percent * self.length_seconds / elapsed


@dataclass(frozen=True)
class Reading:
    """The windows the account had at the last call; None for a window it does not have."""
    five_hour: Window | None
    seven_day: Window | None


def window_in(raw: object, name: str, length_seconds: int, reserve_percent: float) -> Window | None:
    if not isinstance(raw, dict):
        return None
    used, resets_at = raw.get("used_percent"), raw.get("resets_at")
    if not is_number(used) or not is_whole(resets_at):
        return None
    return Window(name, float(used), int(resets_at), length_seconds, reserve_percent)


def share_in(value: object) -> float | None:
    """The share a map of account names to shares holds for the account, or None when the map holds none for it or is
    not a map of shares."""
    return float(value[ACCOUNT]) if is_map_of(value, is_share) and ACCOUNT in value else None


def machine_share(home: Path) -> float | None:
    """The default reserve of the account in the machine settings; settings that cannot be read give none, and a line
    on stderr."""
    return routes.machine_default(home, RESERVES_KEY, "reserves", share_in)


def reserve_percents(shown: dict, home: Path) -> tuple[float, float]:
    """The share of the five-hour and of the seven-day window left unused, in percent. The account's reserve is the
    epic's own rule, else the machine's default, and one share holds for both windows. An account with neither keeps
    10% of the five-hour window and 25% of the seven-day window."""
    own = share_in(of_epic(shown).settings.get(RESERVES_KEY))
    share = own if own is not None else machine_share(home)
    if share is None:
        return DEFAULT_FIVE_HOUR_RESERVE_PERCENT, DEFAULT_SEVEN_DAY_RESERVE_PERCENT
    percent = round(share * 100, 6)
    return percent, percent


def read(home: Path, now: int, shown: dict) -> Reading | None:
    """The account's windows as the lap mod last wrote them, with the reserve of the epic as reserve_percents gives
    it, or None. A file that cannot be read or parsed gives a line on stderr; a missing file, a stale reading and a
    reading of the wrong shape give none."""
    path = home / USAGE_FOLDER / f"{ACCOUNT}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        print(f"scheduler: the account's usage reading was not read: {error}", file=sys.stderr)
        return None
    if not isinstance(raw, dict) or not is_whole(raw.get("read_at")) or now - raw["read_at"] > FRESH_SECONDS:
        return None
    five_hour_percent, seven_day_percent = reserve_percents(shown, home)
    return Reading(window_in(raw.get("five_hour"), "five-hour", FIVE_HOUR_SECONDS, five_hour_percent),
                   window_in(raw.get("seven_day"), "seven-day", SEVEN_DAY_SECONDS, seven_day_percent))


def sync_pause(epic: str, shown: dict, reading: Reading | None, now: int, main_tree: Path) -> bool:
    """Brings the epic's pause on the five-hour reserve in line with the reading, and says whether it wrote.

    A window past its reserve pauses the epic until the window resets, unless a pause that waits covers it already
    until then or is another trouble's. A reading under the reserve, or a window that has reset, clears a pause on the
    reserve whether it still waits or not. No reading changes nothing.
    """
    if reading is None:
        return False
    held = pause.held_by(shown)
    waiting = pause.waiting_at(shown, now)
    window = reading.five_hour
    if window is not None and window.is_past_reserve(now):
        if waiting is not None and (waiting.cause != pause.RESERVE or waiting.until == window.resets_at):
            return False
        since = waiting.since if waiting is not None else now
        pause.write(epic, pause.Pause(pause.RESERVE, since, window.resets_at, 0), main_tree)
        if waiting is None:
            run(["bd", "comment", epic, f"Paused: the account's five-hour window is {window.used_percent:g}% used, "
                                        f"past its reserve of {window.reserve_percent:g}%. Nothing new starts until "
                                        f"it resets in {left(window.resets_at - now)}."],
                main_tree, env_as_factory())
        return True
    if held is not None and held.cause == pause.RESERVE:
        pause.clear(epic, main_tree)
        return True
    return False


def seven_day_past_reserve(shown: dict, reading: Reading | None, now: int) -> Window | None:
    """The seven-day window that is past its reserve for an epic that runs and has not asked about this window, or
    None. An epic that waits on the human or the acceptance gate already is left as it is."""
    window = reading.seven_day if reading is not None else None
    state = state_of(shown)
    if window is None or state.labeled_for_human or state.at_the_gate or not window.is_past_reserve(now):
        return None
    return None if str(metadata_of(shown).get(ASKED_KEY)) == str(window.resets_at) else window


def left(seconds: int) -> str:
    """The time left, to the nearest hour, as days and hours."""
    days, hours = divmod(max(1, round(seconds / 3600)), 24)
    return " ".join(part for part in (f"{days}d" if days else "", f"{hours}h" if hours else "") if part)


def question_of(epic: str, window: Window, now: int) -> park.Question:
    """The question the seven-day reserve asks: one sentence, what the window shows, and an option for each way on,
    each with its next step."""
    found = (f"The account's {window.name} usage window is {window.used_percent:g}% used, and the reserve keeps "
             f"{window.reserve_percent:g}% of it free, so the factory started no new stage and parked {epic}. "
             f"Projection: at this pace the window reaches {window.projected_percent(now):.0f}% when it resets in "
             f"{left(window.resets_at - now)}.")
    options = (park.Option(WAIT, 50, "Take the human label off the epic once the window has reset to go on with a "
                                     "fresh window."),
               park.Option(GO_ON, 30, "Take the human label off the epic now to go on into the reserve. The factory "
                                      "asks no more until this window resets."),
               park.Option(LAND, 20, f"Run /jidoka:accept {epic} to land what the epic holds, which moves its open "
                                     "tasks to a new epic."))
    return park.plain_question(f"Should {epic} wait for the {window.name} usage window to reset before it goes on?",
                               found, options, WAIT)


def park_epic_at(epic: str, window: Window, now: int, home: Path, main_tree: Path) -> None:
    """Parks the epic with the question, and records the window it asked about."""
    park.park_epic_on_question(epic, question_of(epic, window, now), {ASKED_KEY: str(window.resets_at)}, home,
                               main_tree)
