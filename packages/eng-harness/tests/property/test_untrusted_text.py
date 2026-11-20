"""Adversarial strings stay escaped on every screen and in the report (plan 0006 T17; AC48)."""

from __future__ import annotations

import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path

from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from fixtures.report_run import build_report_run
from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness import __version__
from eng_harness._html import Text, field, trusted
from eng_harness._kinds import HARNESS_KINDS
from eng_harness._text import sanitize_html, truncate
from eng_harness.journal import JournalReader
from eng_harness.report import ReleaseMarks, build_report

_ALPHABET = [
    *list("<>&\"'/=`;:() \t\n\r\x00\x1b"),
    "\u202e",
    "\u2066",
    "\u200f",
    "م",
    "ر",
    "٣",
    "a",
    "1",
]
_ANY = st.one_of(
    st.text(max_size=40),
    st.text(alphabet=st.sampled_from(_ALPHABET), max_size=40),
    st.just("x" * 200),
    st.just("<script>alert(1)</script>"),
    st.just("</style>"),
    st.just("javascript:alert(1)"),
    st.just("مرحبا 123"),
)

_ALLOWED_TAGS = frozenset(
    {
        "html",
        "head",
        "meta",
        "title",
        "style",
        "body",
        "h1",
        "h2",
        "h3",
        "p",
        "div",
        "span",
        "bdi",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "ul",
        "ol",
        "li",
        "a",
        "form",
        "input",
        "button",
        "label",
        "hr",
        "br",
        "section",
        "nav",
        "header",
        "footer",
        "strong",
        "em",
        "code",
        "pre",
    }
)


class _Scan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def _parse(markup: str) -> _Scan:
    scan = _Scan()
    scan.feed(markup)
    scan.close()
    return scan


@settings(derandomize=True, max_examples=60, deadline=None)
@given(_ANY)
def test_every_screen_and_report_escape(text: str) -> None:
    """Every screen field and the report show only escaped, labeled, truncated text (AC48)."""
    limit = 32
    rendered = field(trusted("Title"), text, max_chars=limit).render()
    parsed = _parse(rendered)
    assert set(parsed.tags) <= {"span", "bdi"}
    assert parsed.tags.count("bdi") == 1
    shown = sanitize_html(truncate(text, limit))
    assert shown in "".join(parsed.text)
    assert "<script" not in rendered.lower()
    bare = re.sub(r"</?(span|bdi)\b[^<>]*>", "", rendered)
    assert "<" not in bare

    assert "".join(_parse(Text(text).render()).text) == sanitize_html(text)

    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"ac48", clock)
    with tempfile.TemporaryDirectory(prefix="ac48-") as folder:
        workspace = Workspace(root=Path(folder) / "ws", classification=LocationClass.LOCAL)
        store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
        run_dir = workspace.root / "runs" / "run_x"
        run_dir.mkdir(parents=True)
        build_report_run(run_dir, store, ids)
        reader = JournalReader(run_dir)
        try:
            html = build_report(reader, store, ReleaseMarks(records={}), clock, __version__)
        finally:
            reader.close()
        report = _parse(html)
        assert set(report.tags) <= _ALLOWED_TAGS
        poisoned = field(trusted("Note"), text, max_chars=64).render()
        assert sanitize_html(truncate(text, 64)) in "".join(_parse(poisoned).text)
