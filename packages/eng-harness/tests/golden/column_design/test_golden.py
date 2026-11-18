"""Golden cases of the column-workflow calcs (plan 0013 T2; spec 0013 AC4): one test per file of the data folder."""

import pytest

from eng_harness.calc import CalcInput, TraceBuilder
from eng_harness.calcs import REGISTRY

from . import golden_files, input_meta, load_case

CALCS = {
    "column-select": (
        "harness.column_select",
        {
            "scope": "basis.engineer_input/1",
            "frames": "model.frame_placements/1",
            "sections": "model.sections/1",
            "basis": "basis.design_basis/1",
        },
    ),
}
"""Per file prefix: the calc id and the record kind of each referenced input field."""
FILES = golden_files()


def _calc_of(stem: str) -> tuple[str, dict[str, str]]:
    return next(entry for prefix, entry in CALCS.items() if stem.startswith(f"{prefix}-"))


@pytest.mark.parametrize("stem", sorted(FILES))
def test_case(stem: str) -> None:
    case = load_case(FILES[stem])
    calc_id, kinds = _calc_of(stem)
    definition = REGISTRY[calc_id]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    result = definition(input_type.model_validate(case.input), input_meta(case.refs, kinds), TraceBuilder())
    assert result.model_dump(mode="json") == case.expected
