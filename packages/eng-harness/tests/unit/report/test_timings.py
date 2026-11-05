"""Report model: timings, waiting and machine time (plan 0006 T11; spec 0006 AC56)."""

from pathlib import Path

import pytest
from eng_contract.ids import SeededIdSource
from eng_contract.store import ResultStore
from fixtures.report_run import EVENT_COUNT, build_report_run

from eng_harness.journal import JournalReader
from eng_harness.report._model import fold_report


def test_wait_and_run_times(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    run = build_report_run(run_dir, store, ids)
    timings = fold_report(JournalReader(run_dir)).timings
    assert timings.waiting_ms == run.wait_ms
    assert timings.machine_ms == run.machine_ms
    assert timings.resumes == run.resumes == 1
    assert [(s.path, s.status, s.duration_ms) for s in timings.steps] == [
        ("0", "completed", 2_000), ("1", "completed", 5_000), ("2", "failed", 1_500),
    ]  # fmt: skip
    assert [s.started_at for s in timings.steps] == [
        "2026-01-01T00:00:01.000Z", "2026-01-01T00:01:03.000Z", "2026-01-01T00:01:40.000Z",
    ]  # fmt: skip


def test_unanswered_request_is_not_waiting_time(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    run = build_report_run(run_dir, store, ids, open_approval=True)
    model = fold_report(JournalReader(run_dir))
    assert model.timings.waiting_ms == run.wait_ms
    assert model.open_requests == ("ap2",)


def test_model_carries_run_view_and_integrity(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    build_report_run(run_dir, store, ids)
    model = fold_report(JournalReader(run_dir))
    assert model.run.run_id == "run_x"
    assert model.event_count == EVENT_COUNT
    assert len(model.chain_sha256) == 64
    assert [r.resume_no for r in model.resumes] == [1]
    assert model.resumes[0].at == "2026-01-01T00:01:40.000Z"


def test_resolution_before_request_is_refused(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    from eng_harness.report._model import wait_time_ms

    with pytest.raises(ValueError, match="before"):
        wait_time_ms("2026-01-01T00:00:10.000Z", "2026-01-01T00:00:05.000Z")
