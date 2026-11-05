"""ctx types and the basis view (plan task T7; spec 0001 sections 4.3.2 and 4.9, AC17)."""

from enum import StrEnum

import pytest
from eng_contract.kinds.basis import BasisField, DesignBasis
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref
from pydantic import BaseModel, JsonValue, ValidationError

from eng_harness.ctx import (
    Answered,
    Approval,
    ApprovalKind,
    Attempt,
    BasisCount,
    BasisView,
    ModelHandle,
    Preview,
    PreviewItem,
    Promotion,
)
from eng_harness.errors import BlockRuleViolation

RESULT = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
MODEL = "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV"
ALL = (
    "limits.drift_ratio",
    "limits.cover_mm",
    "attempts.design",
    "attempts.bad",
    "attempts.flag",
    "attempts.negative",
    "section.mode",
    "section.other",
)


class Mode(StrEnum):
    A = "a"
    B = "b"


class Form(BaseModel):
    depth_mm: float


def _field(value: JsonValue, unit: str | None) -> BasisField:
    return BasisField(
        value=value,
        unit=unit,
        source="engineer:eng@2026-01-01T00:00:00.000Z",
        confirmed=True,
        citation=None,
    )


def _view(declared: tuple[str, ...]) -> BasisView:
    basis = DesignBasis(
        template=None,
        fields={
            "limits.drift_ratio": _field(0.02, "1"),
            "limits.cover_mm": _field(40, "mm"),
            "attempts.design": _field(3, None),
            "attempts.bad": _field(2.5, None),
            "attempts.flag": _field(True, None),
            "attempts.negative": _field(-1, None),
            "section.mode": _field("a", None),
            "section.other": _field("zzz", None),
            "undeclared.thing": _field(1, None),
        },
    )
    return BasisView(RESULT, basis, declared)


def test_basis_view() -> None:
    view = _view(ALL)
    assert view.ref("limits.drift_ratio").ref == f"{RESULT}#/fields/limits.drift_ratio/value"
    assert view.quantity("limits.cover_mm") == Quantity(40.0, "mm")
    assert view.quantity("limits.drift_ratio") == Quantity(0.02, "1")
    count = view.count("attempts.design")
    assert count == 3
    assert isinstance(count, BasisCount)
    assert view.choice("section.mode", Mode) is Mode.A
    for call in (view.ref, view.quantity, view.count):
        with pytest.raises(BlockRuleViolation):
            call("undeclared.thing")
    with pytest.raises(BlockRuleViolation):
        view.choice("undeclared.thing", Mode)
    with pytest.raises(BlockRuleViolation):
        view.ref("limits.not_a_field")


def test_basis_view_refuses_wrong_value_shapes() -> None:
    view = _view(ALL)
    for path in ("attempts.bad", "attempts.flag", "attempts.negative", "section.mode"):
        with pytest.raises(BlockRuleViolation):
            view.count(path)
    for path in ("attempts.design", "section.mode"):  # no unit
        with pytest.raises(BlockRuleViolation):
            view.quantity(path)
    with pytest.raises(BlockRuleViolation):
        view.choice("section.other", Mode)
    with pytest.raises(BlockRuleViolation):
        view.choice("attempts.design", Mode)


def test_basis_count_is_an_int() -> None:
    assert BasisCount(4) + 1 == 5
    with pytest.raises(ValueError, match="non-negative"):
        BasisCount(-1)


def test_preview_and_approval() -> None:
    item = PreviewItem(id="a", label="Item A", refs=())
    with pytest.raises(ValidationError):
        Preview(items=(item, item), diff_ref=None, models=())
    handle = ModelHandle(model_key="m", model_id=MODEL, revision=2)
    preview = Preview(items=(item,), diff_ref=None, models=(handle,))
    assert preview.models[0].revision == 2
    with pytest.raises(ValidationError):
        item.label = "x"
    approved = Approval(request_id="apr_1", approved=True, rejected_items=("b",), item_reasons={"b": "no"}, reason=None)
    assert approved.accepts("a")
    assert not approved.accepts("b")
    rejected = Approval(request_id="apr_1", approved=False, rejected_items=(), item_reasons={}, reason="no")
    assert not rejected.accepts("a")


def test_enums_attempt_and_answered() -> None:
    assert {k.name for k in ApprovalKind} == {"CHANGE_SET", "PROMOTION", "SIGN_OFF", "INFO"}
    assert {p.name for p in Promotion} == {"FILE_COPY", "REPLAY_WRITES"}
    assert Attempt(index=0, is_last=False).index == 0
    answered = Answered[Form](value=Form(depth_mm=3.0), ref=Ref.model_validate({"$ref": RESULT}))
    assert answered.field_ref("depth_mm").ref == f"{RESULT}#/fields/depth_mm/value"
