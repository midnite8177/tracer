"""The one reader of a T3 thread as a record of a session: its items in order, its runs with their model and tokens, and
its child threads.

It reads the `orchestration_v2_projection_*` tables of T3's state db and no event table, because T3 compacts those or
leaves them empty. It opens the db through t3_turns.select, the one place that knows how the db is opened and what a
missing table or column raises, and it sums tokens with t3_turns.thread_turns, so the ledger and this reader never
disagree about a turn. $JIDOKA_T3_STATE_DB names the db, as t3_turns reads it.

The items of a thread are the rows of `orchestration_v2_projection_turn_items`, ordered by `ordinal`, each with the
`type` T3 gives it and its payload. A thread's child threads are the threads of `orchestration_v2_projection_threads`
whose payload `lineage.parentThreadId` names it. ADR 0012 has the manager launch each worker as a top-level thread, so
T3 may give a worker thread no lineage. The reader therefore also lists, as a child, each thread with no parent whose
title starts with `lap · ` (t3_worker.TITLE_PREFIX) and that is in the same project as the read thread. T3's projection
keeps no field that names the manager that launched a thread, but a manager's launch prints the id of the thread it
made, so the session whose items name a worker thread first is the manager that launched it. The worker thread is a
child of that session whenever it began, and of no other. A worker thread that no session of the project names is
listed, marked as unverified, as a child of the read thread when it was created at or after it and before the next
session of the project, which is the next thread with no parent and no such title that was created after it. The
workers of a lap and the workers of the accept skill share that title. A thread that is itself a worker lists no such
child.

An Antigravity thread keeps the real record of its steps in Antigravity's own transcript. The thread's provider thread,
a row of `orchestration_v2_projection_provider_threads` whose `provider` is `antigravity`, holds in the payload a
`nativeThreadRef` whose `nativeId` names the conversation. Antigravity writes its steps to
`<T3 userdata>/providers/antigravity/<profile>/antigravity-acp/brain/<nativeId>/**/transcript_full.jsonl`, one JSON record
for each line: a `PLANNER_RESPONSE` record holds the `tool_calls` the model made, each with a `name` and `args`, and the
`input_tokens`, `output_tokens` and `cache_read_tokens` of the model call that made them. The next records that are not a
user input, a planner response or a conversation history hold the results in their `content`, an `error` when the step
failed. A transcript carries no call id, so a result belongs to the oldest call without one. The reader merges those
steps, in order, into the thread's tool items: a command, a dynamic tool, a file change or a search. A step goes to the
next tool item of a kind it can answer, so a step that T3 projects no item for, such as a file read before a projected
command, is passed over, and each step that no item took comes after the items, as an item of kind `native_step`. The
tokens of a model call belong to the first tool call it made, so the items carry the per-step tokens that the db's run
totals leave out.

A transcript that is missing, or that cannot be parsed, is not an error. The reader reports from the db and adds a line to
the reading's notes that says what is missing, worded for the person who reads the report.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import reduce
from pathlib import Path

import t3_profiles
import t3_turns
import t3_worker
from prices import Tokens, count_of
from t3_turns import json_object, model_of, reported_as, select

THREADS_TABLE = "orchestration_v2_projection_threads"
THREAD_ID_COLUMN = "thread_id"
THREAD_TITLE_COLUMN = "title"
THREAD_PROJECT_COLUMN = "project_id"
THREAD_CREATED_COLUMN = "created_at"
THREAD_PAYLOAD_COLUMN = "payload_json"
LINEAGE_KEY = "lineage"
PARENT_KEY = "parentThreadId"
RELATIONSHIP_KEY = "relationshipToParent"
LAUNCHED_RELATIONSHIP = "worker thread, launched by this thread"
UNVERIFIED_RELATIONSHIP = "worker thread, found by its title and not confirmed as launched by this thread"
ITEMS_TABLE = "orchestration_v2_projection_turn_items"
ITEM_THREAD_COLUMN = "thread_id"
ITEM_RUN_COLUMN = "run_id"
ITEM_ORDINAL_COLUMN = "ordinal"
ITEM_TYPE_COLUMN = "type"
ITEM_STATUS_COLUMN = "status"
ITEM_UPDATED_COLUMN = "updated_at"
ITEM_PAYLOAD_COLUMN = "payload_json"
PROVIDER_THREADS_TABLE = "orchestration_v2_projection_provider_threads"
PROVIDER_THREAD_THREAD_COLUMN = "thread_id"
PROVIDER_COLUMN = "provider"
PROVIDER_PAYLOAD_COLUMN = "payload_json"
NATIVE_REF_KEY = "nativeThreadRef"
NATIVE_ID_KEY = "nativeId"
ANTIGRAVITY_PROVIDER = "antigravity"
BRAIN_FOLDER = Path("antigravity-acp") / "brain"
TRANSCRIPT_FILE = "transcript_full.jsonl"

TEXT_KEY = "text"
PROMPT_KEY = "prompt"
INPUT_KEY = "input"
OUTPUT_KEY = "output"
EXIT_CODE_KEY = "exitCode"
FAILURE_KEY = "failure"
MESSAGE_KEY = "message"
TOOL_NAME_KEY = "toolName"
FILE_NAME_KEY = "fileName"
QUERY_KEY = "query"
COMMAND_KIND = "command_execution"
DYNAMIC_TOOL_KIND = "dynamic_tool"
FILE_CHANGE_KIND = "file_change"
FILE_SEARCH_KIND = "file_search"
WEB_SEARCH_KIND = "web_search"
ERROR_KIND = "error"
TOOL_KINDS = (COMMAND_KIND, DYNAMIC_TOOL_KIND, FILE_CHANGE_KIND, FILE_SEARCH_KIND, WEB_SEARCH_KIND)
NATIVE_STEP_KIND = "native_step"

RECORD_TYPE_KEY = "type"
PLANNER_RESPONSE = "PLANNER_RESPONSE"
RECORDS_WITHOUT_A_RESULT = ("USER_INPUT", PLANNER_RESPONSE, "CONVERSATION_HISTORY")
TOOL_CALLS_KEY = "tool_calls"
CALL_NAME_KEY = "name"
CALL_ARGUMENTS_KEY = "args"
RECORD_CONTENT_KEY = "content"
RECORD_ERROR_KEY = "error"
RECORD_STEP_KEY = "step_index"
RECORD_INPUT_TOKENS_KEY = "input_tokens"
RECORD_OUTPUT_TOKENS_KEY = "output_tokens"
RECORD_CACHE_READ_TOKENS_KEY = "cache_read_tokens"
STEP_KINDS = {"run_command": COMMAND_KIND, "write_file": FILE_CHANGE_KIND, "edit_file": FILE_CHANGE_KIND}
"""The item kind that T3 projects a native tool call as, for the tools whose item has a kind of its own. Any other
tool is projected as a dynamic tool."""


class NoThread(Exception):
    """T3's state db gave no reading of the thread, with the reason worded for the person who reads stderr."""


class TranscriptUnreadable(Exception):
    """Antigravity's transcript could not be parsed, with the reason worded for the person who reads the report."""


@dataclass(frozen=True)
class ThreadItem:
    """One item of a thread: its `type` as `kind`, the run it belongs to, the time T3 last updated it and what its payload
    says. A tool item has a `tool`, its `arguments` and, once it ended, its `result` or its `error`, and it has `tokens`
    when its native step carried them; a message has its `text`. Each is None when the item has none."""
    ordinal: int
    kind: str
    status: str
    run: str | None
    updated_at: str | None
    text: str | None
    tool: str | None
    arguments: str | None
    result: str | None
    error: str | None
    tokens: Tokens | None


@dataclass(frozen=True)
class ThreadRun:
    """A run of a thread: its status, the model its `modelSelection` names, and the tokens of its turns. The model is
    None when the selection names none, and the tokens are None when no turn of the run carries any."""
    run: str
    status: str
    model: str | None
    tokens: Tokens | None


@dataclass(frozen=True)
class ChildThread:
    """A thread of the read thread's session and how it relates to it: a thread whose lineage names the read thread as
    its parent, with the relationship the lineage gives, or a worker thread that T3 gave no lineage, with
    LAUNCHED_RELATIONSHIP when the read thread's own items name it and UNVERIFIED_RELATIONSHIP when only its title, its
    project and its creation time tie it to the read thread."""
    thread: str
    title: str
    relationship: str | None


@dataclass(frozen=True)
class ThreadReading:
    """A thread as a record of a session. `notes` holds a line for each source the reader fell back from."""
    thread: str
    title: str
    items: tuple[ThreadItem, ...]
    runs: tuple[ThreadRun, ...]
    children: tuple[ChildThread, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class NativeStep:
    """A tool call of Antigravity's transcript with what came of it, and the tokens of the model call that made it when
    it was the first call of that response and the response carried any."""
    tool: str
    arguments: str | None
    result: str | None
    error: str | None
    tokens: Tokens | None


def text_of(value: object) -> str | None:
    """The value as text: a string as it is, nothing as None, and any other JSON value as JSON."""
    if value is None:
        return None
    return value if isinstance(value, str) else json.dumps(value)


def failure_text_of(failure: object) -> str | None:
    """The message of a provider failure, or the failure itself as text when it names no message."""
    message = failure.get(MESSAGE_KEY) if isinstance(failure, dict) else None
    return message if isinstance(message, str) and message else text_of(failure)


def item_of(ordinal: object, kind: object, status: object, run: object, updated_at: object,
            payload_json: object) -> ThreadItem:
    payload = json_object(payload_json)
    kind = str(kind)
    text = text_of(payload.get(TEXT_KEY) if kind != "subagent" else payload.get(PROMPT_KEY))
    tool = arguments = result = error = None
    if kind == COMMAND_KIND:
        exit_code = payload.get(EXIT_CODE_KEY)
        tool, arguments, result = COMMAND_KIND, text_of(payload.get(INPUT_KEY)), text_of(payload.get(OUTPUT_KEY))
        error = f"exit code {exit_code}" if isinstance(exit_code, int) and exit_code != 0 else None
    elif kind == DYNAMIC_TOOL_KIND:
        tool = text_of(payload.get(TOOL_NAME_KEY)) or DYNAMIC_TOOL_KIND
        arguments, result = text_of(payload.get(INPUT_KEY)), text_of(payload.get(OUTPUT_KEY))
    elif kind == FILE_CHANGE_KIND:
        tool, arguments = FILE_CHANGE_KIND, text_of(payload.get(FILE_NAME_KEY))
    elif kind in (FILE_SEARCH_KIND, WEB_SEARCH_KIND):
        tool, arguments = kind, text_of(payload.get(QUERY_KEY))
    elif kind == ERROR_KIND:
        error = failure_text_of(payload.get(FAILURE_KEY))
    return ThreadItem(int(ordinal) if isinstance(ordinal, int) else 0, kind, str(status),
                      str(run) if run is not None else None, str(updated_at) if updated_at is not None else None,
                      text, tool, arguments, result, error, None)


def read_items(thread: str) -> list[ThreadItem]:
    with reported_as(NoThread):
        rows = select(ITEMS_TABLE, (ITEM_ORDINAL_COLUMN, ITEM_TYPE_COLUMN, ITEM_STATUS_COLUMN, ITEM_RUN_COLUMN,
                                    ITEM_UPDATED_COLUMN, ITEM_PAYLOAD_COLUMN), {ITEM_THREAD_COLUMN: thread},
                      (ITEM_ORDINAL_COLUMN,))
    return [item_of(*row) for row in rows]


def read_runs(thread: str) -> list[ThreadRun]:
    with reported_as(NoThread):
        rows = select(t3_turns.RUNS_TABLE, (t3_turns.RUN_ID_COLUMN, t3_turns.RUN_STATUS_COLUMN,
                                            t3_turns.RUN_PAYLOAD_COLUMN), {t3_turns.RUN_THREAD_COLUMN: thread},
                      (t3_turns.RUN_ORDINAL_COLUMN,))
    try:
        turns = t3_turns.thread_turns(thread)
    except t3_turns.NoTurns as error:
        raise NoThread(str(error)) from error
    runs = []
    for run, status, payload in rows:
        tokens = [turn.tokens for turn in turns if turn.run == str(run) and turn.tokens is not None]
        runs.append(ThreadRun(str(run), str(status), model_of(payload),
                              reduce(Tokens.plus, tokens) if tokens else None))
    return runs


@dataclass(frozen=True)
class ThreadRow:
    """A row of the threads table: the id, title, project and creation time, and the payload, which is where `lineage`
    lives."""
    thread: str
    title: str
    project: str
    created: str
    payload: dict


def read_threads() -> list[ThreadRow]:
    """Every thread, in the order T3 wrote them."""
    with reported_as(NoThread):
        rows = select(THREADS_TABLE, (THREAD_ID_COLUMN, THREAD_TITLE_COLUMN, THREAD_PROJECT_COLUMN,
                                      THREAD_CREATED_COLUMN, THREAD_PAYLOAD_COLUMN), {}, ())
    return [ThreadRow(str(thread), str(title), str(project), str(created), json_object(payload))
            for thread, title, project, created, payload in rows]


def parent_of(row: ThreadRow) -> object:
    """The `lineage.parentThreadId` of the row's payload, or None when it names none."""
    lineage = row.payload.get(LINEAGE_KEY)
    return lineage.get(PARENT_KEY) if isinstance(lineage, dict) else None


def is_worker_thread(row: ThreadRow) -> bool:
    """Whether the row's title is the `lap · ` one that every worker thread of a manager gets."""
    return row.title.startswith(t3_worker.TITLE_PREFIX)


def next_session_began(session: ThreadRow, threads: list[ThreadRow]) -> datetime | None:
    """When the next session of the session's project began, or None when none did: the earliest thread of the project
    with no parent and no worker title that was created after the session. A worker thread that began after it was
    launched by that session or a later one, not by this."""
    session_began = t3_turns.began_at(session.created)
    if session_began is None:
        return None
    later = []
    for row in threads:
        began = t3_turns.began_at(row.created)
        if (row.project == session.project and not parent_of(row) and not is_worker_thread(row)
                and began is not None and began > session_began):
            later.append(began)
    return min(later, default=None)


def is_unowned_worker_in(row: ThreadRow, project: str) -> bool:
    """Whether the row is a worker thread of the project that names no parent. ADR 0012 has the manager launch a worker
    as a top-level thread, so T3 may give it no `lineage.parentThreadId`, and the `lap · ` title the launch gives it is
    what marks it. A thread that names a parent of its own belongs to that parent."""
    return is_worker_thread(row) and not parent_of(row) and row.project == project


def is_worker_thread_of(row: ThreadRow, session: ThreadRow, ends: datetime | None) -> bool:
    """Whether the row is an unowned worker thread that began in the session's project at or after the session and
    before `ends`, the start of the next session, which is None when there is none. A worker thread's own session
    launches no worker."""
    began, session_began = t3_turns.began_at(row.created), t3_turns.began_at(session.created)
    return (not is_worker_thread(session) and is_unowned_worker_in(row, session.project)
            and began is not None and session_began is not None and began >= session_began
            and (ends is None or began < ends))


def launched_thread_of(kind: object, payload: object) -> str | None:
    """The thread that the item records the launch of, or None when the item is no launch result. A launch is a command
    or tool call whose output is a JSON object with the `thread` it made, as `factory.py start` prints it. An item
    that only holds the id, such as a later reader's, names no launch."""
    if kind not in (COMMAND_KIND, DYNAMIC_TOOL_KIND):
        return None
    printed = json_object(text_of(json_object(payload).get(OUTPUT_KEY)))
    named = printed.get("thread")
    return named if isinstance(named, str) else None


def first_launches(session: str, workers: list[str]) -> dict[str, datetime]:
    """For each of the worker thread ids whose launch an item of the session records, when T3 last updated the first
    such item."""
    launches: dict[str, datetime] = {}
    with reported_as(NoThread):
        rows = select(ITEMS_TABLE, (ITEM_TYPE_COLUMN, ITEM_PAYLOAD_COLUMN, ITEM_UPDATED_COLUMN),
                      {ITEM_THREAD_COLUMN: session}, ())
    for kind, payload, updated in rows:
        at = t3_turns.began_at(updated)
        launched = launched_thread_of(kind, payload)
        if at is not None and launched in workers and (launched not in launches or at < launches[launched]):
            launches[launched] = at
    return launches


def launchers_of(session: ThreadRow, threads: list[ThreadRow]) -> dict[str, str]:
    """For each worker thread of the session's project whose launch the items of some session of the project record,
    the session whose items record it first, which is the manager that launched it. A session that only reads the
    worker thread later, as a retro does, records no launch. A worker thread no session launched has no entry, and a
    worker thread's own session launched none."""
    workers = [row.thread for row in threads if is_unowned_worker_in(row, session.project)]
    if is_worker_thread(session) or not workers:
        return {}
    sessions = [row for row in threads if row.project == session.project and not is_worker_thread(row)
                and (row.thread == session.thread or not parent_of(row))]
    firsts: dict[str, tuple[datetime, str]] = {}
    for candidate in sessions:
        for worker, at in first_launches(candidate.thread, workers).items():
            if worker not in firsts or at < firsts[worker][0]:
                firsts[worker] = (at, candidate.thread)
    return {worker: launcher for worker, (_, launcher) in firsts.items()}


def children_of(session: ThreadRow, threads: list[ThreadRow]) -> list[ChildThread]:
    """The threads whose lineage names the session as their parent and, unless the session is itself a worker's thread,
    its worker threads. A worker thread whose launch the session's items record is one, whenever it began. A worker
    thread whose launch another session's items record is not. A worker thread whose launch no session records is one,
    marked as unverified, when it began in the session's project after the session and before the project's next
    session."""
    found = []
    launchers = launchers_of(session, threads)
    ends = next_session_began(session, threads)
    for row in threads:
        lineage = row.payload.get(LINEAGE_KEY)
        if isinstance(lineage, dict) and lineage.get(PARENT_KEY) == session.thread:
            relationship = lineage.get(RELATIONSHIP_KEY)
            found.append(ChildThread(row.thread, row.title, relationship if isinstance(relationship, str) else None))
        elif launchers.get(row.thread) == session.thread:
            found.append(ChildThread(row.thread, row.title, LAUNCHED_RELATIONSHIP))
        elif row.thread not in launchers and is_worker_thread_of(row, session, ends):
            found.append(ChildThread(row.thread, row.title, UNVERIFIED_RELATIONSHIP))
    return found


def native_id_of(thread: str) -> tuple[bool, str | None]:
    """Whether the thread runs on Antigravity, and the `nativeThreadRef.nativeId` of its latest Antigravity provider
    thread, None when that names none."""
    with reported_as(NoThread):
        rows = select(PROVIDER_THREADS_TABLE, (PROVIDER_COLUMN, PROVIDER_PAYLOAD_COLUMN),
                      {PROVIDER_THREAD_THREAD_COLUMN: thread}, ())
    native = [json_object(payload).get(NATIVE_REF_KEY) for provider, payload in rows
              if provider == ANTIGRAVITY_PROVIDER]
    if not native:
        return False, None
    ref = native[-1]
    named = ref.get(NATIVE_ID_KEY) if isinstance(ref, dict) else None
    return True, named if isinstance(named, str) and named else None


def transcript_of(native_id: str) -> Path | None:
    """The transcript of the conversation under the first Antigravity profile of T3's userdata that holds one, which is
    the folder the state db sits in. None when no profile does."""
    profiles = t3_profiles.profiles_folder()
    if not profiles.is_dir():
        return None
    for profile in sorted(profiles.iterdir()):
        conversation = profile / BRAIN_FOLDER / native_id
        if conversation.is_dir():
            for found in sorted(conversation.rglob(TRANSCRIPT_FILE)):
                return found
    return None


def records_of(transcript: Path) -> list[dict]:
    """The records of the transcript, one for each of its lines that holds one, in order. It raises TranscriptUnreadable
    when the file cannot be read, a line is not a JSON object, or the file holds no record."""
    try:
        lines = transcript.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise TranscriptUnreadable(f"{transcript} cannot be read: {error}") from error
    records = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as error:
            raise TranscriptUnreadable(f"line {number} of {transcript} is not JSON: {error}") from error
        if not isinstance(record, dict):
            raise TranscriptUnreadable(f"line {number} of {transcript} is not a JSON object")
        records.append(record)
    if not records:
        raise TranscriptUnreadable(f"{transcript} holds no record")
    return records


def tokens_of(record: dict) -> Tokens | None:
    """The tokens a planner response carries for its model call, or None when it carries none."""
    counts = [record.get(key) for key in (RECORD_INPUT_TOKENS_KEY, RECORD_OUTPUT_TOKENS_KEY,
                                          RECORD_CACHE_READ_TOKENS_KEY)]
    if all(count is None for count in counts):
        return None
    return Tokens(count_of(counts[0]), count_of(counts[1]), count_of(counts[2]), 0)


def calls_of(record: dict) -> list[NativeStep]:
    """The tool calls of a planner response, none of them answered yet, the first holding the response's tokens. It
    raises TranscriptUnreadable when the response's `tool_calls` is not a list."""
    calls = record.get(TOOL_CALLS_KEY)
    if calls is None:
        return []
    if not isinstance(calls, list):
        raise TranscriptUnreadable(f"the planner response at step {record.get(RECORD_STEP_KEY)} holds {TOOL_CALLS_KEY} "
                                   "that is not a list")
    found: list[NativeStep] = []
    for call in calls:
        if isinstance(call, dict):
            found.append(NativeStep(text_of(call.get(CALL_NAME_KEY)) or "", text_of(call.get(CALL_ARGUMENTS_KEY)), None,
                                    None, None if found else tokens_of(record)))
    return found


def steps_of(records: list[dict]) -> list[NativeStep]:
    """The tool calls of the records, each with the result and error of the step that answered it, in the order the
    calls were made. A call that nothing answered has neither. It raises TranscriptUnreadable when a planner response's
    `tool_calls` is not a list."""
    pending: list[NativeStep] = []
    steps: list[NativeStep] = []
    for record in records:
        kind = record.get(RECORD_TYPE_KEY)
        if kind == PLANNER_RESPONSE:
            pending.extend(calls_of(record))
        elif kind not in RECORDS_WITHOUT_A_RESULT and pending:
            call = pending.pop(0)
            steps.append(NativeStep(call.tool, call.arguments, text_of(record.get(RECORD_CONTENT_KEY)) or None,
                                    text_of(record.get(RECORD_ERROR_KEY)) or None, call.tokens))
    return [*steps, *pending]


def kind_of_step(step: NativeStep) -> str:
    """The kind of item T3 projects the step's tool as."""
    return STEP_KINDS.get(step.tool, DYNAMIC_TOOL_KIND)


def answers(item: ThreadItem, step: NativeStep) -> bool:
    """Whether the step can be the one that the tool item projects: a step of the kind the item has, or for a dynamic
    tool item a step of the same tool, since a dynamic item's tool is the one T3 names."""
    if item.kind == DYNAMIC_TOOL_KIND:
        return step.tool == item.tool or kind_of_step(step) == DYNAMIC_TOOL_KIND
    return kind_of_step(step) == item.kind


def with_step(item: ThreadItem, step: NativeStep) -> ThreadItem:
    return ThreadItem(item.ordinal, item.kind, item.status, item.run, item.updated_at, item.text, step.tool or item.tool,
                      step.arguments, step.result, step.error, step.tokens)


def merged(items: list[ThreadItem], steps: list[NativeStep]) -> list[ThreadItem]:
    """The items with each tool item given the tool, arguments, result, error and tokens of the next native step it
    answers for, and the steps no item took after them, as items of kind `native_step`. A step is taken in order, so a
    step passed over to reach the one an item answers for is not taken by a later item."""
    queue = list(steps)
    passed_over: list[NativeStep] = []
    found = []
    for item in items:
        if item.tool is not None:
            at = next((index for index, step in enumerate(queue) if answers(item, step)), None)
            if at is not None:
                passed_over.extend(queue[:at])
                item = with_step(item, queue[at])
                queue = queue[at + 1:]
        found.append(item)
    last = items[-1].ordinal if items else 0
    for offset, step in enumerate([*passed_over, *queue], 1):
        found.append(ThreadItem(last + offset, NATIVE_STEP_KIND, "", None, None, None, step.tool, step.arguments,
                                step.result, step.error, step.tokens))
    return found


def items_with_native_steps(thread: str, items: list[ThreadItem]) -> tuple[list[ThreadItem], list[str]]:
    """The items of an Antigravity thread merged with its transcript, or the db's items and the line that says why not
    when the thread has no native id, or no transcript can be found or parsed. Another provider's thread has no
    transcript to read."""
    try:
        antigravity, native_id = native_id_of(thread)
    except NoThread as error:
        return items, [f"no native transcript was read: {error}"]
    if not antigravity:
        return items, []
    where = f"the state db at {t3_turns.state_path()}"
    if native_id is None:
        return items, [f"the Antigravity provider thread of {thread} names no native id, so its {TRANSCRIPT_FILE} is "
                       f"missing; reporting from {where} alone"]
    transcript = transcript_of(native_id)
    if transcript is None:
        return items, [f"{TRANSCRIPT_FILE} of Antigravity conversation {native_id} is missing under "
                       f"{t3_profiles.profiles_folder()}; reporting from {where} alone"]
    try:
        return merged(items, steps_of(records_of(transcript))), []
    except TranscriptUnreadable as error:
        return items, [f"the transcript cannot be parsed: {error}; reporting from {where} alone"]


def read_thread(thread: str) -> ThreadReading:
    """The reading of the thread. It raises NoThread, whose reason names what was missing, when the db is missing or
    unreadable, lacks a table or column this reader knows, or holds no such thread."""
    threads = read_threads()
    own = [row for row in threads if row.thread == thread]
    if not own:
        raise NoThread(f"T3's state db at {t3_turns.state_path()} holds no thread {thread}")
    items, notes = items_with_native_steps(thread, read_items(thread))
    return ThreadReading(thread, own[0].title, tuple(items), tuple(read_runs(thread)),
                         tuple(children_of(own[0], threads)), tuple(notes))
