"""A fixture of T3's state db: the three tables of T3's orchestration projection that t3_turns.py reads for the
tokens of a thread, with T3's own column definitions, and the rows T3 writes into them."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

RUNS_TABLE = (
    "CREATE TABLE orchestration_v2_projection_runs (run_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, ordinal INTEGER "
    "NOT NULL, provider TEXT NOT NULL, provider_thread_id TEXT, status TEXT NOT NULL, requested_at TEXT NOT NULL, "
    "completed_at TEXT, payload_json TEXT NOT NULL)")
ATTEMPTS_TABLE = (
    "CREATE TABLE orchestration_v2_projection_run_attempts (attempt_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, "
    "run_id TEXT NOT NULL, attempt_ordinal INTEGER NOT NULL, root_node_id TEXT NOT NULL, provider TEXT NOT NULL, "
    "provider_thread_id TEXT NOT NULL, provider_turn_id TEXT, status TEXT NOT NULL, payload_json TEXT NOT NULL)")
TURNS_TABLE = (
    "CREATE TABLE orchestration_v2_projection_provider_turns (provider_turn_id TEXT PRIMARY KEY, thread_id TEXT NOT "
    "NULL, provider_thread_id TEXT NOT NULL, node_id TEXT NOT NULL, run_attempt_id TEXT, ordinal INTEGER NOT NULL, "
    "status TEXT NOT NULL, started_at TEXT, completed_at TEXT, payload_json TEXT NOT NULL)")
REQUESTS_TABLE = (
    "CREATE TABLE orchestration_v2_projection_runtime_requests (runtime_request_id TEXT PRIMARY KEY, thread_id TEXT "
    "NOT NULL, node_id TEXT NOT NULL, provider_turn_id TEXT, kind TEXT NOT NULL, status TEXT NOT NULL, created_at "
    "TEXT NOT NULL, resolved_at TEXT, payload_json TEXT NOT NULL)")
TOKEN_TABLES = (RUNS_TABLE, ATTEMPTS_TABLE, TURNS_TABLE)


class StateDbOfATest:
    """The base of a test case that gives each test its own path for T3's state db. `root` is the case's temporary
    folder, and `id` is the test's."""
    root: Path

    @property
    def state(self) -> Path:
        """The fixture of T3's state db for this test, which does not exist until a test makes it."""
        return self.root / f"statev2-{self.id()}.sqlite"


def create(path: Path, tables: tuple[str, ...]) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        for table in tables:
            db.execute(table)


def add_run(path: Path, run: str, thread: str, model: str | None) -> None:
    """A run of the thread whose payload names the model in its `modelSelection`, as T3 encodes a run."""
    payload = {"id": run, "threadId": thread, "status": "completed"}
    if model is not None:
        payload["modelSelection"] = {"instanceId": "antigravity", "model": model}
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("INSERT INTO orchestration_v2_projection_runs VALUES (?, ?, 1, 'antigravity', NULL, 'completed', "
                   "'2026-11-22T10:00:00.000Z', '2026-11-22T10:01:30.000Z', ?)", (run, thread, json.dumps(payload)))


def add_run_in_status(path: Path, run: str, thread: str, ordinal: int, status: str) -> None:
    """The ordinal-th run of the thread, in the status T3 gives it. A run that is still going has no `completed_at`."""
    payload = {"id": run, "threadId": thread, "status": status}
    ended = None if status == "running" else "2026-11-22T10:01:30.000Z"
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("INSERT INTO orchestration_v2_projection_runs VALUES (?, ?, ?, 'antigravity', NULL, ?, "
                   "'2026-11-22T10:00:00.000Z', ?, ?)", (run, thread, ordinal, status, ended, json.dumps(payload)))


def add_request(path: Path, request: str, thread: str, status: str) -> None:
    """A runtime request of the thread, in the status T3 gives it, such as `pending` for one that waits for an answer."""
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("INSERT INTO orchestration_v2_projection_runtime_requests VALUES (?, ?, 'node-1', NULL, "
                   "'approval', ?, '2026-11-22T10:00:00.000Z', NULL, '{}')", (request, thread, status))


def add_next_run(path: Path, run: str, thread: str, model: str, status: str, attempt_status: str) -> None:
    """The thread's next run, in the status T3 gives it, whose payload names the model, with its one attempt, in the
    attempt status. A run that has completed has a `completed_at`."""
    with closing(sqlite3.connect(path)) as db:
        ordinal = db.execute("SELECT COUNT(*) FROM orchestration_v2_projection_runs WHERE thread_id = ?",
                             (thread,)).fetchone()[0] + 1
    payload = {"id": run, "modelSelection": {"instanceId": "antigravity", "model": model}}
    ended = "2026-11-22T10:01:30.000Z" if status == "completed" else None
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("INSERT INTO orchestration_v2_projection_runs VALUES (?, ?, ?, 'antigravity', NULL, ?, "
                   "'2026-11-22T10:00:00.000Z', ?, ?)", (run, thread, ordinal, status, ended, json.dumps(payload)))
    add_attempt_in_status(path, f"attempt-of-{run}", thread, run, attempt_status)


def add_attempt(path: Path, attempt: str, thread: str, run: str) -> None:
    add_attempt_in_status(path, attempt, thread, run, "completed")


def add_attempt_in_status(path: Path, attempt: str, thread: str, run: str, status: str) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("INSERT INTO orchestration_v2_projection_run_attempts VALUES (?, ?, ?, 1, 'node-1', 'antigravity', "
                   "'provider-thread-1', NULL, ?, '{}')", (attempt, thread, run, status))


def add_next_turn(path: Path, thread: str, run: str, token_usage: dict) -> None:
    """A provider turn of the thread that ran under the attempt of the run `add_next_run` made."""
    with closing(sqlite3.connect(path)) as db:
        count = db.execute("SELECT COUNT(*) FROM orchestration_v2_projection_provider_turns").fetchone()[0]
    add_turn(path, f"turn-{count + 1}", thread, f"attempt-of-{run}", token_usage)


def usage(input_tokens: int, cached: int, creation: int, output: int, reasoning: int) -> dict:
    """The `turnTokenUsage` of a completed provider turn. `inputTokens` counts the cached and cache-creation tokens
    too, and `outputTokens` counts the reasoning ones."""
    return {"usageStatus": "complete", "usageScope": "main_agent", "hasSubagents": False, "inputTokens": input_tokens,
            "cachedInputTokens": cached, "cacheCreationTokens": creation, "outputTokens": output,
            "reasoningTokens": reasoning}


def add_turn(path: Path, turn: str, thread: str, attempt: str | None, token_usage: dict | None) -> None:
    """A provider turn of the thread, run under the attempt, whose payload is the turn as T3 encodes it."""
    payload: dict = {"id": turn, "providerThreadId": "provider-thread-1", "nodeId": "node-1", "runAttemptId": attempt,
                     "ordinal": 1, "status": "completed"}
    if token_usage is not None:
        payload["turnTokenUsage"] = token_usage
    add_turn_payload(path, turn, thread, attempt, json.dumps(payload))


def add_turn_of_run(path: Path, thread: str, run: str, model: str | None, token_usage: dict | None) -> None:
    """A provider turn of the run, through the run's one attempt, adding the run and the attempt when they are new."""
    attempt = f"attempt-of-{run}"
    with closing(sqlite3.connect(path)) as db:
        known = db.execute("SELECT COUNT(*) FROM orchestration_v2_projection_runs WHERE run_id = ?",
                           (run,)).fetchone()[0]
        turns = db.execute("SELECT COUNT(*) FROM orchestration_v2_projection_provider_turns").fetchone()[0]
    if not known:
        add_run(path, run, thread, model)
        add_attempt(path, attempt, thread, run)
    add_turn(path, f"turn-{turns + 1}", thread, attempt, token_usage)


def add_child_turn(path: Path, thread: str, run: str, model: str | None, token_usage: dict | None,
                   requested_at: str) -> None:
    """A provider turn of a child thread whose run was requested at the ISO 8601 time, as T3 writes it for a child
    that began after a script recorded its start."""
    add_turn_of_run(path, thread, run, model, token_usage)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE orchestration_v2_projection_runs SET requested_at = ? WHERE run_id = ?",
                   (requested_at, run))


def add_turn_payload(path: Path, turn: str, thread: str, attempt: str | None, payload_json: str) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        ordinal = db.execute("SELECT COUNT(*) FROM orchestration_v2_projection_provider_turns").fetchone()[0] + 1
        db.execute("INSERT INTO orchestration_v2_projection_provider_turns VALUES (?, ?, 'provider-thread-1', "
                   "'node-1', ?, ?, 'completed', NULL, NULL, ?)", (turn, thread, attempt, ordinal, payload_json))
