"""HTML builder: escaping by construction, safe tokens, labeled untrusted fields, style hash.

Plan 0006 T2; spec 0006 section 4.5, AC48 (the escaped, labeled form) and AC49 (attributes accept only tokens).
"""

import base64
import hashlib
import re
from enum import StrEnum
from typing import Any

import pytest

from eng_harness._html import (
    Href,
    HtmlError,
    Node,
    SafeToken,
    Tag,
    Text,
    Trusted,
    document,
    el,
    field,
    href,
    stylesheet,
    trusted,
)
from eng_harness.pages._css import STYLESHEET


class _Kind(StrEnum):
    PRIMARY = "primary"
    DANGER = "danger"


class _BadKind(StrEnum):
    BROKEN = 'a"onclick="x'


def test_attributes_accept_only_tokens() -> None:
    node = el(Tag.DIV, Text("x"), class_=SafeToken("panel-1"), id=SafeToken("run_42.a"))
    assert node.render() == '<div class="panel-1" id="run_42.a">x</div>'
    assert el(Tag.SPAN, class_=SafeToken("a" * 64)).render() == f'<span class="{"a" * 64}"></span>'
    assert el(Tag.BUTTON, class_=_Kind.DANGER).render() == '<button class="danger"></button>'
    for bad in ("a b", "a" * 65, "", 'x"y', "x'y", "<b>", "javascript:alert(1)", "a\n", "é", "٣", "a/b", "a=b"):
        with pytest.raises(HtmlError):
            SafeToken(bad)
        smuggled: Any = bad
        with pytest.raises(HtmlError):
            el(Tag.DIV, class_=smuggled)
        with pytest.raises(HtmlError):
            el(Tag.DIV, id=smuggled)


def test_plain_strings_are_not_attribute_values() -> None:
    plain: Any = "panel"
    for name in ("class_", "id", "name", "type", "value"):
        with pytest.raises(HtmlError):
            el(Tag.DIV, **{name: plain})
    with pytest.raises(HtmlError):
        el(Tag.DIV, class_=_BadKind.BROKEN)


def test_attribute_names_are_allowlisted() -> None:
    for name in ("style", "onclick", "onerror", "srcdoc", "src", "formaction", "x-y", 'a"b'):
        with pytest.raises(HtmlError):
            el(Tag.DIV, **{name: SafeToken("x")})


def test_urls_are_built_from_validated_segments_only() -> None:
    link = href(SafeToken("answer"), SafeToken("req-1"))
    assert isinstance(link, Href)
    assert el(Tag.A, Text("go"), href=link).render() == '<a href="/answer/req-1">go</a>'
    assert (
        el(Tag.FORM, action=href(SafeToken("setup"), SafeToken("s.1"))).render() == '<form action="/setup/s.1"></form>'
    )
    assert href().value == "/"
    smuggled: Any = "/answer/x"
    bad_urls: tuple[Any, ...] = (smuggled, SafeToken("answer"), "javascript:alert(1)")
    for bad in bad_urls:
        with pytest.raises(HtmlError):
            el(Tag.A, href=bad)
    with pytest.raises(HtmlError):
        el(Tag.DIV, class_=link)
    for dots in (".", ".."):
        with pytest.raises(HtmlError):
            href(SafeToken("answer"), SafeToken(dots))
    with pytest.raises(HtmlError):
        href(smuggled)


def test_href_is_minted_only_by_the_factory() -> None:
    for forged in ('" onclick="x', "javascript:alert(1)", "/answer/x"):
        with pytest.raises(HtmlError):
            Href(forged)


def test_foreign_node_subclasses_are_refused() -> None:
    class Raw(Node):
        def render(self) -> str:
            return "<script>x</script>"

    class LoudText(Text):
        def render(self) -> str:
            return "<script>y</script>"

    for foreign in (Raw(), LoudText("a")):
        with pytest.raises(HtmlError):
            el(Tag.DIV, foreign)
        with pytest.raises(HtmlError):
            document(foreign, [], stylesheet("p{}"))


def test_elements_accept_only_tags_and_nodes() -> None:
    tag: Any = "script"
    with pytest.raises(HtmlError):
        el(tag)
    child: Any = "<b>raw</b>"
    with pytest.raises(HtmlError):
        el(Tag.DIV, child)
    with pytest.raises(HtmlError):
        el(Tag.BR, Text("x"))
    assert el(Tag.BR).render() == "<br>"
    hidden = el(Tag.INPUT, type=SafeToken("hidden"), name=SafeToken("csrf"), value=SafeToken("abc_-123"))
    assert hidden.render() == '<input type="hidden" name="csrf" value="abc_-123">'


def test_no_active_or_external_tags_exist() -> None:
    names = {tag.value for tag in Tag}
    assert names.isdisjoint({"script", "iframe", "object", "embed", "img", "link", "base", "svg", "video", "audio"})


def test_text_is_escaped_and_sanitized() -> None:
    assert Text("<script>alert(\"x\")</script> & 'q'").render() == (
        "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; &#x27;q&#x27;"
    )
    assert Text("a\x00b\x1b[31m").render() == "a&lt;U+0000&gt;b&lt;U+001B&gt;[31m"
    assert Text("x\u202ey").render() == "x&lt;U+202E&gt;y"
    assert Text("tab\there\nline").render() == "tab\there\nline"
    assert Text("مرحبا 123").render() == "مرحبا 123"


def test_trusted_is_minted_only_by_the_factory() -> None:
    assert trusted("Approve & continue").render() == "Approve & continue"
    not_a_string: Any = 5
    with pytest.raises(HtmlError):
        trusted(not_a_string)
    with pytest.raises(HtmlError):
        Trusted("<script>")


def test_field_labels_and_wraps_untrusted_value() -> None:
    node = field(trusted("Drawing"), '<img src=x onerror="y">')
    assert node.render() == (
        '<span class="field"><span class="label">Drawing</span> '
        '<bdi dir="auto">&lt;img src=x onerror=&quot;y&quot;&gt;</bdi></span>'
    )
    mixed = field(trusted("Name"), "عمود C12 \u0663\u0660\u00d7\u0664\u0660")
    assert '<bdi dir="auto">عمود C12 \u0663\u0660\u00d7\u0664\u0660</bdi>' in mixed.render()
    assert "&lt;U+202E&gt;" in field(trusted("Name"), "a\u202eb").render()
    assert "&lt;U+0000&gt;" in field(trusted("Name"), "a\x00b").render()


def test_field_label_must_be_trusted() -> None:
    for label in ("Drawing", Text("Drawing"), 5):
        bad: Any = label
        with pytest.raises(HtmlError):
            field(bad, "x")
    value: Any = Text("x")
    with pytest.raises(HtmlError):
        field(trusted("Drawing"), value)


def test_field_truncates_and_states_original_length() -> None:
    node = field(trusted("Note"), "x" * 600)
    assert node.render() == (
        '<span class="field"><span class="label">Note</span> '
        f'<bdi dir="auto">{"x" * 497}...</bdi> <span class="note">(600 characters)</span></span>'
    )
    assert "characters" not in field(trusted("Note"), "x" * 500).render()
    assert "(10 characters)" in field(trusted("Note"), "y" * 10, max_chars=5).render()
    with pytest.raises(HtmlError):
        field(trusted("Note"), "x", max_chars=2)


def test_field_handles_ten_megabyte_value() -> None:
    rendered = field(trusted("Note"), "<" * 10_000_000).render()
    assert "(10000000 characters)" in rendered
    assert len(rendered) < 10_000


def test_stylesheet_hash_is_the_policy_source() -> None:
    css = "body{margin:0}"
    sheet = stylesheet(css)
    digest = base64.b64encode(hashlib.sha256(css.encode("utf-8")).digest()).decode("ascii")
    assert sheet.csp_source == f"'sha256-{digest}'"
    assert sheet.render() == f"<style>{css}</style>"
    for bad in ("a</style><script>", "a<b", "a</"):
        runtime_built: Any = bad
        with pytest.raises(HtmlError):
            stylesheet(runtime_built)


def test_document_embeds_one_style_and_matching_policy() -> None:
    page = document(Text("Run <1>"), [el(Tag.P, Text("hello"))], STYLESHEET)
    assert page.startswith("<!doctype html>")
    assert '<html lang="en" dir="ltr">' in page
    assert "<title>Run &lt;1&gt;</title>" in page
    assert page.count("<style>") == 1
    assert page.count("</style>") == 1
    assert "<script" not in page.lower()
    policy = f"default-src 'none'; style-src {STYLESHEET.csp_source}"
    assert f'<meta http-equiv="Content-Security-Policy" content="{policy}">' in page
    assert "<p>hello</p>" in page


def test_shared_stylesheet_loads_nothing_external() -> None:
    assert re.fullmatch(r"'sha256-[A-Za-z0-9+/]{43}='", STYLESHEET.csp_source)
    css = STYLESHEET.render().removeprefix("<style>").removesuffix("</style>").lower()
    assert css
    for forbidden in ("url(", "@import", "expression(", "javascript:", "<"):
        assert forbidden not in css
