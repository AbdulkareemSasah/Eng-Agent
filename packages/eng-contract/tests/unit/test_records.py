"""Result records (plan T7; spec 4.4; AC12)."""

from typing import Any

import pytest
from pydantic import ValidationError

from eng_contract.records import PAYLOAD_SPLIT_BYTES, ResultRecord

RID = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
RID2 = "res_01ARZ3NDEKTSV4RRFFQ69G5FAW"
TS = "2026-01-02T03:04:05.678Z"
FILE = RID + ".payload.json.gz"


def rec(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "contract": "eng-contract/1",
        "result_id": RID,
        "kind": "model.info/1",
        "created_at": TS,
        "units": "canonical/1",
        "complete": True,
        "producer": {
            "tool": "harness",
            "tool_version": "1",
            "inputs": {},
            "started_at": TS,
            "duration_ms": 0,
        },
        "parents": [],
        "payload_sha256": "b" * 64,
        "payload": {"a": 1},
        "payload_file": None,
    }
    return base | over


def test_payload_location_exclusive() -> None:
    ResultRecord.model_validate(rec())
    ResultRecord.model_validate(rec(payload=None, payload_file=FILE))
    with pytest.raises(ValidationError):
        ResultRecord.model_validate(rec(payload_file=FILE))
    with pytest.raises(ValidationError):
        ResultRecord.model_validate(rec(payload=None, payload_file=None))


@pytest.mark.parametrize("name", [RID2 + ".payload.json.gz", "../" + FILE, "x.json"])
def test_payload_file_name_is_fixed(name: str) -> None:
    with pytest.raises(ValidationError):
        ResultRecord.model_validate(rec(payload=None, payload_file=name))


def test_empty_payload_object_is_a_payload() -> None:
    assert ResultRecord.model_validate(rec(payload={})).payload == {}


def test_parents_unique_ordered() -> None:
    assert ResultRecord.model_validate(rec(parents=[RID2, RID])).parents == [RID2, RID]
    with pytest.raises(ValidationError):
        ResultRecord.model_validate(rec(parents=[RID2, RID2]))
    with pytest.raises(ValidationError):
        ResultRecord.model_validate(rec(parents=["mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV"]))


@pytest.mark.parametrize(
    "over",
    [{"units": "canonical/2"}, {"contract": "x"}, {"payload_sha256": "B" * 64}, {"kind": "bad"}, {"extra": 1}],
)
def test_fixed_fields(over: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ResultRecord.model_validate(rec(**over))


def test_split_threshold() -> None:
    assert PAYLOAD_SPLIT_BYTES == 8 * 1024 * 1024
