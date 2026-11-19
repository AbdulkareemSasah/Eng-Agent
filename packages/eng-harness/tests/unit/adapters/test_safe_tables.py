"""SAFE table readers, field maps and soil-support kinds (plan 0008 T4; spec 0008 AC11, AC12, AC13, section 4.5).

Every host field name and status comes from spec 0008 section 4.5 (SAFE 22 reference keys, or the candidate lists
cited there). Units are converted only through `eng_contract.units.csi_unit_system` (spec 0008 section 4.5).
"""

from __future__ import annotations

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.issues import Severity
from eng_contract.kinds.model import AreaSectionKind, MaterialType, Sections
from eng_contract.verdicts import SubjectKind

from eng_harness._kinds import SafeSoilSupports
from eng_harness.adapters.csi import _tables
from eng_harness.adapters.csi.products import _safe_state
from eng_harness.errors import HarnessCode, NotImplementedGap

UNITS = "kN_m_C"  # present units of the synthetic CSI fake (S-12); length m, stress kN/m2, unit weight kN/m3


def _slab_rows() -> list[dict[str, Any]]:
    # Host keys from spec 0008 section 4.5 (`Slab Property Definitions`); PropType values from AC11.
    return [
        {"Name": "S200", "PropType": "Slab", "Material": "C30", "Thickness": 0.20},
        {"Name": "DROP1", "PropType": "Drop", "Material": "C30", "Thickness": 0.40},
        {"Name": "STIFF1", "PropType": "Stiff", "Material": "C30", "Thickness": 0.50},
        {"Name": "MAT1", "PropType": "Mat", "Material": "C30", "Thickness": 0.80},
        {"Name": "FOOT1", "PropType": "Footing", "Material": "C30", "Thickness": 0.60},
        {"Name": "RIB1", "PropType": "Ribbed", "Material": "C30", "Thickness": 0.30},
        {"Name": "WAF1", "PropType": "Waffle", "Material": "C30", "Thickness": 0.35},
    ]


def _material_tables() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    # Host keys from spec 0008 section 4.5 (Material Properties - General / Basic Mechanical / Concrete Data).
    general = [
        {"Material": "C30", "Type": "Concrete"},
        {"Material": "STEEL1", "Type": "Steel"},
        {"Material": "OTHER1", "Type": "NoDesign"},
    ]
    mechanical = [
        {"Material": "C30", "UnitWeight": 24.0, "E1": 30_000.0, "U12": 0.2},
        {"Material": "STEEL1", "UnitWeight": 77.0, "E1": 200_000.0, "U12": 0.3},
        {"Material": "OTHER1", "UnitWeight": 18.0, "E1": 10_000.0, "U12": 0.1},
    ]
    concrete = [{"Material": "C30", "Fc": 30_000.0}]  # 30 MPa as present stress (kN/m2 under kN_m_C)
    return general, mechanical, concrete


def _spring_tables() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # Host keys from spec 0008 section 4.5 (Spring Property / Area Assignments - Area Springs); AC12.
    props = [
        {
            "Name": "SOIL",
            "StiffOpt": "Simple",
            "StiffU1": 0.0,
            "StiffU2": 0.0,
            "StiffU3": 12_000.0,
            "NonlinOpt3": "CompressionOnly",
        }
    ]
    assignments = [
        {"UniqueName": "A1", "SpringProp": "SOIL"},
        {"UniqueName": "A2", "SpringProp": "None"},
    ]
    return props, assignments


def test_sections_and_materials() -> None:
    """AC11: mapped PropTypes are kind slab; Ribbed/Waffle get SECTION_TYPE_NOT_MAPPED; concrete has fc and gamma."""
    sections, issues = _safe_state.sections_from_rows(_slab_rows(), UNITS)
    assert isinstance(sections, Sections)
    by_name = {row.name: row for row in sections.area_sections}
    assert set(by_name) == {"S200", "DROP1", "STIFF1", "MAT1", "FOOT1"}
    assert sections.frame_sections == []
    for name in ("S200", "DROP1", "STIFF1", "MAT1", "FOOT1"):
        row = by_name[name]
        assert row.kind is AreaSectionKind.SLAB
        assert row.material == "C30"
    assert by_name["S200"].thickness_mm == pytest.approx(200.0)  # 0.20 m under kN_m_C → mm
    assert by_name["FOOT1"].thickness_mm == pytest.approx(600.0)
    assert {issue.code for issue in issues} == {"SECTION_TYPE_NOT_MAPPED"}
    assert all(issue.severity is Severity.INFO for issue in issues)
    assert {issue.subject.id for issue in issues} == {"RIB1", "WAF1"}
    assert all(issue.subject.kind is SubjectKind.SECTION for issue in issues)

    materials = _safe_state.materials_from_rows(*_material_tables(), UNITS)
    by_mat = {row.name: row for row in materials.materials}
    assert by_mat["C30"].type is MaterialType.CONCRETE
    assert by_mat["C30"].fc_MPa == pytest.approx(30.0)  # Fc 30000 kN/m2 → 30 MPa under kN_m_C
    assert by_mat["C30"].gamma_kN_m3 == pytest.approx(24.0)
    assert by_mat["C30"].E_MPa == pytest.approx(30.0)  # E1 30000 kN/m2 → 30 MPa
    assert by_mat["C30"].nu_ratio == pytest.approx(0.2)
    assert by_mat["STEEL1"].type is MaterialType.OTHER  # AC11: non-concrete types are kind other
    assert by_mat["OTHER1"].type is MaterialType.OTHER
    assert by_mat["STEEL1"].fc_MPa is None
    assert by_mat["STEEL1"].gamma_kN_m3 == pytest.approx(77.0)


def test_soil_supports() -> None:
    """AC12: area-spring properties carry the three stiffnesses and NonlinOpt3; None assignment is null."""
    supports = _safe_state.soil_supports_from_rows(*_spring_tables(), UNITS)
    assert isinstance(supports, SafeSoilSupports)
    assert len(supports.properties) == 1
    prop = supports.properties[0]
    assert prop.name == "SOIL"
    assert prop.stiffness_option == "Simple"
    assert prop.u1_kN_m3 == pytest.approx(0.0)
    assert prop.u2_kN_m3 == pytest.approx(0.0)
    assert prop.u3_kN_m3 == pytest.approx(12_000.0)  # unit-weight dimension under kN_m_C (spec Q3)
    assert prop.nonlinear_u3 == "CompressionOnly"
    by_area = {row.area: row.property for row in supports.assignments}
    assert by_area == {"A1": "SOIL", "A2": None}


def test_missing_column() -> None:
    """AC13: a required reference column absent from the reply is INTERNAL naming the table and logical column."""
    rows = [{"Name": "S200", "PropType": "Slab", "Material": "C30"}]  # Thickness missing
    with pytest.raises(ContractError) as caught:
        _tables.map_rows("Slab Property Definitions", rows)
    detail = caught.value.detail
    assert detail.code is ErrorCode.INTERNAL
    assert detail.incident_id is not None
    assert "Slab Property Definitions" in detail.incident_id
    assert "thickness" in detail.incident_id.lower() or "Thickness" in detail.message
    assert detail.received is not None  # columns seen as failure evidence (AC13)


def test_ambiguous_column() -> None:
    """AC13: two reply columns that match one logical field are INTERNAL, never a first match."""
    # Candidate Soil Pressures: both OutputCase and LoadCase normalize to accepted names for logical `case`.
    rows = [
        {
            "OutputCase": "DEAD",
            "LoadCase": "DEAD",
            "Pressure": 100.0,
            "UniqueName": "A1",
        }
    ]
    with pytest.raises(ContractError) as caught:
        _tables.map_rows("Soil Pressures", rows)
    detail = caught.value.detail
    assert detail.code is ErrorCode.INTERNAL
    assert detail.incident_id is not None
    assert "case" in detail.incident_id.lower() or "case" in detail.message.lower()
    assert detail.received is not None


def test_unknown_table_is_gap() -> None:
    """AC13: an unknown field-map entry raises NotImplementedGap; columns seen are evidence."""
    with pytest.raises(NotImplementedGap) as caught:
        _tables.map_rows("Analysis Messages", [{"Text": "ok"}])
    assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
    assert "Analysis Messages" in caught.value.message
    assert any("Analysis Messages" in item or "Text" in item for item in caught.value.evidence)
