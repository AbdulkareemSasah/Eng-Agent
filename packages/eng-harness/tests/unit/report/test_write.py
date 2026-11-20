"""Atomic UTF-8 report write (spec 0006 AC59)."""

from pathlib import Path

from eng_contract.ids import FixedClock

from eng_harness.report import write_report

_ARABIC = "الهندسة ١٢٣"


def test_utf8_lf_atomic(tmp_path: Path, clock: FixedClock) -> None:
    """AC59: UTF-8 without BOM, LF endings, charset meta, rename write, Arabic round-trip."""
    target = tmp_path / "report" / "report.html"
    html = (
        '<!doctype html><html lang="ar" dir="ltr"><head><meta charset="utf-8">'
        f"</head><body><p>{_ARABIC}</p></body></html>"
    )
    write_report(html, target)
    raw = target.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    assert _ARABIC.encode("utf-8") in raw
    assert target.read_text(encoding="utf-8") == html
    assert not target.with_suffix(".html.tmp").exists()
