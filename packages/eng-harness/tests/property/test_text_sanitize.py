"""Sanitized terminal text holds no control sequence (spec 0006 AC21)."""

import unicodedata

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness._text import sanitize_html, sanitize_terminal

_BIDI = set("؜‎‏‪‫‬‭‮⁦⁧⁨⁩")


def _has_control(text: str) -> bool:
    return any(unicodedata.category(c) in {"Cc", "Zl", "Zp"} or c in _BIDI for c in text)


@settings(derandomize=True, max_examples=300)
@given(st.text())
def test_no_control_sequences(text: str) -> None:
    assert not _has_control(sanitize_terminal(text))


@settings(derandomize=True, max_examples=300)
@given(st.text())
def test_html_has_no_controls_but_tab_and_newline(text: str) -> None:
    cleaned = sanitize_html(text).replace("\t", "").replace("\n", "")
    assert not _has_control(cleaned)


@settings(derandomize=True, max_examples=200)
@given(st.text(alphabet=st.characters(blacklist_categories=("Cc", "Zl", "Zp")).filter(lambda c: c not in _BIDI)))
def test_clean_text_unchanged(text: str) -> None:
    assert sanitize_terminal(text) == text
