"""Golden cases of harness.safe_equilibrium (plan 0010 T10; spec 0010 AC25, section 4.9)."""

from __future__ import annotations

import copy
from typing import Any

from eng_harness.calc import TraceBuilder
from eng_harness.calcs.footing.safe_equilibrium import EquilibriumInput, safe_equilibrium

from . import FootingGoldenCase, input_meta, load_cases

CALC_ID = "harness.safe_equilibrium"
KINDS = {
    "loads": "harness.joint_loads/1",
    "base_reactions": "harness.base_reactions/1",
    "safe_load_set": "model.load_set/1",
    "basis": "basis.design_basis/1",
}
STEMS = [
    "equilibrium-at-tolerance",
    "equilibrium-fail-outside",
    "equilibrium-pass-within",
    "equilibrium-self-weight-not-compared",
]


def _run(case: FootingGoldenCase, trace: TraceBuilder | None = None, **changes: Any) -> dict[str, Any]:
    raw = copy.deepcopy(case.input) | changes
    result = safe_equilibrium(
        EquilibriumInput.model_validate(raw), input_meta(case.refs, KINDS), trace or TraceBuilder()
    )
    return result.model_dump(mode="json")


def test_golden_cases() -> None:
    """AC25: within and outside the tolerance; a self-weight pattern not compared; boundary inclusive."""
    cases = load_cases("equilibrium")
    assert sorted(cases) == STEMS
    actual = {stem: _run(case) for stem, case in cases.items()}
    assert {stem: body for stem, body in actual.items() if body != cases[stem].expected} == {}
