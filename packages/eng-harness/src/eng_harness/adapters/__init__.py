"""Adapters from the engine's ports to host tools: descriptors and allowlists (spec 0002 section 4.5)."""

from dataclasses import dataclass
from typing import Any, Self

from eng_harness.adapters._allowlist import Allowlist, AllowlistError, load_allowlist
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.ports import HostPort, ToolPort
from eng_harness.servers import ServerManager


@dataclass(frozen=True)
class AdapterPorts:
    """The ports of a run; `async with` enters and leaves its `ServerManager` (spec 0002 AC48)."""

    tool_port: ToolPort
    host_port: HostPort
    servers: ServerManager

    async def __aenter__(self) -> Self:
        await self.servers.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.servers.__aexit__(*exc)


__all__ = ["AdapterPorts", "Allowlist", "AllowlistError", "ToolDescriptor", "load_allowlist"]
