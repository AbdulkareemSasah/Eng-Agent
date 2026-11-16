"""The change-set, promotion and info screens (spec 0006 4.4.6; AC40, AC41).

Purpose: render an approval request from its stored preview (checked against `shown_sha256`, else a screen with no
button) and the journal's `model_saved` records. Every value shown is read from a stored result and named with its unit
and source; none is computed here. A field name is a prefix and an item id and must be a token (AC49): an id that is
not one makes the change-set screen a refusal screen. Units: as stored with each value. Errors: a damaged preview is a
screen, never an exception.
"""

from collections.abc import Callable, Sequence
from typing import cast

from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError
from eng_contract.refs import Ref, parse_ref
from eng_contract.store import ResultStore
from pydantic import JsonValue, ValidationError

from eng_harness import _html as h
from eng_harness._html import DEFAULT_MAX_CHARS, Element, Node, SafeToken, Tag, Text, Trusted, el
from eng_harness._text import format_number, truncate
from eng_harness.ctx import ApprovalKind, Preview
from eng_harness.journal import JournalReader
from eng_harness.kinds.calcs import Change, ModelDiff
from eng_harness.pages import _labels as lb
from eng_harness.pages._answers import REASON, REJECT, Request, bound_sha256
from eng_harness.pages._ports import PageHub, ScreenBuilder
from eng_harness.pages._routes import Screen
from eng_harness.pages._security import CSRF_FIELD, Subject
from eng_harness.ports import ApprovalRequest

_SHORT = 12  # characters of a hash shown on the change-set screen; a promotion shows the whole hash
type _Journal = Callable[[], JournalReader]


def _inline(text: str) -> Element:
    return el(Tag.BDI, Text(truncate(text, DEFAULT_MAX_CHARS)), dir=SafeToken("auto"))


def _table(head: Sequence[Trusted], rows: Sequence[Element]) -> Element:
    heading = el(Tag.TR, *(el(Tag.TH, label) for label in head))
    return el(Tag.TABLE, el(Tag.THEAD, heading), el(Tag.TBODY, *rows))


def _row(*cells: str) -> Element:
    return el(Tag.TR, *(el(Tag.TD, _inline(cell)) for cell in cells))


def _show(value: JsonValue) -> str:
    """A stored value as text: a quantity as `value unit`, a number in `format_number`, a structure as a note."""
    if isinstance(value, dict) and set(value) == {"value", "unit"}:
        return f"{_show(value['value'])} {value['unit']}"
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format_number(value)
    return str(value) if isinstance(value, int | str) else "(structured value)"


def _at(value: JsonValue, tokens: Sequence[str]) -> JsonValue:
    """The member of `value` at the pointer tokens; raises `LookupError` when there is none."""
    for token in tokens:
        if isinstance(value, dict):
            value = value[token]
        elif isinstance(value, list):
            value = value[int(token)]
        else:
            raise LookupError(token)
    return value


class _Screens:
    def __init__(self, store: ResultStore, journal: _Journal) -> None:
        self._store, self._journal = store, journal

    def _payload(self, ref: str) -> JsonValue:
        """The value `ref` names; raises `ContractError`, `LookupError` or `ValueError` when it cannot be read."""
        result_id, tokens = parse_ref(ref)
        return _at(self._store.payload(result_id), tokens)

    def _preview(self, request: ApprovalRequest, *, fields: bool) -> Preview | None:
        """The stored preview when its hash is the one shown (and, with `fields`, every item id can be a name)."""
        try:
            payload = self._store.payload(parse_ref(request.preview_ref)[0])
            preview = Preview.model_validate(payload)
            for item in preview.items if fields else ():
                SafeToken(REJECT + item.id), SafeToken(REASON + item.id)
        except ContractError, ValidationError, h.HtmlError:
            return None
        return preview if payload_sha256(payload) == request.shown_sha256 else None

    def _cite(self, ref: Ref) -> str:
        """`value unit [tool result#pointer]`: the stored value with its unit and its source."""
        try:
            tool = self._store.get(parse_ref(ref.ref)[0]).producer.tool
            return f"{_show(self._payload(ref.ref))} [{tool} {ref.ref}]"
        except ContractError, LookupError, ValueError:
            return f"(not readable) [{ref.ref}]"

    def _screen(
        self, request: ApprovalRequest, preview: Preview | None, top: Callable[[Preview], list[Node]],
        inside: Callable[[Preview], list[Node]] = lambda _: [], *, accept: Trusted = lb.APPROVE,
    ) -> Screen:  # fmt: skip
        """One screen: the title, `top`, and a form with `inside`, the name, the reason and Approve and Reject."""
        subject = Subject("approval", request.request_id, bound_sha256(request))
        title = h.field(lb.TITLE, request.title)
        if preview is None:
            body = [el(Tag.H1, title), el(Tag.P, lb.DAMAGED), el(Tag.P, el(Tag.A, lb.BACK, href=h.href()))]
            return Screen(lb.TITLE, subject, frozenset(), lambda _: body)
        fields = frozenset({"shown_sha256", "by", "decision", "reason"})
        if preview.items and inside(preview):  # the item boxes of the change set
            fields |= frozenset(p + item.id for item in preview.items for p in (REJECT, REASON))

        def render(token: str) -> list[Node]:
            def hidden(name: str, value: str) -> Element:
                return el(Tag.INPUT, type=SafeToken("hidden"), name=SafeToken(name), value=SafeToken(value))

            def text(label: Trusted, name: str) -> Element:
                return el(Tag.P, el(Tag.LABEL, label, el(Tag.INPUT, type=SafeToken("text"), name=SafeToken(name))))

            decide = [
                el(Tag.BUTTON, label, type=SafeToken("submit"), name=SafeToken("decision"), value=SafeToken(value))
                for label, value in ((accept, "approve"), (lb.REJECT, "reject"))
            ]
            action = h.href(SafeToken("answer"), SafeToken(request.request_id))
            form = el(
                Tag.FORM, hidden(CSRF_FIELD, token), hidden("shown_sha256", bound_sha256(request)),
                *inside(preview), text(lb.NAME, "by"), text(lb.REASON, "reason"), el(Tag.P, *decide),
                method=SafeToken("post"), action=action,
            )  # fmt: skip
            return [el(Tag.H1, title), *top(preview), form]

        return Screen(lb.TITLE, subject, fields, render)

    # change set -------------------------------------------------------------------------------------------------

    def change_set(self, hub: PageHub, request: Request) -> Screen:
        approval = cast(ApprovalRequest, request)
        preview = self._preview(approval, fields=True)
        return self._screen(approval, preview, lambda p: self._change_top(approval, p), self._items)

    def _items(self, preview: Preview) -> list[Node]:
        rows = []
        for item in preview.items:
            values = el(Tag.TD, *(el(Tag.DIV, Text(self._cite(ref))) for ref in item.refs))
            reject = el(Tag.INPUT, type=SafeToken("checkbox"), name=SafeToken(REJECT + item.id))
            reason = el(Tag.INPUT, type=SafeToken("text"), name=SafeToken(REASON + item.id))
            cells = [el(Tag.TD, _inline(item.id)), el(Tag.TD, _inline(item.label)), values]
            rows.append(el(Tag.TR, *cells, el(Tag.TD, reject), el(Tag.TD, reason)))
        return [_table(lb.ITEMS, rows)]

    def _change_top(self, request: ApprovalRequest, preview: Preview) -> list[Node]:
        bound = [
            _row(b.model_key, b.model_id, str(b.revision), b.fingerprint[:_SHORT], b.file_sha256[:_SHORT])
            for b in request.binding
        ]
        digest = h.field(lb.PREVIEW_HASH, request.shown_sha256[:_SHORT])
        return [*self._diff(preview), el(Tag.H2, lb.BINDING_HEADING), _table(lb.BINDING, bound), el(Tag.P, digest)]

    def _diff(self, preview: Preview) -> list[Node]:
        if preview.diff_ref is None:
            return []
        try:
            diff = ModelDiff.model_validate(self._payload(preview.diff_ref.ref))
        except ContractError, LookupError, ValueError:  # a ValidationError is a ValueError
            return [el(Tag.H2, lb.DIFF_HEADING), el(Tag.P, lb.DIFF_UNREADABLE)]
        rows = [row for change in diff.changes for row in self._change_rows(change)]
        return [el(Tag.H2, lb.DIFF_HEADING), _table(lb.DIFF, rows)]

    def _change_rows(self, change: Change) -> list[Element]:
        head = (change.section, "/".join(change.key), change.change)
        if not change.properties:
            return [_row(*head, "", _show(change.before), _show(change.after), "")]
        return [_row(*head, p.pointer, _show(p.before), _show(p.after), p.unit or "") for p in change.properties]

    # promotion and info -----------------------------------------------------------------------------------------

    def promotion(self, hub: PageHub, request: Request) -> Screen:
        approval = cast(ApprovalRequest, request)
        return self._screen(approval, self._preview(approval, fields=False), lambda _: self._promotion_top(approval))

    def _promotion_top(self, request: ApprovalRequest) -> list[Node]:
        reader = self._journal()
        try:
            saved = [v.saved for v in reader.models() if v.saved.role == "working_copy"]
        finally:
            reader.close()
        rows: list[Element] = []
        notes: list[Node] = []
        for b in request.binding:
            copy = next((s for s in reversed(saved) if s.model_key == b.model_key), None)
            if copy is None:
                notes.append(el(Tag.P, _inline(b.model_key), el(Tag.SPAN, lb.NO_WORKING_COPY)))
                rows.append(_row(b.model_key, "", "", "", b.file_sha256))
                continue
            names = ", ".join(copy.origin_file_names)  # base names: the journal model refuses a path
            rows.append(_row(b.model_key, names, names, copy.origin_sha256 or "", b.file_sha256))
        return [*notes, _table(lb.PROMOTION, rows)]

    def info(self, hub: PageHub, request: Request) -> Screen:
        approval = cast(ApprovalRequest, request)
        return self._screen(
            approval, self._preview(approval, fields=False),
            lambda p: [el(Tag.UL, *(el(Tag.LI, _inline(i.label)) for i in p.items))], accept=lb.ACKNOWLEDGE,
        )  # fmt: skip


def approval_screens(store: ResultStore, journal: _Journal) -> dict[str, ScreenBuilder]:
    """The builders of the `change_set`, `promotion` and `info` requests; `journal` opens a reader the screen closes."""
    screens = _Screens(store, journal)
    return {
        ApprovalKind.CHANGE_SET.value: screens.change_set,
        ApprovalKind.PROMOTION.value: screens.promotion,
        ApprovalKind.INFO.value: screens.info,
    }
