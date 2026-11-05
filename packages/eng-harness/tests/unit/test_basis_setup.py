"""Basis setup view and answer model (plan 0004 T7; spec 0004 AC26, AC27).

Every template, value and bound here is a synthetic placeholder, not an engineering value.
"""

from typing import Any

import pytest
from eng_contract.cited import Cited

from eng_harness.basis import (
    BasisSetupAnswer,
    BasisSetupPort,
    BasisSetupView,
    DetectedValue,
    EngineerEntry,
    EngineerValues,
    FieldSpec,
    build_draft,
    build_setup_view,
)
from eng_harness.templates import Template, resolve

CITE = "Synthetic placeholder, not an engineering value"
REF = "res_01JABCDEFGHJKMNPQRSTVWXYZ0#/fields/x"
SETUP_ID = "01JABCDEFGHJKMNPQRSTVWXYZ0"
SHA = "0" * 64
AT = "2026-01-01T00:00:00.000Z"
DRIFT = "limits.drift_ratio"
TOL = "modeling.merge_tolerance_mm"
STORIES = "analysis.stories"
METHOD = "analysis.method"
TITLE = "drawing.title"


class _NoParents:
    def find(self, name: str, version: str) -> Template | None:
        return None


def _specs() -> tuple[FieldSpec, ...]:
    bound = Cited(value=1.0, unit="1", citation="Synthetic bound, not an engineering value")
    return (
        FieldSpec(path=TOL, kind="quantity", label="Tolerance", unit="mm"),
        FieldSpec(path=DRIFT, kind="quantity", label="Drift", unit="1", max=bound),
        FieldSpec(path=STORIES, kind="count", label="Stories"),
        FieldSpec(path=METHOD, kind="choice", label="Method", choices=("a", "b")),
        FieldSpec(path=TITLE, kind="text", label="Title", required=False),
    )


def _view(status: str = "draft") -> BasisSetupView:
    meta: dict[str, Any] = {"name": "synthetic-base", "version": "0.1.0", "synthetic": True, "status": status}
    data = {
        "schema": "eng-template/1",
        "meta": meta,
        "ask_each_run": [],
        "limits": {"drift_ratio": {"value": 0.5, "unit": "1", "citation": CITE}},
    }
    source = _NoParents()
    template = resolve(Template.from_data(data), source)
    draft = build_draft(
        _specs(),
        template,
        EngineerValues(name="syn", values={STORIES: EngineerEntry(value=3)}),
        [DetectedValue(path=TOL, value=2.0, unit="mm", ref=REF)],
        source=source,
    )
    return build_setup_view(draft, workflow="synthetic.flow", setup_id=SETUP_ID)


def test_view_rows() -> None:
    view = _view()
    assert (view.setup_id, view.workflow) == (SETUP_ID, "synthetic.flow")
    assert view.template is not None
    assert view.template.name == "synthetic-base"
    assert view.banners == ("draft_template", "synthetic_template")
    assert [s.name for s in view.sections] == ["analysis", "drawing", "limits", "modeling"]
    sections = {s.name: s for s in view.sections}
    assert sections["analysis"].confirmable is False  # method is required and missing
    assert sections["drawing"].confirmable is True  # only an optional row is missing
    assert sections["limits"].confirmable is True
    assert sections["modeling"].confirmable is True
    rows = {r.path: r for s in view.sections for r in s.rows}
    assert rows[METHOD].state == "missing"
    assert rows[METHOD].value is None
    assert rows[TITLE].state == "missing"
    assert rows[TOL].state == "detected"
    assert rows[TOL].source == f"model:{REF}"
    assert rows[TOL].unit == "mm"
    assert rows[STORIES].state == "provided"
    assert rows[STORIES].source == "values-file:syn"
    assert rows[DRIFT].state == "provided"
    assert rows[DRIFT].citation == CITE
    assert rows[DRIFT].source == "template:synthetic-base@0.1.0"
    assert rows[DRIFT].label == "Drift"
    assert rows[DRIFT].max is not None
    assert rows[DRIFT].max.value == 1.0
    assert rows[DRIFT].min is None
    assert [r.path for r in sections["analysis"].rows] == [METHOD, STORIES]


def test_view_without_template_has_no_banners() -> None:
    draft = build_draft(_specs(), None, None, [])
    view = build_setup_view(draft, workflow="w", setup_id=SETUP_ID)
    assert view.template is None
    assert view.banners == ()
    assert view.draft_sha256 == draft.sha256


def test_approved_template_has_no_draft_banner() -> None:
    assert _view("approved").banners == ("synthetic_template",)


def test_answer_cannot_carry_values() -> None:
    ok = BasisSetupAnswer(
        setup_id=SETUP_ID, draft_sha256=SHA, confirmed_sections=("limits",), by="A. Engineer", at=AT
    )
    assert ok.confirmed_sections == ("limits",)
    assert BasisSetupAnswer(setup_id=SETUP_ID, draft_sha256=SHA, rejected="wrong value").rejected == "wrong value"
    for extra in ({"values": {DRIFT: 0.5}}, {"value": 1}, {"fields": {}}):
        with pytest.raises(ValueError, match="extra"):
            BasisSetupAnswer.model_validate({"setup_id": SETUP_ID, "draft_sha256": SHA, "rejected": "x", **extra})
    bad_forms: tuple[dict[str, Any], ...] = (
        {},  # neither form
        {"rejected": "x", "confirmed_sections": ["a"], "by": "e", "at": AT},  # both forms
        {"confirmed_sections": ["a"]},  # no by, at
        {"confirmed_sections": [], "by": "e", "at": AT},
        {"rejected": ""},
        {"rejected": "x" * 501},
    )
    for bad in bad_forms:
        with pytest.raises(ValueError):
            BasisSetupAnswer.model_validate({"setup_id": SETUP_ID, "draft_sha256": SHA, **bad})
    assert not [name for name in BasisSetupAnswer.model_fields if "value" in name]


def test_port_protocol_shape() -> None:
    class Fake:
        def __init__(self) -> None:
            self.shown: list[BasisSetupView] = []

        def present(self, view: BasisSetupView) -> None:
            self.shown.append(view)

        def answer(self, setup_id: str, *, wait: bool) -> BasisSetupAnswer | None:
            return None

    port: BasisSetupPort = Fake()
    port.present(_view())
    assert port.answer(SETUP_ID, wait=False) is None
