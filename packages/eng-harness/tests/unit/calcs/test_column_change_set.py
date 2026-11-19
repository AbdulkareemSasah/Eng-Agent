"""Items and CW-G3 refusals of harness.column_change_set (spec 0013 AC10, section 4.4.4)."""

from typing import Any

from eng_harness.calc import InputMeta, RefMeta, TraceBuilder
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


def test_items_and_refusals() -> None:
    """AC10: matched accepted frames become frame_section items sorted by id; others are CW-G3 issues."""
    definition = REGISTRY[CALC_ID]
    input_type = definition.input_type
    assert isinstance(input_type, type)
    raw = {
        "matches": [
            _match("C2", "matched", "C60"),
            _match("C1", "matched", "C50"),
            _match("C3", "no_section_in_model"),
            _match("C4", "ambiguous", names=["A", "B"]),
        ],
        "accepted": ["C3", "C2", "C1", "C4"],
    }
    body = definition(input_type.model_validate(raw), _meta(), TraceBuilder()).model_dump(mode="json")
    assert body["source"] == "harness.column_change_set"
    assert body["items"] == [
        {"id": "C1", "kind": "frame_section", "frames": ["C1"], "section": "C50"},
        {"id": "C2", "kind": "frame_section", "frames": ["C2"], "section": "C60"},
    ]
    assert body["issues"] == [
        {"frame_id": "C3", "code": "NOT_IMPLEMENTED", "gap": "CW-G3"},
        {"frame_id": "C4", "code": "NOT_IMPLEMENTED", "gap": "CW-G3"},
    ]
