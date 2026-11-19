"""In-scope subjects always reach the SBC gap for valid base inputs (spec 0003 AC5)."""

from math import ceil, floor
from typing import Any, cast

import pytest
from aci318_14 import PACK
from eng_contract.params import ParamSpec
from eng_contract.verdicts import Subject, VerdictStatus
from hypothesis import given, settings
from hypothesis import strategies as st
from structural_codes import evaluate
from structural_codes.check import Check
from structural_codes.inputs import CheckInputs
from structural_codes.overlay import Overridden
from structural_codes.pack import Pack, Registry

from sbc304_2018._overlay import build_overlay
from sbc304_2018.clause_map import CLAUSE_MAP


def _parameters(model: type[CheckInputs]) -> st.SearchStrategy[dict[str, Any]]:
    """Generate literals using the installed ACI models' cited physical bounds and declared categories."""
    fields: dict[str, st.SearchStrategy[Any]] = {}
    for name, info in model.model_fields.items():
        kind = info.annotation
        spec = info.json_schema_extra
        if isinstance(spec, ParamSpec):
            low = spec.ge if spec.gt is None else spec.gt
            high = spec.le if spec.lt is None else spec.lt
            if kind is int:
                minimum = floor(spec.gt) + 1 if spec.gt is not None else None if low is None else ceil(low)
                maximum = ceil(spec.lt) - 1 if spec.lt is not None else None if high is None else floor(high)
                fields[name] = st.integers(minimum, maximum)
                continue
            numbers = st.floats(
                min_value=low,
                max_value=high,
                exclude_min=spec.gt is not None,
                exclude_max=spec.lt is not None,
                allow_nan=False,
                allow_infinity=False,
            )
            if kind is float:
                fields[name] = numbers
                continue
            if kind == float | None:
                fields[name] = st.none() | numbers
                continue
        fields[name] = st.from_type(cast(type[Any], kind))
    return st.fixed_dictionaries(fields)


@pytest.mark.parametrize("base", PACK.checks, ids=lambda check: check.meta.check_id)
@settings(derandomize=True, deadline=None, max_examples=16)
@given(data=st.data())
def test_never_pass_or_fail(base: Check, data: st.DataObject) -> None:
    row = next(row for row in CLAUSE_MAP if row.base_check_id == base.meta.check_id)
    base_pack = Pack(PACK.name, PACK.code, PACK.edition, PACK.version, (base,), PACK.approvals)
    checks, overlay = build_overlay((row,), base_pack)
    (entry,) = overlay.entries
    assert isinstance(entry, Overridden)
    pack = Pack("sbc304_2018", "SBC 304-2018", "2018", "0.1.0.dev0", checks, "approvals.yaml", PACK.name, overlay)
    registry = Registry.of((base_pack, pack))
    assert issubclass(base.inputs, CheckInputs)
    inputs = data.draw(_parameters(base.inputs))
    subject = Subject(kind=min(base.meta.members), id="generated")
    result = evaluate(entry.check.meta.check_id, inputs, subject=subject, registry=registry)
    assert [verdict.status for verdict in result.payload.verdicts] == [VerdictStatus.NEEDS_ENGINEER]
