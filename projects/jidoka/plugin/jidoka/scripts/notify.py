#!/usr/bin/env python3
"""Tells the human that the factory waits on them, with one notification for one event on one bead.

`notify.py <event> <bead>` sends one notification, once. Run it from inside any checkout of the repo. The
events that name a bead are:
  task-parked        a task is parked; the bead is the task.
  epic-parked        an epic is parked, apart from the acceptance gate; the bead is the epic.
  only-parked-left   every open task of the epic is parked; the bead is the epic.
  acceptance-gate    the epic waits at the acceptance gate; the bead is the epic.
  factory-stopped    the epic has open tasks and no manager runs it; the bead is the epic. The caller knows
                     the factory stopped, and the script checks only that the epic has work left.
                     Its fingerprint holds each open task's lap number, so a stop after a resume is a new one.
  factory-paused     the epic's pause waits on the human: a billing error, an auth failure, or an outage
                     that has lasted an hour; the bead is the epic. A pause on a usage limit waits on the
                     reset, and sends nothing.

`notify.py permission-prompt --session <id>` is the one event about a session: the host asks the human for a
permission while an epic runs. It takes `--session <id>`, the id of the host session, and no bead, and names the
running epic (an open epic with the `factory` label that is neither parked nor at the gate) whose heartbeat
records that session. A session that manages no running epic sends nothing, even when another epic runs in the
repo. It records and delivers as the other events do.

The script checks that the bead is in the state the event names, so a caller that asks for an event that
does not hold sends nothing. A notification points at one bead: the task for task-parked, the first parked
task for only-parked-left, and the epic otherwise. Each one is delivered three ways. It prints one line,
which the host shows. It records itself in the epic's `notification` metadata, a JSON object from
`<event>:<bead>` to an object with the `fingerprint` of the state it announced and the `title` and `text` it
said, which jidoka-ui shows as they stand, and it sends nothing for an event whose fingerprint the object
already holds (an entry is an object with a `fingerprint` field, or the bare fingerprint string), so a park
is announced once and a later park of the same task is a new one. It also sends a Pushover message where this
machine has Pushover keys, with a link to the bead in jidoka-ui.

The Pushover keys live in <jidoka-home>/pushover.json, which install.py writes: `user_key` and `app_token`,
both required, `ui_url` (the address jidoka-ui answers at, http://localhost:5099 when left out) and `api_url`
(the Pushover endpoint, for tests and compatible services). A file that is missing, unreadable or short of a
key means no Pushover, and the notification goes only to the host and the epic's key. A Pushover failure is a
warning on stderr, and the notification still counts as sent. The link is <ui_url>/bead/<id>?project=<the
main worktree>, the address jidoka-ui gives a bead's page.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  the notification was sent, or nothing needed sending, with the reason on stderr.
  1  it refused, or a bd command failed, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import clock
import heartbeat
import lap_record
import park
import pause
import settings_reader
from commands import (COMMAND_TIMEOUT_SECONDS, CommandError, env_as_factory, is_labeled_for_human, metadata_of,
                      parent_of, read_bead, run)
from epic_reader import EpicReadError, NotAnEpic, read_epic, shown_epic, validated_head
from epics import PARKED, WAITING, EpicsError, at_the_gate, is_closed, state_of

TASK_PARKED = "task-parked"
EPIC_PARKED = "epic-parked"
ONLY_PARKED_LEFT = "only-parked-left"
ACCEPTANCE_GATE = "acceptance-gate"
FACTORY_STOPPED = "factory-stopped"
FACTORY_PAUSED = "factory-paused"
PERMISSION_PROMPT = "permission-prompt"
BEAD_EVENTS = [TASK_PARKED, EPIC_PARKED, ONLY_PARKED_LEFT, ACCEPTANCE_GATE, FACTORY_STOPPED, FACTORY_PAUSED]
PAUSE_HINTS = {pause.BILLING: "Fix the billing, and the factory carries on at its next retry.",
               pause.AUTH: "Sign in again, and the factory carries on at its next retry.",
               pause.OUTAGE: "The factory keeps retrying by itself, once an hour.",
               pause.USAGE_LIMIT: "The factory carries on when the limit resets."}
NOTIFICATION_KEY = "notification"
PUSHOVER_FILE = "pushover.json"
PUSHOVER_API = "https://api.pushover.net/1/messages.json"
UI_ADDRESS = "http://localhost:5099"
PUSHOVER_TIMEOUT_SECONDS = 15
TITLE_LIMIT = 250
MESSAGE_LIMIT = 1024
DETAIL_LIMIT = 300
FINGERPRINT_LENGTH = 12


class NotifyError(EpicsError):
    """A reason the script sends nothing, worded for the person who reads stderr."""


class NothingToSend(Exception):
    """The event does not hold on the bead, or was already announced; the reason goes to stderr."""


@dataclass(frozen=True)
class Notice:
    """One notification: the epic whose key records it, the bead it points at, and what it says."""
    event: str
    epic: str
    bead: str
    title: str
    text: str
    fingerprint: str


@dataclass(frozen=True)
class Pushover:
    """The keys of this machine's Pushover account and application, and where jidoka-ui answers."""
    user_key: str
    app_token: str
    ui_url: str
    api_url: str


def digest(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:FINGERPRINT_LENGTH]


def shortened(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def last_park(bead: str, main_tree: Path) -> tuple[str, str]:
    """The fingerprint and the first line of the factory's latest park comment on the bead.

    Both are empty when the factory never parked it, as when the human did.
    """
    latest = park.latest_park(bead, main_tree)
    if latest is None:
        return "", ""
    body = latest.body
    first_line = body.splitlines()[0] if body else ""
    return digest(latest.id, latest.created_at, latest.text), first_line


def parked_task(task: str, main_tree: Path) -> Notice:
    shown = read_bead(task, main_tree)
    if is_closed(shown) or not is_labeled_for_human(shown):
        raise NothingToSend(f"{task} is not parked")
    epic = parent_of(shown)
    if not epic:
        raise NotifyError(f"{task} is held by no epic, so there is no epic key to record the notification in")
    fingerprint, detail = last_park(task, main_tree)
    return Notice(TASK_PARKED, epic, task, f"Task parked: {shown.get('title') or task}",
                  detail or "The task waits on you.", fingerprint or "parked")


def epic_of(bead: str, main_tree: Path) -> dict:
    try:
        return shown_epic(bead, main_tree)
    except NotAnEpic as error:
        raise NotifyError(str(error)) from error


def parked_epic(epic: str, main_tree: Path) -> Notice:
    shown = epic_of(epic, main_tree)
    if is_closed(shown) or state_of(shown).name != PARKED:
        raise NothingToSend(f"{epic} is not parked")
    fingerprint, detail = last_park(epic, main_tree)
    return Notice(EPIC_PARKED, epic, epic, f"Epic parked: {shown.get('title') or epic}",
                  detail or "The epic waits on you.", fingerprint or "parked")


def open_tasks(shown: dict, main_tree: Path) -> list[dict]:
    """The tasks of the shown epic that are not closed, by id."""
    return sorted(read_epic(shown, main_tree).open_task_beads, key=lambda bead: str(bead["id"]))


def only_parked_tasks_left(epic: str, main_tree: Path) -> Notice:
    shown = epic_of(epic, main_tree)
    if is_closed(shown) or at_the_gate(shown):
        raise NothingToSend(f"{epic} is closed or at the acceptance gate")
    tasks = open_tasks(shown, main_tree)
    if not tasks or any(not is_labeled_for_human(task) for task in tasks):
        raise NothingToSend(f"{epic} has a task that is not parked")
    parks = {str(task["id"]): last_park(str(task["id"]), main_tree)[0] for task in tasks}
    first = str(tasks[0]["id"])
    names = ", ".join(parks)
    return Notice(ONLY_PARKED_LEFT, epic, first, f"Only parked tasks left: {shown.get('title') or epic}",
                  f"{len(tasks)} parked and waiting on you: {names}.",
                  digest(*(f"{task}:{fingerprint}" for task, fingerprint in parks.items())))


def at_acceptance_gate(epic: str, main_tree: Path) -> Notice:
    shown = epic_of(epic, main_tree)
    if is_closed(shown) or not at_the_gate(shown):
        raise NothingToSend(f"{epic} is not at the acceptance gate")
    head = validated_head(metadata_of(shown))
    return Notice(ACCEPTANCE_GATE, epic, epic, f"Ready for acceptance: {shown.get('title') or epic}",
                  "The factory has finished its work on the epic. Merge it or drop it, "
                  "or send it back with /jidoka:accept.",
                  digest(WAITING, head))


def stopped_with_work_left(epic: str, main_tree: Path) -> Notice:
    shown = epic_of(epic, main_tree)
    if is_closed(shown) or at_the_gate(shown):
        raise NothingToSend(f"{epic} is closed or at the acceptance gate, so it has no work left")
    tasks = open_tasks(shown, main_tree)
    if not tasks:
        raise NothingToSend(f"{epic} has no open task, so it has no work left")
    ids = [str(task["id"]) for task in tasks]
    return Notice(FACTORY_STOPPED, epic, epic, f"Factory stopped: {shown.get('title') or epic}",
                  f"{len(ids)} open tasks are left: {', '.join(ids)}. Start the factory again to carry on.",
                  digest(*(f"{task['id']}:{lap_record.number_of(metadata_of(task))}" for task in tasks)))


def paused_on_the_human(epic: str, main_tree: Path) -> Notice:
    shown = epic_of(epic, main_tree)
    if is_closed(shown):
        raise NothingToSend(f"{epic} is closed")
    held = pause.held_by(shown)
    if held is None:
        raise NothingToSend(f"{epic} is not paused")
    if not held.needs_human(clock.now()):
        raise NothingToSend(f"the pause on {epic} waits only on the clock")
    return Notice(FACTORY_PAUSED, epic, epic, f"Factory paused: {shown.get('title') or epic}",
                  f"The factory is paused on {pause.WORDS[held.cause]}. {PAUSE_HINTS[held.cause]}",
                  digest(held.cause, str(held.since)))


def host_prompt(session: str, home: Path, main_tree: Path) -> Notice:
    """The notification for a permission prompt in the host of `session`, which names the running epic that a
    manager of that session claimed; raises NothingToSend when the session manages none."""
    managed = heartbeat.managed_by(home, main_tree, session)
    if not managed:
        raise NothingToSend(f"session {session} manages no running epic")
    epic = managed[0]
    shown = epic_of(epic, main_tree)
    return Notice(PERMISSION_PROMPT, epic, epic, f"Permission prompt: {shown.get('title') or epic}",
                  "The host asks you for a permission while the epic runs.", str(time.time_ns()))


def notice_for(event: str, bead: str, main_tree: Path) -> Notice:
    """The notification the event makes on the bead; raises NothingToSend when the event does not hold."""
    makers = {TASK_PARKED: parked_task, EPIC_PARKED: parked_epic, ONLY_PARKED_LEFT: only_parked_tasks_left,
              ACCEPTANCE_GATE: at_acceptance_gate, FACTORY_STOPPED: stopped_with_work_left,
              FACTORY_PAUSED: paused_on_the_human}
    return makers[event](bead, main_tree)


def sent_so_far(epic: dict) -> dict[str, object]:
    held = metadata_of(epic).get(NOTIFICATION_KEY)
    if isinstance(held, str):
        try:
            held = json.loads(held)
        except ValueError:
            held = {}
    return {str(key): value for key, value in held.items()} if isinstance(held, dict) else {}


def fingerprint_of(entry: object) -> str:
    """The fingerprint an entry of the epic's key holds: the `fingerprint` field of an object, or the entry itself
    when it is a bare fingerprint string."""
    return str(entry.get("fingerprint")) if isinstance(entry, dict) else str(entry)


def entry_of(notice: Notice) -> dict[str, str]:
    """What the epic's key records for a notice: the fingerprint that tells one state from the next, and the title
    and text that jidoka-ui shows, so that the app words nothing itself."""
    return {"fingerprint": notice.fingerprint, "title": notice.title, "text": notice.text}


def record(notice: Notice, main_tree: Path) -> None:
    """Writes the notice into the epic's key; raises NothingToSend when the key already holds its fingerprint."""
    sent = sent_so_far(read_bead(notice.epic, main_tree))
    name = f"{notice.event}:{notice.bead}"
    if name in sent and fingerprint_of(sent[name]) == notice.fingerprint:
        raise NothingToSend(f"{notice.event} on {notice.bead} was already sent")
    written = json.dumps({**sent, name: entry_of(notice)}, sort_keys=True)
    run(["bd", "update", notice.epic, "--set-metadata", f"{NOTIFICATION_KEY}={written}"], main_tree,
        env_as_factory())


def pushover_settings(home: Path) -> Pushover | None:
    """This machine's Pushover keys, or None when the file is missing or holds no usable pair."""
    path = home / PUSHOVER_FILE
    if not path.is_file():
        return None
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"notify: {path} cannot be read, so Pushover is off: {error}", file=sys.stderr)
        return None
    if not isinstance(held, dict):
        print(f"notify: {path} does not hold a JSON object, so Pushover is off", file=sys.stderr)
        return None
    keys = [str(held.get(key) or "").strip() for key in ("user_key", "app_token", "ui_url", "api_url")]
    user_key, app_token, ui_url, api_url = keys
    if not user_key or not app_token:
        return None
    return Pushover(user_key, app_token, (ui_url or UI_ADDRESS).rstrip("/"), api_url or PUSHOVER_API)


def bead_link(pushover: Pushover, bead: str, main_tree: Path) -> str:
    return (f"{pushover.ui_url}/bead/{urllib.parse.quote(bead, safe='')}"
            f"?project={urllib.parse.quote(str(main_tree), safe='')}")


def send_pushover(pushover: Pushover, notice: Notice, main_tree: Path) -> None:
    fields = {"token": pushover.app_token, "user": pushover.user_key,
              "title": shortened(notice.title, TITLE_LIMIT), "message": shortened(notice.text, MESSAGE_LIMIT),
              "url": bead_link(pushover, notice.bead, main_tree), "url_title": notice.bead}
    request = urllib.request.Request(pushover.api_url, data=urllib.parse.urlencode(fields).encode("utf-8"),
                                     method="POST")
    try:
        with urllib.request.urlopen(request, timeout=PUSHOVER_TIMEOUT_SECONDS) as response:
            response.read()
    except OSError as error:
        print(f"notify: Pushover did not take the message: {error}", file=sys.stderr)


def deliver(notice: Notice, home: Path, main_tree: Path) -> str:
    """Records the notice, sends it, and returns the line for the host; raises NothingToSend when the epic's key
    already holds it."""
    record(notice, main_tree)
    pushover = pushover_settings(home)
    if pushover is not None:
        send_pushover(pushover, notice, main_tree)
    return f"jidoka: {notice.title}. {notice.text} ({notice.bead})"


def notify(event: str, bead: str, home: Path, main_tree: Path) -> str:
    """Sends the notification once and returns the line for the host; raises NothingToSend when there is none."""
    return deliver(notice_for(event, bead, main_tree), home, main_tree)


def announce(event: str, bead: str, home: Path, main_tree: Path, caller: str) -> None:
    """Sends the notification and puts the line the host shows on stderr, with the caller's name in front of any
    reason it was not sent.

    Missing a notification loses nothing, so one that cannot be sent never fails the caller.
    """
    try:
        print(notify(event, bead, home, main_tree), file=sys.stderr)
    except NothingToSend as reason:
        print(f"{caller}: no {event} notification: {reason}", file=sys.stderr)
    except (EpicsError, EpicReadError, CommandError, OSError) as error:
        print(f"{caller}: the {event} notification was not sent: {error}", file=sys.stderr)


def main(argv: list[str]) -> int:
    home_flag = argparse.ArgumentParser(add_help=False)
    home_flag.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    parser = argparse.ArgumentParser(prog="notify.py", description="Tell the human that the factory waits on them.")
    events = parser.add_subparsers(dest="event", required=True)
    for event in BEAD_EVENTS:
        events.add_parser(event, parents=[home_flag]).add_argument("bead", help="the bead the event is about")
    about_a_session = events.add_parser(PERMISSION_PROMPT, parents=[home_flag])
    about_a_session.add_argument("--session", required=True, help="the id of the host session")
    args = parser.parse_args(argv)
    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = settings_reader.jidoka_home(args.jidoka_home)
        if args.event == PERMISSION_PROMPT:
            line = deliver(host_prompt(args.session, home, main_tree), home, main_tree)
        else:
            line = notify(args.event, args.bead, home, main_tree)
    except NothingToSend as reason:
        print(f"notify: nothing to send: {reason}", file=sys.stderr)
        return 0
    except (EpicsError, EpicReadError, CommandError, settings_reader.SettingsError, OSError) as error:
        print(f"notify: {error}", file=sys.stderr)
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
