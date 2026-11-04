"""POSIX process launcher (plan 0002 T2; spec 0002 AC4, AC6, section 4.3.1)."""

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from eng_harness.servers._launcher import JobPolicy, LaunchedProcess, LaunchError, LaunchSpec, PosixLauncher
from eng_harness.servers._procinfo import PosixProcessInspector, ProcessIdentity

_FAKES = Path(__file__).resolve().parents[2] / "fakes" / "proc"
_TREE = _FAKES / "tree.py"


def _spec(tmp_path: Path, job: JobPolicy, *extra: str, argv: list[str] | None = None) -> LaunchSpec:
    return LaunchSpec(
        argv=argv if argv is not None else [sys.executable, str(_TREE), *extra],
        env=dict(os.environ),
        cwd=tmp_path,
        stderr_path=tmp_path / "servers" / "stand-in.stderr.log",
        job=job,
    )


def _announced(process: LaunchedProcess) -> dict[str, int]:
    pids: dict[str, int] = json.loads(process.stdout.readline())
    return pids


def _alive(inspector: PosixProcessInspector, pid: int) -> bool:
    identity = inspector.identity(pid)
    return identity is not None and inspector.alive(identity)


@pytest.fixture
def cleanup() -> Iterator[list[int]]:
    """Pids that a test may leave running; killed at teardown."""
    leftovers: list[int] = []
    yield leftovers
    for pid in leftovers:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            continue


def test_group_terminated(tmp_path: Path, cleanup: list[int]) -> None:
    inspector = PosixProcessInspector()
    process = PosixLauncher().start(_spec(tmp_path, JobPolicy.SERVER, "--children"))
    pids = _announced(process)
    cleanup.extend(pids.values())
    try:
        assert process.pid == pids["server"]
        identity = inspector.identity(process.pid)
        assert identity is not None
        assert process.started_at == identity.started_at
        assert {m.pid for m in process.job_members()} == {pids["server"], pids["child"]}  # host: own session
        process.terminate_job()
        assert process.wait(10) == -signal.SIGKILL
        assert process.job_members() == []
        for name in ("server", "child"):
            assert not _alive(inspector, pids[name])
        assert _alive(inspector, pids["host"])
    finally:
        process.close()


def test_server_exits_when_engine_killed(tmp_path: Path, cleanup: list[int]) -> None:
    inspector = PosixProcessInspector()
    engine = PosixLauncher().start(
        _spec(tmp_path, JobPolicy.TOOL, argv=[sys.executable, str(_FAKES / "engine.py"), str(tmp_path / "s.log")])
    )
    try:
        server_pid = int(engine.stdout.readline())
        cleanup.append(server_pid)
        assert _alive(inspector, server_pid)
        engine.terminate_job()  # the engine's group only: the server has a session of its own
        engine.wait(10)
        for _ in range(200):  # the server ends on stdin end-of-file; poll for up to 10 s
            if not _alive(inspector, server_pid):
                break
            time.sleep(0.05)
        assert not _alive(inspector, server_pid)
    finally:
        engine.terminate_job()
        engine.close()


def test_tool_timeout_kills_group(tmp_path: Path, cleanup: list[int]) -> None:
    inspector = PosixProcessInspector()
    process = PosixLauncher().start(_spec(tmp_path, JobPolicy.TOOL, "--children"))
    pids = _announced(process)
    cleanup.extend(pids.values())
    try:
        assert process.wait(0.2) is None  # the step's timeout elapsed with the tool still running
        process.terminate_job()
        assert process.wait(10) == -signal.SIGKILL
        assert not _alive(inspector, pids["server"])
        assert not _alive(inspector, pids["child"])
        process.terminate_job()  # idempotent once the group is gone
    finally:
        process.close()


def test_stderr_goes_to_file_and_exit_code_is_returned(tmp_path: Path) -> None:
    code = "import sys; sys.stderr.write('boom'); sys.exit(3)"
    process = PosixLauncher().start(_spec(tmp_path, JobPolicy.SERVER, argv=[sys.executable, "-c", code]))
    try:
        assert process.wait(10) == 3
    finally:
        process.close()
        process.close()  # idempotent
    assert (tmp_path / "servers" / "stand-in.stderr.log").read_text(encoding="utf-8") == "boom"


def test_start_failure_is_typed(tmp_path: Path) -> None:
    with pytest.raises(LaunchError, match="no-such-program"):
        PosixLauncher().start(_spec(tmp_path, JobPolicy.SERVER, argv=[str(tmp_path / "no-such-program")]))


class _ScriptedGroup(PosixProcessInspector):
    """Inspector whose group listing is scripted, and which records which processes it was asked to end."""

    def __init__(self, listings: list[list[ProcessIdentity]]) -> None:
        super().__init__()
        self._listings = listings
        self.terminated: list[ProcessIdentity] = []

    def group_members(self, pgid: int) -> list[ProcessIdentity]:
        return self._listings.pop(0) if self._listings else []

    def terminate(self, identity: ProcessIdentity) -> bool:
        self.terminated.append(identity)
        return True


def test_terminate_job_never_signals_again_once_group_seen_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the leader is reaped and the group was seen empty, a reused group number must not be touched (R1)."""
    stranger = ProcessIdentity(pid=1, started_at="other", exe_name="stranger")
    inspector = _ScriptedGroup([[], [stranger]])  # the second listing is a new, unrelated group with the same number
    signalled: list[int] = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: signalled.append(pgid))
    process = PosixLauncher(inspector).start(_spec(tmp_path, JobPolicy.TOOL, argv=[sys.executable, "-c", "pass"]))
    try:
        assert process.wait(10) == 0
        process.terminate_job()  # the group is empty
        process.terminate_job()  # idempotent: must not look at the group again
    finally:
        process.close()
    assert signalled == []
    assert inspector.terminated == []


def test_terminate_job_after_reaping_ends_members_by_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Once the leader is reaped the group number is no longer reserved: members end by pid and start time."""
    member = ProcessIdentity(pid=1, started_at="member", exe_name="member")
    inspector = _ScriptedGroup([[member]])
    signalled: list[int] = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: signalled.append(pgid))
    process = PosixLauncher(inspector).start(_spec(tmp_path, JobPolicy.TOOL, argv=[sys.executable, "-c", "pass"]))
    try:
        assert process.wait(10) == 0
        process.terminate_job()
    finally:
        process.close()
    assert signalled == []
    assert inspector.terminated == [member]


def test_failed_identity_closes_pipes_and_reaps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _NoIdentity(PosixProcessInspector):
        def identity(self, pid: int) -> ProcessIdentity | None:
            return None

    created: list[subprocess.Popen[bytes]] = []
    real_popen = subprocess.Popen

    def spy(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        popen: subprocess.Popen[bytes] = real_popen(*args, **kwargs)
        created.append(popen)
        return popen

    monkeypatch.setattr(subprocess, "Popen", spy)
    with pytest.raises(LaunchError, match="no start time"):
        PosixLauncher(_NoIdentity()).start(_spec(tmp_path, JobPolicy.SERVER, "--children"))
    (popen,) = created
    assert popen.returncode is not None  # killed and reaped
    assert popen.stdin is not None
    assert popen.stdin.closed
    assert popen.stdout is not None
    assert popen.stdout.closed
