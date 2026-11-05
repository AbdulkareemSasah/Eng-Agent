"""HarnessCalcPort: describe, run, preflight, run class, limits and storage (plan 0003 T5; spec 0003 AC11 to AC18)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from eng_contract.envelope import FailureEnvelope, Provenance, RefInput, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore
from pydantic import JsonValue

from eng_harness import __version__
from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness.calc import CalcRegistry, CalcStatus, NotImplementedGap
from eng_harness.errors import CalcRefused, HarnessCode
from eng_harness.ports import RunClass

HASH = "cd" * 32
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
        self, fx: ModuleType, tmp_path: Path, run_class: RunClass, *, approvals: ApprovalsFile, max_items: int
    ):
        from eng_contract.store import LocationClass, Workspace

        self.fx = fx
        clock = FixedClock(1_767_225_600_000, 1)
        self.ids = SeededIdSource(b"harness", clock)
        kinds = fx.kinds()
        self.store = _CountingStore(
            Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), kinds, self.ids, clock
        )
        registry = CalcRegistry(kinds, [fx.port_sum], hasher=lambda _: HASH)
        self.port = HarnessCalcPort(
            registry, approvals, self.store, CalcSettings(max_items=max_items), run_class, clock, self.ids
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
) -> Rig:
    approvals = ApprovalsFile.model_validate(
        {"schema": 1, "approvals": [APPROVAL] if approved else [], "withdrawn": [WITHDRAWN] if withdrawn else []}
    )
    return Rig(fx, tmp_path, run_class, approvals=approvals, max_items=max_items)


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
