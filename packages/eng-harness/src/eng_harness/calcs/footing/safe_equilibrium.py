"""Calc `harness.safe_equilibrium` v1: applied loads vs base reactions per pattern (spec 0010 4.9 step 6).

Purpose: for each transferred pattern, compare the magnitude of the summed applied `FZ` against the magnitude of the
base-reaction `FZ` within `checks.equilibrium_relative_tolerance_ratio`; self-weight patterns
(`self_weight_ratio > 0` in the SAFE load set) are `NOT_COMPARED`.
Units: forces in kN; the tolerance is dimensionless. Comparisons use exact `Fraction`s of the stored values.
Errors: `ContractError` `INVALID_ARGUMENT` (basis field missing, unconfirmed or not a number);
`UNIT_MISMATCH` (basis field not unit `1`); `OUT_OF_RANGE` (tolerance below zero).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Literal

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.model import LoadSet
from eng_contract.params import eng_param
from pydantic import BaseModel, ConfigDict, Field

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.kinds.footing import BaseReactions, JointLoads, PatternRow

_TOLERANCE = "checks.equilibrium_relative_tolerance_ratio"
BASIS_FIELDS = (_TOLERANCE,)
"""The basis paths this calc reads (spec 0003 4.4); the workflow declares them required."""
ZERO = Cited(value=0, unit="1", source="eng-harness spec 0010 §4.9: relative tolerance is >= 0")
VERSION = Cited(value=1, unit="1", source="Calc version 1 of spec 0010 4.9; a change of method is a new version")
_RULE = "spec 0010 4.9 step 6"


class EquilibriumInput(CalcInput):
    """Applied joint loads, base reactions, the SAFE load set (self-weight flags) and the basis."""

    loads: JointLoads = eng_param(ref_capable=True, ref_kinds={"harness.joint_loads/1"}, engineering_quantity=True)
    base_reactions: BaseReactions = eng_param(
        ref_capable=True, ref_kinds={"harness.base_reactions/1"}, engineering_quantity=True
    )
    safe_load_set: LoadSet = eng_param(ref_capable=True, ref_kinds={"model.load_set/1"}, engineering_quantity=True)
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)


class EquilibriumBody(BaseModel):
    """Payload of `harness.safe_equilibrium/1` without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tolerance: float = Field(ge=ZERO.value)
    patterns: list[PatternRow]


def _refuse(code: ErrorCode, message: str, **fields: Any) -> ContractError:
    return ContractError(code, message, field="basis", **fields)


def _tolerance(basis: DesignBasis, basis_id: str, trace: TraceBuilder) -> Fraction:
    """Spec 0003 4.4: relative tolerance present, confirmed, unit `1`, >= 0."""
    field = basis.fields.get(_TOLERANCE)
    if field is None or not field.confirmed:
        raise _refuse(
            ErrorCode.INVALID_ARGUMENT,
            f"basis field {_TOLERANCE} is missing or not confirmed",
            hint=f"confirm {_TOLERANCE}",
        )
    if field.unit != ZERO.unit:
        raise _refuse(
            ErrorCode.UNIT_MISMATCH,
            f"basis field {_TOLERANCE} must have unit 1",
            expected={"unit": ZERO.unit},
            received=field.unit,
        )
    value = as_fraction(field.value)
    if value is None:
        raise _refuse(ErrorCode.INVALID_ARGUMENT, f"basis field {_TOLERANCE} is not a number")
    if value < Fraction(ZERO.value):
        raise _refuse(
            ErrorCode.OUT_OF_RANGE,
            f"basis field {_TOLERANCE} is below zero",
            expected={"min": ZERO.value},
            received=field.value,
        )
    trace.input("equilibrium_tolerance", float(value), unit=ZERO.unit, ref=f"{basis_id}#/fields/{_TOLERANCE}")
    return value


@calc(
    id="harness.safe_equilibrium",
    version=int(VERSION.value),
    output_kind="harness.safe_equilibrium/1",
    title="SAFE equilibrium: applied FZ vs base reaction FZ per pattern",
    method_source="eng-harness spec 0010 §4.9 step 6",
    verification="draft",
)
def safe_equilibrium(inp: EquilibriumInput, meta: InputMeta, trace: TraceBuilder) -> EquilibriumBody:
    """Compare applied and base-reaction FZ magnitudes per transferred pattern.

    Raises:
        ContractError: see the module docstring.
    """
    basis_id = meta.refs["basis"].result_id
    tol = _tolerance(inp.basis, basis_id, trace)
    trace.constant("zero_tolerance", ZERO)
    self_weight = {
        pattern.name: Fraction(pattern.self_weight_ratio) > Fraction(ZERO.value)
        for pattern in inp.safe_load_set.patterns
    }
    applied: dict[str, Fraction] = {}
    for load in inp.loads.loads:
        # harness.joint_loads/1 (spec 0008 §4.3): wire name FZ_kN on the calc-facing footing kind
        applied[load.pattern] = applied.get(load.pattern, Fraction()) + Fraction(load.FZ_kN)
    reactions: dict[str, Fraction] = {}
    for row in inp.base_reactions.rows:
        # harness.base_reactions/1 (spec 0008 §4.6): case is HarnessCaseRef; wire name FZ_kN
        reactions[row.case.case] = reactions.get(row.case.case, Fraction()) + Fraction(row.FZ_kN)
    patterns = sorted(set(applied) | set(reactions))
    trace.input("load_rows", len(inp.loads.loads), ref=meta.refs["loads"].result_id)
    trace.input("reaction_rows", len(inp.base_reactions.rows), ref=meta.refs["base_reactions"].result_id)
    rows: list[PatternRow] = []
    for name in patterns:
        a = applied.get(name, Fraction())
        r = reactions.get(name, Fraction())
        is_self = self_weight.get(name, False)
        if is_self:
            status: Literal["PASS", "FAIL", "NOT_COMPARED"] = "NOT_COMPARED"
        else:
            # | |R| - |A| | <= tol * |A|  (spec 0010 4.9 step 6, magnitudes; SAFE Q6)
            abs_a = abs(a)
            abs_r = abs(r)
            limit = tol * abs_a
            status = "PASS" if abs(abs_r - abs_a) <= limit else "FAIL"
        rows.append(
            PatternRow(
                pattern=name,
                self_weight=is_self,
                applied_kN=float(a),
                reaction_kN=float(r),
                status=status,
            )
        )
    trace.step(
        "patterns",
        len(rows),
        formula="NOT_COMPARED if self_weight_ratio > 0; else PASS when ||R|-|A|| <= tol*|A|, else FAIL",
        source=_RULE,
        uses=["equilibrium_tolerance", "load_rows", "reaction_rows"],
    )
    trace.output("patterns")
    return EquilibriumBody(tolerance=float(tol), patterns=rows)
