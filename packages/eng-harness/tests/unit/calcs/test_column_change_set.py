"""Items and CW-G3 refusals of harness.column_change_set (spec 0013 AC10, section 4.4.4)."""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.calc import CalcInput, InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs import REGISTRY

CALC_ID = "harness.column_change_set"


def _meta() -> InputMeta:
    return InputMeta(
        refs={
            "matches": RefMeta(
                result_id="res_01KCC000000000000000000061",
                kind="harness.column_match/1",
                complete=True,
                model_id=None,
                model_revision=None,
                parents=(),
                producer_tool="fixture_tool",
            )
        }
    )


def _match(frame_id: str, status: str, section: str | None = None, names: list[str] | None = None) -> dict[str, Any]:
    if status == "matched":
        assert section is not None
        return {"frame_id": frame_id, "status": status, "section": section, "names": [section]}
    return {"frame_id": frame_id, "status": status, "section": None, "names": names or []}


def _input_type() -> type[CalcInput]:
    input_type = REGISTRY[CALC_ID].input_type
    assert isinstance(input_type, type)
    assert issubclass(input_type, CalcInput)
    return input_type


def _run(matches: list[dict[str, Any]], accepted: list[str]) -> dict[str, Any]:
    raw = {"matches": matches, "accepted": accepted}
    return REGISTRY[CALC_ID](_input_type().model_validate(raw), _meta(), TraceBuilder()).model_dump(mode="json")


def test_items_and_refusals() -> None:
    """AC10: matched accepted frames become frame_section items sorted by id; others are CW-G3 issues."""
    body = _run(
        [
            _match("C2", "matched", "C60"),
            _match("C1", "matched", "C50"),
            _match("C3", "no_section_in_model"),
            _match("C4", "ambiguous", names=["A", "B"]),
        ],
        ["C3", "C2", "C1", "C4"],
    )
    assert body["source"] == "harness.column_change_set"
    assert body["items"] == [
        {"id": "C1", "kind": "frame_section", "frames": ["C1"], "section": "C50"},
        {"id": "C2", "kind": "frame_section", "frames": ["C2"], "section": "C60"},
    ]
    assert body["issues"] == [
        {"frame_id": "C3", "code": "NOT_IMPLEMENTED", "gap": "CW-G3"},
        {"frame_id": "C4", "code": "NOT_IMPLEMENTED", "gap": "CW-G3"},
    ]


def test_accepted_without_match_entry_is_cw_g3() -> None:
    body = _run([_match("C1", "matched", "C50")], ["C1", "C9"])
    assert body["items"] == [{"id": "C1", "kind": "frame_section", "frames": ["C1"], "section": "C50"}]
    assert body["issues"] == [{"frame_id": "C9", "code": "NOT_IMPLEMENTED", "gap": "CW-G3"}]


def test_repeated_accepted_ids_count_once() -> None:
    body = _run([_match("C1", "matched", "C50")], ["C1", "C1"])
    assert len(body["items"]) == 1
    assert body["issues"] == []


def test_duplicate_match_frame_is_refused() -> None:
    raw = {
        "matches": [_match("C1", "matched", "C50"), _match("C1", "matched", "C60")],
        "accepted": ["C1"],
    }
    with pytest.raises(ContractError) as caught:
        REGISTRY[CALC_ID](_input_type().model_validate(raw), _meta(), TraceBuilder())
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, "matches")
