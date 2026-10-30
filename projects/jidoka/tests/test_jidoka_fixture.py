import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path, PureWindowsPath

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402


def committed_repo(repo: Path) -> None:
    fixture.init_repo(repo)
    (repo / "README.md").write_text("shop\n", encoding="utf-8")
    fixture.git_commit_all(repo, "Start")


def titles(repo: Path) -> list[str]:
    return [bead["title"] for bead in json.loads(fixture.run(["bd", "list", "--json"], repo) or "[]")]


class StealthBeadsTests(unittest.TestCase):
    def test_two_repos_given_the_stealth_beads_workspace_keep_their_own_beads_and_a_clean_status(self):
        root = fixture.bd_folder(self.addCleanup)
        shop, kiosk = root / "shop", root / "kiosk"
        committed_repo(shop)
        committed_repo(kiosk)

        fixture.add_stealth_beads(shop)
        fixture.add_stealth_beads(kiosk)
        fixture.run(["bd", "create", "--title=Print the receipt", "--type=task"], shop)

        self.assertEqual(["Print the receipt"], titles(shop))
        self.assertEqual([], titles(kiosk))
        self.assertEqual("", fixture.run(["git", "status", "--porcelain", "--untracked-files=all"], shop))


class WindowsExecutableTests(unittest.TestCase):
    """A fake executable on Windows is a launcher exe that starts Python on a script packed behind it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_a_launcher_with_a_script_packed_behind_it_runs_the_script_with_the_arguments_it_was_given(self):
        packed = self.root / "tool.exe"
        packed.write_bytes(fixture.pack_launcher(b"MZ not a real launcher\n", sys.executable,
                                                 "import json, sys\nprint(json.dumps(sys.argv[1:]))\n"))

        done = subprocess.run([sys.executable, str(packed), "one", "two words"], capture_output=True, text=True,
                              encoding="utf-8")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["one", "two words"], json.loads(done.stdout))

    def test_the_shebang_line_quotes_an_interpreter_path_that_holds_a_space(self):
        packed = fixture.pack_launcher(b"MZ\n", "C:\\Program Files\\Python\\python.exe", "pass\n")

        self.assertIn(b'#!"C:\\Program Files\\Python\\python.exe"\n', packed)

    def test_a_shell_script_is_run_by_a_python_launcher_that_hands_it_to_sh(self):
        main = fixture.shell_script_main(fixture.real_shell())
        packed = self.root / "tool.exe"
        packed.write_bytes(fixture.pack_launcher(b"MZ\n", sys.executable, main))
        packed.with_suffix(".sh").write_text('echo "ran with: $@"\n', encoding="utf-8")

        done = subprocess.run([sys.executable, str(packed), "a", "b"], capture_output=True, text=True,
                              encoding="utf-8")

        self.assertEqual("ran with: a b\n", done.stdout)

    def test_an_executable_file_has_the_exe_extension_on_windows_and_none_elsewhere(self):
        self.assertEqual(Path("bin/bd.exe"), fixture.executable_file(Path("bin/bd"), True))
        self.assertEqual(Path("bin/bd"), fixture.executable_file(Path("bin/bd"), False))

    def test_a_script_environment_on_windows_keeps_the_variables_python_cannot_start_without(self):
        environ = {"SystemRoot": "C:\\Windows", "TEMP": "C:\\Temp", "PATH": "C:\\elsewhere", "OTHER": "x"}

        self.assertEqual({"SystemRoot": "C:\\Windows", "TEMP": "C:\\Temp"}, fixture.system_variables(environ, True))
        self.assertEqual({}, fixture.system_variables(environ, False))

    def test_a_launcher_command_names_a_script_file_that_holds_the_launcher_with_forward_slashes_and_its_arguments(self):
        command = fixture.bash_command("C:\\Git\\bin\\bash.exe", PureWindowsPath("C:\\plugin\\bin\\jidoka-run"),
                                       ["x.py", "go"])

        self.assertEqual(2, len(command))
        self.assertEqual("C:\\Git\\bin\\bash.exe", command[0])
        self.assertTrue(command[1].endswith(".sh"))
        self.assertNotIn("\\", command[1])
        self.assertEqual('exec "$BASH" C:/plugin/bin/jidoka-run x.py go\n',
                         Path(command[1]).read_text(encoding="utf-8", newline=""))

    def test_the_git_bash_is_the_outer_bash_of_the_git_folder_and_not_the_inner_one_beside_sh(self):
        git_root = self.root / "Git"
        outer, inner = git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe"
        for bash in (outer, inner):
            bash.parent.mkdir(parents=True)
            bash.write_text("", encoding="utf-8")
        mingw = git_root / "mingw64" / "bin"
        mingw.mkdir(parents=True)
        (git_root / "cmd").mkdir()

        self.assertEqual(str(outer), fixture.git_bash_beside(str(git_root / "cmd" / "git.exe")))
        self.assertEqual(str(outer), fixture.git_bash_beside(str(mingw / "git.exe")))

    def test_a_launcher_command_hands_every_argument_to_the_launcher_as_it_was_given(self):
        given = ["rules.py", "set", "epic", 'tier_routes={"second":"codex"}', 'lap_test_scope="full"', "it's",
                 "two  spaces", "", "back\\slash", "$HOME `x`", "line\nbreak"]
        launcher = self.root / "show-arguments"
        launcher.write_text('for word in "$@"; do printf "[%s]\\n" "$word"; done\n', encoding="utf-8", newline="\n")
        bash = fixture.git_bash() if fixture.WINDOWS else shutil.which("bash")
        self.assertIsNotNone(bash)

        command = fixture.bash_command(bash, launcher, given)
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")

        self.assertEqual("".join(f"[{word}]\n" for word in given), done.stdout)

    def test_a_path_in_the_windows_form_is_read_by_bash_as_drive_folders_joined_by_colons(self):
        self.assertEqual("/c/Program Files/Git/cmd:/d/tools",
                         fixture.windows_bash_path("C:\\Program Files\\Git\\cmd;D:\\tools"))

    def test_a_launcher_command_on_a_path_sets_that_path_before_it_runs_the_launcher(self):
        command = fixture.bash_command_on_path("C:\\Git\\bin\\bash.exe",
                                               PureWindowsPath("C:\\plugin\\bin\\jidoka-run"), ["x.py"],
                                               "/c/Program Files/Git/cmd")

        self.assertEqual("C:\\Git\\bin\\bash.exe", command[0])
        self.assertEqual("PATH='/c/Program Files/Git/cmd'\nexec \"$BASH\" C:/plugin/bin/jidoka-run x.py\n",
                         Path(command[1]).read_text(encoding="utf-8", newline=""))

    def test_a_launcher_run_on_a_path_runs_the_launcher_on_exactly_the_path_it_was_given(self):
        launcher = self.root / "print-path"
        launcher.write_text('#!/bin/sh\nprintf "%s" "$PATH"\n', encoding="utf-8", newline="\n")
        launcher.chmod(0o755)
        only = self.root / "only"
        only.mkdir()
        environment = {**os.environ, "PATH": str(only)}

        done = fixture.run_launcher_on_path(launcher, ["unused"], None, environment, self.root, 30)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(fixture.windows_bash_path(str(only)) if fixture.WINDOWS else str(only), done.stdout)

    def test_a_launcher_run_gives_the_launcher_its_arguments_stdin_environment_and_folder(self):
        launcher = self.root / "report"
        launcher.write_text('#!/bin/sh\nprintf "[%s][%s][%s]" "$1" "$(cat)" "$REPORT_VARIABLE"; { pwd -W 2>/dev/null || pwd; } >&2\n',
                            encoding="utf-8", newline="\n")
        launcher.chmod(0o755)
        folder = self.root / "work"
        folder.mkdir()
        environment = {**os.environ, "REPORT_VARIABLE": "set"}

        done = fixture.run_launcher(launcher, ["first"], "typed in", environment, folder, 30)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual("[first][typed in][set]", done.stdout)
        self.assertEqual(folder.resolve(), Path(done.stderr.strip()).resolve())


class FolderWithoutBeadsAboveTests(unittest.TestCase):
    """The folders under test sit below a user folder that holds a .beads, as a temporary folder does on a machine whose
    user runs bd, so only the top the helper is given can tell it where to stop looking."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        user_folder = Path(tmp.name).resolve() / "user"
        (user_folder / ".beads").mkdir(parents=True)
        self.root = user_folder / "temp"
        self.root.mkdir()

    def test_a_parent_with_a_beads_folder_in_it_or_above_it_is_passed_over_for_the_next_one(self):
        with_beads = self.root / "home"
        (with_beads / ".beads").mkdir(parents=True)
        (with_beads / "temp").mkdir()
        free = self.root / "free"
        free.mkdir()

        made = fixture.folder_without_beads_above([with_beads, with_beads / "temp", free], self.root)

        self.assertEqual(free, made.parent)
        self.assertTrue(made.is_dir())

    def test_a_beads_folder_in_the_top_itself_leaves_no_parent_free(self):
        (self.root / ".beads").mkdir()

        with self.assertRaises(fixture.FixtureError):
            fixture.folder_without_beads_above([self.root], self.root)

    def test_a_beads_folder_above_the_top_is_not_looked_at(self):
        made = fixture.folder_without_beads_above([self.root], self.root)

        self.assertEqual(self.root, made.parent)


class RemoveTreeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_a_folder_holding_read_only_files_and_folders_is_removed_whole(self):
        objects = self.root / "repo" / ".git" / "objects"
        pack = objects / "ab"
        pack.mkdir(parents=True)
        loose = pack / "cdef"
        loose.write_text("object\n", encoding="utf-8")
        loose.chmod(0o444)
        pack.chmod(0o555)
        objects.chmod(0o555)

        fixture.remove_tree(self.root / "repo")

        self.assertFalse((self.root / "repo").exists())

    def test_a_folder_that_is_not_there_is_left_alone(self):
        fixture.remove_tree(self.root / "gone")

        self.assertFalse((self.root / "gone").exists())


WAIT_FOR_PROCESS_SECONDS = 10
WAIT_FOR_PROCESS_POLL_SECONDS = 0.1


def start_holder(folder: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", fixture.SLEEP_FOR_AN_HOUR], cwd=folder,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_file_holder(file: Path, folder: Path) -> subprocess.Popen:
    """A process that runs in another folder, holds the file open, and sleeps once it prints that it does."""
    code = f"held = open({str(file)!r}); print('open', flush=True); {fixture.SLEEP_FOR_AN_HOUR}"
    holder = subprocess.Popen([sys.executable, "-c", code], cwd=folder, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    holder.stdout.readline()
    return holder


def start_holder_after_its_parent_ended(folder: Path) -> int:
    code = "\n".join([
        "import subprocess, sys",
        f"child = subprocess.Popen([sys.executable, '-c', {fixture.SLEEP_FOR_AN_HOUR!r}], cwd={str(folder)!r},",
        "                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)",
        "print(child.pid, flush=True)"])
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8")
    return int(done.stdout)


def wait_until_gone(pid: int) -> bool:
    deadline = time.monotonic() + WAIT_FOR_PROCESS_SECONDS
    while fixture.process_is_running(pid) and time.monotonic() < deadline:
        time.sleep(WAIT_FOR_PROCESS_POLL_SECONDS)
    return not fixture.process_is_running(pid)


class BdFolderTests(unittest.TestCase):
    """A folder that real bd ran in can hold processes bd left behind, which keep Windows from removing it."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(fixture.remove_tree_quietly, self.folder)

    def test_a_process_whose_parent_ended_is_ended_and_the_folder_it_ran_in_is_removed(self):
        pid = start_holder_after_its_parent_ended(self.folder)
        self.addCleanup(fixture.end_process, pid)

        fixture.remove_bd_folder(self.folder)

        self.assertTrue(wait_until_gone(pid))
        self.assertFalse(self.folder.exists())

    def test_a_process_whose_parent_still_runs_is_ended_and_the_folder_it_ran_in_is_removed(self):
        parent = subprocess.Popen(
            [sys.executable, "-c", "\n".join([
                "import subprocess, sys",
                f"child = subprocess.Popen([sys.executable, '-c', {fixture.SLEEP_FOR_AN_HOUR!r}], "
                f"cwd={str(self.folder)!r}, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL)",
                "print(child.pid, flush=True)",
                fixture.SLEEP_FOR_AN_HOUR])],
            stdout=subprocess.PIPE, text=True, encoding="utf-8")
        self.addCleanup(parent.wait)
        self.addCleanup(parent.stdout.close)
        self.addCleanup(fixture.end_process, parent.pid)
        pid = int(parent.stdout.readline())
        self.addCleanup(fixture.end_process, pid)

        fixture.remove_bd_folder(self.folder)

        self.assertTrue(wait_until_gone(pid))
        self.assertTrue(fixture.process_is_running(parent.pid))
        self.assertFalse(self.folder.exists())

    def test_a_process_that_runs_in_a_folder_under_the_folder_is_a_holder(self):
        deeper = self.folder / ".beads" / "dolt"
        deeper.mkdir(parents=True)
        holder = start_holder(deeper)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)

        self.assertIn(holder.pid, fixture.holders_in(self.folder, set()))

    def test_a_process_that_runs_in_another_folder_is_not_a_holder(self):
        elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(fixture.remove_tree_quietly, elsewhere)
        holder = start_holder(elsewhere)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)

        self.assertNotIn(holder.pid, fixture.holders_in(self.folder, set()))

    def holding_a_file_from_elsewhere(self, file: Path) -> subprocess.Popen:
        """A process that runs in a folder of its own, holds the file open, and is ended when the test ends."""
        elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(fixture.remove_tree_quietly, elsewhere)
        holder = start_file_holder(file, elsewhere)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.stdout.close)
        self.addCleanup(holder.kill)
        return holder

    @unittest.skipUnless(fixture.WINDOWS, "only Windows finds a process by the file it holds open")
    def test_a_process_that_runs_elsewhere_and_holds_a_file_open_in_the_folder_is_a_holder(self):
        held = self.folder / ".beads" / "dolt" / "manifest"
        held.parent.mkdir(parents=True)
        held.write_text("x\n", encoding="utf-8")
        holder = self.holding_a_file_from_elsewhere(held)

        self.assertIn(holder.pid, fixture.holders_in(self.folder, set()))

    @unittest.skipUnless(fixture.WINDOWS, "only Windows finds a process by the file it holds open")
    def test_a_process_that_runs_elsewhere_and_holds_a_file_open_in_the_folder_is_ended_and_the_folder_is_removed(self):
        held = self.folder / "dolt-lock"
        held.write_text("x\n", encoding="utf-8")
        holder = self.holding_a_file_from_elsewhere(held)

        fixture.remove_bd_folder(self.folder)

        self.assertTrue(wait_until_gone(holder.pid))
        self.assertFalse(self.folder.exists())

    @unittest.skipUnless(fixture.WINDOWS, "only Windows finds a process by the file it holds open")
    def test_a_process_that_holds_a_file_open_in_another_folder_is_not_a_holder(self):
        other_folder = Path(tempfile.mkdtemp())
        self.addCleanup(fixture.remove_tree_quietly, other_folder)
        other = other_folder / "file"
        other.write_text("x\n", encoding="utf-8")
        holder = self.holding_a_file_from_elsewhere(other)

        self.assertNotIn(holder.pid, fixture.holders_in(self.folder, set()))

    def test_a_process_in_the_spared_set_is_not_a_holder(self):
        holder = start_holder(self.folder)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)

        self.assertNotIn(holder.pid, fixture.holders_in(self.folder, {holder.pid}))

    def test_this_process_and_the_process_that_started_it_are_never_ended(self):
        lineage = fixture.own_lineage()

        self.assertIn(os.getpid(), lineage)
        self.assertIn(os.getppid(), lineage)

    def test_a_folder_made_for_a_test_is_removed_when_the_test_ends(self):
        cleanups = []

        folder = fixture.bd_folder(lambda function, *args: cleanups.append((function, args)))
        self.addCleanup(fixture.remove_tree_quietly, folder)
        (folder / "bd-wrote-this").write_text("x\n", encoding="utf-8")
        for function, args in reversed(cleanups):
            function(*args)

        self.assertFalse(folder.exists())


def write_a_bd_that_prints_its_home(folder: Path) -> Path:
    return fixture.write_executable(folder / "bd", "\n".join([
        f"#!{sys.executable}",
        "import json, os",
        "print(json.dumps([os.environ.get('HOME'), os.environ.get('USERPROFILE')]))",
        ""]))


class BdHomeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def put_a_bd_that_prints_its_home_first_on_the_path(self) -> Path:
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        write_a_bd_that_prints_its_home(bin_dir)
        saved_path = os.environ.get("PATH")
        os.environ["PATH"] = fixture.path_with(bin_dir)
        self.addCleanup(self.restore_path, saved_path)
        return bin_dir

    def restore_path(self, saved_path: str | None) -> None:
        if saved_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = saved_path

    def test_a_bd_the_fixture_runs_sees_one_home_of_its_own_in_home_and_userprofile(self):
        self.put_a_bd_that_prints_its_home_first_on_the_path()
        repo = self.root / "repo"
        repo.mkdir()

        home, userprofile = json.loads(fixture.run(["bd"], repo))

        self.assertEqual(home, userprofile)
        self.assertTrue(Path(home).is_dir())
        self.assertNotEqual(Path.home(), Path(home))
        self.assertNotIn(repo, [Path(home), *Path(home).parents])

    def test_a_fake_bd_a_test_names_by_its_own_path_runs_in_the_environment_the_test_has(self):
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        fake = write_a_bd_that_prints_its_home(fake_bin)

        home, _ = json.loads(fixture.run([str(fake)], self.root))

        self.assertEqual(os.environ.get("HOME"), home)


class RepoSettingsTests(unittest.TestCase):
    """The repo settings a test writes for a repo in a jidoka home."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.repo = self.root / "shop"
        committed_repo(self.repo)
        self.home = self.root / "jidoka-home"
        self.home.mkdir()
        (self.home / "python").write_text(sys.executable + "\n", encoding="utf-8")

    def test_settings_the_script_accepts_are_stored_in_the_jidoka_home(self):
        app = {"name": "shop", "kind": "program", "way_in": "its command line", "build": "make", "run": None,
               "test": "make test", "test_target": "-k <name>", "test_full": None, "hand_run": [],
               "acceptance": None}

        settings = {"lap_test_scope": "targeted", "worker_commands": [], "slot_use": None, "lap_limit": 1,
                    "apps": [app]}

        fixture.write_repo_settings(self.repo, self.home, settings)

        [stored] = (self.home / "repos").glob("*.json")
        self.assertEqual(["shop"], [each["name"] for each in json.loads(stored.read_text(encoding="utf-8"))["apps"]])

    def test_settings_the_script_refuses_fail_with_a_fixture_error_that_names_the_scripts_message(self):
        with self.assertRaises(fixture.FixtureError) as raised:
            fixture.write_repo_settings(self.repo, self.home, {"apps": []})

        self.assertIn("apps must be a list that holds at least one app", str(raised.exception))
        self.assertEqual([], list((self.home / "repos").glob("*.json")))


class LinkTargetTests(unittest.TestCase):
    def test_a_relative_target_is_given_as_it_was_made(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "alias.md"
            link.symlink_to("domain.md")

            self.assertEqual(Path("domain.md"), fixture.link_target(link))

    def test_an_absolute_target_is_given_without_the_prefix_windows_adds(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp).resolve()
            link = folder / "alias"
            link.symlink_to(folder / "real", target_is_directory=True)

            self.assertEqual(folder / "real", fixture.link_target(link))


if __name__ == "__main__":
    unittest.main()
