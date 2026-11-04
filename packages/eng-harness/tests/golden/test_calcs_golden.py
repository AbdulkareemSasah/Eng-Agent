"""Golden cases of the calcs (plan 0003 T6; spec 0003 section 3): one test per file under data/golden/calcs."""

import pytest

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY

from ._golden import golden_files, load_case

PREFIXES = {
    "fingerprint": "harness.model_fingerprint",
    "diff": "harness.model_diff",
    "readback": "harness.readback_check",
    "summary": "harness.design_summary",
    "round": "harness.section_round",
    "placement": "harness.placement_compare",
}
FILES = {p.stem: p for p in golden_files()}


@pytest.mark.parametrize("stem", sorted(FILES))
def test_case(stem: str) -> None:
    case = load_case(FILES[stem])
    definition = REGISTRY[PREFIXES[stem.split("-", 1)[0]]]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    inp = input_type.model_validate(case.inputs["input"])
    meta = InputMeta.model_validate(case.inputs["meta"])
    result = definition(inp, meta, TraceBuilder())
    assert result.model_dump(mode="json") == case.expected
