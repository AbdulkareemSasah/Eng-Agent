"""Calc `harness.column_demands` v1: column code-check items and not-checked reasons (spec 0013 4.4.2, E1 to E6).

Purpose: for each selected column, build check items for `max_axial_strength`, `axial_flexure_uniaxial` (only when
symmetric by geometry and layout: `b_mm == h_mm` and `n_bars_b == n_bars_h`, else `AXES_UNDECLARED` `CW-G9`;
Mu=|M3|, Mu_other=|M2| except M2-only Mu=|M2|, Mu_other=0 per amendment B-596 / OQ-Q98), and one
`longitudinal_reinforcement_limits` item per column; report `SHAPE_NOT_CHECKED`, `LAYOUT_MISSING`, `FORCES_MISSING` and
`AXES_UNDECLARED` in `not_checked`. Converted demands, geometry and layout values are literals equal to E3-E5 trace
steps; confirmed basis fields (`fc_MPa`, `fy_MPa`, `k_factor`, `ratio_limit`) are `{"$ref"}` references into `basis`.
Units: mm, mm2, kN, kN.m, MPa.
Errors: `ContractError` `INVALID_ARGUMENT` (forces `sign_convention` enforced by `forces.member_end/1`, missing or
unconfirmed basis field with `field="basis.fields.<path>"`, `limits.ratio_limit_ratio` above the contract
`Verdict.ratio_limit` default, missing record reference, unknown column section), `UNIT_MISMATCH` / `OUT_OF_RANGE` on
basis/layout quantities, `NotImplementedGap` (`CK Q4`) for spiral reinforcement.
"""

import math
from fractions import Fraction
from typing import Annotated, Any, Literal, Self

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.forces import MemberEnd, MemberEndForce
from eng_contract.kinds.model import Rectangular, Sections
from eng_contract.params import eng_param
from eng_contract.refs import RefString
from eng_contract.units import unit
from eng_contract.verdicts import Verdict
from pydantic import Field, StrictFloat, StrictInt, model_validator

from eng_harness.calc import CalcInput, InputMeta, NotImplementedGap, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.kinds.column_design import ColumnSelection
from eng_harness.kinds.edit_cycle import NONEMPTY, Label
from eng_harness.workflows.model_edit_cycle._change_set import _M, BasisValue, LengthValue, _InputValue

__all__ = [
    "AXIAL_FLEXURE_ID",
    "BASIS_FIELDS",
    "MAX_AXIAL_ID",
    "REINF_LIMITS_ID",
    "ColumnLayout",
    "DemandsBody",
    "DemandsInput",
    "column_demands",
]

_FC = "materials.concrete_fc_MPa"
_FY = "materials.rebar_fy_MPa"
_K = "columns.effective_length_factor_ratio"
_RATIO_LIMIT = "limits.ratio_limit_ratio"
BASIS_FIELDS: tuple[str, ...] = (_FC, _FY, _K, _RATIO_LIMIT)
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""

# Ceiling of limits.ratio_limit_ratio: Verdict.ratio_limit default (04-tool-contract §5.1). Same source as
# structural_codes.inputs CheckInputs.ratio_limit `le` bound; structural_codes is not an allowed calc import.
_RATIO_LIMIT_MAX = Verdict.model_fields["ratio_limit"].default

MAX_AXIAL_ID = "aci318_14.22_4_2_1.max_axial_strength"
AXIAL_FLEXURE_ID = "aci318_14.22_4_1_1.axial_flexure_uniaxial"
REINF_LIMITS_ID = "aci318_14.10_6_1_1.longitudinal_reinforcement_limits"

ZERO = Cited(value=0, unit="1", source="Geometry: a bar area or cover distance is positive")
TWO = Cited(value=2, unit="1", source="Geometry: two opposite faces per direction (b and h), AF CS S1")
FOUR = Cited(value=4, unit="1", source="Geometry: four corner bars counted twice in 2*n_bars_b + 2*n_bars_h (AF CS S1)")
VERSION = Cited(value=1, unit="1", source="Calc version 1 of spec 0013 §4.4.2; a change of method is a new version")

_REFS = ("selection", "forces", "sections", "layouts", "combinations", "basis")
_RULE = "spec 0013 4.4.2"
_LOAD_COMBINATION = "load_combination"
_MM = "mm"
_MM2 = "mm2"
_RefDict = dict[Literal["$ref"], RefString]
_ItemValue = StrictInt | StrictFloat | _RefDict | Literal["tied"]


def _ref(kind: str) -> Any:
    return eng_param(ref_capable=True, ref_kinds={kind}, engineering_quantity=True)


class _Area(_InputValue):
    quantity = "area"


_AreaValue = Annotated[BasisValue | _Area, Field(discriminator="source")]


class _LayoutRow(_M):
    section: Label
    transverse_kind: Literal["tied", "spiral"]
    n_bars_b: Annotated[int, Field(ge=2)]  # spec 0013 section 4.3: at least 2 (AF section 3)
    n_bars_h: Annotated[int, Field(ge=2)]  # spec 0013 section 4.3
    A_bar: _AreaValue
    d_prime: LengthValue


class ColumnLayout(_M):
    """The layout answer (`ColumnLayoutRequest`, spec 0013 4.3), unique per section name."""

    sections: Annotated[list[_LayoutRow], Field(min_length=NONEMPTY)]

    @model_validator(mode="after")
    def _unique_sections(self) -> Self:
        names = [row.section for row in self.sections]
        if len(names) != len(set(names)):
            raise ValueError("duplicate section in layouts")
        return self


class DemandsInput(CalcInput):
    """Selection, member-end forces, sections, layouts, combinations and design basis, all by reference."""

    selection: ColumnSelection = _ref("harness.column_selection/1")
    forces: MemberEnd = _ref("forces.member_end/1")
    sections: Sections = _ref("model.sections/1")
    layouts: ColumnLayout = _ref("basis.engineer_input/1")
    combinations: Annotated[list[Label], Field(min_length=NONEMPTY)] = _ref("basis.engineer_input/1")
    basis: DesignBasis = _ref("basis.design_basis/1")


class _Subject(_M):
    kind: Literal["frame"]
    id: str
    station_mm: float | None = None
    case: str | None = None


class _CheckItem(_M):
    subject: _Subject
    inputs: dict[str, _ItemValue]


class _NotChecked(_M):
    frame_id: str
    code: Literal["FORCES_MISSING", "AXES_UNDECLARED", "SHAPE_NOT_CHECKED", "LAYOUT_MISSING"]
    gap: str | None = None


class DemandsBody(_M):
    """The payload of `harness.column_check_items/1` without `calc`, `draft` and `trace`."""

    items: dict[str, list[_CheckItem]]
    not_checked: list[_NotChecked]


def _refuse_basis(code: ErrorCode, path: str, why: str, **extra: Any) -> ContractError:
    return ContractError(
        code,
        f"basis field {path} {why}",
        field=f"basis.fields.{path}",
        hint=f"set and confirm {path} in the design basis",
        **extra,
    )


def _layout_basis_input_name(path: str) -> str:
    """Deterministic injective trace name for a layout basis path under the `basis_in_` prefix.

    Encode `_` as `_u` before encoding `.` as `_d` so paths such as `layout.values.bar` and
    `layout_values.bar` cannot collide (review r2). The prefix keeps names off the `col_*` step namespace.
    """
    return f"basis_in_{path.replace('_', '_u').replace('.', '_d')}"


def _read_basis(basis: DesignBasis, basis_id: str, trace: TraceBuilder) -> dict[str, _RefDict]:
    """E1: verify every §4.7 A basis field is present, confirmed and positive before emitting any reference."""
    refs: dict[str, _RefDict] = {}
    for path in BASIS_FIELDS:
        field = basis.fields.get(path)
        if field is None:
            raise _refuse_basis(ErrorCode.INVALID_ARGUMENT, path, "is missing (no default)")
        if not field.confirmed:
            raise _refuse_basis(ErrorCode.INVALID_ARGUMENT, path, "is not confirmed")
        if (exact := as_fraction(field.value)) is None:
            raise _refuse_basis(ErrorCode.INVALID_ARGUMENT, path, "is not a finite number")
        if exact <= Fraction():
            raise _refuse_basis(ErrorCode.INVALID_ARGUMENT, path, "must be positive")
        if path == _RATIO_LIMIT and exact > Fraction(str(_RATIO_LIMIT_MAX)):
            raise _refuse_basis(ErrorCode.INVALID_ARGUMENT, path, "must not exceed the contract default")
        trace.input(path.replace(".", "_"), float(exact), unit=field.unit, ref=f"{basis_id}#/fields/{path}")
        refs[path] = {"$ref": f"{basis_id}#/fields/{path}/value"}
    return refs


def _resolve_quantity(
    value: _AreaValue | LengthValue,
    target_unit: str,
    basis: DesignBasis,
    basis_id: str,
    trace: TraceBuilder,
    traced_basis: set[str],
) -> tuple[Fraction, list[str]]:
    """Resolve an engineer input or basis value to an exact `Fraction` in `target_unit` (> 0) and its trace uses."""
    if value.source == "input":
        exact = Fraction(value.value) * unit(value.unit).factor / unit(target_unit).factor
        if exact <= Fraction():
            raise ContractError(
                ErrorCode.OUT_OF_RANGE,
                "layout value must be positive",
                field="layouts",
                expected={"exclusive_min": int(ZERO.value), "unit": target_unit},
                received=value.value,
            )
        return exact, ["layouts"]
    path = value.path
    field = basis.fields.get(path)
    if field is None or not field.confirmed:
        raise _refuse_basis(ErrorCode.INVALID_ARGUMENT, path, "is missing or not confirmed")
    if field.unit is None or unit(field.unit).dimension != unit(target_unit).dimension:
        raise _refuse_basis(
            ErrorCode.UNIT_MISMATCH,
            path,
            f"must convert to {target_unit}",
            expected={"unit": target_unit},
            received=field.unit,
        )
    if (raw := as_fraction(field.value)) is None:
        raise _refuse_basis(ErrorCode.INVALID_ARGUMENT, path, "is not a finite number")
    if raw <= Fraction():
        raise _refuse_basis(ErrorCode.OUT_OF_RANGE, path, "must be positive", received=field.value)
    input_name = _layout_basis_input_name(path)
    if path not in traced_basis:
        traced_basis.add(path)
        trace.input(input_name, float(raw), unit=field.unit, ref=f"{basis_id}#/fields/{path}")
    return raw * unit(field.unit).factor / unit(target_unit).factor, [input_name]


def _to_finite_float(exact: Fraction, what: str) -> float:
    """Convert `exact` once to a positive finite binary64 float."""
    try:
        value = float(exact)
    except OverflowError as exc:
        raise ContractError(ErrorCode.OUT_OF_RANGE, f"{what} exceeds binary64 range", field="layouts") from exc
    if not math.isfinite(value) or value <= float(Fraction()):
        raise ContractError(
            ErrorCode.OUT_OF_RANGE, f"{what} cannot be represented as a positive float", field="layouts"
        )
    return value


@calc(
    id="harness.column_demands",
    version=int(VERSION.value),
    output_kind="harness.column_check_items/1",
    title="Column check items: demand sign, axes, length, layout and not-checked reasons",
    method_source="eng-harness spec 0013 §4.4.2 (E1 to E6)",
    verification="draft",
)
def column_demands(inp: DemandsInput, meta: InputMeta, trace: TraceBuilder) -> DemandsBody:
    """Build per-check items and `not_checked` entries for the selected columns (spec 0013 §4.4.2).

    Raises:
        ContractError: see module docstring.
        NotImplementedGap: spiral transverse reinforcement (`CK Q4`).
    """
    refs: dict[str, str] = {}
    for name in _REFS:
        if (ref := meta.refs.get(name)) is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"input {name} must be a record reference", field=name)
        refs[name] = ref.result_id

    trace.input("selection", len(inp.selection.columns), ref=refs["selection"])
    trace.input("forces", len(inp.forces.rows), ref=refs["forces"])
    trace.input("sections", len(inp.sections.frame_sections), ref=refs["sections"])
    trace.input("layouts", len(inp.layouts.sections), ref=refs["layouts"])
    trace.input("combinations", len(inp.combinations), ref=refs["combinations"])
    basis_refs = _read_basis(inp.basis, refs["basis"], trace)
    traced_basis = set(BASIS_FIELDS)

    trace.constant("c_half", TWO)
    trace.constant("c_corner", FOUR)

    sections = {row.name: row for row in inp.sections.frame_sections}
    layouts = {row.section: row for row in inp.layouts.sections}
    wanted_combos = set(inp.combinations)
    columns = sorted(inp.selection.columns, key=lambda col: col.frame_id)

    for col in columns:
        sec = sections.get(col.section)
        if sec is None:
            message = f"section {col.section} of column {col.frame_id} is not in the sections"
            raise ContractError(ErrorCode.INVALID_ARGUMENT, message, field="sections", received=col.section)
        if isinstance(sec.shape, Rectangular):
            layout = layouts.get(col.section)
            if layout is not None and layout.transverse_kind == "spiral":
                raise NotImplementedGap(
                    "spiral transverse reinforcement is not implemented (gap CK Q4)", evidence=("CK Q4",)
                )

    selected_ids = {col.frame_id for col in columns}
    rows_by_col: dict[str, list[MemberEndForce]] = {}
    for row in inp.forces.rows:
        if (
            row.member in selected_ids
            and row.case.case_type.value == _LOAD_COMBINATION
            and row.case.case in wanted_combos
        ):
            rows_by_col.setdefault(row.member, []).append(row)
    for member_rows in rows_by_col.values():
        member_rows.sort(key=lambda r: (r.member, r.case.case, r.station_mm, r.case.step or ""))

    max_axial_items: list[_CheckItem] = []
    axial_flexure_items: list[_CheckItem] = []
    reinf_limits_items: list[_CheckItem] = []
    not_checked: list[_NotChecked] = []

    fc_ref = basis_refs[_FC]
    fy_ref = basis_refs[_FY]
    k_ref = basis_refs[_K]
    ratio_ref = basis_refs[_RATIO_LIMIT]

    for col_idx, col in enumerate(columns):
        fid = col.frame_id
        c_tag = f"col_{col_idx}"
        shape = sections[col.section].shape
        # E2 before E6 (spec 0013 §4.4.2): missing combination rows are reported even when shape/layout exit.
        col_rows = rows_by_col.get(fid, [])
        seen_combos = {r.case.case for r in col_rows}
        if wanted_combos - seen_combos:
            not_checked.append(_NotChecked(frame_id=fid, code="FORCES_MISSING", gap=None))
        if not isinstance(shape, Rectangular):
            not_checked.append(_NotChecked(frame_id=fid, code="SHAPE_NOT_CHECKED", gap=None))
            continue
        layout = layouts.get(col.section)
        if layout is None:
            not_checked.append(_NotChecked(frame_id=fid, code="LAYOUT_MISSING", gap=None))
            continue

        a_bar_exact, a_bar_uses = _resolve_quantity(layout.A_bar, _MM2, inp.basis, refs["basis"], trace, traced_basis)
        d_prime_exact, d_prime_uses = _resolve_quantity(
            layout.d_prime, _MM, inp.basis, refs["basis"], trace, traced_basis
        )
        b_exact, h_exact = Fraction(shape.b_mm), Fraction(shape.h_mm)
        b_mm, h_mm = float(b_exact), float(h_exact)
        ag_mm2 = _to_finite_float(b_exact * h_exact, f"gross area of {fid}")
        a_bar_mm2 = _to_finite_float(a_bar_exact, f"bar area of {fid}")
        d_prime_mm = _to_finite_float(d_prime_exact, f"bar cover d_prime of {fid}")
        n_bars = int(TWO.value) * layout.n_bars_b + int(TWO.value) * layout.n_bars_h - int(FOUR.value)
        ast_mm2 = _to_finite_float(a_bar_exact * Fraction(n_bars), f"steel area of {fid}")
        lu_mm = float(col.length_mm)

        trace.step(
            f"{c_tag}_b_mm", b_mm, unit=_MM, formula="section.shape.b_mm", source=f"{_RULE} E5", uses=["sections"]
        )
        trace.step(
            f"{c_tag}_h_mm", h_mm, unit=_MM, formula="section.shape.h_mm", source=f"{_RULE} E5", uses=["sections"]
        )
        trace.step(
            f"{c_tag}_Ag_mm2",
            ag_mm2,
            unit=_MM2,
            formula="b_mm * h_mm",
            source=f"{_RULE} E5",
            uses=[f"{c_tag}_b_mm", f"{c_tag}_h_mm"],
        )
        trace.step(
            f"{c_tag}_n_bars_b",
            layout.n_bars_b,
            unit="1",
            formula="layout.n_bars_b",
            source=f"{_RULE} E5",
            uses=["layouts"],
        )
        trace.step(
            f"{c_tag}_n_bars_h",
            layout.n_bars_h,
            unit="1",
            formula="layout.n_bars_h",
            source=f"{_RULE} E5",
            uses=["layouts"],
        )
        trace.step(
            f"{c_tag}_A_bar_mm2",
            a_bar_mm2,
            unit=_MM2,
            formula="layout A_bar converted to mm2",
            source=f"{_RULE} E5",
            uses=a_bar_uses,
        )
        trace.step(
            f"{c_tag}_d_prime_mm",
            d_prime_mm,
            unit=_MM,
            formula="layout d_prime converted to mm",
            source=f"{_RULE} E5",
            uses=d_prime_uses,
        )
        trace.step(
            f"{c_tag}_Ast_mm2",
            ast_mm2,
            unit=_MM2,
            formula="A_bar_mm2 * (c_half * n_bars_b + c_half * n_bars_h - c_corner)",
            source=f"{_RULE} E5",
            uses=[f"{c_tag}_A_bar_mm2", f"{c_tag}_n_bars_b", f"{c_tag}_n_bars_h", "c_half", "c_corner"],
        )
        trace.step(
            f"{c_tag}_lu_mm", lu_mm, unit=_MM, formula="selection.length_mm", source=f"{_RULE} E4", uses=["selection"]
        )
        trace.step(
            f"{c_tag}_transverse_kind",
            "tied",
            unit=None,
            formula="tied (spirals NOT_IMPLEMENTED, spec 0013 §6)",
            source=f"{_RULE} E5",
            uses=["layouts"],
        )

        reinf_limits_items.append(
            _CheckItem(
                subject=_Subject(kind="frame", id=fid, station_mm=None, case=None),
                inputs={"Ag_mm2": ag_mm2, "Ast_mm2": ast_mm2, "ratio_limit": ratio_ref},
            )
        )

        symmetric = b_exact == h_exact and layout.n_bars_b == layout.n_bars_h
        if not symmetric:
            not_checked.append(_NotChecked(frame_id=fid, code="AXES_UNDECLARED", gap="CW-G9"))

        for row_idx, row in enumerate(col_rows):
            r_tag = f"{c_tag}_row_{row_idx}"
            pu_kn = float(-Fraction(row.P_kN))
            trace.step(
                f"{r_tag}_Pu_kN",
                pu_kn,
                unit="kN",
                formula="-P_kN (host_local/1: host axial tension positive; check axial compression positive)",
                source=f"{_RULE} E3",
                uses=["forces"],
            )
            subj = _Subject(kind="frame", id=fid, station_mm=row.station_mm, case=row.case.case)
            max_axial_items.append(
                _CheckItem(
                    subject=subj,
                    inputs={
                        "Pu_kN": pu_kn,
                        "b_mm": b_mm,
                        "h_mm": h_mm,
                        "Ast_mm2": ast_mm2,
                        "fc_MPa": fc_ref,
                        "fy_MPa": fy_ref,
                        "transverse_kind": "tied",
                        "k_factor": k_ref,
                        "lu_mm": lu_mm,
                        "ratio_limit": ratio_ref,
                    },
                )
            )
            if symmetric:
                abs_m2 = abs(Fraction(row.M2_kNm))
                abs_m3 = abs(Fraction(row.M3_kNm))
                # Spec 0013 section 4.4.2 E3 (amendment B-596 / OQ-Q98): default Mu=|M3|, Mu_other=|M2|;
                # when |M3|=0 and |M2|!=0 the sole nonzero magnitude goes in Mu (Mu_other=0).
                m2_only = abs_m3 == 0 and abs_m2 != 0
                if m2_only:
                    mu_knm = float(abs_m2)
                    mu_other_knm = 0.0
                    mu_formula = "|M2_kNm| when |M3_kNm|=0 and |M2_kNm|!=0 (amendment B-596 / OQ-Q98)"
                    mu_other_formula = "0 when |M3_kNm|=0 and |M2_kNm|!=0 (amendment B-596 / OQ-Q98)"
                else:
                    mu_knm = float(abs_m3)
                    mu_other_knm = float(abs_m2)
                    mu_formula = "|M3_kNm|"
                    mu_other_formula = "|M2_kNm|"
                trace.step(
                    f"{r_tag}_Mu_kNm",
                    mu_knm,
                    unit="kN.m",
                    formula=mu_formula,
                    source=f"{_RULE} E3",
                    uses=["forces"],
                )
                trace.step(
                    f"{r_tag}_Mu_other_kNm",
                    mu_other_knm,
                    unit="kN.m",
                    formula=mu_other_formula,
                    source=f"{_RULE} E3",
                    uses=["forces"],
                )
                axial_flexure_items.append(
                    _CheckItem(
                        subject=subj,
                        inputs={
                            "Pu_kN": pu_kn,
                            "Mu_kNm": mu_knm,
                            "Mu_other_kNm": mu_other_knm,
                            "b_mm": b_mm,
                            "h_mm": h_mm,
                            "d_prime_mm": d_prime_mm,
                            "n_bars_b": layout.n_bars_b,
                            "n_bars_h": layout.n_bars_h,
                            "A_bar_mm2": a_bar_mm2,
                            "fc_MPa": fc_ref,
                            "fy_MPa": fy_ref,
                            "transverse_kind": "tied",
                            "k_factor": k_ref,
                            "lu_mm": lu_mm,
                            "ratio_limit": ratio_ref,
                        },
                    )
                )

    not_checked.sort(key=lambda item: (item.frame_id, item.code))
    all_uses = ["selection", "forces", "sections", "layouts", "combinations"]
    trace.step(
        "max_axial_strength_items",
        len(max_axial_items),
        formula="one item per E2 row of a checked rectangular column",
        source=f"{_RULE} E2, E6",
        uses=all_uses,
    )
    trace.step(
        "axial_flexure_uniaxial_items",
        len(axial_flexure_items),
        formula="one item per E2 row of a symmetric checked rectangular column",
        source=f"{_RULE} E3, E6",
        uses=all_uses,
    )
    trace.step(
        "longitudinal_reinforcement_limits_items",
        len(reinf_limits_items),
        formula="one item per checked rectangular column",
        source=f"{_RULE} E5, E6",
        uses=["selection", "sections", "layouts"],
    )
    trace.step(
        "not_checked",
        len(not_checked),
        formula="selected columns with SHAPE_NOT_CHECKED, LAYOUT_MISSING, FORCES_MISSING or AXES_UNDECLARED",
        source=f"{_RULE} E2, E3, E6",
        uses=all_uses,
    )
    trace.output(
        "max_axial_strength_items",
        "axial_flexure_uniaxial_items",
        "longitudinal_reinforcement_limits_items",
        "not_checked",
    )
    return DemandsBody(
        items={
            MAX_AXIAL_ID: max_axial_items,
            AXIAL_FLEXURE_ID: axial_flexure_items,
            REINF_LIMITS_ID: reinf_limits_items,
        },
        not_checked=not_checked,
    )
