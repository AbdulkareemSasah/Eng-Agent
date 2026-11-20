"""FieldSpec and the workflow declaration rules (plan 0004 T5; spec 0004 AC21).

All specs are synthetic: no value or bound here is an engineering value.
"""

from typing import Any

import pytest
from eng_contract.cited import Cited
from eng_contract.errors import ErrorCode

from eng_harness.basis import BasisInvalid, FieldSpec, check_declaration

SRC = "Synthetic placeholder, not an engineering value"


def _spec(**changes: Any) -> FieldSpec:
    base: dict[str, Any] = {"path": "limits.drift_ratio", "kind": "quantity", "label": "Drift", "unit": "1"}
    return FieldSpec(**{**base, **changes})


def _reason(**changes: Any) -> str:
    with pytest.raises(BasisInvalid) as caught:
        _spec(**changes)
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    return caught.value.reason


def test_field_spec_rules() -> None:
    assert _spec().required is True
    assert _spec(path="modeling.merge_tolerance_mm", unit="mm").unit == "mm"
    assert _spec(path="analysis.stories", kind="count", unit=None).kind == "count"
    assert _spec(path="analysis.method", kind="choice", unit=None, choices=("a", "b")).choices == ("a", "b")
    assert _spec(path="drawing.title", kind="text", unit=None).kind == "text"
    # quantity: canonical unit of the path suffix
    assert _reason(unit="mm") == "field_invalid"
    assert _reason(unit=None) == "field_invalid"
    assert _reason(path="limits.drift_mm", unit="m") == "field_invalid"
    assert _reason(path="limits.drift", unit="1") == "field_invalid"
    # count: no unit; choice: two or more choices; others carry no choices
    assert _reason(path="analysis.stories", kind="count", unit="1") == "field_invalid"
    assert _reason(path="analysis.method", kind="choice", unit=None, choices=("a",)) == "field_invalid"
    assert _reason(path="analysis.method", kind="choice", unit=None, choices=None) == "field_invalid"
    assert _reason(path="analysis.method", kind="choice", unit=None, choices=("a", "a")) == "field_invalid"
    assert _reason(path="drawing.title", kind="text", unit=None, choices=("a", "b")) == "field_invalid"
    assert _reason(path="drawing.title", kind="text", unit="mm") == "field_invalid"
    # path and label shape
    assert _reason(path="drift_ratio") == "field_invalid"
    assert _reason(path="limits..x") == "field_invalid"
    assert _reason(label="") == "field_invalid"
    assert _reason(label="x" * 121) == "field_invalid"
    # bounds: numeric kinds only, in the field's unit, min not above max
    low = Cited(value=0.1, unit="1", source=SRC)
    high = Cited(value=0.5, unit="1", source=SRC)
    assert _spec(min=low, max=high).max == high
    assert _reason(min=high, max=low) == "field_invalid"
    assert _reason(min=Cited(value=1, unit="mm", source=SRC)) == "field_invalid"
    assert _reason(path="drawing.title", kind="text", unit=None, min=low) == "field_invalid"
    assert _reason(unknown=1) == "field_invalid"


def test_declaration_must_match_required_basis() -> None:
    fields = (_spec(), _spec(path="modeling.snap_tolerance_mm", unit="mm", required=False))
    check_declaration(fields, ("limits.drift_ratio",))
    check_declaration(fields, ["limits.drift_ratio"])
    for wrong in ((), ("limits.drift_ratio", "modeling.snap_tolerance_mm"), ("limits.other_ratio",)):
        with pytest.raises(BasisInvalid) as caught:
            check_declaration(fields, wrong)
        assert caught.value.reason == "declaration_mismatch"
    with pytest.raises(BasisInvalid) as caught:
        check_declaration((_spec(), _spec()), ("limits.drift_ratio",))
    assert caught.value.reason == "field_invalid"
    assert caught.value.path == "limits.drift_ratio"
