"""Tests of check inputs, the bounded and unbounded helpers and preconditions (plan 0001 T3; AC3, AC4, AC4a)."""

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
_ONE = Cited(value=0, unit="1", source="10-structural-codes synthetic dimensionless bound")


class _Mode(StrEnum):
    A = "a"
    B = "b"


class _NoSource:
    def get(self, result_id: str) -> ResultRecord:
        raise AssertionError(result_id)

    def payload(self, result_id: str) -> NoReturn:
        raise AssertionError(result_id)


def _validate(model: type[CheckInputs], raw: dict[str, Any]) -> dict[str, Any]:
    validated = validate_input(model, raw, source=_NoSource(), current_revision=lambda _id: None, policy=InputPolicy())
    return validated.model.model_dump()


def test_definition_rules() -> None:
    class Good(CheckInputs):
        width_mm: float = bounded(ge=_LOW, le=_HIGH, unit="mm")
        drift_ratio: float = unbounded(reason="signed reaction; no physical bound", unit="1")
        count: int = bounded(gt=_ONE, unit="1")
        flag: bool = False
        mode: _Mode = _Mode.A
        kind: Literal["x", "y"] = "x"

    check_inputs_definition(Good)
    assert Good.model_fields["ratio_limit"].default is None

    for wrong in (ParamModel, dict):
        with pytest.raises(CheckDefinitionError, match="is not a CheckInputs subclass"):
            check_inputs_definition(wrong)

    with pytest.raises(CheckDefinitionError, match="width_mm: a numeric field needs bounds or an unbounded reason"):

        class NoBounds(CheckInputs):
            width_mm: float = eng_param(unit="mm")

    with pytest.raises(
        CheckDefinitionError, match="names: only float, int, bool, StrEnum and Literal fields are allowed"
    ):

        class NotScalar(CheckInputs):
            names: tuple[float, ...] = ()

    with pytest.raises(
        CheckDefinitionError, match="text: only float, int, bool, StrEnum and Literal fields are allowed"
    ):

        class AString(CheckInputs):
            text: str = "a"

    with pytest.raises(CheckDefinitionError, match="bound ge has unit 'mm', the field has 'm'"):

        class BadUnit(CheckInputs):
            width_mm: float = bounded(ge=_LOW, le=_HIGH, unit="m")

    with pytest.raises(CheckDefinitionError, match="width_mm"):

        class BadContract(CheckInputs):
            width_mm: float = eng_param(unit="mm", ge=1.0)  # bounds without a source

    with pytest.raises(CheckDefinitionError, match="bound le has unit 'mm', the field has None"):

        class NoUnit(CheckInputs):
            width_mm: float = bounded(le=_HIGH)


def test_bounded_helper_and_out_of_range() -> None:
    class Section(CheckInputs):
        width_mm: float = bounded(ge=_LOW, le=_HIGH, unit="mm")

    prop = Section.model_json_schema()["properties"]["width_mm"]
    assert prop["minimum"] == 0
    assert prop["maximum"] == 100
    assert prop["x-eng"]["bounds_source"] == f"{_LOW.source}; {_HIGH.source}"
    assert prop["x-eng"]["unit"] == "mm"
    assert not {"exclusiveMinimum", "exclusiveMaximum"} & prop.keys()
    assert _validate(Section, {"width_mm": 100})["width_mm"] == 100
    for bad in (100.0001, -0.0001):
        with pytest.raises(ContractError) as info:
            _validate(Section, {"width_mm": bad})
        assert info.value.detail.code is ErrorCode.OUT_OF_RANGE
        assert info.value.detail.field == "width_mm"

    class Exclusive(CheckInputs):
        width_mm: float = bounded(gt=_LOW, lt=_HIGH, unit="mm")

    eprop = Exclusive.model_json_schema()["properties"]["width_mm"]
    assert eprop["exclusiveMinimum"] == 0
    assert eprop["exclusiveMaximum"] == 100
    assert not {"minimum", "maximum"} & eprop.keys()
    for edge in (0, 100):
        with pytest.raises(ContractError) as info:
            _validate(Exclusive, {"width_mm": edge})
        assert info.value.detail.code is ErrorCode.OUT_OF_RANGE
    assert _validate(Exclusive, {"width_mm": 50})["width_mm"] == 50

    class SameSource(CheckInputs):
        width_mm: float = bounded(ge=_LOW, le=_LOW, unit="mm")

    assert SameSource.model_json_schema()["properties"]["width_mm"]["x-eng"]["bounds_source"] == _LOW.source


def test_ratio_limit_bounds() -> None:
    class Plain(CheckInputs):
        pass

    prop = Plain.model_json_schema()["properties"]["ratio_limit"]
    literal = prop["anyOf"][0]
    assert literal["exclusiveMinimum"] == 0
    assert literal["maximum"] == 1.0
    assert prop["x-eng"]["unit"] == "1"
    assert prop["x-eng"]["ref_capable"] is True
    assert prop["x-eng"]["engineering_quantity"] is True
    assert "ratio_limit is greater than zero" in prop["x-eng"]["bounds_source"]
    assert "does not exceed the contract default" in prop["x-eng"]["bounds_source"]
    assert _validate(Plain, {})["ratio_limit"] is None
    assert _validate(Plain, {"ratio_limit": 0.9})["ratio_limit"] == 0.9
    for bad in (0, -1, 1.01):
        with pytest.raises(ContractError) as info:
            _validate(Plain, {"ratio_limit": bad})
        assert info.value.detail.code is ErrorCode.OUT_OF_RANGE


def test_unbounded_helper() -> None:
    class Load(CheckInputs):
        drift_ratio: float = unbounded(reason="signed reaction; no physical bound", unit="1")

    prop = Load.model_json_schema()["properties"]["drift_ratio"]
    assert prop["x-unbounded-reason"] == "signed reaction; no physical bound"
    assert not {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"} & prop.keys()
    assert prop["x-eng"]["bounds_source"] is None
    assert _validate(Load, {"drift_ratio": -1e9})["drift_ratio"] == -1e9

    for blank in ("", "   ", "\n\t"):
        with pytest.raises(CheckDefinitionError, match="needs a non-blank reason"):
            unbounded(reason=blank, unit="1")

    for key in ("ge", "gt", "le", "lt", "bounds_source"):
        with pytest.raises(CheckDefinitionError, match=f"takes no bounds, got {key}"):
            unbounded(reason="r", unit="1", **{key: 1.0})

    class Defaulted(CheckInputs):
        load: float = unbounded(reason="r", unit="1", default=2.0, ref_capable=True, ref_kinds={"eng.sample/1"})

    dprop = Defaulted.model_json_schema()["properties"]["load"]
    assert dprop["default"] == 2.0
    assert dprop["x-eng"]["ref_kinds"] == ["eng.sample/1"]


def _always(inputs: Any, trace: Any) -> bool:
    return True


_GOOD_PRE: dict[str, Any] = {
    "id": "P1",
    "outcome": Outcome.NOT_APPLICABLE,
    "clause": "22.6.5.2",
    "description": "d",
    "test": _always,
}


def test_precondition_rules() -> None:
    good = _GOOD_PRE
    pre = Precondition(**good)
    assert pre.outcome.value == "NOT_APPLICABLE"
    assert Outcome.NEEDS_ENGINEER.value == "NEEDS_ENGINEER"
    assert Precondition(**{**good, "id": "A_1", "outcome": Outcome.NEEDS_ENGINEER})
    assert Precondition(**{**good, "clause": "c" * 40})
    assert Precondition(**{**good, "clause": "c"})
    bad_cases = (
        ({"id": "p1"}, "must match"),
        ({"id": "1P"}, "must match"),
        ({"id": ""}, "must match"),
        ({"clause": ""}, "clause must have 1 to 40 characters"),
        ({"clause": "c" * 41}, "clause must have 1 to 40 characters"),
        ({"description": " "}, "description must not be blank"),
    )
    for bad, why in bad_cases:
        with pytest.raises(CheckDefinitionError, match=why):
            Precondition(**{**good, **bad})


def test_outcome_and_union_rules() -> None:
    with pytest.raises(CheckDefinitionError, match="outcome must be an Outcome"):
        Precondition(**{**_GOOD_PRE, "outcome": "NOT_APPLICABLE"})
    with pytest.raises(CheckDefinitionError, match="needs at least one cited bound"):
        bounded()
    with pytest.raises(CheckDefinitionError, match="either"):

        class Either(CheckInputs):
            either: int | float = 1
