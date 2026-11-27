"""Contract test of the verdicts the builder produces (plan 0001 T5; spec 0001 AC15)."""

import pytest
from eng_contract.envelope import LiteralInput
from eng_contract.params import ValidatedInput
from eng_contract.quantity import Quantity
from eng_contract.verdicts import Subject, SubjectKind, Verdict, VerdictSource, VerdictStatus

from structural_codes._verdict import VerdictDraft, build_verdict
from structural_codes.errors import CheckDefinitionError
from structural_codes.inputs import CheckInputs
from structural_codes.meta import CheckMeta
from structural_codes.trace import TraceRecorder

_SUBJECT = Subject(kind=SubjectKind.FOOTING, id="F7", case="COMB2")
_META = CheckMeta(
    check_id="synth.21_2_1.demo",
    pack="synth",
    code="Synthetic Code",
    edition="1",
    clauses=("21.2.1", "21.2.2"),
    title="Synthetic demo",
    members=frozenset({SubjectKind.FOOTING}),
    spec="clauses/demo.md",
    assumptions=("check assumption",),
)


def _draft(
    demand: float, capacity: float, *, clause: str | None = None, assumptions: tuple[str, ...] = ()
) -> VerdictDraft:
    t = TraceRecorder(
        ValidatedInput(CheckInputs(), {"ratio_limit": LiteralInput(literal=None)}),
        calc_id=_META.check_id,
        calc_version="1.0.0",
        content_sha256="b" * 64,
        subject=_SUBJECT,
    )
    t.step("demand_kN", demand, unit="kN", formula="x", source="synthetic", uses=[])
    t.step("capacity_kN", capacity, unit="kN", formula="x", source="synthetic", uses=[])
    t.verdict(demand="demand_kN", capacity="capacity_kN", clause=clause, assumptions=assumptions)
    return t.verdicts[0]


def test_verdict_fields() -> None:
    verdict = build_verdict(_draft(60.0, 100.0), _META, _SUBJECT, trace_index=3)
    assert Verdict.model_validate(verdict.model_dump()) == verdict
    assert verdict.source is VerdictSource.CODE_PACK
    assert verdict.check_id == "synth.21_2_1.demo"
    assert verdict.code == "Synthetic Code"
    assert verdict.clause == "21.2.1"
    assert verdict.subject == _SUBJECT
    assert verdict.demand == Quantity(60.0, "kN")
    assert verdict.capacity == Quantity(100.0, "kN")
    assert verdict.ratio == 0.6
    assert verdict.ratio_limit == 1.0
    assert verdict.status is VerdictStatus.PASS
    assert verdict.governing is False
    assert verdict.trace_ref == "#/traces/3"
    assert verdict.assumptions == ["check assumption"]

    chosen = build_verdict(
        _draft(120.0, 100.0, clause="21.2.2", assumptions=("own assumption",)), _META, _SUBJECT, trace_index=0
    )
    assert chosen.clause == "21.2.2"
    assert chosen.status is VerdictStatus.FAIL
    assert chosen.assumptions == ["check assumption", "own assumption"]
    assert chosen.trace_ref == "#/traces/0"

    failed = build_verdict(_draft(1.0, 0.0), _META, _SUBJECT, trace_index=1)
    assert Verdict.model_validate(failed.model_dump()) == failed
    assert failed.status is VerdictStatus.ERROR
    assert failed.ratio is None
    assert failed.clause == "21.2.1"
    assert failed.capacity == Quantity(0.0, "kN")

    with pytest.raises(CheckDefinitionError, match=r"9\.9\.9"):
        build_verdict(_draft(1.0, 2.0, clause="9.9.9"), _META, _SUBJECT, trace_index=0)
