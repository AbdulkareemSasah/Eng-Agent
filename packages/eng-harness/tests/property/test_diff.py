"""Difference-report properties (plan 0003 T8; spec 0003 AC25, AC27): tolerance boundary and symmetry."""

import struct
from typing import Any, cast

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness.calc import InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.model_diff import DiffInput
from eng_harness.kinds.calcs import DiffBody

MDL = "mdl_00000000000000000000000000"
TOL_MM = 5.0  # synthetic compare.length (mm); not a project value


def _frame(x: float) -> dict[str, Any]:
    return {
        "id": "F1",
        "kind": "column",
        "section": "S1",
        "i": {"x_mm": x, "y_mm": 0.0, "z_mm": 0.0},
        "j": {"x_mm": x, "y_mm": 0.0, "z_mm": 3000.0},
        "rotation_deg": 0.0,
    }


def _basis(length: float = TOL_MM) -> dict[str, Any]:
    return {
        "template": {"name": "synthetic", "version": "0.1.0", "sha256": "a" * 64},
        "fields": {
            path: {
                "value": length if path == "compare.length" else 0.0,
                "unit": unit,
                "source": "engineer:synthetic@2026-01-01T00:00:00.000Z",
                "confirmed": True,
                "citation": None,
            }
            for path, unit in (
                ("compare.length", "mm"),
                ("compare.angle", "deg"),
                ("compare.stress", "MPa"),
                ("compare.unit_weight", "kN/m3"),
                ("compare.line_load", "kN/m"),
                ("compare.area_load", "kPa"),
                ("compare.ratio", "1"),
            )
        },
    }


def _meta(before_rev: int = 3, after_rev: int = 4) -> InputMeta:
    ref = {
        "kind": "model.frame_placements/1",
        "complete": True,
        "model_id": MDL,
        "parents": [],
        "producer_tool": "csi",
    }
    return InputMeta.model_validate(
        {
            "refs": {
                "before_frames": ref | {"result_id": "res_00000000000000000000000001", "model_revision": before_rev},
                "after_frames": ref | {"result_id": "res_00000000000000000000000002", "model_revision": after_rev},
                "basis": {
                    "result_id": "res_00000000000000000000000003",
                    "kind": "basis.design_basis/1",
                    "complete": True,
                    "model_id": None,
                    "model_revision": None,
                    "parents": [],
                    "producer_tool": "harness",
                },
            }
        }
    )


def _diff(before: dict[str, Any], after: dict[str, Any], *, basis: dict[str, Any] | None = None) -> DiffBody:
    inp = DiffInput.model_validate({"before_frames": before, "after_frames": after, "basis": basis or _basis()})
    return cast(DiffBody, REGISTRY["harness.model_diff"](inp, _meta(), TraceBuilder()))


def _next_up(value: float) -> float:
    bits = struct.unpack("!Q", struct.pack("!d", value + TOL_MM))[0] + len((False,))
    return cast(float, struct.unpack("!d", struct.pack("!Q", bits))[0])


def test_boundary_exact() -> None:
    """AC25: |Δ| == tolerance is within tolerance; one ULP above is changed; zero tolerance needs exact match."""
    before = {"frames": [_frame(0.0)]}
    at_tol = {"frames": [_frame(TOL_MM)]}  # Δx = 5.0 mm == compare.length
    body = _diff(before, at_tol)
    assert body.within_tolerance
    assert not any(c.change == "changed" for c in body.changes)
    above = {"frames": [_frame(_next_up(TOL_MM))]}  # Δx = TOL + 1 ULP
    body_above = _diff(before, above)
    assert any(c.change == "changed" for c in body_above.changes)
    body_zero = _diff(before, at_tol, basis=_basis(0.0))
    assert any(c.change == "changed" for c in body_zero.changes)


@given(st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False))
@settings(derandomize=True)
def test_identity_and_symmetry(offset: float) -> None:
    """AC27: identical inputs give `identical`; A→B and B→A swap added and removed."""
    offset = offset + 0.0
    frames = {"frames": [_frame(offset)]}
    same = _diff(frames, frames)
    assert same.identical is True
    fewer = {"frames": [_frame(offset)]}
    extra = {
        "frames": [
            _frame(offset),
            {**_frame(offset + 10.0), "id": "F2"},
        ]
    }
    forward = _diff(fewer, extra)
    backward = _diff(extra, fewer)
    assert {c.change for c in forward.changes} == {"added"}
    assert {c.change for c in backward.changes} == {"removed"}
