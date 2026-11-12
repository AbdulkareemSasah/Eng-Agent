"""Report sections 2 to 5 (spec 0006 4.6.1, AC51, AC52, AC55)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from eng_contract.refs import parse_ref
from eng_contract.store import ResultStore
from pydantic import JsonValue

from eng_harness._html import DEFAULT_MAX_CHARS, Element, HtmlError, Node, SafeToken, Tag, Text, el, fragment, trusted
from eng_harness._text import format_number, format_timestamp, truncate
from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev
from eng_harness.report._model import DecisionEntry, ReconciliationEntry, ReportModel, RequestEntry

_MAX_ROWS = 200  # spec 0006 4.6.1: generic renderer row cap
_MAX_DEPTH = 4  # spec 0006 4.6.1: generic renderer depth cap
_CHANGE_SET = frozenset({"change_set", "CHANGE_SET"})
_READBACK = "harness.readback_check/1"
_TITLES = {"changes": trusted("Changes"), "results": trusted("Results summary")}
_TITLES["sources"] = trusted("Sources")
_TITLES["decisions"] = trusted("Decisions")
_OWN = {"verdicts.set/1": "verdicts", "issues.model_check/1": "checks", "forces.story_drifts/1": "drifts"}
_OWN["basis.design_basis/1"] = _OWN["basis.engineer_input/1"] = "basis"
_OWN["harness.approval_preview/1"] = "generic"
type _Renderer = Callable[[dict[str, JsonValue], str, "SourceBook"], list[Node]]
_REGISTRY: dict[str, _Renderer] = {}


@dataclass(frozen=True)
class CellSource:
    result_id: str
    pointer: str


@dataclass
class SourceBook:
    _order: list[CellSource] = field(default_factory=list)
    _index: dict[tuple[str, str], int] = field(default_factory=dict)

    def number(self, source: CellSource) -> int:
        key = (source.result_id, source.pointer)
        found = self._index.get(key)
        if found is None:
            found = len(self._order) + 1
            self._index[key] = found
            self._order.append(source)
        return found


def register_renderer(kind: str, renderer: _Renderer) -> None:
    """Map a result kind to its section renderer (spec 0006 4.6.1). Later specs register theirs."""
    _REGISTRY[kind] = renderer


def value_cell(value: object, source: CellSource, book: SourceBook) -> Element:
    """Cell of class `v` linking to `#src-N` (spec 0006 4.6.1, AC52). `source` is required."""
    if not isinstance(source, CellSource) or not source.result_id:
        raise HtmlError("a value cell requires a source")
    shown = value if isinstance(value, str) else _show(value)
    parts: list[Node] = [el(Tag.BDI, Text(truncate(shown, DEFAULT_MAX_CHARS)), dir=SafeToken("auto"))]
    if len(shown) > DEFAULT_MAX_CHARS:
        parts.append(el(Tag.SPAN, Text(f"({len(shown)} characters)"), class_=SafeToken("note")))
    link = el(Tag.A, *parts, href=fragment(SafeToken(f"src-{book.number(source)}")))
    return el(Tag.TD, link, class_=SafeToken("v"))


def render_sections(model: ReportModel, reader: JournalReader, store: ResultStore) -> str:
    """Sections 2 to 5. Revisions and approval items come from `reader`, not the model (B-435)."""
    return _Page(SourceBook(), model, reader, store).render()


def _show(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format_number(value)
    if isinstance(value, int):
        return str(value)
    return "" if value is None else str(value)


def _render_generic(payload: dict[str, JsonValue], result_id: str, book: SourceBook) -> list[Node]:
    page = _Page.__new__(_Page)
    page.book = book
    return page.generic(payload, result_id)


class _Page:
    def __init__(self, book: SourceBook, model: ReportModel, reader: JournalReader, store: ResultStore) -> None:
        self.book, self.model, self.reader, self.store = book, model, reader, store

    def render(self) -> str:
        return "".join(part.render() for part in (self.changes(), self.results(), self.sources(), self.decisions()))

    def cite(self, value: object, result_id: str, pointer: str) -> Element:
        return value_cell(value, CellSource(result_id, pointer), self.book)

    def bdi(self, text: str) -> Element:
        return el(Tag.TD, el(Tag.BDI, Text(truncate(text, DEFAULT_MAX_CHARS)), dir=SafeToken("auto")))

    def texts(self, *parts: str) -> Element:
        return el(Tag.TR, *(self.bdi(part) for part in parts))

    def table(self, rows: Sequence[Element], *labels: str) -> Element:
        head = el(Tag.TR, *(el(Tag.TH, Text(label)) for label in labels))
        return el(Tag.TABLE, el(Tag.THEAD, head), el(Tag.TBODY, *rows))

    def section(self, token: str, *children: Node) -> Element:
        return el(Tag.SECTION, el(Tag.H2, _TITLES[token]), *children, id=SafeToken(token))

    def unit(self, value: object, unit: object) -> str:
        text = _show(value)
        return f"{text} {unit}" if isinstance(unit, str) and unit else text

    def token(self, part: str) -> str:
        return part.replace("~", "~0").replace("/", "~1")

    def key(self, value: object) -> str:
        return ".".join(str(part) for part in value) if isinstance(value, list) else ""

    def subject(self, value: object) -> str:
        name = value.get("id") if isinstance(value, dict) else None
        return name if isinstance(name, str) else ""

    def dicts(self, value: object) -> list[dict[str, JsonValue]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    def scalars(self, node: JsonValue) -> int:
        if isinstance(node, dict):
            return sum(self.scalars(child) for child in node.values())
        if isinstance(node, list):
            return sum(self.scalars(child) for child in node)
        return 1

    def walk(self, node: JsonValue, pointer: str, depth: int, out: list[tuple[str, str]]) -> int:
        if not isinstance(node, dict | list):
            if len(out) >= _MAX_ROWS:
                return 1
            out.append((pointer or "/", _show(node)))
            return 0
        if depth >= _MAX_DEPTH:
            return self.scalars(node)
        if isinstance(node, dict):
            pairs = [(self.token(key), child) for key, child in node.items()]
        else:
            pairs = [(str(index), child) for index, child in enumerate(node)]
        return sum(self.walk(child, f"{pointer}/{token}", depth + 1, out) for token, child in pairs)

    def generic(self, payload: dict[str, JsonValue], result_id: str) -> list[Node]:
        found: list[tuple[str, str]] = []
        omitted = self.walk(payload, "", 0, found)
        rows = [el(Tag.TR, self.bdi(pointer), self.cite(text, result_id, pointer)) for pointer, text in found]
        if omitted:
            rows.append(el(Tag.TR, el(Tag.TD, Text(f"{omitted} more")), el(Tag.TD, Text(result_id))))
        return [self.table(rows, "Field", "Value")] if rows else []

    def verdicts(self, payload: dict[str, JsonValue], result_id: str) -> list[Node]:
        raw = payload.get("counts")
        nodes: list[Node] = []
        if isinstance(raw, dict):
            counts = [self.texts(str(status), _show(count)) for status, count in raw.items()]
            nodes.append(self.table(counts, "Status", "Count"))
        members: list[Element] = []
        for index, verdict in enumerate(self.dicts(payload.get("verdicts"))):
            if verdict.get("governing") is not True and verdict.get("status") != "FAIL":
                continue
            cells = [self.bdi(self.subject(verdict.get("subject"))), self.bdi(_show(verdict.get("status")))]
            ratio = verdict.get("ratio")
            if ratio is not None:
                cells.append(self.cite(ratio, result_id, f"/verdicts/{index}/ratio"))
            members.append(el(Tag.TR, *cells))
        if members:
            nodes.append(self.table(members, "Member", "Status", "Ratio"))
        return nodes

    def checks(self, payload: dict[str, JsonValue], result_id: str) -> list[Node]:
        rows = [self._issue(issue, result_id, index) for index, issue in enumerate(self.dicts(payload.get("issues")))]
        return [self.table(rows, "Severity", "Code", "Subject", "Message")] if rows else []

    def _issue(self, issue: dict[str, JsonValue], result_id: str, index: int) -> Element:
        message = self.cite(issue.get("message"), result_id, f"/issues/{index}/message")
        severity = self.bdi(_show(issue.get("severity")))
        code = self.bdi(_show(issue.get("code")))
        subject = self.bdi(self.subject(issue.get("subject")))
        return el(Tag.TR, severity, code, subject, message)

    def drifts(self, payload: dict[str, JsonValue], result_id: str) -> list[Node]:
        rows = [self._drift(row, result_id, index) for index, row in enumerate(self.dicts(payload.get("rows")))]
        return [self.table(rows, "Story", "Direction", "Drift ratio")] if rows else []

    def _drift(self, row: dict[str, JsonValue], result_id: str, index: int) -> Element:
        ratio = self.cite(row.get("drift_ratio"), result_id, f"/rows/{index}/drift_ratio")
        return el(Tag.TR, self.bdi(_show(row.get("story"))), self.bdi(_show(row.get("direction"))), ratio)

    def basis(self, payload: dict[str, JsonValue], result_id: str) -> list[Node]:
        fields = payload.get("fields")
        if not isinstance(fields, dict):
            return []
        rows = [row for name, body in fields.items() if (row := self._field_row(name, body, result_id)) is not None]
        return [self.table(rows, "Field", "Value")] if rows else []

    def _field_row(self, name: object, body: object, result_id: str) -> Element | None:
        if not isinstance(body, dict):
            return None
        pointer = f"/fields/{self.token(str(name))}/value"
        shown = self.cite(self.unit(body.get("value"), body.get("unit")), result_id, pointer)
        return el(Tag.TR, self.bdi(str(name)), shown)

    def payload_of(self, ref: object) -> tuple[str, dict[str, JsonValue]] | None:
        if not isinstance(ref, str) or not ref:
            return None
        result_id = parse_ref(ref)[0]
        return result_id, self.store.payload(result_id)

    def applied(self, request_id: str) -> list[tuple[ev.StepStarted, ev.StepCompleted | None]]:
        started: dict[tuple[str | None, int | None], ev.StepStarted] = {}
        done: dict[tuple[str | None, int | None], ev.StepCompleted] = {}
        order: list[tuple[str | None, int | None]] = []
        for event in self.reader.events():
            key = (event.path, event.attempt)
            if isinstance(event.payload, ev.StepStarted) and event.payload.under == request_id:
                started[key] = event.payload
                order.append(key)
            elif isinstance(event.payload, ev.StepCompleted) and key in started:
                done[key] = event.payload
        return [(started[key], done.get(key)) for key in order]

    def diff_rows(self, payload: dict[str, JsonValue], result_id: str, marks: set[tuple[str, str]]) -> list[Element]:
        rows: list[Element] = []
        seen: set[tuple[str, str]] = set()
        for index, change in enumerate(self.dicts(payload.get("changes"))):
            section, key = _show(change.get("section")), self.key(change.get("key"))
            seen.add((section, key))
            mark = "engineer change" if (section, key) in marks else ""
            kind = _show(change.get("change"))
            props = self.dicts(change.get("properties"))
            if not props:
                rows.append(self.texts(section, key, kind, mark))
                continue
            for pindex, prop in enumerate(props):
                pointer = f"/changes/{index}/properties/{pindex}"
                before = self.cite(prop.get("before"), result_id, f"{pointer}/before")
                after = self.cite(prop.get("after"), result_id, f"{pointer}/after")
                cells = (self.bdi(section), self.bdi(key), self.bdi(kind), before, after, self.bdi(mark))
                rows.append(el(Tag.TR, *cells))
        rows.extend(self.texts(section, key, "engineer change") for section, key in sorted(marks - seen))
        return rows

    def changes(self) -> Element:
        views = list(self.reader.models())
        blocks: list[Node] = []
        if views:
            rev = [self.texts(s.role, str(s.revision), s.fingerprint, s.file_name) for v in views if (s := v.saved)]
            blocks.append(self.table(rev, "Role", "Revision", "Fingerprint", "File"))
        events = self.reader.events()
        answers = {e.payload.request_id: e.payload for e in events if isinstance(e.payload, ev.ApprovalResolved)}
        for event in events:
            request = event.payload
            if not isinstance(request, ev.ApprovalRequested) or request.kind not in _CHANGE_SET:
                continue
            answer = answers.get(request.request_id)
            resolved = answer if isinstance(answer, ev.ApprovalResolved) else None
            items = [self.texts(item, *self._item(item, resolved)) for item in request.items]
            blocks.append(self.table(items, "Item", "State", "Reason"))
            bound = [self.texts(key, _show(value)) for key, value in request.binding.items()]
            blocks.append(self.table(bound, "Binding", "Value"))
            unexpected: set[tuple[str, str]] = set()
            steps: list[Element] = []
            for started, completed in self.applied(request.request_id):
                steps.append(self.texts(started.name, started.item or ""))
                ref = None if completed is None or completed.result is None else completed.result.ref
                loaded = self.payload_of(ref)
                if loaded is None or self.store.get(loaded[0]).kind != _READBACK:
                    continue
                found, read_rows = self._readback(loaded)
                unexpected |= found
                steps.extend(read_rows)
            blocks.append(self.table(steps, "Step", "Item"))
            preview = self.payload_of(request.preview_ref)
            diff = self.payload_of(None if preview is None else preview[1].get("diff_ref"))
            if diff is not None:
                diff_rows = self.diff_rows(diff[1], diff[0], unexpected)
                blocks.append(self.table(diff_rows, "Section", "Key", "Change", "Before", "After", "Mark"))
        promoted = [view.saved for view in views if view.saved.role == "promoted"]
        if promoted:
            backups = [self.texts(saved.file_name, ", ".join(saved.origin_file_names)) for saved in promoted]
            blocks.append(self.table(backups, "Target", "Backup"))
        return self.section("changes", *blocks)

    def _item(self, item: str, resolved: ev.ApprovalResolved | None) -> tuple[str, str]:
        if resolved is None:
            return "open", ""
        rejected = resolved.decision == "reject" or item in resolved.rejected_items
        state = "rejected" if rejected else "accepted"
        if item in resolved.item_reasons:
            return state, resolved.item_reasons[item]
        if rejected and resolved.reason:
            return state, resolved.reason
        return state, ""

    def _readback(self, loaded: tuple[str, dict[str, JsonValue]]) -> tuple[set[tuple[str, str]], list[Element]]:
        unexpected: set[tuple[str, str]] = set()
        for row in self.dicts(loaded[1].get("unexpected")):
            section = row.get("section")
            if isinstance(section, str):
                unexpected.add((section, self.key(row.get("key"))))
        rows: list[Element] = []
        for index, item in enumerate(self.dicts(loaded[1].get("items"))):
            expected = self.cite(item.get("expected"), loaded[0], f"/items/{index}/expected")
            read = self.cite(item.get("read"), loaded[0], f"/items/{index}/read")
            name = self.bdi(_show(item.get("item_id")))
            result = self.bdi(_show(item.get("result")))
            rows.append(el(Tag.TR, name, result, expected, read))
        return unexpected, rows

    def results(self) -> Element:
        blocks: list[Node] = []
        for entry in self.model.results:
            blocks.append(el(Tag.H3, Text(entry.kind)))
            payload = self.store.payload(entry.result_id)
            external = _REGISTRY.get(entry.kind)
            if external is not None:
                blocks.extend(external(payload, entry.result_id, self.book))
                continue
            name = _OWN.get(entry.kind, "basis" if entry.kind.startswith("basis.") else "generic")
            blocks.extend(getattr(self, name)(payload, entry.result_id))
        return self.section("results", *blocks)

    def _basis_body(self, payload: dict[str, JsonValue], kind: str, pointer: str) -> dict[str, JsonValue] | None:
        parts = pointer[1:].split("/") if pointer.startswith("/") else []
        parts = [part.replace("~1", "/").replace("~0", "~") for part in parts if part]
        fields = payload.get("fields")
        if len(parts) < 2 or parts[0] != "fields" or not isinstance(fields, dict) or not kind.startswith("basis."):
            return None
        body = fields.get(parts[1])
        return body if isinstance(body, dict) else None

    def _meta(self, kind: str, body: dict[str, JsonValue] | None) -> tuple[str, str, str, str, str]:
        if body is None:
            return "", "", "", "", ""
        if kind == "basis.engineer_input/1":
            when = body.get("entered_at")
            entered = format_timestamp(when) if isinstance(when, str) else ""
            return "", "", "", _show(body.get("entered_by")), entered
        return _show(body.get("source")), _show(body.get("citation")), _show(body.get("confirmed")), "", ""

    def sources(self) -> Element:
        rows: list[Element] = []
        for index, source in enumerate(self.book._order, start=1):
            record = self.store.get(source.result_id)
            payload = self.store.payload(source.result_id)
            meta = self._meta(record.kind, self._basis_body(payload, record.kind, source.pointer))
            left = (source.result_id, source.pointer, record.kind, record.producer.tool, record.producer.tool_version)
            right = (format_timestamp(record.created_at), " ".join(record.parents), *meta)
            cells = [self.bdi(cell) for cell in left + right]
            rows.append(el(Tag.TR, *cells, id=SafeToken(f"src-{index}")))
        labels = ["Result", "Pointer", "Kind", "Producer", "Version", "Created", "Parents"]
        labels += ["Source", "Citation", "Confirmed", "Entered by", "Entered at"]
        return self.section("sources", self.table(rows, *labels))

    def decisions(self) -> Element:
        blocks: list[Node] = []
        if self.model.decisions:
            rows = [self._decision(item) for item in self.model.decisions]
            blocks.append(self.table(rows, "Point", "Options", "Choice", "Tier", "Confidence"))
        if self.model.requests:
            rows = [self._request(item) for item in self.model.requests]
            blocks.append(self.table(rows, "Request", "Kind", "Decision", "Who", "When", "Reasons"))
        if self.model.escalations:
            rows = [self.texts(item.reason, item.detail, item.at) for item in self.model.escalations]
            blocks.append(self.table(rows, "Reason", "Detail", "When"))
        if self.model.reconciliations:
            rows = [self._reconciled(item) for item in self.model.reconciliations]
            blocks.append(self.table(rows, "Path", "Operation", "Outcome", "Who", "When"))
        return self.section("decisions", *blocks)

    def _decision(self, item: DecisionEntry) -> Element:
        confidence = "" if item.confidence is None else format_number(item.confidence)
        options = ", ".join(_show(option) for option in item.options)
        return self.texts(item.point, options, _show(item.choice), item.decided_by, confidence)

    def _request(self, item: RequestEntry) -> Element:
        who = (item.request_id, item.kind, item.outcome or "", item.by or "")
        return self.texts(*who, item.answered_at or "", "; ".join(item.reasons))

    def _reconciled(self, item: ReconciliationEntry) -> Element:
        return self.texts(item.path or "", item.op_id, item.outcome, item.decided_by, item.at)
