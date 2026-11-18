"""Template and basis properties (plan 0004 T10; spec 0004 AC30): round trip and inheritance, over random trees.

Every template, value and citation here is a generated placeholder, not an engineering value.
"""

import string
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds.basis import DesignBasis
from eng_contract.store import LocationClass, ResultStore, Workspace
from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.basis import (
    BasisSetupAnswer,
    EngineerEntry,
    EngineerValues,
    FieldSpec,
    StoreBasisPort,
    build_draft,
    freeze,
)
from eng_harness.templates import Template, resolve
from eng_harness.templates._model import SECTIONS

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
AT = "2026-01-01T00:00:00.000Z"
BY = "engineer-a"
SETUP_ID = "01JABCDEFGHJKMNPQRSTVWXYZ0"
KINDS = ("quantity", "count", "choice", "text")
CHOICES = ("a", "b", "c")
_number = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False).map(lambda v: v + 0.0)
_text = st.text(string.ascii_letters + string.digits + " é", max_size=20)
_citation = st.text(string.ascii_letters, min_size=8, max_size=40)
_origin = st.sampled_from(("template", "engineer"))


class _Source:
    def __init__(self, *templates: Template) -> None:
        self._by_key = {(t.meta.name, t.meta.version): t for t in templates}

    def find(self, name: str, version: str) -> Template | None:
        return self._by_key.get((name, version))


def _template(name: str, sections: Mapping[str, dict[str, Any]], extends: str | None = None) -> Template:
    meta: dict[str, Any] = {"name": f"synthetic-{name}", "version": "0.1.0", "synthetic": True}
    if extends is not None:
        meta["extends"] = extends
    return Template.from_data({"schema": "eng-template/1", "meta": meta, "ask_each_run": [], **sections})


def _spec(path: str, kind: str) -> FieldSpec:
    unit = "mm" if kind == "quantity" else None
    choices = CHOICES if kind == "choice" else None
    return FieldSpec.model_validate({"path": path, "kind": kind, "label": path, "unit": unit, "choices": choices})


@st.composite
def _trees(draw: st.DrawFn) -> list[tuple[str, str, str, Any, str]]:
    """Fields as (path, kind, origin, value, citation); the name suffix of a quantity is its unit's (`_mm`)."""
    rows = []
    for index in range(draw(st.integers(min_value=1, max_value=8))):
        kind = draw(st.sampled_from(KINDS))
        name = {"quantity": f"q{index}_mm", "count": f"n{index}", "choice": f"c{index}", "text": f"t{index}"}[kind]
        value = {
            "quantity": _number,
            "count": st.integers(min_value=0, max_value=10_000),
            "choice": st.sampled_from(CHOICES),
            "text": _text,
        }[kind]
        rows.append((f"{draw(st.sampled_from(SECTIONS))}.{name}", kind, draw(_origin), draw(value), draw(_citation)))
    return rows


@settings(derandomize=True, max_examples=40, deadline=None)
@given(_trees())
def test_round_trip_keeps_every_field(rows: list[tuple[str, str, str, Any, str]]) -> None:
    """entries -> fields -> payload -> load keeps path, value, unit, source and citation of every field (AC30)."""
    sections: dict[str, dict[str, Any]] = {}
    for path, kind, origin, value, citation in rows:
        if origin == "template":
            section, _, key = path.partition(".")
            unit = "mm" if kind == "quantity" else None
            sections.setdefault(section, {})[key] = {"value": value, "unit": unit, "citation": citation}
    base = _template("base", sections)
    source = _Source(base)
    mine = {
        path: EngineerEntry(value=value, unit="mm" if kind == "quantity" else None)
        for path, kind, origin, value, _ in rows
        if origin == "engineer"
    }
    draft = build_draft(
        [_spec(path, kind) for path, kind, *_ in rows],
        resolve(base, source),
        EngineerValues(name="syn", values=mine),
        [],
        source=source,
    )
    answer = BasisSetupAnswer(
        setup_id=SETUP_ID,
        draft_sha256=draft.sha256,
        confirmed_sections=tuple(sorted({path.partition(".")[0] for path, *_ in rows})),
        by=BY,
        at=AT,
    )
    with tempfile.TemporaryDirectory() as root:
        clock = FixedClock(START_MS, 1)
        store = ResultStore(
            Workspace(root=Path(root) / "ws", classification=LocationClass.LOCAL),
            HARNESS_KINDS,
            SeededIdSource(b"harness", clock),
            clock,
        )
        frozen = freeze(draft, answer, store, clock)
        loaded = StoreBasisPort(store).load(frozen.ref)
    fields = loaded.basis.fields
    assert set(fields) == {path for path, *_ in rows}
    for path, kind, origin, value, citation in rows:
        found = fields[path]
        assert found.value == value
        assert found.unit == ("mm" if kind == "quantity" else None)
        assert found.confirmed is True
        if origin == "template":
            assert (found.source, found.citation) == ("template:synthetic-base@0.1.0", citation)
        else:
            assert (found.source, found.citation) == (f"engineer:{BY}@{AT}", None)
    assert DesignBasis.model_validate(loaded.basis.model_dump(mode="json")) == loaded.basis


_pool = [f"{section}.p{index}_mm" for section in ("limits", "modeling") for index in range(3)]
_links = st.lists(st.lists(st.sampled_from(_pool), unique=True, max_size=len(_pool)), min_size=1, max_size=4)


def _paths(template: Template) -> set[str]:
    return {f"{name}.{key}" for name in SECTIONS for key in getattr(template, name)}


@settings(derandomize=True, max_examples=60, deadline=None)
@given(_links)
def test_chain_yields_the_union_of_paths(chain: list[list[str]]) -> None:
    """An inheritance chain yields the union of the chain's paths; the nearest link to the child defines each (AC30)."""
    templates: list[Template] = []
    for depth, paths in enumerate(chain):
        sections: dict[str, dict[str, Any]] = {}
        for path in paths:
            section, _, key = path.partition(".")
            entry = {"value": float(depth), "unit": "mm", "citation": f"Synthetic link {depth} placeholder"}
            sections.setdefault(section, {})[key] = entry
        extends = f"synthetic-l{depth - 1}@0.1.0" if depth else None
        templates.append(_template(f"l{depth}", sections, extends))
    resolved = resolve(templates[-1], _Source(*templates))
    assert _paths(resolved.template) == {path for paths in chain for path in paths}
    assert [f"{link.name}@{link.version}" for link in resolved.chain] == [
        f"synthetic-l{depth}@0.1.0" for depth in reversed(range(len(chain)))
    ]
    for path in _paths(resolved.template):
        section, _, key = path.partition(".")
        owner = max(depth for depth, paths in enumerate(chain) if path in paths)  # the link nearest the child
        assert getattr(resolved.template, section)[key].value == float(owner)
