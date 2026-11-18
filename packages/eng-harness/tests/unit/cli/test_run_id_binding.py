"""The run id behind the page's stop check and report (spec 0006 4.4.8; plan 0006 T14)."""

import asyncio
import io
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore
from fixtures.report_run import build_report_run
from helpers.cli_deps import client_for

from eng_harness.cli._config import HarnessConfig
from eng_harness.cli._control import write_stop
from eng_harness.cli._wiring import PageSession, RunIdCell, engine_settings, release_marks
from eng_harness.engine import EngineSettings
from eng_harness.ports import ApprovalRequest, InputRequest
from eng_harness.report import ReleaseMarks

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


def _recording(opened: list[str]) -> Callable[[str], bool]:
    def opener(address: str) -> bool:
        opened.append(address)
        return True

    return opener


def _input_request() -> InputRequest:
    return InputRequest.model_validate(
        {"request_id": "in_one", "kind": "block", "title": "Data", "fields_schema": {"type": "object"}}
    )


def test_page_server_starts_once_at_the_first_request_shown(
    tmp_path: Path, store: ResultStore, clock: FixedClock
) -> None:
    runs, opened, err = tmp_path / "ws" / "runs", list[str](), io.StringIO()
    session = PageSession(
        config=HarnessConfig(), store=store, runs_dir=runs, cell=RunIdCell(runs, "run_x"), clock=clock,
        wait_timeout_s=None, no_wait=False, no_browser=False, opener=_recording(opened), stderr=err,
    )  # fmt: skip
    assert opened == []  # nothing is served before a request is shown
    asyncio.run(session.inputs.present(_input_request()))
    asyncio.run(session.inputs.present(_input_request()))
    [address] = opened
    assert re.fullmatch(r"http://127\.0\.0\.1:[0-9]+/\S+", address)
    assert err.getvalue() == "approval page opened in your browser\n"
    port = int(address.split(":")[2].split("/")[0])
    assert client_for(address).port == port
    session.close()
    with pytest.raises(OSError, match="refused"):
        client_for(address).get("/")  # the page server stopped with the command


@pytest.mark.parametrize(("no_wait", "no_browser", "browser", "serves"), [
    (True, False, True, False), (False, True, True, False), (False, False, False, False), (False, False, True, True),
])  # fmt: skip
def test_page_server_is_not_started_or_not_opened(
    tmp_path: Path, store: ResultStore, clock: FixedClock, no_wait: bool, no_browser: bool, browser: bool, serves: bool
) -> None:
    runs, opened, err = tmp_path / "ws" / "runs", list[str](), io.StringIO()
    config = HarnessConfig.model_validate({"page": {"open_browser": browser}})
    session = PageSession(
        config=config, store=store, runs_dir=runs, cell=RunIdCell(runs, "run_x"), clock=clock, wait_timeout_s=1,
        no_wait=no_wait, no_browser=no_browser, opener=_recording(opened), stderr=err,
        terminal_writer=lambda _: False,
    )  # fmt: skip
    asyncio.run(session.inputs.present(_input_request()))
    assert asyncio.run(session.inputs.answer("in_one", wait=False)) is None
    session.close()
    assert len(opened) == (1 if serves else 0)
    said = err.getvalue()
    if no_wait:
        assert said == ""  # `--no-wait` serves no page and says nothing about it
    elif not serves:
        assert said.startswith("the launch address cannot be shown here; run from a terminal, or use --no-wait")


def test_settings_and_marks_come_from_the_configuration() -> None:
    config = HarnessConfig.model_validate(
        {"engine": {"default_mode": "approve_each_write", "engineer": "ada", "max_attempts_cap": 4},
         "project_lane": {"tool_a": {"record": "gap-1"}}}
    )  # fmt: skip
    assert engine_settings(config) == EngineSettings(max_attempts_cap=4)
    assert engine_settings(HarnessConfig()) == EngineSettings()
    assert release_marks(config) == ReleaseMarks(records={"tool_a": "gap-1"})
    assert release_marks(HarnessConfig()) == ReleaseMarks(records={})
