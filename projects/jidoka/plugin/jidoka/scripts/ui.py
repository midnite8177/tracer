#!/usr/bin/env python3
"""Starts jidoka-ui for the factory when its address does not answer.

`start --jidoka-home <home> --wait <seconds>` reads the `ui` record that the installer keeps in the machine settings:
the dotnet that published jidoka-ui, the published app and its port. It asks http://localhost:<port>/ for an
answer, and any HTTP answer counts. When the address answers, it starts nothing. Otherwise it runs
`<dotnet> <app> --port <port>` in the app's folder, in a session of its own (on Windows, a process with no window or console of the caller) so that the factory's
session never holds it, with JIDOKA_HOME set to the home, its output in <home>/ui/jidoka-ui.log and its pid in
<home>/ui/jidoka-ui.pid. It then waits until the address answers, the app exits, or the wait passes, and returns.
An app that has not answered by then keeps running, and the reason names its pid.

The probe and the start happen under <home>/locks/ui.lock, which the system lets go of when the holder exits. Two
starts at once therefore start one app: the second waits for the first, then finds the address answering.

It prints one JSON object: `state`, which is `answering`, `started`, `not installed` or `failed`; `address`, null
when no record names one; `why`, the reason when the state is neither of the first two; and `log`, the log of the
app it started, or null.

Exit codes:
  0  the address answers, whether it did already or after the start.
  1  it does not: no published jidoka-ui is recorded, or the app did not answer.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import file_lock
import processes
import routes

UI_FOLDER = "ui"
LOG_FILE = "jidoka-ui.log"
PID_FILE = "jidoka-ui.pid"
LOCK_FILE = Path("locks") / "ui.lock"
PROBE_TIMEOUT_SECONDS = 2.0
POLL_SECONDS = 0.2
LOG_TAIL_LINES = 12
HIGHEST_PORT = 65535
RERUN = "Run install.py from your jidoka checkout with dotnet on the PATH to publish it."


@dataclass(frozen=True)
class Published:
    """The jidoka-ui that the installer published: the dotnet that runs it, the app and the port it binds."""
    dotnet: str
    app: Path
    port: int

    @property
    def address(self) -> str:
        return f"http://localhost:{self.port}"


@dataclass(frozen=True)
class Outcome:
    state: str
    address: str | None
    why: str | None
    log: str | None

    @property
    def answers(self) -> bool:
        return self.state in ("answering", "started")


def published_in(home: Path) -> Published | str:
    """The published jidoka-ui the machine settings record, or the reason there is none."""
    try:
        record = routes.settings_in(home).get("ui")
    except routes.RouteError as error:
        return f"{error}. {RERUN}"
    path = routes.settings_path(home)
    if not isinstance(record, dict):
        return f"{path} records no published jidoka-ui. {RERUN}"
    dotnet, app, port = record.get("dotnet"), record.get("app"), record.get("port")
    if not isinstance(dotnet, str) or not dotnet or not isinstance(app, str) or not app \
            or not isinstance(port, int) or isinstance(port, bool) or not 0 < port <= HIGHEST_PORT:
        return f"{path} holds a jidoka-ui record that does not name a dotnet, an app and a port. {RERUN}"
    return Published(dotnet, Path(app), port)


def answers(address: str) -> bool:
    try:
        with urllib.request.urlopen(address + "/", timeout=PROBE_TIMEOUT_SECONDS):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


def log_tail(log: Path) -> str:
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-LOG_TAIL_LINES:])


def start(published: Published, home: Path, wait: float) -> Outcome:
    folder = home / UI_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / LOG_FILE
    with log.open("wb") as output:
        process = subprocess.Popen([published.dotnet, str(published.app), "--port", str(published.port)],
                                   cwd=published.app.parent, env={**os.environ, "JIDOKA_HOME": str(home)},
                                   stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                   **processes.detached_options())
    (folder / PID_FILE).write_text(f"{process.pid}\n", encoding="utf-8")
    deadline = time.monotonic() + wait
    while True:
        if answers(published.address):
            return Outcome("started", published.address, None, str(log))
        ended = process.poll()
        if ended is not None:
            return Outcome("failed", published.address,
                           f"jidoka-ui exited with {ended} before {published.address} answered. The end of its "
                           f"log, {log}:\n{log_tail(log)}", str(log))
        if time.monotonic() >= deadline:
            return Outcome("failed", published.address,
                           f"{published.address} did not answer within {wait:g} s of the start. jidoka-ui still "
                           f"runs as process {process.pid}, and its log is {log}", str(log))
        time.sleep(POLL_SECONDS)


def ensure_answering(home: Path, wait: float) -> Outcome:
    published = published_in(home)
    if isinstance(published, str):
        return Outcome("not installed", None, published, None)
    with file_lock.exclusive(home / LOCK_FILE):
        if answers(published.address):
            return Outcome("answering", published.address, None, None)
        return start(published, home, wait)


def positive_seconds(text: str) -> float:
    try:
        seconds = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number of seconds") from None
    if not seconds > 0:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive number of seconds")
    return seconds


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ui.py", description="Start jidoka-ui when its address does not answer.")
    modes = parser.add_subparsers(dest="mode", required=True)
    starting = modes.add_parser("start", help="start jidoka-ui unless its address answers")
    starting.add_argument("--jidoka-home", required=True, help="the folder that holds jidoka's per-machine state")
    starting.add_argument("--wait", required=True, type=positive_seconds, metavar="SECONDS",
                          help="how long to wait for a started jidoka-ui to answer")
    args = parser.parse_args(argv)
    home = Path(args.jidoka_home).expanduser().resolve()
    try:
        outcome = ensure_answering(home, args.wait)
    except OSError as error:
        outcome = Outcome("failed", None, f"jidoka-ui could not be started: {error}", None)
    print(json.dumps({"state": outcome.state, "address": outcome.address, "why": outcome.why, "log": outcome.log}))
    return 0 if outcome.answers else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
