"""Trial square footing dimensions (spec 0010 §4.4.2, P0 to P6).

Reactions are global FZ in kN, pressure is in kPa and dimensions are in mm. The sizing comparisons use exact
fractions of the stored numbers. Contract errors reject unusable basis fields. FG-1 is a NotImplementedGap.
"""

from fractions import Fraction
from math import ceil, isqrt

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import BasisField, DesignBasis
from eng_contract.kinds.forces import JointReactions
from eng_contract.params import eng_param
from pydantic import BaseModel, ConfigDict

from eng_harness.calc import CalcInput, InputMeta, NotImplementedGap, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.kinds.footing import DimRow, FootingSubjects

MM_PER_M = Cited(value=1000, unit="1", source="SI prefix milli: mm per m (eng-contract §4.7.3; BP §4.1)")
ZERO = Cited(value=0, unit="1", source="Spec 0010 §4.4.2 P1/P2 and BP §3 physical bounds")
_METHOD = "eng-harness spec 0010 §4.4.2"
_QUANTITIES = (
    ("foundation.allowable_bearing_pressure_kPa", "kPa", True),
    ("foundation.soil_unit_weight_kN_m3", "kN/m3", True),
    ("foundation.soil_depth_above_footing_mm", "mm", False),
    ("foundation.surcharge_kPa", "kPa", False),
    ("materials.concrete_unit_weight_kN_m3", "kN/m3", True),
    ("foundation.min_depth_mm", "mm", True),
    ("foundation.min_plan_dimension_mm", "mm", True),
    ("foundation.max_plan_dimension_mm", "mm", True),
    ("foundation.plan_increment_mm", "mm", True),
    ("reinforcement.max_spacing_mm", "mm", True),
)
_KIND = "foundation.allowable_bearing_kind"
_SHAPE = "foundation.plan_shape"
BASIS_FIELDS = (*(path for path, _, _ in _QUANTITIES), _KIND, _SHAPE)
"""The twelve required design-basis paths from spec 0010 §4.4.2."""


class PlanSizeInput(CalcInput):
    """The subjects, reactions, engineer's service case list and basis, all by reference."""

    subjects: FootingSubjects = eng_param(
        ref_capable=True, ref_kinds={"harness.footing_subjects/1"}, engineering_quantity=True
    )
    reactions: JointReactions = eng_param(
        ref_capable=True, ref_kinds={"forces.joint_reactions/1"}, engineering_quantity=True
    )
    service_cases: list[str] = eng_param(
        ref_capable=True, ref_kinds={"basis.engineer_input/1"}, engineering_quantity=True
    )
    basis: DesignBasis = eng_param(ref_capable=True, ref_kinds={"basis.design_basis/1"}, engineering_quantity=True)


class PlanSizeBody(BaseModel):
    """The body of `harness.footing_dims/1` before the calc port attaches metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    footings: list[DimRow]


def _basis_field(basis: DesignBasis, path: str, unit: str | None) -> BasisField:
    field = basis.fields.get(path)
    if field is None or not field.confirmed:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            f"basis field {path} is missing or not confirmed",
            field="basis",
            hint=f"confirm {path}",
        )
    if field.unit != unit:
        raise ContractError(
            ErrorCode.UNIT_MISMATCH,
            f"basis field {path} has the wrong unit",
            field="basis",
            expected={"unit": unit},
            received=field.unit,
        )
    return field


def _choice(basis: DesignBasis, path: str, choices: tuple[str, ...], ref: str, trace: TraceBuilder) -> str:
    value = _basis_field(basis, path, None).value
    if not isinstance(value, str) or value not in choices:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            f"basis field {path} must be one of {', '.join(choices)}",
            field="basis",
            hint=f"choose one of {', '.join(choices)}",
        )
    trace.input(path.rpartition(".")[2], value, ref=f"{ref}#/fields/{path}/value")
    return value


def _read_quantities(basis: DesignBasis, ref: str, trace: TraceBuilder) -> dict[str, Fraction]:
    quantities: dict[str, Fraction] = {}
    for path, unit, positive in _QUANTITIES:
        raw = _basis_field(basis, path, unit).value
        number = as_fraction(raw)
        if number is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, f"basis field {path} must be a finite number", field="basis"
            )
        if number < ZERO.value or (positive and number == ZERO.value):
            bound = "gt" if positive else "min"
            raise ContractError(
                ErrorCode.OUT_OF_RANGE,
                f"basis field {path} is outside its physical bounds",
                field="basis",
                expected={bound: ZERO.value},
                received=raw,
            )
        name = path.rpartition(".")[2]
        trace.input(name, raw, unit=unit, ref=f"{ref}#/fields/{path}/value")
        quantities[name] = number
    return quantities


def _service_loads(reactions: JointReactions, service_cases: list[str]) -> dict[str, list[float]]:
    """Keep each selected reaction, including separate envelope rows, for P1 and P3."""
    names = frozenset(service_cases)
    loads: dict[str, list[float]] = {}
    for row in reactions.rows:
        if row.case.case in names:
            loads.setdefault(row.joint, []).append(row.FZ_kN)
    return loads


def _engineering_reason(kind: str, loads: list[float], q_net: Fraction) -> str | None:
    if kind == "net":
        return "NET_ALLOWABLE"
    if not loads:
        return "NO_SERVICE_LOAD"
    if min(loads) <= ZERO.value:
        return "UPLIFT"
    if q_net <= ZERO.value:
        return "OVERBURDEN"
    return None


def _required_length(area_mm2: Fraction, increment: Fraction, minimum: Fraction) -> Fraction:
    """P4: start at the greater floor of the area root and minimum, then confirm both inequalities."""
    steps_sq = area_mm2 / (increment * increment)
    floor_area = isqrt(steps_sq.numerator // steps_sq.denominator)
    length = max(floor_area, minimum // increment) * increment
    if length * length < area_mm2 or length < minimum:
        length += increment
    return length


def _plan_row(
    footing_id: str,
    loads: list[float],
    kind: str,
    q_net: Fraction,
    quantities: dict[str, Fraction],
    trace: TraceBuilder,
    prefix: str,
) -> DimRow:
    increment = quantities["plan_increment_mm"]
    minimum = quantities["min_plan_dimension_mm"]
    maximum = quantities["max_plan_dimension_mm"]
    reason = _engineering_reason(kind, loads, q_net)
    load_input = f"{prefix}_fz"
    uses = [load_input, "allowable_bearing_kind", "q_net_kPa", "plan_increment_mm", "min_plan_dimension_mm"]
    status = "NEEDS_ENGINEER"
    capped = False
    if reason is not None:
        size = ceil(minimum / increment) * increment
        formula = "ceil(min_plan / increment) * increment"
        rule = "P6"
    else:
        area = Fraction(max(loads)) / q_net * Fraction(MM_PER_M.value) * Fraction(MM_PER_M.value)
        area_step = f"{prefix}_required_area_mm2"
        trace.step(
            area_step,
            str(area),
            unit="mm2",
            formula="max(service FZ) / q_net * mm_per_m^2 (exact fraction)",
            source=f"{_METHOD} P3",
            uses=[load_input, "q_net_kPa", "mm_per_m"],
        )
        size = _required_length(area, increment, minimum)
        capped = size > maximum
        if capped:
            size = (maximum // increment) * increment
        status = "LIMIT_REACHED" if capped else "OK"
        formula = "least grid size satisfying area and minimum, capped at floor(max_plan / increment) * increment"
        rule = "P4/P5"
        uses.extend([area_step, "max_plan_dimension_mm"])
    name = f"{prefix}_side_mm"
    trace.step(name, float(size), unit="mm", formula=formula, source=f"{_METHOD} {rule}", uses=uses)
    trace.output(name)
    return DimRow(
        id=footing_id,
        Lx_mm=float(size),
        Ly_mm=float(size),
        h_mm=float(quantities["min_depth_mm"]),
        s_mm=float(quantities["max_spacing_mm"]),
        source="calc",
        plan_at_max=capped,
        depth_at_max=False,
        spacing_at_min=False,
        status=status,
        reason=reason,
    )


@calc(
    id="harness.footing_plan_size",
    version=1,
    output_kind="harness.footing_dims/1",
    title="Trial plan size for square isolated footings",
    method_source=f"{_METHOD} (P0 to P6)",
    verification="draft",
)
def footing_plan_size(inp: PlanSizeInput, meta: InputMeta, trace: TraceBuilder) -> PlanSizeBody:
    """Size each subject from its service compression and available gross bearing pressure."""
    basis_ref = meta.refs["basis"].result_id
    shape = _choice(inp.basis, _SHAPE, ("square", "equal_projection"), basis_ref, trace)
    if shape != "square":
        raise NotImplementedGap("FG-1: only square footings have a plan sizing method", evidence=("FG-1",))
    kind = _choice(inp.basis, _KIND, ("gross", "net"), basis_ref, trace)
    values = _read_quantities(inp.basis, basis_ref, trace)
    increment = values["plan_increment_mm"]
    if values["max_plan_dimension_mm"] < increment:
        raise ContractError(
            ErrorCode.OUT_OF_RANGE,
            "foundation.max_plan_dimension_mm is below foundation.plan_increment_mm",
            field="basis",
            expected={"min": float(increment)},
            received=float(values["max_plan_dimension_mm"]),
        )

    trace.constant("mm_per_m", MM_PER_M)
    trace.constant("zero", ZERO)
    scale = Fraction(MM_PER_M.value)
    weight = (
        values["min_depth_mm"] * values["concrete_unit_weight_kN_m3"]
        + values["soil_depth_above_footing_mm"] * values["soil_unit_weight_kN_m3"]
    ) / scale + values["surcharge_kPa"]
    q_net = values["allowable_bearing_pressure_kPa"] - weight
    trace.step(
        "overburden_kPa",
        str(weight),
        unit="kPa",
        formula="(min_depth * gamma_c + soil_depth * gamma_s) / mm_per_m + surcharge",
        source=f"{_METHOD} P2 (BP S3)",
        uses=[
            "min_depth_mm",
            "concrete_unit_weight_kN_m3",
            "soil_depth_above_footing_mm",
            "soil_unit_weight_kN_m3",
            "mm_per_m",
            "surcharge_kPa",
        ],
    )
    trace.step(
        "q_net_kPa",
        str(q_net),
        unit="kPa",
        formula="allowable_bearing_pressure - overburden",
        source=f"{_METHOD} P2",
        uses=["allowable_bearing_pressure_kPa", "overburden_kPa"],
    )
    trace.input(
        "service_cases",
        list(inp.service_cases),
        ref=f"{meta.refs['service_cases'].result_id}#/fields/service_cases/value",
    )
    loads = _service_loads(inp.reactions, inp.service_cases)
    rows = []
    for index, subject in enumerate(inp.subjects.subjects):
        prefix = f"footing_{index}"
        selected = loads.get(subject.joint, [])
        trace.input(f"{prefix}_id", subject.id, ref=f"{meta.refs['subjects'].result_id}#/subjects/{index}/id")
        trace.input(f"{prefix}_fz", list(selected), unit="kN", ref=meta.refs["reactions"].result_id)
        rows.append(_plan_row(subject.id, selected, kind, q_net, values, trace, prefix))
    trace.output("min_depth_mm", "max_spacing_mm")
    return PlanSizeBody(footings=rows)
