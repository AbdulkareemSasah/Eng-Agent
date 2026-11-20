"""Arabic workspace path, cp1256 console and culture-invariant formatting (plan 0006 T17; AC58)."""

from __future__ import annotations

import io
import sys
from contextlib import suppress
from pathlib import Path

import pytest

from eng_harness._text import format_duration_ms, format_number, format_timestamp
from eng_harness.cli._encoding import configure_streams


@pytest.mark.windows
def test_arabic_workspace_and_cp1256(tmp_path: Path) -> None:
    """Dates and numbers stay Gregorian/ASCII under an Arabic path and a cp1256 stream (AC58)."""
    arabic = tmp_path / "مساحة_عمل" / "تشغيل"
    arabic.mkdir(parents=True)
    note = arabic / "ملاحظة.txt"
    note.write_text("مرحبا", encoding="utf-8")
    assert note.read_text(encoding="utf-8") == "مرحبا"
    assert "مساحة_عمل" in note.as_posix()

    stamp = format_timestamp("2026-01-01T00:00:00.000Z")
    assert stamp == "2026-01-01 00:00:00 UTC"
    assert all(ch in "0123456789 -:UTC" for ch in stamp)
    assert format_number(12.5, significant=3) == "12.5"
    assert format_duration_ms(65_000) == "01:05"

    raw = io.BytesIO()
    pipe = io.TextIOWrapper(raw, encoding="cp1256", errors="strict", newline="")
    configure_streams(pipe)
    pipe.write("مرحبا ☃\n")
    pipe.flush()
    assert raw.getvalue() == "مرحبا ☃\n".encode()  # redirected: UTF-8 (AC5 / AC58)

    console_raw = io.BytesIO()

    class _Console(io.TextIOWrapper):
        def isatty(self) -> bool:
            return True

    console = _Console(console_raw, encoding="cp1256", errors="strict", newline="")
    configure_streams(console)
    console.write("م ☃")
    console.flush()
    assert console.encoding == "cp1256"
    assert console_raw.getvalue() == "م".encode("cp1256") + b" \\u2603"

    if sys.platform == "win32":
        import locale

        before = locale.getlocale()
        try:
            with suppress(locale.Error):
                locale.setlocale(locale.LC_ALL, "ar-SA")
            with suppress(locale.Error):
                locale.setlocale(locale.LC_ALL, "ar_SA.UTF-8")
            assert format_timestamp("2026-06-15T12:30:45.000Z") == "2026-06-15 12:30:45 UTC"
            assert format_number(1234.5, significant=6) == "1234.5"
            assert format_duration_ms(3_600_000) == "1:00:00"
        finally:
            with suppress(locale.Error):
                if before[0]:
                    locale.setlocale(locale.LC_ALL, before)
