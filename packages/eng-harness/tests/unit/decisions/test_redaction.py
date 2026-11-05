"""Redaction by construction and at runtime (plan 0005 T3; spec 0005 AC32, AC33 pure check, AC34, section 4.10)."""

from enum import StrEnum
from typing import Any

import pytest
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref
from eng_harness.decisions._redaction import (
    DENIED_TOKENS,
    LABEL_BOUND,
    RedactionFinding,
    RedactionReason,
    check_state,
    denied_token,
    outgoing_state,
)
from pydantic import BaseModel, ConfigDict

from eng_harness.decisions._points import DecisionPoint, Refs, decision_point
from eng_harness.decisions._policy import DecisionSettings
from eng_harness.decisions.types import DecisionDefinitionError, Label

_STRICT = ConfigDict(frozen=True, extra="forbid")
_RES = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
_RES2 = "res_01BX5ZZKBKACTAV9WEVGEMMVRY"


class Action(StrEnum):
    ENLARGE = "enlarge"
    REBAR = "rebar"


def _make(state: type[BaseModel], **over: Any) -> DecisionPoint:
    args: dict[str, Any] = {"name": "footing_fix", "version": 1, "title": "Footing fix", "options": Action}
    args.update(over)
    return decision_point(state=state, **args)(type("Marker", (), {}))


def _model(**fields: Any) -> type[BaseModel]:
    """A strict frozen model with the given annotations (``name=annotation``)."""
    return type("Generated", (BaseModel,), {"model_config": _STRICT, "__annotations__": fields})


def _found(state: dict[str, Any], sensitive: tuple[str, ...] = ()) -> set[tuple[str, str]]:
    return {(f.field_path, str(f.reason)) for f in check_state(state, sensitive)}


def _ref(value: str) -> Ref:
    return Ref.model_validate({"$ref": value})


class Inner(BaseModel):
    model_config = _STRICT
    ref: Ref
    count: int


class Mixed(BaseModel):
    model_config = _STRICT
    count: int
    anchor: Ref
    anchors: tuple[Ref, ...]
    inner: Inner
    inners: tuple[Inner, ...]
    q: Quantity
    labels: tuple[Label, ...]


def test_by_construction() -> None:
    assert {
        "project",
        "client",
        "address",
        "location",
        "person",
        "author",
        "engineer",
        "owner",
        "user",
    } <= DENIED_TOKENS
    assert {"email", "phone", "path", "file", "folder", "directory"} <= DENIED_TOKENS
    for name, token in (("project_name", "project"), ("client", "client"), ("file_path", "file"), ("bar_user", "user")):
        with pytest.raises(DecisionDefinitionError, match=token):
            _make(_model(**{name: int}))
    # a nested model is checked too, and the error names the field
    with pytest.raises(DecisionDefinitionError, match="folder_count"):
        _make(_model(inner=_model(folder_count=int)))
    # tokens are whole words split on "_": these names carry no denied token
    assert _make(_model(filename=int, profile=int, pathway=int)).name == "footing_fix"
    assert denied_token("bar_diameter", frozenset()) is None
    assert denied_token("file_path", frozenset()) == "file"
    # settings may add tokens and never remove one
    settings = DecisionSettings(extra_denied_tokens=("zone",))
    with pytest.raises(DecisionDefinitionError, match="zone"):
        _make(_model(zone_id=int), settings=settings)
    with pytest.raises(DecisionDefinitionError, match="client"):
        _make(_model(client=int), settings=settings)
    assert _make(_model(zone_id=int)).name == "footing_fix"
    # a Label weakened to str is refused (AC32); a Label is accepted
    with pytest.raises(DecisionDefinitionError, match="note"):
        _make(_model(note=str))
    assert _make(_model(note=Label)).name == "footing_fix"
    assert _make(_model(labels=tuple[Label, ...]), options=Refs("labels")).options == Refs("labels")


def test_runtime_check_blocks_send() -> None:
    sample = "Acme Tower"
    state = {
        "a": "C:temp",
        "b": "see /etc/passwd",
        "c": "dir\\file",
        "d": "https://example.com/x",
        "e": "mail me at x@y.z",
        "f": f"the {sample.upper()} job",
        "g": "x" * (LABEL_BOUND + 1),
        "h": "x" * LABEL_BOUND,
        "ok": "enlarge",
        "n": 12,
        "nested": {"deep": ["fine", "a/b", {"leaf": "c@d"}]},
    }
    got = check_state(state, (sample,))
    assert all(isinstance(f, RedactionFinding) for f in got)
    pairs = {(f.field_path, str(f.reason)) for f in got}
    assert ("a", "path") in pairs
    assert ("b", "path") in pairs
    assert ("c", "path") in pairs
    assert ("d", "url") in pairs
    assert ("e", "address") in pairs
    assert ("f", "sensitive_value") in pairs
    assert ("g", "too_long") in pairs
    assert ("nested.deep.1", "path") in pairs
    assert ("nested.deep.2.leaf", "address") in pairs
    assert not {p for p, _ in pairs} & {"h", "ok", "n", "nested.deep.0"}
    # findings carry paths and reasons, never values (AC33)
    text = repr(got) + "".join(f.model_dump_json() for f in got)
    for value in (sample, sample.upper(), "etc", "example.com", "x@y.z", "x" * 20):
        assert value not in text
    assert set(RedactionFinding.model_fields) == {"field_path", "reason"}
    assert {r.value for r in RedactionReason} == {"path", "url", "address", "sensitive_value", "too_long"}
    # same input, same order
    assert check_state(state, (sample,)) == got
    assert [f.field_path for f in got] == sorted(f.field_path for f in got)


def test_runtime_check_value_rules() -> None:
    assert check_state({"a": "enlarge", "b": ["rebar"], "c": 1.5, "d": True, "e": None}, ("Acme",)) == ()
    # a sensitive value shorter than 3 characters is ignored, one of 3 is used, case-insensitively
    assert _found({"a": "xy marks"}, ("xy",)) == set()
    assert _found({"a": "the ABC job"}, ("abc",)) == {("a", "sensitive_value")}
    # the caller passes the union of settings and call values; each is used
    assert _found({"a": "uno", "b": "dos"}, ("uno", "dos")) == {("a", "sensitive_value"), ("b", "sensitive_value")}
    # the label bound is the Label maximum of AC2
    assert LABEL_BOUND == 80
    # a quantity unit from the contract (kN/m) is not a path
    assert _found({"load": {"value": 3.0, "unit": "kN/m"}}) == set()
    assert _found({"load": {"value": 3.0, "unit": "C:/sample"}}) == {("load.unit", "path")}
    assert _found({"load": {"value": 3.0, "unit": "kN/m", "extra": "a/b"}}) == {
        ("load.unit", "path"),
        ("load.extra", "path"),
    }
    # object keys are field names (checked by construction), not values
    assert _found({"a/b": "fine"}) == set()
    # a sensitive value inside a Quantity unit is still found
    assert _found({"q": {"value": 1.0, "unit": "kN/m"}}, ("kn/m",)) == {("q.unit", "sensitive_value")}


def test_refs_not_sent() -> None:
    state = Mixed(
        count=2,
        anchor=_ref(_RES),
        anchors=(_ref(_RES), _ref(_RES2)),
        inner=Inner(ref=_ref(_RES), count=3),
        inners=(Inner(ref=_ref(_RES2), count=4),),
        q=Quantity(2.5, "kN/m"),
        labels=("a", "b"),
    )
    assert _make(Mixed).state is Mixed
    out = outgoing_state(state)
    assert out == {
        "count": 2,
        "inner": {"count": 3},
        "inners": [{"count": 4}],
        "q": {"value": 2.5, "unit": "kN/m"},
        "labels": ["a", "b"],
    }
    assert _RES not in repr(out)
    assert _RES2 not in repr(out)
    # the sent state passes the value check; the model itself is not changed
    assert check_state(out, ()) == ()
    assert state.anchor.ref == _RES
