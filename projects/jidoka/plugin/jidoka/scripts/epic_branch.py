"""The epic branch in the main checkout: its head, which branch the checkout has out, and the one fast-forward that a
lap's merge gate and a pass stage both make. The caller holds the merge lock."""
from __future__ import annotations

from pathlib import Path

from commands import CommandError, capture, head_of, run
from land import edited_paths


class EpicBranchMoved(Exception):
    """The epic branch is not where a caller read it, so what the caller meant to do from that head did not happen."""


class EpicBranchLeftTheHead(EpicBranchMoved):
    """git update-ref refused to move the branch from `old` to `new`, because the branch is no longer at `old`."""

    def __init__(self, branch: str, old: str, new: str) -> None:
        super().__init__(f"{branch} moved from {old}")
        self.branch = branch
        self.old = old
        self.new = new


class EditedCheckout(Exception):
    """The main checkout has the branch out with uncommitted edits, which a move of the branch would overwrite."""

    def __init__(self, branch: str, main_tree: Path, edited: list[str]) -> None:
        super().__init__(f"the main checkout {main_tree} has {branch} checked out with uncommitted edits: "
                         f"{', '.join(edited)}")


def branch_head(branch: str, tree: Path) -> str | None:
    """The sha the branch points at, or None when the repo has no such branch."""
    return head_of(f"refs/heads/{branch}", tree)


def required_head(branch: str, tree: Path, error: type[Exception]) -> str:
    """The sha the epic branch points at; raises the caller's error when the branch does not exist."""
    head = branch_head(branch, tree)
    if head is None:
        raise error(f"the epic branch {branch} does not exist")
    return head


def checked_out_branch(tree: Path) -> str:
    done = capture(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], tree, None)
    return done.stdout.strip() if done.returncode == 0 else ""


def refuse_edited_checkout(branch: str, main_tree: Path) -> None:
    """Raises EditedCheckout when the main checkout has the branch out and holds uncommitted edits."""
    if checked_out_branch(main_tree) == branch:
        edited = sorted(edited_paths(main_tree))
        if edited:
            raise EditedCheckout(branch, main_tree, edited)


def fast_forward(branch: str, old: str, new: str, main_tree: Path) -> None:
    """Moves the branch from old to new with git update-ref, which refuses when the branch has left old, and brings
    the main checkout along when it has the branch checked out.

    A branch that has left old raises EpicBranchLeftTheHead, and the caller words its refusal.
    """
    done = capture(["git", "update-ref", f"refs/heads/{branch}", new, old], main_tree, None)
    if done.returncode != 0:
        if branch_head(branch, main_tree) != old:
            raise EpicBranchLeftTheHead(branch, old, new)
        raise CommandError(f"git update-ref {branch} failed: {done.stderr.strip()}")
    if checked_out_branch(main_tree) == branch:
        run(["git", "read-tree", "-m", "-u", old, new], main_tree, None)
