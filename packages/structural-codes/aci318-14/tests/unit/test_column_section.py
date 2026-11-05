"""Shared column section model CS S1 to S7 and column preconditions CP (plan 0004 T1; AF-AC1, AF-AC2, MA-AC3).

Expected values are the hand values of the clause specs' §8: the axial-flexure spec (common section, SP-1, BD-3, BD-4,
CS S6 and S7) and the maximum axial strength spec (BD-1 to BD-3). Tolerances are those of AF §8: 1e-4 mm, 0.001 kN
and kN.m, 1e-6 on ratios, strains and `phi`.
"""

# ruff: noqa: N815  # B-330: field names are fixed by the contract's unit suffixes (EC §4.7.2), e.g. A_bar_mm2

import os
from pathlib import Path
from typing import Any

import pytest
from eng_contract.cited import Cited
from eng_contract.envelope import LiteralInput
from eng_contract.params import ValidatedInput
from eng_contract.verdicts import Subject, SubjectKind
from structural_codes.applicability import Outcome, Precondition
from structural_codes.errors import CheckDefinitionError
from structural_codes.inputs import CheckInputs, bounded, unbounded
from structural_codes.trace import TraceRecorder

from aci318_14._column import (
    BAR_LAYOUT,
    COLUMN_CITED,
    SHORT_COLUMN,
    STEEL_IN_SECTION,
    TransverseKind,
    axial_cap,
    axial_compression,
    column_section,
    record_point,
)
from aci318_14._common import FC_MIN, FY_MAX, SECTION_CITED

_MM = Cited(value=0, unit="mm", source="Geometry: test input, a length is positive")
_MM2 = Cited(value=0, unit="mm2", source="Geometry: test input, an area is positive")
_MPA = Cited(value=0, unit="MPa", source="Mechanics of materials: test input, a strength is positive")
_ONE = Cited(value=0, unit="1", source="Geometry: test input, a count or factor is positive")
_LEN, _KN, _RATIO = 1e-4, 0.001, 1e-6


class _Column(CheckInputs):
    """Inputs common to the column checks (AF §3, MA §3)."""

    Pu_kN: float = unbounded(reason="signed axial force, compression positive", unit="kN")
    b_mm: float = bounded(gt=_MM, unit="mm")
    h_mm: float = bounded(gt=_MM, unit="mm")
    fc_MPa: float = bounded(gt=_MPA, unit="MPa")
    fy_MPa: float = bounded(gt=_MPA, unit="MPa")
    transverse_kind: TransverseKind = TransverseKind.TIED
    k_factor: float = bounded(gt=_ONE, unit="1")
    lu_mm: float = bounded(gt=_MM, unit="mm")


class _Layout(_Column):
    """Axial-flexure form: the bar layout of CS S1."""

    d_prime_mm: float = bounded(gt=_MM, unit="mm")
    n_bars_b: int = bounded(gt=_ONE, unit="1")
    n_bars_h: int = bounded(gt=_ONE, unit="1")
    A_bar_mm2: float = bounded(gt=_MM2, unit="mm2")


class _Axial(_Column):
    """Maximum axial strength form: the total steel area as an input."""

    Ast_mm2: float = bounded(gt=_MM2, unit="mm2")


class _Limits(CheckInputs):
    """Reinforcement limits form: both areas as inputs."""

    Ag_mm2: float = bounded(gt=_MM2, unit="mm2")
    Ast_mm2: float = bounded(gt=_MM2, unit="mm2")


_BASE: dict[str, Any] = {
    "Pu_kN": 1500.0,
    "b_mm": 500.0,
    "h_mm": 500.0,
    "fc_MPa": 28.0,
    "fy_MPa": 420.0,
    "k_factor": 1.0,
    "lu_mm": 3000.0,
}
COMMON: dict[str, Any] = {**_BASE, "d_prime_mm": 60.0, "n_bars_b": 3, "n_bars_h": 3, "A_bar_mm2": 500.0}
AXIAL: dict[str, Any] = {**_BASE, "Ast_mm2": 4000.0}
_AF = (FC_MIN, FY_MAX, BAR_LAYOUT, STEEL_IN_SECTION, SHORT_COLUMN, axial_compression("G-3"))


def recorder(model_cls: type[Any], **values: Any) -> tuple[Any, TraceRecorder]:
    """Return the validated model and a recorder over it, every field given as a literal."""
    model = model_cls(**values)
    provenance = {name: LiteralInput(literal=value) for name, value in values.items()}
    t = TraceRecorder(
        ValidatedInput(model, provenance),
        calc_id="aci318_14.22_4_1_1.column_test",
        calc_version="0.1.0.dev0",
        content_sha256="0" * 64,
        subject=Subject(kind=SubjectKind.FRAME, id="C1"),
    )
    return model, t


def _passes(p: Precondition, model_cls: type[Any], **values: Any) -> bool:
    model, t = recorder(model_cls, **values)
    return bool(p.test(model, t))


def _section(**changes: Any) -> tuple[Any, TraceRecorder]:
    """Run the axial-flexure preconditions on the common section with `changes`, then CS S1, S2, S6, S7."""
    model, t = recorder(_Layout, **{**COMMON, **changes})
    assert all(p.test(model, t) for p in _AF)
    return column_section(model, t), t


def _steps(t: TraceRecorder) -> dict[str, float]:
    return {s.name: float(s.value) for s in t.to_trace(outputs=[], status=None).steps}


def test_section_point_sp1() -> None:
    """SP-1: CS S3 at the balanced depth `c = eps_cu*dt/(eps_cu + eps_ty)` of the common section (AF-AC1)."""
    sec, t = _section()
    c = t.value("eps_cu") * (500.0 - 60.0) / (t.value("eps_cu") + t.value("eps_ty_ratio"))
    assert c == pytest.approx(258.823529, abs=_LEN)
    point = record_point(t, sec, c, "eps_cu * (h_mm - d_prime_mm) / (eps_cu + eps_ty_ratio)", "AF §8 SP-1")
    s = _steps(t)
    assert s["Ast_mm2"] == 4000.0
    assert [s[f"d_{j}_mm"] for j in range(3)] == [60.0, 250.0, 440.0]
    assert [s[f"A_{j}_mm2"] for j in range(3)] == [1500.0, 1000.0, 1500.0]
    assert s["eps_ty_ratio"] == pytest.approx(0.0021, abs=_RATIO)
    assert s["beta1_ratio"] == 0.85
    assert s["c_mm"] == pytest.approx(258.823529, abs=_LEN)
    assert s["a_mm"] == pytest.approx(220.0, abs=_LEN)
    assert s["Cc_kN"] == pytest.approx(2618.0, abs=_KN)
    assert [s[f"F_{j}_kN"] for j in range(3)] == pytest.approx([594.3, 20.454545, -630.0], abs=_KN)
    assert s["Pn_kN"] == pytest.approx(2602.754545, abs=_KN)
    assert s["Mn_kNm"] == pytest.approx(599.137, abs=_KN)
    assert s["eps_t_ratio"] == pytest.approx(0.0021, abs=_RATIO)
    assert s["phi_ratio"] == pytest.approx(0.65, abs=_RATIO)
    assert point.pn * t.value("k_kilo") == pytest.approx(s["Pn_kN"], abs=1e-9)
    names = {st.name: st for st in t.to_trace(outputs=[], status=None).steps}
    assert set(names["F_0_kN"].uses) >= {"A_0_mm2", "fs_0_MPa", "alpha_1", "fc_MPa", "k_kilo"}
    assert set(names["Mn_kNm"].uses) >= {"Cc_kN", "F_0_kN", "F_1_kN", "F_2_kN", "k_kilo_milli"}


@pytest.mark.parametrize(
    ("kind", "phi_cc", "slope", "phi_pn_max"),
    [(TransverseKind.TIED, 0.65, 0.25, 3918.096), (TransverseKind.SPIRAL, 0.75, 0.15, 4803.435)],
)
def test_phi_rows_and_axial_cap(kind: TransverseKind, phi_cc: float, slope: float, phi_pn_max: float) -> None:
    """BD-4 rows of Table 21.2.2 at their boundaries; CS S6 and S7 for the common section (AF-AC2)."""
    sec, t = _section(transverse_kind=kind)
    eps_ty = t.value("eps_ty_ratio")
    assert sec.phi(eps_ty) == phi_cc
    assert sec.phi(eps_ty - 1e-9) == phi_cc
    assert sec.phi(0.005) == 0.90
    assert sec.phi(0.006) == 0.90
    assert sec.phi((eps_ty + 0.005) / 2) == pytest.approx(phi_cc + slope / 2, abs=1e-12)
    assert t.value("Po_kN") == pytest.approx(7534.8, abs=_KN)
    pn_max = {TransverseKind.TIED: 6027.84, TransverseKind.SPIRAL: 6404.58}[kind]
    assert t.value("Pn_max_kN") == pytest.approx(pn_max, abs=_KN)
    assert t.value("phiPn_max_kN") == pytest.approx(phi_pn_max, abs=_KN)
    assert t.value("c_full_mm") == pytest.approx(1466.666667, abs=_LEN)
    full = sec.at(sec.c_full)
    assert full.a == 500.0
    assert full.pn * t.value("k_kilo") == pytest.approx(t.value("Po_kN"), abs=_KN)
    assert abs(full.mn * t.value("k_kilo_milli")) <= 1e-6


def test_axial_cap_from_input_area() -> None:
    """CS S6 with `Ast_mm2` as an input (maximum axial strength HC-1): `Ag`, `Po`, `Pn_max`, `phiPn_max`."""
    model, t = recorder(_Axial, **AXIAL)
    assert STEEL_IN_SECTION.test(model, t)
    po, pn_max, phi_pn_max = axial_cap(model, t)
    assert t.value("Ag_mm2") == 250000.0
    assert (po, pn_max, phi_pn_max) == pytest.approx((7534.8, 6027.84, 3918.096), abs=_KN)
    with pytest.raises(CheckDefinitionError):
        axial_cap(model, t)


def test_column_preconditions() -> None:
    """Each CP just below, at and above its limit (MA-AC3; MA BD-1 to BD-3, AF BD-3)."""
    assert _passes(FY_MAX, _Layout, **{**COMMON, "fy_MPa": 550.0})
    assert not _passes(FY_MAX, _Layout, **{**COMMON, "fy_MPa": 600.0})
    assert not _passes(FC_MIN, _Layout, **{**COMMON, "fc_MPa": 16.0})
    for d_prime, ok in ((249.0, True), (250.0, False), (251.0, False)):
        assert _passes(BAR_LAYOUT, _Layout, **{**COMMON, "d_prime_mm": d_prime}) is ok
    assert not _passes(BAR_LAYOUT, _Layout, **{**COMMON, "b_mm": 120.0, "h_mm": 900.0})
    assert not _passes(BAR_LAYOUT, _Layout, **{**COMMON, "b_mm": 900.0, "h_mm": 120.0})
    small = {**COMMON, "b_mm": 60.0, "h_mm": 60.0, "d_prime_mm": 20.0, "A_bar_mm2": 1000.0}
    assert not _passes(STEEL_IN_SECTION, _Layout, **small)
    assert _passes(STEEL_IN_SECTION, _Layout, **COMMON)
    for ast, ok in ((249999.0, True), (250000.0, False), (250001.0, False)):
        assert _passes(STEEL_IN_SECTION, _Axial, **{**AXIAL, "Ast_mm2": ast}) is ok
        assert _passes(STEEL_IN_SECTION, _Limits, Ag_mm2=250000.0, Ast_mm2=ast) is ok
    for lu, ok in ((3299.0, True), (3300.0, True), (3301.0, False)):
        model, t = recorder(_Axial, **{**AXIAL, "lu_mm": lu})
        assert SHORT_COLUMN.test(model, t) is ok
        assert t.value("kl_r_ratio") == pytest.approx(lu / 150.0, abs=_RATIO)
    assert not _passes(SHORT_COLUMN, _Axial, **{**AXIAL, "b_mm": 400.0, "lu_mm": 3000.0})
    compression = axial_compression("G-1")
    for pu, ok in ((-1.0, False), (0.0, True), (1.0, True)):
        assert _passes(compression, _Axial, **{**AXIAL, "Pu_kN": pu}) is ok


def test_declarations() -> None:
    """Ids, outcomes and clauses of CP (MA §2.1); the gap id appears in the message; a malformed one is refused."""
    found = [(p.id, p.outcome) for p in (BAR_LAYOUT, STEEL_IN_SECTION, SHORT_COLUMN, axial_compression("G-3"))]
    ne = Outcome.NEEDS_ENGINEER
    assert found == [("BAR_LAYOUT", ne), ("STEEL_IN_SECTION", ne), ("SHORT_COLUMN", ne), ("AXIAL_COMPRESSION", ne)]
    assert "G-2" in SHORT_COLUMN.description
    assert "G-3" in axial_compression("G-3").description
    with pytest.raises(CheckDefinitionError):
        axial_compression("G3")


_AF_SPEC = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "clauses"
    / "aci318_14"
    / "aci318_14.22_4_1_1.axial_flexure_uniaxial.md"
)


def test_constants_match_clause_spec() -> None:
    """The column and stress-block constants carry the value, unit and Citation cell of AF §5 verbatim."""
    if not _AF_SPEC.is_file() and "MUTANT_UNDER_TEST" in os.environ:
        pytest.skip("the clause specs are outside the copy the mutation step runs (B-423); expires 2026-12-31")
    body = _AF_SPEC.read_text(encoding="utf-8").split("\n## 5.", 1)[1].split("\n## ", 1)[0]
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in body.splitlines() if ln.startswith("| `")]
    table = {sym.strip("`"): (float(value), unit, citation) for sym, value, unit, citation in rows}
    for name, cited in {**SECTION_CITED, **COLUMN_CITED}.items():
        assert table[name] == (float(cited.value), cited.unit, cited.source), name
    assert set(SECTION_CITED) == {
        "phi_tc",
        "eps_tc",
        "eps_cu",
        "alpha_1",
        "beta1_hi",
        "beta1_slope",
        "beta1_step",
        "fc_beta_lo",
        "fc_beta_hi",
        "beta1_lo",
    }
