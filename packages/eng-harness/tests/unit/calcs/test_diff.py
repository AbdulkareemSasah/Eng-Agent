"""Calc 2, difference report (plan 0003 T8; spec 0003 4.7, AC24 to AC28): basis, gaps and object matching."""

from typing import Any, cast

import pytest
from eng_contract.errors import ContractError
from pydantic import ValidationError

from eng_harness.calc import InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.model_diff import DiffInput
from eng_harness.kinds.calcs import DiffBody

CALC_ID = "harness.model_diff"
MDL = "mdl_00000000000000000000000000"
KIND = "model.frame_placements/1"


def _point(x: float, y: float, z: float) -> dict[str, float]:
    return {"x_mm": x, "y_mm": y, "z_mm": z}


def _frame(fid: str, *, section: str = "S1", x: float = 0.0, rot: float = 0.0) -> dict[str, Any]:
    return {
        "id": fid,
        "kind": "column",
        "section": section,
        "i": _point(x, 0, 0),
        "j": _point(x, 0, 3000),
        "rotation_deg": rot,
    }


def _basis(**overrides: float) -> dict[str, Any]:
    values: dict[str, float] = {
        "compare.length": 1.0,
        "compare.angle": 1.0,
        "compare.stress": 1.0,
        "compare.unit_weight": 1.0,
        "compare.line_load": 1.0,
        "compare.area_load": 1.0,
        "compare.ratio": 0.0,
    }
    values.update(overrides)
    return {
        "template": {"name": "synthetic", "version": "0.1.0", "sha256": "a" * 64},
        "fields": {
            path: {
                "value": values[path],
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


def _refs(names: tuple[str, ...], *, revision: int = 3) -> dict[str, Any]:
    return {
        name: {
            "result_id": f"res_0000000000000000000000000{i}",
            "kind": KIND if "frames" in name else "basis.design_basis/1",
            "complete": True,
            "model_id": MDL,
            "model_revision": revision,
            "parents": [],
            "producer_tool": "csi",
        }
        for i, name in enumerate(names, start=1)
    }


def _run(
    frames_before: dict[str, Any],
    frames_after: dict[str, Any],
    *,
    basis: dict[str, Any] | None = None,
    meta: InputMeta | None = None,
) -> Any:
    fields = {
        "before_frames": frames_before,
        "after_frames": frames_after,
        "basis": basis or _basis(),
    }
    inp = DiffInput.model_validate(fields)
    refs = _refs(("before_frames", "after_frames", "basis"))
    return REGISTRY[CALC_ID](inp, meta or InputMeta.model_validate({"refs": refs}), TraceBuilder())


def test_basis_tolerances_required() -> None:
    """AC26: every §4.4 `compare.*` field must be present, confirmed and unit-correct (no default)."""
    frames = {"frames": [_frame("F1")]}
    base = _basis()
    del base["fields"]["compare.stress"]
    with pytest.raises(ContractError) as caught:
        _run(frames, frames, basis=base)
    assert caught.value.detail.field == "basis.compare.stress"
    wrong = _basis()
    wrong["fields"]["compare.length"]["unit"] = "m"
    with pytest.raises(ContractError) as caught:
        _run(frames, frames, basis=wrong)
    assert caught.value.detail.field == "basis.compare.length"
    unconfirmed = _basis()
    unconfirmed["fields"]["compare.angle"]["confirmed"] = False
    with pytest.raises(ContractError) as caught:
        _run(frames, frames, basis=unconfirmed)
    assert caught.value.detail.field == "basis.compare.angle"


def test_not_compared_and_ambiguous() -> None:
    """AC28: a section on one side only is `not_compared`; a duplicate key is `ambiguous` with `complete: false`."""
    inp = DiffInput.model_validate(
        {
            "before_frames": {"frames": [_frame("F1")]},
            "after_sections": {
                "frame_sections": [
                    {"name": "S1", "material": "M1", "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 300}}
                ],
                "area_sections": [],
            },
            "basis": _basis(),
        }
    )
    meta = InputMeta.model_validate(
        {
            "refs": {
                "before_frames": {
                    "result_id": "res_00000000000000000000000001",
                    "kind": KIND,
                    "complete": True,
                    "model_id": MDL,
                    "model_revision": 3,
                    "parents": [],
                    "producer_tool": "csi",
                },
                "after_sections": {
                    "result_id": "res_00000000000000000000000002",
                    "kind": "model.sections/1",
                    "complete": True,
                    "model_id": MDL,
                    "model_revision": 4,
                    "parents": [],
                    "producer_tool": "csi",
                },
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
    only_before = cast(DiffBody, REGISTRY[CALC_ID](inp, meta, TraceBuilder()))
    assert set(only_before.not_compared) == {"model.frame_placements/1", "model.sections/1"}
    assert only_before.complete is False
    dup = {
        "frame_loads": [
            {"frame": "F1", "pattern": "P", "direction": "gravity", "w_kN_m": 1.0},
            {"frame": "F1", "pattern": "P", "direction": "gravity", "w_kN_m": 2.0},
        ],
        "patterns": [{"name": "P", "type": "dead", "self_weight_ratio": 0.0}],
        "combinations": [],
        "area_loads": [],
    }
    after_dup = {
        "frame_loads": [
            {"frame": "F1", "pattern": "P", "direction": "gravity", "w_kN_m": 3.0},
            {"frame": "F1", "pattern": "P", "direction": "gravity", "w_kN_m": 4.0},
        ],
        "patterns": [{"name": "P", "type": "dead", "self_weight_ratio": 0.0}],
        "combinations": [],
        "area_loads": [],
    }
    loads = DiffInput.model_validate(
        {
            "before_loads": dup,
            "after_loads": after_dup,
            "basis": _basis(),
        }
    )
    meta = InputMeta.model_validate(
        {
            "refs": {
                "before_loads": {
                    "result_id": "res_00000000000000000000000001",
                    "kind": "model.load_set/1",
                    "complete": True,
                    "model_id": MDL,
                    "model_revision": 3,
                    "parents": [],
                    "producer_tool": "csi",
                },
                "after_loads": {
                    "result_id": "res_00000000000000000000000002",
                    "kind": "model.load_set/1",
                    "complete": True,
                    "model_id": MDL,
                    "model_revision": 4,
                    "parents": [],
                    "producer_tool": "csi",
                },
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
    body = cast(DiffBody, REGISTRY[CALC_ID](loads, meta, TraceBuilder()))
    assert any(c.change == "ambiguous" for c in body.changes)
    assert body.complete is False
    assert not any(c.change == "removed" and c.key == ["F1"] for c in body.changes)


def test_nested_input_aliases_flat_fields() -> None:
    """Golden files may nest `before` and `after`; the input model accepts them."""
    inp = DiffInput.model_validate(
        {
            "before": {"frames": {"frames": [_frame("F1")]}},
            "after": {"frames": {"frames": [_frame("F1")]}},
            "basis": _basis(),
        }
    )
    assert inp.before_frames is not None
    with pytest.raises(ValidationError, match="at least one"):
        DiffInput.model_validate({"basis": _basis()})
