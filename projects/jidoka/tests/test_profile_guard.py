import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402
import lap_guard_record  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
GUARD = PLUGIN / "hooks" / "profile_guard.py"
CASES_MODULE_HEAD = "export const lapGuardCases = "
CASES = json.loads((PLUGIN / "hooks" / "lap_guard_cases.ts").read_text(encoding="utf-8")
                   .removeprefix(CASES_MODULE_HEAD))
TOOLS = {
    "write": {"name": "write_file", "field": "Path"},
    "edit": {"name": "edit_file", "field": "Path"},
    "edit_notebook": {"name": "notebook_edit", "field": "NotebookPath"},
    "read": {"name": "read_file", "field": "Path"},
    "start_workers": {"name": "invoke_subagent", "field": None},
    "define_workers": {"name": "define_subagent", "field": None},
    "ask": {"name": "ask_question", "field": None},
}
RUN_TIMEOUT_SECONDS = 120


def tool_of(case: dict) -> dict:
    """How the guard names and calls the tool of a shared case: `run_command` for a command, the tool the table names
    when it is one the guard has a name for, else a tool of that very name, which no rule knows."""
    if "use" not in case:
        return {"name": "run_command", "field": "CommandLine"}
    return TOOLS.get(case["use"]["tool"], {"name": case["use"]["tool"], "field": None})


def placed(text: str, places: dict) -> str:
    """The text of a shared case with its `{worktree}`, `{outside}` and `{tool}` filled in."""
    for name, value in places.items():
        text = text.replace("{" + name + "}", value)
    return text
OFF_THE_LISTS = "jidoka: `curl https://example.com` is off jidoka's lists for lap workers. Find another way, or park " \
                "the task with a question that names this call."


class ProfileGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.home = cls.root / "home"
        cls.home.mkdir()
        (cls.home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        cls.worktree = cls.root / "repo" / ".worktrees" / "lap-t1"
        (cls.worktree / "src").mkdir(parents=True)
        (cls.root / "repo" / "src").mkdir(parents=True)
        fixture.write_guard_record_of(cls.home, cls.worktree, "lap", CASES["commands"], CASES["barred"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def payload(self, cwd: Path, command: object, **more: object) -> dict:
        args = {} if command is None else {"CommandLine": command}
        return self.call(cwd, "run_command", args, **more)

    def call(self, cwd: Path, tool: str, args: dict, **more: object) -> dict:
        return {"hookEventName": "PreToolUse", "conversationId": "c1", "stepIdx": 3, "cwd": str(cwd),
                "toolCall": {"id": "t1", "name": tool, "args": args}, **more}

    def guard(self, payload: object) -> subprocess.CompletedProcess:
        return self.guard_in_home(payload, self.home)

    def guard_in_home(self, payload: object, home: Path) -> subprocess.CompletedProcess:
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        env = {**os.environ, "JIDOKA_HOME": str(home)}
        return fixture.run_launcher(LAUNCHER, [str(GUARD), "--host", "antigravity"], raw, env, self.root,
                                    RUN_TIMEOUT_SECONDS)

    def assert_answers(self, expected: dict, done: subprocess.CompletedProcess) -> None:
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(expected, json.loads(done.stdout))

    def assert_prints_nothing(self, done: subprocess.CompletedProcess) -> None:
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("", done.stdout)

    def test_every_case_of_the_shared_table_gets_its_decision_from_the_guard(self):
        for case in CASES["cases"]:
            with self.subTest(case["name"]):
                folder = self.root / f"kind-{case['kind']}" / ".worktrees" / "lap-t1"
                outside = folder.parent / "outside"
                outside.mkdir(parents=True, exist_ok=True)
                folder.mkdir(parents=True, exist_ok=True)
                fixture.write_guard_record_of(self.home, folder, case["kind"], CASES["commands"], CASES["barred"])
                places = {"worktree": str(folder), "outside": str(outside), "tool": tool_of(case)["name"]}
                for link, target in case.get("links", {}).items():
                    self.link(Path(placed(link, places)), Path(placed(target, places)))

                done = self.guard(self.shared_call(folder, case, places))

                expected = case["verdict"]
                if "reason" in expected:
                    expected = {**expected, "reason": placed(expected["reason"], places)}
                self.assert_answers(expected, done)

    def link(self, link: Path, target: Path) -> None:
        if not link.is_symlink():
            link.symlink_to(target)

    def shared_call(self, folder: Path, case: dict, places: dict) -> dict:
        if "use" not in case:
            return self.payload(folder, placed(case["call"], places))
        tool, path = tool_of(case), case["use"].get("path")
        args = {} if tool["field"] is None or path is None else {tool["field"]: placed(path, places)}
        return self.call(folder, tool["name"], args)

    def test_a_call_in_a_folder_inside_a_worktree_with_a_record_is_judged_by_the_lists(self):
        listed = self.guard(self.payload(self.worktree / "src", "dotnet build App.slnx"))
        unlisted = self.guard(self.payload(self.worktree / "src", "curl https://example.com"))

        self.assert_answers({"decision": "allow"}, listed)
        self.assert_answers({"decision": "deny", "reason": OFF_THE_LISTS}, unlisted)

    def test_a_call_whose_workspace_path_is_a_guarded_worktree_is_judged_though_its_folder_is_not_one(self):
        done = self.guard(self.payload(self.root / "repo", "curl https://example.com",
                                       workspacePaths=[str(self.root / "elsewhere"), str(self.worktree)]))

        self.assert_answers({"decision": "deny", "reason": OFF_THE_LISTS}, done)

    def test_a_record_names_its_own_worktree_and_guards_no_other(self):
        sibling = self.root / "repo" / ".worktrees" / "lap-t2"
        sibling.mkdir(parents=True)

        done = self.guard(self.payload(sibling, "curl https://example.com"))

        self.assert_prints_nothing(done)

    def test_a_record_in_another_jidoka_home_guards_nothing(self):
        other_home = self.root / "other-home"
        other_home.mkdir()
        (other_home / "python").write_text(sys.executable + "\n", encoding="utf-8")

        done = self.guard_in_home(self.payload(self.worktree, "curl https://example.com"), other_home)

        self.assert_prints_nothing(done)

    def test_a_call_of_any_tool_outside_a_lap_prints_nothing(self):
        for tool in ["write_file", "invoke_subagent", "ask_question", "view_file", "run_command"]:
            with self.subTest(tool=tool):
                done = self.guard(self.call(self.root / "repo", tool, {"Path": "/etc/hosts", "CommandLine": "rm -rf /"}))

                self.assert_prints_nothing(done)

    def test_a_call_of_a_tool_the_guard_does_not_know_is_denied_by_its_name_in_a_lap(self):
        done = self.guard(self.call(self.worktree, "view_file", {"CommandLine": "curl https://example.com"}))

        self.assertEqual(0, done.returncode, done.stderr)
        answer = json.loads(done.stdout)
        self.assertEqual("deny", answer["decision"])
        self.assertIn("view_file", answer["reason"])

    def test_a_write_that_names_no_path_or_a_path_that_is_not_text_is_denied(self):
        for tool, field in [("write_file", "Path"), ("edit_file", "Path"), ("notebook_edit", "NotebookPath")]:
            for args in [{}, {field: ""}, {field: 7}, {"Path" if field != "Path" else "NotebookPath": "/x"}]:
                with self.subTest(tool=tool, args=args):
                    done = self.guard(self.call(self.worktree, tool, args))

                    self.assert_answers({"decision": "deny", "reason": f"jidoka: {tool} names no {field}."}, done)

    def test_a_write_by_a_relative_path_is_denied_though_it_would_land_inside_the_worktree(self):
        done = self.guard(self.call(self.worktree, "write_file", {"Path": "src/a.py"}))

        self.assert_answers({"decision": "deny", "reason": "jidoka: write_file of src/a.py is not an absolute path. "
                             f"Name the file by its absolute path inside the lap's worktree {self.worktree}."}, done)

    def test_a_write_through_a_link_that_leads_nowhere_is_denied(self):
        (self.worktree / "dangling").symlink_to(self.root / "gone" / "far")

        done = self.guard(self.call(self.worktree, "write_file", {"Path": str(self.worktree / "dangling" / "a.py")}))

        self.assert_answers({"decision": "deny", "reason": f"jidoka: write_file of {self.worktree}/dangling/a.py is "
                             f"outside the lap's worktree {self.worktree}."}, done)

    def test_a_write_into_a_folder_whose_case_differs_from_an_acceptance_folder_is_denied(self):
        done = self.guard(self.call(self.worktree, "write_file", {"Path": str(self.worktree / "SPECS" / "Acceptance" / "a.md")}))

        self.assertEqual("deny", json.loads(done.stdout)["decision"])

    def test_every_write_is_denied_when_the_acceptance_folders_could_not_be_read(self):
        folder = self.root / "unread" / ".worktrees" / "lap-t1"
        folder.mkdir(parents=True)
        fixture.write_guard_record_of(self.home, folder, "lap", CASES["commands"], None)

        done = self.guard(self.call(folder, "write_file", {"Path": str(folder / "src" / "a.py")}))

        self.assert_answers({"decision": "deny", "reason": f"jidoka: write_file of {folder}/src/a.py is denied, because "
                             "jidoka could not read which acceptance folders this lap may not write in. Park the task "
                             "with a question that says so."}, done)

    def test_a_relative_path_of_a_command_reads_against_the_folder_the_call_runs_in(self):
        inside = self.guard(self.payload(self.worktree / "src", "rm a.py"))
        climbing = self.guard(self.payload(self.worktree / "src", "rm ../../a.py"))

        self.assert_answers({"decision": "allow"}, inside)
        self.assertEqual("deny", json.loads(climbing.stdout)["decision"])

    def test_a_delete_behind_a_variable_is_denied_as_one_jidoka_cannot_tell(self):
        done = self.guard(self.payload(self.worktree, "FOO=1 rm src/a.py"))

        self.assertIn("is a delete whose paths jidoka cannot tell", json.loads(done.stdout)["reason"])

    def test_a_run_command_with_no_command_line_in_a_lap_is_denied(self):
        for command in [None, 7, ["dotnet", "build"]]:
            with self.subTest(command=command):
                done = self.guard(self.payload(self.worktree, command))

                self.assertEqual(0, done.returncode, done.stderr)
                answer = json.loads(done.stdout)
                self.assertEqual({"decision", "reason"}, set(answer))
                self.assertEqual("deny", answer["decision"])
                self.assertIn("names no command text", answer["reason"])

    def test_input_that_is_not_a_call_prints_nothing(self):
        for raw in ["not json", "[]", "null", json.dumps({"cwd": str(self.worktree)})]:
            with self.subTest(raw=raw):
                self.assert_prints_nothing(self.guard(raw))

    def test_a_record_that_cannot_be_read_crashes_the_guard_with_a_nonzero_exit_and_no_answer(self):
        home = self.root / "broken-home"
        home.mkdir()
        (home / "python").write_text(sys.executable + "\n", encoding="utf-8")
        whole = {"worktree": str(self.worktree), "kind": "lap", "stage": "build", "commands": [], "barred": []}
        for text in ["{", "[]", json.dumps({**whole, "kind": "other"}),
                     json.dumps({key: value for key, value in whole.items() if key != "barred"}),
                     json.dumps({**whole, "barred": "specs"}), json.dumps({**whole, "barred": [7]})]:
            with self.subTest(text=text):
                path = lap_guard_record.record_path(home, self.worktree)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")

                done = self.guard_in_home(self.payload(self.worktree, "dotnet build App.slnx"), home)

                self.assertNotEqual(0, done.returncode)
                self.assertEqual("", done.stdout)


if __name__ == "__main__":
    unittest.main()
