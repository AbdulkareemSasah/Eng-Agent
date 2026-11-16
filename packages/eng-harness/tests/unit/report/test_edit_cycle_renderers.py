"""Edit-cycle renderers, value sources and the timings section (plan 0007 T10; spec 0007 AC32, spec 0006 AC52)."""

import json
import re
from pathlib import Path
from typing import Any

from eng_contract.envelope import Provenance
from eng_contract.store import ResultStore

PRODUCER = Provenance(tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0)
_DATA = Path(__file__).resolve().parents[2] / "data" / "kinds" / "edit_cycle"
_CELL = re.compile(r'<td class="v"><a href="#(src-\d+)">(.*?)</a></td>')


def _resolve(payload: Any, pointer: str) -> Any:
    for token in pointer.split("/")[1:]:
        key = token.replace("~1", "/").replace("~0", "~")
        payload = payload[int(key)] if isinstance(payload, list) else payload[key]
    return payload


def _shown(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return "true" if value is True else "false" if value is False else str(value)


def test_renderers_and_sources(store: ResultStore) -> None:
    """AC32: each kind renders through its registered renderer; every value cell is the stored value at its source."""
    from eng_harness.report._sections import SourceBook, _registry

    book, html = SourceBook(), ""
    for name in ("change_set_check", "analysis_summary", "csi_name_lists"):
        payload = json.loads((_DATA / f"{name}.json").read_text(encoding="utf-8"))
        stored = store.put(f"harness.{name}/1", payload, PRODUCER)
        nodes = _registry()[f"harness.{name}/1"](store.payload(stored.result_id), stored.result_id, book)
        html += "".join(node.render() for node in nodes)
    cells = dict(_CELL.findall(html)[::-1])
    assert len(_CELL.findall(html)) == html.count('<td class="v">') > 15
    pointers = [source.pointer for source in book._order]
    for number, source in enumerate(book._order, start=1):
        value = _resolve(store.payload(source.result_id), source.pointer)
        assert re.sub(r"<[^>]+>", "", cells[f"src-{number}"]) == _shown(value), source.pointer
    for pointer in (
        "/status", "/complete", "/issues/0/detail", "/resolved/1/targets", "/resolved/1/values/0/ref",
        "/counts/warning", "/limit_ratio", "/limit_ref", "/governing_drift/X/ratio", "/exceeding/0/ratio",
        "/frame_sections", "/combinations",
    ):  # fmt: skip
        assert pointer in pointers
    for text in ("CONFLICTS_WITH_ENGINEER_CHANGE", "W20", "EQX", "S3", "Slab200"):
        assert text in html
