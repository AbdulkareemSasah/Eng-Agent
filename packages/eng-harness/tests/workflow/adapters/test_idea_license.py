"""IDEA licensing outcomes through the synthetic fake (plan 0014 T4; spec 0014 AC19, section 4.9).

Sasaah has no license logic; a refusal is `service_unavailable` or a host error text, and a hang ends at the client
backstop (`call_timeout_s + client_grace_s`). The mapper adds a "license seat" hint only when the host text names it.
"""

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from fakes.sasaah_idea.test_server import make_ideacon

from eng_harness.adapters._errors import ErrorReply, parse_error_reply
from eng_harness.adapters.idea import idea_allowlist
from eng_harness.adapters.idea._errors import IdeaErrorMapper
from eng_harness.errors import ToolFailed
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._launcher import PosixLauncher

# Backstop must leave room for the MCP handshake under load, yet stay far below the hang sleep (30 s).
CALL_TIMEOUT_S = 5
CLIENT_GRACE_S = 2
BACKSTOP_S = CALL_TIMEOUT_S + CLIENT_GRACE_S


class RecordingLauncher:
    """POSIX launcher that records started processes."""

    def __init__(self) -> None:
        self._inner = PosixLauncher()

    def start(self, spec: Any) -> Any:
        return self._inner.start(spec)


def _idea_config(tmp_path: Path, control: Path) -> ServersConfig:
    fake = Path(__file__).resolve().parents[2] / "fakes" / "sasaah_idea" / "server.py"
    if not control.exists():
        control.write_text(json.dumps({"faults": [], "seed": {}}), encoding="utf-8")
    wrapper = tmp_path / "sasaah-idea-mcp"
    wrapper.write_text(
        f'#!/bin/sh\nexport SASAAH_IDEA_FAKE_CONTROL="{control}"\nexec "{sys.executable}" "{fake}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    exe = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    allowlist = idea_allowlist()
    return ServersConfig.model_validate(
        {
            "servers": {
                "idea": {
                    "adapter": "sasaah-idea-mcp",
                    "command": str(wrapper),
                    "args": ["--disable-script"],
                    "route": "native",
                    "audit_log": False,
                    "client_grace_s": CLIENT_GRACE_S,
                    "shutdown_grace_s": 5,
                    "max_restarts_per_run": 1,
                    "build": {"sasaah_commit": allowlist.sasaah_commit, "exe_sha256": exe},
                    "host_key": "idea",
                    "roles": {
                        "main": {
                            "classes": ["session", "call", "long"],
                            "call_timeout_s": CALL_TIMEOUT_S,
                        }
                    },
                }
            }
        }
    )


def _fault(control: Path, fault: str, *, tool: str, **extra: Any) -> None:
    entry: dict[str, Any] = {"fault": fault, "tool": tool, **extra}
    control.write_text(json.dumps({"faults": [entry], "seed": {}}), encoding="utf-8")


def _mapper() -> IdeaErrorMapper:
    return IdeaErrorMapper(SeededIdSource(b"idea-license", FixedClock(1_767_225_600_000, 1)))


def _map_result(result: Any, *, effect: CallEffect, tool: str) -> Any:
    dumped = result.model_dump(by_alias=True, mode="json")
    failure = parse_error_reply(dumped)
    assert failure is not None
    return _mapper().map(failure, effect=effect, tool=tool, op_id="op-lic")


def test_refusal_maps(tmp_path: Path) -> None:
    # AC19: license_refused → HOST_NOT_CONNECTED (service_unavailable) with a license-seat hint
    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)
    launcher = RecordingLauncher()
    model = make_ideacon(tmp_path / "joint.ideaCon")

    async def body(manager: ServerManager) -> None:
        opened = await manager.call("idea", "main", "idea_open_project", {"path": str(model)}, CallEffect.WRITE)
        assert opened.is_error is False
        _fault(control, "license_refused", tool="idea_calculate")
        result = await manager.call("idea", "main", "idea_calculate", {"confirm": True}, CallEffect.WRITE)
        assert result.is_error is True
        detail = _map_result(result, effect=CallEffect.WRITE, tool="idea_calculate")
        assert detail.code is ErrorCode.HOST_NOT_CONNECTED
        assert detail.retryable is True
        assert "license seat" in detail.message.lower() or (
            detail.hint is not None and "license seat" in detail.hint.lower()
        )

        # host text with "license" on a HOST_ERROR path (§4.9 alternative form)
        reply = ErrorReply(
            code="idea_error",
            message="Hidden calculator failed: no license seat",
            data={},
        )
        host_error = _mapper().map(reply, effect=CallEffect.WRITE, tool="idea_native_calculate", op_id="op-h")
        assert host_error.code is ErrorCode.HOST_ERROR
        assert host_error.hint is not None
        assert "license seat" in host_error.hint.lower()

    async def scenario() -> None:
        async with ServerManager(config, tmp_path / "run", launcher=launcher) as manager:
            await body(manager)

    anyio.run(scenario)


def test_hang_bounded(tmp_path: Path) -> None:
    # AC19 / Q8: license_hang ends at the client backstop; never waits past call_timeout_s + client_grace_s
    control = tmp_path / "control.json"
    config = _idea_config(tmp_path, control)
    launcher = RecordingLauncher()
    model = make_ideacon(tmp_path / "joint.ideaCon")

    async def body(manager: ServerManager) -> None:
        opened = await manager.call("idea", "main", "idea_open_project", {"path": str(model)}, CallEffect.WRITE)
        assert opened.is_error is False
        # hang longer than the backstop so the client ends the call
        _fault(control, "license_hang", tool="idea_calculate", seconds=30.0)
        started = time.monotonic()
        with pytest.raises(ToolFailed) as raised:
            await manager.call("idea", "main", "idea_calculate", {"confirm": True}, CallEffect.WRITE)
        elapsed = time.monotonic() - started
        assert elapsed <= BACKSTOP_S + 5.0  # scheduler slack under machine load
        assert raised.value.detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME
        assert elapsed < 30.0  # never waited for the full hang

    async def scenario() -> None:
        async with ServerManager(config, tmp_path / "run", launcher=launcher) as manager:
            await body(manager)

    anyio.run(scenario)
