"""ULID identifiers, clocks and id sources (plan T4; spec 4.3.2, 4.2.1; AC5, AC6).

Expected ids are recorded in `tests/data/ids/seeded.json`, derived by hand from the ULID text form (ulid/spec) and
the spec's seeded rule, not read back from the implementation.
"""

import json
import re
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from eng_contract.errors import ErrorCode
from eng_contract.ids import (
    FixedClock,
    IdOverflowError,
    ModelId,
    ResultId,
    SeededIdSource,
    SystemClock,
    SystemIdSource,
    Timestamp,
    new_model_id,
    new_result_id,
    ulid_timestamp_ms,
)

_DATA = json.loads((Path(__file__).parent.parent / "data" / "ids" / "seeded.json").read_text(encoding="utf-8"))
_START = _DATA["start_ms"]
_RES = re.compile(r"^res_[0-7][0-9A-HJKMNP-TV-Z]{25}$")


def _three(source: SeededIdSource) -> list[str]:
    return [new_result_id(source) for _ in range(3)]


def test_seeded_ids_are_deterministic() -> None:
    ids = _three(SeededIdSource(b"t", FixedClock(_START, 1)))
    assert ids == _DATA["ids_step_1"]
    assert all(_RES.match(i) for i in ids)
    assert ids == sorted(ids)
    assert _three(SeededIdSource(b"t", FixedClock(_START, 1))) == ids
    assert _three(SeededIdSource(b"u", FixedClock(_START, 1))) != ids


def test_seeded_same_millisecond_increments() -> None:
    ids = _three(SeededIdSource(b"t", FixedClock(_START)))
    assert ids == _DATA["ids_step_0"]


def test_monotonic_within_millisecond() -> None:
    source = SystemIdSource(FixedClock(_START), random_bytes=lambda n: b"\x00" * (n - 1) + b"\x05")
    first, second, third = (source.new_ulid() for _ in range(3))
    assert first < second < third
    assert first[:10] == second[:10] == third[:10]
    assert first[-2:] == "05" and second[-2:] == "06" and third[-2:] == "07"
    # A clock that goes backwards keeps the previous timestamp.
    back = SystemIdSource(FixedClock(_START, -1), random_bytes=lambda n: b"\x00" * n)
    a, b = back.new_ulid(), back.new_ulid()
    assert a < b and a[:10] == b[:10]


def test_new_ms_uses_fresh_random_part() -> None:
    source = SystemIdSource(FixedClock(_START, 1), random_bytes=lambda n: b"\x07" * n)
    a, b = source.new_ulid(), source.new_ulid()
    assert a[10:] == b[10:] and a < b


def test_overflow_raises() -> None:
    source = SystemIdSource(FixedClock(_START), random_bytes=lambda n: b"\xff" * n)
    assert source.new_ulid()[10:] == "Z" * 16
    with pytest.raises(IdOverflowError) as info:
        source.new_ulid()
    assert info.value.detail.code is ErrorCode.LIMIT_EXCEEDED
    assert info.value.detail.retryable is False


def test_ulid_text_form_known_vector() -> None:
    # ulid/spec README example.
    assert ulid_timestamp_ms("01ARZ3NDEKTSV4RRFFQ69G5FAV") == 1469918176385
    assert ulid_timestamp_ms("res_01ARZ3NDEKTSV4RRFFQ69G5FAV") == 1469918176385
    assert ulid_timestamp_ms("mdl_00000000000000000000000000") == 0
    assert ulid_timestamp_ms("7ZZZZZZZZZ0000000000000000") == 2**48 - 1


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "01ARZ3NDEKTSV4RRFFQ69G5FA",
        "01ARZ3NDEKTSV4RRFFQ69G5FAVV",
        "01arz3ndektsv4rrffq69g5fav",
        "01ARZ3NDEKTSV4RRFFQ69G5FAU",
        "81ARZ3NDEKTSV4RRFFQ69G5FAV",
        "xyz_01ARZ3NDEKTSV4RRFFQ69G5FAV",
    ],
)
def test_ulid_timestamp_rejects_malformed(bad: str) -> None:
    from eng_contract.errors import ContractError

    with pytest.raises(ContractError) as info:
        ulid_timestamp_ms(bad)
    assert info.value.detail.code is ErrorCode.INVALID_ARGUMENT


def test_clock_out_of_range_raises() -> None:
    from eng_contract.errors import ContractError

    for bad in (-1, 2**48):
        with pytest.raises(ContractError) as info:
            SystemIdSource(FixedClock(bad)).new_ulid()
        assert info.value.detail.code in (ErrorCode.LIMIT_EXCEEDED, ErrorCode.INVALID_ARGUMENT)


def test_prefixes() -> None:
    source = SeededIdSource(b"t", FixedClock(_START, 1))
    assert new_result_id(source).startswith("res_")
    assert new_model_id(source).startswith("mdl_")


def test_id_types_validate_patterns() -> None:
    good = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    assert TypeAdapter(ResultId).validate_python("res_" + good)
    assert TypeAdapter(ModelId).validate_python("mdl_" + good)
    for adapter, text in (
        (ResultId, "mdl_" + good),
        (ModelId, "res_" + good),
        (ResultId, "res_81ARZ3NDEKTSV4RRFFQ69G5FAV"),
        (ResultId, "res_01ARZ3NDEKTSV4RRFFQ69G5FAI"),
    ):
        with pytest.raises(ValidationError):
            TypeAdapter(adapter).validate_python(text)


def test_fixed_clock_and_timestamps() -> None:
    clock = FixedClock(1_700_000_000_123, 1000)
    assert clock.now_ms() == 1_700_000_000_123
    assert clock.now() == "2023-11-14T22:13:21.123Z"
    assert clock.now_ms() == 1_700_000_002_123
    assert FixedClock(0).now() == "1970-01-01T00:00:00.000Z"
    assert 1_600_000_000_000 < SystemClock().now_ms() < 2**48
    assert TypeAdapter(Timestamp).validate_python(SystemClock().now())


def test_timestamp_validation() -> None:
    adapter = TypeAdapter(Timestamp)
    assert adapter.validate_python("2024-02-29T23:59:59.999Z")
    for bad in (
        "2023-02-29T00:00:00.000Z",
        "2024-13-01T00:00:00.000Z",
        "2024-01-01T00:00:00Z",
        "2024-01-01T00:00:00.000+00:00",
        "2024-01-01 00:00:00.000Z",
        "2024-01-01T24:00:00.000Z",
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python(bad)


def test_ids_round_trip_timestamp() -> None:
    source = SeededIdSource(b"t", FixedClock(_START, 1))
    assert [ulid_timestamp_ms(new_result_id(source)) for _ in range(3)] == [_START, _START + 1, _START + 2]
