"""Server roles, MCP sessions, crash detection, restart and shutdown (plan 0002 T5; spec 0002 sections 4.3.2 to 4.3.5).

`ServerManager` starts each role (one server process) lazily, keeps one MCP `Client` per role and maps a lost session
to the contract codes of spec section 4.5.6 (`ToolFailed`). The build check of section 4.3.4 follows in task T6b.
"""

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import anyio
import anyio.abc
from eng_contract.errors import RETRY_RULES, ErrorCode, ErrorDetail, RetryRule
from mcp import Client, MCPError, types
from mcp.client.stdio import get_default_environment

from eng_harness.errors import ToolFailed
from eng_harness.servers._config import RoleConfig, ServerConfig, ServersConfig
from eng_harness.servers._launcher import (
    JobPolicy,
    LaunchedProcess,
    LaunchError,
    LaunchSpec,
    PosixLauncher,
    ProcessLauncher,
)
from eng_harness.servers._transport import ProcessTransport

logger = logging.getLogger(__name__)

_MAX_LIST_PAGES = 100  # pages of `tools/list` read before the listing counts as endless; a software setting
_ATTACH_TOOL = "csi_attach"  # S-12: attaches the session to a running instance by process id


class CallEffect(StrEnum):
    """What a call may do to the host; decides the code of a call that was lost in flight (spec section 4.5.6)."""

    READ = "read"
    WRITE = "write"  # write, analysis, design, save or unlock


@dataclass
class _Live:
    """A running role: its client and process, and the task that owns both (so that entry and exit share a task)."""

    client: Client
    launched: LaunchedProcess
    stop: anyio.Event = field(default_factory=anyio.Event)
    finished: anyio.Event = field(default_factory=anyio.Event)


@dataclass
class _Role:
    server: str
    name: str
    config: ServerConfig
    role: RoleConfig
    live: _Live | None = None
    starts: int = 0  # processes started so far; every start after the first is a restart
    lock: anyio.Lock = field(default_factory=anyio.Lock)

    @property
    def backstop_s(self) -> float:
        """Client-side limit of one call: the server's own timeout plus the grace (spec section 4.3.3), s."""
        return float(self.role.call_timeout_s + self.config.client_grace_s)


def _fail(code: ErrorCode, message: str, *, tool: str | None = None, host_code: str | None = None) -> ToolFailed:
    retryable = RETRY_RULES[code] in (RetryRule.always, RetryRule.after_wedge_clears)
    detail = ErrorDetail(code=code, message=message, retryable=retryable, host_method=tool, host_code=host_code)
    return ToolFailed(detail)


class ServerManager:
    """Owns the server processes and MCP sessions of a run; use as `async with`.

    Leaving the context closes each session, waits `shutdown_grace_s` for each process and then ends its job; no host
    instance is ended by it.
    """

    def __init__(self, config: ServersConfig, run_dir: Path, *, launcher: ProcessLauncher | None = None) -> None:
        """Prepare roles from `config`; servers run in the run folder `run_dir`, logging under `servers/`."""
        self._run_dir = run_dir
        self._launcher = launcher or PosixLauncher()
        self._roles = {
            (name, role): _Role(name, role, server, role_config)
            for name, server in config.servers.items()
            for role, role_config in server.roles.items()
        }
        self._epochs: defaultdict[str, int] = defaultdict(int)
        self._bound: dict[str, tuple[int, str]] = {}  # host key -> (pid, product) of the bound instance
        self._group: anyio.abc.TaskGroup  # opened by `__aenter__`, which needs the running event loop

    async def __aenter__(self) -> Self:
        self._group = anyio.create_task_group()
        await self._group.__aenter__()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        for role in self._roles.values():
            if role.live is not None:
                role.live.stop.set()
        await self._group.__aexit__(exc_type, exc, tb)

    def session_epoch(self, host_key: str) -> int:
        """Return the counter that increases whenever a session to the host is lost or re-established."""
        return self._epochs[host_key]

    def bind_instance(self, host_key: str, *, pid: int, product: str) -> None:
        """Record the instance a restarted or later-started role re-attaches to by process id."""
        self._bound[host_key] = (pid, product)

    def server_info(self, server: str, role: str) -> types.Implementation | None:
        """Return what the running role reported in the handshake, or None when it is not running."""
        live = self._roles[server, role].live
        return None if live is None else live.client.server_info

    async def list_tools(self, server: str, role: str) -> list[types.Tool]:
        """Read the complete tool list, every page, never from a cache."""

        async def read(client: Client, backstop_s: float) -> list[types.Tool]:
            tools: list[types.Tool] = []
            cursor: str | None = None
            with anyio.fail_after(backstop_s):
                for _ in range(_MAX_LIST_PAGES):
                    page = await client.list_tools(cursor=cursor)
                    tools += page.tools
                    cursor = page.next_cursor
                    if cursor is None:
                        return tools
            raise _fail(ErrorCode.HOST_ERROR, f"{server} lists more than {_MAX_LIST_PAGES} pages of tools")

        return await self._request(self._roles[server, role], CallEffect.READ, "tools/list", read)

    async def call(
        self, server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
    ) -> types.CallToolResult:
        """Call `tool` on a role and return the raw reply (an error reply of the host is returned, not raised).

        Raises:
            ToolFailed: `HOST_NOT_CONNECTED` (role down for good, or died during a read), `TIMEOUT_NO_EFFECT` (a read
                hit the backstop), `TIMEOUT_UNKNOWN_OUTCOME` (a write died or hit the backstop), `HOST_ERROR`.
        """

        async def send(client: Client, backstop_s: float) -> types.CallToolResult:
            return await client.call_tool(tool, dict(arguments), read_timeout_seconds=backstop_s)

        return await self._request(self._roles[server, role], effect, tool, send)

    async def _request[T](
        self, role: _Role, effect: CallEffect, tool: str, send: Callable[[Client, float], Awaitable[T]]
    ) -> T:
        live = await self._ensure(role)
        try:
            return await send(live.client, role.backstop_s)
        except (TimeoutError, MCPError) as error:
            code = error.code if isinstance(error, MCPError) else types.REQUEST_TIMEOUT
            if code not in (types.REQUEST_TIMEOUT, types.CONNECTION_CLOSED):
                raise _fail(ErrorCode.HOST_ERROR, f"{tool}: {error}", tool=tool, host_code=str(code)) from error
            await self._lose(role, live)  # the server may still hold the host, so the role is restarted
            unknown = effect is CallEffect.WRITE
            if code == types.REQUEST_TIMEOUT:
                lost = ErrorCode.TIMEOUT_UNKNOWN_OUTCOME if unknown else ErrorCode.TIMEOUT_NO_EFFECT
            else:
                lost = ErrorCode.TIMEOUT_UNKNOWN_OUTCOME if unknown else ErrorCode.HOST_NOT_CONNECTED
            raise _fail(lost, f"{role.server}/{role.name} lost its session during {tool}") from error

    async def _ensure(self, role: _Role) -> _Live:
        """Return the running role, restarting it when it is down and the run's restart limit allows."""
        async with role.lock:
            if role.live is not None and role.live.launched.wait(0) is not None:
                await self._lose(role, role.live)  # it exited between calls
            if role.live is not None:
                return role.live
            if role.starts > role.config.max_restarts_per_run:
                raise _fail(ErrorCode.HOST_NOT_CONNECTED, f"{role.server}/{role.name}: restart limit reached")
            role.starts += 1  # counted before the start, so a start that fails still uses up a restart
            live = await self._start(role)
            role.live = live
            try:
                await self._attach(role, live)
            except ToolFailed:
                await self._lose(role, live)
                raise
            if role.starts > 1:
                self._epochs[role.config.host_key] += 1
            return live

    def _spec(self, role: _Role) -> LaunchSpec:
        """The launch of spec section 4.3.2: the adapter's two options follow the configured arguments."""
        servers = self._run_dir / "servers"
        argv = [role.config.command, *role.config.args, "--call-timeout-sec", str(role.role.call_timeout_s)]
        if role.config.audit_log:
            argv += ["--audit-log", str(servers / f"{role.server}-{role.name}-audit.jsonl")]
        env = {**get_default_environment(), **role.config.env}
        stderr = servers / f"{role.server}-{role.name}.stderr.log"
        return LaunchSpec(argv=argv, env=env, cwd=self._run_dir, stderr_path=stderr, job=JobPolicy.SERVER)

    async def _start(self, role: _Role) -> _Live:
        started: _Live | Exception
        try:
            with anyio.fail_after(role.backstop_s):  # also bounds the handshake
                started = await self._group.start(self._serve, role)
        except TimeoutError as error:
            started = error
        if isinstance(started, Exception):
            raise _fail(
                ErrorCode.HOST_NOT_CONNECTED, f"{role.server}/{role.name} cannot start: {started!r}"
            ) from started
        return started

    async def _serve(
        self, role: _Role, *, task_status: anyio.abc.TaskStatus[_Live | Exception] = anyio.TASK_STATUS_IGNORED
    ) -> None:
        """Own one role's process and client until `stop` is set (entry and exit of the client share this task)."""
        self._run_dir.joinpath("servers").mkdir(parents=True, exist_ok=True)
        launched: LaunchedProcess | None = None
        live: _Live | None = None
        try:
            launched = self._launcher.start(self._spec(role))
            transport = ProcessTransport(launched, grace_s=role.config.shutdown_grace_s)
            async with Client(transport, mode=role.config.mcp_mode, cache=None, read_timeout_seconds=None) as client:
                live = _Live(client, launched)
                task_status.started(live)
                await live.stop.wait()
        except (
            LaunchError,
            MCPError,
            OSError,
            ValueError,
            anyio.BrokenResourceError,
            anyio.ClosedResourceError,
        ) as error:
            if live is not None:  # a failure while closing is logged; the role is gone either way
                logger.warning("%s/%s failed while closing: %s", role.server, role.name, error)
            else:
                task_status.started(error)  # reported to the caller of `_start`
        finally:
            if launched is not None:
                launched.terminate_job()
                launched.close()
            if live is not None:
                live.finished.set()

    async def _attach(self, role: _Role, live: _Live) -> None:
        """Attach a (re)started role to the bound instance by process id (spec section 4.3.5); no-op when none."""
        if (bound := self._bound.get(role.config.host_key)) is None:
            return
        pid, product = bound
        try:
            with anyio.fail_after(role.backstop_s):
                result = await live.client.call_tool(_ATTACH_TOOL, {"pid": pid, "product": product})
        except (TimeoutError, MCPError) as error:
            raise _fail(ErrorCode.HOST_NOT_CONNECTED, f"{role.server}/{role.name} cannot attach: {error}") from error
        if result.is_error:
            raise _fail(ErrorCode.HOST_NOT_CONNECTED, f"{role.server}/{role.name} cannot attach to pid {pid}")

    async def _lose(self, role: _Role, live: _Live) -> None:
        """End a dead or stale session: end its job at once, close it, and increase the epoch (idempotent)."""
        if role.live is not live:
            return
        role.live = None
        live.launched.terminate_job()
        live.stop.set()
        await live.finished.wait()
        self._epochs[role.config.host_key] += 1
