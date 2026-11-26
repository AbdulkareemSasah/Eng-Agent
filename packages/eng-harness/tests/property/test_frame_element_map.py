"""`harness.frame_element_map` is invariant under input permutations (plan 0011 T12; spec 0011 AC28)."""

import copy
from fractions import Fraction
from typing import Any, cast

from eng_contract.canonical import payload_sha256
from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness.calc import CalcInput, CalcStatus, InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.calcs.frame_element_map import _squared
from eng_harness.kinds.calcs import CalcMeta

CALC_ID = "harness.frame_element_map"
KINDS = {
    "frames": "model.frame_placements/1",
    "elements": "model.frame_placements/1",
    "structure": "harness.revit_structure/1",
    "basis": "basis.design_basis/1",
}
META = InputMeta(
    refs={
        name: RefMeta(
            result_id=f"res_01FEM{'0' * 20}{n}",
            ref=f"res_01FEM{'0' * 20}{n}",
            kind=kind,
            complete=True,
            model_id=None if name == "basis" else "mdl_00000000000000000000000000",
            model_revision=None if name == "basis" else n,
            parents=(),
            producer_tool="fixture_tool",
        )
        for n, (name, kind) in enumerate(KINDS.items(), 1)
    }
)
SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"
BASIS = {
    "template": None,
    "fields": {
        "compare.length_mm": {
            "value": 5,
            "unit": "mm",
            "source": SRC,
            "confirmed": True,
            "citation": None,
        },
        "mapping.offset_x_mm": {
            "value": 0,
            "unit": "mm",
            "source": SRC,
            "confirmed": True,
            "citation": None,
        },
        "mapping.offset_y_mm": {
            "value": 0,
            "unit": "mm",
            "source": SRC,
            "confirmed": True,
            "citation": None,
        },
        "mapping.offset_z_mm": {
            "value": 0,
            "unit": "mm",
            "source": SRC,
            "confirmed": True,
            "citation": None,
        },
    },
}
IDS = [f"F{n}" for n in range(6)]
UIDS = [f"U{n}" for n in range(6)]


def _point(x: float, y: float, z: float) -> dict[str, float]:
    return {"x_mm": x, "y_mm": y, "z_mm": z}


@st.composite
def frame_row(draw: st.DrawFn, name: str) -> dict[str, Any]:
    dx = draw(st.integers(-4, 4))
    dy = draw(st.integers(-4, 4))
    height = draw(st.integers(2500, 3500))
    return {
        "id": name,
        "kind": "column",
        "section": "C400",
        "i": _point(float(dx), float(dy), 0.0),
        "j": _point(float(dx), float(dy), float(height)),
        "rotation_deg": 0.0,
    }


@st.composite
def element_row(draw: st.DrawFn, uid: str, element_id: int) -> dict[str, Any]:
    dx = draw(st.integers(-4, 4))
    dy = draw(st.integers(-4, 4))
    height = draw(st.integers(2500, 3500))
    type_id = draw(st.integers(100, 110))
    return {
        "unique_id": uid,
        "element_id": element_id,
        "category": "column",
        "family": "Concrete Rectangular Column",
        "type_id": type_id,
        "type_name": f"T{type_id}",
        "level_id": 1,
        "level_name": "L1",
        "location_kind": "curve",
        "i": _point(float(dx), float(dy), 0.0),
        "j": _point(float(dx), float(dy), float(height)),
        "rotation_deg": 0.0,
        "parameters": {},
    }


@st.composite
def inputs(draw: st.DrawFn) -> dict[str, Any]:
    frame_ids = draw(st.lists(st.sampled_from(IDS), min_size=1, max_size=4, unique=True))
    element_ids = draw(st.lists(st.sampled_from(UIDS), min_size=1, max_size=4, unique=True))
    frames = [draw(frame_row(name)) for name in frame_ids]
    # Element placements reuse the Frame shape (id = unique_id); structure carries host ids.
    element_frames = []
    structure_elements = []
    for index, uid in enumerate(element_ids):
        row = draw(element_row(uid, element_id=1000 + index))
        element_frames.append(
            {
                "id": uid,
                "kind": "column",
                "section": f"{row['family']}: {row['type_name']}",
                "i": row["i"],
                "j": row["j"],
                "rotation_deg": row["rotation_deg"],
            }
        )
        structure_elements.append(row)
    structure_elements = sorted(structure_elements, key=lambda row: row["unique_id"])
    link_pairs = draw(
        st.lists(
            st.tuples(st.sampled_from(element_ids), st.sampled_from(frame_ids)),
            max_size=min(2, len(element_ids), len(frame_ids)),
            unique_by=lambda pair: pair[0],
        )
    )
    links = dict(link_pairs) or None
    return {
        "frames": {"frames": frames},
        "elements": {"frames": element_frames},
        "structure": {"elements": structure_elements, "types": []},
        "links": links,
        "basis": BASIS,
    }


def _run(fields: dict[str, Any]) -> tuple[dict[str, Any], str]:
    definition = REGISTRY[CALC_ID]
    digest = REGISTRY.content_hash(CALC_ID)
    input_type = cast(type[CalcInput], definition.input_type)
    trace = TraceBuilder()
    body = definition(input_type.model_validate(fields), META, trace).model_dump(mode="json")
    from eng_harness.kinds.calcs import FrameElementMap

    payload = body | {
        "calc": CalcMeta(
            id=CALC_ID, version=definition.version, content_sha256=digest, status=CalcStatus.DRAFT
        ).model_dump(mode="json"),
        "draft": True,
        "trace": trace.build(definition, digest).model_dump(mode="json"),
    }
    FrameElementMap.model_validate(payload)
    return payload, payload_sha256(payload)


@settings(derandomize=True, max_examples=40, deadline=None)
@given(inputs(), st.data())
def test_permutation_invariant(fields: dict[str, Any], data: st.DataObject) -> None:
    mixed = copy.deepcopy(fields)
    mixed["frames"]["frames"] = data.draw(st.permutations(mixed["frames"]["frames"]))
    mixed["elements"]["frames"] = data.draw(st.permutations(mixed["elements"]["frames"]))
    # harness.revit_structure/1 requires elements sorted by unique_id (spec 0011 §4.5); only valid inputs.
    if mixed["links"] is not None:
        items = list(mixed["links"].items())
        mixed["links"] = dict(data.draw(st.permutations(items)))
    assert _run(mixed) == _run(fields)


@settings(derandomize=True, max_examples=40, deadline=None)
@given(st.fractions(min_value=-100, max_value=100), st.fractions(min_value=-100, max_value=100))
def test_squared_distance_is_exact(scale: Fraction, origin: Fraction) -> None:
    # A scaled 3-4-5 triangle in x/y, with an equal 5-unit separation in z, has d² = 50 * scale².
    a = (origin, origin, origin)
    b = (origin + 3 * scale, origin - 4 * scale, origin + 5 * scale)
    distance_sq = _squared(a, b)
    assert isinstance(distance_sq, Fraction)
    assert distance_sq == 50 * scale**2
