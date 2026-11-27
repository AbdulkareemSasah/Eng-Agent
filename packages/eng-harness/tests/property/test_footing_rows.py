"""Copy selection preserves source rows for every kind (spec 0010 AC35, §4.4.7 K1 and K2)."""

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from eng_harness.calc import CalcInput, InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY

DATA = Path(__file__).resolve().parents[1] / "data" / "kinds" / "footing"


@pytest.mark.parametrize("name", ["dims", "design", "status", "subjects"])
@given(
    requested=st.lists(st.sampled_from("ABCD"), max_size=8),
    base_ids=st.sets(st.sampled_from("ABCD")),
    extra_ids=st.sets(st.sampled_from("ABCD")),
)
@example(requested=["C", "B", "A", "B"], base_ids={"A", "B", "D"}, extra_ids={"B", "C"})
@example(requested=[], base_ids={"A", "B"}, extra_ids={"B", "C"})
def test_copy_preserves_rows(name: str, requested: list[str], base_ids: set[str], extra_ids: set[str]) -> None:
    template: dict[str, Any] = json.loads((DATA / f"{name}.json").read_bytes())
    rows_key = "subjects" if name == "subjects" else "footings"
    base_row = template[rows_key][0]
    # Use distinct rows so selecting the wrong source changes the payload even when the id matches.
    extra_row = base_row | {"source": "engineer"} if name in {"dims", "design"} else template[rows_key][1]
    base = {key: base_row | {"id": key} for key in sorted(base_ids)}
    extra = {key: extra_row | {"id": key} for key in sorted(extra_ids)}
    base_payload = template | {rows_key: list(base.values())}
    extra_payload = template | {rows_key: list(extra.values())}
    if name == "subjects":
        exclusion = template["excluded"][0]
        base_payload["excluded"] = [exclusion | {"joint": "Z-base-exclusion"}, exclusion]
        extra_payload["excluded"] = [exclusion | {"joint": "extra-exclusion"}]

    ids = [key for key in requested if key in base_ids or key in extra_ids]
    definition = REGISTRY[f"harness.footing_rows_{name}"]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    inputs = input_type.model_validate({"base": base_payload, "extra": extra_payload, "ids": ids})
    refs = {
        key: RefMeta(
            result_id=ref,
            ref=ref,
            kind=f"harness.footing_{name}/1",
            complete=True,
            model_id=None,
            model_revision=None,
            parents=(),
            producer_tool="fixture",
        )
        for key, ref in [("base", "res_00000000000000000000000001"), ("extra", "res_00000000000000000000000002")]
    }
    result = definition(inputs, InputMeta(refs=refs), TraceBuilder()).model_dump(mode="json")
    kept = sorted(set(ids))
    assert [row["id"] for row in result[rows_key]] == kept
    assert result[rows_key] == [extra[key] if key in extra else base[key] for key in kept]
    if name == "subjects":
        assert result["excluded"] == base_payload["excluded"]
