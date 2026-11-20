"""Pipe-keyed host lock for Revit (plan 0011 T11; spec 0011 AC26, §4.12).

The lock API itself is product-neutral (`acquire_key`); the test keys it by a hash of the pipe name as the adapter does.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock

from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

_PIPE = r"\\.\pipe\sasaah-revit-session"
_PROGRAM = "revit"
_START = 1_700_000_000_000


def _locks(lock_dir: Path, run_id: str, engine_pid: int = 11) -> HostLocks:
    engine = ProcessIdentity(pid=engine_pid, started_at=f"boot:{engine_pid}", exe_name="python")
    return HostLocks(lock_dir, run_id=run_id, engine=engine, clock=FixedClock(_START))


def _pipe_key(pipe_name: str) -> str:
    """Opaque lock key: sha256 of the pipe name (spec 0011 AC26 / §4.12)."""
    return hashlib.sha256(pipe_name.encode("utf-8")).hexdigest()


def test_pipe_key(tmp_path: Path) -> None:
    """AC26: the host lock is keyed by a hash of the pipe name; a second engine on the same pipe gets HOST_LOCKED."""
    from eng_harness.adapters.revit._session_ops import pipe_lock_key

    key = pipe_lock_key(_PIPE)
    assert key == _pipe_key(_PIPE)
    assert key != _pipe_key(_PIPE + "-other")

    first = _locks(tmp_path / "locks", "run-A", engine_pid=os.getpid())
    second = _locks(tmp_path / "locks", "run-B", engine_pid=os.getpid() + 1)
    first.acquire_key(_PROGRAM, key)
    with pytest.raises(ContractError) as refused:
        second.acquire_key(_PROGRAM, key)
    assert refused.value.detail.code is ErrorCode.HOST_LOCKED
    assert refused.value.detail.retryable is False
    assert "run-A" in refused.value.detail.message

    # A different pipe name is a different lock file.
    other_key = pipe_lock_key(_PIPE + "-other")
    second.acquire_key(_PROGRAM, other_key)
    assert first.key_path(_PROGRAM, key) != second.key_path(_PROGRAM, other_key)

    first.release_all()
    second.acquire_key(_PROGRAM, key)
