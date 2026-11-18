"""CSI reply mapping to neutral kinds (plan 0002 T11; spec 0002 AC27, section 4.6.4)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds import NEUTRAL_KINDS
from eng_contract.kinds.forces import JointReactions, MemberEnd, StoryDrifts
from eng_contract.kinds.model import (
    AreaKind,
    AreaPlacements,
    CombinationType,
    FrameKind,
    FramePlacements,
    GridSystem,
    JointRestraints,
    LoadDirection,
    LoadSet,
    PatternType,
    Stories,
)

from eng_harness.adapters.csi import _replies
from eng_harness.adapters.csi._replies import (
    CsiModelStatus,
    area_section_kinds,
    areas,
    frames,
    grids,
    load_set,
    model_status,
    restraints,
    stories,
)
from eng_harness.adapters.csi.products import _etabs

UNITS = "kN_m_C"  # present units token of the synthetic fake (S-12); length `m`, stress `kN/m2`, line load `kN/m`


def _mm(metres: float) -> float:
    """Hand check: `kN_m_C` length is metres (eng-contract spec 4.7.4, `CsiUnitSystem.length`)."""
    return metres * 1000.0


def test_six_kinds_and_status_validate() -> None:
    """Each mapper accepts Sasaah-shaped replies and the payloads validate under the contract kinds."""
    story_rows = [
        {"name": "Basement", "elevation": 0.0, "height": 4.0, "is_master": True, "similar_to": None},
        {"name": "Mezz", "elevation": 4.25, "height": 2.75, "is_master": False, "similar_to": "Basement"},
        {"name": "Roof", "elevation": 8.5, "height": 3.0, "is_master": False, "similar_to": None},
    ]
    grid_rows = [
        {
            "name": "Skewed",
            "type": "Cartesian",
            "origin": [2.5, 7.25],
            "rotation_deg": 15.0,
            "x_lines": [{"id": "3", "ordinate": 3.25, "visible": True}],
            "y_lines": [{"id": "B", "ordinate": -1.5, "visible": False}],
        }
    ]
    frame_rows = [
        {
            "name": "B1",
            "label": "B1",
            "point1": [1.2, 3.4, 0.5],
            "point2": [5.7, 3.4, 4.1],
            "section": "W14X30",
            "story": "Mezz",
        }
    ]
    area_rows = [
        {
            "name": "SlabA",
            "points": [[0.0, 0.0, 0.0], [6.5, 0.0, 0.0], [2.0, 4.75, 0.0]],
            "section": "SLAB8",
        }
    ]
    area_section_rows = [{"name": "SLAB8", "type": "slab", "thickness": 0.21, "material": "C35"}]
    pattern_rows = [{"name": "DEAD", "type": "Dead", "self_weight": 1.0}]
    combo_rows = [{"name": "1.4D", "type": 0, "items": [{"name": "DEAD", "factor": 1.4, "kind": "case"}]}]
    pattern_table = [{"Name": "DEAD", "Type": "Dead", "SelfWtMultpl": 1.0}]
    combo_table = [{"Name": "1.4D", "Type": "Linear Add"}]
    frame_load_rows = [{"Frame": "B1", "LoadPattern": "DEAD", "Value": 12.5}]
    area_load_rows = [{"UniqueName": "SlabA", "LoadPattern": "DEAD", "Value": 6.25}]
    restraint_rows = [{"UniqueName": "J1", "Ux": True, "Uy": False, "Uz": True, "Rx": False, "Ry": True, "Rz": False}]
    info = {
        "units": UNITS,
        "locked": False,
        "object_counts": {"stories": 3, "frames": 1, "areas": 1},
        "program_version": "22.1.0",
    }

    stories_payload = stories(story_rows, UNITS)
    grid_payload = grids(grid_rows, UNITS)
    frame_payload = frames(frame_rows, UNITS)
    area_payload = areas(area_rows, UNITS, area_section_kinds(area_section_rows))
    load_payload = load_set(
        pattern_rows,
        combo_rows,
        pattern_table,
        combo_table,
        frame_load_rows,
        area_load_rows,
        UNITS,
    )
    joint_payload = restraints(restraint_rows)
    status_payload = model_status(info, Path("/runs/demo/tower.EDB"))

    for kind, payload in (
        ("model.stories/1", stories_payload),
        ("model.grid_system/1", grid_payload),
        ("model.frame_placements/1", frame_payload),
        ("model.area_placements/1", area_payload),
        ("model.load_set/1", load_payload),
        ("model.joint_restraints/1", joint_payload),
        ("harness.csi_model_status/1", status_payload),
    ):
        kind_model = NEUTRAL_KINDS[kind] if kind.startswith("model.") else CsiModelStatus
        kind_model.model_validate(payload.model_dump())

    assert isinstance(stories_payload, Stories)
    assert stories_payload.base_elevation_mm == pytest.approx(_mm(-4.0))
    mezz = next(s for s in stories_payload.stories if s.name == "Mezz")
    assert mezz.elevation_mm == pytest.approx(_mm(4.25))
    assert mezz.height_mm == pytest.approx(_mm(2.75))
    assert mezz.similar_to == "Basement"

    assert isinstance(grid_payload, GridSystem)
    grid_system = grid_payload.systems[0]
    assert grid_system.origin_x_mm == pytest.approx(_mm(2.5))
    assert grid_system.origin_y_mm == pytest.approx(_mm(7.25))
    assert grid_system.rotation_deg == 15.0
    x_line = next(line for line in grid_system.lines if line.axis.value == "x")
    y_line = next(line for line in grid_system.lines if line.axis.value == "y")
    assert x_line.coordinate_mm == pytest.approx(_mm(3.25))
    assert y_line.coordinate_mm == pytest.approx(_mm(-1.5))
    assert y_line.visible is False

    assert isinstance(frame_payload, FramePlacements)
    frame = frame_payload.frames[0]
    assert frame.kind is FrameKind.OTHER
    assert frame.i.x_mm == pytest.approx(_mm(1.2))
    assert frame.j.z_mm == pytest.approx(_mm(4.1))
    assert frame.story == "Mezz"

    assert isinstance(area_payload, AreaPlacements)
    area = area_payload.areas[0]
    assert area.kind is AreaKind.SLAB
    assert len(area.points) == 3
    assert area.points[2].y_mm == pytest.approx(_mm(4.75))

    assert isinstance(load_payload, LoadSet)
    assert load_payload.patterns[0].type is PatternType.DEAD
    assert load_payload.combinations[0].type is CombinationType.LINEAR_ADD
    assert load_payload.frame_loads[0].direction is LoadDirection.GRAVITY
    assert load_payload.frame_loads[0].w_kN_m == pytest.approx(12.5)
    assert load_payload.area_loads[0].q_kPa == pytest.approx(6.25)

    assert isinstance(joint_payload, JointRestraints)
    joint = joint_payload.joints[0]
    assert joint.joint == "J1"
    assert joint.ux is True
    assert joint.uy is False
    assert joint.ry is True

    assert isinstance(status_payload, CsiModelStatus)
    assert status_payload.units == UNITS
    assert status_payload.file_name == "tower.EDB"
    assert status_payload.object_counts["frames"] == 1


def test_two_value_point_is_refused() -> None:
    row = {"name": "B1", "point1": [1.0, 2.0], "point2": [0.0, 0.0, 1.0], "section": "W14"}
    with pytest.raises(ContractError) as refused:
        frames([row], UNITS)
    assert refused.value.detail.field == "point1"


_POINT = {"point1": [0.0, 0.0, 0.0], "point2": [0.0, 0.0, 3.0]}
_PATTERNS: list[dict[str, Any]] = [{"name": "DEAD", "type": "Dead", "self_weight": 1.0}]
_DRIFT_Z = {"story": "S1", "case": "EQ", "direction": "Z", "drift": 0.1}
_NO_TORSION = {"frame": "B1", "case": "D", "P": 1, "V2": 1, "V3": 1}
_NOT_A_ROW: list[Any] = [1]  # a list entry that is no object: `.get` on it is an `AttributeError`


def _combos(items: list[dict[str, Any]]) -> Callable[[], object]:
    return lambda: load_set(_PATTERNS, [{"name": "C1", "type": 0, "items": items}], [], [], [], [], UNITS)


@pytest.mark.parametrize(
    ("call", "field", "text"),
    [
        (
            lambda: stories([{"name": "S1", "height": 3.0}], UNITS),
            "rows",
            "stories: the host reply has no field elevation",
        ),
        (lambda: grids([{"type": "Cartesian"}], UNITS), "rows", "grids: the host reply has no field name"),
        (lambda: frames([{"name": "B1", **_POINT}], UNITS), "rows", "no field section"),
        (lambda: areas([{"name": "A1", "points": []}], UNITS, {}), "rows", "no field section"),
        (_combos([{"name": "DEAD"}]), "rows", "no field factor"),
        (_combos([{"name": "NOPE", "factor": 1.0}]), "rows", "load_set: a value"),  # a combination item naming nothing
        (lambda: restraints(_NOT_A_ROW), "rows", "restraints: a value"),
        (lambda: model_status({"object_counts": {"frames": "many"}}, None), "rows", "model_status: a value"),
        (lambda: area_section_kinds([{"type": "slab"}]), "rows", "no field name"),
        (lambda: _replies.analysis_run({}), "rows", "analysis_run: the host reply has no field started"),
        (lambda: _replies.analysis_run({"started": "yes"}), "rows", "analysis_run: a value"),  # not a boolean: no guess
        (lambda: _replies.analysis_status({"cases": 5}), "cases", "field cases"),
        (lambda: _replies.analysis_status({"cases": [{"case": "DEAD"}]}), "rows", "no field status_code"),
        (
            lambda: _replies.analysis_status({"cases": [{"case": "DEAD", "status_code": 4.5}]}),
            "rows",
            "analysis_status",
        ),
        (lambda: _replies.design_results({"items": [1]}), "items", "field items"),
        (lambda: _replies.design_results({}), "items", "field items"),
        (lambda: _replies.analysis_messages({"rows": "none"}), "rows", "field rows"),
        (lambda: _replies.joint_reactions({"items": [{"joint": "J1", "case": "DEAD"}]}, UNITS), "rows", "no field F1"),
        (lambda: _replies.joint_reactions({"items": _NOT_A_ROW}, UNITS), "items", "field items"),
        (lambda: _replies.member_forces({"items": [_NO_TORSION]}, UNITS), "rows", "no field T"),
        (lambda: _replies.story_drifts({"items": [_DRIFT_Z]}, UNITS), "rows", "story_drifts: a value"),  # not X or Y
    ],
)
def test_mappers_raise_unexpected_reply(call: Callable[[], object], field: str, text: str) -> None:
    """A missing or unusable reply value is `HOST_ERROR` `UNEXPECTED_REPLY` that names it, from every mapper."""
    with pytest.raises(ContractError) as refused:
        call()
    detail = refused.value.detail
    assert (detail.code, detail.host_code, detail.retryable, detail.field) == (
        ErrorCode.HOST_ERROR,
        "UNEXPECTED_REPLY",
        False,
        field,
    )
    assert text in detail.message


def test_combination_item_kinds() -> None:
    """A combination item whose host `kind` is `combo` names a combination; `case` or no kind names a pattern."""
    combos = [
        {
            "name": "C1", "type": 0,
            "items": [{"name": "DEAD", "factor": 1.4, "kind": "case"}, {"name": "DEAD", "factor": 1.0}],
        },
        {"name": "C2", "type": 0, "items": [{"name": "C1", "factor": 1.0, "kind": "combo"}]},
    ]  # fmt: skip
    loads = load_set(_PATTERNS, combos, [], [], [], [], UNITS)
    kinds = [[(i.case.case, i.case.case_type.value, i.scale_ratio) for i in c.items] for c in loads.combinations]
    assert kinds == [[("DEAD", "load_pattern", 1.4), ("DEAD", "load_pattern", 1.0)], [("C1", "load_combination", 1.0)]]


def test_force_mappers_convert_to_canonical() -> None:
    """Forces in `kN_mm_C` are kN and moments kN.mm are x0.001 kN.m; `kN_m_C` lengths are x1000 mm."""
    mm = "kN_mm_C"
    row = {"joint": "J1", "case": "DEAD", "F1": 1.5, "F2": -2.0, "F3": 120.25, "M1": 500.0, "M2": -250.0, "M3": 0.0}
    reactions = _replies.joint_reactions({"items": [row]}, mm)
    assert isinstance(reactions, JointReactions)
    assert reactions.axes == "global"
    got = reactions.rows[0]
    assert (got.joint, got.case.case, got.case.case_type.value, got.case.step) == ("J1", "DEAD", "load_case", None)
    assert (got.FX_kN, got.FY_kN, got.FZ_kN) == (1.5, -2.0, 120.25)
    assert (got.MX_kNm, got.MY_kNm, got.MZ_kNm) == (0.5, -0.25, 0.0)

    frame = {
        "frame": "B1", "case": "1.4D", "kind": "combo", "step": "Max", "end": "j", "station": 1250.0,
        "P": -10.0, "V2": 4.5, "V3": 0.5, "T": 100.0, "M2": 200.0, "M3": -7750.0,
    }  # fmt: skip
    rows = [frame, {**frame, "end": "mid", "step": "", "kind": "case"}, {**frame, "end": "i", "step": None}]
    forces = _replies.member_forces({"items": rows}, mm)
    assert isinstance(forces, MemberEnd)
    assert forces.sign_convention == "host_local/1"
    first, second, third = forces.rows
    assert (third.end, third.case.step) == ("i", None)
    assert (first.member, first.end, first.station_mm) == ("B1", "j", 1250.0)
    assert (first.case.case_type.value, first.case.step) == ("load_combination", "Max")
    assert (first.P_kN, first.V2_kN, first.V3_kN) == (-10.0, 4.5, 0.5)
    assert (first.T_kNm, first.M2_kNm, first.M3_kNm) == (0.1, 0.2, -7.75)
    assert (second.end, second.case.case_type.value, second.case.step) == (None, "load_case", None)  # not i or j

    metres = _replies.member_forces({"items": [{**frame, "station": 1.25}]}, "kN_m_C")
    assert metres.rows[0].station_mm == 1250.0
    assert metres.rows[0].M3_kNm == -7750.0  # kN.m stays kN.m

    drift = {
        "story": "S1",
        "case": "EQX",
        "direction": "X",
        "drift": 0.0025,
        "label": "J2",
        "x": 5.0,
        "y": 0.0,
        "z": 3.0,
    }
    bare_row = {"story": "S2", "case": "EQX", "direction": "Y", "drift": 0.0}
    drifts = _replies.story_drifts({"items": [drift, bare_row]}, "kN_m_C")
    assert isinstance(drifts, StoryDrifts)
    near, bare = drifts.rows
    assert (near.drift_ratio, near.point, near.x_mm, near.y_mm, near.z_mm) == (0.0025, "J2", 5000.0, 0.0, 3000.0)
    assert (bare.direction, bare.point, bare.x_mm, bare.y_mm, bare.z_mm) == ("Y", None, None, None, None)


def test_raw_host_output_is_kept() -> None:
    """Status codes, design rows and analysis messages are stored as the host gave them: not decoded, not judged."""
    status = _replies.analysis_status(
        {"cases": [{"case": "DEAD", "status_code": 4}, {"case": "LIVE", "status_code": 0}]}
    )
    assert [(c.case, c.status_code) for c in status.cases] == [("DEAD", 4), ("LIVE", 0)]
    assert _replies.analysis_run({"started": True}).started is True
    assert _replies.design_run({"kind": "steel", "completed": True}).reply == {"kind": "steel", "completed": True}
    row = {"frame": "B1", "ratio": 0.75, "combo": "1.4D"}
    assert _replies.design_results({"items": [row], "truncated": False}).rows == [row]
    message = {"Message": "Joint J1 is unrestrained", "Type": "Warning"}
    assert _replies.analysis_messages({"rows": [message], "truncated": False}).rows == [message]
    assert _etabs.ANALYSIS_MESSAGES == "Analysis Messages"
    assert set(_replies.CSI_KINDS) == {
        "harness.csi_model_status/1",
        "harness.csi_analysis_run/1",
        "harness.csi_analysis_status/1",
        "harness.csi_design_run/1",
        "harness.csi_design_results/1",
        "harness.csi_analysis_messages/1",
    }
