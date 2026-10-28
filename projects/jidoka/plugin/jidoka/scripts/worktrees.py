"""The git steps on a worktree that laps, passes, validation and the landing gate share: where a worktree goes, hiding
the worktree folder from git, cutting a detached worktree with the main checkout's private docs, removing one, and
staging what a worker left outside the scratch folder."""
from __future__ import annotations

from pathlib import Path

import git_exclude
import private_docs
from commands import SCRATCH_FOLDER, WORKTREE_FOLDER, capture, env_as_factory, run

WORKTREE_EXCLUDE_LINE = f"{WORKTREE_FOLDER}/"


def stage_worktree(prefix: str, bead: str, main_tree: Path) -> Path:
    """The folder of a worktree that a stage, a lap or the landing cuts for the bead, named by the stage's prefix."""
    return main_tree / WORKTREE_FOLDER / f"{prefix}{bead}"


def hide_worktrees(main_tree: Path) -> None:
    git_exclude.add(git_exclude.exclude_file(main_tree), [WORKTREE_EXCLUDE_LINE])


def remove_worktree(path: Path, main_tree: Path) -> None:
    capture(["git", "worktree", "remove", "--force", str(path)], main_tree, None)


def cut_detached(path: Path, head: str, home: Path, main_tree: Path) -> None:
    """Cuts a detached worktree at the head and links the main checkout's private docs into it. When a private path
    clashes, it removes the worktree again and raises private_docs.ClashError."""
    hide_worktrees(main_tree)
    run(["git", "worktree", "add", "-q", "--detach", str(path), head], main_tree, None)
    try:
        private_docs.share(main_tree, path.resolve(), home)
    except private_docs.ClashError:
        remove_worktree(path, main_tree)
        raise


def stage_without_scratch(worktree: Path) -> list[str]:
    """Stages everything the worktree changed from its head except the scratch folder, and returns the staged paths,
    sorted."""
    env = env_as_factory()
    run(["git", "add", "--all"], worktree, env)
    run(["git", "reset", "--quiet", "--", SCRATCH_FOLDER], worktree, env)
    return sorted(run(["git", "diff", "--cached", "--name-only"], worktree, env).splitlines())
