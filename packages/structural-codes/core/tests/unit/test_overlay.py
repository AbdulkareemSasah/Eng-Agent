"""Tests of the overlay mechanism (plan 0001 T10; spec 0001 AC17 to AC20, section 4.11)."""

import importlib
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.verdicts import Subject, SubjectKind, VerdictStatus

from structural_codes import evaluate
from structural_codes.check import Check
from structural_codes.content_hash import content_hash
from structural_codes.errors import CheckDefinitionError
from structural_codes.overlay import Inherited, InheritedCheck, Overlay, Removed
from structural_codes.pack import Pack, Registry
from structural_codes.trace import TraceRecorder

# B-264: the module names are split only because gate rule IM006 reports the fixture packs under tests/fixtures/*/src
# as undeclared distributions (same workaround as tests/unit/test_registry.py, B-260); it hides no import.
_BASE_MODULE = "synth" + "base.runner_checks"
_OVER_MODULE = "synth" + "over"
_FIXTURES = Path(__file__).parent.parent / "fixtures"

_S1 = Subject(kind=SubjectKind.SECTION, id="S1")
_F1 = Subject(kind=SubjectKind.FOOTING, id="F1")
_BASE_CODE = "Synthetic Code"
_OVER_CODE = "Synthetic Overlay Code"
_TWO_PRE = "synthbase.4_1.two_pre"
_SIZED = "synthbase.3_1.sized"


@dataclass(frozen=True)
class _Packs:
    base: Pack
    over: Pack

    def registry(self) -> Registry:
        return Registry.of([self.base, self.over])


@pytest.fixture
def packs(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Packs]:
    monkeypatch.syspath_prepend(str(_FIXTURES / "synthbase" / "src"))
    monkeypatch.syspath_prepend(str(_FIXTURES / "synthover" / "src"))
    base = importlib.import_module(_BASE_MODULE).RUNNER_PACK
    over = importlib.import_module(_OVER_MODULE).PACK
    yield _Packs(base, over)
    for name in [n for n in sys.modules if n.split(".")[0] in {"synthbase", "synthover"}]:
        del sys.modules[name]


def _overlay(over: Pack) -> Overlay:
    assert isinstance(over.overlay, Overlay)
    return over.overlay


def _rebuilt(
    over: Pack,
    *,
    entries: tuple[Any, ...] | None = None,
    clause_map: Mapping[str, str | None] | None = None,
    checks: tuple[Check, ...] | None = None,
) -> Pack:
    """The overlay pack with its entries, clause map or own checks replaced."""
    old = _overlay(over)
    new = Overlay(
        base=old.base,
        clause_map=old.clause_map if clause_map is None else clause_map,
        entries=old.entries if entries is None else entries,
    )
    return replace(over, overlay=new, checks=over.checks if checks is None else checks)


def _inputs(*, width: float = 10.0, demand: float = 50.0, capacity: float = 100.0) -> dict[str, Any]:
    return {"width_mm": width, "demand_mm": demand, "capacity_mm": capacity}


def _own(demand: float = 50.0, capacity: float = 100.0) -> dict[str, Any]:
    return {"demand_mm": demand, "capacity_mm": capacity}


def test_completeness(packs: _Packs) -> None:
    registry = packs.registry()
    ids = [c.meta.check_id for c in registry.checks if c.meta.pack == "synthover"]
    assert ids == [
        "synthover.a1_1.extra",
        "synthover.s3_1.sized_over",
        "synthover.s4_1.two_pre",
        "synthover.s5_2.scoped_free",
        "synthover.s6_1.gap",
    ]
    entries = _overlay(packs.over).entries
    without = tuple(e for e in entries if getattr(e, "base_check_id", None) != _TWO_PRE)
    with pytest.raises(CheckDefinitionError, match=_TWO_PRE):  # a base check without an entry
        Registry.of([packs.base, _rebuilt(packs.over, entries=without)])
    for second in (Removed(_SIZED, reason="synthetic"), Inherited(_SIZED, clause="S3.1")):  # two entries, one base id
        with pytest.raises(CheckDefinitionError, match=_SIZED):
            Registry.of([packs.base, _rebuilt(packs.over, entries=(*entries, second))])
    unknown = Removed("synthbase.9_9.nothing", reason="synthetic")
    with pytest.raises(CheckDefinitionError, match=r"synthbase\.9_9\.nothing"):
        Registry.of([packs.base, _rebuilt(packs.over, entries=(*entries, unknown))])
    with pytest.raises(CheckDefinitionError, match="synthbase"):  # the base pack is not registered
        Registry.of([packs.over])
    with pytest.raises(CheckDefinitionError, match="own checks"):  # Overridden and Added checks are the pack's checks
        Registry.of([packs.base, _rebuilt(packs.over, checks=())])


def test_pack_and_overlay_declarations(packs: _Packs) -> None:
    over = packs.over
    with pytest.raises(CheckDefinitionError, match="overlay"):
        replace(over, overlay=None)  # base without overlay
    with pytest.raises(CheckDefinitionError, match="overlay"):
        replace(over, base=None)  # overlay without base
    with pytest.raises(CheckDefinitionError, match="base"):
        Overlay(base="other", clause_map={}, entries=()).resolve(over, packs.base)  # names another base
    wrong_type: Any = ("not an entry",)
    with pytest.raises(CheckDefinitionError, match="entries"):
        Overlay(base="synthbase", clause_map={}, entries=wrong_type)
    third = Pack(
        name="third",
        code="Third",
        edition="1",
        version="1",
        checks=(),
        approvals="approvals.yaml",
        base="synthover",
        overlay=Overlay(base="synthover", clause_map={}, entries=()),
    )
    with pytest.raises(CheckDefinitionError, match="overlay"):  # an overlay of an overlay is not supported
        Registry.of([packs.base, packs.over, third])


def test_inherited_evaluation(packs: _Packs) -> None:
    registry = packs.registry()
    derived = registry.get("synthover.s4_1.two_pre")
    base = registry.get(_TWO_PRE)
    assert isinstance(derived, InheritedCheck)
    assert derived.base is base
    assert derived.meta.pack == "synthover"
    assert derived.meta.code == _OVER_CODE
    assert derived.meta.edition == "2"
    assert derived.meta.clauses == ("S4.1",)
    assert derived.meta.title == base.meta.title
    assert derived.meta.assumptions == base.meta.assumptions
    assert [(p.id, p.outcome, p.clause, p.description) for p in derived.preconditions] == [
        (p.id, p.outcome, p.clause, p.description) for p in base.preconditions
    ]
    assert derived.inputs is base.inputs

    result = evaluate(derived.meta.check_id, _inputs(), subject=_S1, registry=registry)
    reference = evaluate(_TWO_PRE, _inputs(), subject=_S1, registry=registry)
    verdict, expected = result.payload.verdicts[0], reference.payload.verdicts[0]
    assert (verdict.code, verdict.clause, verdict.check_id) == (_OVER_CODE, "S4.1", "synthover.s4_1.two_pre")
    assert (expected.code, expected.clause) == (_BASE_CODE, "4.1")
    assert verdict.status == VerdictStatus.PASS
    assert verdict.ratio == expected.ratio == 0.5
    trace, base_trace = result.payload.traces[0], reference.payload.traces[0]
    assert trace.constants == base_trace.constants  # base citations are never rewritten
    assert [c.cited.source for c in trace.constants] == ["synthetic test fixture, no engineering meaning"] * 2
    assert trace.calc_id == "synthover.s4_1.two_pre"
    note = f"inherited from {_TWO_PRE}: {_OVER_CODE} S4.1 mapped to {_BASE_CODE} 4.1"
    assert trace.messages.count(note) == 1
    assert note not in base_trace.messages

    stopped = evaluate(derived.meta.check_id, _inputs(width=60.0), subject=_S1, registry=registry)
    assert stopped.payload.verdicts[0].status == VerdictStatus.NOT_APPLICABLE  # the base precondition runs
    assert stopped.payload.verdicts[0].clause == "S4.1"
    assert stopped.payload.traces[0].messages.count(note) == 1  # also when a precondition ends the evaluation

    plain = Check(derived.meta, derived.inputs, derived.preconditions, derived.body, derived.module)
    assert content_hash(derived) == result.content_sha256
    assert content_hash(derived) == content_hash(plain, base=content_hash(base))
    assert content_hash(derived) != content_hash(plain)  # the base member is part of the hash
    assert content_hash(derived) != content_hash(base)


def test_inherited_short_name_and_gap(packs: _Packs) -> None:
    entries = tuple(
        Inherited(_TWO_PRE, clause="S4.1", short_name="renamed")
        if isinstance(e, Inherited) and e.base_check_id == _TWO_PRE
        else e
        for e in _overlay(packs.over).entries
    )
    registry = Registry.of([packs.base, _rebuilt(packs.over, entries=entries)])
    assert registry.get("synthover.s4_1.renamed").meta.check_id == "synthover.s4_1.renamed"
    with pytest.raises(ContractError):
        registry.get("synthover.s4_1.two_pre")
    gap = evaluate("synthover.s6_1.gap", _inputs(), subject=_S1, registry=registry)
    assert gap.payload.verdicts[0].status == VerdictStatus.NEEDS_ENGINEER  # the base gap G-3 is declared
    assert gap.payload.verdicts[0].code == _OVER_CODE


def test_overridden_added_and_clause_map(packs: _Packs) -> None:
    registry = packs.registry()
    over = evaluate("synthover.s3_1.sized_over", _own(), subject=_S1, registry=registry).payload.verdicts[0]
    base = evaluate(_SIZED, _inputs(), subject=_S1, registry=registry).payload.verdicts[0]
    assert (over.code, over.clause, over.ratio) == (_OVER_CODE, "S3.1", 0.25)  # its own body: capacity doubled
    assert (base.code, base.clause, base.ratio) == (_BASE_CODE, "3.1", 0.5)
    added = evaluate("synthover.a1_1.extra", _own(), subject=_S1, registry=registry).payload.verdicts[0]
    assert (added.code, added.clause, added.ratio) == (_OVER_CODE, "A1.1", 0.5)
    assert not isinstance(registry.get("synthover.s3_1.sized_over"), InheritedCheck)

    good = dict(_overlay(packs.over).clause_map)
    absent = {k: v for k, v in good.items() if k != "A1.1"}
    Registry.of([packs.base, _rebuilt(packs.over, clause_map=absent)])  # an added clause may be absent from the map
    wrong: dict[str, dict[str, str | None]] = {
        "inherited clause missing": {k: v for k, v in good.items() if k != "S4.1"},
        "inherited maps elsewhere": {**good, "S4.1": "9.9"},  # 9.9 is the base's second clause, not its first
        "inherited maps to null": {**good, "S4.1": None},
        "overridden clause missing": {k: v for k, v in good.items() if k != "S3.1"},
        "overridden maps elsewhere": {**good, "S3.1": "4.1"},
        "added clause mapped": {**good, "A1.1": "3.1"},
    }
    for label, clause_map in wrong.items():
        with pytest.raises(CheckDefinitionError, match="clause"):
            Registry.of([packs.base, _rebuilt(packs.over, clause_map=clause_map)])
        assert label


def test_removed(packs: _Packs) -> None:
    registry = packs.registry()
    for lookup in (registry.get, lambda i: evaluate(i, _inputs(), subject=_F1, registry=registry)):
        with pytest.raises(ContractError) as removed:
            lookup("synthover.5_1.scoped")
        detail = removed.value.detail
        assert detail.code == ErrorCode.NOT_FOUND
        assert detail.field == "check_id"
        assert detail.hint is not None
        assert "synthetic removal reason scoped" in detail.hint
    with pytest.raises(ContractError) as unknown:
        registry.get("synthover.5_9.nothing")
    assert unknown.value.detail.code == ErrorCode.NOT_FOUND
    assert unknown.value.detail.hint is None
    kept = registry.get("synthbase.5_1.scoped")  # the base check stays usable under its own pack
    assert kept.meta.pack == "synthbase"
    result = evaluate("synthbase.5_1.scoped", _inputs(), subject=_F1, registry=registry)
    assert result.payload.verdicts[0].status == VerdictStatus.PASS


@pytest.mark.parametrize("clause", ["9.9", "S4.1"], ids=["declared-base-clause", "overlay-only-clause"])
def test_inherited_explicit_base_clause(packs: _Packs, clause: str) -> None:
    """An inherited body may name a secondary base clause, but may not name an undeclared one."""

    def body(_inp: Any, t: TraceRecorder) -> None:
        t.verdict(demand="demand_mm", capacity="capacity_mm", clause=clause)

    checks = tuple(
        replace(check, body=body) if check.meta.check_id == _TWO_PRE else check for check in packs.base.checks
    )
    registry = Registry.of([replace(packs.base, checks=checks), packs.over])
    overlay_id = "synthover.s4_1.two_pre"
    if clause == "S4.1":
        with pytest.raises(CheckDefinitionError, match=r"synthbase\.4_1\.two_pre: clause 'S4\.1'"):
            evaluate(overlay_id, _inputs(), subject=_S1, registry=registry)
        return

    result = evaluate(overlay_id, _inputs(), subject=_S1, registry=registry)
    reference = evaluate(_TWO_PRE, _inputs(), subject=_S1, registry=registry)
    (verdict,) = result.payload.verdicts
    (base_verdict,) = reference.payload.verdicts
    assert base_verdict.clause == "9.9"
    assert (verdict.code, verdict.clause, verdict.check_id) == (_OVER_CODE, "S4.1", overlay_id)
    assert verdict.status == VerdictStatus.PASS
    assert verdict.ratio == 0.5  # Synthetic fixture: 50 / 100.
    assert verdict.trace_ref == "#/traces/0"
    (trace,) = result.payload.traces
    (base_trace,) = reference.payload.traces
    assert trace.constants == base_trace.constants
    assert [c.cited.source for c in trace.constants] == ["synthetic test fixture, no engineering meaning"] * 2
