"""S-10 spike: a small ctypes wrapper for Windows Job Objects. Throwaway; never ships.

Windows only at run time. The structure definitions use fixed-width types so their sizes can be checked on any
platform (see layout_selftest, run by check.py on Linux). Nothing in this file has run against Windows yet: the
result is pending the Windows CI job that runs windows_check.py.

API facts used (Microsoft Win32 documentation: "Job Objects", "JOBOBJECT_EXTENDED_LIMIT_INFORMATION",
"AssignProcessToJobObject", "Nested Jobs", "Process Creation Flags"):
  JobObjectBasicProcessIdList = 3, JobObjectExtendedLimitInformation = 9,
  JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000, CREATE_SUSPENDED = 0x4,
  process access rights PROCESS_TERMINATE 0x1, PROCESS_SET_QUOTA 0x100, PROCESS_QUERY_INFORMATION 0x400,
  PROCESS_QUERY_LIMITED_INFORMATION 0x1000, SYNCHRONIZE 0x100000.
"""

import ctypes
import subprocess
import sys
from ctypes import Structure, byref, c_int, c_int32, c_int64, c_size_t, c_uint32, c_uint64, c_void_p, c_wchar_p, sizeof
from typing import Any

JobObjectBasicProcessIdList = 3
JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200

PROCESS_TERMINATE = 0x0001
PROCESS_SET_QUOTA = 0x0100
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000

WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
TH32CS_SNAPTHREAD = 0x00000004
THREAD_SUSPEND_RESUME = 0x0002
_INVALID_HANDLE = (1 << (8 * sizeof(c_void_p))) - 1


class IO_COUNTERS(Structure):
    _fields_ = [
        ("ReadOperationCount", c_uint64),
        ("WriteOperationCount", c_uint64),
        ("OtherOperationCount", c_uint64),
        ("ReadTransferCount", c_uint64),
        ("WriteTransferCount", c_uint64),
        ("OtherTransferCount", c_uint64),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", c_int64),
        ("PerJobUserTimeLimit", c_int64),
        ("LimitFlags", c_uint32),
        ("MinimumWorkingSetSize", c_size_t),
        ("MaximumWorkingSetSize", c_size_t),
        ("ActiveProcessLimit", c_uint32),
        ("Affinity", c_size_t),
        ("PriorityClass", c_uint32),
        ("SchedulingClass", c_uint32),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", c_size_t),
        ("JobMemoryLimit", c_size_t),
        ("PeakProcessMemoryUsed", c_size_t),
        ("PeakJobMemoryUsed", c_size_t),
    ]


_MAX_IDS = 512


class JOBOBJECT_BASIC_PROCESS_ID_LIST(Structure):
    _fields_ = [
        ("NumberOfAssignedProcesses", c_uint32),
        ("NumberOfProcessIdsInList", c_uint32),
        ("ProcessIdList", c_size_t * _MAX_IDS),
    ]


class THREADENTRY32(Structure):
    _fields_ = [
        ("dwSize", c_uint32),
        ("cntUsage", c_uint32),
        ("th32ThreadID", c_uint32),
        ("th32OwnerProcessID", c_uint32),
        ("tpBasePri", c_int32),
        ("tpDeltaPri", c_int32),
        ("dwFlags", c_uint32),
    ]


def layout_selftest() -> list[str]:
    """Sizes the Win32 headers give on 64-bit Windows. Runs anywhere because the field types are fixed width."""
    expected = {
        IO_COUNTERS: 48,
        JOBOBJECT_BASIC_LIMIT_INFORMATION: 64,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION: 144,
        THREADENTRY32: 28,
    }
    if sizeof(c_void_p) != 8:
        return ["layout check is for 64-bit only"]
    return [f"{c.__name__}: size {sizeof(c)} != {n}" for c, n in expected.items() if sizeof(c) != n]


if sys.platform == "win32":
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    def _sig(name: str, argtypes: list[Any], restype: Any) -> None:
        fn = getattr(k32, name)
        fn.argtypes, fn.restype = argtypes, restype

    _sig("CreateJobObjectW", [c_void_p, c_wchar_p], c_void_p)
    _sig("SetInformationJobObject", [c_void_p, c_int, c_void_p, c_uint32], c_int)
    _sig("QueryInformationJobObject", [c_void_p, c_int, c_void_p, c_uint32, c_void_p], c_int)
    _sig("AssignProcessToJobObject", [c_void_p, c_void_p], c_int)
    _sig("TerminateJobObject", [c_void_p, c_uint32], c_int)
    _sig("IsProcessInJob", [c_void_p, c_void_p, c_void_p], c_int)
    _sig("OpenProcess", [c_uint32, c_int, c_uint32], c_void_p)
    _sig("GetCurrentProcess", [], c_void_p)
    _sig("TerminateProcess", [c_void_p, c_uint32], c_int)
    _sig("WaitForSingleObject", [c_void_p, c_uint32], c_uint32)
    _sig("CloseHandle", [c_void_p], c_int)
    _sig("CreateToolhelp32Snapshot", [c_uint32, c_uint32], c_void_p)
    _sig("Thread32First", [c_void_p, c_void_p], c_int)
    _sig("Thread32Next", [c_void_p, c_void_p], c_int)
    _sig("OpenThread", [c_uint32, c_int, c_uint32], c_void_p)
    _sig("ResumeThread", [c_void_p], c_uint32)


def _fail(what: str) -> OSError:
    return ctypes.WinError(ctypes.get_last_error(), what)  # type: ignore[attr-defined,no-any-return]


def _need_windows() -> None:
    if sys.platform != "win32":
        raise OSError("Job Objects exist on Windows only")


class JobObject:
    """An anonymous job object. With kill_on_close, closing the last handle (or the owning process ending, which
    closes its handles) terminates every process in the job."""

    def __init__(self, kill_on_close: bool = True) -> None:
        _need_windows()
        h = k32.CreateJobObjectW(None, None)
        if not h:
            raise _fail("CreateJobObjectW")
        self.handle: int | None = h
        if kill_on_close:
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(h, JobObjectExtendedLimitInformation, byref(info), sizeof(info)):
                err = _fail("SetInformationJobObject")
                self.close()
                raise err

    def assign_process_handle(self, process_handle: int) -> None:
        if not k32.AssignProcessToJobObject(self.handle, process_handle):
            raise _fail("AssignProcessToJobObject")

    def assign_pid(self, pid: int) -> None:
        h = k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_QUERY_INFORMATION, 0, pid)
        if not h:
            raise _fail(f"OpenProcess({pid})")
        try:
            self.assign_process_handle(h)
        finally:
            k32.CloseHandle(h)

    def assign_current_process(self) -> None:
        self.assign_process_handle(k32.GetCurrentProcess())

    def process_ids(self) -> list[int]:
        """Processes in this job and in jobs nested below it (the list of a job includes its descendants' members)."""
        buf = JOBOBJECT_BASIC_PROCESS_ID_LIST()
        if not k32.QueryInformationJobObject(self.handle, JobObjectBasicProcessIdList, byref(buf), sizeof(buf), None):
            raise _fail("QueryInformationJobObject")
        return [int(buf.ProcessIdList[i]) for i in range(buf.NumberOfProcessIdsInList)]

    def terminate(self, exit_code: int = 1) -> None:
        if not k32.TerminateJobObject(self.handle, exit_code):
            raise _fail("TerminateJobObject")

    def contains(self, pid: int) -> bool:
        return pid in self.process_ids()

    def close(self) -> None:
        if self.handle:
            k32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "JobObject":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def current_process_in_any_job() -> bool:
    _need_windows()
    flag = c_int(0)
    if not k32.IsProcessInJob(k32.GetCurrentProcess(), None, byref(flag)):
        raise _fail("IsProcessInJob")
    return bool(flag.value)


# ---- starting a process so that it can never run outside the job -------------------------------------------------


def resume_process(pid: int) -> int:
    """Resume every thread of a process created with CREATE_SUSPENDED. Returns the number of threads resumed."""
    _need_windows()
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if snap is None or snap == _INVALID_HANDLE:
        raise _fail("CreateToolhelp32Snapshot")
    resumed = 0
    try:
        te = THREADENTRY32()
        te.dwSize = sizeof(te)
        ok = k32.Thread32First(snap, byref(te))
        while ok:
            if te.th32OwnerProcessID == pid:
                th = k32.OpenThread(THREAD_SUSPEND_RESUME, 0, te.th32ThreadID)
                if not th:
                    raise _fail("OpenThread")
                try:
                    if k32.ResumeThread(th) == 0xFFFFFFFF:
                        raise _fail("ResumeThread")
                    resumed += 1
                finally:
                    k32.CloseHandle(th)
            ok = k32.Thread32Next(snap, byref(te))
    finally:
        k32.CloseHandle(snap)
    if resumed == 0:
        raise OSError(f"no thread of process {pid} found to resume")
    return resumed


def popen_in_job(job: JobObject, args: list[str], **kwargs: Any) -> "subprocess.Popen[Any]":
    """Start a process suspended, put it in the job, then let it run. No code of the new process (and so no
    grandchild) can run before the assignment. Pipes and other Popen arguments work as usual."""
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_SUSPENDED
    proc = subprocess.Popen(args, **kwargs)
    try:
        job.assign_pid(proc.pid)
        resume_process(proc.pid)
    except BaseException:
        proc.kill()
        raise
    return proc


# ---- helpers for tests --------------------------------------------------------------------------------------------


def open_waitable(pid: int) -> int:
    """A handle that stays valid after the process ends, so a later wait cannot hit a recycled pid."""
    _need_windows()
    h = k32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE, 0, pid)
    if not h:
        raise _fail(f"OpenProcess({pid})")
    return int(h)


def wait_dead(handle: int, timeout_s: float) -> bool:
    r = k32.WaitForSingleObject(handle, int(timeout_s * 1000))
    if r == WAIT_OBJECT_0:
        return True
    if r == WAIT_TIMEOUT:
        return False
    raise _fail("WaitForSingleObject")


def terminate_handle(handle: int) -> None:
    k32.TerminateProcess(handle, 1)


def close_handle(handle: int) -> None:
    k32.CloseHandle(handle)
