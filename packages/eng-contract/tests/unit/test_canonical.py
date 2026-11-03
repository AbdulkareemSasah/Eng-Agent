"""Canonical JSON and payload hash (plan T3; spec 4.3.1; AC1 to AC3).

Expected strings are written out here or come from RFC 8785 (data file), independently of the implementation.
"""

import hashlib
import struct
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from eng_contract.canonical import CanonicalJsonError, canonical_json, loads, payload_sha256
from eng_contract.errors import ContractError, ErrorCode

_DATA = Path(__file__).resolve().parent.parent / "data" / "jcs" / "numbers.csv"


def _samples() -> list[tuple[str, str]]:
    rows = [line.split(",") for line in _DATA.read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    return [(hex_bits, text) for hex_bits, text in rows]


@pytest.mark.parametrize(("hex_bits", "expected"), _samples())
def test_rfc8785_number_samples(hex_bits: str, expected: str) -> None:
    (value,) = struct.unpack(">d", bytes.fromhex(hex_bits))
    if expected == "ERROR":
        with pytest.raises(CanonicalJsonError):
            canonical_json(value)
    else:
        assert canonical_json(value) == expected.encode("ascii")


def test_rfc8785_samples_cover_appendix_b() -> None:
    assert len(_samples()) == 26


def test_number_layout_boundaries() -> None:
    # ECMAScript Number toString layout (RFC 8785 3.2.2.3), boundaries written by hand.
    assert canonical_json(1.0) == b"1"
    assert canonical_json(-0.0) == b"0"
    assert canonical_json(0.5) == b"0.5"
    assert canonical_json(1e-6) == b"0.000001"
    assert canonical_json(1e-7) == b"1e-7"
    assert canonical_json(1.5e-7) == b"1.5e-7"
    assert canonical_json(123456.789) == b"123456.789"
    assert canonical_json(1.5e300) == b"1.5e+300"
    assert canonical_json(1e21) == b"1e+21"
    assert canonical_json(1e20) == b"100000000000000000000"
    assert canonical_json(2**53 - 1) == b"9007199254740991"
    assert canonical_json(-(2**53 - 1)) == b"-9007199254740991"
    assert canonical_json(0) == b"0"


def test_key_order_and_escaping() -> None:
    value = {"b": 1, "a": 2, "é": 3, "\U0001f600": 4, "דּ": 5}
    # UTF-16 code unit order: a, b, e-acute (U+00E9), the emoji (D83D DE00), then U+FB33.
    expected = '{"a":2,"b":1,"é":3,"\U0001f600":4,"דּ":5}'.encode()
    assert canonical_json(value) == expected
    text = '\x00\x08\t\n\x0c\r\x1f\x7f  "\\/'
    assert canonical_json(text) == b'"\\u0000\\b\\t\\n\\f\\r\\u001f\x7f\xe2\x80\xa8\xe2\x80\xa9\\"\\\\/"'
    assert canonical_json("é") == '"é"'.encode()  # no normalization
    assert canonical_json([True, False, None, [], {}, {"k": [1, {"z": None}]}]) == (
        b'[true,false,null,[],{},{"k":[1,{"z":null}]}]'
    )
    assert canonical_json(True) == b"true"
    assert not canonical_json({"a": 1}).startswith(b"\xef\xbb\xbf")


def test_rejects_non_json_values() -> None:
    bad: list[object] = [
        float("nan"),
        float("inf"),
        float("-inf"),
        2**53,
        -(2**53),
        10**16,
        "\ud800",
        {"\udc00": 1},
        {1: "a"},
        {None: "a"},
        Decimal("1.5"),
        Fraction(1, 3),
        b"bytes",
        datetime(2026, 1, 1),  # noqa: DTZ001
        (1, 2),
        {1, 2},
        object(),
        [1, [2, {"a": float("nan")}]],
    ]
    for value in bad:
        with pytest.raises(CanonicalJsonError) as info:
            canonical_json(value)
        assert info.value.detail.code is ErrorCode.INVALID_ARGUMENT
        assert info.value.detail.retryable is False
        assert isinstance(info.value, ContractError)
    deep: object = []
    for _ in range(5000):
        deep = [deep]
    with pytest.raises(CanonicalJsonError):
        canonical_json(deep)


def test_large_integral_floats() -> None:
    expected = {
        2.0**53: b"9007199254740992",
        1e16: b"10000000000000000",
        1e20: b"100000000000000000000",
        1e21: b"1e+21",
        2.0**60: b"1152921504606847000",
        2.0**68: b"295147905179352830000",
    }
    for value, text in expected.items():
        assert canonical_json(value) == text
        back = loads(text)
        assert isinstance(back, float)
        assert back == value
        assert canonical_json(back) == text
    assert loads(b"-9007199254740992") == -(2.0**53)
    # the exact integer value of a float above 2**53 is accepted as that float
    assert loads(b"1152921504606846976") == 2.0**60


def test_loads_values_and_integer_rule() -> None:
    assert loads(b'{"a":[1,2.5,"x",true,null]}') == {"a": [1, 2.5, "x", True, None]}
    value = loads(b"9007199254740991")
    assert value == 2**53 - 1
    assert isinstance(value, int)
    assert isinstance(loads(b"-9007199254740991"), int)
    assert isinstance(loads(b"5"), int)
    assert loads(b"1e2") == 100.0
    assert loads(b"1e21") == 1e21


@pytest.mark.parametrize(
    "text",
    [
        b"NaN",
        b"Infinity",
        b"-Infinity",
        b'{"a":1,"a":2}',
        b'{"a":{"b":1,"b":1}}',
        b"1e400",
        b"-1e400",
        b"9007199254740993",
        b"-9007199254740993",
        b"1" + b"0" * 400,
        b"1" + b"0" * 5000,
        b"",
        b"{",
        b"\xff",
        b"\xef\xbb\xbf1",
        b"[" * 5000,
    ],
)
def test_loads_rejects(text: bytes) -> None:
    with pytest.raises(CanonicalJsonError) as info:
        loads(text)
    assert info.value.detail.code is ErrorCode.INVALID_ARGUMENT


def test_payload_sha256() -> None:
    payload = {"b": [1, 2.0], "a": "x"}
    text = b'{"a":"x","b":[1,2]}'
    assert canonical_json(payload) == text
    assert payload_sha256(payload) == hashlib.sha256(text).hexdigest()
    assert payload_sha256({"a": "x", "b": [1, 2]}) == payload_sha256(payload)
    assert payload_sha256(None) == hashlib.sha256(b"null").hexdigest()
    with pytest.raises(CanonicalJsonError):
        payload_sha256(float("nan"))
