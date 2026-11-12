"""Every value cell links to a sources row (plan 0006 T12; spec 0006 AC52)."""

import re
from pathlib import Path
from typing import cast

import pytest
from eng_contract.ids import SeededIdSource
from eng_contract.store import ResultStore
from golden.test_report import load_sections_run
from pydantic import JsonValue

_CELL = re.compile(r'<td class="v"><a href="(#src-\d+)">(.*?)</a></td>')
_ROW = re.compile(r'<tr id="(src-\d+)">(.*?)</tr>')


def _text(markup: str) -> str:
    return re.sub(r"<[^>]+>", "", markup)


def test_every_value_has_source(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    """AC52: each value cell links to a sources row, and basis and engineer rows carry their provenance."""
    from eng_harness.report._sections import render_sections

    run = load_sections_run(run_dir, store, ids)
    try:
        html = render_sections(run.model, run.reader, store)
    finally:
        run.close()
    cells = _CELL.findall(html)
    rows = dict(_ROW.findall(html))
    assert cells, "the report has no value cell"
    assert len(_CELL.findall(html)) == html.count('<td class="v">')
    for href, _inner in cells:
        assert href.startswith("#src-")
        assert href[1:] in rows
    linked = [(_text(inner), _text(rows[href[1:]])) for href, inner in cells]
    basis = [row for text, row in linked if "0.02" in text]
    assert any(
        "template:office_rc@1" in row and "ASCE 7-16 Table 12.12-1" in row and "basis.design_basis/1" in row
        for row in basis
    )
    assert any("true" in row for row in basis)
    engineer = [row for text, row in linked if "40 mm" in text]
    assert any("A. Engineer" in row and "2026-01-15 10:30:00 UTC" in row for row in engineer)
    assert "hidden-leaf" not in html
    assert ">1 more<" in html


def test_generic_renderer_bounds_and_required_source() -> None:
    """The generic table stops at 200 rows (spec 0006 4.6.1) and a value cell refuses a missing source."""
    from eng_harness._html import HtmlError
    from eng_harness.report._sections import CellSource, SourceBook, _render_generic, value_cell

    book = SourceBook()
    with pytest.raises(HtmlError, match="source"):
        value_cell("x", cast(CellSource, None), book)
    with pytest.raises(HtmlError, match="source"):
        value_cell("x", CellSource("", "/"), book)
    wide: dict[str, JsonValue] = {f"k{index}": index for index in range(201)}
    html = "".join(node.render() for node in _render_generic(wide, "res_wide", book))
    assert "k0" in html
    assert "k199" in html
    assert "k200" not in html
    assert ">1 more<" in html
    long = value_cell("y" * 600, CellSource("res_wide", "/n"), SourceBook())
    assert "(600 characters)" in long.render()
