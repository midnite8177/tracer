"""Runs the git, bd and test commands that jidoka's scripts call, with failures worded for the person who reads the
output, and holds what the scripts read from a bead and from the repo's layout: its labels, parent and metadata, the
factory's labels, the worktree folder and the main ref."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

COMMAND_TIMEOUT_SECONDS = 120
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


def capture(args: list[str], cwd: Path, env: dict[str, str] | None) -> subprocess.CompletedProcess:
    """Runs the command in env, or in the inherited environment when env is None."""
    try:
        return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=COMMAND_TIMEOUT_SECONDS)
    except OSError as error:
        raise CommandError(f"cannot run {args[0]}: {error}") from error
    except subprocess.TimeoutExpired as error:
        raise CommandError(f"{' '.join(args[:3])} did not finish in {COMMAND_TIMEOUT_SECONDS} seconds") from error


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


def bd_show(bead: str, cwd: Path) -> dict | None:
    """The bead as bd show --json prints it, or None when the output holds no bead.

    A caller that goes on without the bead takes None. A caller that needs the bead calls read_bead.
    """
    output = run(["bd", "show", bead, "--json"], cwd, None)
    try:
        parsed = json.loads(output)
    except ValueError:
        return None
    if not isinstance(parsed, list) or not parsed or not isinstance(parsed[0], dict):
        return None
    return parsed[0]


def read_bead(bead: str, cwd: Path) -> dict:
    """The bead as bd show --json prints it; raises CommandError when the output holds no bead."""
    shown = bd_show(bead, cwd)
    if shown is None:
        raise CommandError(f"bd show printed nothing usable for {bead}")
    return shown


def printed_beads(args: list[str], cwd: Path) -> list[dict]:
    """The objects in the JSON list that the bd command prints, an empty list when it prints nothing.

    Output that is not a JSON list raises CommandError.
    """
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
    return printed_beads(["bd", "comments", bead, "--json"], cwd)


def run_test_command(command: str, cwd: Path) -> subprocess.CompletedProcess:
    """Runs a test command line from the repo settings through the shell.

    It has no timeout, because a test suite can run far longer than any git or bd command.
    """
    try:
        return subprocess.run(command, cwd=cwd, shell=True, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as error:
        raise CommandError(f"cannot run the tests: {error}") from error
