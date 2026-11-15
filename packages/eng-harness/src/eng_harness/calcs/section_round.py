"""Calc 5, section size rounding `harness.section_round` v1 (spec 0003 4.10, rules N1 to N4).

Purpose: 11 §4: a new section size is the output of this calc or an engineer input, never a decision. The required
size is rounded up to the smallest multiple of the basis increment that is not below it.
Inputs: `required` (a length in mm > 0, by reference to a calc output or an engineer input) and `basis`
(`modeling.section_increment_mm`, `modeling.section_rounding`). No `compare.*` field is read.
Units: mm; exact fractions of the stored binary values, the size converted to float once (N2); no allowance (Q14).
Errors: `ContractError` `INVALID_ARGUMENT` (with `field`) for a basis given without a record and for a basis field
missing, unconfirmed or of the wrong type; `OUT_OF_RANGE` for an increment not > 0 (the bound of `required` is applied
by `validate_input`); `NotImplementedGap` CG-2 for a rule other than `up` (N4).
"""

from fractions import Fraction
from math import ceil
from typing import Any

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import BasisField, DesignBasis
from eng_contract.params import eng_param
from eng_contract.quantity import Quantity
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict

from eng_harness.calc import CalcInput, InputMeta, NotImplementedGap, TraceBuilder, calc

__all__ = ["BASIS_FIELDS", "RoundBody", "RoundInput", "section_round"]

INCREMENT, RULE = "modeling.section_increment_mm", "modeling.section_rounding"
BASIS_FIELDS = (INCREMENT, RULE)
"""The basis paths this calc reads (`CalcInfo.basis_fields`); the workflow declares them required."""
UP = "up"
"""The only rule of v1 (N4); any other is gap CG-2."""
LOWER = Cited(value=0, unit="mm", source="eng-harness spec 0003 §4.4 and §5: required and increment are > 0")
"""The exclusive lower bound of `required` and of `modeling.section_increment_mm`."""
_INC = INCREMENT.replace(".", "_")


class RoundInput(CalcInput):
    """The required size and the design basis."""

    required: Quantity = eng_param(
        unit=LOWER.unit, gt=LOWER.value, bounds_source=LOWER.source, ref_capable=True, engineering_quantity=True
    )
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)


class RoundBody(BaseModel):
    """The `harness.section_size/1` payload without `calc`, `draft` and `trace` (the framework adds them)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    required: Quantity
    increment: Quantity
    multiple: int
    size: Quantity
    status: VerdictStatus


def _refuse(path: str, why: str, code: ErrorCode = ErrorCode.INVALID_ARGUMENT, **fields: Any) -> ContractError:
    hint = f"set and confirm {path} in the design basis"
    return ContractError(code, f"basis field {path} {why}", field=f"basis.fields.{path}", hint=hint, **fields)


def _field(basis: DesignBasis, path: str, basis_id: str, trace: TraceBuilder) -> BasisField:
    """Spec 4.4: the field present and confirmed (no default), recorded with its basis pointer."""
    field = basis.fields.get(path)
    if field is None:
        raise _refuse(path, "is missing (no default)")
    if not field.confirmed:
        raise _refuse(path, "is not confirmed")
    trace.input(path.replace(".", "_"), field.value, unit=field.unit, ref=f"{basis_id}#/fields/{path}")
    return field


@calc(
    id="harness.section_round",
    version=1,
    output_kind="harness.section_size/1",
    title="Section size rounded up to the basis increment",
    method_source="eng-harness spec 0003 §4.10 (N1 to N4); 13 §2 modeling; 11 §4",
    verification="draft",
)
def section_round(inp: RoundInput, meta: InputMeta, trace: TraceBuilder) -> RoundBody:
    """Check the rule (N4) and the increment, then n = ceil(r / i) and size = n x i on exact fractions (N1 to N3)."""
    if (basis := meta.refs.get("basis")) is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "the basis must be a record reference", field="basis")
    rule = _field(inp.basis, RULE, basis.result_id, trace)
    if rule.unit is not None:
        raise _refuse(RULE, f"must have no unit, not {rule.unit}")
    if not isinstance(rule.value, str):
        raise _refuse(RULE, "must be the name of a rule")
    if rule.value != UP:
        message = f"the section rounding rule {rule.value!r} is not implemented (gap CG-2)"
        raise NotImplementedGap(message, evidence=("CG-2",))
    value = _field(inp.basis, INCREMENT, basis.result_id, trace).value  # its unit is mm: `DesignBasis` checks it
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _refuse(INCREMENT, "must be a number")
    if value <= LOWER.value:
        bound = {"exclusive_min": LOWER.value, "unit": LOWER.unit}
        raise _refuse(INCREMENT, "must be > 0", ErrorCode.OUT_OF_RANGE, expected=bound, received=value)
    ref = meta.refs.get("required")
    trace.input("required", inp.required.value, unit=LOWER.unit, ref=None if ref is None else ref.result_id)
    r, i = Fraction(inp.required.value), Fraction(value)
    n = ceil(r / i)  # Fraction.__ceil__: integer arithmetic, exact
    size = float(n * i)
    trace.step("ratio", float(r / i), formula="r / i on exact fractions", source="§4.10 N1", uses=["required", _INC])
    trace.step("multiple", n, formula="n = ceil(r / i)", source="§4.10 N1", uses=["ratio"])
    trace.step(
        "size", size, formula="n x i, to float once", source="§4.10 N2", uses=["multiple", _INC], unit=LOWER.unit
    )
    trace.output("size")
    return RoundBody(
        required=inp.required,
        increment=Quantity(value=float(value), unit=LOWER.unit),
        multiple=n,
        size=Quantity(value=size, unit=LOWER.unit),
        status=VerdictStatus.PASS,
    )
