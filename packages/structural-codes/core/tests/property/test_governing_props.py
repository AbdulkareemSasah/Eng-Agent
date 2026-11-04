"""Property test of governing selection (plan 0001 T5; spec 0001 AC14); Hypothesis runs derandomized."""

from eng_contract.quantity import Quantity
from eng_contract.verdicts import Subject, SubjectKind, Verdict, VerdictSource, VerdictStatus
from hypothesis import given, settings
from hypothesis import strategies as st

from structural_codes._verdict import assign_governing

_SIZED = (VerdictStatus.PASS, VerdictStatus.FAIL)
_ratios = st.sampled_from([0.0, 0.25, 0.5, 0.5, 0.9, 1.0, 1.1, 2.0])
_items = st.lists(
    st.tuples(st.sampled_from(["A", "B", "C"]), st.sampled_from(list(VerdictStatus)), _ratios, st.booleans()),
    max_size=14,
)


def _verdict(subject_id: str, status: VerdictStatus, ratio: float, preset: bool) -> Verdict:
    sized = status in _SIZED
    if status is VerdictStatus.PASS:
        ratio = min(ratio, 1.0)
    if status is VerdictStatus.FAIL:
        ratio = max(ratio, 1.1)
    return Verdict(
        source=VerdictSource.CODE_PACK,
        check_id="synth.21_2_1.demo",
        code="Synthetic Code",
        clause="21.2.1",
        subject=Subject(kind=SubjectKind.FOOTING, id=subject_id),
        demand=Quantity(ratio, "kN") if sized else None,
        capacity=Quantity(1.0, "kN") if sized else None,
        ratio=ratio if sized else None,
        status=status,
        governing=preset,
        trace_ref="#/traces/0",
    )


@settings(derandomize=True, max_examples=200, deadline=None)
@given(_items)
def test_one_governing_per_subject(items: list[tuple[str, VerdictStatus, float, bool]]) -> None:
    batch = [_verdict(*item) for item in items]
    result = assign_governing(batch)

    assert len(result) == len(batch)
    for before, after in zip(batch, result, strict=True):
        assert after.model_copy(update={"governing": before.governing}) == before
    for subject_id in ("A", "B", "C"):
        own = [(i, v) for i, v in enumerate(result) if v.subject.id == subject_id]
        sized = [(i, v) for i, v in own if v.status in _SIZED]
        flagged = [i for i, v in own if v.governing]
        if not sized:
            assert flagged == []
            continue
        assert len(flagged) == 1
        top = max(v.ratio for _, v in sized if v.ratio is not None)
        first_top = next(i for i, v in sized if v.ratio == top)
        assert flagged == [first_top]
