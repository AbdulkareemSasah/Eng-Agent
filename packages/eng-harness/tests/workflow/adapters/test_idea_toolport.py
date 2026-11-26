"""Assembled IDEA ports against the synthetic MCP host (plan 0014 T9a)."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Envelope, FailureEnvelope, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.refs import RefRule, resolve_ref
from eng_contract.store import LocationClass, ResultStore, Workspace
from fakes.sasaah_idea.test_server import make_ideacon
from fixtures.report_run import HEADER
from mcp.types import CallToolResult
from pydantic import JsonValue

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.adapters import build_ports
from eng_harness.adapters.idea import _loads
from eng_harness.errors import NotImplementedGap
from eng_harness.journal import EventType, JournalWriter
from eng_harness.kinds.idea import IDEA_KINDS
from eng_harness.servers import CallEffect
from workflow.adapters.test_idea_calculate import _DESIGN_CODE, _fault, _idea_config
from workflow.adapters.test_idea_loads import _SYNTHETIC_MAP, _plan

_SET = "idea_native_set_loads"
_GET = "idea_native_get_loads"
_CALC = "idea_calculate"
_RUN_OUTPUT = RefRule(kinds=frozenset({"harness.run_output/1"}))


class _Rig:
    def __init__(self, root: Path, route: str) -> None:
        root.mkdir()
        self.control = root / "control.json"
        self.run = root / "run"
        self.run.mkdir()
        self.clock = FixedClock(1_700_000_000_000, 1)
        self.ids = SeededIdSource(b"idea-toolport", self.clock)
        workspace = Workspace(root=root / "ws", classification=LocationClass.LOCAL)
        self.store = ResultStore(workspace, HARNESS_KINDS.extend(IDEA_KINDS), self.ids, self.clock)
        config = _idea_config(root, self.control, route=route)
        self.service_url = config.servers["idea"].service_url
        self.ports = build_ports(
            config,
            workspace,
            self.store,
            self.run,
            self.clock,
            self.ids,
            files={"joint": make_ideacon(root / "joint.ideaCon")},
            lock_dir=root / "locks",
        )

    def freeze_basis(self, *, tolerance: bool = True) -> None:
        fields: dict[str, JsonValue] = {
            "connection.design_code": self._field(_DESIGN_CODE, None),
        }
        if tolerance:
            # Same synthetic engineer input as the CSI wiring rig, never a product default.
            fields["checks.readback_relative_tolerance_ratio"] = self._field(0.25, "1")
        provenance = Provenance(
            tool="test/idea", tool_version="1", inputs={}, started_at=self.clock.now(), duration_ms=0
        )
        basis = self.store.put("basis.design_basis/1", {"template": None, "fields": fields}, provenance)
        inputs = self.store.put("harness.run_input/1", {"value": {}}, provenance)
        writer = JournalWriter(self.run, self.store, self.clock, self.ids)
        try:
            writer.append(
                EventType.RUN_STARTED,
                {**HEADER, "run_id": self.run.name, "input_ref": inputs.result_id, "basis_ref": basis.result_id},
            )
        finally:
            writer.close()

    def _field(self, value: str | float, unit: str | None) -> dict[str, JsonValue]:
        return {
            "value": value,
            "unit": unit,
            "source": f"engineer:test@{self.clock.now()}",
            "confirmed": True,
            "citation": None,
        }

    async def working_copy(self) -> tuple[str, Path]:
        model = await self.ports.host_port.working_copy("joint", self.run / "copies")
        return model, self.ports.host_port.model_files(model)[0]

    def load_args(self, model: str, path: Path) -> dict[str, JsonValue]:
        return {"model": model, **_plan(self.store, path).model_dump(mode="json", by_alias=True)}

    def payload(self, envelope: Envelope | None, kind: str) -> dict[str, Any]:
        assert isinstance(envelope, SuccessEnvelope), envelope
        assert envelope.kind == kind
        return self.store.payload(envelope.result_id)

    def ref_value(self, ref: str) -> Any:
        return resolve_ref(ref, _RUN_OUTPUT, self.store, lambda _: None).value

    @property
    def ledger(self) -> Path:
        return self.run / "adapter" / "ops.jsonl"

    def record_attempt(self, entry: dict[str, Any], op_id: str, **overrides: Any) -> None:
        with self.ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({**entry, **overrides, "op_id": op_id}) + "\n")

    def record_load_request(
        self, entry: dict[str, Any], op_id: str, sent: dict[str, Any], **changes: JsonValue
    ) -> None:
        observed_ref = entry["pre_image_ref"]
        original = self.store.get(observed_ref.removesuffix("#/value/observed"))
        record = self.store.put(
            "harness.run_output/1",
            {"value": {"observed": self.ref_value(observed_ref), "sent": {**sent, **changes}}},
            original.producer,
        )
        self.record_attempt(entry, op_id, pre_image_ref=f"{record.result_id}#/value/observed")

    def observe_write(
        self, monkeypatch: pytest.MonkeyPatch, tool: str, op_id: str, args: dict[str, JsonValue]
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        seen: list[tuple[dict[str, Any], dict[str, Any]]] = []
        send = self.ports.servers.call

        async def call(
            server: str,
            role: str,
            name: str,
            arguments: Mapping[str, Any],
            effect: CallEffect,
        ) -> CallToolResult:
            if name == tool:
                entries = [json.loads(line) for line in self.ledger.read_text(encoding="utf-8").splitlines()]
                (entry,) = [item for item in entries if item["op_id"] == op_id]
                assert entry["tool"] == tool
                assert entry["args_sha256"] == payload_sha256(args)
                assert entry["target"]
                if tool == _SET:
                    ref = entry["pre_image_ref"]
                    assert ref.endswith("#/value/observed")
                    assert self.ref_value(ref)["effects"][0]["segments"][0]["N_kN"] == 10.0
                    sent = self.ref_value(ref.removesuffix("/observed") + "/sent")
                    assert sent == {
                        **arguments,
                        **{key: Path(arguments[key]).relative_to(self.run).as_posix() for key in ("path", "out_path")},
                    }
                seen.append((entry, dict(arguments)))
            return await send(server, role, name, arguments, effect)

        monkeypatch.setattr(self.ports.servers, "call", call)
        return seen


@pytest.fixture
def confirmed_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_loads, "load_shipped_map", lambda: _loads.load_map_file(_SYNTHETIC_MAP))


def test_build_ports_dispatches_idea_by_route(tmp_path: Path) -> None:
    """AC2, §4.4 and §4.10: describe only the tools served on the configured route."""

    async def body() -> None:
        for route, served, excluded in (("native", _SET, _CALC), ("rest", _CALC, _SET)):
            rig = _Rig(tmp_path / route, route)
            port = rig.ports.tool_port
            assert (await port.describe("idea_status")).effect == "read"
            info = await port.describe(served)
            assert (info.name, info.effect, info.host_key) == (served, "write", "idea")
            if route == "native":
                assert info.model_param == "model"
            with pytest.raises(ContractError) as raised:
                await port.describe(excluded)
            assert raised.value.detail.code == ErrorCode.INVALID_ARGUMENT
            assert raised.value.detail.field == "tool"

    anyio.run(body)


def test_native_load_preview_call_and_read_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC7, AC8, AC10, §4.7 and §4.10: preview references, validated plan, new file and canonical loads."""

    async def body() -> None:
        shipped = _Rig(tmp_path / "shipped", "native")
        async with shipped.ports:
            model, source = await shipped.working_copy()
            calls_before = shipped.control.read_bytes()
            with pytest.raises(NotImplementedGap) as gap:
                await shipped.ports.tool_port.preview(_SET, shipped.load_args(model, source))
            assert "IG-2" in gap.value.evidence
            assert shipped.control.read_bytes() == calls_before

        monkeypatch.setattr(_loads, "load_shipped_map", lambda: _loads.load_map_file(_SYNTHETIC_MAP))
        rig = _Rig(tmp_path / "native", "native")
        rig.freeze_basis(tolerance=False)
        port = rig.ports.tool_port
        async with rig.ports:
            model, source = await rig.working_copy()
            original = source.read_bytes()
            args = rig.load_args(model, source)
            with pytest.raises(ContractError) as invalid:
                await port.preview(
                    _SET,
                    {
                        **args,
                        "effects": [
                            {
                                "name": "LE1",
                                "entries": [
                                    {"beam_segment_id": 1, "position_host": 0.0, "row": 25.0},
                                ],
                            }
                        ],
                    },
                )
            assert invalid.value.detail.code == ErrorCode.INVALID_ARGUMENT
            preview = await port.preview(_SET, args)
            (item,) = preview.items
            (target,) = preview.models
            assert (target if isinstance(target, str) else target.model_key) == model
            assert item.id == _SET
            assert _SET in item.label
            assert preview.diff_ref is None
            assert all(ref.ref.endswith("#/value") for ref in item.refs)
            plan, load_map, proposed = (rig.ref_value(ref.ref) for ref in item.refs)
            assert plan["path"] == source.relative_to(rig.run).as_posix()
            assert plan["effects"] == args["effects"]
            assert load_map == {
                "status": "confirmed",
                "sign_convention": "host_local/1",
                "components": {
                    name: {"csi_field": field, "sign_i": 1, "sign_j": 1}
                    for name, field in zip(
                        ("n", "qy", "qz", "mx", "my", "mz"),
                        ("P_kN", "V2_kN", "V3_kN", "T_kNm", "M2_kNm", "M3_kNm"),
                        strict=True,
                    )
                },
            }
            assert proposed["effects"][0]["segments"][0]["N_kN"] == 25.0  # synthetic member-end fixture
            assert rig.ports.host_port.model_files(model) == (source,)
            assert all(call["tool"] != _SET for call in json.loads(rig.control.read_text()).get("calls", []))

            result = await port.call(_SET, args, op_id="set-loads", model=model)
            rig.payload(result, "harness.idea_loads/1")
            (destination,) = rig.ports.host_port.model_files(model)
            assert destination != source
            assert destination.is_relative_to(rig.run)
            assert source.read_bytes() == original
            observed = rig.payload(await port.read_back(_SET, args), "harness.idea_loads/1")
            assert observed["connection"] == proposed["connection"] == "CON1"
            assert observed["effects"] == proposed["effects"]
            issues = rig.payload(await rig.ports.host_port.check_model(model), "issues.model_check/1")["issues"]
            assert "READBACK_UNAVAILABLE" in {issue["code"] for issue in issues}

    anyio.run(body)


def test_calculation_and_check_results_through_port(tmp_path: Path) -> None:
    """AC11, AC12, AC14, AC15 and §4.10: all three tools use the frozen code and store host verdicts."""

    async def body() -> None:
        for route in ("native", "rest"):
            rig = _Rig(tmp_path / route, route)
            rig.freeze_basis()
            port = rig.ports.tool_port
            async with rig.ports:
                model, path = await rig.working_copy()
                tools: dict[str, dict[str, JsonValue]] = {
                    "idea_native_calculate": {"path": str(path), "connection_id": "CON1"},
                }
                if route == "rest":
                    opened = await port.call("idea_open_project", {"path": str(path)}, op_id="open", model=model)
                    assert rig.payload(opened, "harness.idea_project/1")["live_project"]
                    tools = {_CALC: {"connection_ids": [1]}, "idea_get_check_results": {"connection_id": 1}}
                for tool, args in tools.items():
                    result = await port.call(tool, args, op_id=tool, model=model)
                    verdicts = VerdictSet.model_validate(rig.payload(result, "verdicts.set/1"))
                    assert isinstance(result, SuccessEnvelope)
                    (parent,) = rig.store.get(result.result_id).parents
                    assert rig.store.get(parent).kind == "harness.idea_check_raw/1"
                    assert verdicts.draft
                    assert {v.code for v in verdicts.verdicts} == {_DESIGN_CODE}
                    assert {v.source.value for v in verdicts.verdicts} == {"host"}
                    # Synthetic check percentages from the fake's seeded loads, §4.5 conversion.
                    assert {v.check_id: v.ratio for v in verdicts.verdicts} == {
                        "idea:plates": 0.42,
                        "idea:bolts": 0.235,
                    }
                if route == "rest":
                    tool = "idea_get_check_results"
                    _fault(rig.control, "service_stopped", tool=tool)
                    stub = await port.call(tool, tools[tool], op_id="stub-results", model=model)
                    assert isinstance(stub, FailureEnvelope), stub
                    assert (stub.error.code, stub.error.host_code) == (ErrorCode.HOST_ERROR, "OFFLINE_STUB")

    anyio.run(body)


def test_reconcile_lost_writes_through_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, confirmed_map: None
) -> None:
    """AC18, §4.7 and §4.10: durable pre-send evidence and read-only reconciliation of both writes."""

    async def body() -> None:
        native = _Rig(tmp_path / "native", "native")
        native.freeze_basis()
        async with native.ports:
            model, path = await native.working_copy()
            port = native.ports.tool_port
            args = native.load_args(model, path)
            writes = native.observe_write(monkeypatch, _SET, "lost-loads", args)
            # The fake applies the write, adds 1 N, and withholds its reply. The frozen synthetic tolerance accepts it.
            _fault(native.control, "timeout_set_loads", tool=_SET, mismatch=True)
            before = native.ports.host_port.session_epoch("idea")
            failed = await port.call(_SET, args, op_id="lost-loads", model=model)
            _assert_lost(failed, "lost-loads")
            assert native.ports.host_port.session_epoch("idea") > before
            ((entry, wire),) = writes
            assert entry["target"] == {
                "route": "native",
                "file": path.relative_to(native.run).as_posix(),
                "service_url": native.service_url,
            }
            pre_image_ref = entry["pre_image_ref"]
            sent = native.ref_value(pre_image_ref.removesuffix("/observed") + "/sent")
            assert wire["confirm"] is True
            assert wire["connection_id"] == "CON1"
            assert port.supports_reconcile(_SET)
            await _assert_native_reconcile_failures(native, args, entry, sent, path)

            calls_at_read: list[bytes] = []
            send = native.ports.servers.call

            async def note_read(
                server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
            ) -> CallToolResult:
                reply = await send(server, role, tool, arguments, effect)
                if tool == _GET:
                    calls_at_read.append(native.control.read_bytes())
                return reply

            with monkeypatch.context() as patch:
                patch.setattr(native.ports.servers, "call", note_read)
                decision = await port.reconcile(_SET, args, "lost-loads")
            # Reconciliation reads the file through the host. The control log stays unchanged after that read.
            (calls_after_read,) = calls_at_read
            assert native.control.read_bytes() == calls_after_read
            assert decision.outcome == "applied"
            observed = native.payload(decision.result, "harness.idea_loads/1")
            assert observed["effects"][0]["segments"][0]["N_kN"] == 25.001
            assert native.ports.host_port.model_files(model) == (native.run / sent["out_path"],)
            assert len(writes) == 1

        rest = _Rig(tmp_path / "rest", "rest")
        rest.freeze_basis()
        async with rest.ports:
            model, path = await rest.working_copy()
            port = rest.ports.tool_port
            opened = await port.call("idea_open_project", {"path": str(path)}, op_id="open", model=model)
            assert rest.payload(opened, "harness.idea_project/1")["live_project"]
            rest_args: dict[str, JsonValue] = {"connection_ids": [1]}
            writes = rest.observe_write(monkeypatch, _CALC, "lost-calc", rest_args)
            _fault(rest.control, "timeout_calculate", tool=_CALC)
            _assert_lost(await port.call(_CALC, rest_args, op_id="lost-calc", model=model), "lost-calc")
            ((rest_entry, wire),) = writes
            assert rest_entry["target"] != entry["target"]
            assert rest_entry["target"] == {
                "route": "rest",
                "file": path.relative_to(rest.run).as_posix(),
                "service_url": rest.service_url,
            }
            assert wire == {"connection_ids": [1], "confirm": True}
            assert port.supports_reconcile(_CALC)
            calls_before = rest.control.read_bytes()
            malformed = await port.reconcile(_CALC, {"connection_ids": "x"}, "lost-calc")
            assert malformed.outcome == "unknown"
            assert malformed.result is None
            assert (await port.reconcile(_CALC, rest_args, "lost-calc")).outcome == "unknown"
            assert rest.control.read_bytes() == calls_before
            assert len(writes) == 1

    anyio.run(body)


async def _assert_native_reconcile_failures(
    rig: _Rig, args: dict[str, JsonValue], entry: dict[str, Any], sent: dict[str, Any], source: Path
) -> None:
    port = rig.ports.tool_port
    rig.record_load_request(entry, "tampered", sent, confirm=False)
    rig.record_load_request(entry, "outside", sent, out_path="../outside.ideaCon")
    rig.record_load_request(entry, "not-applied", sent, out_path="never-written.ideaCon")
    malformed = {**args, "effects": "invalid"}
    rig.record_attempt(entry, "bad-plan", args_sha256=payload_sha256(malformed))

    calls_before = rig.control.read_bytes()
    for op_id, request in (
        ("lost-loads", {**args, "connection": "different"}),
        ("missing", args),
        ("tampered", args),
        ("outside", args),
        ("bad-plan", malformed),
    ):
        decision = await port.reconcile(_SET, request, op_id)
        assert decision.outcome == "unknown", op_id
        assert decision.result is None
        assert rig.control.read_bytes() == calls_before

    original = source.read_bytes()
    source.write_bytes(original + b"\n")
    try:
        drifted = await port.reconcile(_SET, args, "lost-loads")
        assert drifted.outcome == "unknown"
        (evidence,) = drifted.evidence
        assert rig.ref_value(evidence.ref) == {"read_failed": ErrorCode.PRECONDITION_FAILED.value}
        assert rig.control.read_bytes() == calls_before
    finally:
        source.write_bytes(original)

    absent = await port.reconcile(_SET, args, "not-applied")
    assert absent.outcome == "not_applied"
    assert absent.result is None
    assert rig.control.read_bytes() == calls_before
    observed = rig.payload(await port.read_back(_SET, args), "harness.idea_loads/1")
    assert observed == rig.ref_value(entry["pre_image_ref"])

    _fault(rig.control, "license_refused", tool=_GET)
    failed = await port.reconcile(_SET, args, "lost-loads")
    assert failed.outcome == "unknown"
    assert failed.result is None
    (evidence,) = failed.evidence
    assert rig.ref_value(evidence.ref) == {"read_failed": ErrorCode.HOST_NOT_CONNECTED.value}


def _assert_lost(envelope: Envelope, op_id: str) -> None:
    assert isinstance(envelope, FailureEnvelope), envelope
    assert envelope.error.code == ErrorCode.TIMEOUT_UNKNOWN_OUTCOME
    assert envelope.error.op_id == op_id
