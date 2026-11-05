"""Check `aci318_14.8_6_1_1.min_flexural_reinforcement`: minimum bottom steel of a footing (clause spec, plan T7). R1.

Purpose: per plan direction, the provided bottom reinforcement against `As_min = rho_min*Ag` of 8.6.1.1, with
`rho_min` from Table 8.6.1.1 (deformed bars) and `Ag` the full footing width times the total depth; 13.3.3.1 refers
two-way footings to the two-way slab provisions (C-1, plan §6 Q9). Two verdicts, X then Y; no load input.
Units: mm, mm2 and MPa inputs; areas in mm2; ratios unitless.
Errors: none of its own; a failed `FY_MAX` precondition gives `NEEDS_ENGINEER`.
"""

# ruff: noqa: N815  # B-276: field names are fixed by the contract's unit suffixes (EC §4.7.2), e.g. fy_MPa

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind
from structural_codes.check import check
from structural_codes.inputs import CheckInputs, bounded
from structural_codes.meta import CheckMeta
from structural_codes.trace import TraceRecorder

from aci318_14._common import FY_MAX

__all__ = ["MinReinforcementInputs", "min_flexural_reinforcement"]

_TABLE = "ACI 318-14 Table 8.6.1.1"
_FY_ROW = Cited(value=420, unit="MPa", source=f"{_TABLE} (row boundary)")
_R1 = Cited(value=0.0020, unit="1", source=f"{_TABLE} (deformed bars, fy < 420 MPa)")
_R2 = Cited(value=0.0018, unit="1", source=f"{_TABLE} (deformed bars, fy >= 420 MPa)")
_R3 = Cited(value=0.0014, unit="1", source=f"{_TABLE} (lower limit, fy >= 420 MPa)")
_LENGTH = Cited(value=0, unit="mm", source="Geometry: the length of a solid is positive")
_AREA = Cited(value=0, unit="mm2", source="Geometry: provided reinforcement has a positive area")
_STRENGTH = Cited(value=0, unit="MPa", source="Mechanics of materials: a strength is positive")
_CLAUSE = "8.6.1.1"
_ASSUMPTIONS = (
    "deformed bars: Table 8.6.1.1 rows for deformed bars only (no welded wire reinforcement in footings)",
    "gross section Ag = full footing width across the bars times the total depth h",
    "two-way slab minimum through 13.3.3.1; a beam-type minimum is not checked (C-1, plan Q9)",
)
# Per direction: suffix, width of the section crossed by the bars, provided area.
_DIRECTIONS = (("x", "Ly_mm", "As_x_mm2"), ("y", "Lx_mm", "As_y_mm2"))


class MinReinforcementInputs(CheckInputs):
    """Footing plan, total depth, provided bottom steel per direction and bar yield strength (clause spec §3)."""

    Lx_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    Ly_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    h_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    As_x_mm2: float = bounded(gt=_AREA, unit="mm2", ref_capable=True)
    As_y_mm2: float = bounded(gt=_AREA, unit="mm2", ref_capable=True)
    fy_MPa: float = bounded(gt=_STRENGTH, unit="MPa", ref_capable=True, engineering_quantity=True)


_META = CheckMeta(
    check_id="aci318_14.8_6_1_1.min_flexural_reinforcement",
    pack="aci318_14",
    code="ACI 318-14",
    edition="2014",
    clauses=(_CLAUSE, "Table 8.6.1.1", "13.3.3.1", "20.2.2.4"),
    title="Minimum flexural reinforcement of an isolated footing in each direction",
    members=frozenset({SubjectKind.FOOTING}),
    spec="aci318_14/aci318_14.8_6_1_1.min_flexural_reinforcement.md",
    gaps=(),
    assumptions=_ASSUMPTIONS,
)


@check(meta=_META, inputs=MinReinforcementInputs, preconditions=(FY_MAX,))
def min_flexural_reinforcement(inp: MinReinforcementInputs, t: TraceRecorder) -> None:
    """Record `rho_min`, then `Ag` and `As_min` per direction and one verdict each, X then Y (clause spec §4)."""
    fy, fy_row = t.value("fy_MPa"), t.const("fy_row", _FY_ROW)
    r1, r2, r3 = t.const("r1", _R1), t.const("r2", _R2), t.const("r3", _R3)
    rho = t.step(
        "rho_min_ratio",
        r1 if fy < fy_row else max(r2 * fy_row / fy, r3),
        unit="1",
        formula="r1 if fy_MPa < fy_row else max(r2 * fy_row / fy_MPa, r3)",
        source=_TABLE,
        uses=["fy_MPa", "fy_row", "r1", "r2", "r3"],
    )
    for s, width, _area in _DIRECTIONS:
        ag = t.step(
            f"Ag_{s}_mm2",
            t.value(width) * t.value("h_mm"),
            unit="mm2",
            formula=f"{width} * h_mm",
            source="Geometry: gross area of the section crossed by the bars",
            uses=[width, "h_mm"],
        )
        t.step(
            f"As_min_{s}_mm2",
            rho * ag,
            unit="mm2",
            formula=f"rho_min_ratio * Ag_{s}_mm2",
            source=f"ACI 318-14 {_CLAUSE}",
            uses=["rho_min_ratio", f"Ag_{s}_mm2"],
        )
    for s, _width, area in _DIRECTIONS:
        t.verdict(demand=f"As_min_{s}_mm2", capacity=area, clause=_CLAUSE, assumptions=_ASSUMPTIONS)
