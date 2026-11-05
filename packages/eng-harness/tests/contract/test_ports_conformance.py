"""Shared conformance test of the port fakes (spec 0001 AC57; plan 0001 T6).

Each fake is bound to its `Protocol` by a typed assignment (checked by mypy) and then driven through the behavior the
spec states for that port. The `DecisionPort` is not covered here: its protocol and fake arrive with plan task T14.
"""

import asyncio
from pathlib import Path

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from fakes.ports import (
    FakeApprovalPort,
    FakeBasisPort,
    FakeCalcPort,
    FakeHost,
    FakeInputPort,
    FakeRunControl,
    Raise,
    RecordingProgressSink,
    failure,
)
from pydantic import ValidationError

from eng_harness.calc import CalcStatus
from eng_harness.errors import CalcRefused, HarnessCode
from eng_harness.journal import Event, EventType
from eng_harness.journal._events import RunPaused
from eng_harness.ports import (
    ApprovalAnswer,
    ApprovalPort,
    ApprovalRequest,
    BasisPort,
    CalcInfo,
    CalcPort,
    HostInstance,
    HostModelState,
    HostPort,
    InputAnswer,
    InputPort,
    InputRequest,
    ProgressSink,
    Reconciliation,
    RunClass,
    RunControlPort,
    SavedModel,
    ToolInfo,
    ToolPort,
    UnitsState,
)

SHA = "a" * 64
OP = "op_" + "1" * 32


def _tools() -> list[ToolInfo]:
    return [
        ToolInfo(name="model/read", effect="read", action="plain", host_key="h"),
        ToolInfo(name="model/write", effect="write", action="plain", host_key="h", model_param="model_key"),
    ]


def _host() -> FakeHost:
    clock = FixedClock(1_767_225_600_000, 1)
    host = FakeHost(_tools(), SeededIdSource(b"ports", clock), clock, unreleased={"model/write": "docs/gap.md"})
    instance = HostInstance(instance_id="i1", pid=7, process_started_at="2026-01-01T00:00:00.000Z", program="h")
    host.add_model("m", instance)
    return host


def test_fakes_conform() -> None:
    """AC57: every fake is a port by type and passes the behavior checks of its port."""
    host = _host()
    tool_port: ToolPort = host
    host_port: HostPort = host
    _check_tool_port(tool_port, host)
    _check_host_port(host_port, host)
    _check_calc_port()
    _check_basis_port()
    _check_dialog_ports()
    _check_sink_and_control()


def _check_tool_port(port: ToolPort, host: FakeHost) -> None:
    assert asyncio.run(port.describe("model/read")).effect == "read"
    with pytest.raises(ContractError) as unknown:
        asyncio.run(port.describe("csi_run_script"))
    assert unknown.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert port.unreleased_tools() == {"model/write": "docs/gap.md"}
    assert port.supports_reconcile("model/write")
    assert not port.supports_reconcile("model/read")
    assert asyncio.run(port.read_back("model/read", {})) is None

    # a success is recorded with its op_id; a write raises the revision and changes the fingerprint
    before = asyncio.run(host.model_state("m", "i1"))
    result = asyncio.run(port.call("model/write", {"x": 1}, op_id=OP, model="m"))
    assert result.ok
    after = asyncio.run(host.model_state("m", "i1"))
    assert before.revision is not None
    assert after.revision == before.revision + 1
    assert after.fingerprint != before.fingerprint
    assert [(e.tool, e.op_id, e.model) for e in host.ledger] == [("model/write", OP, "m")]
    assert asyncio.run(port.reconcile("model/write", {"x": 1}, OP)) == Reconciliation(outcome="applied")
    assert asyncio.run(port.reconcile("model/write", {"x": 1}, "op_" + "2" * 32)).outcome == "not_applied"

    # scripted outcomes: failure envelopes of the contract codes, and a raise; each call stays in the ledger
    host.script(
        "model/read", failure(ErrorCode.TIMEOUT_UNKNOWN_OUTCOME), failure(ErrorCode.HOST_WEDGED), Raise(OSError("x"))
    )
    codes = []
    for _ in range(2):
        reply = asyncio.run(port.call("model/read", {}, op_id=OP, model=None))
        assert not reply.ok
        codes.append(reply.error.code)
    assert codes == [ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, ErrorCode.HOST_WEDGED]
    with pytest.raises(OSError, match="x"):
        asyncio.run(port.call("model/read", {}, op_id=OP, model=None))
    assert len(host.ledger) == 4
    assert asyncio.run(port.call("model/read", {}, op_id=OP, model=None)).ok  # script exhausted: success


def _check_host_port(port: HostPort, host: FakeHost) -> None:
    checks = asyncio.run(port.preflight({"srv": "1"}))
    assert [c.server for c in checks] == ["srv"]
    assert all(c.ok for c in checks)

    lease = asyncio.run(port.acquire("h"))
    with pytest.raises(ContractError) as held:
        asyncio.run(port.acquire("h"))
    assert held.value.detail.code is ErrorCode.HOST_LOCKED
    asyncio.run(port.release(lease))
    asyncio.run(port.release(asyncio.run(port.acquire("h"))))

    instance = asyncio.run(port.locate("m"))
    assert instance is not None
    assert instance.instance_id == "i1"
    assert asyncio.run(port.locate("unknown")) is None
    assert not asyncio.run(port.model_state("m", "other")).loaded
    units = asyncio.run(port.read_units("m", "i1"))
    assert units.loaded
    assert units.ok
    assert not asyncio.run(port.read_units("m", "other")).loaded
    assert asyncio.run(port.check_model("m")).ok
    assert port.model_files("m") == (Path("m.edb"),)

    saved = asyncio.run(port.save("m", "revision"))
    assert saved.revision == 1
    copy_key = asyncio.run(port.working_copy("m", Path("work")))
    assert copy_key == "m@copy"
    assert asyncio.run(port.model_state(copy_key, "i1")).loaded

    # a host crash: models reported not loaded, session epoch increased, units not loaded
    epoch = port.session_epoch("h")
    host.crash("h")
    assert port.session_epoch("h") == epoch + 1
    assert not asyncio.run(port.model_state("m", "i1")).loaded
    assert asyncio.run(port.locate("m")) is None
    assert not asyncio.run(port.read_units("m", "i1")).loaded

    restored = asyncio.run(port.restore("m", saved))
    state = asyncio.run(port.model_state("m", restored.instance_id))
    assert state.loaded
    assert state.revision == saved.revision
    assert state.fingerprint == saved.fingerprint
    started = asyncio.run(port.started_instances("h"))
    assert restored in started
    asyncio.run(port.close_started("h", [restored]))
    assert restored not in asyncio.run(port.started_instances("h"))


def _check_calc_port() -> None:
    info = CalcInfo(
        id="harness.demo", version=1, content_sha256=SHA, status=CalcStatus.DRAFT,
        engineering_params=(), basis_fields=(), ref_rules={},
    )  # fmt: skip
    port: CalcPort = FakeCalcPort(RunClass.TRIAL, [info])
    assert port.run_class is RunClass.TRIAL
    assert port.describe("harness.demo") == info
    with pytest.raises(ContractError):
        port.describe("harness.none")
    refused = CalcRefused(HarnessCode.CALC_NOT_APPROVED, "draft calc in a production run")
    fake = FakeCalcPort(RunClass.PRODUCTION, [info])
    fake.results["harness.demo"] = Raise(refused)
    with pytest.raises(CalcRefused) as caught:
        fake.run("harness.demo", {})
    assert caught.value.code is HarnessCode.CALC_NOT_APPROVED
    assert fake.runs == [("harness.demo", {})]


def _check_basis_port() -> None:
    port: BasisPort = FakeBasisPort({})
    with pytest.raises(ContractError) as missing:
        port.load("res_" + "0" * 26)
    assert missing.value.detail.code is ErrorCode.REF_NOT_FOUND


def _check_dialog_ports() -> None:
    approvals = FakeApprovalPort()
    approval_port: ApprovalPort = approvals
    request = ApprovalRequest(
        request_id="apr_x", run_id="r", kind="CHANGE_SET", title="t",
        preview_ref="res_" + "0" * 26, shown_sha256=SHA, binding=(), items=("a", "b"),
    )  # fmt: skip
    asyncio.run(approval_port.present(request))
    assert approvals.presented == [request]
    assert asyncio.run(approval_port.answer("apr_x", wait=False)) is None  # no answer: the engine pauses
    answer = ApprovalAnswer(request_id="apr_x", shown_sha256=SHA, decision="approve", by="engineer:a")
    approvals.script("apr_x", answer)
    assert asyncio.run(approval_port.answer("apr_x", wait=True)) == answer
    assert asyncio.run(approval_port.answer("apr_x", wait=True)) is None  # used once

    inputs = FakeInputPort()
    input_port: InputPort = inputs
    ask = InputRequest(
        request_id="inp_x", kind="block", title="t", fields_schema={"x-eng-input": "data", "type": "object"}
    )
    asyncio.run(input_port.present(ask))
    assert inputs.presented == [ask]
    reply = InputAnswer(request_id="inp_x", shown_sha256=ask.fields_schema_sha256, values={"a": 1}, by="engineer:a")
    inputs.script("inp_x", reply)
    assert asyncio.run(input_port.answer("inp_x", wait=False)) == reply
    assert inputs.waits == [False]


def _check_sink_and_control() -> None:
    sink = RecordingProgressSink()
    progress: ProgressSink = sink
    event = Event(
        1,
        EventType.RUN_PAUSED,
        None,
        None,
        "2026-01-01T00:00:00.000Z",
        RunPaused(reason="stop_requested", request_ids=[]),
    )
    progress.emit(event)
    assert sink.events == [event]
    control = FakeRunControl()
    port: RunControlPort = control
    assert not port.stop_requested("r1")
    control.stopped.add("r1")
    assert port.stop_requested("r1")
    assert not port.stop_requested("r2")


def test_data_types_enforce_spec_rules() -> None:
    """Spec 4.8 and 4.9: not-loaded states carry no values; answers hold exactly one of values and choices."""
    with pytest.raises(ValidationError):
        HostModelState(loaded=False, revision=1)
    with pytest.raises(ValidationError):
        HostModelState(loaded=True)
    with pytest.raises(ValidationError):
        UnitsState(loaded=False, ok=False, present=None, expected="u")
    with pytest.raises(ValidationError):
        InputAnswer(request_id="i", shown_sha256=SHA, by="engineer:a")
    with pytest.raises(ValidationError):
        InputAnswer(request_id="i", shown_sha256=SHA, by="engineer:a", values={}, choices={})
    with pytest.raises(ValidationError):  # a rejected item needs a reason
        ApprovalAnswer(request_id="a", shown_sha256=SHA, decision="reject", rejected_items=("x",), by="engineer:a")
    with pytest.raises(ValidationError):  # a reason is 1 to 500 characters after trimming
        ApprovalAnswer(
            request_id="a", shown_sha256=SHA, decision="reject", rejected_items=("x",), item_reasons={"x": "  "},
            by="engineer:a",
        )  # fmt: skip
    assert (
        ApprovalAnswer(request_id="a", shown_sha256=SHA, decision="approve", by="engineer:a").acknowledged_unreleased
        is False
    )
    assert SavedModel.model_fields.keys() >= {"model_id", "revision", "fingerprint", "file_sha256", "file_name"}
    assert [c.value for c in RunClass] == ["trial", "production"]
