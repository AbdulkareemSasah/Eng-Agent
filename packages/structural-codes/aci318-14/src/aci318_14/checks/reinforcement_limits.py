"""Check `aci318_14.10_6_1_1.longitudinal_reinforcement_limits`: column bar area limits (clause spec, plan 0004 T4). R1.

Purpose: per plan direction, the total longitudinal reinforcement against `0.01·Ag <= Ast <= 0.08·Ag` of 10.6.1.1.
Two verdicts, minimum then maximum; no load input.
Units: mm2 inputs; areas in mm2; ratios unitless.
Errors: none of its own; a failed `STEEL_IN_SECTION` precondition gives `NEEDS_ENGINEER`.
"""

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind
from structural_codes.check import check
from structural_codes.inputs import CheckInputs, bounded
from structural_codes.meta import CheckMeta, GapDecl
from structural_codes.trace import TraceRecorder

from aci318_14._column import STEEL_IN_SECTION

__all__ = ["LongitudinalReinforcementLimitsInputs", "longitudinal_reinforcement_limits"]

_RHO_MIN = Cited(value=0.01, unit="1", source="ACI 318-14 10.6.1.1 (nonprestressed columns, 0.01·Ag)")
_RHO_MAX = Cited(value=0.08, unit="1", source="ACI 318-14 10.6.1.1 (0.08·Ag)")
_AREA = Cited(value=0, unit="mm2", source="Geometry: gross section area and reinforcement area are positive")
_CLAUSE = "10.6.1.1"
_ASSUMPTIONS = (
    "nonprestressed column (prestressed limits are not representable)",
    "minimum on the full gross area: reduced effective area of 10.3.1.2 is not used (G-1, safe side)",
    "the section checked is outside lap splices (plan Q8)",
)


class LongitudinalReinforcementLimitsInputs(CheckInputs):
    """Gross section area and total longitudinal reinforcement of the column (clause spec §3)."""

    Ag_mm2: float = bounded(gt=_AREA, unit="mm2", ref_capable=True)
    Ast_mm2: float = bounded(gt=_AREA, unit="mm2", ref_capable=True)


_META = CheckMeta(
    check_id="aci318_14.10_6_1_1.longitudinal_reinforcement_limits",
    pack="aci318_14",
    code="ACI 318-14",
    edition="2014",
    clauses=(_CLAUSE, "10.3.1.2"),
    title="Longitudinal reinforcement limits of a nonprestressed column",
    members=frozenset({SubjectKind.FRAME}),
    spec="aci318_14/aci318_14.10_6_1_1.longitudinal_reinforcement_limits.md",
    gaps=(GapDecl(id="G-1", clause="10.3.1.2", reason="reduced effective area for the minimum is not used"),),
    assumptions=_ASSUMPTIONS,
)


@check(meta=_META, inputs=LongitudinalReinforcementLimitsInputs, preconditions=(STEEL_IN_SECTION,))
def longitudinal_reinforcement_limits(inp: LongitudinalReinforcementLimitsInputs, t: TraceRecorder) -> None:
    """Record `As_min`, `As_max`, `rho_ratio`, then the minimum and maximum verdicts (clause spec §4)."""
    ag, ast = t.value("Ag_mm2"), t.value("Ast_mm2")
    rho_min, rho_max = t.const("rho_min", _RHO_MIN), t.const("rho_max", _RHO_MAX)
    t.step(
        "As_min_mm2",
        rho_min * ag,
        unit="mm2",
        formula="rho_min * Ag_mm2",
        source=f"ACI 318-14 {_CLAUSE}",
        uses=["rho_min", "Ag_mm2"],
    )
    t.step(
        "As_max_mm2",
        rho_max * ag,
        unit="mm2",
        formula="rho_max * Ag_mm2",
        source=f"ACI 318-14 {_CLAUSE}",
        uses=["rho_max", "Ag_mm2"],
    )
    t.step(
        "rho_ratio",
        ast / ag,
        unit="1",
        formula="Ast_mm2 / Ag_mm2",
        source="Geometry: longitudinal reinforcement ratio for the calculation note",
        uses=["Ast_mm2", "Ag_mm2"],
    )
    t.verdict(demand="As_min_mm2", capacity="Ast_mm2", clause=_CLAUSE, assumptions=_ASSUMPTIONS)
    t.verdict(demand="Ast_mm2", capacity="As_max_mm2", clause=_CLAUSE, assumptions=_ASSUMPTIONS)
