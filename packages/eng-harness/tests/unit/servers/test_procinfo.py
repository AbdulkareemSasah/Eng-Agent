"""POSIX process inspector (plan 0002 T2; spec 0002 AC7, section 4.3.1)."""

import dataclasses
import os
import signal
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from eng_harness.servers._procinfo import PosixProcessInspector, ProcessIdentity

_SLEEP = [sys.executable, "-c", "import time; time.sleep(120)"]


@pytest.fixture
def sleeper() -> Iterator[subprocess.Popen[bytes]]:
    process = subprocess.Popen(_SLEEP, stdin=subprocess.DEVNULL)
    try:
        yield process
    finally:
        process.kill()
        process.wait()


def test_identity_stable(sleeper: subprocess.Popen[bytes]) -> None:
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
    other = subprocess.Popen(_SLEEP, stdin=subprocess.DEVNULL)
    try:
        assert inspector.identity(other.pid) != first
    finally:
        other.kill()
        other.wait()


def test_identity_of_missing_process_is_none() -> None:
    assert PosixProcessInspector().identity(2**31 - 1) is None


def test_terminate_checks_start_time(sleeper: subprocess.Popen[bytes]) -> None:
    inspector = PosixProcessInspector()
    real = inspector.identity(sleeper.pid)
    assert real is not None
    reused = dataclasses.replace(real, started_at=real.started_at + "0")  # same pid, other start time
    assert inspector.alive(real)
    assert not inspector.alive(reused)
    assert inspector.terminate(reused) is False
    assert sleeper.poll() is None
    assert inspector.terminate(real) is True
    assert sleeper.wait(timeout=10) == -signal.SIGKILL
    assert not inspector.alive(real)
    assert inspector.terminate(real) is False


def test_terminate_without_pidfd(sleeper: subprocess.Popen[bytes], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(os, "pidfd_open", raising=False)
    inspector = PosixProcessInspector()
    real = inspector.identity(sleeper.pid)
    assert real is not None
    reused = ProcessIdentity(pid=real.pid, started_at="other:1", exe_name=real.exe_name)
    assert inspector.terminate(reused) is False
    assert sleeper.poll() is None
    assert inspector.terminate(real) is True
    assert sleeper.wait(timeout=10) == -signal.SIGKILL


def test_children_and_snapshot(sleeper: subprocess.Popen[bytes]) -> None:
    inspector = PosixProcessInspector()
    child = inspector.identity(sleeper.pid)
    assert child is not None
    assert child in inspector.children(os.getpid())
    assert inspector.children(sleeper.pid) == []
    assert child in inspector.snapshot([child.exe_name])
    assert inspector.snapshot(["no-such-program-name"]) == []
