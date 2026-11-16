"""Golden cases and contract of harness.analysis_summary (plan 0007 T4; spec 0007 AC30, section 4.4.4, gap EC-G3)."""

import copy
from typing import Any

from eng_harness.calc import InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs.edit_cycle.analysis_summary import SummaryInput, analysis_summary

from . import EditCycleGoldenCase, load_cases

KINDS = {
    "messages": "harness.csi_analysis_messages/1",
    "drifts": "forces.story_drifts/1",
    "basis": "basis.design_basis/1",
}
"""The record kind of each reference input of `harness.analysis_summary`."""
STEMS = [
    "analysis-clean",
    "analysis-drift-exceeding",
    "analysis-messages-unclassified",
    "analysis-no-drifts",
]


def meta_for(refs: dict[str, str]) -> InputMeta:
    """`InputMeta` of the summary calc: three complete records."""
    return InputMeta(
        refs={
            name: RefMeta(
                result_id=result_id,
                kind=KINDS[name],
                complete=True,
                model_id=None,
                model_revision=None,
                parents=(),
                producer_tool="csi" if name != "basis" else "harness",
            )
            for name, result_id in refs.items()
        }
    )


def run_summary(
    case: EditCycleGoldenCase, *, trace: TraceBuilder | None = None, meta: InputMeta | None = None, **changes: Any
) -> dict[str, Any]:
    """Run `harness.analysis_summary` on the case input with some input fields replaced."""
    inp = SummaryInput.model_validate(copy.deepcopy(case.input) | changes)
    return analysis_summary(inp, meta or meta_for(case.refs), trace or TraceBuilder()).model_dump(mode="json")


def test_golden_cases() -> None:
    cases = load_cases("analysis")
    assert sorted(cases) == STEMS
    actual = {stem: run_summary(case) for stem, case in cases.items()}
    assert {stem: body for stem, body in actual.items() if body != cases[stem].expected} == {}
