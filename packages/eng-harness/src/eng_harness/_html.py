"""HTML builder: escaping by construction (spec 0006 section 4.5, AC48, AC49).

Text enters markup only as `Text` (sanitized, then escaped) or `Trusted` (a literal written in this package).
Untrusted data enters only through `field`, as an escaped, truncated `<bdi dir="auto">` value under a fixed label.
Attributes accept a `SafeToken`, an enumerated value or an `Href` built from tokens: a data string is never placed
in an attribute, a URL, a class name, an id or a style.

Raises:
    HtmlError: every refusal of this module (a value outside the rules above, an unknown tag or attribute).
"""

import base64
import hashlib
import html
import re
from collections.abc import Sequence
from enum import StrEnum
from typing import LiteralString

from eng_harness._text import sanitize_html, truncate

_TOKEN = re.compile(r"[A-Za-z0-9_.-]{1,64}", re.ASCII)
_PATH = re.compile(r"(/[A-Za-z0-9_.-]{1,64})*/?", re.ASCII)
_ATTRS = frozenset(
    {"class", "id", "href", "action", "method", "name", "type", "value", "for", "dir", "colspan", "scope"}
)
_URL_ATTRS = frozenset({"href", "action"})
DEFAULT_MAX_CHARS = 500
_MINT = object()


class HtmlError(ValueError):
    """The builder refused a value, tag or attribute."""


class SafeToken(str):
    """A string of `[A-Za-z0-9_.-]{1,64}`: the only free string an attribute may hold."""

    __slots__ = ()

    def __new__(cls, text: str) -> SafeToken:
        """Validate `text`. Raises: HtmlError if it is not a token."""
        if not isinstance(text, str) or _TOKEN.fullmatch(text) is None:
            raise HtmlError("not a safe token")
        return super().__new__(cls, text)


class Href:
    """A site-relative URL path made only of validated segments (a route constant or a validated id)."""

    __slots__ = ("_value",)

    def __init__(self, value: str, _mint: object = None) -> None:
        if _mint is not _MINT:
            raise HtmlError("Href is created only by href()")
        self._value = value

    @property
    def value(self) -> str:
        """The path (read-only)."""
        return self._value


def href(*segments: SafeToken) -> Href:
    """Join `segments` into `/a/b`. Raises: HtmlError for a non-token segment or `.` and `..`."""
    for segment in segments:
        if not isinstance(segment, SafeToken) or segment in {".", ".."}:
            raise HtmlError("a URL segment must be a SafeToken other than . and ..")
    return Href("/" + "/".join(segments), _MINT)


class Node:
    """Anything an element may hold; renders to markup."""

    __slots__ = ()

    def render(self) -> str:
        """Return the markup of this node."""
        raise NotImplementedError


class Text(Node):
    """Untrusted text: control and bidirectional characters shown as `<U+XXXX>`, then escaped."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise HtmlError("Text holds a string")
        self._value = value

    def render(self) -> str:
        """Return the escaped text (`& < > " '`)."""
        return html.escape(sanitize_html(self._value), quote=True)


class Trusted(Node):
    """A literal written in this package; created only by `trusted`."""

    __slots__ = ("_markup",)

    def __init__(self, markup: str, _mint: object = None) -> None:
        if _mint is not _MINT or not isinstance(markup, str):
            raise HtmlError("Trusted is created only by trusted()")
        self._markup = markup

    def render(self) -> str:
        """Return the literal unchanged."""
        return self._markup


def trusted(text: LiteralString) -> Trusted:
    """Wrap a source-code literal (a `str` built at run time is a type error). Raises: HtmlError if not a str."""
    return Trusted(text, _MINT)


class Tag(StrEnum):
    """The allowlisted tags: no script, frame, object, image, link or base."""

    BODY = "body"
    MAIN = "main"
    SECTION = "section"
    HEADER = "header"
    H1 = "h1"
    H2 = "h2"
    H3 = "h3"
    P = "p"
    DIV = "div"
    SPAN = "span"
    BDI = "bdi"
    STRONG = "strong"
    PRE = "pre"
    CODE = "code"
    TABLE = "table"
    THEAD = "thead"
    TBODY = "tbody"
    TR = "tr"
    TH = "th"
    TD = "td"
    UL = "ul"
    OL = "ol"
    LI = "li"
    DL = "dl"
    DT = "dt"
    DD = "dd"
    A = "a"
    FORM = "form"
    LABEL = "label"
    INPUT = "input"
    BUTTON = "button"
    BR = "br"
    HR = "hr"


_VOID = frozenset({Tag.BR, Tag.HR, Tag.INPUT})
type Attr = SafeToken | StrEnum | Href


def _attr(name: str, value: object) -> str:
    key = name.removesuffix("_")
    if key not in _ATTRS:
        raise HtmlError("attribute not allowed")
    if key in _URL_ATTRS:
        if type(value) is not Href or _PATH.fullmatch(value.value) is None:
            raise HtmlError("a URL attribute takes an Href")
        text = value.value
    elif isinstance(value, SafeToken):
        text = str(value)
    elif isinstance(value, StrEnum) and _TOKEN.fullmatch(value.value) is not None:
        text = value.value
    else:
        raise HtmlError("an attribute takes a SafeToken or an enumerated value")
    return f' {key}="{text}"'


class Element(Node):
    """A tag with checked attributes and node children."""

    __slots__ = ("_attrs", "_children", "_tag")

    def __init__(self, tag: Tag, children: Sequence[Node], attrs: dict[str, object]) -> None:
        if not isinstance(tag, Tag):
            raise HtmlError("tag not allowed")
        if any(type(child) not in _NODES for child in children):
            raise HtmlError("a child must be a Text, Trusted or Element of this module")
        if tag in _VOID and children:
            raise HtmlError("a void element has no children")
        self._tag, self._children = tag, tuple(children)
        self._attrs = "".join(_attr(name, value) for name, value in attrs.items())

    def render(self) -> str:
        """Return the element markup."""
        if self._tag in _VOID:
            return f"<{self._tag}{self._attrs}>"
        return f"<{self._tag}{self._attrs}>{''.join(c.render() for c in self._children)}</{self._tag}>"


def el(tag: Tag, *children: Node, **attrs: Attr) -> Element:
    """Build an element; a trailing underscore on an attribute name (`class_`, `for_`) is dropped. Raises: HtmlError."""
    return Element(tag, children, dict(attrs))


def field(label: Trusted, value: str, max_chars: int = DEFAULT_MAX_CHARS) -> Element:
    """A labeled untrusted value: `<bdi dir="auto">` keeps mixed-direction text from reordering its surroundings.

    The value is cut to `max_chars` characters (`...` at the end) with the original length stated in the
    note `(N characters)`; control and bidirectional characters are shown as `<U+XXXX>`.

    Raises:
        HtmlError: the label is not `Trusted`, the value is not a string or `max_chars` is below 3.
    """
    if not isinstance(label, Trusted) or not isinstance(value, str) or max_chars < 3:
        raise HtmlError("field takes a Trusted label, a string value and max_chars of at least 3")
    space = trusted(" ")
    parts = [
        el(Tag.SPAN, label, class_=SafeToken("label")),
        space,
        el(Tag.BDI, Text(truncate(value, max_chars)), dir=SafeToken("auto")),
    ]
    if len(value) > max_chars:
        parts += [space, el(Tag.SPAN, Text(f"({len(value)} characters)"), class_=SafeToken("note"))]
    return el(Tag.SPAN, *parts, class_=SafeToken("field"))


class Stylesheet(Node):
    """The one `<style>` element of a page and the policy source that allows exactly it."""

    __slots__ = ("_css", "csp_source")

    def __init__(self, css: str, _mint: object = None) -> None:
        if _mint is not _MINT or not isinstance(css, str) or "<" in css:
            raise HtmlError("a stylesheet is a source literal without '<'")
        self._css = css
        digest = base64.b64encode(hashlib.sha256(css.encode("utf-8")).digest()).decode("ascii")
        self.csp_source = f"'sha256-{digest}'"

    def render(self) -> str:
        """Return `<style>` with the CSS unescaped, so the hash matches the policy."""
        return f"<style>{self._css}</style>"


def stylesheet(css: LiteralString) -> Stylesheet:
    """Wrap a CSS source literal. Raises: HtmlError if it holds `<` or is not a str."""
    return Stylesheet(css, _MINT)


def document(title: Node, body: Sequence[Node], style: Stylesheet) -> str:
    """Return a complete English page with one style element and the policy that allows only it (no script)."""
    if not isinstance(style, Stylesheet) or type(title) not in _NODES:
        raise HtmlError("document takes a Node title and a Stylesheet")
    policy = f"default-src 'none'; style-src {style.csp_source}"
    head = f'<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{policy}">'
    return (
        f'<!doctype html><html lang="en" dir="ltr"><head>{head}<title>{title.render()}</title>{style.render()}</head>'
        f"{el(Tag.BODY, *body).render()}</html>"
    )


_NODES: frozenset[type[Node]] = frozenset({Text, Trusted, Element, Stylesheet})  # closed: no foreign subclass
