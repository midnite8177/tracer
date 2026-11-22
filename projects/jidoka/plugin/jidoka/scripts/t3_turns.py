"""The one reader of T3's state db, which gives the provider turns of a thread, whether it has a run in progress, the
runtime requests that wait for an answer and the runs that ended.

T3 keeps its state in <T3 userdata>/statev2.sqlite, a file private to T3, so no other module opens it, and this reader
opens it read-only. A thread has a run in progress when its latest run, by `ordinal`, in
`orchestration_v2_projection_runs` has the status `running` (has_run_in_progress). The table
`projection_thread_sessions` holds no row in T3's db, so it is not read. Its runtime requests are the rows of `orchestration_v2_projection_runtime_requests`,
and one waits for an answer when its status is `pending` (pending_requests). Its runs are the rows of
`orchestration_v2_projection_runs`, and one has ended when its status is `completed` (completed_runs). A db that lacks
one of those tables or their columns raises NoRunState.

For the turns, this reader reads three tables. `orchestration_v2_projection_provider_turns` has a row for each provider
turn, with its `thread_id`, its `run_attempt_id` and its `payload_json`, the JSON of the provider turn as T3 encodes it.
The tokens of a turn are the `turnTokenUsage` object of that payload: `inputTokens`, `cachedInputTokens`,
`cacheCreationTokens` and `outputTokens`. T3 counts the cached and cache-creation tokens inside the input and the
reasoning tokens inside the output, so a turn's fresh input is the input less the other two, and `reasoningTokens` is
never read. A turn whose `usageStatus` is `unavailable`, or that has no `turnTokenUsage`, adds nothing. The payload's
`tokenUsage` is a snapshot of the context window, not what the turn used, and is never read.

A turn belongs to a run through its attempt: `orchestration_v2_projection_run_attempts` maps an `attempt_id` to a
`run_id`, and the run's row in `orchestration_v2_projection_runs` holds the model in the `modelSelection.model` of its
`payload_json`. A turn whose attempt is not known belongs to no run and names no model.

A run has failed when its status is `failed`, or when one of its attempts has the status `failed` while the run itself
is neither `completed` nor `running` (thread_runs). The run's payload has no error field, so the status is the whole
sign of a failure (ADR 0013).

The names of these tables, columns and payload fields are read from T3's own source, and are held in the constants
below so that a schema change breaks this file alone. A db that lacks a table or a column, a file that is missing or
cannot be read as SQLite, a thread or run with no turn, and a thread or run whose turns carry no readable tokens all
raise NoTurns, whose reason names what was missing; the caller writes the row with no tokens and logs the reason.

$JIDOKA_T3_STATE_DB names the db file, else it is ~/.t3/userdata/statev2.sqlite.
"""
from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from prices import NO_TOKENS, Tokens, count_of

STATE_VARIABLE = "JIDOKA_T3_STATE_DB"
STATE_FILE = Path(".t3") / "userdata" / "statev2.sqlite"
TURNS_TABLE = "orchestration_v2_projection_provider_turns"
TURN_THREAD_COLUMN = "thread_id"
TURN_ATTEMPT_COLUMN = "run_attempt_id"
TURN_PAYLOAD_COLUMN = "payload_json"
USAGE_KEY = "turnTokenUsage"
USAGE_STATUS_KEY = "usageStatus"
USAGE_UNAVAILABLE = "unavailable"
INPUT_KEY = "inputTokens"
CACHED_KEY = "cachedInputTokens"
CREATION_KEY = "cacheCreationTokens"
OUTPUT_KEY = "outputTokens"
ATTEMPTS_TABLE = "orchestration_v2_projection_run_attempts"
ATTEMPT_ID_COLUMN = "attempt_id"
ATTEMPT_THREAD_COLUMN = "thread_id"
ATTEMPT_RUN_COLUMN = "run_id"
RUN_PAYLOAD_COLUMN = "payload_json"
MODEL_SELECTION_KEY = "modelSelection"
MODEL_KEY = "model"
RUNNING_STATUS = "running"
REQUESTS_TABLE = "orchestration_v2_projection_runtime_requests"
REQUEST_ID_COLUMN = "runtime_request_id"
REQUEST_THREAD_COLUMN = "thread_id"
REQUEST_STATUS_COLUMN = "status"
PENDING_STATUS = "pending"
RUNS_TABLE = "orchestration_v2_projection_runs"
RUN_ID_COLUMN = "run_id"
RUN_THREAD_COLUMN = "thread_id"
RUN_STATUS_COLUMN = "status"
RUN_ORDINAL_COLUMN = "ordinal"
RUN_REQUESTED_COLUMN = "requested_at"
RUN_COMPLETED_COLUMN = "completed_at"
COMPLETED_STATUS = "completed"
FAILED_STATUS = "failed"
ATTEMPT_STATUS_COLUMN = "status"
BUSY_TIMEOUT_SECONDS = 5


class NoTurns(Exception):
    """T3 gave no turns for the thread, with the reason worded for the person who reads stderr."""


class NoRunState(Exception):
    """T3 gave no answer about the runs and requests of the thread, with the reason worded for the person who reads
    stderr."""


@dataclass(frozen=True)
class ModelTurns:
    """The summed tokens of the turns of one thread that ran on one model. The model is None when the turns' model
    selection names none."""
    model: str | None
    tokens: Tokens


@dataclass(frozen=True)
class CompletedRun:
    """A run of a thread that has ended, and the seconds it took from its request to its end."""
    run: str
    wall_seconds: int


def state_path() -> Path:
    named = os.environ.get(STATE_VARIABLE, "").strip()
    return Path(named).expanduser() if named else Path.home() / STATE_FILE


def json_object(text: object) -> dict:
    """The JSON object that the text holds, or an empty one when it is not text, not JSON or not an object."""
    if not isinstance(text, str):
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def model_of(run_payload: object) -> str | None:
    """The `modelSelection.model` of a run's payload JSON, or None when the payload holds none."""
    selection = json_object(run_payload).get(MODEL_SELECTION_KEY)
    model = selection.get(MODEL_KEY) if isinstance(selection, dict) else None
    return model if isinstance(model, str) and model else None


def tokens_of(turn_payload: object) -> Tokens | None:
    """What the turn used, from the `turnTokenUsage` of its payload JSON, with the cached and cache-creation tokens
    taken out of the input. None when the payload has no such object, says its usage is unavailable, or counts no
    input and no output."""
    usage = json_object(turn_payload).get(USAGE_KEY)
    if not isinstance(usage, dict) or usage.get(USAGE_STATUS_KEY) == USAGE_UNAVAILABLE:
        return None
    if INPUT_KEY not in usage and OUTPUT_KEY not in usage:
        return None
    cached, creation = count_of(usage.get(CACHED_KEY)), count_of(usage.get(CREATION_KEY))
    fresh = max(0, count_of(usage.get(INPUT_KEY)) - cached - creation)
    return Tokens(fresh, count_of(usage.get(OUTPUT_KEY)), cached, creation)


class StateDbError(Exception):
    """T3's state db could not give a table's rows, with the reason worded for the person who reads stderr. Each
    reader below says what that means to its callers, as NoTurns or NoRunState."""


@contextmanager
def reported_as(failure: type[Exception]) -> Iterator[None]:
    """Raises `failure` with the reason of any StateDbError the block raises."""
    try:
        yield
    except StateDbError as error:
        raise failure(str(error)) from error


def select(table: str, selected: tuple[str, ...], where: dict[str, object], order_by: tuple[str, ...]
           ) -> list[tuple]:
    """The selected columns of the rows of the table whose `where` columns hold the given values, oldest first by the
    `order_by` columns and then by the row, read-only, never creating the db. It raises StateDbError when the db is
    missing, cannot be read as SQLite, or lacks the table or any column it names."""
    path = state_path()
    if not path.is_file():
        raise StateDbError(f"T3 has no state db at {path}")
    required = tuple(dict.fromkeys((*where, *selected, *order_by)))
    condition = " AND ".join(f"{column} = ?" for column in where)
    order = ", ".join((*order_by, "rowid"))
    try:
        with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=BUSY_TIMEOUT_SECONDS)) as db:
            held = {name for (_, name, *_rest) in db.execute(f"PRAGMA table_info({table})")}
            missing = [column for column in required if column not in held]
            if missing:
                lacking = f"lacks {', '.join(missing)}" if held else "has no such table"
                raise StateDbError(f"the schema of {path} is not one this reader knows: {table} {lacking}")
            return db.execute(f"SELECT {', '.join(selected)} FROM {table} WHERE {condition} ORDER BY {order}",
                              tuple(where.values())).fetchall()
    except sqlite3.Error as error:
        raise StateDbError(f"T3's state db at {path} could not be read: {error}") from error


def has_run_in_progress(thread: str) -> bool:
    """True when the thread's latest run, the one with the highest `ordinal` in `orchestration_v2_projection_runs`,
    has the status `running`. A thread with no run has none in progress."""
    with reported_as(NoRunState):
        found = select(RUNS_TABLE, (RUN_STATUS_COLUMN,), {RUN_THREAD_COLUMN: thread}, (RUN_ORDINAL_COLUMN,))
    return bool(found) and found[-1][0] == RUNNING_STATUS


def pending_requests(thread: str) -> list[str]:
    """The ids of the thread's runtime requests that wait for an answer, the oldest first."""
    with reported_as(NoRunState):
        found = select(REQUESTS_TABLE, (REQUEST_ID_COLUMN,),
                       {REQUEST_THREAD_COLUMN: thread, REQUEST_STATUS_COLUMN: PENDING_STATUS}, ())
    return [str(request) for (request,) in found]


def seconds_between(begun: object, ended: object) -> int:
    """The whole seconds from one ISO 8601 time to another, 0 when either cannot be read or the second is earlier."""
    try:
        first, last = (datetime.fromisoformat(str(each).replace("Z", "+00:00")) for each in (begun, ended))
        return max(0, int((last - first).total_seconds()))
    except ValueError:
        return 0


def completed_runs(thread: str) -> list[CompletedRun]:
    """The runs of the thread that have ended, the oldest first."""
    with reported_as(NoRunState):
        found = select(RUNS_TABLE, (RUN_ID_COLUMN, RUN_REQUESTED_COLUMN, RUN_COMPLETED_COLUMN),
                       {RUN_THREAD_COLUMN: thread, RUN_STATUS_COLUMN: COMPLETED_STATUS}, ())
    return [CompletedRun(str(run), seconds_between(requested, completed)) for run, requested, completed in found]


@dataclass(frozen=True)
class ThreadRun:
    """A run of a thread, and whether it failed, as the status of the run and of its attempts say."""
    run: str
    failed: bool


def thread_runs(thread: str) -> list[ThreadRun]:
    """The thread's runs, the oldest first by `ordinal`, so that the last is the latest run as has_run_in_progress
    reads it. A run has failed when its status is `failed`, or when an attempt of it failed while the run is neither
    completed nor running, which covers a failed run whose own row says otherwise."""
    with reported_as(NoRunState):
        runs = select(RUNS_TABLE, (RUN_ID_COLUMN, RUN_STATUS_COLUMN), {RUN_THREAD_COLUMN: thread},
                      (RUN_ORDINAL_COLUMN,))
        attempts = select(ATTEMPTS_TABLE, (ATTEMPT_RUN_COLUMN, ATTEMPT_STATUS_COLUMN),
                          {ATTEMPT_THREAD_COLUMN: thread}, ())
    with_failed_attempt = {str(run) for run, status in attempts if status == FAILED_STATUS}
    return [ThreadRun(str(run), status == FAILED_STATUS
                      or (str(run) in with_failed_attempt and status not in (COMPLETED_STATUS, RUNNING_STATUS)))
            for run, status in runs]


@dataclass(frozen=True)
class ThreadTurn:
    """A provider turn of a thread: the run it belongs to and that run's model, each None when T3's rows do not tie
    the turn to one, and the tokens the turn used, None when its payload gives none."""
    run: str | None
    model: str | None
    tokens: Tokens | None


def thread_turns(thread: str) -> list[ThreadTurn]:
    """The thread's provider turns, the oldest first, each tied to its run through its attempt."""
    with reported_as(NoTurns):
        turns = select(TURNS_TABLE, (TURN_ATTEMPT_COLUMN, TURN_PAYLOAD_COLUMN), {TURN_THREAD_COLUMN: thread}, ())
        attempts = select(ATTEMPTS_TABLE, (ATTEMPT_ID_COLUMN, ATTEMPT_RUN_COLUMN), {ATTEMPT_THREAD_COLUMN: thread},
                          ())
        runs = select(RUNS_TABLE, (RUN_ID_COLUMN, RUN_PAYLOAD_COLUMN), {RUN_THREAD_COLUMN: thread}, ())
    run_of_attempt = {str(attempt): str(run) for attempt, run in attempts}
    model_of_run = {str(run): model_of(payload) for run, payload in runs}
    found = []
    for attempt, payload in turns:
        run = run_of_attempt.get(str(attempt))
        found.append(ThreadTurn(run, model_of_run.get(run) if run is not None else None, tokens_of(payload)))
    return found


def summed(turns: list[ThreadTurn]) -> list[ModelTurns]:
    """The tokens of the turns that have any, summed for each model in the order the models first appear."""
    sums: dict[str | None, Tokens] = {}
    for turn in turns:
        if turn.tokens is not None:
            sums[turn.model] = sums.get(turn.model, NO_TOKENS).plus(turn.tokens)
    return [ModelTurns(model, tokens) for model, tokens in sums.items()]


def read_turns_of(thread: str, run: str | None) -> list[ModelTurns]:
    """The turns of the thread, or of one run of it, summed for each model. It raises NoTurns when there is no such
    turn, or when none of them carries tokens this reader can read."""
    turns = thread_turns(thread)
    where = f"thread {thread}" if run is None else f"run {run} of thread {thread}"
    if run is not None:
        turns = [turn for turn in turns if turn.run == run]
    if not turns:
        raise NoTurns(f"T3's state db holds no provider turn of {where}")
    summed_turns = summed(turns)
    if not summed_turns:
        raise NoTurns(f"no provider turn of {where} has a {USAGE_KEY} this reader can read in its "
                      f"{TURN_PAYLOAD_COLUMN}")
    return summed_turns


def read_turns(thread: str) -> list[ModelTurns]:
    """The turns of the thread, summed for each model in the order the models first appear."""
    return read_turns_of(thread, None)


def read_run_turns(thread: str, run: str) -> list[ModelTurns]:
    """The turns of one run of the thread, summed as read_turns sums them."""
    return read_turns_of(thread, run)
