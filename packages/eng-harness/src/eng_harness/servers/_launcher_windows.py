"""Windows process launcher: one Job Object per started process (plan 0002 T3; spec 0002 AC5, AC6, section 4.3.1).

A process is created suspended, assigned to its job and only then resumed (S-10 report, "Closing the race"). The job
kills its processes when its last handle closes, which includes the engine ending for any reason; a `SERVER` job also
has silent breakaway, so host programs a server starts survive it (ADR-0030 decision 8); a `TOOL` job allows none. The
Win32 calls go through a `Kernel32` object, so the logic runs against a fake on every platform.
"""

import contextlib
import io
import math
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from ctypes import addressof, byref, c_size_t, c_uint64, create_string_buffer, create_unicode_buffer, sizeof
from typing import IO

from eng_harness.servers import _procinfo as pi
from eng_harness.servers._launcher import JobPolicy, LaunchError, LaunchSpec
from eng_harness.servers._procinfo import BOOL, DWORD, HANDLE, WORD

# Software constants of winbase.h, winnt.h and processthreadsapi.h; Win32 pages "JOBOBJECT_BASIC_LIMIT_INFORMATION",
# "JOBOBJECTINFOCLASS", "Process Creation Flags" and "UpdateProcThreadAttribute".
JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x1000, 0x2000
BASIC_PROCESS_ID_LIST, EXTENDED_LIMIT_INFORMATION = 3, 9  # JOBOBJECTINFOCLASS: JobObjectBasicProcessIdList, ...
CREATE_SUSPENDED, CREATE_UNICODE_ENVIRONMENT, EXTENDED_STARTUPINFO_PRESENT = 0x4, 0x400, 0x80000
CREATE_NO_WINDOW, STARTF_USESTDHANDLES = 0x08000000, 0x100
ATTRIBUTE_HANDLE_LIST = (
    0x00020002  # PROC_THREAD_ATTRIBUTE_HANDLE_LIST = ProcThreadAttributeValue(2, FALSE, TRUE, FALSE)
)
INFINITE = RESUME_FAILED = 0xFFFFFFFF  # WaitForSingleObject's wait forever; ResumeThread's (DWORD)-1

JOB_SIGNATURES: pi.Signatures = {
    "CreateJobObjectW": ([HANDLE, HANDLE], HANDLE),
    "SetInformationJobObject": ([HANDLE, DWORD, HANDLE, DWORD], BOOL),
    "QueryInformationJobObject": ([HANDLE, DWORD, HANDLE, DWORD, HANDLE], BOOL),
    "AssignProcessToJobObject": ([HANDLE, HANDLE], BOOL),
    "TerminateJobObject": ([HANDLE, DWORD], BOOL),
    "InitializeProcThreadAttributeList": ([HANDLE, DWORD, DWORD, HANDLE], BOOL),
    "UpdateProcThreadAttribute": ([HANDLE, DWORD, c_size_t, HANDLE, c_size_t, HANDLE, HANDLE], BOOL),
    "DeleteProcThreadAttributeList": ([HANDLE], None),
    "CreateProcessW": ([HANDLE] * 4 + [BOOL, DWORD] + [HANDLE] * 4, BOOL),
    "ResumeThread": ([HANDLE], DWORD),
    "GetExitCodeProcess": ([HANDLE, HANDLE], BOOL),
}

JobObjectExtendedLimitInformation = pi.structure(  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION, flattened
    "JobObjectExtendedLimitInformation",
    ("PerProcessUserTimeLimit", c_uint64), ("PerJobUserTimeLimit", c_uint64), ("LimitFlags", DWORD),
    ("MinimumWorkingSetSize", c_size_t), ("MaximumWorkingSetSize", c_size_t), ("ActiveProcessLimit", DWORD),
    ("Affinity", c_size_t), ("PriorityClass", DWORD), ("SchedulingClass", DWORD),
    ("IoInfo", c_uint64 * 6),  # IO_COUNTERS: six ULONGLONG counters
    *[(n, c_size_t) for n in ("ProcessMemoryLimit", "JobMemoryLimit", "PeakProcessMemoryUsed", "PeakJobMemoryUsed")],
)  # fmt: skip
JobProcessIdList = pi.structure(  # JOBOBJECT_BASIC_PROCESS_ID_LIST
    "JobProcessIdList",
    ("NumberOfAssignedProcesses", DWORD), ("NumberOfProcessIdsInList", DWORD),
    ("ProcessIdList", c_size_t * 512),  # room for 512 members; more fail with ERROR_MORE_DATA
)  # fmt: skip
STARTUPINFOEXW = pi.structure(  # STARTUPINFOEXW (processthreadsapi.h), its nested STARTUPINFOW flattened
    "STARTUPINFOEXW",
    ("cb", DWORD), ("lpReserved", HANDLE), ("lpDesktop", HANDLE), ("lpTitle", HANDLE),
    *[(name, DWORD) for name in ("dwX", "dwY", "dwXSize", "dwYSize", "dwXCountChars", "dwYCountChars")],
    ("dwFillAttribute", DWORD), ("dwFlags", DWORD), ("wShowWindow", WORD), ("cbReserved2", WORD),
    ("lpReserved2", HANDLE), ("hStdInput", HANDLE), ("hStdOutput", HANDLE), ("hStdError", HANDLE),
    ("lpAttributeList", HANDLE),
)  # fmt: skip
ProcessInformation = pi.structure(  # PROCESS_INFORMATION
    "ProcessInformation", ("hProcess", HANDLE), ("hThread", HANDLE), ("dwProcessId", DWORD), ("dwThreadId", DWORD)
)


def _passable(argv: Sequence[str], env: Mapping[str, str]) -> tuple[str, str]:
    """Return the command line (C runtime quoting) and the environment block of `CreateProcessW`: `name=value`
    strings sorted by upper-cased name, each ended by NUL. LaunchError: `argv` is empty, a part holds NUL, or an
    environment name is empty or holds `=`."""
    if not argv or any("\0" in part for part in argv):
        raise LaunchError("argv is empty or holds a NUL character")
    for name, value in env.items():
        if not name or "=" in name or "\0" in name or "\0" in value:
            raise LaunchError(f"environment variable {name!r} cannot be passed to CreateProcessW")
    block = "".join(f"{n}={v}\0" for n, v in sorted(env.items(), key=lambda item: item[0].upper()))
    return subprocess.list2cmdline(list(argv)), block or "\0"


class WindowsProcess:
    """A started process, its job and its pipes (`LaunchedProcess`); `close()` also ends the job (kill-on-close)."""

    def __init__(
        self, kernel32: pi.Kernel32, inspector: pi.ProcessInspector, job: int, created: tuple[int, int, int],
        started_at: str, pipes: Sequence[IO[bytes]],
    ) -> None:  # fmt: skip
        self._k, self._inspector, self.job_handle = kernel32, inspector, job
        self._process, self._thread, self.pid = created
        self.started_at, (self.stdin, self.stdout) = started_at, pipes
        self._closed = False

    def wait(self, timeout: float | None) -> int | None:
        """Return the exit code, or None when the process still runs after `timeout` seconds."""
        milliseconds = INFINITE if timeout is None else min(math.ceil(timeout * 1000), INFINITE - 1)
        result, code = self._k.WaitForSingleObject(self._process, milliseconds), DWORD()
        if result == pi.WAIT_TIMEOUT:
            return None
        if result != pi.WAIT_OBJECT_0 or not self._k.GetExitCodeProcess(self._process, byref(code)):
            raise pi.win32_error(self._k, "WaitForSingleObject")
        return code.value

    def job_members(self) -> list[pi.ProcessIdentity]:
        """Return the running processes of the job (none once it is closed)."""
        if self._closed:
            return []
        ids = JobProcessIdList()
        if not self._k.QueryInformationJobObject(self.job_handle, BASIC_PROCESS_ID_LIST, byref(ids), sizeof(ids), None):
            raise pi.win32_error(self._k, "QueryInformationJobObject")
        found = (self._inspector.identity(pid) for pid in ids.ProcessIdList[: ids.NumberOfProcessIdsInList])
        return [member for member in found if member is not None]  # one that ended since the listing is not running

    def terminate_job(self) -> None:
        """End every process of the job (`TerminateJobObject`); a no-op once the job is closed."""
        if not self._closed and not self._k.TerminateJobObject(self.job_handle, pi.KILLED_EXIT_CODE):
            raise pi.win32_error(self._k, "TerminateJobObject")

    def close(self) -> None:
        """Close the pipes and every handle, the job's last; idempotent."""
        if self._closed:
            return
        self._closed = True
        self.stdin.close()
        self.stdout.close()
        for handle in (self._thread, self._process, self.job_handle):
            self._k.CloseHandle(handle)


class WindowsLauncher:
    """`ProcessLauncher` with one Job Object per started process; `windows_launcher()` builds the real one."""

    def __init__(self, kernel32: pi.Kernel32, inspector: pi.ProcessInspector) -> None:
        self._k, self._inspector = kernel32, inspector

    def start(self, spec: LaunchSpec) -> WindowsProcess:
        """Start `spec` suspended in a new job, resume it once it is a member, and return it.

        Raises:
            LaunchError: arguments that cannot be passed, a failed Win32 call or no start time; nothing is left open.
        """
        line, block = _passable(spec.argv, spec.env)
        try:
            return self._start(spec, line, block)
        except OSError as exc:
            raise LaunchError(f"cannot start {spec.argv[0]}: {exc}") from exc

    def _start(self, spec: LaunchSpec, line: str, block: str) -> WindowsProcess:
        k = self._k
        spec.stderr_path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.ExitStack() as child_side, contextlib.ExitStack() as undo:
            stderr = child_side.enter_context(spec.stderr_path.open("ab"))
            job = k.CreateJobObjectW(None, None)  # no security attrs: the handle cannot be inherited
            if not job:
                raise pi.win32_error(k, "CreateJobObjectW")
            undo.callback(k.CloseHandle, job)
            limits = JobObjectExtendedLimitInformation()
            silent = JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK if spec.job is JobPolicy.SERVER else 0
            limits.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | silent
            if not k.SetInformationJobObject(job, EXTENDED_LIMIT_INFORMATION, byref(limits), sizeof(limits)):
                raise pi.win32_error(k, "SetInformationJobObject")
            handles, files = [], []  # what the child gets (stdin, stdout, stderr) and the parent's ends of the pipes
            for parent_reads in (False, True):
                read_fd, write_fd = os.pipe()
                child_fd, parent_fd = (write_fd, read_fd) if parent_reads else (read_fd, write_fd)
                child_side.callback(os.close, child_fd)
                files.append(undo.enter_context(io.FileIO(parent_fd, "r" if parent_reads else "w")))
                handles.append(k.inheritable_handle(child_fd))
            handles.append(k.inheritable_handle(stderr.fileno()))
            process, thread, pid = self._create(line, block, str(spec.cwd), handles)
            undo.callback(k.CloseHandle, thread)
            undo.callback(k.CloseHandle, process)
            undo.callback(k.TerminateProcess, process, pi.KILLED_EXIT_CODE)  # undone first: nothing runs unjobbed
            if not k.AssignProcessToJobObject(job, process):
                raise pi.win32_error(k, "AssignProcessToJobObject")
            if (identity := self._inspector.identity(pid)) is None:
                raise LaunchError(f"no start time readable for pid {pid}")
            if k.ResumeThread(thread) == RESUME_FAILED:
                raise pi.win32_error(k, "ResumeThread")
            undo.pop_all()
            return WindowsProcess(k, self._inspector, job, (process, thread, pid), identity.started_at, files)

    def _create(self, line: str, block: str, cwd: str, handles: list[int]) -> tuple[int, int, int]:
        """`CreateProcessW` suspended; the child inherits `handles` (stdin, stdout, stderr) and nothing else.
        Return the process handle, the primary thread handle and the pid."""
        k = self._k
        size = c_size_t()
        k.InitializeProcThreadAttributeList(None, 1, 0, byref(size))  # the sizing call fails by design
        attrs = create_string_buffer(size.value)
        if not k.InitializeProcThreadAttributeList(attrs, 1, 0, byref(size)):
            raise pi.win32_error(k, "InitializeProcThreadAttributeList")
        try:
            shared = (HANDLE * len(handles))(*handles)
            if not k.UpdateProcThreadAttribute(attrs, 0, ATTRIBUTE_HANDLE_LIST, shared, sizeof(shared), None, None):
                raise pi.win32_error(k, "UpdateProcThreadAttribute")
            startup, info = STARTUPINFOEXW(), ProcessInformation()
            startup.cb, startup.dwFlags = sizeof(startup), STARTF_USESTDHANDLES
            startup.hStdInput, startup.hStdOutput, startup.hStdError = handles
            startup.lpAttributeList = addressof(attrs)
            flags = CREATE_SUSPENDED | CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT
            if not k.CreateProcessW(
                None, create_unicode_buffer(line), None, None, True, flags,
                create_unicode_buffer(block), create_unicode_buffer(cwd), byref(startup), byref(info),
            ):  # fmt: skip
                raise pi.win32_error(k, "CreateProcessW")
        finally:
            k.DeleteProcThreadAttributeList(attrs)
        return int(info.hProcess), int(info.hThread), int(info.dwProcessId)


if sys.platform == "win32":

    def windows_launcher() -> WindowsLauncher:
        """The launcher over the real kernel32 and its inspector (the edge of the package)."""
        kernel32 = pi.CtypesKernel32({**pi.PROCESS_SIGNATURES, **JOB_SIGNATURES})
        return WindowsLauncher(kernel32, pi.WindowsProcessInspector(kernel32))
