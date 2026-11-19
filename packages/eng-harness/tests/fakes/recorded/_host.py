"""The recorded-reply fake (plan 0002 T17; spec 0002 section 4.8.2): serves a session from a recording folder.

A request is matched by tool and canonical arguments with the recorded one, the first unused exchange that equals it
(so repeated requests are served in recorded order); a request nobody recorded fails the test with
`UnmatchedRequestError`.
Arguments must be in the recording's sanitized form; give a `Sanitizer` to sanitize live arguments first (the numbering
of placeholders then follows the first appearance in the requests, which is the recording's when no reply names a
file first).
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import MCPError, types

from eng_harness.servers import CallEffect, Sanitizer, verify_manifest


class UnmatchedRequestError(AssertionError):
    """A request that the recording does not hold (or holds only as already served)."""


@dataclass(frozen=True)
class Exchange:
    """One recorded request and reply (`result`) or JSON-RPC error."""

    seq: int
    method: str
    tool: str
    request: dict[str, Any]
    result: dict[str, Any] | None
    error: dict[str, Any] | None

    @property
    def arguments(self) -> dict[str, Any]:
        """The recorded arguments of a `tools/call`."""
        arguments = self.request.get("arguments")
        return arguments if isinstance(arguments, dict) else {}


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class RecordedHost:
    """A recording folder as a session: `call` is the session side (`HostCaller`), `host_call` the reply bodies."""

    def __init__(self, directory: Path, *, sanitizer: Sanitizer | None = None) -> None:
        problems = verify_manifest(directory)
        assert not problems, f"the manifest of {directory} does not verify: {problems}"
        self.directory = directory
        self.manifest: dict[str, Any] = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        self.exchanges = [
            Exchange(
                seq=data["seq"],
                method=data["method"],
                tool=data["tool"],
                request=data["request"],
                result=data.get("reply"),
                error=data.get("error"),
            )
            for data in (json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("[0-9]*.json")))
        ]
        self._sanitizer = sanitizer
        self._used: set[int] = set()

    @property
    def tool_schemas(self) -> dict[str, Any]:
        """The input schema of every tool of the recorded `tools/list` replies."""
        return {
            tool["name"]: tool["inputSchema"]
            for exchange in self.exchanges
            if exchange.method == "tools/list" and exchange.result is not None
            for tool in exchange.result["tools"]
        }

    @property
    def calls(self) -> list[Exchange]:
        """The recorded `tools/call` exchanges, in recorded order."""
        return [e for e in self.exchanges if e.method == "tools/call"]

    def unused(self) -> list[Exchange]:
        """The recorded calls nobody asked for."""
        return [e for e in self.calls if e.seq not in self._used]

    def take(self, tool: str, arguments: Mapping[str, Any]) -> Exchange:
        """The first unused recorded call of `tool` with equal arguments; `UnmatchedRequestError` when there is none."""
        shown = dict(arguments) if self._sanitizer is None else self._sanitizer.value(dict(arguments))
        for exchange in self.calls:
            if (
                exchange.seq not in self._used
                and exchange.tool == tool
                and _canonical(exchange.arguments) == _canonical(shown)
            ):
                self._used.add(exchange.seq)
                return exchange
        raise UnmatchedRequestError(f"no recorded {tool} with arguments {_canonical(shown)}")

    async def call(
        self, server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
    ) -> types.CallToolResult:
        """Serve one tool call as the session would."""
        exchange = self.take(tool, arguments)
        if exchange.error is not None:
            raise MCPError(exchange.error["code"], exchange.error["message"])
        assert exchange.result is not None
        return types.CallToolResult.model_validate(exchange.result)

    async def host_call(self, tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
        """The adapter's `HostCall` shape: the reply body of a success; an error reply raises `AssertionError`."""
        from eng_harness.servers._session import reply_body

        reply = await self.call("csi", "main", tool, arguments, effect)
        body = reply_body(reply)
        assert body is not None, f"{tool} was recorded without a JSON body"
        assert not reply.is_error, f"{tool} was recorded as {body}"
        return body
