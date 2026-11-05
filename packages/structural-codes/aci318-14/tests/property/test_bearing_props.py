"""Property test of `aci318_14.13_3_1_1.bearing_pressure_service` (plan 0002 T3; BP-AC4); Hypothesis derandomized.

Clause spec §8: `q_max` is non-decreasing in `FZ` (with `N > 0`), `|MX|`, `|MY|`, `gamma_c`, `gamma_s`, `soil_depth`
and `surcharge`; the verdict does not depend on the signs of `MX`, `MY` when `e = 0`. Correctly rounded float64
operations are monotone, so the comparisons are exact. Inputs are synthetic and stay in full contact (assumed).
"""

from typing import Any

from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from structural_codes import BatchItem, evaluate_batch
from structural_codes.pack import Pack, Registry

from aci318_14 import __version__
from aci318_14.checks.bearing_pressure import bearing_pressure_service

_ID = "aci318_14.13_3_1_1.bearing_pressure_service"
_F1 = Subject(kind=SubjectKind.FOOTING, id="F1")
_REGISTRY = Registry.of(
    [Pack("aci318_14", "ACI 318-14", "2014", __version__, (bearing_pressure_service,), "approvals.yaml")]
)
_GROWS = ("FZ_kN", "MX_kNm", "MY_kNm", "gamma_c_kN_m3", "gamma_s_kN_m3", "soil_depth_mm", "surcharge_kPa")


def _num(low: int, high: int) -> st.SearchStrategy[float]:
    return st.integers(min_value=low, max_value=high).map(float)


_inputs = st.fixed_dictionaries(
    {
        "FX_kN": _num(-100, 100),
        "FY_kN": _num(-100, 100),
        "FZ_kN": _num(500, 5000),
        "MX_kNm": _num(0, 150),
        "MY_kNm": _num(0, 150),
        "Lx_mm": _num(2000, 4000),
        "Ly_mm": _num(2000, 4000),
        "h_mm": _num(300, 1200),
        "soil_depth_mm": _num(0, 2000),
        "gamma_c_kN_m3": _num(20, 26),
        "gamma_s_kN_m3": _num(14, 22),
        "surcharge_kPa": _num(0, 20),
        "q_allow_kPa": _num(100, 600),
    }
)


def _run(*cases: dict[str, Any]) -> list[tuple[VerdictStatus, float | None, dict[str, Any]]]:
    """Evaluate the cases in one batch; per case the status, the ratio and the trace steps by name."""
    items = [BatchItem(_F1, {**c, "reaction_height_mm": 0.0, "allowable_kind": "gross"}) for c in cases]
    payload = evaluate_batch(_ID, items, registry=_REGISTRY).payload
    steps = [{s.name: s.value for s in trace.steps} for trace in payload.traces]
    return [(v.status, v.ratio, k) for v, k in zip(payload.verdicts, steps, strict=True)]


@settings(derandomize=True, max_examples=150, deadline=None)
@given(inputs=_inputs, grow=st.sampled_from(_GROWS), more=_num(1, 50))
def test_monotone_and_sign_free(inputs: dict[str, Any], grow: str, more: float) -> None:
    """Increasing one load or overburden input never lowers q_max; flipping MX and MY changes nothing (BP-AC4)."""
    larger = {**inputs, grow: inputs[grow] + more}
    flipped = {**inputs, "MX_kNm": -inputs["MX_kNm"], "MY_kNm": -inputs["MY_kNm"]}
    (status, ratio, steps), (status_2, _, steps_2), (status_3, ratio_3, steps_3) = _run(inputs, larger, flipped)
    full = (VerdictStatus.PASS, VerdictStatus.FAIL)
    assume(status in full and status_2 in full)
    assert steps_2["q_max_kPa"] >= steps["q_max_kPa"]
    assert (status_3, ratio_3) == (status, ratio)
    assert (steps_3["q_max_kPa"], steps_3["q_min_kPa"]) == (steps["q_max_kPa"], steps["q_min_kPa"])
