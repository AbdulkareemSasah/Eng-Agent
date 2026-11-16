"""Edit-cycle renderers, value sources and the timings section (plan 0007 T10; spec 0007 AC32, spec 0006 AC52)."""

import json
import re
from pathlib import Path

from eng_contract.ids import FixedClock, IdSource
from eng_contract.store import ResultStore
from fixtures.report_run import build_report_run
from unit.edit_cycle.test_timings import PRODUCER, write_cycles

from eng_harness import __version__
from eng_harness._text import format_duration_ms
from eng_harness.journal import JournalReader
from eng_harness.report import ReleaseMarks, build_report

_DATA = Path(__file__).resolve().parents[2] / "data" / "kinds" / "edit_cycle"
_CELL = re.compile(r'<td class="v"><a href="#(src-\d+)">(.*?)</a></td>')


def _resolve(payload: object, pointer: str) -> object:
    for token in pointer.split("/")[1:]:
        key = token.replace("~1", "/").replace("~0", "~")
        payload = payload[int(key)] if isinstance(payload, list) else payload[key]  # type: ignore[index]
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


def test_report_adds_the_cycle_timings(run_dir: Path, store: ResultStore, ids: IdSource, clock: FixedClock) -> None:
    """The timings section gains the cycle tables only when the journal holds edit-cycle steps (spec 0007 4.9)."""
    reader = write_cycles(run_dir, store, ids)
    html = build_report(reader, store, ReleaseMarks(records={}), clock, __version__)
    assert "Edit cycles" in html
    assert format_duration_ms(120_000) in html
    assert "R1" in html
    plain = tmp_run = run_dir.parent / "plain"
    plain.mkdir()
    build_report_run(plain, store, ids)
    assert "Edit cycles" not in build_report(
        JournalReader(tmp_run), store, ReleaseMarks(records={}), clock, __version__
    )


def test_cycle_timings_file(run_dir: Path, store: ResultStore, ids: IdSource, tmp_path: Path) -> None:
    """`report/cycle-timings.json` holds the measures for the B-1 sheet and no file path."""
    from eng_harness.report._edit_cycle import edit_cycle_timings
    from eng_harness.report._write import write_cycle_timings

    timings = edit_cycle_timings(write_cycles(run_dir, store, ids), store)
    target = tmp_path / "report" / "cycle-timings.json"
    write_cycle_timings(timings, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert [c["wall_ms"] for c in data["cycles"]] == [120_000, 69_000]
    assert data["benchmarks"] == [{"label": "R1", "elapsed_ms": 177_000, "cycles": 2}]
    assert [t["wait_ms"] for t in data["turns"]] == [30_000, 10_000]
    assert data["cycles"][0]["prompts"] == 1
    assert str(tmp_path) not in target.read_text(encoding="utf-8")
