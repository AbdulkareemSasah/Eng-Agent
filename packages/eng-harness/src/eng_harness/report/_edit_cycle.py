"""Edit-cycle report support (spec 0007 section 4.9, AC25, AC32).

Purpose: renderers for the edit-cycle kinds (every value cell is a stored value with its source) and the A3 audit of
write arguments (`audit_value_sources`). Both are pure functions of the journal and the store; a renderer computes
nothing. Units: as the stored values carry them.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from eng_contract.errors import ContractError
from eng_contract.refs import parse_ref
from eng_contract.store import ResultStore
from pydantic import JsonValue

from eng_harness._html import Element, Node, Tag, el
from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev
from eng_harness.report._sections import SourceBook, _Page, _show, register_renderer

_BASIS = frozenset({"basis.design_basis/1", "basis.engineer_input/1"})


@dataclass(frozen=True)
class SourceFinding:
    """A write step argument at an engineering parameter that is not a reference to a basis record."""

    path: str
    tool: str
    argument: str


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


def _row(page: _Page, rid: str, obj: Mapping[str, JsonValue], base: str, *columns: str) -> Element:
    """A table row: `key` is shown as text, `*key` as a value cell citing `base/key` of the stored result."""
    cells = [
        page.cite(_text(obj.get(c[1:])), rid, f"{base}/{c[1:]}") if c[0] == "*" else page.bdi(_show(obj.get(c)))
        for c in columns
    ]
    return el(Tag.TR, *cells)


def _text(value: JsonValue) -> str:
    return ", ".join(_show(item) for item in value) if isinstance(value, list) else _show(value)


def _change_set_check(payload: dict[str, JsonValue], rid: str, book: SourceBook) -> list[Node]:
    page = _page(book)
    items, values, issues = [], [], []
    for i, item in enumerate(page.dicts(payload.get("resolved"))):
        items.append(_row(page, rid, item, f"/resolved/{i}", "item_id", "kind", "*targets"))
        for j, value in enumerate(page.dicts(item.get("values"))):
            held = {**value, "item": item.get("item_id")}
            values.append(_row(page, rid, held, f"/resolved/{i}/values/{j}", "item", "pointer", "*ref", "unit"))
    for i, issue in enumerate(page.dicts(payload.get("issues"))):
        issues.append(_row(page, rid, issue, f"/issues/{i}", "item_id", "severity", "code", "*detail", "gap"))
    return [
        page.table([_row(page, rid, payload, "", "*status", "*complete")], "Status", "Complete"),
        page.table(items, "Item", "Kind", "Targets"),
        page.table(values, "Item", "Pointer", "Reference", "Unit"),
        page.table(issues, "Item", "Severity", "Code", "Detail", "Gap"),
    ]


def _analysis_summary(payload: dict[str, JsonValue], rid: str, book: SourceBook) -> list[Node]:
    page, counts, drift = _page(book), payload.get("counts"), payload.get("governing_drift")
    governing = [
        _row(
            page,
            rid,
            {**row, "direction": key},
            f"/governing_drift/{page.token(key)}",
            "direction",
            "story",
            "case",
            "*ratio",
        )
        for key, row in (drift.items() if isinstance(drift, dict) else [])
        if isinstance(row, dict)
    ]
    exceeding = [
        _row(page, rid, row, f"/exceeding/{i}", "direction", "story", "case", "*ratio")
        for i, row in enumerate(page.dicts(payload.get("exceeding")))
    ]
    head = _row(page, rid, payload, "", "*status", "*limit_ratio", "*limit_ref")
    tally = _row(
        page, rid, counts if isinstance(counts, dict) else {}, "/counts", "*error", "*warning", "*info", "*unclassified"
    )
    return [
        page.table([head], "Status", "Limit ratio", "Limit source"),
        page.table([tally], "Errors", "Warnings", "Info", "Unclassified"),
        page.table(governing, "Direction", "Story", "Case", "Ratio"),
        page.table(exceeding, "Direction", "Story", "Case", "Ratio"),
    ]


def _name_lists(payload: dict[str, JsonValue], rid: str, book: SourceBook) -> list[Node]:
    page = _page(book)
    rows = [el(Tag.TR, page.bdi(name), _row(page, rid, payload, "", f"*{name}")) for name in sorted(payload)]
    return [page.table(rows, "List", "Names")]


def register() -> None:
    """Register the renderers of the edit-cycle kinds (called lazily by `_sections`, spec 0007 4.9)."""
    register_renderer("harness.change_set_check/1", _change_set_check)
    register_renderer("harness.analysis_summary/1", _analysis_summary)
    register_renderer("harness.csi_name_lists/1", _name_lists)
