"""Contract of harness.column_section_match: sizes must be harness.section_size/1 results (spec 0013 AC9)."""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import InputPolicy, validate_input
from eng_contract.records import ResultRecord

from eng_harness.calcs import REGISTRY

CALC_ID = "harness.column_section_match"
SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"


class _NoStore:
    """A record source that holds nothing: literal inputs never reach it."""

    def get(self, result_id: str) -> ResultRecord:
        raise AssertionError(result_id)

    def payload(self, result_id: str) -> dict[str, Any]:
        raise AssertionError(result_id)


def _basis() -> dict[str, Any]:
    return {
        "template": None,
        "fields": {
            "compare.length_mm": {
                "value": 5,
                "unit": "mm",
                "source": SRC,
                "confirmed": True,
                "citation": None,
            }
        },
    }


def _column() -> dict[str, Any]:
    return {
        "frame_id": "C1",
        "section": "C30x30",
        "shape": "rectangular",
        "material": "C30",
        "story": "L1",
        "length_mm": 3000.0,
    }


def _sections() -> dict[str, Any]:
    return {
        "frame_sections": [
            {
                "name": "C40x60",
                "material": "C30",
                "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 600},
            }
        ],
        "area_sections": [],
    }


def test_size_must_be_rounding_result() -> None:
    """AC9: a literal length is not a harness.section_size/1 result (INVALID_ARGUMENT)."""
    definition = REGISTRY[CALC_ID]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    raw = {
        "column": _column(),
        "sizes": {
            "b": {"value": 400.0, "unit": "mm"},
            "h": {"value": 600.0, "unit": "mm"},
        },
        "sections": _sections(),
        "basis": _basis(),
    }
    with pytest.raises(ContractError) as caught:
        validate_input(
            input_type,
            raw,
            source=_NoStore(),
            current_revision=lambda _: None,
            policy=InputPolicy(require_refs=False),
        )
    detail = caught.value.detail
    assert detail.code is ErrorCode.INVALID_ARGUMENT
    assert detail.field is not None and detail.field.startswith("sizes")
