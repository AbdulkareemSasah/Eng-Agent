"""Adversarial strings stay escaped on every screen and in the report (plan 0006 T17; AC48)."""

from __future__ import annotations

import asyncio
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Provenance
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import JsonValue

from eng_harness import __version__
from eng_harness._html import DEFAULT_MAX_CHARS, document
from eng_harness._kinds import HARNESS_KINDS
from eng_harness._text import sanitize_html, truncate
from eng_harness.ctx import ApprovalKind
from eng_harness.engine._inputs import Evidence, Question, build_request, choice_schema
from eng_harness.errors import HarnessCode
from eng_harness.journal import Event, EventType, JournalReader, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.pages import PageApprovalPort, PageInputPort, Screen
from eng_harness.pages._css import STYLESHEET
from eng_harness.pages._screens_approval import approval_screens, sign_off_screens
from eng_harness.pages._screens_choice import choice_screens
from eng_harness.ports import ApprovalRequest
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
    st.just("x" * 10_000_000),  # AC48: a 10 MB string
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
        "main",
    }
)
_ALLOWED_ATTRS = frozenset(
    {
        "class",
        "id",
        "href",
        "action",
        "method",
        "name",
        "type",
        "value",
        "for",
        "dir",
        "colspan",
        "scope",
        "lang",
        "charset",
        "http-equiv",
        "content",
    }
)
_PRODUCER = Provenance(
    tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
)
_SHA = "a" * 64
_START_MS = 1_767_225_600_000


class _Scan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str | None]] = []
        self.text: list[str] = []
        self._bdi: list[str] = []
        self._in_bdi = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attrs.extend(attrs)
        if tag == "bdi":
            self._in_bdi += 1
            self._bdi.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "bdi" and self._in_bdi:
            self._in_bdi -= 1

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self._in_bdi:
            self._bdi[-1] += data


def _parse(markup: str) -> _Scan:
    scan = _Scan()
    scan.feed(markup)
    scan.close()
    return scan


def _expected(text: str, limit: int = DEFAULT_MAX_CHARS) -> str:
    return sanitize_html(truncate(text, limit))


def _assert_body(markup: str, text: str, *, labeled: bool) -> None:
    """Parsed output stays inside the allowlists; the adversarial value is only escaped inside `<bdi dir="auto">`."""
    limit = DEFAULT_MAX_CHARS
    shown = _expected(text, limit)
    parsed = _parse(markup)
    assert set(parsed.tags) <= _ALLOWED_TAGS
    assert {name for name, _ in parsed.attrs} <= _ALLOWED_ATTRS
    assert shown in "".join(parsed.text)
    assert shown in parsed._bdi
    assert 'dir="auto"' in markup
    if labeled:
        assert 'class="field"' in markup
        assert 'class="label"' in markup
        if len(text) > limit:
            assert f"({len(text)} characters)" in "".join(parsed.text)
    # Outside tags, `<` must only appear as an entity (`&lt;`); the doctype is stripped first.
    bare = re.sub(r"<!doctype html>", "", markup, flags=re.IGNORECASE)
    bare = re.sub(r"</?[a-zA-Z][^<>]*>", "", bare)
    assert "<" not in bare
    for control in ("\u202e", "\u2066", "\u200f"):
        assert control not in bare
        if control in text:
            assert f"<U+{ord(control):04X}>" in "".join(parsed.text)


def _journal_text(text: str) -> str:
    """Journal events refuse payloads over 16384 bytes without a ref (spec 4.4.1); keep inline titles under that."""
    encoded = text.encode("utf-8")
    if len(encoded) <= 12_000:
        return text
    # AC48's 10 MB example still reaches screens and the report through preview/result store fields.
    return text[:200]


def _render_screen(screen: Screen) -> str:
    return document(screen.title, list(screen.render("tok")), STYLESHEET)


def _approval_bodies(store: ResultStore, run_dir: Path, text: str, preview_ref: str, digest: str) -> list[str]:
    builders = approval_screens(store, lambda: JournalReader(run_dir))
    sign_builders, sign_checks = sign_off_screens(store, lambda: JournalReader(run_dir))
    port = PageApprovalPort(builders={**builders, **sign_builders}, checks=sign_checks)
    bodies: list[str] = []
    for kind in (
        ApprovalKind.CHANGE_SET.value,
        ApprovalKind.PROMOTION.value,
        ApprovalKind.INFO.value,
        ApprovalKind.SIGN_OFF.value,
    ):
        request = ApprovalRequest(
            request_id=f"apr_{kind}",
            run_id="run_ac48",
            kind=kind,
            title=text,
            preview_ref=preview_ref,
            shown_sha256=digest,
            binding=(),
            items=("i1",),
        )
        asyncio.run(port.present(request))
        screen = port.hub.screen("request", request.request_id)
        assert screen is not None
        bodies.append(_render_screen(screen))
    return bodies


def _void_body(text: str) -> str:
    """Voided display (T7b): the APPROVAL_VOID message is an untrusted labeled field."""
    port = PageApprovalPort()
    request = ApprovalRequest(
        request_id="apr_void",
        run_id="run_ac48",
        kind=ApprovalKind.CHANGE_SET.value,
        title="Apply",
        preview_ref="res_" + "0" * 26,
        shown_sha256=_SHA,
        binding=(),
        items=("i1",),
    )
    asyncio.run(port.present(request))
    resolved = ev.ApprovalResolved.model_validate(
        {
            "request_id": request.request_id,
            "shown_sha256": _SHA,
            "decision": "approve",
            "rejected_items": [],
            "reason": None,
            "by": "engineer:ada",
        }
    )
    port.hub.emit(
        Event(
            seq=1,
            type=EventType.APPROVAL_RESOLVED,
            path=None,
            attempt=None,
            at="2026-01-01T00:00:00.000Z",
            payload=resolved,
        )
    )
    error = ev.HarnessError(harness_code=HarnessCode.APPROVAL_VOID, message=text)
    port.hub.emit(
        Event(
            seq=2,
            type=EventType.STEP_FAILED,
            path="1",
            attempt=1,
            at="2026-01-01T00:00:00.000Z",
            payload=ev.StepFailed(error=error, retryable=False, duration_ms=1),
        )
    )
    screen = port.hub.screen("request", request.request_id)
    assert screen is not None
    return _render_screen(screen)


def _choice_body(text: str) -> str:
    builders, checks = choice_screens()
    approvals = PageApprovalPort(builders=builders, checks=checks)
    inputs = PageInputPort(approvals)
    ids = SeededIdSource(b"ac48-choice", FixedClock(_START_MS, 1))
    schema = choice_schema(
        [Question(name="next", prompt="Prompt", options=("accept", "more_edits"))],
        [Evidence(name="e0", label="Evidence", text=text)],
    )
    request = build_request(ids, "dec_ac48", "engine.decision", text, schema, ())
    asyncio.run(inputs.present(request))
    screen = approvals.hub.screen("request", request.request_id)
    assert screen is not None
    return _render_screen(screen)


def _preview_payload(text: str) -> dict[str, JsonValue]:
    return {
        "items": [{"id": "i1", "label": text, "refs": []}],
        "diff_ref": None,
        "models": [],
    }


def _report_body(store: ResultStore, run_dir: Path, ids: SeededIdSource, clock: FixedClock, text: str) -> str:
    """Journal, result and preview text fields carry `text`; the report must show it only escaped."""
    preview = _preview_payload(text)
    stored = store.put("harness.approval_preview/1", preview, _PRODUCER)
    digest = payload_sha256(preview)
    blob = store.put("harness.journal_blob/1", {"value": text}, _PRODUCER).result_id
    inline = _journal_text(text)
    writer = JournalWriter(run_dir, store, clock, ids)
    header = {
        "run_id": "run_ac48",
        "workflow": "w",
        "block": {"name": "b", "version": "1", "code_sha256": _SHA},
        "input_sha256": _SHA,
        "mode": "work_on_copy",
        "run_class": "trial",
        "engine_version": "1",
        "contract_version": "eng-contract/1",
        "settings_sha256": _SHA,
        "servers": [],
        "always_ask": [],
        "input_ref": blob,
        "basis_ref": blob,
    }
    writer.append(EventType.RUN_STARTED, header)
    writer.append(
        EventType.APPROVAL_REQUESTED,
        {
            "request_id": "ap1",
            "kind": "INFO",
            "title": inline,
            "preview_ref": stored.result_id,
            "shown_sha256": digest,
            "binding": {},
            "items": ["i1"],
        },
    )
    writer.append(
        EventType.APPROVAL_RESOLVED,
        {
            "request_id": "ap1",
            "shown_sha256": digest,
            "decision": "reject",
            "rejected_items": ["i1"],
            "item_reasons": {"i1": inline},
            "reason": inline,
            "by": "engineer:x",
        },
    )
    writer.append(
        EventType.STEP_STARTED,
        {"kind": "tool", "name": "t", "args": {}, "args_sha256": _SHA, "effect": "read"},
        path="0",
        attempt=1,
    )
    writer.append(
        EventType.STEP_COMPLETED,
        {
            "result": {"ref": f"{blob}#/value", "summary": {}, "warnings": [], "complete": True},
            "duration_ms": 1,
        },
        path="0",
        attempt=1,
    )
    writer.append(
        EventType.STEP_STARTED,
        {"kind": "tool", "name": "t", "args": {}, "args_sha256": _SHA, "effect": "read"},
        path="1",
        attempt=1,
    )
    writer.append(
        EventType.STEP_FAILED,
        {
            "error": {"harness_code": "NEEDS_ENGINEER", "message": inline},
            "retryable": False,
            "duration_ms": 1,
        },
        path="1",
        attempt=1,
    )
    writer.append(
        EventType.RUN_ESCALATED,
        {"reason": "needs_reconciliation", "detail": inline, "evidence": [], "request_id": None},
    )
    writer.close()
    reader = JournalReader(run_dir)
    try:
        return build_report(reader, store, ReleaseMarks(records={}), clock, __version__)
    finally:
        reader.close()


@settings(derandomize=True, max_examples=60, deadline=None)
@given(_ANY)
def test_every_screen_and_report_escape(text: str) -> None:
    """Every screen and the report show adversarial text only escaped, labeled, truncated (AC48)."""
    clock = FixedClock(_START_MS, 1)
    ids = SeededIdSource(b"ac48", clock)
    with tempfile.TemporaryDirectory(prefix="ac48-") as folder:
        workspace = Workspace(root=Path(folder) / "ws", classification=LocationClass.LOCAL)
        store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
        run_dir = workspace.root / "runs" / "run_ac48"
        run_dir.mkdir(parents=True)
        preview = _preview_payload(text)
        stored = store.put("harness.approval_preview/1", preview, _PRODUCER)
        digest = payload_sha256(preview)
        # Empty journal so promotion / sign-off can open a reader.
        JournalWriter(run_dir, store, clock, ids).close()

        for body in _approval_bodies(store, run_dir, text, stored.result_id, digest):
            _assert_body(body, text, labeled=True)

        _assert_body(_void_body(text), text, labeled=True)
        _assert_body(_choice_body(text), text, labeled=True)

        report_dir = workspace.root / "runs" / "run_report"
        report_dir.mkdir(parents=True)
        report = _report_body(store, report_dir, SeededIdSource(b"ac48-report", clock), clock, text)
        # Report rows use `<bdi dir="auto">` (not always the labeled `field()` wrapper); journal inline
        # fields use `_journal_text` when over the 16384-byte event cap, while preview/result hold `text`.
        _assert_body(report, _journal_text(text), labeled=False)
        assert _expected(text) in _parse(report)._bdi or _expected(_journal_text(text)) in _parse(report)._bdi
