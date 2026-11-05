"""Unit tests of `aci318_14.13_3_1_1.bearing_pressure_service` (plan 0002 T3; BP-AC2, BP-AC3).

Inputs are the clause spec's §8 common inputs; expected values and tolerances are those of §8 (0.01 kPa on pressures,
1e-6 on ratios). BD-2's `q_min_kPa` is asserted to be exactly 0.0 (edge case E-1).
"""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.params import ParamSpec
from eng_contract.records import ResultRecord
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry

from aci318_14 import __version__
from aci318_14.checks.bearing_pressure import AllowableKind, BearingInputs, bearing_pressure_service

_ID = "aci318_14.13_3_1_1.bearing_pressure_service"
_F1 = Subject(kind=SubjectKind.FOOTING, id="F1")
_P_KPA = 0.01
_RATIO = 1e-6
_BASIS_ID = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
_FORCES_ID = "res_01ARZ3NDEKTSV4RRFFQ69G5FAW"
_TS = "2026-01-02T03:04:05.678Z"
_COMMON: dict[str, Any] = {
    "FX_kN": 0.0,
    "FY_kN": 0.0,
    "FZ_kN": 1200.0,
    "MX_kNm": 0.0,
    "MY_kNm": 0.0,
    "Lx_mm": 2500.0,
    "Ly_mm": 2500.0,
    "reaction_height_mm": 0.0,
    "h_mm": 600.0,
    "soil_depth_mm": 1000.0,
    "gamma_c_kN_m3": 24.0,
    "gamma_s_kN_m3": 18.0,
    "surcharge_kPa": 0.0,
    "q_allow_kPa": 250.0,
    "allowable_kind": "gross",
}
_REGISTRY = Registry.of(
    [Pack("aci318_14", "ACI 318-14", "2014", __version__, (bearing_pressure_service,), "approvals.yaml")]
)


def _run(**changes: Any) -> Any:
    return evaluate(_ID, {**_COMMON, **changes}, subject=_F1, registry=_REGISTRY).payload


def _steps(payload: Any) -> dict[str, float]:
    return {s.name: s.value for s in payload.traces[0].steps}


@pytest.mark.parametrize(
    ("case", "changes", "precondition", "gap"),
    [
        ("BD-1", {"FZ_kN": 200.0, "MY_kNm": 300.0}, "FULL_CONTACT", "G-1"),
        ("BD-3", {"FZ_kN": -250.0}, "COMPRESSION", None),
        ("BD-4", {"allowable_kind": "net"}, "ALLOWABLE_GROSS", "G-2"),
    ],
)
def test_preconditions(case: str, changes: dict[str, Any], precondition: str, gap: str | None) -> None:
    """BD-1, BD-3, BD-4: one NEEDS_ENGINEER verdict, no numbers, a message naming the precondition and gap (BP-AC2)."""
    payload = _run(**changes)
    (verdict,) = payload.verdicts
    assert verdict.status is VerdictStatus.NEEDS_ENGINEER, case
    assert (verdict.demand, verdict.capacity, verdict.ratio) == (None, None, None)
    (message,) = [m for m in payload.traces[0].messages if m.startswith(precondition)]
    assert gap is None or gap in message
    if case == "BD-1":
        assert _steps(payload)["q_min_kPa"] == pytest.approx(-50.8, abs=_P_KPA)


def test_contact_at_zero_and_scope() -> None:
    """BD-2: q_min = 0 exactly keeps full contact and gives FAIL with the §8 values; BD-5: NOT_APPLICABLE (BP-AC2)."""
    payload = _run(MY_kNm=584.375)
    (verdict,) = payload.verdicts
    assert _steps(payload)["q_min_kPa"] == 0.0
    assert verdict.status is VerdictStatus.FAIL
    assert verdict.demand is not None
    assert (verdict.demand.value, verdict.demand.unit) == (pytest.approx(448.8, abs=_P_KPA), "kPa")
    assert verdict.ratio == pytest.approx(1.7952, abs=_RATIO)
    assert verdict.clause == "13.3.1.1"
    frame = evaluate(_ID, _COMMON, subject=Subject(kind=SubjectKind.FRAME, id="B1"), registry=_REGISTRY).payload
    assert frame.verdicts[0].status is VerdictStatus.NOT_APPLICABLE


def test_metadata() -> None:
    """Check id, clause, member scope, gaps and spec path of the clause spec (§2, §10; plan §2 T3 to T8)."""
    meta = bearing_pressure_service.meta
    assert meta.check_id == _ID
    assert meta.clauses == ("13.3.1.1",)
    assert meta.members == frozenset({SubjectKind.FOOTING})
    assert [g.id for g in meta.gaps] == ["G-1", "G-2"]
    assert meta.spec == f"aci318_14/{_ID}.md"
    assert [p.id for p in bearing_pressure_service.preconditions] == ["ALLOWABLE_GROSS", "COMPRESSION", "FULL_CONTACT"]
    assert {k.value for k in AllowableKind} == {"gross", "net"}


class _Records:
    """In-memory record source: one `basis.design_basis/1` result and one `forces.joint_reactions/1` result."""

    def __init__(self) -> None:
        engineer = "engineer:Sam@2026-02-01T08:00:00.000Z"
        fields: dict[str, dict[str, Any]] = {
            "foundation.allowable_bearing_pressure": {"value": 250.0, "unit": "kPa"},
            "foundation.allowable_bearing_kind": {"value": "gross", "unit": None},
        }
        basis = {
            "template": None,
            "fields": {p: {**f, "source": engineer, "confirmed": True, "citation": None} for p, f in fields.items()},
        }
        DesignBasis.model_validate(basis)  # the fixture is a valid design basis
        self.records = {
            _BASIS_ID: self._record(_BASIS_ID, "basis.design_basis/1", basis),
            _FORCES_ID: self._record(_FORCES_ID, "forces.joint_reactions/1", {"rows": [{"q_kPa": 250.0}]}),
        }

    @staticmethod
    def _record(result_id: str, kind: str, payload: dict[str, Any]) -> ResultRecord:
        producer = {"tool": "harness", "tool_version": "1", "inputs": {}, "started_at": _TS, "duration_ms": 0}
        return ResultRecord.model_validate(
            {
                "contract": "eng-contract/1",
                "result_id": result_id,
                "kind": kind,
                "created_at": _TS,
                "units": "canonical/1",
                "complete": True,
                "producer": producer,
                "parents": [],
                "payload_sha256": "b" * 64,
                "payload": payload,
                "payload_file": None,
            }
        )

    def get(self, result_id: str) -> ResultRecord:
        if result_id not in self.records:
            raise ContractError(ErrorCode.REF_NOT_FOUND, f"no result {result_id}")
        return self.records[result_id]

    def payload(self, result_id: str) -> dict[str, Any]:
        return dict(self.get(result_id).payload or {})


def test_allowable_from_basis() -> None:
    """The allowable pressure and its kind come from the design basis; the trace keeps the reference (BP-AC3).

    Every recorded constant is one of the clause spec's §5 (`k_m`, `c_S`, `c_I`).
    """
    spec = BearingInputs.model_fields["q_allow_kPa"].json_schema_extra
    assert isinstance(spec, ParamSpec)
    assert (spec.unit, spec.ref_capable, spec.ref_kinds) == ("kPa", True, frozenset({"basis.design_basis/1"}))
    kind_spec = BearingInputs.model_fields["allowable_kind"].json_schema_extra
    assert isinstance(kind_spec, ParamSpec)
    assert (kind_spec.ref_capable, kind_spec.ref_kinds) == (True, frozenset({"basis.design_basis/1"}))

    records = _Records()
    kind_ref = f"{_BASIS_ID}#/fields/foundation.allowable_bearing_kind/value"
    raw = {**_COMMON, "allowable_kind": {"$ref": kind_ref}}
    payload = evaluate(_ID, raw, subject=_F1, registry=_REGISTRY, source=records).payload
    assert payload.verdicts[0].status is VerdictStatus.PASS
    trace = payload.traces[0]
    refs = {i.name: i.ref for i in trace.inputs}
    assert refs["allowable_kind"] == kind_ref
    assert refs["q_allow_kPa"] is None  # given as a literal here
    assert {c.name: c.cited.value for c in trace.constants} == {"k_m": 0.001, "c_S": 6, "c_I": 12}
    assert all(c.cited.source.startswith(("SI prefix", "Mechanics of materials")) for c in trace.constants)

    wrong = {**_COMMON, "q_allow_kPa": {"$ref": f"{_FORCES_ID}#/rows/0/q_kPa"}}
    with pytest.raises(ContractError) as refused:
        evaluate(_ID, wrong, subject=_F1, registry=_REGISTRY, source=records)
    assert refused.value.detail.code is ErrorCode.REF_KIND_MISMATCH
    assert refused.value.detail.field == "q_allow_kPa"
