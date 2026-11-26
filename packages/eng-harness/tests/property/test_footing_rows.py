"""Copy selection preserves its source rows (spec 0010 AC35, §4.4.7 K1 and K2)."""

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from eng_harness.calc import CalcInput, InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY
from eng_harness.kinds.footing import FootingSubjects

KIND = "harness.footing_subjects/1"
RECORD = FootingSubjects.model_validate_json(
    (Path(__file__).resolve().parents[1] / "data" / "kinds" / "footing" / "subjects.json").read_bytes()
)


@given(data=st.data(), base_ids=st.sets(st.sampled_from("ABCD")), extra_ids=st.sets(st.sampled_from("ABCD")))
def test_copy_preserves_rows(data: st.DataObject, base_ids: set[str], extra_ids: set[str]) -> None:
    available = sorted(base_ids | extra_ids)
    ids = data.draw(st.lists(st.sampled_from(available), max_size=8)) if available else []
    base = {key: RECORD.subjects[0].model_copy(update={"id": key}) for key in sorted(base_ids)}
    extra = {key: RECORD.subjects[1].model_copy(update={"id": key}) for key in sorted(extra_ids)}
    definition = REGISTRY["harness.footing_rows_subjects"]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    inputs = input_type.model_validate(
        {
            "base": RECORD.model_copy(update={"subjects": list(base.values())}),
            "extra": RECORD.model_copy(update={"subjects": list(extra.values())}),
            "ids": ids,
        }
    )
    refs = {
        key: RefMeta(
            result_id=ref,
            ref=ref,
            kind=KIND,
            complete=True,
            model_id=None,
            model_revision=None,
            parents=(),
            producer_tool="fixture",
        )
        for key, ref in [("base", "res_00000000000000000000000001"), ("extra", "res_00000000000000000000000002")]
    }
    result = definition(inputs, InputMeta(refs=refs), TraceBuilder()).model_dump(mode="json")
    assert [row["id"] for row in result["subjects"]] == sorted(set(ids))
    for row in result["subjects"]:
        key = row["id"]
        expected = extra[key] if key in extra else base[key]
        assert row == expected.model_dump(mode="json")
