"""Report DRAFT, signing and completeness marks (spec 0006 AC53)."""

from pathlib import Path

from eng_contract.envelope import Provenance
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore

from eng_harness import __version__
from eng_harness.journal import EventType, JournalReader, JournalWriter
from eng_harness.report import ReleaseMarks, build_report

_SHA = "a" * 64
_MARKS = ReleaseMarks(records={})


def _minimal_run(
    run_dir: Path,
    store: ResultStore,
    ids: SeededIdSource,
    clock: FixedClock,
    *,
    terminal: bool,
    draft_output: bool,
    signed: bool,
) -> None:
    producer = Provenance(
        tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
    )
    base = store.put("harness.journal_blob/1", {"value": 1}, producer).result_id
    header = {
        "run_id": "run_x",
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
    }
    writer = JournalWriter(run_dir, store, clock, ids)
    writer.append(EventType.RUN_STARTED, {**header, "input_ref": base, "basis_ref": base})
    if terminal:
        writer.append(
            EventType.RUN_COMPLETED,
            {"output_ref": base, "output_sha256": _SHA, "draft": draft_output},
        )
        if signed:
            writer.append(
                EventType.SIGNED_OFF,
                {"outputs": [base], "approval_request_id": "sign", "by": "engineer:ada"},
            )
    writer.close()


def _html(
    run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: FixedClock, **kwargs: bool
) -> str:
    _minimal_run(run_dir, store, ids, clock, **kwargs)
    reader = JournalReader(run_dir)
    try:
        return build_report(reader, store, _MARKS, clock, __version__)
    finally:
        reader.close()


def test_draft_signed_and_sources(
    run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: FixedClock
) -> None:
    """AC53: DRAFT until signed; signed banner; DRAFT SOURCES after signing; INCOMPLETE when not terminal."""
    unsigned = _html(run_dir, store, ids, clock, terminal=False, draft_output=False, signed=False)
    assert '<div class="draft">' in unsigned
    assert "<title>DRAFT " in unsigned
    assert "INCOMPLETE:" in unsigned

    signed_clean = _html(run_dir, store, ids, clock, terminal=True, draft_output=False, signed=True)
    assert '<div class="draft">' not in signed_clean
    assert "DRAFT —" not in signed_clean
    assert "Signed by engineer:ada" in signed_clean
    assert "2026-01-01 00:00:00.002 UTC" in signed_clean

    signed_draft_sources = _html(run_dir, store, ids, clock, terminal=True, draft_output=True, signed=True)
    assert "DRAFT SOURCES" in signed_draft_sources
    assert '<div class="draft">' not in signed_draft_sources
