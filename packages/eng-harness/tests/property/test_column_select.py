"""`harness.column_select` is invariant under permutations of its lists (plan 0013 T2; spec 0013 AC5)."""

import copy
from typing import Any, cast

from eng_contract.canonical import payload_sha256
from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness.calc import CalcInput, InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY

CALC_ID = "harness.column_select"
KINDS = {
    "scope": "basis.engineer_input/1",
    "frames": "model.frame_placements/1",
    "sections": "model.sections/1",
    "basis": "basis.design_basis/1",
}
META = InputMeta(
    refs={
        name: RefMeta(
            result_id=f"res_01KCC{'0' * 20}{n}",
            kind=kind,
            complete=True,
            model_id=None,
            model_revision=None,
            parents=(),
            producer_tool="fixture_tool",
        )
        for n, (name, kind) in enumerate(KINDS.items(), 1)
    }
)
BASIS = {
    "template": None,
    "fields": {
        "compare.length_mm": {
            "value": 5,
            "unit": "mm",
            "source": "engineer:trial@2026-11-01T00:00:00.000Z",
            "confirmed": True,
            "citation": None,
        }
    },
}
SECTIONS = [
    {"name": "C40", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 600}},
    {"name": "C50", "material": "C35", "shape": {"type": "circular", "D_mm": 500}},
    {"name": "W1", "material": "S355", "shape": {"type": "other", "host_shape": "SD Section"}},
]
STORIES = ["L1", "L2", "L3"]
NAMES = st.lists(st.sampled_from([f"F{n}" for n in range(8)]), min_size=1, max_size=8, unique=True)


@st.composite
def frame(draw: st.DrawFn, name: str) -> dict[str, Any]:
    dx, dy = draw(st.integers(-6, 6)), draw(st.integers(-6, 6))  # around the 5 mm tolerance: some in, some out
    z = draw(st.integers(1000, 4000))
    return {
        "id": name,
        "kind": "other",
        "section": draw(st.sampled_from([s["name"] for s in SECTIONS])),
        "i": {"x_mm": 0, "y_mm": 0, "z_mm": 0},
        "j": {"x_mm": dx, "y_mm": dy, "z_mm": z},
        "story": draw(st.sampled_from(STORIES)),
        "rotation_deg": 0,
    }


@st.composite
def inputs(draw: st.DrawFn) -> dict[str, Any]:
    names = draw(NAMES)
    frames = [draw(frame(name)) for name in names]
    if draw(st.booleans()):
        scope: dict[str, Any] = {"frames": draw(st.lists(st.sampled_from([*names, "X1", "X2"]), min_size=1))}
    else:
        stories = draw(st.none() | st.lists(st.sampled_from([*STORIES, "L9"]), min_size=1, unique=True))
        sections = draw(st.lists(st.sampled_from(["C40", "C50", "W1", "NOPE"]), min_size=1, unique=True))
        scope = {"select": {"stories": stories, "sections": sections}}
    scope |= {"combinations": ["ULS1"], "special_seismic": False}
    return {
        "scope": scope,
        "frames": {"frames": frames},
        "sections": {"frame_sections": copy.deepcopy(SECTIONS), "area_sections": []},
        "basis": BASIS,
    }


def _run(fields: dict[str, Any]) -> tuple[dict[str, Any], str, Any]:
    definition = REGISTRY[CALC_ID]
    input_type = cast(type[CalcInput], definition.input_type)
    trace = TraceBuilder()
    body = definition(input_type.model_validate(fields), META, trace).model_dump(mode="json")
    return body, payload_sha256(body), trace.build(definition, "ab" * 32).model_dump(mode="json")


@settings(derandomize=True, max_examples=60, deadline=None)
@given(inputs(), st.data())
def test_permutation_invariant(fields: dict[str, Any], data: st.DataObject) -> None:
    mixed = copy.deepcopy(fields)
    mixed["frames"]["frames"] = data.draw(st.permutations(mixed["frames"]["frames"]))
    mixed["sections"]["frame_sections"] = data.draw(st.permutations(mixed["sections"]["frame_sections"]))
    scope = mixed["scope"]
    if "frames" in scope:
        scope["frames"] = data.draw(st.permutations(scope["frames"]))
    else:
        for key in ("stories", "sections"):
            if scope["select"][key] is not None:
                scope["select"][key] = data.draw(st.permutations(scope["select"][key]))
    assert _run(mixed) == _run(fields)
