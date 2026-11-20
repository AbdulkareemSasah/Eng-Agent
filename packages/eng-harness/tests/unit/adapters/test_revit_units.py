"""Revit specification-identifier units (plan 0011 T5; spec 0011 AC7, §4.6).

Length: raw feet → mm by eng_contract.units.convert (ft is the international foot, NIST SP 811).
Unmapped specifications are left out with info issue PARAMETER_UNIT_UNMAPPED. displayValue is never parsed.
"""

import pytest
from eng_contract.issues import Severity
from eng_contract.units import convert
from eng_contract.verdicts import Subject, SubjectKind


def test_length_feet_to_mm() -> None:
    # AC7: length specification rawValue in feet → millimetres (spec 0011 §4.6; fake pins length-2.0.0).
    from eng_harness.adapters.revit._units import convert_parameter

    raw_ft = 1.0
    expected_mm = convert(raw_ft, "ft", "mm")  # 304.8; hand check: 1 international foot = 304.8 mm (NIST SP 811)
    assert expected_mm == pytest.approx(304.8)

    value, issue = convert_parameter(
        {
            "name": "b",
            "rawValue": raw_ft,
            "displayValue": '12"',  # project display; must not be used
            "specId": "autodesk.spec.aec:length-2.0.0",
        },
        subject=Subject(kind=SubjectKind.SECTION, id="C300x300"),
    )
    assert issue is None
    assert value == pytest.approx(expected_mm)

    half, _ = convert_parameter(
        {
            "name": "h",
            "rawValue": 0.5,
            "displayValue": "152.4 mm",
            "specId": "autodesk.spec.aec:length-2.0.0",
        },
        subject=Subject(kind=SubjectKind.SECTION, id="C300x300"),
    )
    assert half == pytest.approx(convert(0.5, "ft", "mm"))


def test_unmapped_spec_listed() -> None:
    # AC7: a specification with no entry in _specs.toml is left out and listed as info PARAMETER_UNIT_UNMAPPED.
    from eng_harness.adapters.revit._units import convert_parameter

    value, issue = convert_parameter(
        {
            "name": "Area",
            "rawValue": 10.0,
            "displayValue": "10 SF",
            "specId": "autodesk.spec.aec:area-2.0.0",
        },
        subject=Subject(kind=SubjectKind.SECTION, id="C300x300"),
    )
    assert value is None
    assert issue is not None
    assert issue.severity is Severity.INFO
    assert issue.code == "PARAMETER_UNIT_UNMAPPED"
    assert "autodesk.spec.aec:area-2.0.0" in issue.message


def test_display_value_never_used() -> None:
    # AC7: displayValue is never parsed; a misleading display string does not change the payload.
    from eng_harness.adapters.revit._units import convert_parameter

    value, issue = convert_parameter(
        {
            "name": "b",
            "rawValue": 2.0,  # 2 ft → 609.6 mm
            "displayValue": "9999",  # would be wrong if parsed as mm or as feet
            "specId": "autodesk.spec.aec:length-2.0.0",
        },
        subject=Subject(kind=SubjectKind.SECTION, id="beam"),
    )
    assert issue is None
    assert value == pytest.approx(convert(2.0, "ft", "mm"))
    assert value != pytest.approx(9999.0)
