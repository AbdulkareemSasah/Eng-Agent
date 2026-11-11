"""CSI launch, open and save on the main role (plan 0002 T10; spec 0002 sections 4.4.2, 4.5.8, 4.5.9, 4.6.1)."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import IdSource, Timestamp

from eng_harness.adapters._errors import ErrorReply
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.servers import CallEffect
from eng_harness.servers._guard import ProcessGuard, StartedInstance
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity, ProcessInspector
from eng_harness.servers._session import ServerManager, reply_body

_ROLE = "main"  # spec 0002 sections 4.5.8 and 4.6.1: these calls run on the main role


class NotLaunchedError(Exception):
    """`not_launched_by_server` on `csi_open_model` (spec 0002 section 4.5.9)."""


@dataclass(frozen=True)
class OpenedInstance:
    instance_id: str
    pid: int
    started_at: str
    observed_at: Timestamp
    exe_name: str
    session: int
    visible: bool


class CsiSession:
    def __init__(
        self, sessions: ServerManager, guard: ProcessGuard, inspector: ProcessInspector, locks: HostLocks,
        ids: IdSource, *, server: str, product: str, program: str, exe_name: str,
    ) -> None:  # fmt: skip
        self._sessions, self._guard, self._inspector, self._locks, self._ids = sessions, guard, inspector, locks, ids
        self._server, self._product, self._program, self._exe = server, product, program, exe_name

    def owns(self, instance: OpenedInstance) -> bool:
        return self._sessions.role_session(self._server, _ROLE) == instance.session

    def alive(self, instance: OpenedInstance) -> bool:
        return self._inspector.alive(ProcessIdentity(instance.pid, instance.started_at, instance.exe_name))

    async def open_file(self, path: Path, instance: OpenedInstance | None, observed_at: Timestamp) -> OpenedInstance:
        if instance is not None and self.owns(instance) and self.alive(instance):
            try:
                await self._open(path, instance.pid)
            except NotLaunchedError:
                pass
            else:
                return instance
        return await self._launch(path, observed_at)

    async def save(self, path: Path, instance: OpenedInstance) -> None:
        await self._call("csi_save_model", self._target(instance.pid, path=str(path), confirm=True), CallEffect.WRITE)

    async def units(self, instance: OpenedInstance) -> str:
        units = (await self._call("csi_model_info", self._target(instance.pid), CallEffect.READ)).get("units")
        if not isinstance(units, str):
            self._bad("csi_model_info")
        return units

    async def model_path(self, instance: OpenedInstance) -> Path | None:
        try:
            reported = (await self._call("csi_model_info", self._target(instance.pid), CallEffect.READ)).get(
                "model_path"
            )
        except ContractError:
            return None
        return Path(reported) if isinstance(reported, str) else None

    async def close(self, instances: list[StartedInstance]) -> None:
        await self._guard.close_started(self._sessions, instances)

    def _target(self, pid: int, **extra: Any) -> dict[str, Any]:
        sent: dict[str, Any] = {"target": {"product": self._product, "pid": pid}}
        sent.update(extra)
        return sent

    async def _launch(self, path: Path, observed_at: Timestamp) -> OpenedInstance:
        before = self._guard.snapshot()
        launched: dict[str, Any] = {"product": self._product, "visible": False}
        pid = (await self._call("csi_launch", launched, CallEffect.WRITE)).get("pid")
        if not isinstance(pid, int):
            self._bad("csi_launch")
        found = self._guard.identify_launch(before, named_pid=pid)
        self._guard.record_launch(self._sessions, found, visible=False, server=self._server, role=_ROLE)
        self._locks.acquire(self._program, found)  # before any other call on the instance (spec 4.4.1)
        await self._open(path, found.pid)
        return OpenedInstance(
            self._ids.new_ulid(), found.pid, found.started_at, observed_at, found.exe_name,
            self._sessions.role_session(self._server, _ROLE), False,
        )  # fmt: skip

    async def _open(self, path: Path, pid: int) -> None:
        await self._call("csi_open_model", self._target(pid, path=str(path), confirm=True), CallEffect.WRITE)

    async def _call(self, tool: str, arguments: Mapping[str, Any], effect: CallEffect) -> dict[str, Any]:
        result = await self._sessions.call(self._server, _ROLE, tool, arguments, effect)
        body = reply_body(result) or {}
        if not result.is_error:
            return body
        if body.get("code") == "not_launched_by_server":
            raise NotLaunchedError(tool)
        self._fail(tool, effect, body)

    def _fail(self, tool: str, effect: CallEffect, body: dict[str, Any]) -> NoReturn:
        code, message, data = body.get("code"), body.get("message"), body.get("data")
        reply = ErrorReply(
            code=code if isinstance(code, str) else None,
            message=message if isinstance(message, str) else "",
            data=data if isinstance(data, dict) else {},
        )
        detail = CsiErrorMapper(self._ids).map(reply, effect=effect, tool=tool, op_id="")
        names = ("incident_id", "host_code", "host_method", "precondition")
        extra = {name: getattr(detail, name) for name in names if getattr(detail, name) is not None}
        raise ContractError(detail.code, detail.message, retryable=detail.retryable, **extra)

    def _bad(self, tool: str) -> NoReturn:
        raise ContractError(ErrorCode.HOST_ERROR, f"{tool} gave no usable reply", host_method=tool, retryable=False)
