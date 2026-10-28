"""What the stages of a pass share: the epic branch they move forward, the files of the epic they may touch, the
worktree a stage's worker edits and the one call that settles it as a commit, the tasks they file in the epic with the
shape of a finding's report and of a title, and the way they park the epic on the human.

The `Stage` record configures a stage whose worker edits files in a detached worktree of its own, as the test cleanup,
the tidy and the review's fix do, so that those stages share one skeleton: what is owed, the read of it that cuts no
worktree, the cut, and the settle that refuses a worktree the worker no longer holds.

No stage owns these. Each stage keeps its own metadata keys in its own module, and this module holds no key.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import caps
import git_exclude
import lap_record
import park
import private_docs
from bench import WORKTREE_FOLDER, hide_worktrees
from caps import metadata_of
from commands import SCRATCH_FOLDER, capture, env_as_factory, head_of, run, set_metadata
from land import acquire_lock, edited_paths, merge_lock, release_lock
from merge_gate import checked_out_branch, protected_folders

MAIN_BRANCH = "main"
TITLE_LIMIT = 80
OUTPUT_TAIL_LINES = 40
TEXT_FIELDS = ("file", "title", "note")
LEAST_LINE = 1
DONE = "done"


class PassError(Exception):
    """A reason a stage writes nothing more, worded for the person who reads stderr. Each stage raises a subclass of
    its own, so one except clause takes them all."""


def count_of(shown: dict, key: str) -> int:
    """The whole number the epic's metadata holds under the key, or none when it holds nothing."""
    try:
        return caps.count_in(metadata_of(shown), key)
    except caps.NotAWholeNumber as error:
        raise PassError(f"on the epic, {error}") from error


@dataclass(frozen=True)
class Stage:
    """A stage of a pass whose worker edits files in a detached worktree of its own: its name in a refusal, the
    action it prints, the prefix of its worktree's folder, the metadata key that records it done (none for a stage that
    is owed by other means), the commit it settles with, which files of the epic it may touch and how the action
    names them, the report its worker writes in the scratch folder (none when the stage has no report), and the error
    it raises."""
    name: str
    action: str
    prefix: str
    state_key: str | None
    commit_message: str
    allowed_kind: str
    files_key: str
    wants: Callable[[str], bool]
    report: str | None
    error: type[PassError]

    def worktree_of(self, epic: str, main_tree: Path) -> Path:
        return main_tree / WORKTREE_FOLDER / f"{self.prefix}{epic}"

    def is_done(self, shown: dict) -> bool:
        return self.state_key is not None and metadata_of(shown).get(self.state_key) == DONE


@dataclass(frozen=True)
class StageToRun:
    """What a stage owes: the commit its worker starts from, the worktree where one belongs, and the files it may
    touch."""
    stage: Stage
    epic: str
    branch: str
    head: str
    worktree: Path
    files: list[str]

    @property
    def scratch(self) -> Path:
        return self.worktree / SCRATCH_FOLDER

    def fields(self) -> dict:
        printed = {"action": self.stage.action, "epic": self.epic, "branch": self.branch, "head": self.head,
                   "worktree": str(self.worktree), "scratch": str(self.scratch)}
        if self.stage.report is not None:
            printed["report"] = str(self.scratch / self.stage.report)
        printed[self.stage.files_key] = self.files
        return printed


@dataclass(frozen=True)
class Committed:
    """What settling a stage's worktree did: the commit the epic branch now ends with, or its old head when the worker
    changed nothing, and the paths the commit changed."""
    head: str
    changed: list[str]


def every_file(path: str) -> bool:
    return True


def accepts_any_change(changed: list[str]) -> None:
    """The check of a stage whose worker reports nothing that the change must agree with."""


def owed(stage: Stage, epic: str, shown: dict, branch: str, settings: dict, main_tree: Path) -> StageToRun | None:
    """The stage this pass still owes, or None when it is done or the epic holds no file for it. It cuts no worktree:
    the path in the result is where one belongs."""
    if stage.is_done(shown):
        return None
    head = head_of(f"refs/heads/{branch}", main_tree)
    if head is None:
        raise stage.error(f"the epic branch {branch} does not exist")
    files = [path for path in epic_files(head, settings, main_tree) if stage.wants(path)]
    if not files:
        return None
    return StageToRun(stage, epic, branch, head, stage.worktree_of(epic, main_tree), files)


def to_run(stage: Stage, epic: str, shown: dict, branch: str, settings: dict, home: Path,
           main_tree: Path) -> StageToRun | None:
    """The stage this pass still owes, with its worktree cut at the epic branch's head for the worker."""
    found = owed(stage, epic, shown, branch, settings, main_tree)
    if found is not None:
        worktree_at(found.worktree, found.head, home, main_tree)
    return found


def refuse_a_lost_worktree(found: StageToRun) -> None:
    """Refuses to settle a worktree that is gone or at another head than the one the worker started from, because a
    fresh cut would hold none of the worker's edits."""
    if not found.worktree.is_dir() or head_of("HEAD", found.worktree) != found.head:
        raise found.stage.error(f"the worktree {found.worktree} of the {found.stage.name} is gone or is not at "
                                f"{found.head}, so the worker's edits are not in it and nothing was written")


def owed_in_worktree(stage: Stage, epic: str, shown: dict, branch: str, settings: dict,
                     main_tree: Path) -> StageToRun:
    """The stage a worker's report settles, read without cutting a worktree. It refuses when the stage is owed no
    more, or when its worktree is gone or at another head."""
    found = owed(stage, epic, shown, branch, settings, main_tree)
    if found is None:
        raise stage.error(f"{epic} waits on no {stage.name}, so nothing was written")
    refuse_a_lost_worktree(found)
    return found


def settle_worktree(found: StageToRun, check: Callable[[list[str]], None], home: Path, main_tree: Path) -> Committed:
    """Takes what the stage's worker left in its worktree: stages it, refuses a path the stage may not touch, lets
    `check` refuse the changed paths, commits them as one commit, moves the epic branch to it and removes the
    worktree. Nothing is committed when nothing changed."""
    changed = changed_within(found.worktree, found.files, found.stage.name, found.stage.allowed_kind)
    check(changed)
    head = found.head
    if changed:
        run(["git", "commit", "--quiet", "--message", found.stage.commit_message], found.worktree, env_as_factory())
        head = head_of("HEAD", found.worktree) or found.head
        move_epic_branch(found.branch, found.head, head, home, main_tree)
    remove_worktree(found.worktree, main_tree)
    return Committed(head, changed)


def tail_of(output: str) -> str:
    """The last lines of a command's output, which is where a failure says what went wrong."""
    return "\n".join(output.strip().splitlines()[-OUTPUT_TAIL_LINES:])


def shortened_title(text: str) -> str:
    """The text cut to TITLE_LIMIT characters, with an ellipsis where it was cut."""
    return text if len(text) <= TITLE_LIMIT else f"{text[:TITLE_LIMIT - 3].rstrip()}..."


def created_id(created: str) -> str:
    """The id `bd create --json` printed for the bead it made."""
    try:
        return str(json.loads(created)["id"])
    except (ValueError, KeyError, TypeError) as error:
        raise PassError(f"bd create did not print the id of the bead it made: {created.strip()[:200]!r}") from error


def located_texts(value: object, where: str, shape: str) -> tuple[dict[str, str], int]:
    """The file, title and note, trimmed, and the line of one finding in a report.

    `where` names the finding in a refusal, and `shape` lists the fields its object must hold.
    """
    if not isinstance(value, dict):
        raise PassError(f"{where} must be an object with {shape}")
    texts = {}
    for field in TEXT_FIELDS:
        text = value.get(field)
        if not isinstance(text, str) or not text.strip():
            raise PassError(f"{where} must name its {field}")
        texts[field] = text.strip()
    line = value.get("line")
    if not isinstance(line, int) or isinstance(line, bool) or line < LEAST_LINE:
        raise PassError(f"the line of {where} must be a whole number from {LEAST_LINE}, not {line!r}")
    return texts, line


def epic_files(branch_head: str, settings: dict, main_tree: Path) -> list[str]:
    """The files the epic added or changed, outside every acceptance folder, sorted."""
    folders = protected_folders(settings)
    listed = run(["git", "diff", "--name-only", "--diff-filter=AM", f"{MAIN_BRANCH}...{branch_head}"], main_tree,
                 None).splitlines()
    return sorted(path for path in listed
                  if not any(folder == PurePosixPath(path) or folder in PurePosixPath(path).parents
                             for folder in folders))


def changed_paths(worktree: Path) -> list[str]:
    """Every path the worktree changed from its head, outside the scratch folder."""
    env = env_as_factory()
    run(["git", "add", "--all"], worktree, env)
    run(["git", "reset", "--quiet", "--", SCRATCH_FOLDER], worktree, env)
    return sorted(run(["git", "diff", "--cached", "--name-only"], worktree, env).splitlines())


def park_epic(epic: str, comment: str, metadata: dict[str, str], main_tree: Path) -> None:
    """Parks the epic on the human: the comment says why, the metadata is set, and the human label goes on last, so a
    labeled epic always has its comment."""
    env = env_as_factory()
    run(["bd", "comment", epic, comment], main_tree, env)
    run(["bd", "update", epic, *set_metadata(*metadata.items()), f"--add-label={park.HUMAN_LABEL}"], main_tree, env)


def remove_worktree(path: Path, main_tree: Path) -> None:
    capture(["git", "worktree", "remove", "--force", str(path)], main_tree, None)


def worktree_at(path: Path, head: str, home: Path, main_tree: Path) -> None:
    """Cuts the detached worktree at the head, again when it holds another commit, with its scratch folder."""
    if path.is_dir() and head_of("HEAD", path) != head:
        remove_worktree(path, main_tree)
    if not path.is_dir():
        capture(["git", "worktree", "prune"], main_tree, None)
        hide_worktrees(main_tree)
        run(["git", "worktree", "add", "-q", "--detach", str(path), head], main_tree, None)
        try:
            private_docs.share(main_tree, path.resolve(), home)
        except private_docs.ClashError as error:
            remove_worktree(path, main_tree)
            raise PassError(str(error)) from error
    git_exclude.add(git_exclude.exclude_file(main_tree), [git_exclude.exclude_line(SCRATCH_FOLDER, True)])
    (path / SCRATCH_FOLDER).mkdir(exist_ok=True)


def changed_within(worktree: Path, allowed: list[str], stage: str, allowed_kind: str) -> list[str]:
    """Every path the stage's worktree changed, refusing when one is not among the allowed paths. `stage` and
    `allowed_kind` word the refusal."""
    changed = changed_paths(worktree)
    stray = [path for path in changed if path not in allowed]
    if stray:
        raise PassError(f"the {stage} changed paths that are not {allowed_kind}: {', '.join(stray)}, so nothing was "
                        "written")
    return changed


def move_epic_branch(branch: str, old: str, new: str, home: Path, main_tree: Path) -> None:
    """Fast-forwards the epic branch from old to new under the merge lock, bringing the main checkout along."""
    if old == new:
        return
    lock = merge_lock(home)
    acquire_lock(lock)
    try:
        checked_out = checked_out_branch(main_tree) == branch
        if checked_out:
            edited = sorted(edited_paths(main_tree))
            if edited:
                raise PassError(f"the main checkout {main_tree} has {branch} checked out with uncommitted "
                                f"edits: {', '.join(edited)}. Commit or discard them, then run the "
                                "scheduler again")
        done = capture(["git", "update-ref", f"refs/heads/{branch}", new, old], main_tree, None)
        if done.returncode != 0:
            raise PassError(f"{branch} moved from {old} while a stage ran, so nothing changed. Run the scheduler "
                            f"again: {done.stderr.strip()}")
        if checked_out:
            run(["git", "read-tree", "-m", "-u", old, new], main_tree, None)
    finally:
        release_lock(lock)


def file_task(epic: str, title: str, description: str, area: str, main_tree: Path) -> str:
    """Files a task in the epic with the track and area the scheduler needs to open its lap."""
    env = env_as_factory()
    created = run(["bd", "create", "--title", title, "--type", "task", "--parent", epic, "--description",
                   description, "--json"], main_tree, env)
    task = created_id(created)
    run(["bd", "update", task, *lap_record.assigning(lap_record.SIMPLE_TRACK, area)], main_tree, env)
    return task
