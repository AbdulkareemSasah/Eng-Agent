"""Tests of check inputs, the bounded and unbounded helpers and preconditions (plan 0001 T3; spec 0001 AC3, AC4, AC4a)."""

from enum import StrEnum
from typing import Any, Literal, NoReturn

import pytest
from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import InputPolicy, ParamModel, eng_param, validate_input
from eng_contract.records import ResultRecord

from structural_codes.applicability import Outcome, Precondition
from structural_codes.errors import CheckDefinitionError
from structural_codes.inputs import CheckInputs, bounded, check_inputs_definition, unbounded

# Structural fixtures only: the numbers are labels for the bounds machinery, not engineering data.
_LOW = Cited(value=0, unit="mm", source="10-structural-codes synthetic lower bound")
_HIGH = Cited(value=100, unit="mm", source="10-structural-codes synthetic upper bound")


class _Mode(StrEnum):
    A = "a"
    B = "b"


class _NoSource:
    def get(self, result_id: str) -> ResultRecord:
        raise AssertionError(result_id)

    def payload(self, result_id: str) -> NoReturn:
        raise AssertionError(result_id)


def _validate(model: type[CheckInputs], raw: dict[str, Any]) -> dict[str, Any]:
    validated = validate_input(
        model, raw, source=_NoSource(), current_revision=lambda _id: None, policy=InputPolicy()
    )
    return validated.model.model_dump()


def test_definition_rules() -> None:
    class Good(CheckInputs):
        width_mm: float = bounded(ge=_LOW, le=_HIGH, unit="mm")
        force_kN: float = unbounded(reason="signed reaction; no physical bound", unit="kN")
        count: int = bounded(gt=_LOW, unit="1")
        flag: bool = False
        mode: _Mode = _Mode.A
        kind: Literal["x", "y"] = "x"

    check_inputs_definition(Good)
    assert Good.model_fields["ratio_limit"].default is None

    with pytest.raises(CheckDefinitionError):
        check_inputs_definition(ParamModel)  # type: ignore[arg-type]  # B-257: the point of the test
    with pytest.raises(CheckDefinitionError):
        check_inputs_definition(dict)  # type: ignore[arg-type]  # B-257: the point of the test

    with pytest.raises(CheckDefinitionError, match="width_mm"):

        class NoBounds(CheckInputs):
            width_mm: float = eng_param(unit="mm")

    with pytest.raises(CheckDefinitionError, match="names"):

        class NotScalar(CheckInputs):
            names: list[float] = []

    with pytest.raises(CheckDefinitionError, match="text"):

        class AString(CheckInputs):
            text: str = "a"

    with pytest.raises(CheckDefinitionError, match="width_mm"):

        class BadUnit(CheckInputs):
            width_mm: float = bounded(ge=_LOW, le=_HIGH, unit="m")

    with pytest.raises(CheckDefinitionError):

        class BadContract(CheckInputs):
            width_mm: float = eng_param(unit="mm", ge=1.0)  # bounds without a source


def test_bounded_helper_and_out_of_range() -> None:
    class Section(CheckInputs):
        width_mm: float = bounded(ge=_LOW, le=_HIGH, unit="mm")

    prop = Section.model_json_schema()["properties"]["width_mm"]
    assert prop["minimum"] == 0
    assert prop["maximum"] == 100
    source = prop["x-eng"]["bounds_source"]
    assert "synthetic lower bound" in source
    assert "synthetic upper bound" in source
    assert _validate(Section, {"width_mm": 100})["width_mm"] == 100
    for bad in (100.0001, -0.0001):
        with pytest.raises(ContractError) as info:
            _validate(Section, {"width_mm": bad})
        assert info.value.code is ErrorCode.OUT_OF_RANGE
        assert info.value.field == "width_mm"

    class Exclusive(CheckInputs):
        width_mm: float = bounded(gt=_LOW, lt=_HIGH, unit="mm")

    with pytest.raises(ContractError) as info:
        _validate(Exclusive, {"width_mm": 0})
    assert info.value.code is ErrorCode.OUT_OF_RANGE


def test_ratio_limit_bounds() -> None:
    class Plain(CheckInputs):
        pass

    prop = Plain.model_json_schema()["properties"]["ratio_limit"]
    literal = next(c for c in prop["anyOf"] if c.get("type") == "number")
    assert literal["exclusiveMinimum"] == 0
    assert literal["maximum"] == 1.0
    assert _validate(Plain, {})["ratio_limit"] is None
    assert _validate(Plain, {"ratio_limit": 0.9})["ratio_limit"] == 0.9
    for bad in (0, -1, 1.01):
        with pytest.raises(ContractError) as info:
            _validate(Plain, {"ratio_limit": bad})
        assert info.value.code is ErrorCode.OUT_OF_RANGE


def test_unbounded_helper() -> None:
    class Load(CheckInputs):
        force_kN: float = unbounded(reason="signed reaction; no physical bound", unit="kN")

    prop = Load.model_json_schema()["properties"]["force_kN"]
    assert prop["x-unbounded-reason"] == "signed reaction; no physical bound"
    assert not {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"} & prop.keys()
    assert prop["x-eng"]["bounds_source"] is None
    assert _validate(Load, {"force_kN": -1e9})["force_kN"] == -1e9

    for blank in ("", "   ", "\n\t"):
        with pytest.raises(CheckDefinitionError):
            unbounded(reason=blank, unit="kN")


def _always(inputs: Any, trace: Any) -> bool:
    return True


def test_precondition_rules() -> None:
    good: dict[str, Any] = {
        "id": "P1",
        "outcome": Outcome.NOT_APPLICABLE,
        "clause": "22.6.5.2",
        "description": "d",
        "test": _always,
    }
    pre = Precondition(**good)
    assert pre.outcome.value == "NOT_APPLICABLE"
    assert Outcome.NEEDS_ENGINEER.value == "NEEDS_ENGINEER"
    assert Precondition(**{**good, "id": "A_1", "outcome": Outcome.NEEDS_ENGINEER})
    for bad in ({"id": "p1"}, {"id": "1P"}, {"id": ""}, {"clause": ""}, {"clause": "c" * 41}, {"description": " "}):
        with pytest.raises(CheckDefinitionError):
            Precondition(**{**good, **bad})
