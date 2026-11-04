"""Process identity and termination: POSIX (plan 0002 T2) and Windows (T3); spec 0002 AC7, section 4.3.1.

`started_at` is an opaque string. On Linux it is `<boot id>:<start time>` where the boot id is
`/proc/sys/kernel/random/boot_id` and the start time is field 22 of `/proc/<pid>/stat` (proc(5)), in clock ticks
since boot, so a pid reused by a new process, or after a reboot, never compares equal. On Windows it is the creation
FILETIME of `GetProcessTimes` as a decimal integer.
"""

import errno
import os
import signal
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from ctypes import Structure, byref, c_int, c_size_t, c_uint16, c_uint32, c_void_p, create_unicode_buffer, sizeof
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

_PROC = Path("/proc")
_BOOT_ID = _PROC / "sys" / "kernel" / "random" / "boot_id"


@dataclass(frozen=True)
class ProcessIdentity:
    """A process as the operating system identifies it.

    Attributes:
        pid: Process id.
        started_at: Opaque OS creation time (see the module docstring); equal only for the same process.
        exe_name: Name of the program image (POSIX: the kernel's command name, at most 15 characters; Windows: the
            file name of the image).
    """

    pid: int
    started_at: str
    exe_name: str


class ProcessInspector(Protocol):
    """Port: reads and ends processes by identity, never by a bare pid."""

    def identity(self, pid: int) -> ProcessIdentity | None:
        """Return the identity of `pid`, or None when no such process exists."""

    def alive(self, identity: ProcessIdentity) -> bool:
        """Return True when the process with this pid and start time still runs."""

    def children(self, pid: int) -> list[ProcessIdentity]:
        """Return the direct children of `pid`."""

    def snapshot(self, exe_names: list[str]) -> list[ProcessIdentity]:
        """Return every running process whose `exe_name` is in `exe_names`."""

    def terminate(self, identity: ProcessIdentity) -> bool:
        """End the process only if pid and start time match; return True when it was signalled."""


class PosixProcessInspector:
    """`ProcessInspector` over `/proc`; development and Linux CI only (spec section 4.3.1)."""

    def __init__(self) -> None:
        self._boot_id = _BOOT_ID.read_text(encoding="ascii").strip()

    def _stat(self, pid: int) -> tuple[str, str, int, int, int] | None:
        """Return (comm, state, ppid, pgrp, start ticks) from `/proc/<pid>/stat`, or None when it is gone."""
        try:
            text = (_PROC / str(pid) / "stat").read_text(encoding="utf-8")
        except FileNotFoundError, ProcessLookupError:  # the process ended: a normal outcome
            return None
        # The command name sits in parentheses and may itself contain spaces and parentheses.
        comm = text[text.index("(") + 1 : text.rindex(")")]
        rest = text[text.rindex(")") + 2 :].split()  # field 3 (state) is rest[0]
        return comm, rest[0], int(rest[1]), int(rest[2]), int(rest[19])

    def _identity(self, pid: int) -> tuple[ProcessIdentity, str, int, int] | None:
        stat = self._stat(pid)
        if stat is None:
            return None
        comm, state, ppid, pgrp, ticks = stat
        return ProcessIdentity(pid, f"{self._boot_id}:{ticks}", comm), state, ppid, pgrp

    def identity(self, pid: int) -> ProcessIdentity | None:
        """Return the identity of `pid` (a zombie still has one), or None when no such process exists."""
        found = self._identity(pid)
        return None if found is None else found[0]

    def alive(self, identity: ProcessIdentity) -> bool:
        """Return True when pid and start time match and the process is not a zombie."""
        found = self._identity(identity.pid)
        return found is not None and found[0].started_at == identity.started_at and found[1] != "Z"

    def _scan(self) -> list[tuple[ProcessIdentity, str, int, int]]:
        found = (self._identity(int(entry.name)) for entry in _PROC.iterdir() if entry.name.isdigit())
        return [item for item in found if item is not None]

    def children(self, pid: int) -> list[ProcessIdentity]:
        """Return the direct children of `pid`, zombies excluded."""
        return [ident for ident, state, ppid, _ in self._scan() if ppid == pid and state != "Z"]

    def snapshot(self, exe_names: list[str]) -> list[ProcessIdentity]:
        """Return every running process whose command name is in `exe_names`, zombies excluded."""
        return [ident for ident, state, _, _ in self._scan() if ident.exe_name in exe_names and state != "Z"]

    def group_members(self, pgid: int) -> list[ProcessIdentity]:
        """Return the running processes of process group `pgid` (the POSIX "job"), zombies excluded."""
        return [ident for ident, state, _, pgrp in self._scan() if pgrp == pgid and state != "Z"]

    def terminate(self, identity: ProcessIdentity) -> bool:
        """Send SIGKILL (the equivalent of `TerminateProcess`) only when pid and start time match.

        A pidfd is opened first and the start time compared afterwards, so the signal reaches the process that was
        compared; without `pidfd_open` the check immediately precedes `kill`.

        Returns:
            True when the signal was sent; False when the process was gone or the pid belongs to another process.
        """
        pidfd: int | None = None
        if hasattr(os, "pidfd_open"):
            try:
                pidfd = os.pidfd_open(identity.pid)
            except ProcessLookupError:
                return False
            except OSError as exc:
                if exc.errno != errno.ENOSYS:  # a kernel without pidfd falls back to the checked kill
                    raise
        try:
            if not self.alive(identity):
                return False
            try:
                if pidfd is None:
                    os.kill(identity.pid, signal.SIGKILL)
                else:
                    signal.pidfd_send_signal(pidfd, signal.SIGKILL)
            except ProcessLookupError:
                return False
            return True
        finally:
            if pidfd is not None:
                os.close(pidfd)


# ---- Windows (spec 0002 section 4.3.1): the same rules over a kernel32 object, so they also run against a fake ------
# Software constants of winnt.h, winerror.h and tlhelp32.h; Win32 pages "Process Security and Access Rights",
# "WaitForSingleObject" and "Maximum Path Length Limitation".
PROCESS_TERMINATE, PROCESS_QUERY_LIMITED_INFORMATION, SYNCHRONIZE = 0x0001, 0x1000, 0x00100000
WAIT_OBJECT_0, WAIT_TIMEOUT = 0, 0x102
ERROR_NO_MORE_FILES, ERROR_INVALID_PARAMETER = 18, 87  # the end of a walk; OpenProcess for a pid no process has
TH32CS_SNAPPROCESS, KILLED_EXIT_CODE = 0x2, 1  # a terminated process gets any exit code but STILL_ACTIVE (259)
IMAGE_NAME_CHARS = 32767  # the longest extended-length path
INVALID_HANDLE_VALUE = (1 << 8 * sizeof(c_void_p)) - 1
BOOL, DWORD, HANDLE, WORD = c_int, c_uint32, c_void_p, c_uint16  # Win32 type names; a pointer is a HANDLE

type Signatures = Mapping[str, tuple[list[Any], Any]]  # kernel32 function -> (argtypes, restype)
type Kernel32 = Any  # a kernel32 library object: `CtypesKernel32`, or a test fake serving the same functions

PROCESS_SIGNATURES: Signatures = {
    "OpenProcess": ([DWORD, BOOL, DWORD], HANDLE),
    "GetProcessTimes": ([HANDLE] * 5, BOOL),
    "QueryFullProcessImageNameW": ([HANDLE, DWORD, HANDLE, HANDLE], BOOL),
    "WaitForSingleObject": ([HANDLE, DWORD], DWORD),
    "TerminateProcess": ([HANDLE, DWORD], BOOL),
    "CloseHandle": ([HANDLE], BOOL),
    "CreateToolhelp32Snapshot": ([DWORD, DWORD], HANDLE),
    "Process32FirstW": ([HANDLE, HANDLE], BOOL),
    "Process32NextW": ([HANDLE, HANDLE], BOOL),
}


def structure(name: str, *fields: tuple[str, Any]) -> type[Structure]:
    """Return a ctypes structure of the SDK's fields (fixed-width types, so layouts are checked on every platform)."""
    return type(name, (Structure,), {"_fields_": list(fields)})


FILETIME = structure("FILETIME", ("dwLowDateTime", DWORD), ("dwHighDateTime", DWORD))  # minwinbase.h
PROCESSENTRY32W = structure(  # tlhelp32.h
    "PROCESSENTRY32W",
    ("dwSize", DWORD), ("cntUsage", DWORD), ("th32ProcessID", DWORD), ("th32DefaultHeapID", c_size_t),
    ("th32ModuleID", DWORD), ("cntThreads", DWORD), ("th32ParentProcessID", DWORD), ("pcPriClassBase", BOOL),
    ("dwFlags", DWORD), ("szExeFile", WORD * 260),  # WCHAR[MAX_PATH]
)  # fmt: skip


def win32_error(kernel32: Kernel32, call: str) -> OSError:
    """Return the `OSError` of a failed Win32 call; on Windows its class follows the code (access denied)."""
    return OSError(None, f"{call} failed", None, kernel32.last_error())


class WindowsProcessInspector:
    """`ProcessInspector` over kernel32: the pid with the creation FILETIME of `GetProcessTimes`.

    A process that has exited has no identity. A failed Win32 call raises `OSError`, except `OpenProcess` for a pid
    that no process has.
    """

    def __init__(self, kernel32: Kernel32) -> None:
        self._k = kernel32

    @contextmanager
    def _process(self, pid: int, rights: int) -> Iterator[int | None]:
        """Open `pid` once for a whole check (None when no such process exists) and close it afterwards."""
        handle = self._k.OpenProcess(rights, False, pid)
        if not handle and self._k.last_error() != ERROR_INVALID_PARAMETER:
            raise win32_error(self._k, f"OpenProcess({pid})")
        try:
            yield int(handle) if handle else None
        finally:
            if handle:
                self._k.CloseHandle(handle)

    def _started(self, handle: int) -> str:
        created, other = FILETIME(), FILETIME()
        if not self._k.GetProcessTimes(handle, byref(created), byref(other), byref(other), byref(other)):
            raise win32_error(self._k, "GetProcessTimes")
        return str(created.dwHighDateTime << 32 | created.dwLowDateTime)

    def _exited(self, handle: int) -> bool:
        return bool(self._k.WaitForSingleObject(handle, 0) == WAIT_OBJECT_0)

    def identity(self, pid: int) -> ProcessIdentity | None:
        """Return the identity of the running process `pid`, or None when none runs with that pid."""
        with self._process(pid, PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE) as handle:
            if handle is None or self._exited(handle):
                return None
            size, path = DWORD(IMAGE_NAME_CHARS), create_unicode_buffer(IMAGE_NAME_CHARS)
            if not self._k.QueryFullProcessImageNameW(handle, 0, path, byref(size)):
                raise win32_error(self._k, "QueryFullProcessImageNameW")
            return ProcessIdentity(pid, self._started(handle), path.value.rpartition("\\")[2])

    def alive(self, identity: ProcessIdentity) -> bool:
        """Return True when pid and start time match and the process has not exited."""
        found = self.identity(identity.pid)
        return found is not None and found.started_at == identity.started_at

    def _entries(self) -> list[tuple[int, int, str]]:
        """Return (pid, parent pid, image file name) of every process in one Toolhelp snapshot."""
        snapshot = self._k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == INVALID_HANDLE_VALUE:
            raise win32_error(self._k, "CreateToolhelp32Snapshot")
        try:
            entry, found = PROCESSENTRY32W(), []
            entry.dwSize = sizeof(entry)
            more = self._k.Process32FirstW(snapshot, byref(entry))
            while more:
                name = bytes(entry.szExeFile).decode("utf-16-le").partition("\0")[0]
                found.append((entry.th32ProcessID, entry.th32ParentProcessID, name))
                more = self._k.Process32NextW(snapshot, byref(entry))
            if self._k.last_error() != ERROR_NO_MORE_FILES:  # the walk ended on an error, not after the last process
                raise win32_error(self._k, "Process32NextW")
            return found
        finally:
            self._k.CloseHandle(snapshot)

    def children(self, pid: int) -> list[ProcessIdentity]:
        """Return the running direct children of `pid`; one older than `pid` is no child (a reused parent pid)."""
        parent = self.identity(pid)
        if parent is None:
            return []
        found = (self.identity(child) for child, ppid, _ in self._entries() if ppid == pid)
        return [c for c in found if c is not None and int(c.started_at) >= int(parent.started_at)]

    def snapshot(self, exe_names: list[str]) -> list[ProcessIdentity]:
        """Return every running process whose image file name is in `exe_names` (compared without case)."""
        wanted = {name.lower() for name in exe_names}
        found = (self.identity(pid) for pid, _, name in self._entries() if name.lower() in wanted)
        return [i for i in found if i is not None]

    def terminate(self, identity: ProcessIdentity) -> bool:
        """End the process only if pid and start time match, through the handle that was compared; False if not."""
        with self._process(identity.pid, PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE) as handle:
            if handle is None or self._started(handle) != identity.started_at or self._exited(handle):
                return False
            if self._k.TerminateProcess(handle, KILLED_EXIT_CODE):
                return True
            if self._exited(handle):  # it ended between the check and the call
                return False
            raise win32_error(self._k, "TerminateProcess")


if sys.platform == "win32":
    import ctypes
    import msvcrt

    class CtypesKernel32:
        """The real kernel32: typed signatures, the calling thread's last error, and inheritable handles."""

        last_error = staticmethod(ctypes.get_last_error)

        def __init__(self, signatures: Signatures) -> None:
            dll = ctypes.WinDLL("kernel32", use_last_error=True)
            for name, (argtypes, restype) in signatures.items():
                function = getattr(dll, name)
                function.argtypes, function.restype = argtypes, restype
                setattr(self, name, function)

        @staticmethod
        def inheritable_handle(fd: int) -> int:
            """Return the OS handle of descriptor `fd`, marked inheritable (a child gets it through a handle list)."""
            handle = int(msvcrt.get_osfhandle(fd))
            os.set_handle_inheritable(handle, True)
            return handle
