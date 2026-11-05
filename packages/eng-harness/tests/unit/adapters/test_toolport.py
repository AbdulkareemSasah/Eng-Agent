"""ToolPort over the allowlist and the write ledger (plan 0002 T8b; spec 0002 sections 4.5.2, 4.5.3, 4.5.7; AC17, AC38).

The host is a recording fake behind the `HostCaller` seam, so nothing is started and no clock or network is read. The
expected values come from the spec text and from independent definitions: 250 mm is exactly 0.25 m, and the ledger
holds `{op_id, tool, args_sha256, target, pre_image_ref, sent_at}` for a write, appended and `fsync`ed before the send.
"""

import asyncio
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from eng_contract.canonical import payload_sha256
from eng_contract.envelope import FailureEnvelope, HostInfo, Provenance, RefInput, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode, ErrorDetail
from eng_contract.ids import SeededIdSource
from eng_contract.params import ParamModel, eng_param
from eng_contract.store import ResultStore
from mcp import types

from eng_harness.adapters import Allowlist
from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._ledger import LedgerEntry, WriteLedger
from eng_harness.adapters._toolport import AdapterToolPort, Binding
from eng_harness.errors import ToolFailed
from eng_harness.ports import ServerCheck, ToolInfo
from eng_harness.servers import CallEffect, ServersConfig

MODEL_ID = "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV"
SHA = "d" * 64
WHY = "Synthetic bounds for the test model, not a code value"
HOST = HostInfo(program="ETABS", version="22.1.0", model_id=MODEL_ID, model_revision=2)
TARGET = HostTarget(product="ETABS", pid=4242)
PRE_IMAGE = "res_01ARZ3NDEKTSV4RRFFQ69G5FAW#/value/wall"
CHECK = ServerCheck(
    server="csi", build="0123456789ab+fedcba987654", min_build="", fingerprint=SHA, expected_fingerprint=SHA, ok=True,
    reason=None,
)  # fmt: skip
RECORD = "docs/gaps/tool-gap.md"


class StoriesArgs(ParamModel):
    """A canonical argument model with no engineering quantity; `model` names the model key."""

    model: str


class WallArgs(ParamModel):
    """A canonical argument model with one engineering quantity, which must come as a reference."""

    model: str
    name: str
    thickness_mm: float = eng_param(
        unit="mm", ge=1, le=5000, bounds_source=WHY, ref_capable=True, engineering_quantity=True
    )


def _entry(name: str, kind: str, effect: str, args_model: str, **over: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "timeout_class": "call",
        "effect": effect,
        "action": "plain",
        "args_model": args_model,
        "units": "none",
        "confirm": "never",
        "products": ["ETABS"],
    }
    if effect == "write":
        fields["readback"] = "wall"
    return fields | over


def _allowlist() -> Allowlist:
    tools = [
        _entry("csi_list_stories", "read", "read", "StoriesArgs", result_kind="harness.run_output/1"),
        _entry("csi_list_points", "read", "read", "StoriesArgs", result_kind="harness.run_output/1"),
        _entry("csi_define_wall_section", "write", "write", "WallArgs", units="token"),
        _entry("csi_save_model", "session", "write", "StoriesArgs", action="save", confirm="approved"),
        _entry("csi_exit", "session", "write", "StoriesArgs", confirm="owned"),
        _entry("csi_future_read", "read", "read", "StoriesArgs", release="unreleased", release_record=RECORD),
    ]
    return Allowlist.model_validate(
        {
            "adapter": "test-adapter",
            "sasaah_commit": "a" * 40,
            "tool_fingerprint": SHA,
            "fingerprint_source": "s12-inventory",
            "tool": tools,
        }
    )


def _config(*, cli_unreleased: bool = False) -> ServersConfig:
    server = {
        "adapter": "test-adapter",
        "command": os.path.abspath(os.sep + "opt"),
        "client_grace_s": 5,
        "build": {"sasaah_commit": "a" * 40, "exe_sha256": SHA},
        "host_key": "csi",
        "roles": {
            "main": {"classes": ["session", "call"], "call_timeout_s": 30},
            "long": {"classes": ["long"], "call_timeout_s": 900},
        },
    }
    cli = {"shell": server["command"], "script": server["command"], "timeout_s": 60}
    if cli_unreleased:
        cli |= {"release": "unreleased", "release_record": "docs/gaps/cli-gap.md"}
    return ServersConfig.model_validate({"servers": {"csi": server}, "cli_tools": {"dxf-prep/prepare": cli}})


class FakeCaller:
    """Records each host call and what the ledger held when it was sent; answers one scripted reply or error."""

    def __init__(self, ledger: WriteLedger) -> None:
        self.calls: list[tuple[str, str, str, dict[str, Any], CallEffect]] = []
        self.ledger_at_send: list[str] = []
        self.body: Any = {"stories": ["S1", "S2"], "truncated": False}
        self.is_error = False
        self.failure: ToolFailed | None = None
        self._ledger = ledger

    async def call(
        self, server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
    ) -> types.CallToolResult:
        self.calls.append((server, role, tool, dict(arguments), effect))
        self.ledger_at_send.append(self._ledger.path.read_text() if self._ledger.path.exists() else "")
        if self.failure is not None:
            raise self.failure
        block = types.TextContent(type="text", text=json.dumps(self.body))
        return types.CallToolResult(content=[block], is_error=self.is_error)


class FakeBinder:
    """The bound instance of every model key; the stale revision is whatever `revisions` says."""

    def __init__(self, binding: Binding) -> None:
        self.binding_of = binding
        self.asked: list[tuple[str, str | None]] = []

    async def binding(self, host_key: str, model: str | None) -> Binding:
        self.asked.append((host_key, model))
        return self.binding_of

    def revision(self, model_id: str) -> int | None:
        return None


class Rig:
    """A ToolPort over the fakes, in a temporary run folder."""

    def __init__(self, run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: Any, **over: Any) -> None:
        self.ledger = WriteLedger(run_dir)
        self.caller = FakeCaller(self.ledger)
        self.binder = FakeBinder(Binding(target=TARGET, units_system="kN_m_C", host=HOST, pre_image_ref=PRE_IMAGE))
        self.store = store
        fields: dict[str, Any] = {
            "allowlist": _allowlist(),
            "config": _config(),
            "server": "csi",
            "caller": self.caller,
            "binder": self.binder,
            "store": store,
            "ledger": self.ledger,
            "clock": clock,
            "ids": ids,
            "check": CHECK,
            "arg_models": {"StoriesArgs": StoriesArgs, "WallArgs": WallArgs},
            "readers": {"csi_list_stories": _stories_reader},
        }
        self.port = AdapterToolPort(**(fields | over))

    def call(self, tool: str, args: dict[str, Any], op_id: str = "op-1", model: str | None = "main") -> Any:
        return asyncio.run(self.port.call(tool, args, op_id=op_id, model=model))

    def thickness_ref(self, value: float = 250.0) -> dict[str, str]:
        producer = Provenance(
            tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
        )
        rid = self.store.put("harness.run_input/1", {"value": {"t": value}}, producer).result_id
        return {"$ref": f"{rid}#/value/t"}

    def wall(self) -> dict[str, Any]:
        return {"model": "main", "name": "W1", "thickness_mm": self.thickness_ref()}


def _stories_reader(reply: Mapping[str, Any], binding: Binding) -> tuple[dict[str, Any], dict[str, Any]]:
    return {"value": {"stories": reply["stories"]}}, {"count": len(reply["stories"])}


@pytest.fixture
def rig(run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: Any) -> Rig:
    return Rig(run_dir, store, ids, clock)


def _ledger_lines(ledger: WriteLedger) -> list[dict[str, Any]]:
    return [json.loads(line) for line in ledger.path.read_text(encoding="utf-8").splitlines()]


def test_not_allowlisted(rig: Rig) -> None:
    # AC17: a tool outside the allowlist is INVALID_ARGUMENT for describe and call, and nothing is sent
    for name in ("csi_run_script", "csi_nothing"):
        with pytest.raises(ContractError) as described:
            asyncio.run(rig.port.describe(name))
        assert described.value.detail.code is ErrorCode.INVALID_ARGUMENT
        with pytest.raises(ContractError) as called:
            rig.call(name, {"model": "main"})
        assert called.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert rig.caller.calls == []
    assert rig.binder.asked == []
    assert not rig.ledger.path.exists()


def test_unreleased_tools(run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: Any, rig: Rig) -> None:
    # AC38: the allowlist's unreleased entries and the [cli_tools.*] ones, each with its record
    assert rig.port.unreleased_tools() == {"csi_future_read": RECORD}
    both = Rig(run_dir, store, ids, clock, config=_config(cli_unreleased=True))
    assert both.port.unreleased_tools() == {"csi_future_read": RECORD, "dxf-prep/prepare": "docs/gaps/cli-gap.md"}
    plain = _allowlist().model_copy(update={"tools": tuple(t for t in _allowlist().tools if t.release == "released")})
    assert Rig(run_dir, store, ids, clock, allowlist=plain).port.unreleased_tools() == {}


def test_describe(rig: Rig) -> None:
    assert asyncio.run(rig.port.describe("csi_define_wall_section")) == ToolInfo(
        name="csi_define_wall_section",
        effect="write",
        action="plain",
        host_key="csi",
        model_param="model",
        engineering_params=("thickness_mm",),
    )
    save = asyncio.run(rig.port.describe("csi_save_model"))
    assert (save.effect, save.action, save.engineering_params) == ("write", "save", ())


def test_read_call_makes_an_envelope_and_no_ledger_entry(rig: Rig) -> None:
    envelope = rig.call("csi_list_stories", {"model": "main"})

    assert isinstance(envelope, SuccessEnvelope)
    assert envelope.kind == "harness.run_output/1"
    assert envelope.summary == {"count": 2}
    assert rig.store.payload(envelope.result_id) == {"value": {"stories": ["S1", "S2"]}}
    p = envelope.provenance
    assert (p.tool, p.tool_version, p.host) == ("test-adapter/csi_list_stories", CHECK.build, HOST)
    # the explicit target is always sent; the model key stays in the harness; a read goes to the main role
    assert rig.caller.calls == [
        ("csi", "main", "csi_list_stories", {"target": {"product": "ETABS", "pid": 4242}}, CallEffect.READ)
    ]
    assert rig.binder.asked == [("csi", "main")]
    assert not rig.ledger.path.exists()  # only a write is ledgered


def test_write_is_ledgered_and_fsynced_before_the_send(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    synced: list[int] = []
    real = os.fsync
    monkeypatch.setattr("eng_harness.adapters._ledger.os.fsync", lambda fd: (synced.append(fd), real(fd))[1])
    args = rig.wall()

    envelope = rig.call("csi_define_wall_section", args, op_id="op-7")

    assert isinstance(envelope, SuccessEnvelope)
    # 250 mm is 0.25 m; quantities are converted to the token's units, the reference is recorded, never the value
    sent = {"name": "W1", "thickness_mm": 0.25, "units": "kN_m_C", "target": {"product": "ETABS", "pid": 4242}}
    assert rig.caller.calls == [("csi", "main", "csi_define_wall_section", sent, CallEffect.WRITE)]
    assert isinstance(envelope.provenance.inputs["thickness_mm"], RefInput)
    # no result kind: the reply is stored as a generic value
    assert (envelope.kind, rig.store.payload(envelope.result_id)) == (
        "harness.run_output/1",
        {"value": {"stories": ["S1", "S2"], "truncated": False}},
    )

    [row] = _ledger_lines(rig.ledger)
    assert (row["op_id"], row["tool"], row["target"]) == (
        "op-7",
        "csi_define_wall_section",
        {"product": "ETABS", "pid": 4242},
    )
    assert row["args_sha256"] == payload_sha256(args)  # the canonical arguments as the caller gave them
    assert row["pre_image_ref"] == PRE_IMAGE
    assert row["sent_at"] >= envelope.provenance.started_at
    assert sorted(row) == ["args_sha256", "op_id", "pre_image_ref", "sent_at", "target", "tool"]
    assert len(synced) >= 1  # flushed and fsynced
    # the entry was on disk when the host call was made
    assert [json.loads(t)["op_id"] for t in rig.caller.ledger_at_send[0].splitlines()] == ["op-7"]


def test_ledger_appends_one_line_per_write(rig: Rig) -> None:
    rig.call("csi_define_wall_section", rig.wall(), op_id="op-1")
    rig.call("csi_define_wall_section", rig.wall(), op_id="op-2")
    assert [r["op_id"] for r in _ledger_lines(rig.ledger)] == ["op-1", "op-2"]
    entry = LedgerEntry.model_validate(_ledger_lines(rig.ledger)[0])
    assert entry.target == TARGET


def test_ledger_failure_means_nothing_is_sent(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("eng_harness.adapters._ledger.os.fsync", broken)
    envelope = rig.call("csi_define_wall_section", rig.wall())

    assert isinstance(envelope, FailureEnvelope)
    assert envelope.error.code is ErrorCode.INTERNAL
    assert envelope.error.incident_id is not None
    assert rig.caller.calls == []


@pytest.mark.parametrize("literal", [250.0, {"$ref": "res_01ARZ3NDEKTSV4RRFFQ69G5FAX#/value/t"}])
def test_invalid_arguments_send_and_ledger_nothing(rig: Rig, literal: object) -> None:
    # a literal engineering quantity (11 section 6 item 2) and an unknown reference fail before any host contact
    envelope = rig.call("csi_define_wall_section", {"model": "main", "name": "W1", "thickness_mm": literal})
    assert isinstance(envelope, FailureEnvelope)
    assert envelope.error.code in (ErrorCode.INVALID_ARGUMENT, ErrorCode.REF_NOT_FOUND)
    assert rig.caller.calls == [] and not rig.ledger.path.exists()


def test_a_lost_write_keeps_its_ledger_entry(rig: Rig) -> None:
    detail = ErrorDetail(code=ErrorCode.TIMEOUT_UNKNOWN_OUTCOME, message="lost", retryable=False)
    rig.caller.failure = ToolFailed(detail)
    envelope = rig.call("csi_define_wall_section", rig.wall(), op_id="op-9")
    assert isinstance(envelope, FailureEnvelope)
    assert envelope.error.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME
    assert [r["op_id"] for r in _ledger_lines(rig.ledger)] == ["op-9"]  # reconciliation starts from it


def test_host_error_reply_is_a_failure_envelope(rig: Rig) -> None:
    rig.caller.body, rig.caller.is_error = {"code": "model_locked", "message": "locked", "data": None}, True
    envelope = rig.call("csi_list_stories", {"model": "main"})
    assert isinstance(envelope, FailureEnvelope)
    assert (envelope.error.code, envelope.error.host_code) == (ErrorCode.HOST_ERROR, "model_locked")


def test_confirm_follows_the_descriptor(rig: Rig) -> None:
    rig.call("csi_save_model", {"model": "main"})  # approved: the call reaches the port only after the approval
    rig.call("csi_exit", {"model": "main"})  # owned, and the instance is not launch-owned
    rig.binder.binding_of = rig.binder.binding_of.model_copy(update={"owned": True})
    rig.call("csi_exit", {"model": "main"})
    confirms = [c[3].get("confirm") for c in rig.caller.calls]
    assert confirms == [True, None, True]


def test_result_kind_needs_a_reader(rig: Rig) -> None:
    # csi_list_points names a result kind but the adapter registered no reader: an adapter defect, not a stored guess
    envelope = rig.call("csi_list_points", {"model": "main"})
    assert isinstance(envelope, FailureEnvelope)
    assert envelope.error.code is ErrorCode.INTERNAL
