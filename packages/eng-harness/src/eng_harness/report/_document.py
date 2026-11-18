"""Run report document: status, timings, run events, marks (spec 0006 sections 4.6.1 to 4.6.2)."""

from eng_contract import CONTRACT_VERSION
from eng_contract.ids import Clock
from eng_contract.refs import parse_ref
from eng_contract.store import ResultStore

from eng_harness._html import Element, Node, SafeToken, Tag, Text, document, el, trusted
from eng_harness._text import format_duration_ms, format_timestamp, truncate
from eng_harness.journal import Event, JournalReader
from eng_harness.journal import _events as ev
from eng_harness.pages._css import STYLESHEET
from eng_harness.report._edit_cycle import cycle_timing_nodes, edit_cycle_timings
from eng_harness.report._lineage import ReleaseMarks, ReportError, ResultMark, unreleased_dependencies
from eng_harness.report._model import ReportModel, fold_report
from eng_harness.report._sections import SourceBook, _Page

_TERMINAL = frozenset({"COMPLETED", "FAILED"})


def build_report(
    reader: JournalReader,
    store: ResultStore,
    marks: ReleaseMarks,
    clock: Clock,
    version: str,
) -> str:
    """Build one self-contained HTML report from the journal and store only (spec 0006 section 4.6)."""
    _ = clock
    model = fold_report(reader, store)
    events = reader.events()
    last_seq = events[-1].seq if events else 0
    signed = next((event for event in events if isinstance(event.payload, ev.SignedOff)), None)
    marked = unreleased_dependencies(reader, store, marks)
    title = (
        Text(f"DRAFT — Run report: {model.run.run_id}") if signed is None else Text(f"Run report: {model.run.run_id}")
    )
    parts: list[Node] = [
        _banner(model, signed, marked, last_seq),
        _status(model, reader, store, version),
        *_section_nodes(model, reader, store),
        _timings(model, reader, store),
        _run_events(model),
    ]
    return document(title, parts, STYLESHEET)


def _section_nodes(model: ReportModel, reader: JournalReader, store: ResultStore) -> list[Element]:
    page = _Page(SourceBook(), model, reader, store)
    return [page.changes(), page.results(), page.sources(), page.decisions()]


def _banner(model: ReportModel, signed: Event | None, marked: dict[str, ResultMark], last_seq: int) -> Element:
    lines = _mark_lines(model, marked, last_seq)
    if signed is None:
        return el(Tag.DIV, *(el(Tag.P, Text(line)) for line in lines), class_=SafeToken("draft"))
    payload = signed.payload
    if not isinstance(payload, ev.SignedOff):
        raise ReportError("signed_off event has an invalid payload")
    signed_line = f"Signed by {payload.by} at {format_timestamp(signed.at)}"
    mark_rows = [el(Tag.P, Text(line)) for line in lines]
    return el(Tag.DIV, el(Tag.P, Text(signed_line), class_=SafeToken("banner")), *mark_rows)


def _mark_lines(model: ReportModel, marked: dict[str, ResultMark], last_seq: int) -> list[str]:
    lines: list[str] = []
    if model.run.status not in _TERMINAL:
        extra = f"; run in progress as of seq {last_seq}" if model.run.status == "RUNNING" else ""
        lines.append(f"INCOMPLETE: {model.run.status}{extra}")
    if model.run.draft:
        lines.append("DRAFT SOURCES")
    if model.run.run_class == "trial":
        lines.append("Trial run")
    if marked:
        lines.append(f"Unreleased tools: {len(marked)} result(s)")
    return lines


def _status(model: ReportModel, reader: JournalReader, store: ResultStore, version: str) -> Element:
    header = reader.header()
    block = header.block
    rows = [
        _row("Run", model.run.run_id),
        _row("Workflow", model.run.workflow),
        _row("Block", f"{block.name}@{block.version}"),
        _row("Code hash", block.code_sha256[:16] + "…"),
        _row("Mode", model.run.mode),
        _row("Engine", header.engine_version),
        _row("Contract", CONTRACT_VERSION),
        _row("Package", version),
        _row("Started", format_timestamp(model.run.started_at)),
        _row("Ended", format_timestamp(model.run.ended_at) if model.run.ended_at else ""),
        _row("Status", model.run.status),
        _row("Integrity", f"{model.event_count} events; chain {model.chain_sha256}"),
        *(_row(label, value) for label, value in _basis_rows(store, header.basis_ref)),
        *(_row(label, value) for label, value in _runtime_rows(model, reader, store)),
    ]
    return el(
        Tag.SECTION,
        el(Tag.H2, trusted("Status")),
        el(Tag.TABLE, el(Tag.TBODY, *rows)),
        id=SafeToken("status"),
    )


def _row(label: str, value: str) -> Element:
    return el(
        Tag.TR, el(Tag.TH, Text(label)), el(Tag.TD, el(Tag.BDI, Text(truncate(value, 500)), dir=SafeToken("auto")))
    )


def _basis_rows(store: ResultStore, basis_ref: str) -> list[tuple[str, str]]:
    result_id = parse_ref(basis_ref)[0]
    payload = store.payload(result_id)
    template = payload.get("template")
    if not isinstance(template, dict):
        return []
    name, ver = template.get("name", ""), template.get("version", "")
    digest = str(template.get("sha256", ""))[:16]
    rows = [("Template", f"{name}@{ver} ({digest}…)")]
    fields = payload.get("fields")
    if isinstance(fields, dict):
        for key, body in fields.items():
            if isinstance(body, dict):
                rows.append((f"Basis {key}", f"{body.get('source', '')} (confirmed={body.get('confirmed')})"))
    return rows


def _runtime_rows(model: ReportModel, reader: JournalReader, store: ResultStore) -> list[tuple[str, str]]:
    """The run header's decision runtime as label and value rows, under the caps of the generic renderer (4.6.1)."""
    found: list[tuple[str, str]] = []
    omitted = _Page(SourceBook(), model, reader, store).walk(dict(model.run.decision_runtime), "", 0, found)
    rows = [(f"Decision runtime {pointer}", text) for pointer, text in found]
    return [*rows, ("Decision runtime", f"{omitted} more")] if omitted else rows


def _timings(model: ReportModel, reader: JournalReader, store: ResultStore) -> Element:
    steps = [
        el(
            Tag.TR,
            *(
                el(Tag.TD, el(Tag.BDI, Text(truncate(text, 500)), dir=SafeToken("auto")))
                for text in (
                    step.path,
                    step.name,
                    format_timestamp(step.started_at),
                    "" if step.duration_ms is None else format_duration_ms(step.duration_ms),
                )
            ),
        )
        for step in model.timings.steps
    ]
    summary = _row(
        "Summary",
        f"Engineer waiting {format_duration_ms(model.timings.waiting_ms)}; "
        f"machine {format_duration_ms(model.timings.machine_ms)}; resumes {model.timings.resumes}",
    )
    head = el(Tag.TR, *(el(Tag.TH, Text(label)) for label in ("Path", "Name", "Started", "Duration")))
    cycles = edit_cycle_timings(reader, store)
    return el(
        Tag.SECTION,
        el(Tag.H2, trusted("Timings")),
        el(Tag.TABLE, el(Tag.THEAD, head), el(Tag.TBODY, *steps, summary)),
        *(cycle_timing_nodes(cycles) if cycles.cycles else []),
        id=SafeToken("timings"),
    )


def _run_events(model: ReportModel) -> Element:
    blocks: list[Node] = []
    if model.resumes:
        rows = [
            el(Tag.TR, *(el(Tag.TD, Text(str(value))) for value in (item.resume_no, item.at, item.code_hash_changed)))
            for item in model.resumes
        ]
        head = el(Tag.TR, *(el(Tag.TH, Text(label)) for label in ("Resume", "At", "Code hash changed")))
        blocks += [el(Tag.H3, Text("Resumes")), el(Tag.TABLE, el(Tag.THEAD, head), el(Tag.TBODY, *rows))]
    if model.hosts:
        rows = [
            el(
                Tag.TR,
                *(
                    el(Tag.TD, Text(str(value)))
                    for value in (
                        host.host_key,
                        host.instance_id,
                        host.program,
                        host.at,
                        host.open,
                    )
                ),
            )
            for host in model.hosts
        ]
        head = el(Tag.TR, *(el(Tag.TH, Text(label)) for label in ("Host", "Instance", "Program", "Started", "Open")))
        blocks += [el(Tag.H3, Text("Host instances")), el(Tag.TABLE, el(Tag.THEAD, head), el(Tag.TBODY, *rows))]
    return el(Tag.SECTION, el(Tag.H2, trusted("Run events")), *blocks, id=SafeToken("run-events"))
