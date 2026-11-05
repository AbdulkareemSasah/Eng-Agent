"""Windows process inspector (plan 0002 T3; spec 0002 AC7, section 4.3.1).

The rules run on every platform over a fake kernel32 (the tests before the platform check); the tests against the real
Windows API are defined only on Windows (marker `windows`). They have not run on Windows yet and are an owner local
test.
"""

import os
import re
import sys
from ctypes import c_void_p, sizeof
from dataclasses import dataclass
from functools import partial
from typing import Any

import pytest

from eng_harness.servers._procinfo import FILETIME, PROCESSENTRY32W, ProcessIdentity, WindowsProcessInspector

# winnt.h access rights and winerror.h codes, restated here as the oracle of the fake.
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_PARAMETER = 87
ERROR_NO_MORE_FILES = 18
ERROR_BAD_LENGTH = 24
WAIT_OBJECT_0, WAIT_TIMEOUT = 0, 0x102
TH32CS_SNAPPROCESS = 0x2
KILLED = 1  # the exit code given to a process the inspector ends

CREATED = 133_000_000_000_000_000  # a FILETIME of 2022: 100 ns ticks since 1601-01-01
OTHER = "C:\\Program Files\\Vendor\\Other.exe"
PATH = "C:\\Program Files\\Vendor\\Etabs.exe"
ETABS = ProcessIdentity(pid=42, started_at=str(CREATED), exe_name="Etabs.exe")


@dataclass
class _Process:
    created: int
    parent: int = 1
    path: str = PATH
    running: bool = True


class _FakeKernel32:
    """kernel32 process queries over an in-memory table; records the handle every call used.

    A kernel32 function `OpenProcess` is served by the method `open_process` (the Win32 spelling is not a Python name).
    """

    def __init__(self, table: dict[int, _Process]) -> None:
        self.table = table
        self.denied: set[int] = set()
        self.fail: dict[str, int] = {}  # function name -> the last error it sets while returning failure
        self.terminate_fails = False
        self.exits_before_terminate = False
        self.enumeration_error = ERROR_NO_MORE_FILES
        self.opened: list[tuple[int, int]] = []  # (rights, pid)
        self.closed: list[int] = []
        self.queried: list[int] = []  # handles of GetProcessTimes
        self.terminated: list[int] = []  # handles of TerminateProcess
        self._pid_of: dict[int, int] = {}
        self._error = 0
        self._pending: list[tuple[int, _Process]] = []

    def __getattr__(self, name: str) -> Any:
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
        if snake == name:
            raise AttributeError(name)  # not a kernel32 function this fake serves
        return getattr(self, snake)

    def last_error(self) -> int:
        return self._error

    def _fails(self, name: str) -> bool:
        if name in self.fail:
            self._error = self.fail[name]
        return name in self.fail

    def open_process(self, rights: int, inherit: bool, pid: int) -> int | None:
        if pid in self.denied:
            self._error = ERROR_ACCESS_DENIED
            return None
        if pid not in self.table:
            self._error = ERROR_INVALID_PARAMETER
            return None
        handle = 1000 + len(self.opened)
        self.opened.append((rights, pid))
        self._pid_of[handle] = pid
        return handle

    def get_process_times(self, handle: int, created: Any, *ignored: Any) -> int:
        self.queried.append(handle)
        if self._fails("GetProcessTimes"):
            return 0
        value = self.table[self._pid_of[handle]].created
        created._obj.dwLowDateTime, created._obj.dwHighDateTime = value & 0xFFFFFFFF, value >> 32
        return 1

    def wait_for_single_object(self, handle: int, milliseconds: int) -> int:
        assert milliseconds == 0  # a check, never a wait
        return WAIT_TIMEOUT if self.table[self._pid_of[handle]].running else WAIT_OBJECT_0

    def query_full_process_image_name_w(self, handle: int, flags: int, path: Any, size: Any) -> int:
        assert flags == 0
        assert size._obj.value >= len(PATH)  # room for a long path
        if self._fails("QueryFullProcessImageNameW"):
            return 0
        path.value = self.table[self._pid_of[handle]].path
        return 1

    def terminate_process(self, handle: int, exit_code: int) -> int:
        self.terminated.append(handle)
        assert exit_code == KILLED
        process = self.table[self._pid_of[handle]]
        if self.exits_before_terminate:
            process.running = False
        if self.terminate_fails:
            self._error = ERROR_ACCESS_DENIED
            return 0
        process.running = False
        return 1

    def close_handle(self, handle: int) -> int:
        self.closed.append(handle)
        return 1

    def create_toolhelp32_snapshot(self, flags: int, pid: int) -> int:
        assert flags == TH32CS_SNAPPROCESS
        if self._fails("CreateToolhelp32Snapshot"):
            return 0
        self._pending = sorted(self.table.items())
        return 5000

    def _next_entry(self, entry: Any) -> int:
        if not self._pending:
            self._error = self.enumeration_error
            return 0
        pid, process = self._pending.pop(0)
        assert entry._obj.dwSize == sizeof(PROCESSENTRY32W)
        entry._obj.th32ProcessID, entry._obj.th32ParentProcessID = pid, process.parent
        units = list(memoryview(process.path.rpartition("\\")[2].encode("utf-16-le")).cast("H"))
        entry._obj.szExeFile[: len(units) + 1] = [*units, 0]
        return 1

    def process32_first_w(self, snapshot: int, entry: Any) -> int:
        return self._next_entry(entry)

    def process32_next_w(self, snapshot: int, entry: Any) -> int:
        return self._next_entry(entry)


def _inspector(table: dict[int, _Process]) -> tuple[WindowsProcessInspector, _FakeKernel32]:
    kernel32 = _FakeKernel32(table)
    return WindowsProcessInspector(kernel32), kernel32


def _running(kernel32: _FakeKernel32, pid: int) -> bool:
    return kernel32.table[pid].running


def test_structure_layouts() -> None:
    # Sizes and offsets of the 64-bit layouts of minwinbase.h and tlhelp32.h (natural alignment).
    assert sizeof(c_void_p) == 8
    assert sizeof(FILETIME) == 8
    assert sizeof(PROCESSENTRY32W) == 568
    offsets = {"th32ProcessID": 8, "th32DefaultHeapID": 16, "th32ParentProcessID": 32, "szExeFile": 44}
    assert {name: getattr(PROCESSENTRY32W, name).offset for name in offsets} == offsets


def test_identity_fields() -> None:
    inspector, _ = _inspector({42: _Process(CREATED)})
    first, second = inspector.identity(42), inspector.identity(42)
    assert first == second
    assert first == ETABS


def test_started_at_is_the_creation_filetime_of_both_words() -> None:
    inspector, _ = _inspector({7: _Process(0x0000_0001_0000_0002)})  # high word 1, low word 2
    identity = inspector.identity(7)
    assert identity is not None
    assert identity.started_at == str(0x0000_0001_0000_0002)


def test_unknown_pid_has_no_identity_and_is_not_alive() -> None:
    inspector, _ = _inspector({42: _Process(CREATED)})
    missing = ProcessIdentity(43, str(CREATED), "x.exe")
    assert inspector.identity(43) is None
    assert inspector.alive(missing) is False
    assert inspector.terminate(missing) is False


def test_exited_process_has_no_identity() -> None:
    inspector, _ = _inspector({42: _Process(CREATED, running=False)})
    assert inspector.identity(42) is None


def test_access_denied_is_an_error_not_a_missing_process() -> None:
    inspector, kernel32 = _inspector({4: _Process(CREATED)})
    kernel32.denied.add(4)
    with pytest.raises(OSError, match=r"OpenProcess\(4\)"):
        inspector.identity(4)


def test_every_handle_is_closed() -> None:
    inspector, kernel32 = _inspector({42: _Process(CREATED)})
    inspector.identity(42)
    inspector.alive(ETABS)
    inspector.terminate(ETABS)
    assert len(kernel32.opened) == 3
    assert sorted(kernel32.closed) == [1000, 1001, 1002]


def test_alive_needs_matching_start_time_and_a_running_process() -> None:
    inspector, kernel32 = _inspector({42: _Process(CREATED)})
    reused = ProcessIdentity(42, str(CREATED - 1), "Etabs.exe")
    assert inspector.alive(ETABS) is True
    assert inspector.alive(reused) is False
    kernel32.table[42].running = False
    assert inspector.alive(ETABS) is False


def test_terminate_checks_start_time() -> None:
    inspector, kernel32 = _inspector({42: _Process(CREATED)})
    reused = ProcessIdentity(42, str(CREATED - 1), "Etabs.exe")
    assert inspector.terminate(reused) is False
    assert kernel32.terminated == []
    assert _running(kernel32, 42)
    assert inspector.terminate(ETABS) is True
    assert not _running(kernel32, 42)
    assert inspector.terminate(ETABS) is False  # already gone


def test_terminate_uses_the_one_handle_that_was_compared() -> None:
    inspector, kernel32 = _inspector({42: _Process(CREATED)})
    assert inspector.terminate(ETABS) is True
    (rights, pid) = kernel32.opened[0]  # opened once, with the right to terminate
    assert len(kernel32.opened) == 1
    assert pid == 42
    assert rights & PROCESS_TERMINATE
    assert rights & PROCESS_QUERY_LIMITED_INFORMATION
    assert rights & SYNCHRONIZE
    assert kernel32.queried == kernel32.terminated == [1000]  # the start time and the kill went through that handle


def test_terminate_failure_is_raised_while_the_process_runs() -> None:
    inspector, kernel32 = _inspector({42: _Process(CREATED)})
    kernel32.terminate_fails = True
    with pytest.raises(OSError, match="TerminateProcess"):
        inspector.terminate(ETABS)


def test_terminate_of_a_process_that_ended_meanwhile_is_false() -> None:
    inspector, kernel32 = _inspector({42: _Process(CREATED)})
    kernel32.terminate_fails = kernel32.exits_before_terminate = True
    assert inspector.terminate(ETABS) is False


def test_snapshot_compares_names_without_case() -> None:
    table = {10: _Process(CREATED, path="C:\\a\\ETABS.EXE"), 11: _Process(CREATED, path="C:\\a\\other.exe")}
    inspector, _ = _inspector(table)
    assert [i.pid for i in inspector.snapshot(["etabs.exe"])] == [10]
    assert inspector.snapshot(["missing.exe"]) == []


def test_children_are_direct_running_and_not_older_than_the_parent() -> None:
    table = {
        10: _Process(CREATED),
        11: _Process(CREATED + 5, parent=10),
        12: _Process(CREATED - 5, parent=10),  # created before pid 10: its parent pid was reused
        13: _Process(CREATED + 9, parent=11),  # a grandchild
        14: _Process(CREATED + 6, parent=10, running=False),
    }
    inspector, _ = _inspector(table)
    assert [c.pid for c in inspector.children(10)] == [11]
    assert inspector.children(99) == []


def test_listing_skips_inaccessible(caplog: pytest.LogCaptureFixture) -> None:
    table = {
        10: _Process(CREATED, path=OTHER),
        11: _Process(CREATED + 5, parent=10, path=OTHER),  # a child the engine may not open
        12: _Process(CREATED + 6, parent=10, path=OTHER),
        13: _Process(CREATED, path="C:\\a\\Etabs.exe"),  # a matching process the engine may not open
        14: _Process(CREATED, path="C:\\a\\Etabs.exe"),
    }
    inspector, kernel32 = _inspector(table)
    kernel32.denied = {11, 13}
    with caplog.at_level("DEBUG"):
        assert [c.pid for c in inspector.children(10)] == [12]
        assert [i.pid for i in inspector.snapshot(["etabs.exe"])] == [14]
    assert "11" in caplog.text
    assert "13" in caplog.text
    with pytest.raises(OSError, match=r"OpenProcess\(11\)"):
        inspector.identity(11)
    assert set(range(1000, 1000 + len(kernel32.opened))) <= set(kernel32.closed)


@pytest.mark.parametrize("call", ["GetProcessTimes", "QueryFullProcessImageNameW", "CreateToolhelp32Snapshot"])
def test_a_failed_query_is_raised_and_the_handle_is_still_closed(call: str) -> None:
    inspector, kernel32 = _inspector({42: _Process(CREATED)})
    kernel32.fail[call] = ERROR_ACCESS_DENIED
    query = (
        partial(inspector.snapshot, ["etabs.exe"])
        if call == "CreateToolhelp32Snapshot"
        else partial(inspector.identity, 42)
    )
    with pytest.raises(OSError, match=call):
        query()
    assert sorted(kernel32.closed) == list(range(1000, 1000 + len(kernel32.opened)))


def test_a_failed_enumeration_is_raised() -> None:
    inspector, kernel32 = _inspector({10: _Process(CREATED)})
    kernel32.enumeration_error = ERROR_BAD_LENGTH
    with pytest.raises(OSError, match="Process32NextW"):
        inspector.snapshot(["etabs.exe"])


if sys.platform == "win32":
    from collections.abc import Iterator
    from pathlib import Path

    from eng_harness.servers._launcher import JobPolicy, LaunchSpec
    from eng_harness.servers._launcher_windows import WindowsProcess, windows_launcher
    from eng_harness.servers._procinfo import PROCESS_SIGNATURES, CtypesKernel32

    def windows_inspector() -> WindowsProcessInspector:
        return WindowsProcessInspector(CtypesKernel32(PROCESS_SIGNATURES))

    def _sleeper(tmp_path: Path) -> WindowsProcess:
        """Start a sleeping interpreter in a tool job; the base interpreter, so the pid is the program's own."""
        spec = LaunchSpec(
            argv=[str(Path(sys.base_prefix) / "python.exe"), "-c", "import time; time.sleep(300)"],
            env=dict(os.environ),
            cwd=tmp_path,
            stderr_path=tmp_path / "sleeper.stderr.log",
            job=JobPolicy.TOOL,
        )
        return windows_launcher().start(spec)

    @pytest.fixture
    def sleeper(tmp_path: Path) -> Iterator[WindowsProcess]:
        process = _sleeper(tmp_path)
        try:
            yield process
        finally:
            process.terminate_job()
            process.wait(10)
            process.close()

    @pytest.mark.windows
    def test_identity_windows(sleeper: WindowsProcess, tmp_path: Path) -> None:
        inspector = windows_inspector()
        first, second = inspector.identity(sleeper.pid), inspector.identity(sleeper.pid)
        assert first is not None
        assert first == second
        assert first.pid == sleeper.pid
        assert first.started_at == sleeper.started_at
        assert first.started_at.isdigit()
        assert first.exe_name.lower() == "python.exe"
        assert inspector.alive(first)
        other = _sleeper(tmp_path)
        try:
            later = inspector.identity(other.pid)
            assert later is not None
            assert later != first
            assert int(later.started_at) >= int(first.started_at)  # created after it, on the same clock
        finally:
            other.terminate_job()
            other.wait(10)
            other.close()

    @pytest.mark.windows
    def test_unknown_pid_windows() -> None:
        assert windows_inspector().identity(0x7FFFFFFC) is None  # a multiple of four far above any pid in use

    @pytest.mark.windows
    def test_terminate_checks_start_time_windows(sleeper: WindowsProcess) -> None:
        inspector = windows_inspector()
        real = inspector.identity(sleeper.pid)
        assert real is not None
        reused = ProcessIdentity(real.pid, str(int(real.started_at) + 1), real.exe_name)
        assert inspector.alive(real)
        assert not inspector.alive(reused)
        assert inspector.terminate(reused) is False
        assert sleeper.wait(0) is None  # untouched
        assert inspector.terminate(real) is True
        assert sleeper.wait(10) == KILLED
        assert not inspector.alive(real)
        assert inspector.terminate(real) is False
        assert inspector.identity(real.pid) is None

    @pytest.mark.windows
    def test_children_and_snapshot_windows(sleeper: WindowsProcess) -> None:
        inspector = windows_inspector()
        mine = inspector.identity(sleeper.pid)
        assert mine is not None
        assert inspector.children(sleeper.pid) == []
        assert mine in inspector.children(os.getpid())  # this process created it
        assert mine in inspector.snapshot([mine.exe_name.upper()])  # the file name is compared without case
        assert inspector.snapshot(["no-such-program-name.exe"]) == []
