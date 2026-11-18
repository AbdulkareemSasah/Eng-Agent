"""The run id behind the page's stop check and report (spec 0006 4.4.8; plan 0006 T14)."""

import asyncio
import io
from pathlib import Path

import pytest
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore
from fixtures.report_run import build_report_run

from eng_harness.cli._config import HarnessConfig
from eng_harness.cli._control import write_stop
from eng_harness.cli._wiring import PageSession, RunIdCell
from eng_harness.ports import ApprovalRequest

SHA = "a" * 64


def _session(store: ResultStore, clock: FixedClock, runs: Path, cell: RunIdCell) -> PageSession:
    return PageSession(
        config=HarnessConfig(), store=store, runs_dir=runs, cell=cell, clock=clock, wait_timeout_s=None, no_wait=True,
        no_browser=True, opener=lambda _: False, stderr=io.StringIO(),
    )  # fmt: skip


def test_page_bindings_before_and_after_run_id(
    tmp_path: Path, store: ResultStore, ids: SeededIdSource, clock: FixedClock
) -> None:
    runs = tmp_path / "ws" / "runs"
    run_id = f"run_{ids.new_ulid()}"
    (runs / run_id).mkdir(parents=True)
    write_stop(runs / run_id, "cli", clock)
    cell = RunIdCell(runs)
    page = _session(store, clock, runs, cell).page.hub
    assert [cell.run_id] == [None]
    assert page.stop_requested() is False  # the stop file exists, but no run is known yet
    assert "The report is not available yet" in page.report()
    with pytest.raises(RuntimeError, match="the run id is not known yet"):
        cell.folder()
    session = _session(store, clock, runs, cell)
    request = ApprovalRequest(
        request_id="apr_one", run_id=run_id, kind="info", title="t", preview_ref="res_" + "0" * 26,
        shown_sha256=SHA, binding=(), items=(),
    )  # fmt: skip
    asyncio.run(session.approvals.present(request))  # the first request of a run fills the cell
    assert (cell.run_id, cell.folder()) == (run_id, runs / run_id)
    assert session.page.hub.stop_requested() is True
    assert "The report is not available yet" in session.page.hub.report()  # no journal in the folder yet
    build_report_run(runs / run_id, store, ids)
    assert "Run report" in session.page.hub.report()
    cell.fill(run_id)  # the same id again confirms it
    with pytest.raises(RuntimeError, match="the run id changed"):
        cell.fill("run_" + "1" * 26)


def test_resume_fills_the_cell_at_once(tmp_path: Path, store: ResultStore, clock: FixedClock) -> None:
    runs = tmp_path / "ws" / "runs"
    (runs / "run_x").mkdir(parents=True)
    write_stop(runs / "run_x", "signal", clock)
    cell = RunIdCell(runs, "run_x")
    assert (cell.run_id, _session(store, clock, runs, cell).page.hub.stop_requested()) == ("run_x", True)
