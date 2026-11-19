"""HarnessCalcPort: describe, run, preflight, run class, limits and storage (plan 0003 T5; spec 0003 AC11 to AC18)."""

import dataclasses
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from eng_contract.envelope import FailureEnvelope, Provenance, RefInput, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode, WarningCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from pydantic import JsonValue

from eng_harness import __version__
from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import CalcRegistry, CalcStatus, NotImplementedGap
from eng_harness.errors import CalcRefused, HarnessCode
from eng_harness.ports import RunClass

HASH = "cd" * 32
VERIFIED_ID = "harness.port_verified"
_PATH = Path(__file__).resolve().parents[2] / "data" / "calcs" / "port_calcs.py"
APPROVAL = {
    "calc_id": "harness.port_sum",
    "version": 2,
    "content_sha256": HASH,
    "approver": "owner",
    "date": "2026-01-31",
    "verification_record": "docs/verification/calcs/harness.port_sum.md",
    "pull_request": 12,
}
WITHDRAWN = {
    "calc_id": "harness.port_sum",
    "version": 2,
    "content_sha256": "any",
    "date": "2026-02-01",
    "reason": "Wrong rule",
    "advisory": "Rerun",
}


@pytest.fixture(scope="module")
def fx() -> ModuleType:
    """The fixture calc module, loaded by path."""
    spec = importlib.util.spec_from_file_location("port_calcs", _PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["port_calcs"] = module
    spec.loader.exec_module(module)
    return module


class _CountingStore(ResultStore):
    """A result store that counts `put` calls."""

    puts = 0

    def put(self, *args: Any, **kwargs: Any) -> Any:
        """Count, then delegate."""
        self.puts += 1
        return super().put(*args, **kwargs)


class Rig:
    """A port over a store that counts `put` calls."""

    def __init__(
        self,
        fx: ModuleType,
        tmp_path: Path,
        run_class: RunClass,
        *,
        approvals: ApprovalsFile,
        max_items: int,
        basis_fields: dict[str, list[str]] | None = None,
    ):
        from eng_contract.store import LocationClass, Workspace

        self.fx = fx
        clock = FixedClock(1_767_225_600_000, 1)
        self.ids = SeededIdSource(b"harness", clock)
        kinds = fx.kinds()
        self.store = _CountingStore(
            Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), kinds, self.ids, clock
        )
        verified = dataclasses.replace(fx.port_sum, id=VERIFIED_ID, verification="verified")
        registry = CalcRegistry(kinds, [fx.port_sum, verified], hasher=lambda _: HASH)
        self.port = HarnessCalcPort(
            registry,
            approvals,
            self.store,
            CalcSettings(max_items=max_items),
            run_class,
            clock,
            self.ids,
            basis_fields=basis_fields,
        )

    def source(self, value: dict[str, JsonValue], kind: str | None = None) -> str:
        """Store a record and return its id."""
        producer = Provenance(
            tool="harness", tool_version="t", inputs={}, started_at=FixedClock(1, 1).now(), duration_ms=0
        )
        result_id: str = self.store.put(kind or self.fx.SOURCE_KIND, {"value": value}, producer).result_id
        return result_id

    def args(self, **extra: Any) -> dict[str, Any]:
        """Arguments with a valid span reference."""
        rid = self.source({"span_mm": 500.0, "rows": [1.0, 2.0, 3.0]})
        return {"span_mm": {"$ref": f"{rid}#/value/span_mm"}, **extra} | {"_rid": rid}


def make(
    fx: ModuleType,
    tmp_path: Path,
    run_class: RunClass = RunClass.TRIAL,
    *,
    approved: bool = False,
    withdrawn: bool = False,
    max_items: int = 100,
    basis_fields: dict[str, list[str]] | None = None,
) -> Rig:
    approvals = ApprovalsFile.model_validate(
        {"schema": 1, "approvals": [APPROVAL] if approved else [], "withdrawn": [WITHDRAWN] if withdrawn else []}
    )
    return Rig(fx, tmp_path, run_class, approvals=approvals, max_items=max_items, basis_fields=basis_fields)


def run(rig: Rig, **extra: Any) -> SuccessEnvelope | FailureEnvelope:
    args = rig.args(**extra)
    args.pop("_rid")
    return rig.port.run("harness.port_sum", args)


def test_describe(fx: ModuleType, tmp_path: Path) -> None:
    rig = make(fx, tmp_path)
    info = rig.port.describe("harness.port_sum")
    assert (info.id, info.version, info.content_sha256, info.status) == ("harness.port_sum", 2, HASH, CalcStatus.DRAFT)
    assert info.engineering_params == ("span_mm", "older_mm", "rows")
    assert set(info.ref_rules) == {"span_mm", "older_mm", "rows"}
    assert info.ref_rules["span_mm"].kinds == frozenset({fx.SOURCE_KIND})
    assert info.ref_rules["span_mm"].unit == "mm"
    assert [p for p, r in info.ref_rules.items() if r.stale_ok] == ["older_mm"]
    assert info.basis_fields == ()
    with_basis = make(fx, tmp_path / "b", basis_fields={"harness.port_sum": ["tolerances.length_mm"]})
    assert with_basis.port.describe("harness.port_sum").basis_fields == ("tolerances.length_mm",)
    assert make(fx, tmp_path / "a", approved=True).port.describe("harness.port_sum").status is CalcStatus.APPROVED
    with pytest.raises(ContractError) as caught:
        rig.port.describe("harness.nope")
    assert caught.value.detail.code is ErrorCode.NOT_FOUND


def test_input_validation_codes(fx: ModuleType, tmp_path: Path) -> None:
    rig = make(fx, tmp_path)
    rid = rig.source({"span_mm": 500.0})
    other = rig.source({"span_mm": 500.0}, fx.OTHER_KIND)
    neg = rig.source({"span_mm": -1.0})

    def code(args: dict[str, Any]) -> ErrorCode:
        out = rig.port.run("harness.port_sum", args)
        assert isinstance(out, FailureEnvelope)
        return out.error.code

    assert code({"span_mm": 500.0}) is ErrorCode.INVALID_ARGUMENT  # literal for an engineering input
    assert code({"span_mm": {"$ref": f"{other}#/value/span_mm"}}) is ErrorCode.REF_KIND_MISMATCH
    assert code({"span_mm": {"$ref": f"{rid}#/value/missing"}}) is ErrorCode.REF_POINTER_INVALID
    assert code({"span_mm": {"$ref": "res_" + "0" * 26}}) is ErrorCode.REF_NOT_FOUND
    assert code({"span_mm": {"$ref": f"{neg}#/value/span_mm"}}) is ErrorCode.OUT_OF_RANGE
    assert rig.store.puts == 3  # only the three source records


def test_item_limit(fx: ModuleType, tmp_path: Path) -> None:
    rig = make(fx, tmp_path, max_items=3)
    rid = rig.source({"span_mm": 1.0, "rows": [1.0, 2.0, 3.0, 4.0]})
    before = rig.store.puts
    out = rig.port.run(
        "harness.port_sum", {"span_mm": {"$ref": f"{rid}#/value/span_mm"}, "rows": {"$ref": f"{rid}#/value/rows"}}
    )
    assert isinstance(out, FailureEnvelope)
    assert out.error.code is ErrorCode.LIMIT_EXCEEDED
    assert out.error.expected == {"max": 3}
    assert out.error.received == 4
    assert rig.store.puts == before


def test_item_limit_at_limit_runs(fx: ModuleType, tmp_path: Path) -> None:
    rig = make(fx, tmp_path, max_items=4)
    rid = rig.source({"span_mm": 1.0, "rows": [1.0, 2.0, 3.0, 4.0]})
    before = rig.store.puts
    out = rig.port.run(
        "harness.port_sum", {"span_mm": {"$ref": f"{rid}#/value/span_mm"}, "rows": {"$ref": f"{rid}#/value/rows"}}
    )
    assert isinstance(out, SuccessEnvelope)
    assert rig.store.puts == before + 1


def _two_record_args(rig: Rig) -> dict[str, Any]:
    """Arguments referencing two records that hold 2 and 3 list items."""
    first = rig.source({"span_mm": 1.0, "pad": [1.0, 2.0]})
    second = rig.source({"rows": [1.0, 2.0, 3.0]})
    return {"span_mm": {"$ref": f"{first}#/value/span_mm"}, "rows": {"$ref": f"{second}#/value/rows"}}


def test_item_limit_totals_over_records(fx: ModuleType, tmp_path: Path) -> None:
    rig = make(fx, tmp_path, max_items=4)
    args = _two_record_args(rig)
    before = rig.store.puts
    out = rig.port.run("harness.port_sum", args)
    assert isinstance(out, FailureEnvelope)
    assert out.error.code is ErrorCode.LIMIT_EXCEEDED
    assert out.error.expected == {"max": 4}
    assert out.error.received == 5
    assert rig.store.puts == before


def test_item_limit_totals_over_records_at_limit_runs(fx: ModuleType, tmp_path: Path) -> None:
    rig = make(fx, tmp_path, max_items=5)
    args = _two_record_args(rig)
    before = rig.store.puts
    assert isinstance(rig.port.run("harness.port_sum", args), SuccessEnvelope)
    assert rig.store.puts == before + 1


def test_item_limit_counts_unreferenced_items_of_record(fx: ModuleType, tmp_path: Path) -> None:
    rig = make(fx, tmp_path, max_items=3)
    rid = rig.source({"span_mm": 1.0, "rows": [1.0, 2.0, 3.0, 4.0]})
    before = rig.store.puts
    out = rig.port.run("harness.port_sum", {"span_mm": {"$ref": f"{rid}#/value/span_mm"}})
    assert isinstance(out, FailureEnvelope)
    assert out.error.code is ErrorCode.LIMIT_EXCEEDED
    assert out.error.received == 4
    assert rig.store.puts == before


def test_item_limit_counts_nested_lists(fx: ModuleType, tmp_path: Path) -> None:
    value: dict[str, JsonValue] = {"span_mm": 1.0, "areas": [{"pts": [1, 2]}, {"pts": [3]}]}  # 2 outer + 3 inner = 5
    over = make(fx, tmp_path / "o", max_items=4)
    rid = over.source(value)
    args: dict[str, JsonValue] = {"span_mm": {"$ref": f"{rid}#/value/span_mm"}}
    out = over.port.run("harness.port_sum", args)
    assert isinstance(out, FailureEnvelope)
    assert out.error.code is ErrorCode.LIMIT_EXCEEDED
    assert out.error.expected == {"max": 4}
    assert out.error.received == 5
    ok = make(fx, tmp_path / "k", max_items=5)
    rid = ok.source(value)
    assert isinstance(ok.port.run("harness.port_sum", {"span_mm": {"$ref": f"{rid}#/value/span_mm"}}), SuccessEnvelope)


def test_run_unknown_calc_is_not_found(fx: ModuleType, tmp_path: Path) -> None:
    out = make(fx, tmp_path).port.run("harness.nope", {})
    assert isinstance(out, FailureEnvelope)
    assert out.error.code is ErrorCode.NOT_FOUND


def test_result_record(fx: ModuleType, tmp_path: Path) -> None:
    rig = make(fx, tmp_path)
    args = rig.args(offset=2.5, whole=False)
    rid = args.pop("_rid")
    before = rig.store.puts
    out = rig.port.run("harness.port_sum", args)
    assert isinstance(out, SuccessEnvelope)
    assert rig.store.puts == before + 1
    record = rig.store.get(out.result_id)
    assert record.kind == fx.OUTPUT_KIND
    assert record.complete is False
    assert [w.code for w in out.warnings] == [WarningCode.PARTIAL_DATA]
    assert record.parents == [rid]
    assert record.producer.tool == "harness"
    assert record.producer.tool_version == __version__
    assert record.producer.inputs == {"span_mm": RefInput(ref=f"{rid}#/value/span_mm")}
    payload = rig.store.payload(out.result_id)
    assert payload["total"] == pytest.approx(502.5, abs=1e-9)
    assert payload["calc"] == {"id": "harness.port_sum", "version": 2, "content_sha256": HASH, "status": "draft"}
    trace = payload["trace"]
    assert isinstance(trace, dict)
    assert trace["content_sha256"] == HASH


def test_complete_payload_gives_complete_record(fx: ModuleType, tmp_path: Path) -> None:
    rig = make(fx, tmp_path)
    out = run(rig, whole=True)
    assert isinstance(out, SuccessEnvelope)
    assert rig.store.get(out.result_id).complete is True
    assert out.warnings == []


def test_verified_calc_is_not_approved(fx: ModuleType, tmp_path: Path) -> None:
    prod = make(fx, tmp_path / "p", RunClass.PRODUCTION)
    assert [(r.calc_id, r.status, r.code) for r in prod.port.preflight([VERIFIED_ID])] == [
        (VERIFIED_ID, CalcStatus.VERIFIED, HarnessCode.CALC_NOT_APPROVED)
    ]
    args = prod.args()
    args.pop("_rid")
    before = prod.store.puts
    with pytest.raises(CalcRefused) as caught:
        prod.port.run(VERIFIED_ID, args)
    assert caught.value.code is HarnessCode.CALC_NOT_APPROVED
    assert prod.store.puts == before
    trial = make(fx, tmp_path / "t")
    args = trial.args()
    args.pop("_rid")
    out = trial.port.run(VERIFIED_ID, args)
    assert isinstance(out, SuccessEnvelope)
    assert trial.store.payload(out.result_id)["draft"] is True


def test_production_and_withdrawn_refusal(fx: ModuleType, tmp_path: Path) -> None:
    prod = make(fx, tmp_path / "p", RunClass.PRODUCTION)
    assert prod.port.run_class is RunClass.PRODUCTION
    refusals = prod.port.preflight(["harness.port_sum"])
    assert [(r.calc_id, r.status, r.code) for r in refusals] == [
        ("harness.port_sum", CalcStatus.DRAFT, HarnessCode.CALC_NOT_APPROVED)
    ]
    args = prod.args()
    args.pop("_rid")
    before = prod.store.puts
    with pytest.raises(CalcRefused) as caught:
        prod.port.run("harness.port_sum", args)
    assert caught.value.code is HarnessCode.CALC_NOT_APPROVED
    assert "harness.port_sum" in str(caught.value)
    assert "draft" in str(caught.value)
    assert prod.store.puts == before
    approved = make(fx, tmp_path / "a", RunClass.PRODUCTION, approved=True)
    assert approved.port.preflight(["harness.port_sum"]) == []
    assert isinstance(run(approved), SuccessEnvelope)
    for cls in (RunClass.TRIAL, RunClass.PRODUCTION):
        gone = make(fx, tmp_path / f"w{cls}", cls, approved=True, withdrawn=True)
        assert [r.code for r in gone.port.preflight(["harness.port_sum"])] == [HarnessCode.CALC_WITHDRAWN]
        with pytest.raises(CalcRefused) as withdrawn:
            run(gone)
        assert withdrawn.value.code is HarnessCode.CALC_WITHDRAWN
        assert "harness.port_sum" in str(withdrawn.value)
        assert "withdrawn" in str(withdrawn.value)
    trial = make(fx, tmp_path / "t")
    assert trial.port.preflight(["harness.port_sum"]) == []
    with pytest.raises(ContractError) as unknown:
        trial.port.preflight(["harness.nope"])
    assert unknown.value.detail.code is ErrorCode.NOT_FOUND


def test_draft_marking(fx: ModuleType, tmp_path: Path) -> None:
    rig = make(fx, tmp_path)
    out = run(rig)
    assert isinstance(out, SuccessEnvelope)
    assert rig.store.payload(out.result_id)["draft"] is True
    assert out.summary["status"] == "draft"
    assert out.summary["draft"] is True
    done = run(make(fx, tmp_path / "a", approved=True))
    assert isinstance(done, SuccessEnvelope)
    assert done.summary["status"] == "approved"
    assert done.summary["draft"] is False


def test_not_implemented_gap(fx: ModuleType, tmp_path: Path) -> None:
    rig = make(fx, tmp_path)
    args = rig.args(gap=True)
    args.pop("_rid")
    before = rig.store.puts
    with pytest.raises(NotImplementedGap) as caught:
        rig.port.run("harness.port_sum", args)
    assert fx.GAP_ID in caught.value.message
    assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
    assert rig.store.puts == before


def test_unexpected_exception_is_internal(fx: ModuleType, tmp_path: Path) -> None:
    rig = make(fx, tmp_path)
    out = run(rig, boom=True)
    assert isinstance(out, FailureEnvelope)
    assert out.error.code is ErrorCode.INTERNAL
    assert out.error.incident_id is not None

def test_ref_meta_preserves_pointer(tmp_path: Path) -> None:
    """B-580 / plan 0013 T5: RefMeta.ref keeps the original input reference including its JSON pointer.

    On a harness.section_size/1 record whose required differs from size, sibling pointers #/required and
    #/increment must survive into RefMeta (and therefore into the calc trace) instead of being dropped to the
    bare result id.
    """
    from eng_contract.kinds import KindRegistry
    from eng_contract.params import eng_param
    from eng_contract.quantity import Quantity
    from pydantic import BaseModel, ConfigDict

    from eng_harness.calc import CalcInput, CalcRegistry, InputMeta, TraceBuilder, calc
    from eng_harness.kinds.calcs import CalcPayload

    out_kind = "harness.port_size_echo/1"

    class EchoBody(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")

        value: float

    class EchoOut(CalcPayload, EchoBody):
        pass

    class EchoIn(CalcInput):
        dim: Quantity = eng_param(
            unit="mm",
            ref_capable=True,
            ref_kinds={"harness.section_size/1"},
            engineering_quantity=True,
        )

    @calc(
        id="harness.port_size_echo",
        version=1,
        output_kind=out_kind,
        title="Echo a section_size dimension reference",
        method_source="Test double for RefMeta.ref pointer preservation (B-580)",
    )
    def port_size_echo(inp: EchoIn, meta: InputMeta, trace: TraceBuilder) -> EchoBody:
        seen = meta.refs["dim"].ref
        trace.input("dim", inp.dim.value, unit="mm", ref=seen)
        trace.output("value")
        return EchoBody(value=float(inp.dim.value))

    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"portref", clock)
    kinds = HARNESS_KINDS.extend({out_kind: EchoOut})
    store = ResultStore(Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), kinds, ids, clock)
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=FixedClock(1, 1).now(), duration_ms=0)
    # required=375 mm, size=400 mm (multiple 8 x increment 50); required differs from size (spec 0003 N2 bounds).
    size_payload: dict[str, JsonValue] = {
        "required": {"value": 375.0, "unit": "mm"},
        "increment": {"value": 50.0, "unit": "mm"},
        "multiple": 8,
        "size": {"value": 400.0, "unit": "mm"},
        "status": "PASS",
        "calc": {"id": "harness.section_round", "version": 1, "content_sha256": "a" * 64, "status": "draft"},
        "draft": True,
        "trace": {
            "calc_id": "harness.section_round",
            "calc_version": "1",
            "content_sha256": "a" * 64,
            "inputs": [],
            "constants": [],
            "steps": [
                {
                    "name": "size",
                    "value": 400.0,
                    "unit": "mm",
                    "formula": "n x i",
                    "source": "0003 4.10 N2",
                    "uses": [],
                }
            ],
            "outputs": ["size"],
        },
    }
    size_id = store.put("harness.section_size/1", size_payload, producer).result_id
    registry = CalcRegistry(kinds, [port_size_echo], hasher=lambda _: "ab" * 32)
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
    port = HarnessCalcPort(
        registry,
        approvals,
        store,
        CalcSettings(max_items=1000),
        RunClass.TRIAL,
        clock,
        ids,
    )
    for pointer, expected_value in (("/required", 375.0), ("/increment", 50.0)):
        ref = f"{size_id}#{pointer}"
        out = port.run("harness.port_size_echo", {"dim": {"$ref": ref}})
        assert isinstance(out, SuccessEnvelope), out
        payload = store.payload(out.result_id)
        assert payload["value"] == pytest.approx(expected_value)
        inputs = {row["name"]: row["ref"] for row in payload["trace"]["inputs"]}
        assert inputs["dim"] == ref
