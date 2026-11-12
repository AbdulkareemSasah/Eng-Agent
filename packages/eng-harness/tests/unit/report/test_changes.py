"""Changes, decisions and model revisions (plan 0006 T12; spec 0006 AC55)."""

import re
from pathlib import Path

from eng_contract.ids import SeededIdSource
from eng_contract.store import ResultStore
from golden.test_report import load_sections_run, section


def _row(html: str, item: str) -> str:
    match = re.search(rf">(?P<id>{re.escape(item)})</bdi>(?P<body>.{{0,500}}?)</tr>", html)
    assert match is not None, item
    return match.group("body")


def test_changes_decisions_revisions(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    """AC55: revisions, change-set items, binding, applied read-back, differences and decisions."""
    from eng_harness.report._sections import render_sections

    run = load_sections_run(run_dir, store, ids)
    try:
        html = render_sections(run.model, run.reader, store)
    finally:
        run.close()
    changes = section(html, "Changes", "Results summary")
    results = section(html, "Results summary", "Sources")
    decisions = section(html, "Decisions")
    assert "rev-1.edb" in changes
    assert "fp-1" in changes
    assert "rev-2.edb" in changes
    assert "fp-2" in changes
    assert "promoted.edb" in changes
    assert "original.edb" in changes
    assert "fp-bind" in changes
    accepted = _row(changes, "i1")
    assert "accepted" in accepted
    assert "rejected" not in accepted
    rejected = _row(changes, "i2")
    assert "rejected" in rejected
    assert "too thin &lt;b&gt;x&lt;/b&gt;" in rejected
    whole = _row(changes, "i4")
    assert "rejected" in whole
    assert "stop" in whole
    assert "accepted" not in whole
    assert "mismatch" in changes
    assert "apply_change" in changes
    assert "F1" in changes
    assert "C40" in changes
    assert "F7" in changes
    assert "engineer change" in changes
    assert "<b>x</b>" not in html
    assert "C1" in results
    assert "1.2" in results
    assert "0.004" in results
    assert "end points coincide" in results
    assert "S1" in results
    assert "cycle.turn" in decisions
    assert "more_edits" in decisions
    assert "engineer:ada" in decisions
