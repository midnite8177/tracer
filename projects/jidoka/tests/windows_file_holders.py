"""Which processes hold a file open, asked of the Windows Restart Manager, which names the processes that keep a file
from being deleted whatever their working folder is. Only `holders_of` and `holders_under` need Windows; the DLL loads when it runs.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

ERROR_MORE_DATA = 234
SESSION_KEY_LENGTH = 32
FILES_PER_REGISTRATION = 200


class UniqueProcess(ctypes.Structure):
    _fields_ = [("dwProcessId", wintypes.DWORD), ("ProcessStartTime", wintypes.FILETIME)]


class ProcessInfo(ctypes.Structure):
    _fields_ = [("Process", UniqueProcess), ("strAppName", wintypes.WCHAR * 256),
                ("strServiceShortName", wintypes.WCHAR * 64), ("ApplicationType", ctypes.c_int),
                ("AppStatus", wintypes.ULONG), ("TSSessionId", wintypes.DWORD), ("bRestartable", wintypes.BOOL)]


def files_under(folder: Path) -> list[str]:
    """Every file under the folder, as a path string."""
    return [os.path.join(where, name) for where, _, names in os.walk(folder) for name in names]


def holders_under(folder: Path) -> set[int]:
    """The ids of the processes that hold any file under the folder open."""
    return holders_of(files_under(folder))


def holders_of(files: list[str]) -> set[int]:
    """The ids of the processes that hold any of the files open. A file that cannot be asked about is left out."""
    if not files:
        return set()
    library = ctypes.WinDLL("rstrtmgr")
    session = wintypes.DWORD()
    key = ctypes.create_unicode_buffer(SESSION_KEY_LENGTH + 1)
    if library.RmStartSession(ctypes.byref(session), 0, key) != 0:
        return set()
    try:
        for start in range(0, len(files), FILES_PER_REGISTRATION):
            chunk = files[start:start + FILES_PER_REGISTRATION]
            names = (wintypes.LPCWSTR * len(chunk))(*chunk)
            if library.RmRegisterResources(session, len(chunk), names, 0, None, 0, None) != 0:
                return set()
        needed = wintypes.UINT(0)
        given = wintypes.UINT(0)
        reasons = wintypes.DWORD()
        found = library.RmGetList(session, ctypes.byref(needed), ctypes.byref(given), None, ctypes.byref(reasons))
        while found == ERROR_MORE_DATA:
            given = wintypes.UINT(needed.value)
            table = (ProcessInfo * given.value)()
            found = library.RmGetList(session, ctypes.byref(needed), ctypes.byref(given), table,
                                      ctypes.byref(reasons))
            if found == 0:
                return {table[index].Process.dwProcessId for index in range(given.value)}
        return set()
    finally:
        library.RmEndSession(session)
