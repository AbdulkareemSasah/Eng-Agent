"""Contract of harness.column_section_match: sizes must be harness.section_size/1 results (spec 0013 AC9)."""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import InputPolicy, validate_input
from eng_contract.records import ResultRecord

from eng_harness.calc import CalcInput, InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY

CALC_ID = "harness.column_section_match"
SRC = "engineer:synthetic@2026-01-01T00:00:00.000Z"


class _NoStore:
    """A record source that holds nothing: literal inputs never reach it."""

    def get(self, result_id: str) -> ResultRecord:
        raise AssertionError(result_id)

    def payload(self, result_id: str) -> dict[str, Any]:
        raise AssertionError(result_id)


def _basis(value: float = 5) -> dict[str, Any]:
    return {
        "template": None,
        "fields": {
            "compare.length_mm": {
                "value": value,
                "unit": "mm",
                "source": SRC,
                "confirmed": True,
                "citation": None,
            }
        },
    }


def _column(*, shape: str = "rectangular", material: str = "C30") -> dict[str, Any]:
    return {
        "frame_id": "C1",
        "section": "C30x30",
        "shape": shape,
        "material": material,
        "story": "L1",
        "length_mm": 3000.0,
    }


def _size(value: float, multiple: int) -> dict[str, Any]:
    return {
        "required": {"value": value, "unit": "mm"},
        "increment": {"value": 50.0, "unit": "mm"},
        "multiple": multiple,
        "size": {"value": value, "unit": "mm"},
        "status": "PASS",
    }


def _sections(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"frame_sections": list(rows), "area_sections": []}


def _meta() -> InputMeta:
    return InputMeta(
        refs={
            name: RefMeta(
                result_id=f"res_01KCC00000000000000000000{i}",
                kind=kind,
                complete=True,
                model_id=None,
                model_revision=None,
                parents=(),
                producer_tool="fixture_tool",
            )
            for i, (name, kind) in enumerate(
                (
                    ("column", "harness.column_selection/1"),
                    ("sections", "model.sections/1"),
                    ("basis", "basis.design_basis/1"),
                ),
                start=1,
            )
        }
    )


def _input_type() -> type[CalcInput]:
    input_type = REGISTRY[CALC_ID].input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    return input_type


def _run(**changes: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "column": _column(),
        "sizes": {"b": _size(400.0, 8), "h": _size(600.0, 12)},
        "sections": _sections(
            {"name": "C40x60", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 600}}
        ),
        "basis": _basis(),
    }
    raw.update(changes)
    return REGISTRY[CALC_ID](_input_type().model_validate(raw), _meta(), TraceBuilder()).model_dump(mode="json")


def test_size_must_be_rounding_result() -> None:
    """AC9: a literal length is not a harness.section_size/1 result (INVALID_ARGUMENT)."""
    raw = {
        "column": _column(),
        "sizes": {
            "b": {"value": 400.0, "unit": "mm"},
            "h": {"value": 600.0, "unit": "mm"},
        },
        "sections": _sections(
            {"name": "C40x60", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 600}}
        ),
        "basis": _basis(),
    }
    with pytest.raises(ContractError) as caught:
        validate_input(
            _input_type(),
            raw,
            source=_NoStore(),
            current_revision=lambda _: None,
            policy=InputPolicy(require_refs=False),
        )
    detail = caught.value.detail
    assert detail.code is ErrorCode.INVALID_ARGUMENT
    assert detail.field is not None and detail.field.startswith("sizes")


def test_just_beyond_tolerance_is_not_a_candidate() -> None:
    """M1 exclusive of differences above compare.length_mm: |406 - 400| = 6 > 5."""
    body = _run(
        sections=_sections(
            {"name": "C406x600", "material": "C30", "shape": {"type": "rectangular", "b_mm": 406, "h_mm": 600}}
        )
    )
    assert body == {"status": "no_section_in_model", "section": None, "names": []}


def test_zero_tolerance_requires_exact_dimensions() -> None:
    body = _run(
        basis=_basis(0),
        sections=_sections(
            {"name": "C405x600", "material": "C30", "shape": {"type": "rectangular", "b_mm": 405, "h_mm": 600}},
            {"name": "C40x60", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 600}},
        ),
    )
    assert body == {"status": "matched", "section": "C40x60", "names": ["C40x60"]}


def test_other_shape_column_has_no_candidates() -> None:
    body = _run(column=_column(shape="other"))
    assert body["status"] == "no_section_in_model"
    assert body["names"] == []


def test_missing_record_refs_are_refused() -> None:
    raw = {
        "column": _column(),
        "sizes": {"b": _size(400.0, 8), "h": _size(600.0, 12)},
        "sections": _sections(
            {"name": "C40x60", "material": "C30", "shape": {"type": "rectangular", "b_mm": 400, "h_mm": 600}}
        ),
        "basis": _basis(),
    }
    with pytest.raises(ContractError) as caught:
        REGISTRY[CALC_ID](_input_type().model_validate(raw), InputMeta(refs={}), TraceBuilder())
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, "column")
