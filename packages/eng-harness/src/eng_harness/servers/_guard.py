"""Process guard: which host instances a run started, who may close them, and helper processes (plan 0002 T7).

Spec 0002 AC15 and section 4.4.2. `identify_launch` finds the instance a `csi_launch` created by a snapshot diff;
`record_launch` keeps the launching role and its session counter (launch ownership); `close_started` closes only
instances the run started whose pid and start time still match: gracefully through `csi_exit` while the launching
role owns the launch and `csi_status` names the instance as the session's current target, else by ending a hidden
instance's process, else leaving a visible one open and listing it in `<run_dir>/hosts/left_open.json`. An instance
the run only attached to is never passed here, hence never closed. Start times are opaque strings, so "started after
the call began" is checked as "absent from the snapshot taken just before the call".
"""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from eng_contract.errors import ContractError, ErrorCode
from mcp import types

from eng_harness.errors import ToolFailed
from eng_harness.servers._procinfo import ProcessIdentity, ProcessInspector
from eng_harness.servers._session import CallEffect, reply_body

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StartedInstance:
    """A host instance this run launched, as journaled in `host_started` (engine spec section 4.6 item 10)."""

    pid: int
    started_at: str
    program: str
    visible: bool

    @property
    def identity(self) -> ProcessIdentity:
        """The process identity the inspector compares."""
        return ProcessIdentity(self.pid, self.started_at, self.program)


class Sessions(Protocol):
    """What the guard needs of the `ServerManager`: calls and the role session counter."""

    def role_session(self, server: str, role: str) -> int:
        """The role's session counter."""

    async def call(
        self, server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
    ) -> types.CallToolResult:
        """Call `tool` on the role and return the raw reply."""


@dataclass(frozen=True)
class _Launch:
    server: str
    role: str
    session: int  # the role's session counter at `csi_launch`


class ProcessGuard:
    """Implements the process guard of spec section 4.4.2; also a `HelperTracker` of the `ServerManager`."""

    def __init__(self, inspector: ProcessInspector, run_dir: Path, *, host_exes: Sequence[str]) -> None:
        """`host_exes` are the image names of the host program; any other child of a job member is a helper."""
        self._inspector, self._run_dir, self._exes = inspector, run_dir, list(host_exes)
        self._launches: dict[tuple[int, str], _Launch] = {}
        self._helpers: dict[str, dict[tuple[int, str], ProcessIdentity]] = {}
        self._left_open: dict[tuple[int, str], StartedInstance] = {}

    def snapshot(self) -> list[ProcessIdentity]:
        """Host program processes now running; take it just before `csi_launch`."""
        return self._inspector.snapshot(self._exes)

    def identify_launch(self, before: Sequence[ProcessIdentity], *, named_pid: int) -> ProcessIdentity:
        """The one new host process, which must be the pid the launch reply names.

        Raises:
            ContractError: `CONFLICT` "launched instance not identified" for zero or several new processes, or one
                that is not `named_pid`; the instance is not adopted and the run escalates.
        """
        new = [p for p in self.snapshot() if p not in before]
        if len(new) != 1 or new[0].pid != named_pid:
            raise ContractError(
                ErrorCode.CONFLICT, f"launched instance not identified: {len(new)} new, pid {named_pid}"
            )
        return new[0]

    def record_launch(
        self, sessions: Sessions, identity: ProcessIdentity, *, visible: bool, server: str = "csi", role: str = "main"
    ) -> StartedInstance:
        """Remember who launched `identity` and the role's session counter now; return what the engine journals."""
        self._launches[identity.pid, identity.started_at] = _Launch(server, role, sessions.role_session(server, role))
        return StartedInstance(identity.pid, identity.started_at, identity.exe_name, visible)

    async def close_started(self, sessions: Sessions, instances: Sequence[StartedInstance]) -> list[StartedInstance]:
        """Close the given instances (run end only); return those left open. Idempotent."""
        for instance in instances:
            key = (instance.pid, instance.started_at)
            if not self._inspector.alive(instance.identity):
                self._left_open.pop(key, None)
                continue  # gone, or the pid belongs to another process now
            if await self._exit(sessions, instance, self._launches.get(key)):
                continue
            if not instance.visible:
                self._inspector.terminate(instance.identity)
            else:
                logger.warning("visible %s pid %d left open", instance.program, instance.pid)
                self._left_open[key] = instance
        if self._left_open:
            path = self._run_dir / "hosts" / "left_open.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            listed = [
                {"pid": i.pid, "started_at": i.started_at, "program": i.program} for i in self._left_open.values()
            ]
            path.write_text(json.dumps(listed), encoding="utf-8")
        return [i for i in instances if (i.pid, i.started_at) in self._left_open]

    async def _exit(self, sessions: Sessions, instance: StartedInstance, launch: _Launch | None) -> bool:
        """`csi_exit` when the launching role still owns the launch and the instance is the current target."""
        if launch is None or sessions.role_session(launch.server, launch.role) != launch.session:
            return False
        try:
            status = reply_body(await sessions.call(launch.server, launch.role, "csi_status", {}, CallEffect.READ))
            target = (status or {}).get("current_target")
            if not isinstance(target, dict) or target.get("pid") != instance.pid:
                return False
            exited = await sessions.call(launch.server, launch.role, "csi_exit", {"confirm": True}, CallEffect.WRITE)
        except ToolFailed as error:
            logger.warning("csi_exit for pid %d failed: %s", instance.pid, error)
            return False
        return not exited.is_error

    def observe_helpers(self, key: str, members: Sequence[ProcessIdentity]) -> None:
        """Record the children of job `members` that are neither members nor host programs (spec 4.3.1)."""
        known = {(m.pid, m.started_at) for m in members}
        for member in members:
            for child in self._inspector.children(member.pid):
                if child.exe_name not in self._exes and (child.pid, child.started_at) not in known:
                    self._helpers.setdefault(key, {})[child.pid, child.started_at] = child

    def terminate_helpers(self, key: str) -> None:
        """End the helpers recorded for role `key` that still match their identity; a failure is logged."""
        for helper in self._helpers.pop(key, {}).values():
            try:
                if self._inspector.terminate(helper):
                    logger.info("helper %s pid %d ended at server stop", helper.exe_name, helper.pid)
            except OSError as error:
                logger.warning("helper pid %d could not be ended: %s", helper.pid, error)
