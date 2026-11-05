"""Freeze and storage of the design basis (plan 0004 T8; spec 0004 AC22 to AC25), against the contract result store.

Every template, value and bound here is a synthetic placeholder, not an engineering value.
"""

from pathlib import Path
from typing import Any

import pytest
from eng_contract.cited import Cited
from eng_contract.envelope import Provenance
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock
from eng_contract.kinds.basis import DesignBasis
from eng_contract.store import ResultStore

from eng_harness.basis import (
    BasisDraft,
    BasisIncomplete,
    BasisInvalid,
    BasisNotConfirmed,
    BasisSetupAnswer,
    DetectedValue,
    EngineerEntry,
    EngineerValues,
    FieldSpec,
    FrozenBasis,
    StoreBasisPort,
    build_draft,
    freeze,
)
from eng_harness.templates import Template, resolve

CITE = "Synthetic placeholder, not an engineering value"
REF = "res_01JABCDEFGHJKMNPQRSTVWXYZ0#/fields/x"
SETUP_ID = "01JABCDEFGHJKMNPQRSTVWXYZ0"
UNKNOWN_ID = "res_01JABCDEFGHJKMNPQRSTVWXYZ0"
AT = "2026-01-01T00:00:00.000Z"
BY = "engineer-a"
DRIFT = "limits.drift_ratio"
TOL = "modeling.merge_tolerance_mm"
STORIES = "analysis.stories"
METHOD = "analysis.method"
TITLE = "drawing.title"
ALL_SECTIONS = ("analysis", "drawing", "limits", "modeling")


class _Source:
    def __init__(self, template: Template) -> None:
        self._template = template

    def find(self, name: str, version: str) -> Template | None:
        meta = self._template.meta
        return self._template if (name, version) == (meta.name, meta.version) else None


def _specs() -> tuple[FieldSpec, ...]:
    bound = Cited(value=1.0, unit="1", source="Synthetic bound, not an engineering value")
    return (
        FieldSpec(path=TOL, kind="quantity", label="Tolerance", unit="mm"),
        FieldSpec(path=DRIFT, kind="quantity", label="Drift", unit="1", max=bound),
        FieldSpec(path=STORIES, kind="count", label="Stories"),
        FieldSpec(path=METHOD, kind="choice", label="Method", choices=("a", "b")),
        FieldSpec(path=TITLE, kind="text", label="Title", required=False),
    )


def _draft(*, method: str | None = "a", drift: float = 0.5) -> BasisDraft:
    values: dict[str, EngineerEntry] = {STORIES: EngineerEntry(value=3), TITLE: EngineerEntry(value="synthetic-title")}
    if method is not None:
        values[METHOD] = EngineerEntry(value=method)
    data: dict[str, Any] = {
        "schema": "eng-template/1",
        "meta": {"name": "synthetic-base", "version": "0.1.0", "synthetic": True},
        "ask_each_run": [],
        "limits": {"drift_ratio": {"value": drift, "unit": "1", "citation": CITE}},
    }
    base = Template.from_data(data)
    source = _Source(base)
    return build_draft(
        _specs(),
        resolve(base, source),
        EngineerValues(name="syn", values=values),
        [DetectedValue(path=TOL, value=2.0, unit="mm", ref=REF)],
        source=source,
    )


def _answer(draft: BasisDraft, sections: tuple[str, ...] = ALL_SECTIONS) -> BasisSetupAnswer:
    return BasisSetupAnswer(setup_id=SETUP_ID, draft_sha256=draft.sha256, confirmed_sections=sections, by=BY, at=AT)


def _count(root: Path) -> int:
    results = root / "ws" / "results"
    return len(list(results.rglob("*.json"))) if results.exists() else 0


def test_refusals(store: ResultStore, clock: FixedClock, tmp_path: Path) -> None:
    draft = _draft()
    other = _draft(drift=0.25)
    incomplete = _draft(method=None)
    rejected = BasisSetupAnswer(setup_id=SETUP_ID, draft_sha256=draft.sha256, rejected="not right")
    empty = _answer(draft).model_copy(update={"confirmed_sections": ()})
    cases: list[tuple[BasisDraft, BasisSetupAnswer, str]] = [
        (draft, _answer(other), "draft_changed"),
        (draft, _answer(draft, ("nowhere",)), "draft_changed"),
        (incomplete, _answer(incomplete), "section_incomplete"),
        (draft, rejected, "rejected"),
        (draft, empty, "nothing_confirmed"),
    ]
    for case_draft, answer, reason in cases:
        with pytest.raises(BasisNotConfirmed) as caught:
            freeze(case_draft, answer, store, clock)
        assert caught.value.reason == reason
        assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert _count(tmp_path) == 0


def test_engineer_source_from_answer(store: ResultStore, clock: FixedClock) -> None:
    draft = _draft()
    frozen = freeze(draft, _answer(draft), store, clock)
    fields = DesignBasis.model_validate(store.payload(frozen.ref)).fields
    assert fields[STORIES].source == f"engineer:{BY}@{AT}"
    assert fields[METHOD].source == f"engineer:{BY}@{AT}"
    assert fields[TITLE].source == f"engineer:{BY}@{AT}"
    assert fields[TOL].source == f"model:{REF}"
    assert fields[DRIFT].source == "template:synthetic-base@0.1.0"
    assert fields[DRIFT].citation == CITE


def test_incomplete_lists_paths(store: ResultStore, clock: FixedClock, tmp_path: Path) -> None:
    missing = _draft(method=None)
    with pytest.raises(BasisIncomplete) as caught:
        freeze(missing, _answer(missing, ("drawing", "limits", "modeling")), store, clock)
    assert caught.value.paths == (STORIES, METHOD)  # required, in declaration order: unconfirmed, then absent
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    complete = _draft()
    with pytest.raises(BasisIncomplete) as caught_optional:
        freeze(complete, _answer(complete, ("analysis", "limits", "modeling")), store, clock)
    assert caught_optional.value.paths == (TITLE,)  # a present field in an unconfirmed section
    assert _count(tmp_path) == 0


def test_freeze_stores_result(store: ResultStore, clock: FixedClock) -> None:
    draft = _draft()
    frozen = freeze(draft, _answer(draft), store, clock)
    assert isinstance(frozen, FrozenBasis)
    record = store.get(frozen.result_id)
    assert record.kind == "basis.design_basis/1"
    assert frozen.ref == frozen.result_id
    assert frozen.payload_sha256 == record.payload_sha256
    basis = DesignBasis.model_validate(store.payload(frozen.result_id))
    assert set(basis.fields) == {TOL, DRIFT, STORIES, METHOD, TITLE}
    assert all(field.confirmed for field in basis.fields.values())
    assert basis.template is not None
    assert (basis.template.name, basis.template.version) == ("synthetic-base", "0.1.0")
    assert draft.template is not None
    assert basis.template.sha256 == draft.template.sha256
    assert basis.missing([TOL, DRIFT, STORIES, METHOD]) == []


def test_freeze_without_template_stores_null_template(store: ResultStore, clock: FixedClock) -> None:
    values = {
        TOL: EngineerEntry(value=2.0, unit="mm"),
        DRIFT: EngineerEntry(value=0.5, unit="1"),
        STORIES: EngineerEntry(value=3),
        METHOD: EngineerEntry(value="b"),
    }
    draft = build_draft(_specs(), None, EngineerValues(name="syn", values=values), [])
    frozen = freeze(draft, _answer(draft, ("analysis", "limits", "modeling")), store, clock)
    assert store.payload(frozen.result_id)["template"] is None


def test_stored_basis_immutable(store: ResultStore, clock: FixedClock, tmp_path: Path) -> None:
    draft = _draft()
    first = freeze(draft, _answer(draft), store, clock)
    second = freeze(draft, _answer(draft), store, clock)
    assert first.payload_sha256 == second.payload_sha256
    assert first.result_id != second.result_id
    port = StoreBasisPort(store)
    loaded = port.load(first.ref)
    assert loaded.result_id == first.result_id
    assert loaded.basis.fields[DRIFT].value == 0.5
    changed = _draft(drift=0.25)
    third = freeze(changed, _answer(changed), store, clock)
    assert third.payload_sha256 != first.payload_sha256
    assert port.load(first.ref) == loaded
    assert port.load(third.ref).basis.fields[DRIFT].value == 0.25
    producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=AT, duration_ms=0)
    blob = store.put("harness.journal_blob/1", {"value": 1}, producer)
    for ref, reason in ((blob.result_id, "not_a_basis"), (UNKNOWN_ID, "not_found"), ("nonsense", "not_found")):
        with pytest.raises(BasisInvalid) as caught:
            port.load(ref)
        assert caught.value.reason == reason
    (path,) = list((tmp_path / "ws" / "results").rglob(f"{first.result_id}.json"))
    path.write_bytes(path.read_bytes().replace(b"synthetic-title", b"synthetic-titlX"))
    with pytest.raises(BasisInvalid) as damaged:
        port.load(first.ref)
    assert damaged.value.reason == "hash_mismatch"
