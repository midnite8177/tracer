"""How a process is looked at and ended on Windows, through the Win32 calls that Python's os module does not offer.

`os.kill` on Windows ends the process whatever the signal, and there are no process groups, so `processes.py` calls
this module for the Windows side of each question: whether a process runs, when it began, which processes are
orphans in a folder, and ending a process with the processes it started. Only the functions that call Win32 need
Windows; the DLLs load when one of them runs.
"""
from __future__ import annotations

import ctypes
import subprocess
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

STILL_ACTIVE = 259
ERROR_ACCESS_DENIED = 5
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x2
PEB_PROCESS_PARAMETERS = 0x20
PARAMETERS_CURRENT_DIRECTORY = 0x38
TASKKILL_TIMEOUT_SECONDS = 30
END_WAIT_SECONDS = 10.0
END_POLL_SECONDS = 0.05


@dataclass(frozen=True)
class Entry:
    """One row of the process table: the process that started it, and the moment this one began, as a FILETIME."""
    parent: int
    created: int | None


class ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260)]


class ProcessBasicInformation(ctypes.Structure):
    _fields_ = [("Reserved1", ctypes.c_void_p), ("PebBaseAddress", ctypes.c_void_p),
                ("Reserved2", ctypes.c_void_p * 2), ("UniqueProcessId", ctypes.c_void_p),
                ("Reserved3", ctypes.c_void_p)]


class UnicodeString(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ushort), ("MaximumLength", ctypes.c_ushort), ("Buffer", ctypes.c_void_p)]


def kernel32():
    library = ctypes.WinDLL("kernel32", use_last_error=True)
    library.OpenProcess.restype = wintypes.HANDLE
    library.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    library.CloseHandle.argtypes = [wintypes.HANDLE]
    library.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    library.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                                        ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
                                        ctypes.POINTER(wintypes.FILETIME)]
    library.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    library.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    library.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    library.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    library.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                          ctypes.POINTER(ctypes.c_size_t)]
    return library


def is_alive(pid: int) -> bool:
    library = kernel32()
    handle = library.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ctypes.get_last_error() == ERROR_ACCESS_DENIED
    try:
        code = wintypes.DWORD()
        return bool(library.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == STILL_ACTIVE
    finally:
        library.CloseHandle(handle)


def created_at(pid: int) -> int | None:
    """The FILETIME at which the process began, or None when no such process can be read."""
    library = kernel32()
    handle = library.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not library.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel),
                                       ctypes.byref(user)):
            return None
        return (created.dwHighDateTime << 32) | created.dwLowDateTime
    finally:
        library.CloseHandle(handle)


def started_at(pid: int) -> str | None:
    created = created_at(pid)
    return None if created is None else str(created)


def process_table() -> dict[int, Entry]:
    """Every running process by id, with its parent and the moment it began."""
    library = kernel32()
    snapshot = library.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    parents: dict[int, int] = {}
    entry = ProcessEntry()
    entry.dwSize = ctypes.sizeof(ProcessEntry)
    more = library.Process32FirstW(snapshot, ctypes.byref(entry))
    while more:
        parents[entry.th32ProcessID] = entry.th32ParentProcessID
        more = library.Process32NextW(snapshot, ctypes.byref(entry))
    library.CloseHandle(snapshot)
    return {pid: Entry(parent, created_at(pid)) for pid, parent in parents.items()}


def living_parent(table: dict[int, Entry], entry: Entry) -> Entry | None:
    """The entry's parent, or None when the parent is gone. Windows keeps the parent id after the parent ends, so a
    parent that the table lacks, or that began after its child, is a process that ended and whose id another process
    took."""
    parent = table.get(entry.parent)
    if parent is None:
        return None
    if parent.created is not None and entry.created is not None and entry.created < parent.created:
        return None
    return parent


def orphans_of(table: dict[int, Entry]) -> list[int]:
    """The processes whose parent is gone."""
    return sorted(pid for pid, entry in table.items() if living_parent(table, entry) is None)


def current_folder_of(pid: int) -> Path | None:
    """The working folder of a 64-bit process, read from its process parameters; None when it cannot be read."""
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        return None
    library = kernel32()
    ntdll = ctypes.WinDLL("ntdll")
    handle = library.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        return None
    try:
        basic = ProcessBasicInformation()
        returned = wintypes.ULONG()
        if ntdll.NtQueryInformationProcess(handle, 0, ctypes.byref(basic), ctypes.sizeof(basic),
                                           ctypes.byref(returned)) != 0 or not basic.PebBaseAddress:
            return None
        parameters = ctypes.c_void_p()
        read = ctypes.c_size_t()
        if not library.ReadProcessMemory(handle, basic.PebBaseAddress + PEB_PROCESS_PARAMETERS,
                                         ctypes.byref(parameters), ctypes.sizeof(parameters), ctypes.byref(read)) \
                or not parameters.value:
            return None
        folder = UnicodeString()
        if not library.ReadProcessMemory(handle, parameters.value + PARAMETERS_CURRENT_DIRECTORY,
                                         ctypes.byref(folder), ctypes.sizeof(folder), ctypes.byref(read)) \
                or not folder.Buffer or not folder.Length:
            return None
        text = ctypes.create_unicode_buffer(folder.Length // 2)
        if not library.ReadProcessMemory(handle, folder.Buffer, text, folder.Length, ctypes.byref(read)):
            return None
        return Path(text.value)
    finally:
        library.CloseHandle(handle)


def orphans_with_cwd_in(worktree: Path, own_pid: int) -> list[int]:
    """The orphan processes whose working folder is the worktree or a folder under it, this one left out."""
    root = worktree.resolve()
    found = []
    for pid in orphans_of(process_table()):
        if pid == own_pid:
            continue
        folder = current_folder_of(pid)
        if folder is not None and (folder == root or root in folder.parents):
            found.append(pid)
    return found


def descendants_of(table: dict[int, Entry], root: int) -> list[int]:
    """The processes that the root started, and those they started, in order of id."""
    children: dict[int, list[int]] = {}
    for pid, entry in table.items():
        if living_parent(table, entry) is not None:
            children.setdefault(entry.parent, []).append(pid)
    found: set[int] = set()
    pending = [root]
    while pending:
        for child in children.get(pending.pop(), []):
            if child != root and child not in found:
                found.add(child)
                pending.append(child)
    return sorted(found)


def end_tree(pid: int) -> None:
    """Ends the process and the processes it started, and returns once they are gone or END_WAIT_SECONDS have passed.
    A process without a window cannot be asked to close, so the end is forced.

    taskkill returns when it has asked for the end, and the files a process holds stay held until the process is
    gone. A caller that starts the app again, or removes its folder, right after would meet a log or a folder still
    held.
    """
    tree = [pid, *descendants_of(process_table(), pid)]
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       timeout=TASKKILL_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return
    deadline = time.monotonic() + END_WAIT_SECONDS
    while any(is_alive(member) for member in tree) and time.monotonic() < deadline:
        time.sleep(END_POLL_SECONDS)
