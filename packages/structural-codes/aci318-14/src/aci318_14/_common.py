"""Shared cited constants and material preconditions of the ACI 318-14 pack (plan 0002 T2). R1 module.

Purpose: `CITED` (constants used by several checks, by trace name; `const` records one) and the preconditions of the
clause specs §2. Units: as each `Cited` states (`sf_max` in MPa^0.5 stored with unit 1, plan §6 Q6). Errors: `KeyError`
for an unknown constant; `CheckDefinitionError` from the recorder for a name recorded twice.
"""

from enum import StrEnum
from types import MappingProxyType
from typing import Any

from eng_contract.cited import Cited
from structural_codes.applicability import Outcome, Precondition
from structural_codes.trace import TraceRecorder

__all__ = ["CITED", "FC_MIN", "FY_MAX", "NORMALWEIGHT", "ConcreteClass", "const"]

CITED = MappingProxyType(
    {
        "phi_v": Cited(value=0.75, unit="1", source="ACI 318-14 Table 21.2.1, row (b) shear"),
        "lambda_nw": Cited(value=1.0, unit="1", source="ACI 318-14 19.2.4.2 (normalweight concrete)"),
        "sf_max": Cited(
            value=8.3,
            unit="1",
            source="ACI 318-14 22.5.3.1, 22.6.3.1, 25.4.1.4 (limit on sqrt f'c)",
            note="true unit MPa^0.5; stored as 1 because the eng-contract unit table has no MPa^0.5 (plan 0002 §6 Q6)",
        ),
        "fc_min": Cited(value=17, unit="MPa", source="ACI 318-14 Table 19.2.1.1 (minimum f'c, general row)"),
        "fy_max": Cited(value=550, unit="MPa", source="ACI 318-14 Table 20.2.2.4(a) (not special seismic)"),
        "k_m": Cited(value=0.001, unit="1", source="SI prefix milli: m per mm (EC §4.7.3)"),
        "k_kN": Cited(value=0.001, unit="1", source="SI prefix kilo: kN per N (EC §4.7.3)"),
        "k_kNm": Cited(value=1.0e-6, unit="1", source="SI prefixes kilo and milli: kN.m per N.mm (EC §4.7.3)"),
        "c_S": Cited(value=6, unit="1", source="Mechanics of materials: section modulus of a rectangle, b*h^2/6"),
        "c_I": Cited(value=12, unit="1", source="Mechanics of materials: second moment of a rectangle, b*h^3/12"),
        "c_half": Cited(
            value=2,
            unit="1",
            source="Statics and geometry: factor 2 of a half or a pair (L/2 and c/2 of a centered footing and column, "
            "the midpoint xbar, the resultant at a/2, the integral Lp^2/2, mid-depth h/2, the bisection midpoint, "
            "two side bars per inner layer)",
        ),
        "c_third": Cited(value=3, unit="1", source="Statics: integral of u^2 du over a cantilever, Lp^3/3"),
    }
)


def const(t: TraceRecorder, name: str) -> float:
    """Record the shared constant `name` on `t` and return its value (errors: see the module docstring)."""
    return t.const(name, CITED[name])


class ConcreteClass(StrEnum):
    """Concrete density class of the design basis field `materials.concrete_class` (19.2.4)."""

    NORMALWEIGHT = "normalweight"
    LIGHTWEIGHT = "lightweight"
    SAND_LIGHTWEIGHT = "sand_lightweight"


def _normalweight(inp: Any, t: TraceRecorder) -> bool:
    return bool(inp.concrete_class == ConcreteClass.NORMALWEIGHT)


def _fc_min(inp: Any, t: TraceRecorder) -> bool:
    return t.value("fc_MPa") >= const(t, "fc_min")


def _fy_max(inp: Any, t: TraceRecorder) -> bool:
    return t.value("fy_MPa") <= const(t, "fy_max")


_NE = Outcome.NEEDS_ENGINEER
NORMALWEIGHT = Precondition("NORMALWEIGHT", _NE, "19.2.4.2", "concrete must be normalweight (gap G-1)", _normalweight)
FC_MIN = Precondition("FC_MIN", _NE, "Table 19.2.1.1", "fc_MPa >= fc_min (general row, SDC A to C)", _fc_min)
FY_MAX = Precondition("FY_MAX", _NE, "Table 20.2.2.4(a)", "fy_MPa <= fy_max (no special seismic system)", _fy_max)
