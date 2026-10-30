"""Starting a process detached, and asking after it and ending it, the same way on macOS, Linux and Windows.

macOS and Linux start a process in a session of its own, and end it with SIGTERM and then SIGKILL, to the whole
process group when the process leads one. Windows has neither sessions nor groups to signal, so a process starts with
no window and no console of its caller, and `taskkill` ends it with the processes it started.

A "group" below is the id of the process that leads the app. On macOS and Linux it is a process group, which
outlives its leader and is ended whole. On Windows it is only the id of the root of a process tree: `taskkill`
reaches the processes the root started while the root runs, and none of them once the root has ended, and
`group_is_alive` there says whether the root runs. A caller treats a group as the id of its leader and assumes
nothing more of it.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import windows_processes
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, capture

_WINDOWS = os.name == "nt"
INIT_PROCESS = 1
STOP_WAIT_SECONDS = 3.0
STOP_POLL_SECONDS = 0.05
CREATE_NEW_PROCESS_GROUP = 0x200
CREATE_NO_WINDOW = 0x08000000


def detached_options() -> dict[str, Any]:
    """The Popen options that start a process which the caller's session or console never holds."""
    if _WINDOWS:
        return {"creationflags": CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW}
    return {"start_new_session": True}


def signal_reaches(kill: Callable[[int, int], None], target: int) -> bool:
    """True when signal 0 sent with `kill` finds the target. A refusal for lack of permission counts too, since the target exists."""
    try:
        kill(target, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def is_alive(pid: int) -> bool:
    if _WINDOWS:
        return windows_processes.is_alive(pid)
    return signal_reaches(os.kill, pid)


def started_at(pid: int) -> str | None:
    """The moment the process began, as text that is the same each time it is asked; None when no such process runs."""
    if _WINDOWS:
        return windows_processes.started_at(pid)
    try:
        done = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                              timeout=COMMAND_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None


def own_group() -> int:
    return os.getpid() if _WINDOWS else os.getpgrp()


def group_is_alive(group: int) -> bool:
    if _WINDOWS:
        return windows_processes.is_alive(group)
    return signal_reaches(os.killpg, group)


def end_after_wait(send: Callable[[int], None], is_there: Callable[[], bool]) -> None:
    send(signal.SIGTERM)
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    while is_there() and time.monotonic() < deadline:
        time.sleep(STOP_POLL_SECONDS)
    if is_there():
        send(signal.SIGKILL)


def end_with_signals(kill: Callable[[int, int], None], target: int) -> None:
    """Sends the target SIGTERM and then SIGKILL through `kill`, which is `os.kill` for a process and `os.killpg`
    for a group."""

    def send(signal_number: int) -> None:
        try:
            kill(target, signal_number)
        except ProcessLookupError:
            return

    end_after_wait(send, lambda: signal_reaches(kill, target))


def end_group(group: int) -> None:
    """Ends the group with SIGTERM, then SIGKILL when it is still there after the wait; on Windows the process and
    its children at once."""
    if _WINDOWS:
        windows_processes.end_tree(group)
        return
    end_with_signals(os.killpg, group)


def end_process(pid: int) -> None:
    """Ends the process with SIGTERM, then SIGKILL when it is still there after the wait; on Windows it and its
    children at once."""
    if _WINDOWS:
        windows_processes.end_tree(pid)
        return
    end_with_signals(os.kill, pid)


def parent_of(pid: int) -> int | None:
    done = capture(["ps", "-o", "ppid=", "-p", str(pid)], Path.cwd(), None)
    try:
        return int(done.stdout.strip())
    except ValueError:
        return None


def pids_with_cwd_in(worktree: Path) -> list[int]:
    """The processes whose working folder is the worktree or a folder under it, as lsof lists them."""
    root = worktree.resolve()
    try:
        done = capture(["lsof", "-a", "-d", "cwd", "-Fpn"], Path.cwd(), None)
    except CommandError:
        return []
    found: list[int] = []
    pid: int | None = None
    for line in done.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n") and pid is not None:
            folder = Path(line[1:])
            if folder == root or root in folder.parents:
                found.append(pid)
    return found


def orphans_in(worktree: Path, own_pid: int) -> list[int]:
    """The orphan processes whose working folder is the worktree or a folder under it, `own_pid` left out. On macOS
    and Linux an orphan is a process whose parent is the init process. Windows keeps no init process to adopt
    them, so there it is a process whose parent has ended."""
    if _WINDOWS:
        return windows_processes.orphans_with_cwd_in(worktree, own_pid)
    return [pid for pid in pids_with_cwd_in(worktree) if pid != own_pid and parent_of(pid) == INIT_PROCESS]
