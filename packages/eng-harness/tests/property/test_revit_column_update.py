"""`harness.revit_column_update` is invariant under the U10 input permutations (plan 0013 T7; spec 0013 AC11)."""

import copy
from typing import Any, cast

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness.calc import CalcInput, CalcStatus, InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.kinds.calcs import CalcMeta
from eng_harness.kinds.column_design import RevitColumnUpdate

CALC_ID = "harness.revit_column_update"
KINDS = {
    "map": "harness.frame_element_map/1",
    "frames": "model.frame_placements/1",
    "sections": "model.sections/1",
    "revit": "harness.revit_structure/1",
    "revit_placements": "model.frame_placements/1",
    "changed": "harness.column_design_record/1",
    "basis": "basis.design_basis/1",
}
REFS = {name: f"res_01KCD{'0' * 20}{n}" for n, name in enumerate(KINDS, 1)}
BY_ID = {result_id: name for name, result_id in REFS.items()}
META = InputMeta(
    refs={
        name: RefMeta(
            result_id=result_id,
            ref=result_id + "#/changed" if name == "changed" else result_id,
            kind=kind,
            complete=True,
            model_id=None,
            model_revision=None,
            parents=(),
            producer_tool="fixture_tool",
        )
        for name, kind, result_id in ((n, KINDS[n], REFS[n]) for n in KINDS)
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
SHA = "c" * 64
DIMS = [(300, 300), (400, 400), (500, 500), (400, 600), (300, 500), (600, 400)]
FAR = [(700, 700), (800, 800), (700, 800), (800, 700)]
ROTATIONS = [0, 90, 180, 270]
ROLE_FIELD = {"section_b": "b_mm", "section_h": "h_mm", "section_D": "D_mm"}


def _calc_header(calc_id: str) -> dict[str, Any]:
    return {
        "calc": {"id": calc_id, "version": 1, "content_sha256": SHA, "status": "draft"},
        "draft": True,
        "trace": {
            "calc_id": calc_id,
            "calc_version": "1",
            "content_sha256": SHA,
            "inputs": [],
            "constants": [],
            "steps": [],
            "outputs": [],
        },
    }


@st.composite
def _revit_inputs(draw: st.DrawFn) -> dict[str, Any]:
    n = draw(st.integers(1, 3))
    frame_ids = [f"C{i + 1}" for i in range(n)]
    unique_ids = draw(st.permutations([f"u-{i + 1}" for i in range(n)]))
    n_sections = draw(st.integers(1, n))
    dims = draw(st.lists(st.sampled_from(DIMS), min_size=n_sections, max_size=n_sections, unique=True))
    sections = [
        {"name": f"S{i + 1}", "material": "C30", "shape": {"type": "rectangular", "b_mm": b, "h_mm": h}}
        for i, (b, h) in enumerate(dims)
    ]
    names = [row["name"] for row in sections]
    pair_sections = [draw(st.sampled_from(names)) for _ in range(n)]
    pair_families = [draw(st.sampled_from(["F1", "F2"])) for _ in range(n)]
    target_dims = {row["name"]: (row["shape"]["b_mm"], row["shape"]["h_mm"]) for row in sections}
    elements: list[dict[str, Any]] = []
    types: list[dict[str, Any]] = []
    for i in range(n):
        b_mm, h_mm = target_dims[pair_sections[i]] if draw(st.booleans()) else draw(st.sampled_from(FAR))
        elements.append(
            {
                "unique_id": unique_ids[i],
                "element_id": 101 + i,
                "category": "column",
                "family": pair_families[i],
                "type_id": 11 + i,
                "type_name": f"T{i + 1}",
                "level_id": 1,
                "level_name": "L1",
                "location_kind": "point",
                "i": None,
                "j": None,
                "rotation_deg": draw(st.sampled_from(ROTATIONS)),
                "parameters": {},
            }
        )
        types.append(
            {
                "type_id": 11 + i,
                "family": pair_families[i],
                "name": f"T{i + 1}",
                "instance_ids": [101 + i],
                "parameters": {
                    "section_b": {"value": float(b_mm), "unit": "mm"},
                    "section_h": {"value": float(h_mm), "unit": "mm"},
                },
            }
        )
    elements.sort(key=lambda row: row["unique_id"])
    return {
        "map": _calc_header("harness.frame_element_map")
        | {
            "pairs": [
                {
                    "frame_id": frame_ids[i],
                    "unique_id": unique_ids[i],
                    "element_id": 101 + i,
                    "type_id": 11 + i,
                    "basis": "geometry",
                    "lower_distance_mm": 0.0,
                    "upper_distance_mm": 0.0,
                }
                for i in range(n)
            ],
            "ambiguous": [],
            "unmatched_frames": [],
            "unmatched_elements": [],
            "conflicts": [],
            "complete": True,
        },
        "frames": {
            "frames": [
                {
                    "id": frame_ids[i],
                    "kind": "other",
                    "section": pair_sections[i],
                    "i": {"x_mm": 6000 * i, "y_mm": 0, "z_mm": 0},
                    "j": {"x_mm": 6000 * i, "y_mm": 0, "z_mm": 3000},
                    "story": "L1",
                    "rotation_deg": draw(st.sampled_from(ROTATIONS)),
                }
                for i in range(n)
            ]
        },
        "sections": {"frame_sections": sections, "area_sections": []},
        "revit": {"elements": elements, "types": types},
        "role_statuses": {family: {"section_b": "reference", "section_h": "reference"} for family in ("F1", "F2")},
        "revit_placements": {
            "frames": [
                {
                    "id": unique_ids[i],
                    "kind": "column",
                    "section": f"{pair_families[i]}: T{i + 1}",
                    "i": {"x_mm": 6000 * i, "y_mm": 0, "z_mm": 0},
                    "j": {"x_mm": 6000 * i, "y_mm": 0, "z_mm": 3000},
                    "story": "L1",
                    "rotation_deg": draw(st.sampled_from(ROTATIONS)),
                }
                for i in range(n)
            ]
        },
        "changed": [
            {"frame_id": frame_ids[i], "from_section": "Sold", "to_section": pair_sections[i]}
            for i in range(n)
            if draw(st.booleans())
        ],
        "basis": BASIS,
    }


def _run(fields: dict[str, Any]) -> dict[str, Any]:
    definition = REGISTRY[CALC_ID]
    digest = REGISTRY.content_hash(CALC_ID)
    input_type = cast(type[CalcInput], definition.input_type)
    trace = TraceBuilder()
    body = definition(input_type.model_validate(fields), META, trace).model_dump(mode="json")
    payload = body | {
        "calc": CalcMeta(
            id=CALC_ID, version=definition.version, content_sha256=digest, status=CalcStatus.DRAFT
        ).model_dump(mode="json"),
        "draft": True,
        "trace": trace.build(definition, digest).model_dump(mode="json"),
    }
    RevitColumnUpdate.model_validate(payload)
    return body


def _normalize(body: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """Replace every reference with its input, row key and field (spec 0013 U10).

    Each reference must resolve to its intended field: a U1 role reference to the new type's
    ETABS section row and the role's shape field, an orientation row to the ETABS frame row by
    frame_id first and the Revit row by unique_id second.
    """
    section_names = [row["name"] for row in fields["sections"]["frame_sections"]]
    etabs_ids = [row["id"] for row in fields["frames"]["frames"]]
    revit_ids = [row["id"] for row in fields["revit_placements"]["frames"]]
    frame_to_unique = {pair["frame_id"]: pair["unique_id"] for pair in fields["map"]["pairs"]}
    assert [(row["family"], row["name"]) for row in body["expected"]["types"]] == [
        (row["family"], row["name"]) for row in body["new_types"]
    ], "U7/U9: expected.types holds one row per new type in new_types order"

    def _record(ref: str) -> tuple[str, str]:
        result_id, _, pointer = ref.partition("#")
        assert result_id in BY_ID, f"reference to an unknown record: {ref}"
        return BY_ID[result_id], pointer

    def _u1_token(role: str, ref: str, section: str) -> str:
        name, pointer = _record(ref)
        parts = pointer.split("/")
        assert name == "sections", f"U1: {role} must reference sections, not {name}: {ref}"
        assert len(parts) == 5, f"U1 pointer must be /frame_sections/<i>/shape/<field>: {ref}"
        assert parts[1] == "frame_sections", f"U1 pointer must be /frame_sections/<i>/shape/<field>: {ref}"
        assert parts[2].isdigit(), f"U1 pointer must be /frame_sections/<i>/shape/<field>: {ref}"
        assert parts[3] == "shape", f"U1 pointer must be /frame_sections/<i>/shape/<field>: {ref}"
        index = int(parts[2])
        assert 0 <= index < len(section_names), f"U1 section index out of range: {ref}"
        assert section_names[index] == section, f"U1 must resolve to section {section}: {ref}"
        assert parts[4] == ROLE_FIELD[role], f"U1: {role} must reference {ROLE_FIELD[role]}: {ref}"
        return f"sections/{section}/{parts[4]}"

    def _u5_tokens(row: dict[str, Any]) -> list[str]:
        frame_id = row["frame_id"]
        assert len(row["rotations"]) == 2, f"U5: two rotation references: {row}"
        first, second = row["rotations"]
        name, pointer = _record(first)
        parts = pointer.split("/")
        assert name == "frames", f"U5: the first rotation must reference the ETABS frames: {first}"
        assert len(parts) == 4, f"U5 pointer must be /frames/<i>/rotation_deg: {first}"
        assert parts[1] == "frames", f"U5 pointer must be /frames/<i>/rotation_deg: {first}"
        assert parts[2].isdigit(), f"U5 pointer must be /frames/<i>/rotation_deg: {first}"
        assert parts[3] == "rotation_deg", f"U5 pointer must be /frames/<i>/rotation_deg: {first}"
        assert etabs_ids[int(parts[2])] == frame_id, f"U5: the first rotation must be row {frame_id}: {first}"
        name, pointer = _record(second)
        parts = pointer.split("/")
        assert name == "revit_placements", f"U5: the second rotation must reference revit_placements: {second}"
        assert len(parts) == 4, f"U5 pointer must be /frames/<j>/rotation_deg: {second}"
        assert parts[1] == "frames", f"U5 pointer must be /frames/<j>/rotation_deg: {second}"
        assert parts[2].isdigit(), f"U5 pointer must be /frames/<j>/rotation_deg: {second}"
        assert parts[3] == "rotation_deg", f"U5 pointer must be /frames/<j>/rotation_deg: {second}"
        unique_id = frame_to_unique[frame_id]
        assert revit_ids[int(parts[2])] == unique_id, f"U5: the second rotation must be row {unique_id}: {second}"
        return [f"frames/{frame_id}/rotation_deg", f"revit_placements/{unique_id}/rotation_deg"]

    normalized = copy.deepcopy(body)
    for row in normalized["new_types"]:
        row["roles"] = {role: _u1_token(role, ref, row["section"]) for role, ref in row["roles"].items()}
    new_sections = {(row["family"], row["name"]): row["section"] for row in body["new_types"]}
    for row in normalized["expected"]["types"]:
        section = new_sections[(row["family"], row["name"])]
        row["roles"] = {role: _u1_token(role, ref, section) for role, ref in row["roles"].items()}
    for row in normalized["orientation"]:
        row["rotations"] = _u5_tokens(row)
    return normalized


@settings(derandomize=True, max_examples=60, deadline=None)
@given(_revit_inputs(), st.data())
def test_permutation_invariant(fields: dict[str, Any], data: st.DataObject) -> None:
    """U10: permuting frames, revit_placements, sections and changed keeps the plan identical.

    The map and the Revit structure stay in the order their kinds require. Raw reference strings
    may differ (U1 and U5 pointers use the actual input row indices), so the plans are compared
    after resolving each reference against its own run's input.
    """
    mixed = copy.deepcopy(fields)
    mixed["frames"]["frames"] = data.draw(st.permutations(mixed["frames"]["frames"]))
    mixed["revit_placements"]["frames"] = data.draw(st.permutations(mixed["revit_placements"]["frames"]))
    mixed["sections"]["frame_sections"] = data.draw(st.permutations(mixed["sections"]["frame_sections"]))
    mixed["changed"] = data.draw(st.permutations(mixed["changed"]))
    first, second = _run(fields), _run(mixed)
    assert first["complete"] is True  # U8: every referenced record is complete
    assert second["complete"] is True
    assert _normalize(first, fields) == _normalize(second, mixed)
