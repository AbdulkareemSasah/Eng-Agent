"""Text, date and number formatting (plan 0006 T1; spec 0006 section 4.7, AC21, AC58)."""

import pytest

from eng_harness._text import (
    format_duration_ms,
    format_number,
    format_timestamp,
    sanitize_html,
    sanitize_terminal,
    truncate,
)


@pytest.mark.parametrize(
    ("ms", "expected"),
    [
        (0, "0 ms"),
        (850, "850 ms"),
        (1000, "1 s"),
        (12_345, "12 s"),
        (125_000, "2 min 05 s"),
        (3_723_999, "1 h 02 min 03 s"),
        (7_200_000, "2 h 00 min 00 s"),
    ],
)
def test_format_duration_ms(ms: int, expected: str) -> None:
    assert format_duration_ms(ms) == expected


def test_format_duration_rejects_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        format_duration_ms(-1)


def test_format_timestamp_slices_contract_timestamp() -> None:
    assert format_timestamp("2026-03-04T05:06:07.089Z") == "2026-03-04 05:06:07 UTC"


@pytest.mark.parametrize("bad", ["2026-03-04", "2026-03-04T05:06:07Z", "", "٢٠٢٦-٠٣-٠٤T٠٥:٠٦:٠٧.٠٨٩Z"])
def test_format_timestamp_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError, match="timestamp"):
        format_timestamp(bad)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0, "0"), (1.5, "1.5"), (1234567.0, "1.23457e+06"), (0.000123456789, "0.000123457"), (-2.25, "-2.25")],
)
def test_format_number_point_and_ascii(value: float, expected: str) -> None:
    assert format_number(value) == expected


def test_format_number_explicit_significant_digits() -> None:
    assert format_number(3.14159265, significant=3) == "3.14"


def test_format_number_rejects_bad_significant() -> None:
    with pytest.raises(ValueError, match="significant"):
        format_number(1.0, significant=0)


def test_sanitize_terminal_marks_controls() -> None:
    assert sanitize_terminal("a\x1b[31mb\x07\n") == "a<U+001B>[31mb<U+0007><U+000A>"
    assert sanitize_terminal("x\x85y\x7fz") == "x<U+0085>y<U+007F>z"
    assert sanitize_terminal("a‮b⁦c") == "a<U+202E>b<U+2066>c"


def test_sanitize_terminal_keeps_arabic_text() -> None:
    assert sanitize_terminal("عمود C1") == "عمود C1"


def test_sanitize_html_keeps_tab_and_newline_only() -> None:
    assert sanitize_html("a\tb\nc\x00d\x1be‮f") == "a\tb\nc<U+0000>d<U+001B>e<U+202E>f"


def test_truncate() -> None:
    assert truncate("abcdef", 6) == "abcdef"
    assert truncate("abcdefg", 6) == "abc..."
    assert len(truncate("x" * 100, 10)) == 10
    with pytest.raises(ValueError, match="limit"):
        truncate("abc", 2)
