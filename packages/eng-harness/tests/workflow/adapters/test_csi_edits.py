"""CSI edit kinds (plan 0002 T12; spec 0002 AC26, section 4.6.2).

Every expected host argument is derived by hand from the spec table: a thickness of 250 mm is 250 with `kN_mm_C` and
0.25 with `kN_m_C`; 12.5 kN/m is 0.0125 kN/mm; the pattern types and combination codes are the tool schema's values.
The adapter imports are inside the tests so a missing module fails the test.
"""

from typing import Any

import pytest
from eng_contract.kinds.model import CombinationItem, CombinationType, LoadDirection, PatternType
from pydantic import JsonValue

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._toolport import Binding
from eng_harness.errors import HarnessCode, NotImplementedGap


def _build(tool: str, model: Any, token: str | None = None) -> dict[str, JsonValue]:
    from eng_harness.adapters.csi import csi_allowlist
    from eng_harness.adapters.csi._edits import EDIT_BUILDERS

    binding = Binding(target=HostTarget(product="ETABS", pid=4242), units_system=token)
    return EDIT_BUILDERS[tool](model, csi_allowlist().descriptor(tool), binding)


def _item(case: str, kind: str, scale: float) -> CombinationItem:
    return CombinationItem.model_validate({"case": {"case": case, "case_type": kind}, "scale_ratio": scale})


def test_edit_kinds() -> None:
    """Each edit kind maps its canonical arguments to the S-12 tool's arguments, in the token's units."""
    from eng_harness.adapters.csi import _edits as e

    assert _build("csi_assign_frame_section", e.AssignFrameSectionArgs(model="m", frame="F1", section="C40")) == {
        "name": "F1",
        "section": "C40",
    }
    assert _build("csi_assign_area_section", e.AssignAreaSectionArgs(model="m", area="A1", section="SL20")) == {
        "name": "A1",
        "section": "SL20",
    }
    wall = e.DefineWallSectionArgs(model="m", name="W1", material="C30", thickness_mm=250.0)
    expected = {
        "name": "W1",
        "material": "C30",
        "thickness": 250.0,
        "wall_type": "Specified",
        "shell_type": "ShellThin",
    }
    assert _build("csi_define_wall_section", wall, "kN_mm_C") == expected  # millimetres: the value is the canonical one
    assert _build("csi_define_wall_section", wall, "kN_m_C")["thickness"] == 0.25
    thick = wall.model_copy(update={"shell_type": e.ShellType.THICK})
    assert _build("csi_define_wall_section", thick, "kN_mm_C")["shell_type"] == "ShellThick"

    frame_load = e.SetFrameLoadDistributedArgs(model="m", frame="F1", pattern="DEAD", w_kN_m=12.5)
    assert _build("csi_set_frame_load_distributed", frame_load, "kN_m_C") == {
        "name": "F1",
        "load_pattern": "DEAD",
        "value": 12.5,
        "direction": "gravity",
    }
    assert _build("csi_set_frame_load_distributed", frame_load, "kN_mm_C")["value"] == 0.0125
    area_load = e.SetAreaLoadUniformArgs(model="m", area="A1", pattern="LIVE", q_kPa=6.25)
    assert _build("csi_set_area_load_uniform", area_load, "kN_m_C") == {
        "name": "A1",
        "load_pattern": "LIVE",
        "value": 6.25,
        "direction": "gravity",
    }

    mapped = {"dead": "Dead", "live": "Live", "seismic": "Quake", "wind": "Wind", "snow": "Snow", "other": "Other"}
    for kind, name in mapped.items():
        pattern = e.AddLoadPatternArgs(model="m", name="P", type=PatternType(kind), self_weight_ratio=1.0)
        assert _build("csi_add_load_pattern", pattern) == {"name": "P", "type": name, "self_weight": 1.0}

    codes = {"linear_add": 0, "envelope": 1, "absolute_add": 2, "srss": 3}
    items = [_item("DEAD", "load_pattern", 1.4), _item("C1", "load_combination", 1.0)]
    for kind, code in codes.items():
        combo = e.AddLoadComboArgs(model="m", name="C2", type=CombinationType(kind), items=items)
        assert _build("csi_add_load_combo", combo) == {
            "name": "C2",
            "combo_type": code,
            "components": [
                {"name": "DEAD", "factor": 1.4, "kind": "case"},
                {"name": "C1", "factor": 1.0, "kind": "combo"},
            ],
        }
    assert _build("csi_delete_load_combo", e.DeleteLoadComboArgs(model="m", name="C2")) == {"name": "C2"}
    restraint = e.SetPointRestraintArgs(model="m", joint="P1", ux=True, uy=False, uz=True, rx=False, ry=True, rz=False)
    assert _build("csi_set_point_restraint", restraint) == {
        "name": "P1",
        "values": [True, False, True, False, True, False],
    }


def test_wrong_model_is_a_defect() -> None:
    """A builder given another tool's model raises `TypeError` and names both."""
    from eng_harness.adapters.csi import _edits as e

    with pytest.raises(
        TypeError, match="csi_delete_load_combo builds from DeleteLoadComboArgs, not AssignFrameSectionArgs"
    ):
        _build("csi_delete_load_combo", e.AssignFrameSectionArgs(model="m", frame="F1", section="C40"))


GAPS = {
    "define_material": "H-G1",
    "define_frame_section": "H-G1",
    "define_area_section": "H-G1",
    "slab_thickness": "H-G1",
    "frame_point_load": "H-G2",
    "change_load_pattern": "OQ-G8",
    "delete_load_pattern": "OQ-G8",
    "seismic_parameters": "OQ-G8",
}


@pytest.mark.parametrize(("edit", "gap"), sorted(GAPS.items()))
def test_gaps_not_implemented(edit: str, gap: str) -> None:
    """An edit kind with no tool, or no mapping, raises `NotImplementedGap` with its gap id (AC26)."""
    from eng_harness.adapters.csi._edits import refuse

    with pytest.raises(NotImplementedGap) as caught:
        refuse(edit)
    assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
    assert caught.value.evidence == (gap,)
    assert edit in caught.value.message


def test_gaps_in_the_arguments() -> None:
    """A direction other than gravity is gap H-G2; a pattern or combination type with no code is gap H-G3."""
    from eng_harness.adapters.csi import _edits as e

    for direction in LoadDirection:
        if direction is LoadDirection.GRAVITY:
            continue
        frame = e.SetFrameLoadDistributedArgs(model="m", frame="F1", pattern="D", direction=direction, w_kN_m=1.0)
        area = e.SetAreaLoadUniformArgs(model="m", area="A1", pattern="D", direction=direction, q_kPa=1.0)
        for tool, model in (("csi_set_frame_load_distributed", frame), ("csi_set_area_load_uniform", area)):
            with pytest.raises(NotImplementedGap) as caught:
                _build(tool, model, "kN_m_C")
            assert caught.value.evidence == ("H-G2",)
            assert direction.value in caught.value.message
    for kind in (PatternType.SUPERIMPOSED_DEAD, PatternType.ROOF_LIVE):
        pattern = e.AddLoadPatternArgs(model="m", name="P", type=kind, self_weight_ratio=0.0)
        with pytest.raises(NotImplementedGap) as caught:
            _build("csi_add_load_pattern", pattern)
        assert caught.value.evidence == ("H-G3",)
        assert kind.value in caught.value.message
    combo = e.AddLoadComboArgs(
        model="m", name="C", type=CombinationType.RANGE, items=[_item("DEAD", "load_pattern", 1.0)]
    )
    with pytest.raises(NotImplementedGap) as caught:
        _build("csi_add_load_combo", combo)
    assert caught.value.evidence == ("H-G3",)
    assert "range" in caught.value.message
