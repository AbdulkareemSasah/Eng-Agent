"""Error codes, retry rules, warnings and ContractError (plan T2; spec 4.2.3, 4.2.4; AC10).

The code list and the retry column come from 04 section 8.1 and 8.2, written out here independently of the
implementation.
"""

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from eng_contract._types import FieldPath, KindName, Sha256Hex
from eng_contract.errors import (
    RETRY_RULES,
    ContractError,
    ContractWarning,
    ErrorCode,
    ErrorDetail,
    Precondition,
    RetryRule,
    WarningCode,
)

# 04 section 8.1: code -> required `retryable`; None means the producer decides ("Depends").
TABLE: dict[str, bool | None] = {
    "INVALID_ARGUMENT": False,
    "OUT_OF_RANGE": False,
    "UNIT_MISMATCH": False,
    "REF_NOT_FOUND": False,
    "REF_POINTER_INVALID": False,
    "REF_KIND_MISMATCH": False,
    "REF_UNIT_MISMATCH": False,
    "REF_STALE": False,
    "NOT_FOUND": False,
    "CONFLICT": False,
    "PRECONDITION_FAILED": False,
    "CONFIRMATION_REQUIRED": False,
    "LIMIT_EXCEEDED": False,
    "HOST_NOT_CONNECTED": True,
    "HOST_BUSY": True,
    "HOST_WEDGED": True,
    "HOST_LOCKED": False,
    "HOST_ERROR": None,
    "TIMEOUT_NO_EFFECT": True,
    "TIMEOUT_UNKNOWN_OUTCOME": False,
    "NOT_SUPPORTED_BY_VERSION": False,
    "INTERNAL": False,
}
RULE_NAMES = {
    "HOST_NOT_CONNECTED": "always",
    "HOST_BUSY": "always",
    "TIMEOUT_NO_EFFECT": "always",
    "HOST_WEDGED": "after_wedge_clears",
    "TIMEOUT_UNKNOWN_OUTCOME": "reconcile_first",
    "HOST_ERROR": "depends",
}
HOST_FIELD_CODES = ("HOST_ERROR", "HOST_BUSY")


def _required(code: str) -> dict[str, Any]:
    """Extra fields a code requires, so a detail is valid apart from the field under test."""
    if code == "PRECONDITION_FAILED":
        return {"precondition": "model_saved"}
    if code == "INTERNAL":
        return {"incident_id": "inc_1"}
    return {}


def _detail(code: str, retryable: bool, **extra: Any) -> ErrorDetail:
    data = {"code": code, "message": "m", "retryable": retryable, **_required(code), **extra}
    return ErrorDetail.model_validate(data)


def test_all_22_codes_present() -> None:
    assert {c.value for c in ErrorCode} == set(TABLE)
    assert len(ErrorCode) == 22
    assert set(RETRY_RULES) == set(ErrorCode)


def test_warning_codes() -> None:
    assert {c.value for c in WarningCode} == {
        "PARTIAL_DATA",
        "MODEL_CHANGED_OUTSIDE",
        "DIALOG_DISMISSED",
        "HOST_WARNING",
        "DEPRECATED",
    }


def test_precondition_values() -> None:
    assert {p.value for p in Precondition} == {
        "model_saved",
        "model_open",
        "analysis_current",
        "units_verified",
        "local_workspace",
    }


@pytest.mark.parametrize("code", sorted(TABLE))
def test_retry_rules_per_code(code: str) -> None:
    fixed = TABLE[code]
    assert RETRY_RULES[ErrorCode(code)] == RetryRule(RULE_NAMES.get(code, "never"))
    for value in (True, False):
        if fixed is None or fixed == value:
            assert _detail(code, value).retryable is value
        else:
            with pytest.raises(ValidationError):
                _detail(code, value)


@pytest.mark.parametrize("code", sorted(TABLE))
def test_contract_error_fills_retryable(code: str) -> None:
    fixed = TABLE[code]
    if fixed is None:
        with pytest.raises(TypeError):
            ContractError(ErrorCode(code), "m")
        err = ContractError(ErrorCode(code), "m", retryable=True)
        assert err.detail.retryable is True
    else:
        err = ContractError(ErrorCode(code), "m", **_required(code))
        assert err.detail.retryable is fixed
    assert err.detail.code == code
    assert code in str(err)


def test_contract_error_contradiction_fails() -> None:
    with pytest.raises(ValidationError):
        ContractError(ErrorCode.INVALID_ARGUMENT, "m", retryable=True)


def test_code_specific_fields() -> None:
    with pytest.raises(ValidationError):
        ErrorDetail(code=ErrorCode.PRECONDITION_FAILED, message="m", retryable=False)
    assert _detail("PRECONDITION_FAILED", False, precondition="model_open").precondition is Precondition.model_open
    with pytest.raises(ValidationError):
        _detail("PRECONDITION_FAILED", False, precondition="nonsense")
    with pytest.raises(ValidationError):
        ErrorDetail(code=ErrorCode.INTERNAL, message="m", retryable=False)
    assert _detail("INTERNAL", False, incident_id="01ABC").incident_id == "01ABC"
    with pytest.raises(ValidationError):
        _detail("INTERNAL", False, incident_id="x" * 65)
    for code, fixed in TABLE.items():
        retryable = bool(fixed)
        if code != "PRECONDITION_FAILED":
            with pytest.raises(ValidationError):
                _detail(code, retryable, precondition="model_saved")
        if code != "INTERNAL":
            with pytest.raises(ValidationError):
                _detail(code, retryable, incident_id="inc_1")
        if code not in HOST_FIELD_CODES:
            for name in ("host_code", "host_method"):
                for value in ("X", ""):
                    with pytest.raises(ValidationError):
                        _detail(code, retryable, **{name: value})
    for code in HOST_FIELD_CODES:
        d = _detail(code, True, host_code="MODAL_DIALOG", host_method="Save")
        assert (d.host_code, d.host_method) == ("MODAL_DIALOG", "Save")
        with pytest.raises(ValidationError):
            _detail(code, True, host_code="x" * 201)
        with pytest.raises(ValidationError):
            _detail(code, True, host_method="x" * 201)


def test_field_limits() -> None:
    bad_values: list[dict[str, Any]] = [
        {"message": ""},
        {"message": "x" * 2001},
        {"hint": "x" * 2001},
        {"op_id": "x" * 201},
        {"field": "a..b"},
        {"field": "x" * 513},
        {"unknown": 1},
        {"expected": [1]},
        {"expected": "x"},
    ]
    for bad in bad_values:
        with pytest.raises(ValidationError):
            _detail("INVALID_ARGUMENT", False, **bad)
    ok = _detail("INVALID_ARGUMENT", False, message="x" * 2000, field="a.b[0].c", op_id="x" * 200)
    assert ok.field == "a.b[0].c"
    with pytest.raises(ValidationError):
        ok.message = "other"


def test_contract_warning() -> None:
    w = ContractWarning(code=WarningCode.PARTIAL_DATA, message="fewer rows", field="rows[0]")
    assert w.code == "PARTIAL_DATA"
    assert ContractWarning(code=WarningCode.DEPRECATED, message="m").field is None
    for bad in ({"message": ""}, {"message": "x" * 2001}, {"code": "OTHER"}, {"field": "1a"}):
        with pytest.raises(ValidationError):
            ContractWarning.model_validate({"code": "DEPRECATED", "message": "m", **bad})


@pytest.mark.parametrize(
    ("tp", "good", "bad"),
    [
        (FieldPath, ["a", "a.b", "a[0]", "_x1.y[10].z"], ["", "a[01]", "a.", ".a", "a[-1]", "1a", "a b", "a" * 513]),
        (Sha256Hex, ["0" * 64], ["0" * 63, "A" * 64, "g" * 64]),
        (KindName, ["a.b/1", "model.info/12", "x_1.y_2.z/9999"], ["a/1", "a.b/0", "a.b/10000", "A.b/1", "a.b"]),
    ],
)
def test_shared_types(tp: Any, good: list[str], bad: list[str]) -> None:
    adapter: TypeAdapter[str] = TypeAdapter(tp)
    for g in good:
        assert adapter.validate_python(g) == g
    for b in bad:
        with pytest.raises(ValidationError):
            adapter.validate_python(b)
