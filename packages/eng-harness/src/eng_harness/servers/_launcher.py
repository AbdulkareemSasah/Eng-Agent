"""Process launcher port and its POSIX implementation (plan 0002 T2; spec 0002 AC4, AC6, section 4.3.1).

POSIX is for development and Linux CI only: the "job" is one process group per started process (`start_new_session`)
and `terminate_job` is `killpg`. POSIX has no kill-on-close job: when the engine is killed, a server ends because
its standard input reaches end-of-file. The Windows job with kill-on-close arrives with plan task T3.
"""

import contextlib
import os
import signal
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import IO, Protocol, cast

from eng_harness.servers._procinfo import PosixProcessInspector, ProcessIdentity


class JobPolicy(Enum):
    """How a started process and its descendants are bound to the engine (spec section 4.3.1)."""

    SERVER = "server"  # kill on close, silent breakaway (Windows); a process group (POSIX)
    TOOL = "tool"  # kill on close, no breakaway


class LaunchError(Exception):
    """The process could not be started (missing program, bad working folder, no start time readable)."""


@dataclass(frozen=True)
class LaunchSpec:
    """What to start.

    Attributes:
        argv: Program and arguments; the program is run as given, never through a shell.
        env: The complete environment of the process (nothing is inherited implicitly).
        cwd: Working folder (the run folder).
        stderr_path: File that receives standard error (appended; its folder is created).
        job: The job policy.
    """

    argv: Sequence[str]
    env: Mapping[str, str]
    cwd: Path
    stderr_path: Path
    job: JobPolicy


class LaunchedProcess(Protocol):
    """A started process with its job and binary pipes.

    Attributes:
        pid: Process id.
        started_at: OS creation time as the inspector reports it.
        stdin: Binary pipe to the process.
        stdout: Binary pipe from the process.
    """

    pid: int
    started_at: str
    stdin: IO[bytes]
    stdout: IO[bytes]

    def wait(self, timeout: float | None) -> int | None:
        """Return the exit code, or None when the process still runs after `timeout` seconds."""

    def terminate_job(self) -> None:
        """End every process of the job; idempotent."""

    def job_members(self) -> list[ProcessIdentity]:
        """Return the running processes of the job."""

    def close(self) -> None:
        """Release the pipes and handles; does not end the job (call `terminate_job`); idempotent."""


class ProcessLauncher(Protocol):
    """Port: starts a process in a job."""

    def start(self, spec: LaunchSpec) -> LaunchedProcess:
        """Start `spec`; raises `LaunchError` when it cannot be started."""


class _PosixProcess:
    def __init__(
        self,
        popen: subprocess.Popen[bytes],
        pipes: tuple[IO[bytes], IO[bytes], IO[bytes]],
        started_at: str,
        inspector: PosixProcessInspector,
    ) -> None:
        self.pid = popen.pid
        self.started_at = started_at
        self.stdin, self.stdout, self._stderr = pipes
        self._popen, self._inspector = popen, inspector
        self._ended = False

    def wait(self, timeout: float | None) -> int | None:
        try:
            return self._popen.wait(timeout)
        except subprocess.TimeoutExpired:
            return None

    def job_members(self) -> list[ProcessIdentity]:
        return self._inspector.group_members(self.pid)

    def terminate_job(self) -> None:
        # While the leader is unreaped its pid, and so the group id, stays reserved: signal the group. After that the
        # number may belong to an unrelated group, so members end one by one by identity, and never again once the
        # group has been seen empty.
        if self._ended:
            return
        if self._popen.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.pid, signal.SIGKILL)
            return
        members = self.job_members()
        for member in members:
            self._inspector.terminate(member)
        self._ended = not members

    def close(self) -> None:
        for stream in (self.stdin, self.stdout, self._stderr):
            stream.close()
        self._popen.poll()  # reap the leader when it has exited


class PosixLauncher:
    """`ProcessLauncher` with one process group per started process."""

    def __init__(self, inspector: PosixProcessInspector | None = None) -> None:
        self._inspector = inspector or PosixProcessInspector()

    def start(self, spec: LaunchSpec) -> LaunchedProcess:
        """Start `spec` in a new session and process group; `JobPolicy` makes no difference on POSIX."""
        spec.stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr = spec.stderr_path.open("ab")
        try:
            popen = subprocess.Popen(  # noqa: S603  # B-121: argv comes from the validated server configuration
                list(spec.argv),
                env=dict(spec.env),
                cwd=spec.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
                bufsize=0,
                start_new_session=True,
            )
        except OSError as exc:
            stderr.close()
            raise LaunchError(f"cannot start {spec.argv[0]}: {exc}") from exc
        identity = self._inspector.identity(popen.pid)
        if identity is None:
            popen.kill()
            popen.wait()
            for stream in (popen.stdin, popen.stdout, stderr):
                if stream is not None:
                    stream.close()
            raise LaunchError(f"no start time readable for pid {popen.pid} of {spec.argv[0]}")
        pipes = (cast("IO[bytes]", popen.stdin), cast("IO[bytes]", popen.stdout), stderr)  # PIPE: never None
        return _PosixProcess(popen, pipes, identity.started_at, self._inspector)
