"""Basis draft: precedence, sources, citations, pending list and draft hash (plan 0004 T6; spec 0004 AC14 to AC20).

Every template, value and bound here is a synthetic placeholder, not an engineering value.
"""

from collections.abc import Callable
from typing import Any

import pytest
from eng_contract.cited import Cited
from eng_contract.errors import ErrorCode

from eng_harness.basis import (
    BasisDraft,
    BasisInvalid,
    DetectedValue,
    EngineerEntry,
    EngineerValues,
    FieldSpec,
    build_draft,
)
from eng_harness.templates import ResolvedTemplate, Template, resolve

CITE = "Synthetic placeholder, not an engineering value"
CITE_PARENT = "Synthetic parent placeholder, not an engineering value"
BOUND = "Synthetic bound, not an engineering value"
REF = "res_01JABCDEFGHJKMNPQRSTVWXYZ0#/fields/x"
DRIFT = "limits.drift_ratio"
TOL = "modeling.merge_tolerance_mm"
STORIES = "analysis.stories"
METHOD = "analysis.method"
TITLE = "drawing.title"


class _Source:
    def __init__(self, *templates: Template) -> None:
        self._by_key = {(t.meta.name, t.meta.version): t for t in templates}

    def find(self, name: str, version: str) -> Template | None:
        return self._by_key.get((name, version))


def _entry(value: Any, unit: str | None = None, citation: str = CITE) -> dict[str, Any]:
    return {"value": value, "unit": unit, "citation": citation}


def _template(
    name: str = "base", extends: str | None = None, asks: list[dict[str, Any]] | None = None, **sections: Any
) -> Template:
    meta: dict[str, Any] = {"name": f"synthetic-{name}", "version": "0.1.0", "synthetic": True}
    if extends:
        meta["extends"] = extends
    return Template.from_data({"schema": "eng-template/1", "meta": meta, "ask_each_run": asks or [], **sections})


def _resolved(*chain: Template) -> tuple[ResolvedTemplate, _Source]:
    source = _Source(*chain)
    return resolve(chain[0], source), source


def _specs(**changes: Any) -> tuple[FieldSpec, ...]:
    return (
        FieldSpec(path=DRIFT, kind="quantity", label="Drift", unit="1", **changes),
        FieldSpec(path=TOL, kind="quantity", label="Tolerance", unit="mm"),
        FieldSpec(path=STORIES, kind="count", label="Stories"),
        FieldSpec(path=METHOD, kind="choice", label="Method", choices=("a", "b")),
        FieldSpec(path=TITLE, kind="text", label="Title", required=False),
    )


def _values(path: str, value: Any, unit: str | None = None) -> EngineerValues:
    return EngineerValues(name="syn", values={path: EngineerEntry(value=value, unit=unit)})


def _detected(path: str, value: Any, unit: str | None = None) -> DetectedValue:
    return DetectedValue(path=path, value=value, unit=unit, ref=REF)


def _reason(draft_call: Callable[[], object]) -> str:
    with pytest.raises(BasisInvalid) as caught:
        draft_call()
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    return caught.value.reason


def test_precedence_and_pending() -> None:
    template, source = _resolved(
        _template(limits={"drift_ratio": _entry(0.5, "1")}, modeling={"merge_tolerance_mm": _entry(2.0, "mm")})
    )
    draft = build_draft(
        _specs(),
        template,
        _values(DRIFT, 0.25, "1"),
        [_detected(DRIFT, 0.75, "1"), _detected(TOL, 3.0, "mm")],
        source=source,
    )
    assert draft.fields[DRIFT].value == 0.25  # engineer beats detected beats template
    assert draft.fields[TOL].value == 3.0  # detected beats template
    assert draft.pending == (STORIES, METHOD)  # required, no value; the optional title is not pending
    assert STORIES not in draft.fields
    assert METHOD not in draft.fields
    assert TITLE not in draft.fields  # no default
    only_template = build_draft(_specs(), template, None, [], source=source)
    assert (only_template.fields[DRIFT].value, only_template.fields[TOL].value) == (0.5, 2.0)
    nothing = build_draft(_specs(), None, None, [])
    assert nothing.fields == {}
    assert nothing.template is None
    assert nothing.pending == (DRIFT, TOL, STORIES, METHOD)


def test_sources_and_citations() -> None:
    parent = _template("parent", limits={"drift_ratio": _entry(0.5, "1", CITE_PARENT)})
    child = _template("child", extends="synthetic-parent@0.1.0", modeling={"merge_tolerance_mm": _entry(2.0, "mm")})
    template, source = _resolved(child, parent)
    draft = build_draft(_specs(), template, _values(STORIES, 3), [_detected(METHOD, "a")], source=source)
    drift, tol, stories, method = (draft.fields[p] for p in (DRIFT, TOL, STORIES, METHOD))
    assert (drift.source, drift.citation) == ("template:synthetic-parent@0.1.0", CITE_PARENT)  # the ancestor defines it
    assert (tol.source, tol.citation) == ("template:synthetic-child@0.1.0", CITE)
    assert (stories.source, stories.citation, stories.origin) == (None, None, "values-file:syn")
    assert (method.source, method.citation, method.origin) == (f"model:{REF}", None, None)
    assert all(field.confirmed is False for field in draft.fields.values())
    assert draft.template is not None
    assert (draft.template.name, draft.template.version, draft.template.sha256) == (
        "synthetic-child",
        "0.1.0",
        template.sha256,
    )
    assert draft.template.chain == ("synthetic-child@0.1.0", "synthetic-parent@0.1.0")
    assert draft.template.status == "draft"


def test_detected_differs_warning() -> None:
    template, source = _resolved(_template(limits={"drift_ratio": _entry(0.5, "1")}))
    draft = build_draft(_specs(), template, None, [_detected(DRIFT, 0.75, "1")], source=source)
    assert draft.fields[DRIFT].value == 0.75
    assert draft.fields[DRIFT].source == f"model:{REF}"
    assert [(w.kind, w.path, w.detected, w.template) for w in draft.warnings] == [
        ("detected_differs", DRIFT, 0.75, 0.5)
    ]
    same = build_draft(_specs(), template, None, [_detected(DRIFT, 0.5, "1")], source=source)
    assert same.warnings == ()
    no_template_value = build_draft(_specs(), None, None, [_detected(DRIFT, 0.75, "1")])
    assert no_template_value.warnings == ()


def test_value_file_rules() -> None:
    specs = _specs(min=Cited(value=0, unit="1", source=BOUND), max=Cited(value=1, unit="1", source=BOUND))

    def build(path: str, value: Any, unit: str | None) -> BasisDraft:
        return build_draft(specs, None, _values(path, value, unit), [])

    assert build(DRIFT, 0.5, "1").fields[DRIFT].value == 0.5
    assert _reason(lambda: build("limits.other_ratio", 1, "1")) == "unknown_field"
    assert _reason(lambda: build(DRIFT, "x", "1")) == "field_invalid"  # kind
    assert _reason(lambda: build(DRIFT, True, "1")) == "field_invalid"  # a bool is not a number
    assert _reason(lambda: build(DRIFT, float("nan"), "1")) == "field_invalid"
    assert _reason(lambda: build(DRIFT, 0.5, "mm")) == "field_invalid"  # unit
    assert _reason(lambda: build(DRIFT, 0.5, None)) == "field_invalid"
    assert _reason(lambda: build(DRIFT, 1.5, "1")) == "field_invalid"  # above the cited maximum
    assert _reason(lambda: build(DRIFT, -0.1, "1")) == "field_invalid"  # below the cited minimum
    assert _reason(lambda: build(STORIES, 2.5, None)) == "field_invalid"
    assert _reason(lambda: build(STORIES, 2, "mm")) == "field_invalid"
    assert _reason(lambda: build(METHOD, "c", None)) == "field_invalid"  # choice
    assert _reason(lambda: build(TITLE, 3, None)) == "field_invalid"
    assert build(TITLE, "t", None).fields[TITLE].value == "t"
    with pytest.raises(BasisInvalid) as caught:
        build(DRIFT, 1.5, "1")
    assert caught.value.path == DRIFT
    # a values file cannot set `confirmed`, on an entry or at the top
    on_entry = {"name": "n", "values": {DRIFT: {"value": 1, "unit": "1", "confirmed": True}}}
    assert _reason(lambda: EngineerValues.model_validate(on_entry)) == "confirmed_not_allowed"
    at_top = {"name": "n", "confirmed": True, "values": {}}
    assert _reason(lambda: EngineerValues.model_validate(at_top)) == "confirmed_not_allowed"
    extra = {"name": "n", "values": {DRIFT: {"value": 1, "unit": "1", "x": 1}}}
    assert _reason(lambda: EngineerValues.model_validate(extra)) == "field_invalid"
    # detected values obey the same rules
    assert _reason(lambda: build_draft(specs, None, None, [_detected("limits.other_ratio", 1, "1")])) == "unknown_field"
    assert _reason(lambda: build_draft(specs, None, None, [_detected(DRIFT, 1.5, "1")])) == "field_invalid"
    twice = [_detected(DRIFT, 0.1, "1"), _detected(DRIFT, 0.2, "1")]
    assert _reason(lambda: build_draft(specs, None, None, twice)) == "field_invalid"
    # a template value that breaks the FieldSpec is refused, not defaulted
    template, source = _resolved(_template(limits={"drift_ratio": _entry(5, "1")}))
    assert _reason(lambda: build_draft(specs, template, None, [], source=source)) == "field_invalid"
    # the template's ask item cannot disagree with the workflow's FieldSpec on kind
    asked, asked_source = _resolved(_template(asks=[{"path": STORIES, "label": "S", "kind": "text"}]))
    assert _reason(lambda: build_draft(specs, asked, None, [], source=asked_source)) == "field_invalid"


def test_asked_and_undeclared_fields() -> None:
    ask = {"path": STORIES, "label": "Stories", "kind": "count"}
    template, source = _resolved(
        _template(
            asks=[ask],
            limits={"drift_ratio": _entry(0.5, "1"), "other_ratio": _entry(0.1, "1")},
            analysis={"extra_count": _entry(4)},
        )
    )
    draft = build_draft(_specs(), template, None, [], source=source)
    assert STORIES in draft.pending
    assert STORIES not in draft.fields  # asked, no template value
    assert METHOD in draft.pending  # required, neither the template nor ask_each_run covers it: still asked
    assert draft.unused == ("analysis.extra_count", "limits.other_ratio")  # template values the workflow does not use
    assert "limits.other_ratio" not in draft.fields
    answered = build_draft(_specs(), template, _values(STORIES, 3), [], source=source)
    assert STORIES not in answered.pending
    assert answered.fields[STORIES].value == 3
    # a template value is found only through the source that holds its chain
    assert _reason(lambda: build_draft(_specs(), template, None, [])) == "not_found"


def test_draft_hash() -> None:
    template, source = _resolved(_template(limits={"drift_ratio": _entry(0.5, "1")}))
    values = _values(STORIES, 3)

    def make(specs: tuple[FieldSpec, ...] = _specs(), val: EngineerValues | None = values) -> str:
        return build_draft(specs, template, val, [], source=source).sha256

    first = make()
    assert first == make()
    assert len(first) == 64
    assert make(val=_values(STORIES, 4)) != first  # values
    assert make(val=None) != first  # pending list changes
    other, other_source = _resolved(_template(limits={"drift_ratio": _entry(0.6, "1")}))
    assert build_draft(_specs(), other, values, [], source=other_source).sha256 != first  # template
    relabelled = tuple(s.model_copy(update={"label": "Changed"}) for s in _specs())
    assert make(specs=relabelled) != first  # field specs
    assert make(specs=_specs()[:-1]) != first


def test_confirmation_never_carried() -> None:
    template, source = _resolved(_template(limits={"drift_ratio": _entry(0.5, "1")}))
    draft = build_draft(_specs(), template, None, [], source=source)
    assert draft == build_draft(_specs(), template, None, [], source=source)  # nothing of an earlier run enters
    assert all(field.confirmed is False for field in draft.fields.values())
    dumped = draft.model_dump_json()
    assert '"confirmed":true' not in dumped
    assert "engineer:" not in dumped
    # a previous run's confirmed flag or timestamp has no way in: the values file refuses `confirmed`
    previous = {"name": "n", "values": {DRIFT: {"value": 1, "unit": "1", "confirmed": True, "at": "2026-01-01"}}}
    assert _reason(lambda: EngineerValues.model_validate(previous)) == "confirmed_not_allowed"
