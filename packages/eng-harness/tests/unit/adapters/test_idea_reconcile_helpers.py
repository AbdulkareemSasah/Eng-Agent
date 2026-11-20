"""IDEA IdeaReconciler unit coverage (plan 0014 T8; spec 0014 AC18, section 4.8).

Covers decide / observe / _set_loads branches with fakes only (no live IDEA): applied, not_applied,
unknown, missing out_path, calculate never re-runs, HostRead/LostWrite shapes, empty loads,
mismatched loads, malformed read-back, and timeout ContractError → unknown via the ToolPort.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import HostInfo
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import SeededIdSource
from eng_contract.params import ParamModel
from eng_contract.store import ResultStore
from mcp import types

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._errors import HostHealth
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import AdapterToolPort, Binding, Decision, LostWrite
from eng_harness.adapters.idea import _tools as idea_tools
from eng_harness.adapters.idea import idea_allowlist
from eng_harness.adapters.idea._errors import IdeaErrorMapper
from eng_harness.adapters.idea._reconcile import IdeaReconciler
from eng_harness.adapters.idea._tools import CalculateArgs, NativeSetLoadsArgs, OpenProjectArgs
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect, ServersConfig

_SHA = "d" * 64
_HOST = HostInfo(program="IDEA", version="24.1.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=1)
_TARGET = HostTarget(product="IDEA", pid=4242)
_CHECK = ServerCheck(
    server="idea",
    build="0123456789ab+fedcba987654",
    min_build="",
    fingerprint=_SHA,
    expected_fingerprint=_SHA,
    ok=True,
    reason=None,
)
# Synthetic host force values (N / N.m) for read-back shape only — not engineering results.
_N_MATCH = 1000.0
_N_MISMATCH = 1500.0


def _binding() -> Binding:
    return Binding(target=_TARGET, units_system=None, host=_HOST, owned=True, pre_image_ref=None)


def _load_effect(*, name: str = "LE1", n: float = _N_MATCH) -> dict[str, Any]:
    return {
        "id": 1,
        "name": name,
        "checkEquilibrium": True,
        "forcesOnSegments": [
            {
                "beamSegmentId": 1,
                "position": 0.0,
                "n": n,
                "qy": 0.0,
                "qz": 0.0,
                "mx": 0.0,
                "my": 0.0,
                "mz": 0.0,
            }
        ],
        "forcesPercentageOnSegments": None,
    }


def _lost_set_loads(
    *,
    path: str = "/models/src.ideaCon",
    out_path: str,
    loads: list[dict[str, Any]] | None = None,
    connection_id: str = "CON1",
    model: ParamModel | None = None,
) -> LostWrite:
    allowlist = idea_allowlist(route="native")
    descriptor = allowlist.descriptor("idea_native_set_loads")
    if model is not None:
        args: ParamModel = model
    else:
        args = NativeSetLoadsArgs(
            path=path,
            loads=loads if loads is not None else [_load_effect()],
            connection_id=connection_id,
            out_path=out_path,
        )
    return LostWrite(descriptor=descriptor, model=args, binding=_binding(), known=True, pre_image=None)


def _lost_calculate() -> LostWrite:
    allowlist = idea_allowlist(route="rest")
    descriptor = allowlist.descriptor("idea_calculate")
    model = CalculateArgs(connection_ids=[1])
    return LostWrite(descriptor=descriptor, model=model, binding=_binding(), known=False, pre_image=None)


def _lost_unknown_tool() -> LostWrite:
    allowlist = idea_allowlist(route="rest")
    descriptor = allowlist.descriptor("idea_status").model_copy(update={"name": "idea_unknown_tool"})
    return LostWrite(
        descriptor=descriptor, model=idea_tools.StatusArgs(), binding=_binding(), known=False, pre_image=None
    )


def _lost_native_calculate() -> LostWrite:
    allowlist = idea_allowlist(route="native")
    descriptor = allowlist.descriptor("idea_native_calculate")
    model = idea_tools.NativeCalculateArgs(path="/models/src.ideaCon")
    return LostWrite(descriptor=descriptor, model=model, binding=_binding(), known=False, pre_image=None)


class RecordingRead:
    """Fake HostRead: records calls and returns a scripted body or raises."""

    def __init__(
        self,
        body: dict[str, Any] | None = None,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any], CallEffect]] = []
        self.body = body if body is not None else {"loads": [_load_effect()]}
        self.error = error

    async def __call__(self, tool: str, args: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
        self.calls.append((tool, dict(args), effect))
        if self.error is not None:
            raise self.error
        return self.body


def test_decide_calculate_unknown_never_calls_host() -> None:
    """AC18: idea_calculate always unknown; HostRead is never invoked (no re-run)."""
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead()

    async def body() -> None:
        decided = await reconciler.decide(_lost_calculate(), read)
        assert decided.outcome == "unknown"
        assert decided.evidence["tool"] == "idea_calculate"
        assert "no readable state" in str(decided.evidence["reason"])
        assert read.calls == []

    anyio.run(body)


def test_observe_calculate_returns_none_without_host() -> None:
    """AC18: observe has no read-back for idea_calculate."""
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead()

    async def body() -> None:
        assert await reconciler.observe(_lost_calculate(), read) is None
        assert read.calls == []

    anyio.run(body)


def test_decide_unknown_tool_no_rule() -> None:
    """AC18: a tool with no reconciliation rule answers unknown without calling the host."""
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead()

    async def body() -> None:
        decided = await reconciler.decide(_lost_unknown_tool(), read)
        assert decided.outcome == "unknown"
        assert decided.evidence == {"reason": "no reconciliation rule", "tool": "idea_unknown_tool"}
        assert read.calls == []

    anyio.run(body)


def test_decide_native_calculate_no_rule() -> None:
    """AC18: idea_native_calculate is not in the calculate set; no rule → unknown, no host call."""
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead()

    async def body() -> None:
        decided = await reconciler.decide(_lost_native_calculate(), read)
        assert decided.outcome == "unknown"
        assert decided.evidence["reason"] == "no reconciliation rule"
        assert decided.evidence["tool"] == "idea_native_calculate"
        assert read.calls == []

    anyio.run(body)


def test_observe_non_set_loads_returns_none() -> None:
    """AC18: observe returns None for tools other than idea_native_set_loads."""
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead()

    async def body() -> None:
        assert await reconciler.observe(_lost_unknown_tool(), read) is None
        assert await reconciler.observe(_lost_native_calculate(), read) is None
        assert read.calls == []

    anyio.run(body)


def test_observe_wrong_model_type_returns_none(tmp_path: Path) -> None:
    """AC18: observe requires NativeSetLoadsArgs; wrong model shape yields None without a host call."""
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead()
    out = tmp_path / "out.ideaCon"
    out.write_text("{}", encoding="utf-8")
    lost = _lost_set_loads(out_path=str(out), model=OpenProjectArgs(path="/models/src.ideaCon"))

    async def body() -> None:
        assert await reconciler.observe(lost, read) is None
        assert read.calls == []

    anyio.run(body)


def test_decide_wrong_model_type_unknown(tmp_path: Path) -> None:
    """AC18: _set_loads with non-NativeSetLoadsArgs → unknown (args are not NativeSetLoadsArgs)."""
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead()
    out = tmp_path / "out.ideaCon"
    out.write_text("{}", encoding="utf-8")
    lost = _lost_set_loads(out_path=str(out), model=OpenProjectArgs(path="/models/src.ideaCon"))

    async def body() -> None:
        decided = await reconciler.decide(lost, read)
        assert decided.outcome == "unknown"
        assert decided.evidence == {"reason": "args are not NativeSetLoadsArgs"}
        assert read.calls == []

    anyio.run(body)


def test_decide_missing_out_path_not_applied(tmp_path: Path) -> None:
    """AC18: absent out_path → not_applied; HostRead is not called."""
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead()
    missing = tmp_path / "never_written.ideaCon"
    assert not missing.exists()
    lost = _lost_set_loads(out_path=str(missing))

    async def body() -> None:
        decided = await reconciler.decide(lost, read)
        assert decided.outcome == "not_applied"
        assert decided.evidence == {"out_path": str(missing), "exists": False}
        assert read.calls == []

    anyio.run(body)


def test_observe_missing_out_path(tmp_path: Path) -> None:
    """AC18: missing out_path observe payload is observed None with the path string."""
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead()
    missing = tmp_path / "never_written.ideaCon"
    lost = _lost_set_loads(out_path=str(missing))

    async def body() -> None:
        observed = await reconciler.observe(lost, read)
        assert observed == {"observed": None, "out_path": str(missing)}
        assert read.calls == []

    anyio.run(body)


def test_decide_applied_matching_loads(tmp_path: Path) -> None:
    """AC18: out_path exists and read-back matches → applied; HostRead shape is get_loads + READ."""
    out = tmp_path / "out_ok.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    loads = [_load_effect(n=_N_MATCH)]
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead({"loads": loads})
    lost = _lost_set_loads(out_path=str(out), loads=loads, connection_id="CON1")

    async def body() -> None:
        decided = await reconciler.decide(lost, read)
        assert decided.outcome == "applied"
        assert decided.evidence == {"out_path": str(out), "exists": True, "read_back_ok": True}
        assert len(read.calls) == 1
        tool, args, effect = read.calls[0]
        assert tool == "idea_native_get_loads"
        assert args == {"path": str(out), "connection_id": "CON1"}
        assert effect is CallEffect.READ

    anyio.run(body)


def test_decide_applied_empty_loads(tmp_path: Path) -> None:
    """AC18: empty requested and empty observed loads lists compare as applied."""
    out = tmp_path / "out_empty.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead({"loads": []})
    lost = _lost_set_loads(out_path=str(out), loads=[])

    async def body() -> None:
        decided = await reconciler.decide(lost, read)
        assert decided.outcome == "applied"
        assert decided.evidence["read_back_ok"] is True

    anyio.run(body)


def test_decide_unknown_mismatched_loads(tmp_path: Path) -> None:
    """AC18: file exists but force fields differ → unknown with READBACK_MISMATCH."""
    out = tmp_path / "out_bad.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    requested = [_load_effect(n=_N_MATCH)]
    got = [_load_effect(n=_N_MISMATCH)]
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead({"loads": got})
    lost = _lost_set_loads(out_path=str(out), loads=requested)

    async def body() -> None:
        decided = await reconciler.decide(lost, read)
        assert decided.outcome == "unknown"
        assert decided.evidence["out_path"] == str(out)
        assert decided.evidence["exists"] is True
        assert decided.evidence["read_back_ok"] is False
        assert decided.evidence["issue_codes"] == ["READBACK_MISMATCH"]

    anyio.run(body)


def test_decide_unknown_missing_effect_on_readback(tmp_path: Path) -> None:
    """AC18: requested effect absent on read-back → unknown READBACK_MISMATCH."""
    out = tmp_path / "out_missing_effect.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    requested = [_load_effect(name="LE1", n=_N_MATCH)]
    got = [_load_effect(name="OTHER", n=_N_MATCH)]
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead({"loads": got})
    lost = _lost_set_loads(out_path=str(out), loads=requested)

    async def body() -> None:
        decided = await reconciler.decide(lost, read)
        assert decided.outcome == "unknown"
        codes = decided.evidence["issue_codes"]
        assert isinstance(codes, list)
        assert "READBACK_MISMATCH" in codes

    anyio.run(body)


@pytest.mark.parametrize(
    "loads_body",
    [
        None,
        "not-a-list",
        42,
        {"n": 1},
        ["not-a-dict"],
        [{"ok": True}, "bad"],
    ],
    ids=["none", "str", "int", "dict", "list_str", "mixed_list"],
)
def test_decide_unknown_malformed_loads_body(tmp_path: Path, loads_body: Any) -> None:
    """AC18: non-list-of-dicts loads → got_list None → READBACK_UNAVAILABLE → unknown."""
    out = tmp_path / "out_malformed.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    if loads_body is None:
        body: dict[str, Any] = {}
    else:
        body = {"loads": loads_body}
    read = RecordingRead(body)
    lost = _lost_set_loads(out_path=str(out), loads=[_load_effect()])

    async def run() -> None:
        decided = await reconciler.decide(lost, read)
        assert decided.outcome == "unknown"
        assert decided.evidence["read_back_ok"] is False
        assert decided.evidence["issue_codes"] == ["READBACK_UNAVAILABLE"]

    anyio.run(run)


def test_decide_unknown_when_tolerance_missing(tmp_path: Path) -> None:
    """AC18: tolerance_ratio None → READBACK_UNAVAILABLE → unknown even when shapes match."""
    out = tmp_path / "out_tol.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    loads = [_load_effect()]
    reconciler = IdeaReconciler(tolerance_ratio=None)
    read = RecordingRead({"loads": loads})
    lost = _lost_set_loads(out_path=str(out), loads=loads)

    async def body() -> None:
        decided = await reconciler.decide(lost, read)
        assert decided.outcome == "unknown"
        assert decided.evidence["issue_codes"] == ["READBACK_UNAVAILABLE"]

    anyio.run(body)


def test_decide_unknown_when_tolerance_non_positive(tmp_path: Path) -> None:
    """AC18: tolerance_ratio <= 0 is treated as unavailable by compare_loads_readback."""
    out = tmp_path / "out_tol0.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    loads = [_load_effect()]
    reconciler = IdeaReconciler(tolerance_ratio=0.0)
    read = RecordingRead({"loads": loads})
    lost = _lost_set_loads(out_path=str(out), loads=loads)

    async def body() -> None:
        decided = await reconciler.decide(lost, read)
        assert decided.outcome == "unknown"
        assert decided.evidence["issue_codes"] == ["READBACK_UNAVAILABLE"]

    anyio.run(body)


def test_observe_existing_out_path_calls_host(tmp_path: Path) -> None:
    """AC18: observe with existing out_path returns body loads and records HostRead shape."""
    out = tmp_path / "out_obs.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    loads = [_load_effect(n=_N_MATCH)]
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead({"loads": loads, "extra": "ignored"})
    lost = _lost_set_loads(out_path=str(out), loads=loads, connection_id="CON9")

    async def body() -> None:
        observed = await reconciler.observe(lost, read)
        assert observed == {"observed": loads, "out_path": str(out)}
        assert len(read.calls) == 1
        tool, args, effect = read.calls[0]
        assert tool == "idea_native_get_loads"
        assert args == {"path": str(out), "connection_id": "CON9"}
        assert effect is CallEffect.READ

    anyio.run(body)


def test_observe_existing_out_path_loads_key_absent(tmp_path: Path) -> None:
    """AC18: observe reports observed None when the get_loads body omits loads."""
    out = tmp_path / "out_no_loads.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead({"status": "ok"})
    lost = _lost_set_loads(out_path=str(out))

    async def body() -> None:
        observed = await reconciler.observe(lost, read)
        assert observed == {"observed": None, "out_path": str(out)}

    anyio.run(body)


def test_decide_propagates_non_timeout_contract_error(tmp_path: Path) -> None:
    """AC18: HostRead ContractError that is not a timeout propagates from decide."""
    out = tmp_path / "out_err.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    err = ContractError(ErrorCode.HOST_ERROR, "get_loads failed", retryable=False)
    read = RecordingRead(error=err)
    lost = _lost_set_loads(out_path=str(out))

    async def body() -> None:
        with pytest.raises(ContractError) as caught:
            await reconciler.decide(lost, read)
        assert caught.value.detail.code is ErrorCode.HOST_ERROR

    anyio.run(body)


def test_decide_propagates_timeout_contract_error(tmp_path: Path) -> None:
    """AC18: IdeaReconciler itself re-raises timeout; the ToolPort maps it to unknown (next test)."""
    out = tmp_path / "out_timeout.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    err = ContractError(ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, "timed out", retryable=False)
    read = RecordingRead(error=err)
    lost = _lost_set_loads(out_path=str(out))

    async def body() -> None:
        with pytest.raises(ContractError) as caught:
            await reconciler.decide(lost, read)
        assert caught.value.detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME

    anyio.run(body)


class _FakeCaller:
    """Scripted caller for ToolPort.reconcile timeout → unknown."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, dict[str, Any], CallEffect]] = []
        self.body: Any = {"code": "timeout", "message": "idea call timed out", "data": None}
        self.is_error = True

    async def call(
        self, server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
    ) -> types.CallToolResult:
        self.calls.append((server, role, tool, dict(arguments), effect))
        block = types.TextContent(type="text", text=json.dumps(self.body))
        return types.CallToolResult(content=[block], is_error=self.is_error)


class _FakeBinder:
    def __init__(self, binding: Binding) -> None:
        self.binding_of = binding

    async def binding(self, host_key: str, model: str | None, descriptor: Any) -> Binding:
        return self.binding_of

    def revision(self, model_id: str) -> int | None:
        return None


def _servers_config() -> ServersConfig:
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
                    "build": {"sasaah_commit": idea_allowlist().sasaah_commit, "exe_sha256": _SHA},
                    "host_key": "idea",
                    "roles": {"main": {"classes": ["session", "call", "long"], "call_timeout_s": 30}},
                }
            }
        }
    )


def _reader(_reply: Any, _binding: Binding) -> tuple[dict[str, Any], dict[str, Any]]:
    return {"value": _reply}, {}


def test_toolport_timeout_on_readback_becomes_unknown(
    tmp_path: Path, store: ResultStore, ids: SeededIdSource, clock: Any
) -> None:
    """AC18: ToolPort.reconcile maps a timeout ContractError from HostRead to outcome unknown."""
    out = tmp_path / "out_port.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    ledger = WriteLedger(tmp_path / "run")
    caller = _FakeCaller()
    binder = _FakeBinder(Binding(target=_TARGET, units_system=None, host=_HOST, pre_image_ref=None))
    health = HostHealth()
    health.mark_wedged("idea", "op-set", bump_epoch=True)
    full = idea_allowlist(route="native")
    tools = tuple(t for t in full.tools if t.name == "idea_native_set_loads")
    allowlist = full.model_copy(update={"tools": tools})
    arg_models: dict[str, type[ParamModel]] = {
        "NativeSetLoadsArgs": idea_tools.NativeSetLoadsArgs,
    }
    port = AdapterToolPort(
        allowlist=allowlist,
        config=_servers_config(),
        server="idea",
        caller=caller,
        binder=binder,
        store=store,
        ledger=ledger,
        clock=clock,
        ids=ids,
        check=_CHECK,
        arg_models=arg_models,
        readers={"idea_native_set_loads": _reader},
        health=health,
        errors=IdeaErrorMapper(ids),
        reconciler=IdeaReconciler(tolerance_ratio=1e-9),
    )

    async def body() -> None:
        result = await port.reconcile(
            "idea_native_set_loads",
            {
                "path": "/models/src.ideaCon",
                "connection_id": "CON1",
                "out_path": str(out),
                "loads": [_load_effect()],
            },
            "op-set",
        )
        assert result.outcome == "unknown"
        assert health.wedged("idea") is None
        assert any(call[2] == "idea_native_get_loads" for call in caller.calls)

    anyio.run(body)


def test_set_loads_direct_applied_and_not_applied(tmp_path: Path) -> None:
    """AC18: exercise _set_loads directly for applied and not_applied branches."""
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    missing = tmp_path / "gone.ideaCon"
    out = tmp_path / "present.ideaCon"
    out.write_text("{}\n", encoding="utf-8")
    loads = [_load_effect()]
    read = RecordingRead({"loads": loads})

    async def body() -> None:
        not_applied = await reconciler._set_loads(_lost_set_loads(out_path=str(missing), loads=loads), read)
        assert not_applied.outcome == "not_applied"
        assert not_applied.evidence["exists"] is False

        applied = await reconciler._set_loads(_lost_set_loads(out_path=str(out), loads=loads), read)
        assert applied.outcome == "applied"
        assert applied.evidence["read_back_ok"] is True
        assert isinstance(applied, Decision)

    anyio.run(body)


def test_directory_out_path_is_not_file(tmp_path: Path) -> None:
    """AC18: out_path that exists as a directory is not a file → not_applied / observe None loads."""
    out_dir = tmp_path / "out_dir.ideaCon"
    out_dir.mkdir()
    reconciler = IdeaReconciler(tolerance_ratio=1e-9)
    read = RecordingRead()
    lost = _lost_set_loads(out_path=str(out_dir))

    async def body() -> None:
        decided = await reconciler.decide(lost, read)
        assert decided.outcome == "not_applied"
        observed = await reconciler.observe(lost, read)
        assert observed == {"observed": None, "out_path": str(out_dir)}
        assert read.calls == []

    anyio.run(body)
