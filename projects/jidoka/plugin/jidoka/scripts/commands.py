"""Runs the git, bd and test commands that jidoka's scripts call, with failures worded for the person who reads the
output, and holds what the scripts read from a bead and from the repo's layout: its labels, parent and metadata, the
factory's labels, the worktree folder and the main ref."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from runner_summary import Finished

COMMAND_TIMEOUT_SECONDS = 120
GIT_BASH_VARIABLE = "CLAUDE_CODE_GIT_BASH_PATH"
# Folders above git that can be the Git for Windows root: <Git>/cmd/git.exe is one below it, <Git>/mingw64/bin/git.exe two.
GIT_FOLDERS_ABOVE_GIT = 3
FACTORY_ACTOR = "jidoka"
FACTORY_LABEL = "factory"
HUMAN_LABEL = "human"
SCRATCH_FOLDER = ".scratch"
WORKTREE_FOLDER = ".worktrees"
MAIN_REF = "refs/heads/main"
PARENT_CHILD = "parent-child"
NONE_YET = 0


class CommandError(Exception):
    """A command that could not start, ran past the timeout, or exited nonzero where success was required."""


class BeadNotCreated(CommandError):
    """`bd create --json` printed no id for the bead it made."""

    def __init__(self, printed: str) -> None:
        super().__init__(f"bd create did not print the id of the bead it made: {printed.strip()[:200]!r}")
        self.printed = printed


@dataclass(frozen=True)
class Worktree:
    """A worktree of the repo: its path as git prints it, and its branch, or an empty string when it has none."""
    path: Path
    branch: str


class BeadReads:
    """What one call of a script has read from bd, kept so that the call does not ask bd for the same thing twice.

    A bd command that writes drops the copies it can change: the written bead's own, the shows of the beads that wait
    on it or sit under it, because bd embeds a bead in the show of each bead linked to it, and every list. A command
    that bd does not read with is taken as a write to every bead, so a new bd subcommand costs a read, never a stale
    copy. It holds the beads as bd printed them and hands out copies, so a caller can change what it gets.
    """

    READING = frozenset({"show", "list", "comments", "ready", "blocked", "prime", "where", "info", "version"})
    WRITING_ONE_BEAD = {"update": 1, "comment": 1, "close": 1, "label": 2}

    def __init__(self) -> None:
        self.shown: dict[str, dict] = {}
        self.comments: dict[str, list[dict]] = {}
        self.lists: dict[tuple[str, ...], list[dict]] = {}

    def forget_after(self, bd_args: list[str]) -> None:
        """Drops what a bd command with these arguments, after the `bd`, can have changed."""
        if not bd_args or bd_args[0] in self.READING:
            return
        written = self.WRITING_ONE_BEAD.get(bd_args[0])
        if written is None or len(bd_args) <= written or any(argument.startswith("--parent") for argument in bd_args):
            self.shown.clear()
            self.comments.clear()
            self.lists.clear()
            return
        bead = bd_args[written]
        self.shown = {key: held for key, held in self.shown.items() if not self.is_affected_by(bead, key, held)}
        self.comments.pop(bead, None)
        self.lists.clear()

    @staticmethod
    def is_affected_by(bead: str, key: str, held: dict) -> bool:
        links = [link.get("id") for link in held.get("dependencies") or [] if isinstance(link, dict)]
        return bead in (key, held.get("id"), *links)


_reads: BeadReads | None = None


@contextmanager
def keeping_reads() -> Iterator[None]:
    """For the length of the block, the bd reads of bd_show, bd_list, bd_comments and bd_show_all are kept, and a bd
    command that writes drops the copies it can change. A script that runs once and exits keeps its reads for its
    whole call; one that polls bd keeps none, because it waits for another process to change a bead."""
    global _reads
    outer, _reads = _reads, BeadReads()
    try:
        yield
    finally:
        _reads = outer


def capture(args: list[str], cwd: Path, env: dict[str, str] | None) -> subprocess.CompletedProcess:
    """Runs the command in env, or in the inherited environment when env is None."""
    try:
        return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=COMMAND_TIMEOUT_SECONDS)
    except OSError as error:
        raise CommandError(f"cannot run {args[0]}: {error}") from error
    except subprocess.TimeoutExpired as error:
        raise CommandError(f"{' '.join(args[:3])} did not finish in {COMMAND_TIMEOUT_SECONDS} seconds") from error
    finally:
        if _reads is not None and args[:1] == ["bd"]:
            _reads.forget_after(args[1:])


def run(args: list[str], cwd: Path, env: dict[str, str] | None) -> str:
    """The command's stdout, run in env, or in the inherited environment when env is None.

    A nonzero exit raises CommandError with its stderr.
    """
    done = capture(args, cwd, env)
    if done.returncode != 0:
        detail = done.stderr.strip() or done.stdout.strip()
        raise CommandError(f"{' '.join(args[:3])} failed: {detail}")
    return done.stdout


def env_as_git_user(main_tree: Path) -> dict[str, str]:
    """The environment bd runs in, with BEADS_ACTOR set to the repo's git user.name."""
    name = capture(["git", "config", "user.name"], main_tree, None).stdout.strip()
    if not name:
        raise CommandError(f"git config user.name is not set in {main_tree}, and jidoka writes to the beads "
                           "under that name. Set it with git config user.name \"<your name>\"")
    return {**os.environ, "BEADS_ACTOR": name}


def env_as_factory() -> dict[str, str]:
    """The environment bd runs in for what the factory writes on a lap, with BEADS_ACTOR set to jidoka."""
    return {**os.environ, "BEADS_ACTOR": FACTORY_ACTOR}


def set_metadata(*pairs: tuple[str, object]) -> list[str]:
    """The `--set-metadata key=value` arguments of a `bd update`, one for each pair."""
    return [argument for key, value in pairs for argument in ("--set-metadata", f"{key}={value}")]


def unset_metadata(*keys: str) -> list[str]:
    """The `--unset-metadata key` arguments of a `bd update`, one for each key."""
    return [argument for key in keys for argument in ("--unset-metadata", key)]


def metadata_of(bead: dict) -> dict:
    """The metadata object bd shows on the bead, or an empty one when it shows none."""
    metadata = bead.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def parent_of(shown: dict) -> str:
    """The bead's parent id, from bd's parent field or else its parent-child dependency; empty when it has none."""
    if shown.get("parent"):
        return str(shown["parent"])
    for link in shown.get("dependencies") or []:
        if isinstance(link, dict) and link.get("dependency_type") == PARENT_CHILD and link.get("id"):
            return str(link["id"])
    return ""


def labels_of(shown: dict) -> list[str]:
    """The labels bd shows on the bead."""
    return [str(label) for label in shown.get("labels") or []]


def is_labeled_for_human(shown: dict) -> bool:
    """True when the bead carries the human label, the human's brake."""
    return HUMAN_LABEL in labels_of(shown)


class NotAWholeNumber(ValueError):
    """A metadata value that should hold a whole number and holds something else."""


def whole_number_in(metadata: dict, key: str) -> int | None:
    """The whole number the metadata holds under the key, or None when it holds nothing.

    A value that is not a whole number raises NotAWholeNumber. A caller that counts from zero takes None as zero, and
    a caller that needs the value takes None as an error.
    """
    value = metadata.get(key)
    if value is None or value == "":
        return None
    try:
        return int(str(value))
    except ValueError as error:
        raise NotAWholeNumber(f"the {key} metadata holds {value!r} where it needs a whole number") from error


def count_in(metadata: dict, key: str) -> int:
    """The whole number the metadata holds under the key, or none yet when it holds nothing."""
    counted = whole_number_in(metadata, key)
    return NONE_YET if counted is None else counted


def head_of(ref: str, cwd: Path) -> str | None:
    """The sha of the commit the ref names, or None when it names no commit."""
    done = capture(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd, None)
    return done.stdout.strip() if done.returncode == 0 else None


def worktree_list(cwd: Path) -> list[Worktree]:
    """Every worktree of the repo that cwd is in, the main checkout first."""
    listing = run(["git", "worktree", "list", "--porcelain"], cwd, None)
    found: list[Worktree] = []
    for line in listing.splitlines():
        if line.startswith("worktree "):
            found.append(Worktree(Path(line[len("worktree "):]), ""))
        elif line.startswith("branch refs/heads/") and found:
            found[-1] = Worktree(found[-1].path, line[len("branch refs/heads/"):])
    return found


class UnreadableShow(CommandError):
    """`bd show --json` printed something other than a JSON list."""


def print_shown(beads: list[str], cwd: Path) -> list[dict]:
    """The objects in the JSON list that one bd show prints for the beads."""
    output = run(["bd", "show", *beads, "--json"], cwd, None)
    try:
        parsed = json.loads(output)
    except ValueError as error:
        raise UnreadableShow(f"bd show did not print JSON: {output.strip()[:200]!r}") from error
    if not isinstance(parsed, list):
        raise UnreadableShow("bd show printed JSON that is not a list")
    return [bead for bead in parsed if isinstance(bead, dict)]


def bd_show_all(beads: list[str], cwd: Path) -> list[dict]:
    """The beads as bd show --json prints them. With reads off, in the order bd prints them. While reads are kept, one
    bd show asks for the beads the call has not read yet, and none when it has read them all, and the beads come back
    in the order asked, only those found in the cache.

    The cache is keyed by the id bd prints. The one exception is a single bead asked for alone: it is kept under the id
    asked for, whatever id bd prints it under, because a caller may ask by a short form of the id and ask again. A bead
    asked for among several is found only under the id bd prints. Output that is not a JSON list raises
    UnreadableShow.
    """
    if _reads is None:
        return print_shown(beads, cwd)
    held = _reads.shown
    missing = [bead for bead in dict.fromkeys(beads) if bead not in held]
    if missing:
        printed = print_shown(missing, cwd)
        if len(missing) == 1 and len(printed) == 1:
            held[missing[0]] = printed[0]
        else:
            held.update((str(bead.get("id")), bead) for bead in printed)
    return copy.deepcopy([held[bead] for bead in beads if bead in held])


def bd_show(bead: str, cwd: Path) -> dict | None:
    """The bead as bd show --json prints it, or None when the output holds no bead.

    A caller that goes on without the bead takes None. A caller that needs the bead calls read_bead.
    """
    try:
        printed = bd_show_all([bead], cwd)
    except UnreadableShow:
        return None
    return printed[0] if printed else None


def read_bead(bead: str, cwd: Path) -> dict:
    """The bead as bd show --json prints it; raises CommandError when the output holds no bead."""
    shown = bd_show(bead, cwd)
    if shown is None:
        raise CommandError(f"bd show printed nothing usable for {bead}")
    return shown


def printed_beads(args: list[str], cwd: Path) -> list[dict]:
    """The objects in the JSON list that the bd command prints, an empty list when it prints nothing.

    Output that is not a JSON list raises CommandError. While reads are kept, the command runs once between writes.
    """
    if _reads is None:
        return print_list(args, cwd)
    key = tuple(args)
    if key not in _reads.lists:
        _reads.lists[key] = print_list(args, cwd)
    return copy.deepcopy(_reads.lists[key])


def print_list(args: list[str], cwd: Path) -> list[dict]:
    """The objects in the JSON list that the bd command prints, read afresh."""
    output = run(args, cwd, None)
    name = " ".join(args[:2])
    try:
        parsed = json.loads(output or "[]") or []
    except ValueError as error:
        raise CommandError(f"{name} did not print JSON: {output.strip()[:200]!r}") from error
    if not isinstance(parsed, list):
        raise CommandError(f"{name} printed JSON that is not a list")
    return [item for item in parsed if isinstance(item, dict)]


def created_id(created: str) -> str:
    """The id `bd create --json` printed for the bead it made."""
    try:
        return str(json.loads(created)["id"])
    except (ValueError, KeyError, TypeError) as error:
        raise BeadNotCreated(created) from error


def bd_list(filters: list[str], cwd: Path) -> list[dict]:
    """The beads that bd list --json prints for the filters."""
    return printed_beads(["bd", "list", *filters, "--json"], cwd)


def bd_comments(bead: str, cwd: Path) -> list[dict]:
    """The comments on the bead as bd comments --json prints them, oldest first."""
    command = ["bd", "comments", bead, "--json"]
    if _reads is None:
        return print_list(command, cwd)
    if bead not in _reads.comments:
        _reads.comments[bead] = print_list(command, cwd)
    return copy.deepcopy(_reads.comments[bead])


def git_bash_path(git: str | None, environ: Mapping[str, str]) -> Path | None:
    """The Git Bash that Claude Code looks for: the file GIT_BASH_VARIABLE names, else bin/bash.exe in the Git for
    Windows folder that holds git. None when that file does not exist."""
    named = environ.get(GIT_BASH_VARIABLE)
    if named:
        return Path(named) if Path(named).is_file() else None
    if git is None:
        return None
    for folder in list(Path(git).parents)[:GIT_FOLDERS_ABOVE_GIT]:
        candidate = folder / "bin" / "bash.exe"
        if candidate.is_file():
            return candidate
    return None


def test_script(command: str, folder: Path) -> Path:
    """The script file in the folder that holds the test command line, for Git Bash to read.

    The Windows command line loses the double quotes of an argument, so a line that holds a quote reaches bash.exe
    cut. A file holds the line as written.
    """
    script = folder / "run-tests.sh"
    script.write_bytes(f"{command}\n".encode("utf-8"))
    return script


def git_bash_command(script: Path, git: str | None, environ: Mapping[str, str]) -> list[str]:
    """The arguments that run a test script through Git Bash, where the filter in the line is quoted for sh and
    cmd.exe would read it differently. The script goes by a path with forward slashes, which bash.exe reads.

    Raises CommandError when there is no Git Bash.
    """
    bash = git_bash_path(git, environ)
    if bash is None:
        raise CommandError(f"cannot run the tests: Git Bash is not where Claude Code looks for it, in the file "
                           f"{GIT_BASH_VARIABLE} names or in bin/bash.exe of the folder that holds git")
    return [str(bash), script.as_posix()]


def run_test_command(command: str, cwd: Path) -> subprocess.CompletedProcess:
    """Runs a test command line from the repo settings through Git Bash on Windows and through the shell elsewhere.

    It has no timeout, because a test suite can run far longer than any git or bd command.
    """
    try:
        if os.name != "nt":
            return subprocess.run(command, cwd=cwd, shell=True, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
        with tempfile.TemporaryDirectory(prefix="jidoka-tests-") as folder:
            arguments = git_bash_command(test_script(command, Path(folder)), shutil.which("git"), os.environ)
            return subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace")
    except OSError as error:
        raise CommandError(f"cannot run the tests: {error}") from error


def run_finished(command: str, cwd: Path) -> Finished:
    """Runs a test command line, as run_test_command does, and gives how it exited and what it printed: standard output,
    then standard error. A newline separates them when standard output ends without one, because the summary lines
    that runner_summary reads are anchored at the start of a line."""
    done = run_test_command(command, cwd)
    separator = "\n" if done.stdout and not done.stdout.endswith("\n") else ""
    return Finished(done.returncode, f"{done.stdout}{separator}{done.stderr}")
