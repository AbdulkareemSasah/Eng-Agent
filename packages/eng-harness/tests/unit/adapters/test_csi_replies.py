"""CSI reply mapping to neutral kinds (plan 0002 T11; spec 0002 AC27, section 4.6.4)."""

from pathlib import Path

import pytest
from eng_contract.errors import ContractError
from eng_contract.kinds import NEUTRAL_KINDS
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
