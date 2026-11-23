import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import t3_state  # noqa: E402
from t3_state import usage  # noqa: E402
from test_scheduler import PLUGIN  # noqa: E402

sys.path.insert(0, str(PLUGIN / "scripts"))
import t3_thread  # noqa: E402

THREAD = "thread-of-the-session"
CHILD = "thread-of-a-lap"
NATIVE = "native-conversation-1"
NEON = "gemini-4-neon"


def step(kind: str, index: int, **fields) -> str:
    return json.dumps({"type": kind, "step_index": index, **fields})


class ThreadReaderCase(unittest.TestCase):
    """A fake T3 userdata folder with a fixture `statev2.sqlite`, which `$JIDOKA_T3_STATE_DB` names, and the profile
    folder where Antigravity keeps a conversation's transcript."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.userdata = Path(folder.name).resolve() / "userdata"
        self.userdata.mkdir()
        self.state = self.userdata / "statev2.sqlite"
        patched = mock.patch.dict(os.environ, {t3_thread.t3_turns.STATE_VARIABLE: str(self.state)})
        patched.start()
        self.addCleanup(patched.stop)
        t3_state.create(self.state, t3_state.THREAD_TABLES)
        t3_state.add_thread(self.state, THREAD, "Plan the epic", None)

    def brain(self, native: str) -> Path:
        folder = self.userdata / "providers" / "antigravity" / "profile-a" / "antigravity-acp" / "brain" / native
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def write_transcript(self, native: str, lines: list[str]) -> Path:
        logs = self.brain(native) / ".system_generated" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        path = logs / "transcript_full.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def kinds(self, reading: t3_thread.ThreadReading) -> list[str]:
        return [item.kind for item in reading.items]


class ThreadsItemsTests(ThreadReaderCase):
    def test_the_items_of_a_thread_come_back_in_the_order_of_their_ordinals(self):
        t3_state.add_item(self.state, THREAD, "run-1", 2, "assistant_message", {"text": "Done."})
        t3_state.add_item(self.state, THREAD, "run-1", 1, "user_message", {"text": "Plan it."})
        t3_state.add_item(self.state, "another-thread", "run-9", 1, "user_message", {"text": "Not mine."})

        reading = t3_thread.read_thread(THREAD)

        self.assertEqual(["user_message", "assistant_message"], self.kinds(reading))
        self.assertEqual(["Plan it.", "Done."], [item.text for item in reading.items])
        self.assertEqual("Plan the epic", reading.title)

    def test_a_command_a_dynamic_tool_and_an_error_say_what_they_ran_and_how_they_ended(self):
        t3_state.add_item(self.state, THREAD, "run-1", 1, "command_execution",
                          {"input": "git status", "output": "clean", "exitCode": 0})
        t3_state.add_item(self.state, THREAD, "run-1", 2, "command_execution",
                          {"input": "make", "output": "boom", "exitCode": 2})
        t3_state.add_item(self.state, THREAD, "run-1", 3, "dynamic_tool",
                          {"toolName": "view_file", "input": {"path": "a.py"}, "output": "text"})
        t3_state.add_item(self.state, THREAD, "run-1", 4, "error", {"failure": {"message": "quota exhausted"}})

        ran, failed, tool, error = t3_thread.read_thread(THREAD).items

        self.assertEqual(("command_execution", "git status", "clean", None),
                         (ran.tool, ran.arguments, ran.result, ran.error))
        self.assertEqual("exit code 2", failed.error)
        self.assertEqual(("view_file", '{"path": "a.py"}', "text"), (tool.tool, tool.arguments, tool.result))
        self.assertEqual("quota exhausted", error.error)

    def test_a_thread_with_no_item_has_none(self):
        self.assertEqual([], list(t3_thread.read_thread(THREAD).items))


class ThreadsRunsAndChildrenTests(ThreadReaderCase):
    def test_each_run_has_its_model_and_the_tokens_of_its_turns(self):
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", NEON, usage(10_000, 6_000, 0, 500, 0))
        t3_state.add_turn_of_run(self.state, THREAD, "run-1", NEON, usage(20_000, 15_000, 0, 700, 0))
        t3_state.add_run_in_status(self.state, "run-2", THREAD, 2, "failed")

        first, second = t3_thread.read_thread(THREAD).runs

        self.assertEqual(("run-1", "completed", NEON), (first.run, first.status, first.model))
        self.assertEqual((9_000, 1_200, 21_000, 0),
                         (first.tokens.input, first.tokens.output, first.tokens.cache_read, first.tokens.cache_write))
        self.assertEqual(("run-2", "failed", None, None), (second.run, second.status, second.model, second.tokens))

    def test_the_child_threads_are_the_threads_whose_lineage_names_it_as_their_parent(self):
        t3_state.add_thread(self.state, CHILD, "lap · tracer-1.1 build", THREAD)
        t3_state.add_thread(self.state, "a-stranger", "lap · elsewhere", "another-parent")
        t3_state.add_thread(self.state, "a-root", "Another session", None)

        [child] = t3_thread.read_thread(THREAD).children

        self.assertEqual((CHILD, "lap · tracer-1.1 build", "subagent"), (child.thread, child.title, child.relationship))


    def test_a_worker_thread_with_no_lineage_is_a_child_when_it_began_in_the_same_project_after_the_thread(self):
        t3_state.add_thread_made_at(self.state, CHILD, "lap · Build the greeting", None, "project-1",
                                    "2026-11-22T09:30:00.000Z")

        [child] = t3_thread.read_thread(THREAD).children

        self.assertEqual((CHILD, "lap · Build the greeting", t3_thread.UNVERIFIED_RELATIONSHIP),
                         (child.thread, child.title, child.relationship))

    def launch_item(self, session: str, ordinal: int, worker: str, updated_at: str) -> None:
        t3_state.add_item_updated_at(self.state, session, "run-1", ordinal, "command_execution",
                                     {"input": "factory.py start", "output": json.dumps({"thread": worker}),
                                      "exitCode": 0}, updated_at)

    def test_a_worker_thread_that_the_items_of_the_thread_name_is_a_launched_child_whenever_it_began(self):
        t3_state.add_thread_made_at(self.state, "next-session", "Plan another epic", None, "project-1",
                                    "2026-11-22T10:00:00.000Z")
        t3_state.add_thread_made_at(self.state, CHILD, "lap · Build the greeting", None, "project-1",
                                    "2026-11-22T10:30:00.000Z")
        self.launch_item(THREAD, 1, CHILD, "2026-11-22T10:30:05.000Z")

        [child] = t3_thread.read_thread(THREAD).children

        self.assertEqual((CHILD, t3_thread.LAUNCHED_RELATIONSHIP), (child.thread, child.relationship))
        self.assertEqual((), t3_thread.read_thread("next-session").children)

    def test_a_worker_thread_that_the_items_of_another_session_name_is_not_a_child_of_this_one(self):
        t3_state.add_thread_made_at(self.state, "other-manager", "Plan another epic", None, "project-1",
                                    "2026-11-22T09:10:00.000Z")
        t3_state.add_thread_made_at(self.state, CHILD, "lap · Build the greeting", None, "project-1",
                                    "2026-11-22T09:05:00.000Z")
        self.launch_item("other-manager", 1, CHILD, "2026-11-22T09:05:05.000Z")

        self.assertEqual((), t3_thread.read_thread(THREAD).children)
        [owned] = t3_thread.read_thread("other-manager").children
        self.assertEqual((CHILD, t3_thread.LAUNCHED_RELATIONSHIP), (owned.thread, owned.relationship))

    def test_a_session_that_only_reads_a_worker_thread_after_its_launch_does_not_own_it(self):
        t3_state.add_thread_made_at(self.state, "retro-session", "Retro", None, "project-1",
                                    "2026-11-22T11:00:00.000Z")
        t3_state.add_thread_made_at(self.state, CHILD, "lap · Build the greeting", None, "project-1",
                                    "2026-11-22T09:30:00.000Z")
        self.launch_item(THREAD, 1, CHILD, "2026-11-22T09:30:05.000Z")
        self.launch_item("retro-session", 1, CHILD, "2026-11-22T11:05:00.000Z")

        self.assertEqual([CHILD], [child.thread for child in t3_thread.read_thread(THREAD).children])
        self.assertEqual((), t3_thread.read_thread("retro-session").children)

    def test_a_session_whose_items_only_mention_a_worker_thread_has_not_launched_it_and_finds_it_unverified(self):
        t3_state.add_thread_made_at(self.state, "retro-session", "Retro", None, "project-1",
                                    "2026-11-22T09:20:00.000Z")
        t3_state.add_thread_made_at(self.state, CHILD, "lap · Build the greeting", None, "project-1",
                                    "2026-11-22T09:30:00.000Z")
        t3_state.add_item_updated_at(self.state, "retro-session", "run-1", 1, "assistant_message",
                                     {"text": f"the worker {CHILD} built it"}, "2026-11-22T09:31:00.000Z")

        [child] = t3_thread.read_thread("retro-session").children

        self.assertEqual((CHILD, t3_thread.UNVERIFIED_RELATIONSHIP), (child.thread, child.relationship))

    def test_a_worker_thread_that_began_after_the_next_session_of_the_project_is_not_a_child(self):
        t3_state.add_thread_made_at(self.state, CHILD, "lap · Build the greeting", None, "project-1",
                                    "2026-11-22T09:30:00.000Z")
        t3_state.add_thread_made_at(self.state, "next-session", "Plan another epic", None, "project-1",
                                    "2026-11-22T10:00:00.000Z")
        t3_state.add_thread_made_at(self.state, "later-lap", "lap · Check the greeting", None, "project-1",
                                    "2026-11-22T10:30:00.000Z")
        t3_state.add_thread_made_at(self.state, "other-project-session", "Elsewhere", None, "project-2",
                                    "2026-11-22T09:10:00.000Z")

        self.assertEqual([CHILD], [child.thread for child in t3_thread.read_thread(THREAD).children])
        self.assertEqual(["later-lap"], [child.thread for child in t3_thread.read_thread("next-session").children])

    def test_a_thread_that_is_not_a_lap_of_this_session_is_not_a_child(self):
        t3_state.add_thread_made_at(self.state, "other-project", "lap · Elsewhere", None, "project-2",
                                    "2026-11-22T09:30:00.000Z")
        t3_state.add_thread_made_at(self.state, "earlier", "lap · Before the session", None, "project-1",
                                    "2026-11-22T08:30:00.000Z")
        t3_state.add_thread_made_at(self.state, "not-a-lap", "Another session", None, "project-1",
                                    "2026-11-22T09:30:00.000Z")
        t3_state.add_thread_made_at(self.state, "named-for-someone", "lap · Of another session", "another-parent",
                                    "project-1", "2026-11-22T09:30:00.000Z")

        self.assertEqual((), t3_thread.read_thread(THREAD).children)

    def test_a_lap_thread_whose_lineage_names_the_thread_is_listed_once_as_its_subagent(self):
        t3_state.add_thread_made_at(self.state, CHILD, "lap · Build the greeting", THREAD, "project-1",
                                    "2026-11-22T09:30:00.000Z")

        [child] = t3_thread.read_thread(THREAD).children

        self.assertEqual("subagent", child.relationship)

    def test_the_reading_of_a_lap_thread_lists_no_other_lap_as_its_child(self):
        t3_state.add_thread_made_at(self.state, CHILD, "lap · Build the greeting", None, "project-1",
                                    "2026-11-22T09:30:00.000Z")
        t3_state.add_thread_made_at(self.state, "later-lap", "lap · Check the greeting", None, "project-1",
                                    "2026-11-22T09:45:00.000Z")

        self.assertEqual((), t3_thread.read_thread(CHILD).children)


class AntigravityTranscriptTests(ThreadReaderCase):
    def setUp(self):
        super().setUp()
        t3_state.add_provider_thread(self.state, THREAD, "antigravity", NATIVE)
        t3_state.add_item(self.state, THREAD, "run-1", 1, "user_message", {"text": "Look around."})
        t3_state.add_item(self.state, THREAD, "run-1", 2, "dynamic_tool", {"toolName": "tool", "input": {}})
        t3_state.add_item(self.state, THREAD, "run-1", 3, "assistant_message", {"text": "Found it."})
        t3_state.add_item(self.state, THREAD, "run-1", 4, "command_execution", {"input": "x", "output": "y"})

    def test_the_native_steps_give_each_tool_item_its_real_name_arguments_result_and_error(self):
        self.write_transcript(NATIVE, [
            step("USER_INPUT", 0, content="Look around."),
            step("PLANNER_RESPONSE", 1, content="", tool_calls=[{"name": "view_file", "args": {"AbsolutePath": "/a"}}]),
            step("VIEW_FILE", 2, content="file text"),
            step("PLANNER_RESPONSE", 3, content="Found it.", tool_calls=[{"name": "run_command",
                                                                         "args": {"CommandLine": "ls"}}]),
            step("RUN_COMMAND", 4, content="", error="permission denied"),
        ])

        reading = t3_thread.read_thread(THREAD)

        viewed, ran = (item for item in reading.items if item.tool is not None)
        self.assertEqual(("view_file", '{"AbsolutePath": "/a"}', "file text", None),
                         (viewed.tool, viewed.arguments, viewed.result, viewed.error))
        self.assertEqual(("run_command", '{"CommandLine": "ls"}', "permission denied"),
                         (ran.tool, ran.arguments, ran.error))
        self.assertEqual([], list(reading.notes))

    def test_a_native_step_the_db_has_no_item_for_is_added_after_the_items(self):
        self.write_transcript(NATIVE, [
            step("PLANNER_RESPONSE", 1, content="", tool_calls=[
                {"name": "read_file", "args": {}}, {"name": "run_command", "args": {}},
                {"name": "manage_task", "args": {}}]),
            step("READ_FILE", 2, content="first"), step("RUN_COMMAND", 3, content="second"),
            step("MANAGE_TASK", 4, content="third"),
        ])

        reading = t3_thread.read_thread(THREAD)

        self.assertEqual(["read_file", "run_command", "manage_task"],
                         [item.tool for item in reading.items if item.tool is not None])
        self.assertEqual("native_step", reading.items[-1].kind)
        self.assertEqual(5, len(reading.items))

    def test_a_native_only_step_before_a_projected_command_does_not_overwrite_the_command(self):
        t3_state.add_item(self.state, "command-thread", None, 1, "command_execution", {"input": "git status"})
        t3_state.add_thread(self.state, "command-thread", "Commands", None)
        t3_state.add_provider_thread(self.state, "command-thread", "antigravity", "native-command")
        self.write_transcript("native-command", [
            step("PLANNER_RESPONSE", 1, content="", tool_calls=[
                {"name": "read_file", "args": {"Path": "/a"}},
                {"name": "run_command", "args": {"CommandLine": "git status"}}]),
            step("READ_FILE", 2, content="file text"), step("RUN_COMMAND", 3, content="clean"),
        ])

        reading = t3_thread.read_thread("command-thread")

        ran, read = reading.items
        self.assertEqual(("command_execution", "run_command", '{"CommandLine": "git status"}', "clean"),
                         (ran.kind, ran.tool, ran.arguments, ran.result))
        self.assertEqual(("native_step", "read_file", "file text"), (read.kind, read.tool, read.result))

    def test_a_transcript_whose_tool_calls_is_not_a_list_falls_back_to_the_db(self):
        self.write_transcript(NATIVE, [step("PLANNER_RESPONSE", 1, content="", tool_calls=42)])

        reading = t3_thread.read_thread(THREAD)

        self.assertEqual(4, len(reading.items))
        [note] = reading.notes
        self.assertIn("cannot be parsed", note)
        self.assertIn("tool_calls", note)

    def test_the_tokens_of_a_planner_response_belong_to_the_first_tool_call_it_made(self):
        self.write_transcript(NATIVE, [
            step("PLANNER_RESPONSE", 1, content="", input_tokens=900, output_tokens=40, cache_read_tokens=300,
                 tool_calls=[{"name": "read_file", "args": {}}, {"name": "run_command", "args": {}}]),
            step("READ_FILE", 2, content="text"), step("RUN_COMMAND", 3, content="ok"),
        ])

        viewed, ran = (item for item in t3_thread.read_thread(THREAD).items if item.tool is not None)

        self.assertEqual((900, 40, 300, 0), (viewed.tokens.input, viewed.tokens.output, viewed.tokens.cache_read,
                                             viewed.tokens.cache_write))
        self.assertIsNone(ran.tokens)

    def test_a_step_carries_no_tokens_when_its_planner_response_has_none(self):
        self.write_transcript(NATIVE, [
            step("PLANNER_RESPONSE", 1, content="", tool_calls=[{"name": "read_file", "args": {}}]),
            step("READ_FILE", 2, content="text"),
        ])

        [viewed] = (item for item in t3_thread.read_thread(THREAD).items if item.tool == "read_file")

        self.assertIsNone(viewed.tokens)

    def test_an_item_carries_the_time_t3_last_updated_it(self):
        t3_state.add_item(self.state, "timed-thread", "run-1", 1, "user_message", {"text": "Plan it."})
        t3_state.add_thread(self.state, "timed-thread", "Timed", None)

        [item] = t3_thread.read_thread("timed-thread").items

        self.assertEqual("2026-11-22T10:00:00.000Z", item.updated_at)

    def test_a_missing_transcript_falls_back_to_the_db_with_a_line_that_names_what_is_missing(self):
        reading = t3_thread.read_thread(THREAD)

        self.assertEqual(4, len(reading.items))
        [note] = reading.notes
        self.assertIn("transcript_full.jsonl", note)
        self.assertIn(NATIVE, note)
        self.assertIn("missing", note)

    def test_a_transcript_that_is_not_json_is_treated_as_missing_with_a_line_that_says_so(self):
        path = self.write_transcript(NATIVE, [step("USER_INPUT", 0, content="Hi"), "{not json"])

        reading = t3_thread.read_thread(THREAD)

        self.assertEqual(4, len(reading.items))
        [note] = reading.notes
        self.assertIn(str(path), note)
        self.assertIn("cannot be parsed", note)
        self.assertIn("line 2", note)

    def test_a_transcript_with_no_step_is_treated_as_unparseable(self):
        self.write_transcript(NATIVE, [""])

        [note] = t3_thread.read_thread(THREAD).notes

        self.assertIn("cannot be parsed", note)

    def test_a_provider_thread_that_names_no_native_id_falls_back_with_a_line(self):
        other = "thread-with-no-native-id"
        t3_state.add_thread(self.state, other, "Odd", None)
        t3_state.add_provider_thread(self.state, other, "antigravity", None)

        [note] = t3_thread.read_thread(other).notes

        self.assertIn("names no native id", note)

    def test_a_thread_of_another_provider_reads_no_transcript(self):
        other = "thread-of-claude"
        t3_state.add_thread(self.state, other, "Claude", None)
        t3_state.add_provider_thread(self.state, other, "claudeAgent", "native-claude")

        self.assertEqual([], list(t3_thread.read_thread(other).notes))


class UnreadableStateTests(ThreadReaderCase):
    def test_a_thread_the_db_holds_no_row_for_raises_with_its_id(self):
        with self.assertRaises(t3_thread.NoThread) as raised:
            t3_thread.read_thread("no-such-thread")

        self.assertIn("no-such-thread", str(raised.exception))

    def test_a_db_without_the_tables_raises_with_the_table_it_lacks(self):
        self.state.unlink()
        t3_state.create(self.state, (t3_state.RUNS_TABLE,))

        with self.assertRaises(t3_thread.NoThread) as raised:
            t3_thread.read_thread(THREAD)

        self.assertIn("orchestration_v2_projection_threads", str(raised.exception))

    def test_a_missing_db_raises_with_its_path(self):
        self.state.unlink()

        with self.assertRaises(t3_thread.NoThread) as raised:
            t3_thread.read_thread(THREAD)

        self.assertIn(str(self.state), str(raised.exception))


if __name__ == "__main__":
    unittest.main()
