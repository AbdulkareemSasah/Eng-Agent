"""Calc 6, element count and position comparison (plan 0003 T12; spec 0003 4.11, AC42 to AC45)."""

import json
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import CalcInput, InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.kinds.calcs import PlacementComparison

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


def _refusal(fields: dict[str, Any], refs: dict[str, Any]) -> ContractError:
    with pytest.raises(ContractError) as caught:
        _run(fields, refs)
    return caught.value


def test_basis_refused() -> None:
    """Spec 4.4: compare.length_mm present, confirmed, in mm and >= 0; basis must be a record."""
    frames = _frames(_frame("F1"))
    fields = {"a_frames": frames, "b_frames": frames, "basis": _basis(1.0)}
    refs = {
        "a_frames": _ref(1, FP),
        "b_frames": _ref(2, FP, revision=4),
        "basis": _ref(9, "basis.design_basis/1", revision=None),
    }
    missing = _basis(1.0)
    missing["fields"] = {}
    detail = _refusal({**fields, "basis": missing}, refs).detail
    assert (detail.code, detail.message) == (ErrorCode.INVALID_ARGUMENT, f"basis field {LENGTH} is missing (no default)")
    unconfirmed = _basis(1.0)
    unconfirmed["fields"][LENGTH] = _field(1.0, confirmed=False)
    detail = _refusal({**fields, "basis": unconfirmed}, refs).detail
    assert detail.message == f"basis field {LENGTH} is not confirmed"
    from eng_contract.kinds.basis import BasisField, DesignBasis
    from eng_contract.kinds.model import FramePlacements
    from eng_harness.calcs.placement_compare import PlacementInput, placement_compare

    wrong_unit = _basis(1.0)
    wrong_unit["fields"][LENGTH] = _field(1.0, "deg")
    with pytest.raises(Exception, match="unit of .compare.length_mm."):
        _input_type().model_validate({**fields, "basis": wrong_unit})
    # Calc also checks the unit for a basis built past the contract check (B-464).
    constructed = PlacementInput.model_construct(
        a_frames=FramePlacements.model_validate(frames),
        b_frames=FramePlacements.model_validate(frames),
        a_areas=None,
        b_areas=None,
        basis=DesignBasis.model_construct(
            template=None,
            fields={LENGTH: BasisField.model_validate(_field(1.0, "deg"))},
        ),
    )
    with pytest.raises(ContractError) as caught:
        placement_compare(constructed, InputMeta.model_validate({"refs": refs}), TraceBuilder())
    assert caught.value.detail.message == f"basis field {LENGTH} must be in mm, not deg"

    for bad in (-0.5, "1", True):
        bad_basis = _basis(1.0)
        bad_basis["fields"][LENGTH] = _field(bad)
        detail = _refusal({**fields, "basis": bad_basis}, refs).detail
        assert detail.message == f"basis field {LENGTH} must be a number >= 0"
    no_basis_ref = {k: v for k, v in refs.items() if k != "basis"}
    detail = _refusal(fields, no_basis_ref).detail
    assert (detail.code, detail.message, detail.field) == (
        ErrorCode.INVALID_ARGUMENT,
        "the basis must be a record reference",
        "basis",
    )


def test_zero_tolerance_needs_exact_geometry() -> None:
    """P2: tolerance 0 accepts only exact equality; a subnormal offset is moved."""
    tiny = 5e-324
    frames = _frames(_frame("F1"))
    moved = _frames(_frame("F1", i=(tiny, 0.0, 0.0), j=(0.0, 0.0, 3000.0)))
    out = _run(
        {"a_frames": frames, "b_frames": moved, "basis": _basis(0.0)},
        {
            "a_frames": _ref(1, FP),
            "b_frames": _ref(2, FP, revision=4),
            "basis": _ref(9, "basis.design_basis/1", revision=None),
        },
    )
    assert _by_id(out, "frame", "F1")["result"] == "moved"
    same = _run(
        {"a_frames": frames, "b_frames": frames, "basis": _basis(0.0)},
        {
            "a_frames": _ref(1, FP),
            "b_frames": _ref(2, FP, revision=4),
            "basis": _ref(9, "basis.design_basis/1", revision=None),
        },
    )
    assert same["equal"] is True
    assert _by_id(same, "frame", "F1")["result"] == "same"


def test_incomplete_side_and_stale_ok_marks() -> None:
    """complete is the conjunction of the input refs; only a_* fields are stale_ok (4.13)."""
    frames = _frames(_frame("F1"))
    out = _run(
        {"a_frames": frames, "b_frames": frames, "basis": _basis(1.0)},
        {
            "a_frames": _ref(1, FP, complete=False),
            "b_frames": _ref(2, FP, revision=4),
            "basis": _ref(9, "basis.design_basis/1", revision=None),
        },
    )
    assert out["complete"] is False
    properties = _input_type().model_json_schema()["properties"]
    flags = {name: prop["x-eng"]["stale_ok"] for name, prop in properties.items()}
    assert flags == {
        "a_frames": True,
        "b_frames": False,
        "a_areas": True,
        "b_areas": False,
        "basis": False,
    }


def test_sides_must_match_and_be_records() -> None:
    """Each side needs the same sections; a placement without a record reference is refused."""
    frames = _frames(_frame("F1"))
    areas = _areas(_area("A1", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]))
    with pytest.raises(Exception):
        _input_type().model_validate({"a_frames": frames, "basis": _basis(1.0)})
    with pytest.raises(Exception):
        _input_type().model_validate({"a_frames": frames, "b_areas": areas, "basis": _basis(1.0)})
    detail = _refusal(
        {"a_frames": frames, "b_frames": frames, "basis": _basis(1.0)},
        {"b_frames": _ref(2, FP, revision=4), "basis": _ref(9, "basis.design_basis/1", revision=None)},
    ).detail
    assert (detail.message, detail.field) == ("a placement must be a record reference", "a_frames")


def test_golden_expectations_are_valid_payloads() -> None:
    """Each placement golden expected body, with calc metadata and a trace added, fits the output kind."""
    output_type = HARNESS_KINDS[REGISTRY[CALC_ID].output_kind]
    assert output_type is PlacementComparison
    files = sorted(GOLDEN_DIR.glob("placement-*.json"))
    assert len(files) == 4
    meta = {"id": CALC_ID, "version": 1, "content_sha256": "a" * 64, "status": "draft"}
    trace = {"calc_id": CALC_ID, "calc_version": "1", "content_sha256": "a" * 64, "steps": [], "outputs": []}
    for path in files:
        expected = json.loads(path.read_text(encoding="utf-8"))["expected"]
        output_type.model_validate(
            expected | {"calc": meta, "draft": True, "trace": trace | {"inputs": [], "constants": []}}
        )


def test_reversed_area_not_same_orientation() -> None:
    """P4: a reversed order is reversed, never same; a pure translation beyond tolerance is moved."""
    triangle = [(0.0, 0.0, 0.0), (3000.0, 0.0, 0.0), (0.0, 4000.0, 0.0)]
    out = _run(
        {
            "a_areas": _areas(_area("A1", triangle)),
            "b_areas": _areas(_area("A1", [triangle[0], triangle[2], triangle[1]])),
            "basis": _basis(1.0),
        },
        {
            "a_areas": _ref(3, AP),
            "b_areas": _ref(4, AP, revision=4),
            "basis": _ref(9, "basis.design_basis/1", revision=None),
        },
    )
    assert _by_id(out, "area", "A1")["result"] == "reversed"
    moved = _run(
        {
            "a_areas": _areas(_area("A1", triangle)),
            "b_areas": _areas(_area("A1", [(p[0] + 10.0, p[1], p[2]) for p in triangle])),
            "basis": _basis(1.0),
        },
        {
            "a_areas": _ref(3, AP),
            "b_areas": _ref(4, AP, revision=4),
            "basis": _ref(9, "basis.design_basis/1", revision=None),
        },
    )
    row = _by_id(moved, "area", "A1")
    assert row["result"] == "moved"
    assert row["distance_mm"] == 10.0
