"""Windows launcher and Job Objects (plan 0002 T3; spec 0002 AC5, AC6, section 4.3.1).

The launcher logic runs on every platform over a fake kernel32 (the tests before the platform check). The tests that
start real processes in real jobs are defined only on Windows (marker `windows`); they have not run on Windows yet and
are an owner local test. Each tracks the processes it created and proves they exist before it asserts that they ended
(S-10 report, "Windows results": its engine-exit runs tracked no process and so proved nothing).
"""

import os
import re
import sys
from collections.abc import Iterator
from ctypes import c_void_p, sizeof
from pathlib import Path
from typing import Any

import pytest

from eng_harness.servers._launcher import JobPolicy, LaunchError, LaunchSpec
from eng_harness.servers._launcher_windows import (
    STARTUPINFOEXW,
    JobObjectExtendedLimitInformation,
    JobProcessIdList,
    ProcessInformation,
    WindowsLauncher,
)
from eng_harness.servers._procinfo import ProcessIdentity

# Windows SDK values (winnt.h, winbase.h, processthreadsapi.h), restated here as the oracle of the fake.
JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x1000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x0800
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
JOB_OBJECT_BASIC_PROCESS_ID_LIST = 3
CREATE_SUSPENDED = 0x4
CREATE_UNICODE_ENVIRONMENT = 0x400
EXTENDED_STARTUPINFO_PRESENT = 0x80000
CREATE_NO_WINDOW = 0x08000000
STARTF_USESTDHANDLES = 0x100
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x20002  # = ProcThreadAttributeValue(2, FALSE, TRUE, FALSE)
HANDLE_FLAG_INHERIT = 0x1  # only the real-process tests below read it
ERROR_MORE_DATA = 234
WAIT_OBJECT_0, WAIT_TIMEOUT, WAIT_FAILED = 0, 0x102, 0xFFFFFFFF
INFINITE = 0xFFFFFFFF
KILLED = 1  # the exit code given to processes the launcher ends

JOB, PROCESS, THREAD, PID = 100, 201, 202, 4242
SERVER = ProcessIdentity(pid=PID, started_at="133000000000000000", exe_name="srv.exe")


class _FakeKernel32:
    """kernel32 job and process-creation calls, recorded in order; the child's pipe ends are real pipes.

    A kernel32 function `CreateJobObjectW` is served by the method `create_job_object_w` (the Win32 spelling is not a
    Python name). `fail` maps a function name to the last error it sets while returning failure.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.events: list[tuple[str, int]] = []  # ("terminate" | "close", handle), in order
        self.fail: dict[str, int] = {}
        self.inheritable: list[int] = []
        self.members: list[int] = []
        self.waits: list[int] = []
        self.wait_result = WAIT_OBJECT_0
        self.terminated_jobs: list[tuple[int, int]] = []
        self.job_security: object = "unset"
        self.limits: tuple[int, int, int] | None = None  # (information class, limit flags, size passed)
        self.attribute: tuple[int, list[int | None], int] | None = None  # (attribute, handles, size passed)
        self.created: dict[str, Any] = {}
        self.suspended = False
        self.suspended_at_assign: bool | None = None
        self.assigned: tuple[int, int] | None = None
        self.child_fds: list[int] = []  # the child's ends of the pipes and the stderr file, as made inheritable
        self.child_stdin: int | None = None
        self._error = 0

    def __getattr__(self, name: str) -> Any:
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
        if snake == name:
            raise AttributeError(name)  # not a kernel32 function this fake serves
        return getattr(self, snake)

    def last_error(self) -> int:
        return self._error

    def inheritable_handle(self, fd: int) -> int:
        self.child_fds.append(fd)
        if "SetHandleInformation" in self.fail:  # what the real adapter raises when the handle cannot be marked
            raise OSError(None, "SetHandleInformation failed", None, self.fail["SetHandleInformation"])
        self.inheritable.append(fd)
        return fd

    def _ok(self, name: str) -> bool:
        self.calls.append(name)
        if name in self.fail:
            self._error = self.fail[name]
            return False
        return True

    def create_job_object_w(self, attributes: object, name: object) -> int | None:
        self.job_security = attributes
        return JOB if self._ok("CreateJobObjectW") else None

    def set_information_job_object(self, job: int, information_class: int, info: Any, size: int) -> int:
        limits = info._obj
        assert isinstance(limits, JobObjectExtendedLimitInformation)
        self.limits = (information_class, limits.LimitFlags, size)
        assert size == sizeof(limits)
        return int(self._ok("SetInformationJobObject"))

    def initialize_proc_thread_attribute_list(self, attributes: Any, count: int, flags: int, size: Any) -> int:
        assert count == 1
        size._obj.value = 48
        if attributes is None:  # the sizing call fails by design
            self.calls.append("InitializeProcThreadAttributeList(size)")
            return 0
        assert len(attributes) >= 48
        return int(self._ok("InitializeProcThreadAttributeList"))

    def update_proc_thread_attribute(
        self, attributes: Any, flags: int, attribute: int, value: Any, size: int, previous: Any, returned: Any
    ) -> int:
        self.attribute = (attribute, list(value), size)
        assert size == sizeof(value)
        return int(self._ok("UpdateProcThreadAttribute"))

    def delete_proc_thread_attribute_list(self, attributes: Any) -> None:
        self.calls.append("DeleteProcThreadAttributeList")

    def create_process_w(self, *args: Any) -> int:
        application, line, _, _, inherit, flags, environment, cwd, startup, info = args
        if not self._ok("CreateProcessW"):
            return 0
        basic = startup._obj
        assert isinstance(basic, STARTUPINFOEXW)
        self.created = {
            "application": application,
            "line": line.value,
            "inherit": bool(inherit),
            "flags": flags,
            "environment": environment[:],
            "cwd": cwd.value,
            "cb": basic.cb,
            "startf": basic.dwFlags,
            "std": (basic.hStdInput, basic.hStdOutput, basic.hStdError),
            "attributes": basic.lpAttributeList,
        }
        self.suspended = bool(flags & CREATE_SUSPENDED)
        os.write(basic.hStdOutput, b"hello\n")  # the child's side of the pipes
        self.child_stdin = os.dup(basic.hStdInput)
        process_information = info._obj
        assert isinstance(process_information, ProcessInformation)
        process_information.hProcess, process_information.hThread = PROCESS, THREAD
        process_information.dwProcessId = PID
        return 1

    def assign_process_to_job_object(self, job: int, process: int) -> int:
        self.assigned, self.suspended_at_assign = (job, process), self.suspended
        return int(self._ok("AssignProcessToJobObject"))

    def resume_thread(self, thread: int) -> int:
        if not self._ok("ResumeThread"):
            return WAIT_FAILED  # (DWORD)-1
        self.suspended = False
        return 1  # the previous suspend count

    def query_information_job_object(
        self, job: int, information_class: int, listing: Any, size: int, returned: Any
    ) -> int:
        assert information_class == JOB_OBJECT_BASIC_PROCESS_ID_LIST
        ids = listing._obj
        assert isinstance(ids, JobProcessIdList)
        assert size == sizeof(ids)
        if not self._ok("QueryInformationJobObject"):
            return 0
        if len(self.members) > len(ids.ProcessIdList):  # a longer list than the buffer holds
            self._error = ERROR_MORE_DATA
            return 0
        ids.NumberOfAssignedProcesses = ids.NumberOfProcessIdsInList = len(self.members)
        for index, pid in enumerate(self.members):
            ids.ProcessIdList[index] = pid
        return 1

    def terminate_job_object(self, job: int, exit_code: int) -> int:
        self.terminated_jobs.append((job, exit_code))
        return int(self._ok("TerminateJobObject"))

    def wait_for_single_object(self, handle: int, milliseconds: int) -> int:
        self.waits.append(milliseconds)
        return self.wait_result

    def get_exit_code_process(self, handle: int, code: Any) -> int:
        code._obj.value = 7
        return int(self._ok("GetExitCodeProcess"))

    def terminate_process(self, handle: int, exit_code: int) -> int:
        assert exit_code == KILLED
        self.events.append(("terminate", handle))
        return 1

    def close_handle(self, handle: int) -> int:
        self.events.append(("close", handle))
        return 1


class _FakeInspector:
    """Process identities by pid; `known` are the running processes."""

    def __init__(self, *known: ProcessIdentity) -> None:
        self.known = {identity.pid: identity for identity in known}

    def identity(self, pid: int) -> ProcessIdentity | None:
        return self.known.get(pid)

    def alive(self, identity: ProcessIdentity) -> bool:
        return self.known.get(identity.pid) == identity

    def children(self, pid: int) -> list[ProcessIdentity]:
        return []

    def snapshot(self, exe_names: list[str]) -> list[ProcessIdentity]:
        return []

    def terminate(self, identity: ProcessIdentity) -> bool:
        return False


@pytest.fixture
def pipes(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[int]]:
    """The descriptors `os.pipe` hands out during a test; any still open at the end are closed."""
    seen: list[int] = []
    real = os.pipe

    def spy() -> tuple[int, int]:
        pair = real()
        seen.extend(pair)
        return pair

    monkeypatch.setattr(os, "pipe", spy)
    yield seen
    for fd in seen:
        try:
            os.close(fd)
        except OSError:
            continue  # closed by the launcher, as it should be


def _is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


def _spec(tmp_path: Path, job: JobPolicy = JobPolicy.SERVER, **overrides: Any) -> LaunchSpec:
    fields: dict[str, Any] = {
        "argv": ["C:\\Program Files\\srv.exe", "--call-timeout-sec", "30"],
        "env": {"B": "2"},
        "cwd": tmp_path,
        "stderr_path": tmp_path / "servers" / "srv.stderr.log",
        "job": job,
    }
    return LaunchSpec(**{**fields, **overrides})


@pytest.fixture
def kernel32() -> Iterator[_FakeKernel32]:
    fake = _FakeKernel32()
    yield fake
    if fake.child_stdin is not None:
        os.close(fake.child_stdin)


def _launcher(kernel32: _FakeKernel32, *known: ProcessIdentity) -> WindowsLauncher:
    return WindowsLauncher(kernel32, _FakeInspector(*(known or (SERVER,))))


def test_structure_layouts() -> None:
    # Sizes and offsets of the 64-bit layouts of winnt.h and processthreadsapi.h (natural alignment).
    assert sizeof(c_void_p) == 8
    sizes = {
        JobObjectExtendedLimitInformation: 144,  # JOBOBJECT_BASIC_LIMIT_INFORMATION 64, IO_COUNTERS 48, four SIZE_T
        JobProcessIdList: 8 + 8 * 512,
        STARTUPINFOEXW: 112,  # STARTUPINFOW 104 and the attribute list pointer
        ProcessInformation: 24,
    }
    assert {structure: sizeof(structure) for structure in sizes} == sizes
    offsets = {
        (JobObjectExtendedLimitInformation, "LimitFlags"): 16,
        (JobObjectExtendedLimitInformation, "IoInfo"): 64,
        (JobObjectExtendedLimitInformation, "ProcessMemoryLimit"): 112,
        (JobProcessIdList, "ProcessIdList"): 8,
        (STARTUPINFOEXW, "dwFlags"): 60,
        (STARTUPINFOEXW, "hStdInput"): 80,
        (STARTUPINFOEXW, "lpAttributeList"): 104,
        (ProcessInformation, "dwProcessId"): 16,
    }
    assert {key: getattr(key[0], key[1]).offset for key in offsets} == offsets


@pytest.mark.parametrize(
    ("policy", "flags"),
    [
        (JobPolicy.SERVER, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK),
        (JobPolicy.TOOL, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE),
    ],
)
def test_job_limits_follow_the_policy(
    tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32, policy: JobPolicy, flags: int
) -> None:
    launcher = _launcher(kernel32)
    launcher.start(_spec(tmp_path, policy)).close()
    assert kernel32.limits == (
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
        flags,
        sizeof(JobObjectExtendedLimitInformation),
    )
    assert policy is JobPolicy.SERVER or not flags & (
        JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK | JOB_OBJECT_LIMIT_BREAKAWAY_OK
    )


def test_created_suspended_assigned_then_resumed(tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32) -> None:
    launcher = _launcher(kernel32)
    process = launcher.start(_spec(tmp_path))
    process.close()
    order = [
        c
        for c in kernel32.calls
        if c in ("CreateJobObjectW", "CreateProcessW", "AssignProcessToJobObject", "ResumeThread")
    ]
    assert order == ["CreateJobObjectW", "CreateProcessW", "AssignProcessToJobObject", "ResumeThread"]
    assert kernel32.created["flags"] & CREATE_SUSPENDED
    assert kernel32.assigned == (JOB, PROCESS)
    assert kernel32.suspended_at_assign is True  # no instruction of the process ran before it was in the job
    assert kernel32.suspended is False


def test_child_inherits_only_its_three_handles(tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32) -> None:
    launcher = _launcher(kernel32)
    launcher.start(_spec(tmp_path)).close()
    created = kernel32.created
    flags = CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT
    assert created["flags"] & flags == flags
    assert created["inherit"] is True
    assert created["cb"] == sizeof(STARTUPINFOEXW)
    assert created["startf"] & STARTF_USESTDHANDLES
    assert created["attributes"]
    assert kernel32.attribute is not None
    attribute, handles, size = kernel32.attribute
    assert attribute == PROC_THREAD_ATTRIBUTE_HANDLE_LIST
    assert size == 3 * sizeof(c_void_p)
    assert tuple(handles) == created["std"]  # stdin, stdout, stderr and nothing else
    assert len(set(handles)) == 3
    assert sorted(kernel32.inheritable) == sorted(h for h in handles if h is not None)


def test_job_handle_is_not_inheritable(tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32) -> None:
    launcher = _launcher(kernel32)
    process = launcher.start(_spec(tmp_path))
    process.close()
    assert kernel32.job_security is None  # no security attributes: the handle cannot be inherited
    assert JOB not in kernel32.inheritable
    assert kernel32.attribute is not None
    assert JOB not in kernel32.attribute[1]


def test_pid_start_time_and_pipes(tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32) -> None:
    launcher = _launcher(kernel32)
    process = launcher.start(_spec(tmp_path))
    try:
        assert process.pid == PID
        assert process.started_at == SERVER.started_at
        assert process.stdout.readline() == b"hello\n"  # what the child wrote to its end
        process.stdin.write(b"ping")
        assert kernel32.child_stdin is not None
        assert os.read(kernel32.child_stdin, 4) == b"ping"
        assert all(_is_closed(fd) for fd in kernel32.child_fds)  # the child's ends are not kept
        assert (tmp_path / "servers").is_dir()
    finally:
        process.close()


def test_command_line_and_environment_are_passed(tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32) -> None:
    launcher = _launcher(kernel32)
    spec = _spec(
        tmp_path, argv=["C:\\Program Files\\srv.exe", 'say "hi"', "plain"], env={"b": "2", "A": "1", "Path": "C:\\x"}
    )
    launcher.start(spec).close()
    assert kernel32.created["application"] is None  # the program is the first token of the command line
    assert kernel32.created["line"] == '"C:\\Program Files\\srv.exe" "say \\"hi\\"" plain'
    assert kernel32.created["environment"] == "A=1\0b=2\0Path=C:\\x\0\0"  # sorted without case, double NUL at the end
    assert kernel32.created["cwd"] == str(tmp_path)


def test_empty_environment_is_a_double_nul(tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32) -> None:
    launcher = _launcher(kernel32)
    launcher.start(_spec(tmp_path, env={})).close()
    assert kernel32.created["environment"] == "\0\0"


@pytest.mark.parametrize(
    "overrides",
    [{"argv": []}, {"argv": ["a\0b"]}, {"env": {"A=B": "1"}}, {"env": {"": "1"}}, {"env": {"A": "x\0y"}}],
    ids=["no-argv", "nul-in-argv", "equals-in-name", "empty-name", "nul-in-value"],
)
def test_arguments_that_cannot_be_passed_are_refused_before_anything_is_created(
    tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32, overrides: dict[str, Any]
) -> None:
    launcher = _launcher(kernel32)
    with pytest.raises(LaunchError):
        launcher.start(_spec(tmp_path, **overrides))
    assert kernel32.calls == []
    assert pipes == []


def test_failed_assignment_terminates_the_suspended_process_and_does_not_resume(
    tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32
) -> None:
    launcher = _launcher(kernel32)
    kernel32.fail["AssignProcessToJobObject"] = 5
    with pytest.raises(LaunchError, match=r"srv\.exe.*AssignProcessToJobObject"):
        launcher.start(_spec(tmp_path))
    assert "ResumeThread" not in kernel32.calls
    assert ("terminate", PROCESS) in kernel32.events
    assert kernel32.events.index(("terminate", PROCESS)) < kernel32.events.index(("close", PROCESS))
    assert sorted(h for kind, h in kernel32.events if kind == "close") == [JOB, PROCESS, THREAD]
    assert all(_is_closed(fd) for fd in [*pipes, *kernel32.child_fds])


@pytest.mark.parametrize(
    "call",
    [
        "CreateJobObjectW",
        "SetInformationJobObject",
        "SetHandleInformation",
        "InitializeProcThreadAttributeList",
        "UpdateProcThreadAttribute",
        "CreateProcessW",
    ],
)
def test_a_failure_before_the_process_exists_leaves_nothing_open(
    tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32, call: str
) -> None:
    launcher = _launcher(kernel32)
    kernel32.fail[call] = 87
    with pytest.raises(LaunchError, match=rf"srv\.exe.*{call}"):
        launcher.start(_spec(tmp_path))
    assert ("terminate", PROCESS) not in kernel32.events  # nothing was created that could run
    assert [h for kind, h in kernel32.events if kind == "close"] == ([] if call == "CreateJobObjectW" else [JOB])
    assert "ResumeThread" not in kernel32.calls
    assert all(_is_closed(fd) for fd in [*pipes, *kernel32.child_fds])


def test_missing_start_time_terminates_and_does_not_resume(
    tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32
) -> None:
    launcher = _launcher(kernel32, ProcessIdentity(1, "x", "other.exe"))  # the new pid is not known
    with pytest.raises(LaunchError, match="no start time"):
        launcher.start(_spec(tmp_path))
    assert "ResumeThread" not in kernel32.calls
    assert ("terminate", PROCESS) in kernel32.events
    assert all(_is_closed(fd) for fd in [*pipes, *kernel32.child_fds])


def test_failed_resume_terminates(tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32) -> None:
    launcher = _launcher(kernel32)
    kernel32.fail["ResumeThread"] = 5
    with pytest.raises(LaunchError, match="ResumeThread"):
        launcher.start(_spec(tmp_path))
    assert ("terminate", PROCESS) in kernel32.events


def test_job_members_are_the_running_processes_of_the_job(
    tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32
) -> None:
    helper = ProcessIdentity(10, "h", "helper.exe")
    launcher = _launcher(kernel32, SERVER, helper)
    process = launcher.start(_spec(tmp_path))
    try:
        kernel32.members = [PID, 10, 11]  # pid 11 ended since the listing
        assert process.job_members() == [SERVER, helper]
    finally:
        process.close()


def test_more_members_than_the_buffer_holds_is_an_error_not_a_short_list(
    tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32
) -> None:
    launcher = _launcher(kernel32)
    process = launcher.start(_spec(tmp_path))
    try:
        kernel32.members = list(range(1000, 1000 + 513))  # the buffer holds 512
        with pytest.raises(OSError, match="QueryInformationJobObject"):
            process.job_members()
        kernel32.members = list(range(1000, 1000 + 512))
        assert process.job_members() == []  # none of them is a running process of the fake inspector
        kernel32.fail["QueryInformationJobObject"] = 5
        with pytest.raises(OSError, match="QueryInformationJobObject"):
            process.job_members()
    finally:
        process.close()


def test_terminate_job_asks_for_the_end_of_the_job_and_may_be_repeated(
    tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32
) -> None:
    launcher = _launcher(kernel32)
    process = launcher.start(_spec(tmp_path))
    try:
        process.terminate_job()
        process.terminate_job()
        assert kernel32.terminated_jobs == [(JOB, KILLED), (JOB, KILLED)]
    finally:
        process.close()


def test_a_failed_terminate_job_is_raised_and_may_be_retried(
    tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32
) -> None:
    launcher = _launcher(kernel32)
    process = launcher.start(_spec(tmp_path))
    try:
        kernel32.fail["TerminateJobObject"] = 5
        with pytest.raises(OSError, match="TerminateJobObject"):
            process.terminate_job()
        del kernel32.fail["TerminateJobObject"]
        process.terminate_job()
        assert len(kernel32.terminated_jobs) == 2
    finally:
        process.close()


def test_close_releases_everything_once_and_the_job_last(
    tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32
) -> None:
    launcher = _launcher(kernel32)
    process = launcher.start(_spec(tmp_path))
    assert kernel32.events == []  # both handles are kept until close
    process.close()
    process.close()
    assert kernel32.events == [("close", THREAD), ("close", PROCESS), ("close", JOB)]  # closing the job ends it
    assert process.stdin.closed
    assert process.stdout.closed
    process.terminate_job()
    assert kernel32.terminated_jobs == []
    assert process.job_members() == []


@pytest.mark.parametrize(
    ("timeout", "milliseconds"),
    [(None, INFINITE), (0, 0), (0.0004, 1), (0.5, 500), (10, 10_000), (10**9, INFINITE - 1)],
)
def test_wait_converts_seconds_to_milliseconds(
    tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32, timeout: float | None, milliseconds: int
) -> None:
    launcher = _launcher(kernel32)
    process = launcher.start(_spec(tmp_path))
    try:
        kernel32.wait_result = WAIT_TIMEOUT
        assert process.wait(timeout) is None
        assert kernel32.waits == [milliseconds]
    finally:
        process.close()


def test_wait_returns_the_exit_code_and_raises_on_failure(
    tmp_path: Path, pipes: list[int], kernel32: _FakeKernel32
) -> None:
    launcher = _launcher(kernel32)
    process = launcher.start(_spec(tmp_path))
    try:
        assert process.wait(1) == 7
        kernel32.wait_result = WAIT_FAILED
        with pytest.raises(OSError, match="WaitForSingleObject"):
            process.wait(1)
    finally:
        process.close()


if sys.platform == "win32":
    import _winapi
    import json
    import subprocess
    import threading
    import time
    from collections.abc import Iterable
    from contextlib import contextmanager
    from ctypes import WinDLL, byref, c_uint32

    from eng_harness.servers import _launcher_windows, _procinfo
    from eng_harness.servers._launcher_windows import WindowsProcess, windows_launcher
    from eng_harness.servers._procinfo import PROCESS_SIGNATURES, CtypesKernel32, WindowsProcessInspector

    PYTHON = str(Path(sys.base_prefix) / "python.exe")  # not a virtual-environment launcher: its child would escape
    ENGINE = Path(__file__).resolve().parents[1] / "fakes" / "proc" / "winengine.py"
    TREE = Path(__file__).resolve().parents[1] / "fakes" / "proc" / "wintree.py"
    ACCESS_DENIED = 5

    @pytest.fixture
    def inspector() -> WindowsProcessInspector:
        return WindowsProcessInspector(CtypesKernel32(PROCESS_SIGNATURES))

    @pytest.fixture
    def leftovers(inspector: WindowsProcessInspector) -> Iterator[list[ProcessIdentity]]:
        """Processes that outlive their job on purpose; ended at teardown by identity."""
        found: list[ProcessIdentity] = []
        yield found
        for identity in found:
            inspector.terminate(identity)

    def _tree(tmp_path: Path, policy: JobPolicy, *options: str) -> tuple[WindowsProcess, dict[str, Any]]:
        spec = LaunchSpec(
            argv=[PYTHON, str(TREE), *options],
            env=dict(os.environ),
            cwd=tmp_path,
            stderr_path=tmp_path / "tree.stderr.log",
            job=policy,
        )
        process = windows_launcher().start(spec)
        announced: dict[str, Any] = json.loads(process.stdout.readline())
        return process, announced

    @contextmanager
    def _engine(tmp_path: Path, policy: str) -> Iterator[tuple[WindowsProcess, dict[str, Any]]]:
        """Run the engine stand-in in a job of its own; yields it and what it announced."""
        spec = LaunchSpec(
            argv=[sys.executable, str(ENGINE), policy, str(tmp_path / "server.stderr.log")],
            env=dict(os.environ),
            cwd=tmp_path,
            stderr_path=tmp_path / "engine.stderr.log",
            job=JobPolicy.TOOL,
        )
        engine = windows_launcher().start(spec)
        watchdog = threading.Timer(120, engine.terminate_job)  # a stand-in that never answers cannot hang the run
        watchdog.start()
        try:
            line = engine.stdout.readline()
            assert line, (tmp_path / "engine.stderr.log").read_text(encoding="utf-8")
            yield engine, json.loads(line)
        finally:
            watchdog.cancel()
            engine.terminate_job()
            engine.close()

    def _tracked(inspector: WindowsProcessInspector, pids: Iterable[int]) -> list[ProcessIdentity]:
        """Identities of `pids`; every one must exist and run now, so that a later "ended" proves something."""
        wanted = list(pids)
        found = [i for i in (inspector.identity(pid) for pid in wanted) if i is not None]
        assert [i.pid for i in found] == wanted, "a process that the test is to track does not exist"
        assert all(inspector.alive(i) for i in found)
        return found

    def _wait_ended(
        inspector: WindowsProcessInspector, identities: list[ProcessIdentity], seconds: float = 20.0
    ) -> bool:
        for _ in range(int(seconds / 0.05)):
            if not any(inspector.alive(i) for i in identities):
                return True
            time.sleep(0.05)
        return not any(inspector.alive(i) for i in identities)

    def _inheritable(handle: int) -> bool:
        kernel32 = WinDLL("kernel32", use_last_error=True)
        kernel32.GetHandleInformation.argtypes = [c_void_p, c_void_p]
        flags = c_uint32()
        assert kernel32.GetHandleInformation(handle, byref(flags))
        return bool(flags.value & HANDLE_FLAG_INHERIT)

    @pytest.mark.windows
    def test_constants_match_the_standard_library() -> None:
        assert _launcher_windows.CREATE_NO_WINDOW == subprocess.CREATE_NO_WINDOW
        assert _launcher_windows.STARTF_USESTDHANDLES == subprocess.STARTF_USESTDHANDLES
        assert _launcher_windows.INFINITE == _winapi.INFINITE
        assert _procinfo.WAIT_OBJECT_0 == _winapi.WAIT_OBJECT_0
        assert _procinfo.WAIT_TIMEOUT == _winapi.WAIT_TIMEOUT

    @pytest.mark.windows
    def test_suspended_assign_resume(tmp_path: Path, inspector: WindowsProcessInspector) -> None:
        for _ in range(5):  # S-10: the first act of a child may be to start a grandchild; none may escape the job
            process, pids = _tree(tmp_path, JobPolicy.TOOL)
            try:
                tracked = _tracked(inspector, [pids["server"], pids["child"], pids["grandchild"]])
                assert pids["server"] == process.pid
                assert {m.pid for m in process.job_members()} >= {i.pid for i in tracked}
                assert process.started_at == tracked[0].started_at
                assert process.wait(0) is None  # it was resumed and runs
                assert not _inheritable(process.job_handle)
            finally:
                process.terminate_job()
                process.wait(10)
                process.close()

    @pytest.mark.windows
    @pytest.mark.parametrize("how", ["close", "engine_exit", "engine_kill"])
    def test_kill_on_close(tmp_path: Path, inspector: WindowsProcessInspector, how: str) -> None:
        if how == "close":  # the last handle of the job closes in the test process itself
            process, pids = _tree(tmp_path, JobPolicy.TOOL)
            tracked = _tracked(inspector, [pids["server"], pids["child"], pids["grandchild"]])
            process.close()
            assert _wait_ended(inspector, tracked)
            return
        with _engine(tmp_path, "tool") as (engine, pids):
            tracked = _tracked(inspector, [pids["server"], pids["child"], pids["grandchild"]])
            (engine_identity,) = _tracked(inspector, [pids["engine"]])
            assert set(pids["members"]) >= {i.pid for i in tracked}
            if how == "engine_exit":
                engine.stdin.close()  # end-of-file: the stand-in returns from main and the process exits
                assert _wait_ended(inspector, [engine_identity])
            else:
                assert inspector.terminate(engine_identity)
                assert _wait_ended(inspector, [engine_identity])
            assert _wait_ended(inspector, tracked)  # the engine's end closed the only handle of the server's job

    @pytest.mark.windows
    def test_breakaway_survives(
        tmp_path: Path, inspector: WindowsProcessInspector, leftovers: list[ProcessIdentity]
    ) -> None:
        process, pids = _tree(tmp_path, JobPolicy.SERVER)
        try:
            (server,) = _tracked(inspector, [pids["server"]])
            survivors = _tracked(inspector, [pids["child"], pids["grandchild"]])  # a host program started by the server
            leftovers.extend(survivors)
            assert [m.pid for m in process.job_members()] == [server.pid]  # only the server is a member
            process.terminate_job()
            assert process.wait(10) == KILLED
            assert _wait_ended(inspector, [server])
            assert all(inspector.alive(i) for i in survivors)
        finally:
            process.close()
        assert all(inspector.alive(i) for i in survivors)  # closing the job does not reach them either

    @pytest.mark.windows
    @pytest.mark.parametrize("how", ["engine_exit", "engine_kill"])
    def test_breakaway_survives_the_engine(
        tmp_path: Path, inspector: WindowsProcessInspector, leftovers: list[ProcessIdentity], how: str
    ) -> None:
        with _engine(tmp_path, "server") as (engine, pids):
            (server,) = _tracked(inspector, [pids["server"]])
            survivors = _tracked(inspector, [pids["child"], pids["grandchild"]])
            leftovers.extend(survivors)
            (engine_identity,) = _tracked(inspector, [pids["engine"]])
            assert pids["members"] == [server.pid]
            if how == "engine_exit":
                engine.stdin.close()
            else:
                assert inspector.terminate(engine_identity)
            assert _wait_ended(inspector, [engine_identity])
            assert _wait_ended(inspector, [server])  # the job closed with the engine and took the server
            assert all(inspector.alive(i) for i in survivors)

    @pytest.mark.windows
    def test_tool_job_no_breakaway(tmp_path: Path, inspector: WindowsProcessInspector) -> None:
        process, pids = _tree(tmp_path, JobPolicy.TOOL)
        try:
            tracked = _tracked(inspector, [pids["server"], pids["child"], pids["grandchild"]])
            assert {m.pid for m in process.job_members()} >= {i.pid for i in tracked}  # none left the job
            assert process.wait(0.2) is None  # the step's timeout elapsed with the tool still running
            process.terminate_job()
            assert process.wait(10) == KILLED
            assert _wait_ended(inspector, tracked)
            assert process.job_members() == []
        finally:
            process.close()

    @pytest.mark.windows
    def test_tool_job_refuses_an_explicit_breakaway(tmp_path: Path, inspector: WindowsProcessInspector) -> None:
        process, pids = _tree(tmp_path, JobPolicy.TOOL, "--breakaway")
        try:
            assert pids["breakaway"] == "denied"  # CREATE_BREAKAWAY_FROM_JOB fails: the job allows no breakaway
        finally:
            process.terminate_job()
            process.close()

    @pytest.mark.windows
    def test_jobs_are_independent(tmp_path: Path, inspector: WindowsProcessInspector) -> None:
        first, first_pids = _tree(tmp_path, JobPolicy.TOOL)
        second, second_pids = _tree(tmp_path, JobPolicy.TOOL)
        try:
            ended = _tracked(inspector, [first_pids["server"], first_pids["child"], first_pids["grandchild"]])
            kept = _tracked(inspector, [second_pids["server"], second_pids["child"], second_pids["grandchild"]])
            first.terminate_job()
            assert _wait_ended(inspector, ended)
            assert all(inspector.alive(i) for i in kept)
        finally:
            for process in (first, second):
                process.terminate_job()
                process.close()
