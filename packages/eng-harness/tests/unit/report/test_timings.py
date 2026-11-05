"""Report model: timings, waiting and machine time (plan 0006 T11; spec 0006 AC56)."""

from pathlib import Path

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from fixtures.report_run import EVENT_COUNT, build_report_run

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.journal import JournalReader
from eng_harness.report._model import fold_report


def test_wait_and_run_times(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    run = build_report_run(run_dir, store, ids)
    timings = fold_report(JournalReader(run_dir), store).timings
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
    model = fold_report(JournalReader(run_dir), store)
    assert model.timings.waiting_ms == run.wait_ms
    assert model.open_requests == ("ap2",)


def test_model_carries_run_view_and_integrity(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    build_report_run(run_dir, store, ids)
    model = fold_report(JournalReader(run_dir), store)
    assert model.run.run_id == "run_x"
    assert model.event_count == EVENT_COUNT
    assert len(model.chain_sha256) == 64
    assert [r.resume_no for r in model.resumes] == [1]
    assert model.resumes[0].at == "2026-01-01T00:01:40.000Z"


def test_decision_answer_counts_as_input_wait(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    build_report_run(run_dir, store, ids)
    model = fold_report(JournalReader(run_dir), store)
    by_id = {r.request_id: r for r in model.requests}
    assert by_id["dec1"].wait_ms == 5_000
    assert by_id["dec1"].outcome == "decision"
    assert sum(r.wait_ms or 0 for r in model.requests) == model.timings.waiting_ms


def test_requests_carry_who_what_and_reasons(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    build_report_run(run_dir, store, ids, open_approval=True)
    by_id = {r.request_id: r for r in fold_report(JournalReader(run_dir), store).requests}
    approval = by_id["ap1"]
    assert (approval.kind, approval.outcome, approval.by, approval.wait_ms) == ("INFO", "reject", "engineer:x", 60_000)
    assert approval.requested_at == "2026-01-01T00:00:03.000Z"
    assert approval.answered_at == "2026-01-01T00:01:03.000Z"
    assert approval.reasons == ("no", "i: too thin")
    assert (by_id["in1"].outcome, by_id["in1"].by) == ("provided", "engineer:x")
    assert (by_id["ap2"].outcome, by_id["ap2"].answered_at, by_id["ap2"].wait_ms) == (None, None, None)


def test_decisions_escalations_reconciliations(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    build_report_run(run_dir, store, ids)
    model = fold_report(JournalReader(run_dir), store)
    (decision,) = model.decisions
    assert (decision.point, decision.options, decision.choice) == ("p", ["a", "b"], "a")
    assert (decision.decided_by, decision.confidence, decision.request_id) == ("engineer:x", None, "dec1")
    assert decision.at == "2026-01-01T00:01:47.000Z"
    (escalation,) = model.escalations
    assert (escalation.reason, escalation.detail, escalation.at) == (
        "needs_reconciliation", "d", "2026-01-01T00:01:41.700Z",
    )  # fmt: skip
    (reconciled,) = model.reconciliations
    assert (reconciled.op_id, reconciled.outcome, reconciled.decided_by, reconciled.path) == (
        "op1", "applied", "engineer:x", None,
    )  # fmt: skip


def test_hosts_left_open_until_the_run_ends(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    build_report_run(run_dir, store, ids)
    model = fold_report(JournalReader(run_dir), store)
    assert [(h.instance_id, h.open) for h in model.hosts] == [("i1", True)]
    assert model.run.ended_at is None


def test_results_folded_from_the_store(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    run = build_report_run(run_dir, store, ids)
    results = fold_report(JournalReader(run_dir), store).results
    assert [r.result_id for r in results] == list(run.result_ids)
    first, second = results
    assert (first.kind, first.tool, first.tool_version, first.parents) == ("harness.journal_blob/1", "harness", "1", ())
    assert second.parents == (first.result_id,)
    assert second.created_at == store.get(second.result_id).created_at


def test_missing_stored_result_is_refused(
    run_dir: Path, store: ResultStore, ids: SeededIdSource, tmp_path: Path
) -> None:
    build_report_run(run_dir, store, ids)
    empty = ResultStore(
        Workspace(root=tmp_path / "empty", classification=LocationClass.LOCAL), HARNESS_KINDS, ids, FixedClock(0, 1)
    )
    with pytest.raises(ContractError) as caught:
        fold_report(JournalReader(run_dir), empty)
    assert caught.value.detail.code is ErrorCode.REF_NOT_FOUND


def test_resolution_before_request_is_refused(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    from eng_harness.report._model import wait_time_ms

    with pytest.raises(ValueError, match="before"):
        wait_time_ms("2026-01-01T00:00:10.000Z", "2026-01-01T00:00:05.000Z")
