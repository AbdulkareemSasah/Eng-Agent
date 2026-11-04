"""POSIX process inspector (plan 0002 T2; spec 0002 AC7, section 4.3.1)."""

import dataclasses
import os
import signal
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from eng_harness.servers._launcher import JobPolicy, LaunchedProcess, LaunchSpec, PosixLauncher
from eng_harness.servers._procinfo import PosixProcessInspector, ProcessIdentity


def _start_sleeper(tmp_path: Path) -> LaunchedProcess:
    spec = LaunchSpec(
        argv=[sys.executable, "-c", "import time; time.sleep(120)"],
        env=dict(os.environ),
        cwd=tmp_path,
        stderr_path=tmp_path / "sleeper.stderr.log",
        job=JobPolicy.TOOL,
    )
    return PosixLauncher().start(spec)


@pytest.fixture
def sleeper(tmp_path: Path) -> Iterator[LaunchedProcess]:
    process = _start_sleeper(tmp_path)
    try:
        yield process
    finally:
        process.terminate_job()
        process.wait(10)
        process.close()


def test_identity_stable(sleeper: LaunchedProcess, tmp_path: Path) -> None:
    inspector = PosixProcessInspector()
    first = inspector.identity(sleeper.pid)
    second = inspector.identity(sleeper.pid)
    assert first is not None
    assert first == second
    assert first.pid == sleeper.pid
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    assert first.started_at.startswith(boot_id + ":")
    assert first.started_at.removeprefix(boot_id + ":").isdigit()
    assert first.exe_name
    other = _start_sleeper(tmp_path)
    try:
        assert inspector.identity(other.pid) != first
    finally:
        other.terminate_job()
        other.wait(10)
        other.close()


def test_identity_of_missing_process_is_none() -> None:
    assert PosixProcessInspector().identity(2**31 - 1) is None


def test_terminate_checks_start_time(sleeper: LaunchedProcess) -> None:
    inspector = PosixProcessInspector()
    real = inspector.identity(sleeper.pid)
    assert real is not None
    reused = dataclasses.replace(real, started_at=real.started_at + "0")  # same pid, other start time
    assert inspector.alive(real)
    assert not inspector.alive(reused)
    assert inspector.terminate(reused) is False
    assert sleeper.wait(0) is None
    assert inspector.terminate(real) is True
    assert sleeper.wait(10) == -signal.SIGKILL
    assert not inspector.alive(real)
    assert inspector.terminate(real) is False


def test_terminate_without_pidfd(sleeper: LaunchedProcess, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(os, "pidfd_open", raising=False)
    inspector = PosixProcessInspector()
    real = inspector.identity(sleeper.pid)
    assert real is not None
    reused = ProcessIdentity(pid=real.pid, started_at="other:1", exe_name=real.exe_name)
    assert inspector.terminate(reused) is False
    assert sleeper.wait(0) is None
    assert inspector.terminate(real) is True
    assert sleeper.wait(10) == -signal.SIGKILL


def test_children_and_snapshot(sleeper: LaunchedProcess) -> None:
    inspector = PosixProcessInspector()
    child = inspector.identity(sleeper.pid)
    assert child is not None
    assert child in inspector.children(os.getpid())
    assert inspector.children(sleeper.pid) == []
    assert child in inspector.snapshot([child.exe_name])
    assert inspector.snapshot(["no-such-program-name"]) == []
