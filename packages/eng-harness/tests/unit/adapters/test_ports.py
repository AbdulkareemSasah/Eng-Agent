"""`AdapterPorts` owns the server manager's lifetime (plan 0002 T22; spec 0002 AC48, section 4.1)."""

from pathlib import Path
from types import TracebackType
from typing import Any, cast

import anyio
import pytest

from eng_harness.adapters import AdapterPorts
from eng_harness.servers import ServerManager, ServersConfig


class _Manager(ServerManager):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(ServersConfig(), tmp_path)
        self.events: list[str] = []

    async def __aenter__(self) -> _Manager:
        self.events.append("enter")
        await super().__aenter__()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.events.append(f"exit {exc_type.__name__ if exc_type else 'none'}")
        await super().__aexit__(exc_type, exc, tb)


def _ports(manager: _Manager) -> AdapterPorts:
    tool_port, host_port = cast(Any, object()), cast(Any, object())
    return AdapterPorts(tool_port=tool_port, host_port=host_port, servers=manager)


def test_ports_enter_and_leave_server_manager(tmp_path: Path) -> None:
    manager = _Manager(tmp_path)
    ports = _ports(manager)

    async def normal() -> None:
        async with ports as entered:
            assert entered is ports
            assert manager.events == ["enter"]

    anyio.run(normal)
    assert manager.events == ["enter", "exit none"]

    failing = _Manager(tmp_path)

    async def failure() -> None:
        async with _ports(failing):
            raise RuntimeError("boom")

    with pytest.raises(ExceptionGroup) as caught:  # the manager's task group wraps what leaves its context
        anyio.run(failure)
    assert [str(item) for item in caught.value.exceptions] == ["boom"]
    assert failing.events == ["enter", "exit RuntimeError"]
