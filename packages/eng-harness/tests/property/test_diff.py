"""Difference report properties (plan 0003 T8b; spec 0003 AC25, AC27): the exact boundary, identity and symmetry."""

import math
from fractions import Fraction
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness.calc import InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.model_diff import DiffInput

FP = "model.frame_placements/1"
UNITS = {
    "compare.length_mm": "mm",
    "compare.angle_deg": "deg",
    "compare.stress_MPa": "MPa",
    "compare.unit_weight_kN_m3": "kN/m3",
    "compare.line_load_kN_m": "kN/m",
    "compare.area_load_kPa": "kPa",
    "compare.dimensionless_ratio": "1",
}
_finite = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False).map(lambda v: v + 0.0)
_ids = st.lists(st.sampled_from(["F1", "F2", "F3", "F4", "F5"]), max_size=5, unique=True)


def _ref(n: int, revision: int) -> dict[str, Any]:
    return {
        "result_id": f"res_0000000000000000000000000{n}",
        "kind": FP,
        "complete": True,
        "model_id": "mdl_00000000000000000000000000",
        "model_revision": revision,
        "parents": [],
        "producer_tool": "csi",
    }


def _frame(fid: str, x: float, section: str = "S1", rotation: float = 0.0) -> dict[str, Any]:
    return {
        "id": fid,
        "kind": "column",
        "section": section,
        "i": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0},
        "j": {"x_mm": x, "y_mm": 0.0, "z_mm": 3000.0},
        "rotation_deg": rotation,
    }


def _diff(before: list[dict[str, Any]], after: list[dict[str, Any]], length: float = 1.0) -> dict[str, Any]:
    source = "engineer:synthetic@2026-01-01T00:00:00.000Z"
    fields = {
        p: {"value": length if p == "compare.length_mm" else 1.0, "unit": u, "source": source, "confirmed": True,
            "citation": None}
        for p, u in UNITS.items()
    }  # fmt: skip
    inp = DiffInput.model_validate(
        {"before_frames": {"frames": before}, "after_frames": {"frames": after}, "basis": {"template": None,
         "fields": fields}}
    )  # fmt: skip
    basis = _ref(9, 0) | {"kind": "basis.design_basis/1", "model_id": None, "model_revision": None}
    meta = InputMeta.model_validate({"refs": {"before_frames": _ref(1, 3), "after_frames": _ref(2, 4), "basis": basis}})
    return REGISTRY["harness.model_diff"](inp, meta, TraceBuilder()).model_dump(mode="json")


@settings(derandomize=True, max_examples=200, deadline=None)
@given(n=st.integers(-(10**6), 10**6), k=st.integers(0, 10**4), m=st.integers(0, 20))
def test_boundary_exact(n: int, k: int, m: int) -> None:
    """AC25: a difference of exactly the tolerance is within it, the next float above is changed (exact Fractions).

    x = n / 2^m and tolerance = k / 2^m are dyadic, so x + tolerance is exact in binary64.
    """
    x, tolerance = n / 2**m, k / 2**m
    assert Fraction(x + tolerance) - Fraction(x) == Fraction(tolerance)
    above = math.nextafter(x + tolerance, math.inf)
    out = _diff([_frame("F1", x), _frame("F2", x)], [_frame("F1", x + tolerance), _frame("F2", above)], tolerance)
    within = [(w["key"], w["after"], w["rule"]) for w in out["within_tolerance"]]
    assert within == ([] if tolerance == 0 else [(["frames", "F1"], x + tolerance, "D3")])
    assert [(c["key"], c["properties"][0]["after"]) for c in out["changes"]] == [(["frames", "F2"], above)]
    assert out["changes"][0]["properties"][0]["tolerance"] == tolerance
    assert out["counts"][FP]["within_tolerance"] == len(within)


@settings(derandomize=True, max_examples=100, deadline=None)
@given(a=_finite, b=_finite)
def test_zero_tolerance_needs_exact_equality(a: float, b: float) -> None:
    """AC25: with a tolerance of zero only exact equality is equal; a property is never within a zero tolerance."""
    out = _diff([_frame("F1", a)], [_frame("F1", b)], 0.0)
    assert out["within_tolerance"] == []
    assert bool(out["changes"]) is (a != b)


@st.composite
def _states(draw: st.DrawFn) -> list[dict[str, Any]]:
    """A synthetic frame list: ids from a small pool so two draws share some keys."""
    return [
        _frame(fid, draw(_finite), draw(st.sampled_from(["S1", "S2"])), draw(st.sampled_from([0.0, 90.0, 360.0])))
        for fid in draw(_ids)
    ]


@settings(derandomize=True, max_examples=150, deadline=None)
@given(a=_states(), b=_states())
def test_identity_and_symmetry(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> None:
    """AC27: A to A is identical; A to B and B to A swap added and removed and every before and after value.

    An empty frame list is a valid section, so the all-added and all-removed cases are drawn too.
    """
    same = _diff(a, a)
    assert (same["identical"], same["changes"], same["within_tolerance"]) == (True, [], [])
    forward, backward = _diff(a, b), _diff(b, a)
    swap = {"added": "removed", "removed": "added", "changed": "changed", "ambiguous": "ambiguous"}
    mirrored = [
        {
            **c,
            "change": swap[c["change"]],
            "before": c["after"],
            "after": c["before"],
            "properties": [p | {"before": p["after"], "after": p["before"]} for p in c["properties"]],
        }
        for c in backward["changes"]
    ]
    assert forward["changes"] == mirrored
    assert forward["within_tolerance"] == [
        w | {"before": w["after"], "after": w["before"]} for w in backward["within_tolerance"]
    ]
    f, r = forward["counts"][FP], backward["counts"][FP]
    assert (f["added"], f["removed"], f["changed"]) == (r["removed"], r["added"], r["changed"])
    assert f["unchanged"] == r["unchanged"]
    assert forward["identical"] is backward["identical"] is (not forward["changes"])
