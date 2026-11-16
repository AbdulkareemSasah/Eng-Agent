"""Edit-cycle report support (spec 0007 section 4.9, AC25, AC26, AC29, AC32).

Purpose: renderers for the edit-cycle kinds (every value cell is a stored value with its source), the A3 audit of write
arguments (`audit_value_sources`), the A7 prompt counter (`count_prompts`) and the B-1 cycle timings
(`edit_cycle_timings`, its section and its JSON). All are pure functions of the journal and the store.
Units: milliseconds. Errors: `ReportError` when an answer is dated before its request.
"""

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace

from eng_contract.errors import ContractError
from eng_contract.refs import parse_ref
from eng_contract.store import ResultStore
from pydantic import JsonValue

from eng_harness._html import Node, Tag, Text, el
from eng_harness._text import format_duration_ms
from eng_harness.journal import Event, JournalReader
from eng_harness.journal import _events as ev
from eng_harness.report._lineage import ReportError
from eng_harness.report._model import wait_time_ms
from eng_harness.report._sections import SourceBook, _Page, _show, register_renderer

CYCLE_BLOCK = "edit_cycle_once"
"""The child block that runs one cycle (spec 0007 section 4.1)."""
TURN_POINT = "edit_cycle_engineer_turn"
"""The decision point of the engineer turn (spec 0007 section 4.6, D-6)."""
_OWN = frozenset({"CHANGE_SET", "block"})  # a cycle's own first approval and change-set request (spec 0007 4.9)
_CHANGE_SET = frozenset({"change_set", "CHANGE_SET"})
_SCOPES = frozenset({"block", "parallel", "attempts"})  # their duration holds their children's
_ENGINEER_STEPS = frozenset({"ask", "approve", "decide", "decide_many"})  # their duration may hold the engineer's wait
_BASIS = frozenset({"basis.design_basis/1", "basis.engineer_input/1"})


@dataclass(frozen=True)
class SourceFinding:
    """A write step argument at an engineering parameter that is not a reference to a basis record."""

    path: str
    tool: str
    argument: str


@dataclass(frozen=True)
class CountedRequest:
    """One engineer request that counts towards A7."""

    kind: str
    title: str


@dataclass(frozen=True)
class PromptCount:
    """The counted requests of one cycle."""

    cycle: int
    requests: tuple[CountedRequest, ...]

    @property
    def count(self) -> int:
        """Number of counted requests."""
        return len(self.requests)


@dataclass(frozen=True)
class StepTime:
    """A step of a cycle: kind, name and the duration the journal recorded (None while running)."""

    path: str
    kind: str
    name: str
    duration_ms: int | None


@dataclass(frozen=True)
class CycleTime:
    """Wall, machine, host and engineer-wait time of one cycle, and its prompt count."""

    cycle: int
    path: str
    wall_ms: int | None
    machine_ms: int
    host_ms: int
    wait_ms: int
    prompts: int


@dataclass(frozen=True)
class TurnWait:
    """The wait from the engineer-turn request to its answer."""

    cycle: int
    wait_ms: int


@dataclass(frozen=True)
class BenchmarkTime:
    """From the first change-set request of a `benchmark_request` to its `accept`; None while not accepted."""

    label: str
    elapsed_ms: int | None
    cycles: int


@dataclass(frozen=True)
class CycleTimings:
    """The B-1 measures (spec 0007 section 4.9)."""

    steps: tuple[StepTime, ...]
    cycles: tuple[CycleTime, ...]
    turns: tuple[TurnWait, ...]
    benchmarks: tuple[BenchmarkTime, ...]


@dataclass(frozen=True)
class _Cycle:
    path: str
    first: int
    began: str
    last: int | None = None
    ended: str | None = None


@dataclass(frozen=True)
class _Request:
    seq: int
    cycle: int | None
    request_id: str
    kind: str
    title: str
    at: str
    answered_at: str | None
    by: str | None
    point: str | None


def _ms(began: str, ended: str) -> int:
    try:
        return wait_time_ms(began, ended)
    except ValueError as error:
        raise ReportError(str(error)) from error


def _cycles(events: list[Event]) -> list[_Cycle]:
    """The cycle blocks in order of first start: a cycle holds the events from its start to its last end."""
    found: dict[str, _Cycle] = {}
    for e in events:
        if e.path is None:
            continue
        if (
            isinstance(e.payload, ev.StepStarted)
            and e.payload.child is not None
            and e.payload.child.name == CYCLE_BLOCK
        ):
            found.setdefault(e.path, _Cycle(e.path, e.seq, e.at))
        elif isinstance(e.payload, ev.StepCompleted | ev.StepFailed) and e.path in found:
            found[e.path] = replace(found[e.path], last=e.seq, ended=e.at)
    return list(found.values())


def _cycle_of(cycles: list[_Cycle], seq: int) -> int | None:
    return next((i for i, c in enumerate(cycles, 1) if c.first <= seq and (c.last is None or seq <= c.last)), None)


def _requests(events: list[Event], cycles: list[_Cycle]) -> list[_Request]:
    answers: dict[str, tuple[Event, str, str | None]] = {}
    for e in events:
        p = e.payload
        if isinstance(p, ev.ApprovalResolved | ev.InputProvided):
            answers.setdefault(p.request_id, (e, p.by, None))
        elif isinstance(p, ev.DecisionMade) and p.request_id is not None:
            answers.setdefault(p.request_id, (e, p.decided_by, p.point))
    found: list[_Request] = []
    for e in events:
        p = e.payload
        if isinstance(p, ev.ApprovalRequested | ev.InputRequested):
            got = answers.get(p.request_id)
            done, by, point = got if got else (None, None, None)
            found.append(
                _Request(e.seq, _cycle_of(cycles, e.seq), p.request_id, p.kind, p.title, e.at,
                         done.at if done else None, by, point)
            )  # fmt: skip
    return found


def _prompts(requests: list[_Request], cycles: int) -> tuple[PromptCount, ...]:
    """A7 (spec 0007 4.9): the first change-set approval and request of a cycle, its engineer turn and the requests a
    mode answered are the cycle's own; an engine decision still open cannot be told from the turn and is not counted."""
    seen: set[tuple[int, str]] = set()
    counted: dict[int, list[CountedRequest]] = {i: [] for i in range(1, cycles + 1)}
    for r in requests:
        if r.cycle is None:
            continue
        key = (r.cycle, "CHANGE_SET" if r.kind in _CHANGE_SET else r.kind)
        first = key[1] in _OWN and key not in seen
        seen.add(key)
        own = (
            r.by is None or r.point == TURN_POINT
            if r.kind == "engine.decision"
            else first or str(r.by).startswith("mode:")
        )
        if not own:
            counted[r.cycle].append(CountedRequest(r.kind, r.title))
    return tuple(PromptCount(cycle, tuple(items)) for cycle, items in counted.items())


def count_prompts(reader: JournalReader) -> tuple[PromptCount, ...]:
    """The engineer requests that count towards A7, per cycle (spec 0007 section 4.9, AC26)."""
    events = reader.events()
    cycles = _cycles(events)
    return _prompts(_requests(events, cycles), len(cycles))


def _inside(path: str, scope: str) -> bool:
    return path == scope or path.startswith(f"{scope}/")


def _benchmarks(
    events: list[Event], requests: list[_Request], cycles: list[_Cycle], store: ResultStore | None
) -> tuple[BenchmarkTime, ...]:
    if store is None:
        return ()
    provided = {e.payload.request_id: e.payload.answer_ref for e in events if isinstance(e.payload, ev.InputProvided)}
    started: dict[str, _Request] = {}
    for r in requests:
        ref = provided.get(r.request_id)
        if r.kind != "block" or ref is None or r.cycle is None:
            continue
        fields = store.payload(parse_ref(ref)[0]).get("fields")
        body = fields.get("benchmark_request") if isinstance(fields, dict) else None
        label = body.get("value") if isinstance(body, dict) else None
        if isinstance(label, str):
            started.setdefault(label, r)
    accepts = [
        (e.seq, e.at, _cycle_of(cycles, e.seq))
        for e in events
        if isinstance(e.payload, ev.DecisionMade) and e.payload.point == TURN_POINT and e.payload.choice == "accept"
    ]
    found: list[BenchmarkTime] = []
    for label, r in started.items():
        end = next(((at, cycle) for seq, at, cycle in accepts if seq > r.seq), None)
        last = (end[1] if end else None) or len(cycles)
        found.append(BenchmarkTime(label, _ms(r.at, end[0]) if end else None, last - (r.cycle or 0) + 1))
    return tuple(found)


def edit_cycle_timings(reader: JournalReader, store: ResultStore | None = None) -> CycleTimings:
    """The B-1 measures of the journal (spec 0007 section 4.9, AC29).

    Machine time is the duration of the completed steps of a cycle that are neither scopes (their duration holds their
    children's) nor engineer steps (a decision's duration holds the engineer's wait); host time is its tool steps;
    engineer wait is the sum of its answered requests' waits. `store` is needed only to read the `benchmark_request`
    labels of the change-set answers; without it `benchmarks` is empty.

    Raises:
        ReportError: an answer is dated before its request, or a cycle ends before it starts.
    """
    events = reader.events()
    cycles = _cycles(events)
    requests = _requests(events, cycles)
    prompts = _prompts(requests, len(cycles))
    views = [(i, view) for view in reader.steps() for i, c in enumerate(cycles, 1) if _inside(view.path, c.path)]
    waits = [(r.cycle, _ms(r.at, r.answered_at)) for r in requests if r.answered_at is not None]

    def measured(number: int, cycle: _Cycle) -> CycleTime:
        done = [v for i, v in views if i == number and v.status == "completed"]
        machine = sum(v.duration_ms or 0 for v in done if v.kind not in _SCOPES | _ENGINEER_STEPS)
        host = sum(v.duration_ms or 0 for v in done if v.kind == "tool")
        wall = None if cycle.ended is None else _ms(cycle.began, cycle.ended)
        wait = sum(ms for owner, ms in waits if owner == number)
        return CycleTime(number, cycle.path, wall, machine, host, wait, prompts[number - 1].count)

    turns = tuple(
        TurnWait(r.cycle, _ms(r.at, r.answered_at))
        for r in requests
        if r.cycle is not None and r.answered_at is not None and r.point == TURN_POINT
    )
    steps = tuple(StepTime(v.path, v.kind, v.name, v.duration_ms) for _, v in views)
    found = tuple(measured(number, cycle) for number, cycle in enumerate(cycles, 1))
    return CycleTimings(steps, found, turns, _benchmarks(events, requests, cycles, store))


def _unsourced(value: JsonValue, store: ResultStore) -> bool:
    if value is None:
        return False
    if isinstance(value, dict) and set(value) == {"$ref"}:
        ref = value["$ref"]
        try:
            return not isinstance(ref, str) or store.get(parse_ref(ref)[0]).kind not in _BASIS
        except ContractError:
            return True
    if isinstance(value, dict | list):
        return any(_unsourced(item, store) for item in (value.values() if isinstance(value, dict) else value))
    return True


def audit_value_sources(
    reader: JournalReader, store: ResultStore, engineering_params: Mapping[str, frozenset[str]]
) -> list[SourceFinding]:
    """Every write tool step argument at an engineering parameter that is not a reference to `basis.design_basis/1`
    or `basis.engineer_input/1` (spec 0007 section 4.9, AC25). `engineering_params` maps a tool name to its parameter
    names; the journal does not record them."""
    found: list[SourceFinding] = []
    for e in reader.events():
        p = e.payload
        if not isinstance(p, ev.StepStarted) or p.kind != "tool" or p.effect != "write" or e.path is None:
            continue
        args = p.args if p.args is not None else store.payload(p.args_ref or "")["value"]
        names = engineering_params.get(p.name, frozenset())
        if isinstance(args, dict):
            found += [
                SourceFinding(e.path, p.name, n) for n in sorted(names) if n in args and _unsourced(args[n], store)
            ]
    return found


def _page(book: SourceBook) -> _Page:
    page = _Page.__new__(_Page)
    page.book = book
    return page


def _text(value: JsonValue) -> str:
    return ", ".join(_show(item) for item in value) if isinstance(value, list) else _show(value)


def _change_set_check(payload: dict[str, JsonValue], result_id: str, book: SourceBook) -> list[Node]:
    page = _page(book)
    head = el(
        Tag.TR,
        page.cite(payload.get("status"), result_id, "/status"),
        page.cite(payload.get("complete"), result_id, "/complete"),
    )
    items, values = [], []
    for i, item in enumerate(page.dicts(payload.get("resolved"))):
        name = _show(item.get("item_id"))
        targets = page.cite(_text(item.get("targets")), result_id, f"/resolved/{i}/targets")
        items.append(el(Tag.TR, page.bdi(name), page.bdi(_show(item.get("kind"))), targets))
        for j, value in enumerate(page.dicts(item.get("values"))):
            ref = page.cite(value.get("ref"), result_id, f"/resolved/{i}/values/{j}/ref")
            values.append(
                el(
                    Tag.TR,
                    page.bdi(name),
                    page.bdi(_show(value.get("pointer"))),
                    ref,
                    page.bdi(_show(value.get("unit"))),
                )
            )
    issues = []
    for i, issue in enumerate(page.dicts(payload.get("issues"))):
        detail = page.cite(issue.get("detail"), result_id, f"/issues/{i}/detail")
        cells = [page.bdi(_show(issue.get(key))) for key in ("item_id", "severity", "code")]
        issues.append(el(Tag.TR, *cells, detail, page.bdi(_show(issue.get("gap")))))
    return [
        page.table([head], "Status", "Complete"),
        page.table(items, "Item", "Kind", "Targets"),
        page.table(values, "Item", "Pointer", "Reference", "Unit"),
        page.table(issues, "Item", "Severity", "Code", "Detail", "Gap"),
    ]


def _analysis_summary(payload: dict[str, JsonValue], result_id: str, book: SourceBook) -> list[Node]:
    page = _page(book)
    counts = [page.cite(payload.get("status"), result_id, "/status")]
    counts += [
        page.cite(_text(_count(payload, key)), result_id, f"/counts/{key}")
        for key in ("error", "warning", "info", "unclassified")
    ]
    limit = el(
        Tag.TR,
        page.cite(payload.get("limit_ratio"), result_id, "/limit_ratio"),
        page.cite(payload.get("limit_ref"), result_id, "/limit_ref"),
    )
    drift = payload.get("governing_drift")
    governing = []
    for direction, row in drift.items() if isinstance(drift, dict) else []:
        if isinstance(row, dict):
            ratio = page.cite(row.get("ratio"), result_id, f"/governing_drift/{page.token(direction)}/ratio")
            governing.append(
                el(
                    Tag.TR,
                    page.bdi(direction),
                    page.bdi(_show(row.get("story"))),
                    page.bdi(_show(row.get("case"))),
                    ratio,
                )
            )
    exceeding = []
    for i, row in enumerate(page.dicts(payload.get("exceeding"))):
        ratio = page.cite(row.get("ratio"), result_id, f"/exceeding/{i}/ratio")
        exceeding.append(el(Tag.TR, *(page.bdi(_show(row.get(key))) for key in ("direction", "story", "case")), ratio))
    return [
        page.table([el(Tag.TR, *counts)], "Status", "Errors", "Warnings", "Info", "Unclassified"),
        page.table([limit], "Limit ratio", "Limit source"),
        page.table(governing, "Direction", "Story", "Case", "Ratio"),
        page.table(exceeding, "Direction", "Story", "Case", "Ratio"),
    ]


def _count(payload: dict[str, JsonValue], key: str) -> JsonValue:
    counts = payload.get("counts")
    return counts.get(key) if isinstance(counts, dict) else None


def _name_lists(payload: dict[str, JsonValue], result_id: str, book: SourceBook) -> list[Node]:
    page = _page(book)
    rows = [
        el(Tag.TR, page.bdi(name), page.cite(_text(payload.get(name)), result_id, f"/{name}"))
        for name in sorted(payload)
    ]
    return [page.table(rows, "List", "Names")]


def register() -> None:
    """Register the renderers of the edit-cycle kinds (called lazily by `_sections`, spec 0007 4.9)."""
    register_renderer("harness.change_set_check/1", _change_set_check)
    register_renderer("harness.analysis_summary/1", _analysis_summary)
    register_renderer("harness.csi_name_lists/1", _name_lists)


def cycle_timing_nodes(timings: CycleTimings) -> list[Node]:
    """The cycle tables of the report's timings section."""
    page, show = _page(SourceBook()), format_duration_ms
    cycles = [
        page.texts(
            str(c.cycle), c.path, "" if c.wall_ms is None else show(c.wall_ms), show(c.machine_ms), show(c.host_ms),
            show(c.wait_ms), str(c.prompts),
        )
        for c in timings.cycles
    ]  # fmt: skip
    nodes: list[Node] = [el(Tag.H3, Text("Edit cycles"))]
    nodes.append(page.table(cycles, "Cycle", "Path", "Wall", "Machine", "Host", "Engineer wait", "Prompts"))
    if timings.turns:
        turns = [page.texts(str(t.cycle), show(t.wait_ms)) for t in timings.turns]
        nodes += [el(Tag.H3, Text("Engineer turns")), page.table(turns, "Cycle", "Wait")]
    if timings.benchmarks:
        rows = [
            page.texts(b.label, "" if b.elapsed_ms is None else show(b.elapsed_ms), str(b.cycles))
            for b in timings.benchmarks
        ]
        nodes += [el(Tag.H3, Text("Benchmark requests")), page.table(rows, "Request", "Elapsed", "Cycles")]
    return nodes


def cycle_timings_json(timings: CycleTimings) -> str:
    """The text of `report/cycle-timings.json` for the owner's B-1 sheet: step paths, kinds, names and milliseconds."""
    return json.dumps(asdict(timings), indent=2, sort_keys=True) + "\n"
