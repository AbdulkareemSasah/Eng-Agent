"""Revit write value encoding (plan 0011 T8; spec 0011 AC8, section 4.6, R-G6).

A length is sent as valueType double in millimetres in the shortest round-trip decimal form.
Any other double kind raises NotImplementedGap (R-G6) and nothing is sent. valueType is never
auto; unit on a GUID write is never auto.
"""

from __future__ import annotations

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.errors import NotImplementedGap


def test_value_encoding() -> None:
    # AC8: length -> valueType "double", mm shortest round-trip; non-length double -> NotImplementedGap R-G6.
    from eng_harness.adapters.revit._edits import encode_write_value
    from eng_harness.adapters.revit._units import specs_table

    length_spec = "autodesk.spec.aec:length-2.0.0"
    assert length_spec in specs_table()
    assert specs_table()[length_spec].kind == "length"

    value, value_type = encode_write_value(
        value_mm=304.8,
        storage="Double",
        spec_id=length_spec,
    )
    assert value_type == "double"
    assert value == "304.8"  # shortest round-trip decimal (repr); never "auto"
    assert float(value) == pytest.approx(304.8)
    assert float(value) == 304.8

    # Integer, string and element id are sent with their explicit valueTypes (AC8 / section 4.8).
    assert encode_write_value(value=3, storage="Integer", spec_id=None) == ("3", "integer")
    assert encode_write_value(value="Concrete", storage="String", spec_id=None) == ("Concrete", "string")
    assert encode_write_value(value=2001, storage="ElementId", spec_id=None) == ("2001", "elementId")

    # A double that is not a length (no length spec, or a non-length kind) is refused (R-G6).
    with pytest.raises(NotImplementedGap) as gap:
        encode_write_value(value_mm=1.0, storage="Double", spec_id="test:area-unmapped")
    assert "R-G6" in gap.value.evidence

    with pytest.raises(NotImplementedGap) as gap_none:
        encode_write_value(value_mm=1.0, storage="Double", spec_id=None)
    assert "R-G6" in gap_none.value.evidence

    # valueType auto is refused before any send (builders / encode path).
    from eng_harness.adapters.revit import _tools as revit_tools

    with pytest.raises(ContractError) as auto:
        revit_tools.build_set_element_parameter_values_args(
            element_ids=[1],
            parameter_name="b",
            value="300",
            value_type="auto",
        )
    assert auto.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert auto.value.detail.field == "valueType"

    with pytest.raises(ContractError) as unit_auto:
        revit_tools.build_set_parameter_value_by_guid_args(
            element_ids=[1],
            guid="00000000-0000-0000-0000-000000000001",
            value="300",
            value_type="double",
            unit="auto",
        )
    assert unit_auto.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert unit_auto.value.detail.field == "unit"
