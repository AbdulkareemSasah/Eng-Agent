"""Calc 6, element count and position comparison (plan 0003 T12; spec 0003 4.11, AC42 to AC45)."""

import json
from pathlib import Path
from typing import Any

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY

CALC_ID = "harness.placement_compare"
LENGTH = "compare.length_mm"
MDL = "mdl_00000000000000000000000000"
SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"
FP = "model.frame_placements/1"
AP = "model.area_placements/1"
GOLDEN_DIR = Path(__file__).resolve().parents[2] / "data" / "golden" / "calcs"


def _field(value: Any, unit: str = "mm", *, confirmed: bool = True) -> dict[str, Any]:
    return {"value": value, "unit": unit, "source": SRC, "confirmed": confirmed, "citation": None}


def _basis(length: float = 1.0) -> dict[str, Any]:
    return {"template": None, "fields": {LENGTH: _field(length)}}


def _ref(n: int, kind: str, *, revision: int | None = 3, complete: bool = True) -> dict[str, Any]:
    return {
        "result_id": f"res_{n:026d}",
        "kind": kind,
        "complete": complete,
        "model_id": None if revision is None else MDL,
        "model_revision": revision,
        "parents": [],
        "producer_tool": "csi" if revision is not None else "harness",
    }


def _point(x: float, y: float, z: float) -> dict[str, float]:
    return {"x_mm": x, "y_mm": y, "z_mm": z}


def _frame(
    fid: str,
    *,
    kind: str = "column",
    i: tuple[float, float, float] = (0.0, 0.0, 0.0),
    j: tuple[float, float, float] = (0.0, 0.0, 3000.0),
    story: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": fid,
        "kind": kind,
        "section": "S1",
        "i": _point(*i),
        "j": _point(*j),
        "rotation_deg": 0.0,
    }
    if story is not None:
        row["story"] = story
    return row


def _area(aid: str, points: list[tuple[float, float, float]], *, kind: str = "slab") -> dict[str, Any]:
    return {"id": aid, "kind": kind, "section": "S200", "points": [_point(*p) for p in points]}


def _frames(*frames: dict[str, Any]) -> dict[str, Any]:
    return {"frames": list(frames)}


def _areas(*areas: dict[str, Any]) -> dict[str, Any]:
    return {"areas": list(areas)}


def _input_type() -> type[CalcInput]:
    input_type = REGISTRY[CALC_ID].input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    return input_type


def _run(fields: dict[str, Any], refs: dict[str, Any], trace: TraceBuilder | None = None) -> dict[str, Any]:
    inp = _input_type().model_validate(fields)
    meta = InputMeta.model_validate({"refs": refs})
    return REGISTRY[CALC_ID](inp, meta, trace or TraceBuilder()).model_dump(mode="json")


def _by_id(out: dict[str, Any], element: str, item_id: str) -> dict[str, Any]:
    for row in out["by_id"]:
        if row["element"] == element and row["id"] == item_id:
            return row
    raise AssertionError((element, item_id, out["by_id"]))


def _count(out: dict[str, Any], element: str, by: str, name: str) -> dict[str, Any]:
    for row in out["counts"]:
        if (row["element"], row["by"], row["name"]) == (element, by, name):
            return row
    raise AssertionError((element, by, name, out["counts"]))


def test_counts_frames_areas_renames() -> None:
    """AC42 to AC45: the four golden scenarios as unit cases (plan amendment B-452)."""
    # AC42 / placement-counts: one column and one beam fewer on side b; counts and story rows.
    counts = _run(
        {
            "a_frames": _frames(
                _frame("C1", story="S1"),
                _frame("C2", i=(6000.0, 0.0, 0.0), j=(6000.0, 0.0, 3000.0), story="S1"),
                _frame("B1", kind="beam", i=(0.0, 0.0, 3000.0), j=(6000.0, 0.0, 3000.0), story="S1"),
                _frame("B2", kind="beam", i=(0.0, 0.0, 6000.0), j=(6000.0, 0.0, 6000.0), story="S2"),
            ),
            "b_frames": _frames(
                _frame("C1", story="S1"),
                _frame("B1", kind="beam", i=(0.0, 0.0, 3000.0), j=(6000.0, 0.0, 3000.0), story="S1"),
            ),
            "basis": _basis(1.0),
        },
        {
            "a_frames": _ref(1, FP),
            "b_frames": _ref(2, FP, revision=4),
            "basis": _ref(9, "basis.design_basis/1", revision=None),
        },
    )
    assert _count(counts, "frame", "type", "column") == {
        "element": "frame",
        "by": "type",
        "name": "column",
        "a": 2,
        "b": 1,
        "difference": -1,
    }
    assert _count(counts, "frame", "type", "beam")["difference"] == -1
    assert _count(counts, "frame", "story", "S1") == {
        "element": "frame",
        "by": "story",
        "name": "S1",
        "a": 3,
        "b": 2,
        "difference": -1,
    }
    assert _count(counts, "frame", "story", "S2")["difference"] == -1
    assert {row["id"] for row in counts["only_in_a"]} == {"B2", "C2"}
    assert counts["equal"] is False

    # AC43 / placement-frames: reversed ends; (3,4,0) at t=5 is same; (6,8,0) is moved.
    frames = _run(
        {
            "a_frames": _frames(
                _frame("F_rev"),
                _frame("F_bound"),
                _frame("F_far"),
            ),
            "b_frames": _frames(
                _frame("F_rev", i=(0.0, 0.0, 3000.0), j=(0.0, 0.0, 0.0)),
                _frame("F_bound", i=(3.0, 4.0, 0.0), j=(0.0, 0.0, 3000.0)),
                _frame("F_far", i=(6.0, 8.0, 0.0), j=(0.0, 0.0, 3000.0)),
            ),
            "basis": _basis(5.0),
        },
        {
            "a_frames": _ref(1, FP),
            "b_frames": _ref(2, FP, revision=4),
            "basis": _ref(9, "basis.design_basis/1", revision=None),
        },
    )
    assert _by_id(frames, "frame", "F_rev") == {
        "element": "frame",
        "id": "F_rev",
        "result": "reversed",
        "distance_mm": 0.0,
    }
    assert _by_id(frames, "frame", "F_bound") == {
        "element": "frame",
        "id": "F_bound",
        "result": "same",
        "distance_mm": 5.0,
    }
    assert _by_id(frames, "frame", "F_far") == {
        "element": "frame",
        "id": "F_far",
        "result": "moved",
        "distance_mm": 10.0,
    }

    # AC44 / placement-areas: cyclic shift same; reversed order reversed; different point count reshaped.
    triangle = [(0.0, 0.0, 0.0), (3000.0, 0.0, 0.0), (0.0, 4000.0, 0.0)]
    areas = _run(
        {
            "a_areas": _areas(
                _area("A_rot", triangle),
                _area("A_rev", triangle),
                _area("A_shape", triangle),
            ),
            "b_areas": _areas(
                _area("A_rot", [triangle[1], triangle[2], triangle[0]]),
                _area("A_rev", [triangle[0], triangle[2], triangle[1]]),
                _area(
                    "A_shape",
                    [triangle[0], triangle[1], (1500.0, 2000.0, 0.0), triangle[2]],
                ),
            ),
            "basis": _basis(1.0),
        },
        {
            "a_areas": _ref(3, AP),
            "b_areas": _ref(4, AP, revision=4),
            "basis": _ref(9, "basis.design_basis/1", revision=None),
        },
    )
    assert _by_id(areas, "area", "A_rot")["result"] == "same"
    assert _by_id(areas, "area", "A_rev")["result"] == "reversed"
    assert _by_id(areas, "area", "A_shape") == {
        "element": "area",
        "id": "A_shape",
        "result": "reshaped",
        "distance_mm": None,
    }

    # AC45 / placement-renames: one geometric partner each way; coincident pair is ambiguous.
    renames = _run(
        {
            "a_frames": _frames(
                _frame("F_keep", i=(-6000.0, 0.0, 0.0), j=(-6000.0, 0.0, 3000.0)),
                _frame("F_old"),
                _frame("F5", i=(10000.0, 0.0, 0.0), j=(10000.0, 0.0, 3000.0)),
            ),
            "b_frames": _frames(
                _frame("F_keep", i=(-6000.0, 0.0, 0.0), j=(-6000.0, 0.0, 3000.0)),
                _frame("F_new"),
                _frame("F6", i=(10000.0, 0.0, 0.0), j=(10000.0, 0.0, 3000.0)),
                _frame("F7", i=(10000.0, 0.0, 0.0), j=(10000.0, 0.0, 3000.0)),
            ),
            "basis": _basis(1.0),
        },
        {
            "a_frames": _ref(1, FP),
            "b_frames": _ref(2, FP, revision=4),
            "basis": _ref(9, "basis.design_basis/1", revision=None),
        },
    )
    assert renames["renamed"] == [{"element": "frame", "a_id": "F_old", "b_id": "F_new"}]
    assert renames["ambiguous"] == [
        {"element": "frame", "side": "a", "id": "F5", "candidates": ["F6", "F7"]}
    ]
    assert {row["id"] for row in renames["only_in_b"]} == {"F6", "F7"}
    assert _by_id(renames, "frame", "F_keep")["result"] == "same"

    # Golden files of this task are present and match the hand-derived expectations above.
    files = sorted(GOLDEN_DIR.glob("placement-*.json"))
    assert [path.stem for path in files] == [
        "placement-areas",
        "placement-counts",
        "placement-frames",
        "placement-renames",
    ]
    for path in files:
        case = json.loads(path.read_text(encoding="utf-8"))
        assert case["synthetic"] is True
        assert case["method_ref"].startswith("§4.11")
        assert case["derivation"].strip()
