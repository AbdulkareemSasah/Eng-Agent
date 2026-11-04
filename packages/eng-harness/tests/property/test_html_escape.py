"""Text and untrusted fields leave the HTML builder only as escaped text nodes (spec 0006 AC48, AC49)."""

import re
from html.parser import HTMLParser

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness._html import HtmlError, SafeToken, Tag, Text, el, field, trusted
from eng_harness._text import sanitize_html, truncate

_ALPHABET = list("<>&\"'/=`;:() \t\n\r\x00\x1b") + ["‮", "⁦", "‏", "م", "ر", "٣", "a", "1"]
_ANY_TEXT = st.one_of(st.text(max_size=60), st.text(alphabet=st.sampled_from(_ALPHABET), max_size=60))


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str | None]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attrs.extend(attrs)

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def _parse(markup: str) -> _Collector:
    collector = _Collector()
    collector.feed(markup)
    collector.close()
    return collector


@settings(derandomize=True, max_examples=300)
@given(_ANY_TEXT)
def test_text_parses_back_to_the_sanitized_input(text: str) -> None:
    parsed = _parse(Text(text).render())
    assert parsed.tags == []
    assert "".join(parsed.text) == sanitize_html(text)


@settings(derandomize=True, max_examples=300)
@given(_ANY_TEXT, st.integers(min_value=3, max_value=40))
def test_field_has_only_allowlisted_markup(value: str, limit: int) -> None:
    rendered = field(trusted("Label"), value, max_chars=limit).render()
    parsed = _parse(rendered)
    assert set(parsed.tags) <= {"span", "bdi"}
    assert parsed.tags.count("bdi") == 1
    assert {name for name, _ in parsed.attrs} <= {"class", "dir"}
    shown = sanitize_html(truncate(value, limit))
    expected = ["Label", " ", shown]
    if len(value) > limit:
        expected += [" ", f"({len(value)} characters)"]
    assert "".join(parsed.text) == "".join(expected)
    assert "<" not in re.sub(r"</?(span|bdi)\b[^<>]*>", "", rendered)


@settings(derandomize=True, max_examples=300)
@given(st.one_of(st.text(max_size=80), st.text(alphabet=st.sampled_from(list("ab.-_ \n\"<é٣")), max_size=80)))
def test_a_token_is_accepted_only_when_it_matches_the_rule(text: str) -> None:
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", text, re.ASCII):
        assert el(Tag.DIV, class_=SafeToken(text)).render() == f'<div class="{text}"></div>'
        return
    try:
        SafeToken(text)
    except HtmlError:
        return
    raise AssertionError("a string outside the token rule was accepted")
