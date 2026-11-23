#!/usr/bin/env python3
"""Keeps the ledger of what the factory spends, in jidoka's home, and prints an epic's rows.

The ledger is the SQLite file <jidoka-home>/ledger.sqlite, with one row in its `runs` table for each worker run and
for each request of a manager. It lives in the user-scope home, not in a repo's beads, so it outlives the epics it
prices and holds every repo. A row names the repo (the path of its main worktree), the epic, the task, the lap, the
stage, the try, the track, the tier, the route's harness, the model that ran, the route's effort, the agent id, the
tokens by kind, the dollars at list price (price_pages.py), the wall time in seconds and the outcome. A row is
written once and keeps the dollars it was written with when the list prices change; only its outcome can change, as
the next paragraph says. The dollars are None when the model has no listed price.

The lap mod writes <jidoka-home>/tokens/<agent id>.json for each lap worker, a JSON object with `model` and the sums
over all the worker's steps: `input_tokens`, `output_tokens`, `cache_read_input_tokens` and
`cache_creation_input_tokens`. Under an Antigravity host there is no lap mod, the agent id is the worker's T3 thread,
and t3_turns.py reads the thread's provider turns from T3's state db: a row for each model the turns' runs name, else one
row on the route's model. Turns that cannot be read write the row with no tokens and a line on stderr. The
scheduler records a run when a worker's report comes in, naming the agent
id the manager got when it started the worker. A report that names no agent writes its row with no tokens. Under an
Antigravity host a thread whose rows the ledger holds already is not priced again, so a T3 stage that priced its
thread when it was reported (t3_stage.py) is not counted twice. The scheduler's report gives those rows its outcome
and writes none. The
workers of an epic's pass (the test cleanup, the tidy, each review lane, the fix and the validation) belong to no task,
so their rows have no task and the stage's name. Both go through `record_run_or_say`, which takes the worker, where the
run belongs and the outcome, and never fails. A run that a script measured itself goes through `record_ran_or_say`.

After each row the epic's metadata gets `spend.dollars`, the sum of the dollars of its rows in the repo, because the
scheduler reads only beads when it checks the budget.

`list <epic>` prints {"epic", "dollars", "rows"}: the epic's running total and its rows in the order they were
written, each with the columns above (`try` for the try, `cache_read_tokens` and `cache_write_tokens` for the cache
tokens) and `at`, the second the row was written.

`request --session <id> --model <model> --input <n> --output <n> --cache-read <n> --cache-write <n> --seconds <n>`
is what the lap mod runs when a manager's request ends, from the host's folder. It writes a `manager` row on the
epic whose heartbeat records that session (the first by id when there are several), and nothing when none does. It
reads the heartbeat files before anything else, because the mod runs it after every request of every session.
Under an Antigravity host there is no lap mod, and the beater (beater.py) writes the same row for each completed run
of the manager's T3 thread, one for each model the run's provider turns name.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  success, or a request that no epic concerns.
  1  it could not run, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import clock
import heartbeat
import price_pages
import settings_reader
import routes
import t3_turns
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, env_as_factory, run, set_metadata
from lap_record import Lap
from prices import NO_TOKENS, SPEND_KEY, Tokens, count_of

LEDGER_FILE = "ledger.sqlite"
TOKENS_FOLDER = "tokens"
MANAGER_STAGE = "manager"
REQUEST_OUTCOME = "request"
BUSY_TIMEOUT_SECONDS = 30
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at INTEGER NOT NULL,
    repo TEXT NOT NULL,
    epic TEXT NOT NULL,
    task TEXT,
    lap INTEGER,
    stage TEXT NOT NULL,
    try_number INTEGER,
    track TEXT,
    tier TEXT,
    harness TEXT,
    model TEXT,
    effort TEXT,
    agent TEXT,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL,
    cache_write_tokens INTEGER NOT NULL,
    dollars REAL,
    wall_seconds INTEGER NOT NULL,
    outcome TEXT NOT NULL
)
"""
COLUMNS = ("at", "repo", "epic", "task", "lap", "stage", "try_number", "track", "tier", "harness", "model", "effort",
           "agent", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "dollars",
           "wall_seconds", "outcome")


@dataclass(frozen=True)
class Row:
    """One row of the ledger, as it is written."""
    at: int
    repo: str
    epic: str
    task: str | None
    lap: int | None
    stage: str
    try_number: int | None
    track: str | None
    tier: str | None
    harness: str | None
    model: str | None
    effort: str | None
    agent: str | None
    used: Tokens
    dollars: float | None
    wall_seconds: int
    outcome: str


class LedgerError(Exception):
    """A row the ledger could not take, or a total it could not keep, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Worker:
    """What the manager knows of the worker whose report it takes: the agent id the host gave it, which names the
    tokens the lap mod summed for it, and the tier it ran on. Either is None when the report names none. `on_native`
    is true when the report says the worker ran on the tier's native route, because the tier's own route failed: the
    row is then priced from the native route, not from the route the machine records for the tier."""
    agent: str | None
    tier: str | None
    on_native: bool


@dataclass(frozen=True)
class Where:
    """Where in an epic a run belongs: the task, lap, try and track of a lap's stage, or only the name of a pass
    stage, and the seconds the stage took."""
    task: str | None
    lap: int | None
    stage: str
    try_number: int | None
    track: str | None
    wall_seconds: int

    @staticmethod
    def of_lap(lap: Lap, now: int) -> Where:
        """The wall time runs from the stage's start to now, and is zero for a stage that records no start. The try is
        the one this run is: the tries counted so far plus one."""
        wall = max(0, now - lap.started) if lap.started is not None else 0
        return Where(lap.task, lap.number, lap.stage, lap.tries + 1, lap.track, wall)

    @staticmethod
    def of_pass(stage: str) -> Where:
        """A pass stage belongs to no task and no lap, and it records no start, so it has no task, lap, try or track,
        and its wall time is zero."""
        return Where(None, None, stage, None, None, 0)


@dataclass(frozen=True)
class Used:
    """What the lap mod wrote for one agent id: the model that ran and the tokens it used."""
    model: str | None
    tokens: Tokens


NOTHING_USED = Used(None, NO_TOKENS)


def ledger_path(home: Path) -> Path:
    return home / LEDGER_FILE


def connect(home: Path) -> sqlite3.Connection:
    """The ledger of the home, made with its table when it is new."""
    home.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(ledger_path(home), timeout=BUSY_TIMEOUT_SECONDS)
    connection.execute(SCHEMA)
    return connection


def tokens_of(home: Path, agent: str | None) -> Used:
    """The model and tokens the lap mod wrote for the agent id, or nothing used when it wrote none or the file
    cannot be read."""
    if not agent:
        return NOTHING_USED
    try:
        written = json.loads((home / TOKENS_FOLDER / f"{agent}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return NOTHING_USED
    if not isinstance(written, dict):
        return NOTHING_USED
    model = written.get("model")
    return Used(model if isinstance(model, str) and model else None,
                Tokens(count_of(written.get("input_tokens")), count_of(written.get("output_tokens")),
                       count_of(written.get("cache_read_input_tokens")),
                       count_of(written.get("cache_creation_input_tokens"))))


def route_of(home: Path, tier: str | None, on_native: bool) -> routes.Route | None:
    """The route the worker ran on: the tier's native route when it fell back to it, else the tier's route from the
    table of the host the caller runs under, or None when the settings cannot give a complete one. A run is priced
    whatever the settings hold."""
    if not tier:
        return None
    try:
        if on_native:
            return routes.native_route_of(tier)
        return routes.recorded_route_here(tier, home)
    except (routes.RouteError, OSError):
        return None


def write(home: Path, row: Row) -> None:
    values = (row.at, row.repo, row.epic, row.task, row.lap, row.stage, row.try_number, row.track, row.tier,
              row.harness, row.model, row.effort, row.agent, row.used.input, row.used.output, row.used.cache_read,
              row.used.cache_write, row.dollars, row.wall_seconds, row.outcome)
    with closing(connect(home)) as connection, connection:
        connection.execute(f"INSERT INTO runs ({', '.join(COLUMNS)}) VALUES ({', '.join('?' for _ in COLUMNS)})",
                           values)


def total_of(home: Path, repo: str, epic: str) -> float:
    """The sum of the dollars of the epic's rows in the repo; a row with no price adds nothing."""
    connection = connect(home)
    try:
        [(total,)] = connection.execute("SELECT COALESCE(SUM(dollars), 0.0) FROM runs WHERE repo = ? AND epic = ?",
                                        (repo, epic)).fetchall()
    finally:
        connection.close()
    return round(float(total), 6)


def rows_of(home: Path, repo: str, epic: str) -> list[dict]:
    connection = connect(home)
    try:
        found = connection.execute(f"SELECT {', '.join(COLUMNS)} FROM runs WHERE repo = ? AND epic = ? "
                                   "ORDER BY id", (repo, epic)).fetchall()
    finally:
        connection.close()
    return [{("try" if column == "try_number" else column): value for column, value in zip(COLUMNS, row)}
            for row in found]


def keep_total(home: Path, repo: str, epic: str, main_tree: Path) -> float:
    """Puts the epic's running total into its metadata and returns it."""
    total = total_of(home, repo, epic)
    run(["bd", "update", epic, *set_metadata((SPEND_KEY, total))], main_tree, env_as_factory())
    return total


@dataclass(frozen=True)
class Ran:
    """What a worker run is priced from: the tokens it used, the one model they are priced at and the row names, and
    the harness and effort of the route its tier names."""
    tokens: Tokens
    harness: str | None
    model: str | None
    effort: str | None


def lap_mod_tokens(home: Path, agent: str | None) -> list[tuple[str | None, Tokens]]:
    """The model and tokens of the agent that the lap mod's file holds, as the Claude Code host keeps them."""
    written = tokens_of(home, agent)
    return [(written.model, written.tokens)]


def t3_tokens(home: Path, agent: str | None) -> list[tuple[str | None, Tokens]]:
    """The model and tokens of each model the T3 thread ran on, from its provider turns, as the Antigravity host keeps
    them. An agent id that is no thread, and turns that T3 cannot give, are one entry with no tokens, and the reason
    goes to stderr."""
    if not agent:
        return [(None, NO_TOKENS)]
    try:
        return [(each.model, each.tokens) for each in t3_turns.read_turns(agent)]
    except t3_turns.NoTurns as why:
        print(f"ledger: no tokens for thread {agent}: {why}", file=sys.stderr)
        return [(None, NO_TOKENS)]


TOKEN_SOURCES = {routes.CLAUDE_CODE_HOST: lap_mod_tokens, routes.ANTIGRAVITY_HOST: t3_tokens}


def tokens_for(home: Path, worker: Worker) -> list[tuple[str | None, Tokens]]:
    """The tokens the worker used, one entry for each model it ran on, from the source of the host the caller runs
    under: the lap mod's file under Claude Code, the thread's provider turns under Antigravity (t3_turns.py)."""
    return TOKEN_SOURCES[routes.host_of_environment()](home, worker.agent)


def ran_by(home: Path, worker: Worker) -> list[Ran]:
    """The runs of the worker, one for each model it ran on, priced on the model the tokens name, else the route's of
    its tier."""
    route = route_of(home, worker.tier, worker.on_native)
    used = tokens_for(home, worker)
    if route is None:
        return [Ran(tokens, None, model, None) for model, tokens in used]
    return [Ran(tokens, route.harness, model or route.model, route.effort) for model, tokens in used]


def append(home: Path, main_tree: Path, epic: str, row: Row) -> float:
    """Writes the row and returns the epic's running total, which it keeps in the epic's metadata."""
    try:
        write(home, row)
        return keep_total(home, str(main_tree), epic, main_tree)
    except (sqlite3.Error, OSError, CommandError) as error:
        raise LedgerError(str(error)) from error


def record_ran(home: Path, main_tree: Path, epic: str, where: Where, worker: Worker, ran: Ran, outcome: str,
               now: int) -> float:
    """Writes the row of a worker that has ended, from a run the caller measured itself, and returns the epic's
    running total."""
    return append(home, main_tree, epic, Row(
        at=now, repo=str(main_tree), epic=epic, task=where.task, lap=where.lap, stage=where.stage,
        try_number=where.try_number, track=where.track, tier=worker.tier, harness=ran.harness, model=ran.model,
        effort=ran.effort, agent=worker.agent, used=ran.tokens,
        dollars=price_pages.dollars(home, ran.model, ran.tokens), wall_seconds=where.wall_seconds,
        outcome=outcome))


def record_ran_or_say(home: Path, main_tree: Path, epic: str, where: Where, worker: Worker, ran: Ran, outcome: str,
                      now: int) -> None:
    """Writes the row of a run the caller measured. A ledger that cannot take the row is a line on stderr, never a
    failure."""
    try:
        record_ran(home, main_tree, epic, where, worker, ran, outcome, now)
    except LedgerError as error:
        print(f"ledger: took no row for the {where.stage} of {where.task or epic}: {error}", file=sys.stderr)


def settle_priced(home: Path, repo: str, epic: str, agent: str, outcome: str) -> bool:
    """Gives the epic's rows of the agent the outcome and says whether the agent had any. A thread that has rows was
    priced already, as a T3 stage's own report prices it, so pricing it again would count its tokens twice."""
    with closing(connect(home)) as connection, connection:
        changed = connection.execute("UPDATE runs SET outcome = ? WHERE repo = ? AND epic = ? AND agent = ?",
                                     (outcome, repo, epic, agent)).rowcount
    return changed > 0


def record_run_or_say(home: Path, main_tree: Path, epic: str, where: Where, worker: Worker, outcome: str,
                      now: int) -> None:
    """Writes the row of a worker that has ended. Under an Antigravity host the agent id is a T3 thread, which no
    other worker shares, so a thread that already has rows in the ledger is not priced again; its rows take the
    outcome. A ledger that cannot take the row is a line on stderr, never a failure, because the report of the worker
    must settle whatever the ledger does."""
    try:
        if (worker.agent and routes.host_of_environment() == routes.ANTIGRAVITY_HOST
                and settle_priced(home, str(main_tree), epic, worker.agent, outcome)):
            return
    except (sqlite3.Error, OSError) as error:
        print(f"ledger: took no row for the {where.stage} of {where.task or epic}: {error}", file=sys.stderr)
        return
    for ran in ran_by(home, worker):
        record_ran_or_say(home, main_tree, epic, where, worker, ran, outcome, now)


def epic_claimed_by(home: Path, session: str) -> str | None:
    """The first epic, by id, whose heartbeat records the session, or None when the session claimed none. It reads
    the heartbeat files alone, because it runs after every request of every session."""
    claimed = heartbeat.claimed_by(home, session)
    return claimed[0] if claimed else None


def record_request(home: Path, main_tree: Path, epic: str, model: str | None, used: Tokens, seconds: int) -> float:
    """Writes a manager row on the epic and returns the epic's running total. A row whose model is None has no
    price."""
    return append(home, main_tree, epic, Row(
        at=clock.now(), repo=str(main_tree), epic=epic, task=None, lap=None, stage=MANAGER_STAGE, try_number=None,
        track=None, tier=None, harness=None, model=model, effort=None, agent=None, used=used,
        dollars=price_pages.dollars(home, model, used), wall_seconds=seconds, outcome=REQUEST_OUTCOME))


def listing(home: Path, main_tree: Path, epic: str) -> dict:
    return {"epic": epic, "dollars": total_of(home, str(main_tree), epic), "rows": rows_of(home, str(main_tree), epic)}


def main(argv: list[str]) -> int:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    parser = argparse.ArgumentParser(prog="ledger.py", description="Print an epic's ledger rows, or write a row for "
                                                                   "a manager's request.")
    modes = parser.add_subparsers(dest="mode", required=True)
    listed = modes.add_parser("list", parents=[shared], help="print the epic's rows and its running total")
    listed.add_argument("epic")
    requested = modes.add_parser("request", parents=[shared], help="write a row for a manager's request")
    requested.add_argument("--session", required=True)
    requested.add_argument("--model", required=True)
    requested.add_argument("--input", type=int, required=True)
    requested.add_argument("--output", type=int, required=True)
    requested.add_argument("--cache-read", type=int, required=True)
    requested.add_argument("--cache-write", type=int, required=True)
    requested.add_argument("--seconds", type=int, required=True)
    args = parser.parse_args(argv)

    try:
        home = settings_reader.jidoka_home(args.jidoka_home)
        if args.mode == "list":
            main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
            print(json.dumps(listing(home, main_tree, args.epic)))
            return 0
        epic = epic_claimed_by(home, args.session)
        if epic is not None:
            main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
            used = Tokens(args.input, args.output, args.cache_read, args.cache_write)
            record_request(home, main_tree, epic, args.model, used, args.seconds)
    except (CommandError, settings_reader.SettingsError, LedgerError, sqlite3.Error, OSError) as error:
        print(f"ledger: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
