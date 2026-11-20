"""IDEA timeout mapping and the wedged host through the ToolPort (plan 0014 T4; spec 0014 AC18, section 4.8).

The host is a recording fake behind the ToolPort seam: a server `timeout` arrives as an error reply. Reconciliation of
`idea_native_set_loads` / `idea_calculate` is plan 0014 T8.
"""

import asyncio
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from eng_contract.envelope import FailureEnvelope, HostInfo
from eng_contract.errors import ErrorCode, ErrorDetail
from eng_contract.ids import SeededIdSource
from eng_contract.params import ParamModel
from eng_contract.store import ResultStore
from mcp import types

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._errors import HostHealth
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import AdapterToolPort, Binding
from eng_harness.adapters.idea import _tools as idea_tools
from eng_harness.adapters.idea import idea_allowlist
from eng_harness.adapters.idea._errors import IdeaErrorMapper
from eng_harness.errors import ToolFailed
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect, ServersConfig

SHA = "d" * 64
HOST = HostInfo(program="IDEA", version="24.1.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=1)
TARGET = HostTarget(product="IDEA", pid=4242)
CHECK = ServerCheck(
    server="idea",
    build="0123456789ab+fedcba987654",
    min_build="",
    fingerprint=SHA,
    expected_fingerprint=SHA,
    ok=True,
    reason=None,
)
TIMEOUT_REPLY = {"code": "timeout", "message": "idea call timed out after 30 s", "data": None}


class FakeCaller:
    """Records each host call; answers one scripted error reply or a ToolFailed."""

    def __init__(self, ledger: WriteLedger) -> None:
        self.calls: list[tuple[str, str, str, dict[str, Any], CallEffect]] = []
        self.body: Any = TIMEOUT_REPLY
        self.is_error = True
        self.failure: ToolFailed | None = None
        self._ledger = ledger

    async def call(
        self, server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
    ) -> types.CallToolResult:
        self.calls.append((server, role, tool, dict(arguments), effect))
        if self.failure is not None:
            raise self.failure
        block = types.TextContent(type="text", text=json.dumps(self.body))
        return types.CallToolResult(content=[block], is_error=self.is_error)


class FakeBinder:
    """Fixed binding for every IDEA call."""

    def __init__(self, binding: Binding) -> None:
        self.binding_of = binding

    async def binding(self, host_key: str, model: str | None, descriptor: Any) -> Binding:
        return self.binding_of

    def revision(self, model_id: str) -> int | None:
        return None


def _config() -> ServersConfig:
    return ServersConfig.model_validate(
        {
            "servers": {
                "idea": {
                    "adapter": "sasaah-idea-mcp",
                    "command": os.path.abspath(os.sep + "opt"),
                    "client_grace_s": 5,
                    "route": "native",
                    "audit_log": False,
                    "args": ["--disable-script"],
                    "build": {"sasaah_commit": idea_allowlist().sasaah_commit, "exe_sha256": SHA},
                    "host_key": "idea",
                    "roles": {"main": {"classes": ["session", "call", "long"], "call_timeout_s": 30}},
                }
            }
        }
    )


def _reader(reply: Any, binding: Binding) -> tuple[dict[str, Any], dict[str, Any]]:
    return {"value": reply}, {}


_TIMEOUT_TOOLS = frozenset(
    {"idea_list_connections", "idea_native_calculate", "idea_calculate", "idea_native_set_loads"}
)


class Rig:
    """ToolPort over the IDEA tools used for timeout mapping, with a scripted caller."""

    def __init__(self, run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: Any) -> None:
        self.ledger = WriteLedger(run_dir)
        self.caller = FakeCaller(self.ledger)
        self.binder = FakeBinder(Binding(target=TARGET, units_system=None, host=HOST, pre_image_ref=None))
        self.health = HostHealth()
        full = idea_allowlist()
        tools = tuple(t for t in full.tools if t.name in _TIMEOUT_TOOLS)
        allowlist = full.model_copy(update={"tools": tools})
        arg_models: dict[str, type[ParamModel]] = {
            "ListConnectionsArgs": idea_tools.ListConnectionsArgs,
            "CalculateArgs": idea_tools.CalculateArgs,
            "NativeCalculateArgs": idea_tools.NativeCalculateArgs,
            "NativeSetLoadsArgs": idea_tools.NativeSetLoadsArgs,
        }
        readers = dict.fromkeys(_TIMEOUT_TOOLS, _reader)
        self.port = AdapterToolPort(
            allowlist=allowlist,
            config=_config(),
            server="idea",
            caller=self.caller,
            binder=self.binder,
            store=store,
            ledger=self.ledger,
            clock=clock,
            ids=ids,
            check=CHECK,
            arg_models=arg_models,
            readers=readers,
            health=self.health,
            errors=IdeaErrorMapper(ids),
        )

    def call(self, tool: str, args: dict[str, Any], op_id: str = "op-1") -> Any:
        return asyncio.run(self.port.call(tool, args, op_id=op_id, model=None))


def _failure(envelope: Any) -> ErrorDetail:
    assert isinstance(envelope, FailureEnvelope)
    return envelope.error


def test_timeout_mapping(run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: Any) -> None:
    # AC18: read / native_calculate → TIMEOUT_NO_EFFECT; calculate / set_loads → TIMEOUT_UNKNOWN_OUTCOME with op_id
    rig = Rig(run_dir, store, ids, clock)
    assert rig.health.wedged("idea") is None

    read = _failure(rig.call("idea_list_connections", {}, op_id="op-r"))
    assert (read.code, read.retryable, read.op_id) == (ErrorCode.TIMEOUT_NO_EFFECT, True, None)
    assert rig.health.wedged("idea") == "op-r"
    assert rig.health.epoch_bumps("idea") == 1

    rig.health.reconciled("op-r")
    native = _failure(rig.call("idea_native_calculate", {"path": "/models/joint.ideaCon"}, op_id="op-n"))
    assert (native.code, native.retryable, native.op_id) == (ErrorCode.TIMEOUT_NO_EFFECT, True, None)
    assert rig.health.wedged("idea") == "op-n"
    assert rig.health.epoch_bumps("idea") == 2

    rig.health.reconciled("op-n")
    calc = _failure(rig.call("idea_calculate", {"connection_ids": [1]}, op_id="op-c"))
    assert (calc.code, calc.retryable, calc.op_id) == (ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, False, "op-c")
    assert rig.health.wedged("idea") == "op-c"
    assert rig.health.epoch_bumps("idea") == 3

    rig.health.reconciled("op-c")
    loads = _failure(
        rig.call(
            "idea_native_set_loads",
            {
                "path": "/models/joint.ideaCon",
                "connection_id": "CON1",
                "out_path": "/models/out.ideaCon",
                "loads": [{"member": "M1"}],
            },
            op_id="op-w",
        )
    )
    assert (loads.code, loads.retryable, loads.op_id) == (ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, False, "op-w")
    assert rig.health.wedged("idea") == "op-w"
    assert rig.health.epoch_bumps("idea") == 4


def test_backstop_on_calculate_gets_op_id_without_a_second_epoch_bump(
    run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: Any
) -> None:
    # client backstop: the session restarted the role and increased the epoch itself (0002 §4.5.6)
    rig = Rig(run_dir, store, ids, clock)
    lost = ErrorDetail(code=ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, message="idea/main lost its session", retryable=False)
    rig.caller.failure = ToolFailed(lost)
    failure = _failure(rig.call("idea_calculate", {"connection_ids": [1]}, op_id="op-b"))
    assert (failure.code, failure.op_id) == (ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, "op-b")
    assert rig.health.wedged("idea") == "op-b"
    assert rig.health.epoch_bumps("idea") == 0
