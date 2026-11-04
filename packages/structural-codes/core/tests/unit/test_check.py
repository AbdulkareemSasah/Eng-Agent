"""Tests of the @check decorator (plan 0001 T6; spec 0001 AC5b, section 4.6)."""

from typing import Any

import pytest
from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind

from structural_codes.applicability import Outcome, Precondition
from structural_codes.check import Check, check
from structural_codes.errors import CheckDefinitionError
from structural_codes.inputs import CheckInputs, bounded
from structural_codes.meta import CheckMeta
from structural_codes.trace import TraceRecorder

_LOW = Cited(value=0, unit="mm", source="synthetic lower bound")
_HIGH = Cited(value=100, unit="mm", source="synthetic upper bound")


class _In(CheckInputs):
    width_mm: float = bounded(ge=_LOW, le=_HIGH, unit="mm")


def _meta(unconditional: str | None = None) -> CheckMeta:
    return CheckMeta(
        check_id="packx.1_1.demo",
        pack="packx",
        code="Synthetic Code",
        edition="1",
        clauses=("1.1",),
        title="Demo",
        members=frozenset({SubjectKind.SECTION}),
        spec="packx/demo.md",
        unconditional=unconditional,
    )


def _body(inp: _In, t: TraceRecorder) -> None:
    return None


def _pre(pre_id: str = "P1") -> Precondition:
    return Precondition(pre_id, Outcome.NEEDS_ENGINEER, "1.1", "synthetic", lambda inp, t: True)


def test_applicability_declared() -> None:
    with pytest.raises(CheckDefinitionError, match="unconditional"):
        check(meta=_meta(), inputs=_In, preconditions=())(_body)
    with pytest.raises(CheckDefinitionError, match="both"):
        check(meta=_meta("section 1"), inputs=_In, preconditions=(_pre(),))(_body)
    plain = check(meta=_meta("section 1"), inputs=_In, preconditions=())(_body)
    guarded = check(meta=_meta(), inputs=_In, preconditions=(_pre(),))(_body)
    for made in (plain, guarded):
        assert isinstance(made, Check)
        assert made.meta.check_id == "packx.1_1.demo"
        assert made.inputs is _In
        assert made.body is _body
        assert made.module == _body.__module__
    assert plain.preconditions == ()
    assert len(guarded.preconditions) == 1


def test_definition_errors() -> None:
    bad_inputs: Any = dict
    with pytest.raises(CheckDefinitionError, match="CheckInputs"):
        check(meta=_meta("s"), inputs=bad_inputs, preconditions=())(_body)
    with pytest.raises(CheckDefinitionError, match="twice"):
        check(meta=_meta(), inputs=_In, preconditions=(_pre(), _pre()))(_body)
    bad_pre: Any = (object(),)
    with pytest.raises(CheckDefinitionError, match="Precondition"):
        check(meta=_meta(), inputs=_In, preconditions=bad_pre)(_body)
