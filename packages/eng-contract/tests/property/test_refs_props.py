"""Property tests of JSON Pointer round trip and evaluation (plan T8; spec 4.6.1; AC29)."""

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from eng_contract.refs import JsonPointer, parse_ref

_RID = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
# Tokens rich in the two escaped characters, plus arbitrary text (any Unicode, including empty).
_TOKENS = st.one_of(st.text(alphabet="~/01a", max_size=8), st.text(max_size=8))
_JSON = st.recursive(
    st.one_of(st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.text()),
    lambda children: st.one_of(st.lists(children, max_size=4), st.dictionaries(_TOKENS, children, max_size=4)),
    max_leaves=20,
)


@st.composite
def _document_and_path(draw: st.DrawFn) -> tuple[Any, tuple[str, ...], Any]:
    """A document, a path of tokens that exists in it, and the value reached by direct indexing."""
    document = draw(_JSON)
    node, tokens = document, []
    while isinstance(node, dict | list) and node and draw(st.booleans()):
        if isinstance(node, dict):
            key = draw(st.sampled_from(sorted(node)))
            tokens.append(key)
            node = node[key]
        else:
            index = draw(st.integers(0, len(node) - 1))
            tokens.append(str(index))
            node = node[index]
    return document, tuple(tokens), node


@settings(derandomize=True, max_examples=300, deadline=None)
@given(_document_and_path())
def test_pointer_round_trip(case: tuple[Any, tuple[str, ...], Any]) -> None:
    document, tokens, expected = case
    text = JsonPointer.format(tokens)
    assert JsonPointer.parse(text) == tokens
    assert JsonPointer.evaluate(document, JsonPointer.parse(text)) == expected
    assert parse_ref(f"{_RID}#{text}") == (_RID, tokens)


@settings(derandomize=True, max_examples=300, deadline=None)
@given(st.lists(_TOKENS, max_size=6))
def test_escaping_then_parsing_returns_the_tokens(tokens: list[str]) -> None:
    text = JsonPointer.format(tuple(tokens))
    assert JsonPointer.parse(text) == tuple(tokens)
    # Every "~" in the escaped text starts a "~0" or "~1" escape, and every "/" starts a token.
    assert "~" not in text.replace("~0", "").replace("~1", "")
    assert text.count("/") == len(tokens)
