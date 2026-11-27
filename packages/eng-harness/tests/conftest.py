"""Shared fixtures of the eng-harness tests: deterministic clock and ids, a result store, a run folder."""

import ipaddress
import socket
from pathlib import Path
from typing import Any

import pytest
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z


@pytest.fixture
def clock() -> FixedClock:
    """A clock that advances by one millisecond per reading."""
    return FixedClock(START_MS, 1)


@pytest.fixture
def ids(clock: FixedClock) -> SeededIdSource:
    """A seeded id source."""
    return SeededIdSource(b"harness", clock)


@pytest.fixture
def store(tmp_path: Path, ids: SeededIdSource) -> ResultStore:
    """A result store in a temporary workspace that knows the harness kinds."""
    from eng_harness._kinds import HARNESS_KINDS  # imported late so tests that need no store run without it

    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS, ids, FixedClock(START_MS, 1))


@pytest.fixture
def run_dir(tmp_path: Path, ids: SeededIdSource) -> Path:
    """An empty run folder `runs/run_<ULID>`."""
    path = tmp_path / "runs" / f"run_{ids.new_ulid()}"
    path.mkdir(parents=True)
    return path


def _refuse_non_loopback(original: Any) -> Any:
    def guarded(self: socket.socket, address: Any) -> Any:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            host = address[0]
            try:
                loopback = str(host).lower() == "localhost" or ipaddress.ip_address(host).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                raise OSError("connection to a non-loopback address refused by the test network guard")
        return original(self, address)

    return guarded


@pytest.fixture(autouse=True)
def _network_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec 0009 AC36: refuse non-loopback connections and PydanticAI model requests in every test."""
    monkeypatch.setattr(socket.socket, "connect", _refuse_non_loopback(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse_non_loopback(socket.socket.connect_ex))
    from pydantic_ai import models

    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
