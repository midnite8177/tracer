"""Lands an epic on main as one commit for each task, with the pass's own commits folded into the tasks' commits.

The epic branch holds one commit for each task, which the merge gate put there, and the commits the pass's stages added
after them (the test cleanup, the tidy, the fix worker). Each task's commit is found by the sha that the merge gate
wrote in the task's close reason. Each path the epic changed belongs to the last task commit that touched it; a path
no task commit touched belongs to the last task commit. A commit on main carries its task's message and holds each
path it owns as the epic's final tree has it, and each path another task commit owns later as that task commit left
it, so the last commit's tree is the tree the epic branch merged onto main would have.
"""
from __future__ import annotations

from pathlib import Path

from commands import MAIN_REF, capture, run
from epic_reader import child_ids, shown_beads


def merged_task_commits(epic: str, branch: str, main_tree: Path) -> list[str]:
    """The task commits the epic branch holds that main lacks, oldest first."""
    recorded = {str(child.get("close_reason") or "").partition(":")[0].strip()
                for child in shown_beads(child_ids(epic, main_tree), main_tree)}
    listed = run(["git", "log", "--no-merges", "--topo-order", "--reverse", "--format=%H",
                  f"{MAIN_REF}..refs/heads/{branch}"], main_tree, None).split()
    return [commit for commit in listed if commit in recorded]


def paths_between(old: str, new: str, worktree: Path) -> list[str]:
    """The paths that differ between two commits or trees, a rename counted as a deletion and an addition."""
    listed = run(["git", "diff", "--name-only", "--no-renames", "-z", old, new], worktree, None)
    return [path for path in listed.split("\0") if path]


def has_path(source: str, path: str, worktree: Path) -> bool:
    return capture(["git", "cat-file", "-e", f"{source}:{path}"], worktree, None).returncode == 0


def take_paths(source: str, paths: list[str], worktree: Path) -> None:
    """Stages each path as the commit or tree has it, and stages the deletion of each path it lacks."""
    present = [path for path in paths if has_path(source, path, worktree)]
    absent = [path for path in paths if path not in present]
    if present:
        run(["git", "--literal-pathspecs", "checkout", source, "--", *present], worktree, None)
    if absent:
        run(["git", "--literal-pathspecs", "rm", "-q", "-f", "--ignore-unmatch", "--", *absent], worktree, None)


def owners_of(touched: list[list[str]], final_paths: list[str]) -> dict[str, int]:
    """For each path the epic changed, the index of the task commit that owns it."""
    owners: dict[str, int] = {}
    for index, paths in enumerate(touched):
        for path in paths:
            owners[path] = index
    for path in final_paths:
        owners.setdefault(path, len(touched) - 1)
    return owners


def commit_per_task(epic: str, branch: str, worktree: Path, main_tree: Path, error: type[Exception]) -> str:
    """Commits the epic once for each task in the worktree, which is at main's head with the epic branch squashed into
    its index; returns the last commit, whose tree is the squashed tree."""
    commits = merged_task_commits(epic, branch, main_tree)
    if not commits:
        raise error(f"{branch} holds no commit of a task that main lacks, so there is no commit to land for a task")
    final = run(["git", "write-tree"], worktree, None).strip()
    run(["git", "reset", "-q", "--hard"], worktree, None)
    touched = [paths_between(f"{commit}^", commit, worktree) for commit in commits]
    owners = owners_of(touched, paths_between("HEAD", final, worktree))
    for index, commit in enumerate(commits):
        sources: dict[str, list[str]] = {}
        for path in touched[index]:
            sources.setdefault(final if owners[path] == index else commit, []).append(path)
        sources.setdefault(final, []).extend(path for path, owner in owners.items()
                                             if owner == index and path not in touched[index])
        for source, paths in sources.items():
            take_paths(source, paths, worktree)
        if capture(["git", "diff", "--cached", "--quiet"], worktree, None).returncode == 0:
            continue
        message = run(["git", "log", "-1", "--format=%B", commit], worktree, None)
        run(["git", "commit", "-q", "-m", message.rstrip()], worktree, None)
    if run(["git", "rev-parse", "HEAD^{tree}"], worktree, None).strip() != final:
        raise error(f"the commits for the tasks of {epic} do not add up to the epic branch's tree, so nothing landed")
    return run(["git", "rev-parse", "HEAD"], worktree, None).strip()
