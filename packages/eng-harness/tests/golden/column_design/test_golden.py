"""Golden cases of the column-workflow calcs (plan 0013 T2; spec 0013 AC4)."""

import pytest

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY

from . import golden_files, load_case

CALC_ID = "harness.column_select"
FILES = {p.stem: p for p in golden_files()}


@pytest.mark.parametrize("stem", sorted(FILES))
def test_case(stem: str) -> None:
    case = load_case(FILES[stem])
    definition = REGISTRY[CALC_ID]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    inp = input_type.model_validate(case.inputs.input)
    meta = InputMeta.model_validate(case.inputs.meta)
    result = definition(inp, meta, TraceBuilder())
    assert result.model_dump(mode="json") == case.expected
