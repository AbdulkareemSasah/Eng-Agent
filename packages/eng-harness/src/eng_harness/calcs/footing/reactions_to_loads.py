"""Calc `harness.reactions_to_joint_loads` v1: ETABS reactions to SAFE joint loads (spec 0010 4.9 M1 to M4).

Purpose: match each footing subject to one SAFE point within `compare.length_mm` in plan, negate the transferred
pattern reactions into `harness.joint_loads/1` rows (null punching dimensions, SG-7), and list ETABS combinations to
add when SAFE has no combination of the same name with the same items.
Units: lengths in mm, forces in kN, moments in kN.m. Plan distances compared as exact squared `Fraction`s.
Errors: `ContractError` `INVALID_ARGUMENT` (basis field missing/unconfirmed/not a number; two or more SAFE points
within the tolerance: hint `DOUBLE_MATCH`; chosen case not an ETABS combination); `UNIT_MISMATCH` (basis field not
in mm); `OUT_OF_RANGE` (tolerance below zero). Engineering soft outcomes of §4.9 (unmatched subject `UNMATCHED`,
missing SAFE pattern `PATTERN_MISSING`, SAFE combination same name with other items `COMBO_CONFLICT`) are payload
`status` `NEEDS_ENGINEER` with those reason codes (spec 0003 4.2: engineering outcomes are payload statuses, never
exceptions; sibling footing calcs).
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from typing import Any, Literal

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.forces import JointReactions
from eng_contract.kinds.model import Combination, LoadSet
from eng_contract.params import eng_param
from pydantic import BaseModel, ConfigDict

from eng_harness._kinds import ModelPoints
from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.kinds.footing import FootingSubjects, JointLoadRow

_LENGTH = "compare.length_mm"
BASIS_FIELDS = (_LENGTH,)
"""The basis paths this calc reads (spec 0003 4.4); the workflow declares them required."""
ZERO_MM = Cited(value=0, unit="mm", source="eng-harness spec 0003 §4.4: compare.length_mm is >= 0")
VERSION = Cited(value=1, unit="1", source="Calc version 1 of spec 0010 4.9; a change of method is a new version")
_RULE = "spec 0010 4.9"
_PATTERN_CASE_TYPES = frozenset({"load_pattern", "load_case"})
"""Case types transferred as column-load patterns (spec 0010 4.9 M1)."""
_STATUS_OK = "OK"
_STATUS_NEEDS_ENGINEER = "NEEDS_ENGINEER"


class ReactionsInput(CalcInput):
    """ETABS reactions and load set, footing subjects, SAFE points and load set, engineer cases, and the basis."""

    reactions: JointReactions = eng_param(
        ref_capable=True, ref_kinds={"forces.joint_reactions/1"}, engineering_quantity=True
    )
    subjects: FootingSubjects = eng_param(
        ref_capable=True, ref_kinds={"harness.footing_subjects/1"}, engineering_quantity=True
    )
    etabs_load_set: LoadSet = eng_param(ref_capable=True, ref_kinds={"model.load_set/1"}, engineering_quantity=True)
    safe_points: ModelPoints = eng_param(
        ref_capable=True, ref_kinds={"harness.model_points/1"}, engineering_quantity=True
    )
    safe_load_set: LoadSet = eng_param(ref_capable=True, ref_kinds={"model.load_set/1"}, engineering_quantity=True)
    cases: list[str] = eng_param(ref_capable=True, ref_kinds={"basis.engineer_input/1"}, engineering_quantity=True)
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)


class ReactionsBody(BaseModel):
    """Body of the calc result: joint loads plus combinations to add (spec 0010 4.9 step 2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    axes: Literal["global"] = "global"
    loads: list[JointLoadRow]
    combinations_to_add: list[Combination]
    status: str
    reason: str | None


def _refuse(code: ErrorCode, message: str, *, field: str, hint: str | None = None, **fields: Any) -> ContractError:
    return ContractError(code, message, field=field, hint=hint, **fields)


def _soft(trace: TraceBuilder, reason: str, *, uses: list[str]) -> ReactionsBody:
    """Payload `NEEDS_ENGINEER` with empty loads (spec 0010 4.9; spec 0003 4.2)."""
    trace.step(
        "status",
        _STATUS_NEEDS_ENGINEER,
        formula=f"engineering soft outcome {reason}",
        source=f"{_RULE}",
        uses=uses,
    )
    trace.output("status")
    return ReactionsBody(
        axes="global",
        loads=[],
        combinations_to_add=[],
        status=_STATUS_NEEDS_ENGINEER,
        reason=reason,
    )


def _length(basis: DesignBasis, basis_id: str, trace: TraceBuilder) -> Fraction:
    """Spec 0003 4.4: `compare.length_mm` present, confirmed, in mm and >= 0."""
    field = basis.fields.get(_LENGTH)
    if field is None or not field.confirmed:
        raise _refuse(
            ErrorCode.INVALID_ARGUMENT,
            f"basis field {_LENGTH} is missing or not confirmed",
            field="basis",
            hint=f"confirm {_LENGTH}",
        )
    if field.unit != ZERO_MM.unit:
        raise _refuse(
            ErrorCode.UNIT_MISMATCH,
            f"basis field {_LENGTH} must be in mm",
            field="basis",
            expected={"unit": ZERO_MM.unit},
            received=field.unit,
        )
    value = as_fraction(field.value)
    if value is None:
        raise _refuse(ErrorCode.INVALID_ARGUMENT, f"basis field {_LENGTH} is not a number", field="basis")
    if value < Fraction(ZERO_MM.value):
        raise _refuse(
            ErrorCode.OUT_OF_RANGE,
            f"basis field {_LENGTH} is below zero",
            field="basis",
            expected={"min": ZERO_MM.value},
            received=field.value,
        )
    trace.input("compare_length", float(value), unit=ZERO_MM.unit, ref=f"{basis_id}#/fields/{_LENGTH}")
    return value


def _plan_sq(x1: float, y1: float, x2: float, y2: float) -> Fraction:
    """Exact squared plan distance in millimetres."""
    dx = Fraction(x1) - Fraction(x2)
    dy = Fraction(y1) - Fraction(y2)
    return dx * dx + dy * dy


def _match_point(
    subject_x: float,
    subject_y: float,
    points: ModelPoints,
    tolerance_sq: Fraction,
    subject_joint: str,
) -> str | None:
    """The name of the one SAFE point within the tolerance, or None if unmatched (spec 0010 4.9 M2).

    Two or more matches raise `INVALID_ARGUMENT` (hint `DOUBLE_MATCH`).
    """
    hits = [
        point.name for point in points.points if _plan_sq(subject_x, subject_y, point.x_mm, point.y_mm) <= tolerance_sq
    ]
    if not hits:
        return None
    if len(hits) > 1:
        raise _refuse(
            ErrorCode.INVALID_ARGUMENT,
            f"subject joint {subject_joint} matches more than one SAFE point within compare.length_mm",
            field="points",
            hint="DOUBLE_MATCH",
            received=sorted(hits),
        )
    return hits[0]


def _transferred_patterns(etabs: LoadSet, cases: Sequence[str]) -> list[str]:
    """M1: load_pattern and load_case item names of the chosen combinations, sorted uniquely."""
    by_name = {combo.name: combo for combo in etabs.combinations}
    names: set[str] = set()
    for case_name in cases:
        combo = by_name.get(case_name)
        if combo is None:
            raise _refuse(
                ErrorCode.INVALID_ARGUMENT,
                f"chosen case {case_name} is not an ETABS combination",
                field="cases",
                received=case_name,
            )
        for item in combo.items:
            if item.case.case_type.value in _PATTERN_CASE_TYPES:
                names.add(item.case.case)
    return sorted(names)


def _combo_items_key(combo: Combination) -> tuple[tuple[str, str, float], ...]:
    """Comparable identity of a combination's items (name, case_type, scale), sorted."""
    return tuple(sorted((item.case.case, item.case.case_type.value, float(item.scale_ratio)) for item in combo.items))


def _combinations_to_add(etabs: LoadSet, safe: LoadSet, cases: Sequence[str]) -> tuple[list[Combination], str | None]:
    """ETABS combinations to add on SAFE; same name with other items is COMBO_CONFLICT (spec 0010 4.9)."""
    safe_by_name = {combo.name: combo for combo in safe.combinations}
    etabs_by_name = {combo.name: combo for combo in etabs.combinations}
    to_add: list[Combination] = []
    for case_name in cases:
        etabs_combo = etabs_by_name[case_name]
        existing = safe_by_name.get(case_name)
        if existing is None:
            to_add.append(etabs_combo)
            continue
        if _combo_items_key(existing) != _combo_items_key(etabs_combo):
            return [], "COMBO_CONFLICT"
    return to_add, None


@calc(
    id="harness.reactions_to_joint_loads",
    version=int(VERSION.value),
    output_kind="harness.reactions_to_joint_loads/1",
    title="ETABS reactions to SAFE joint loads and combinations to add",
    method_source="eng-harness spec 0010 §4.9 (M1 to M4)",
    verification="draft",
)
def reactions_to_joint_loads(inp: ReactionsInput, meta: InputMeta, trace: TraceBuilder) -> ReactionsBody:
    """Match subjects to SAFE points, negate transferred reactions, and list combinations to add.

    Raises:
        ContractError: invalid basis, unknown chosen case, or dual SAFE-point match (see the module docstring).
    """
    basis_id = meta.refs["basis"].result_id
    tolerance = _length(inp.basis, basis_id, trace)
    tolerance_sq = tolerance * tolerance
    trace.constant("zero_mm", ZERO_MM)
    patterns = _transferred_patterns(inp.etabs_load_set, inp.cases)
    trace.input("chosen_cases", len(inp.cases), ref=meta.refs["cases"].result_id)
    trace.step(
        "transferred_patterns",
        len(patterns),
        formula="load_pattern and load_case items of the chosen combinations",
        source=f"{_RULE} M1",
        uses=["chosen_cases"],
    )
    safe_pattern_names = {pattern.name for pattern in inp.safe_load_set.patterns}
    missing = [name for name in patterns if name not in safe_pattern_names]
    if missing:
        trace.step(
            "pattern_missing",
            missing[0],
            formula="SAFE load set has no pattern of the transferred name",
            source=f"{_RULE} M4",
            uses=["transferred_patterns"],
        )
        return _soft(trace, "PATTERN_MISSING", uses=["pattern_missing"])
    joint_to_point: dict[str, str] = {}
    for subject in inp.subjects.subjects:
        matched = _match_point(subject.x_mm, subject.y_mm, inp.safe_points, tolerance_sq, subject.joint)
        if matched is None:
            trace.step(
                "unmatched_subject",
                subject.joint,
                formula="no SAFE point within compare.length_mm in plan",
                source=f"{_RULE} M2",
                uses=["compare_length"],
            )
            return _soft(trace, "UNMATCHED", uses=["unmatched_subject"])
        joint_to_point[subject.joint] = matched
    trace.step(
        "matched_subjects",
        len(joint_to_point),
        formula="one SAFE point within compare.length_mm in plan per subject",
        source=f"{_RULE} M2",
        uses=["compare_length"],
    )
    pattern_set = set(patterns)
    loads: list[JointLoadRow] = []
    for row in inp.reactions.rows:
        if row.case.case not in pattern_set:
            continue
        if row.case.case_type.value not in _PATTERN_CASE_TYPES:
            continue
        point = joint_to_point.get(row.joint)
        if point is None:
            continue
        loads.append(
            JointLoadRow(
                joint=point,
                pattern=row.case.case,
                FX_kN=-row.FX_kN,
                FY_kN=-row.FY_kN,
                FZ_kN=-row.FZ_kN,
                MX_kNm=-row.MX_kNm,
                MY_kNm=-row.MY_kNm,
                MZ_kNm=-row.MZ_kNm,
                punch_x_mm=None,
                punch_y_mm=None,
            )
        )
    loads.sort(key=lambda load: (load.joint, load.pattern))
    trace.step(
        "loads",
        len(loads),
        formula="negatives of the transferred reactions; punch dimensions null (SG-7)",
        source=f"{_RULE} M3",
        uses=["transferred_patterns", "matched_subjects"],
    )
    to_add, combo_reason = _combinations_to_add(inp.etabs_load_set, inp.safe_load_set, inp.cases)
    if combo_reason is not None:
        trace.step(
            "combo_conflict",
            combo_reason,
            formula="SAFE combination of the same name has other items; never replaced",
            source=f"{_RULE} step 2",
            uses=["chosen_cases"],
        )
        return _soft(trace, combo_reason, uses=["combo_conflict"])
    trace.step(
        "combinations_to_add",
        len(to_add),
        formula="chosen ETABS combinations absent from SAFE, or equal; never replace differing items",
        source=f"{_RULE} step 2",
        uses=["chosen_cases"],
    )
    trace.step(
        "status",
        _STATUS_OK,
        formula="no soft outcome of M2, M4 or step 2",
        source=f"{_RULE}",
        uses=["loads", "combinations_to_add"],
    )
    trace.output("loads", "combinations_to_add", "status")
    return ReactionsBody(
        axes="global",
        loads=loads,
        combinations_to_add=to_add,
        status=_STATUS_OK,
        reason=None,
    )
