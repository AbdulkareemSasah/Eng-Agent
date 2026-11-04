"""Process identity and termination, POSIX implementation (plan 0002 T2; spec 0002 AC7, section 4.3.1).

`started_at` is an opaque string. On Linux it is `<boot id>:<start time>` where the boot id is
`/proc/sys/kernel/random/boot_id` and the start time is field 22 of `/proc/<pid>/stat` (proc(5)), in clock ticks
since boot, so a pid reused by a new process, or after a reboot, never compares equal.
"""

import errno
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_PROC = Path("/proc")
_BOOT_ID = _PROC / "sys" / "kernel" / "random" / "boot_id"


@dataclass(frozen=True)
class ProcessIdentity:
    """A process as the operating system identifies it.

    Attributes:
        pid: Process id.
        started_at: Opaque OS creation time (see the module docstring); equal only for the same process.
        exe_name: Name of the program image (POSIX: the kernel's command name, at most 15 characters).
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
