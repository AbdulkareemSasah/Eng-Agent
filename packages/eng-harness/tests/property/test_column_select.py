"""Column selection permutation invariance (plan 0013 T2; spec 0013 AC5)."""

import copy
from fractions import Fraction
from typing import Any, cast

from eng_contract.canonical import payload_sha256
from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY

CALC_ID = "harness.column_select"
_BASIS = {
    "template": None,
    "fields": {
        "compare.length": {
            "value": 5,
            "unit": "mm",
            "source": "engineer:trial@2026-11-01T00:00:00.000Z",
            "confirmed": True,
            "citation": None,
        }
    },
}
_META = {
    "scope": {
        "result_id": "res_00000000000000000000000001",
        "kind": "basis.engineer_input/1",
        "complete": True,
        "model_id": None,
        "model_revision": None,
        "parents": [],
        "producer_tool": "harness",
    },
    "frames": {
        "result_id": "res_00000000000000000000000002",
        "kind": "model.frame_placements/1",
        "complete": True,
        "model_id": "mdl_00000000000000000000000000",
        "model_revision": 1,
        "parents": [],
        "producer_tool": "csi",
    },
    "sections": {
        "result_id": "res_00000000000000000000000003",
        "kind": "model.sections/1",
        "complete": True,
        "model_id": "mdl_00000000000000000000000000",
        "model_revision": 1,
        "parents": [],
        "producer_tool": "csi",
    },
    "basis": {
        "result_id": "res_00000000000000000000000004",
        "kind": "basis.design_basis/1",
        "complete": True,
        "model_id": None,
        "model_revision": None,
        "parents": [],
        "producer_tool": "harness",
    },
}
_coord = st.integers(min_value=-50, max_value=50).map(lambda v: float(v))
_name = st.from_regex(r"[A-Z][0-9]{0,2}", fullmatch=True)


def _frame(name: str, z: float, plan: tuple[float, float]) -> dict[str, Any]:
    return {
        "id": name,
        "kind": "other",
        "section": "S1",
        "i": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0},
        "j": {"x_mm": plan[0], "y_mm": plan[1], "z_mm": z},
        "story": "L1",
        "rotation_deg": 0.0,
    }


@st.composite
def inputs(draw: st.DrawFn) -> dict[str, Any]:
    names = draw(st.lists(_name, min_size=1, max_size=6, unique=True))
    frames = []
    for name in names:
        z = float(draw(st.integers(1000, 5000)))
        plan_x = float(draw(st.integers(0, 4)))
        frames.append(_frame(name, z, (plan_x, 0.0)))
    scope_names = list(draw(st.permutations(names)))
    return {
        "scope": {"frames": list(scope_names), "combinations": ["1"]},
        "frames": {"frames": frames},
        "sections": {
            "frame_sections": [
                {
                    "name": "S1",
                    "material": "C30",
                    "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 550},
                }
            ],
            "area_sections": [],
        },
        "basis": _BASIS,
    }


def _run(fields: dict[str, Any]) -> tuple[dict[str, Any], str]:
    definition = REGISTRY[CALC_ID]
    input_type = cast(type[CalcInput], definition.input_type)
    inp = input_type.model_validate(fields)
    meta = InputMeta.model_validate({"refs": _META})
    body = definition(inp, meta, TraceBuilder())
    dumped = body.model_dump(mode="json")
    return dumped, payload_sha256(dumped)


def _shuffled(data: st.DataObject, rows: list[Any]) -> list[Any]:
    return list(data.draw(st.permutations(rows)))


@settings(derandomize=True, max_examples=40, deadline=None)
@given(inputs(), st.data())
def test_permutation_invariant(fields: dict[str, Any], data: st.DataObject) -> None:
    base, base_hash = _run(fields)
    mixed = copy.deepcopy(fields)
    mixed["frames"]["frames"] = _shuffled(data, mixed["frames"]["frames"])
    mixed["sections"]["frame_sections"] = _shuffled(data, mixed["sections"]["frame_sections"])
    mixed["scope"]["frames"] = _shuffled(data, mixed["scope"]["frames"])
    for frame in mixed["frames"]["frames"]:
        dx, dy = frame["j"]["x_mm"], frame["j"]["y_mm"]
        assert Fraction(str(dx)) ** 2 + Fraction(str(dy)) ** 2 <= 25
    permuted, permuted_hash = _run(mixed)
    assert permuted == base
    assert permuted_hash == base_hash
