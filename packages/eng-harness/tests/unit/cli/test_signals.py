"""Interrupt signal handling for `run` and `resume` (spec 0006 AC10, section 4.4.8; plan 0006 T14b)."""

import io
import os
import signal
from pathlib import Path
from typing import NoReturn

import pytest
from eng_contract.ids import FixedClock
from helpers.cli_deps import START_MS, WORKFLOW, Rig, pauses_on_stop

from eng_harness.cli import ExitCode
from eng_harness.cli._control import STOP_FILE, StopRequest, read_stop, write_stop
from eng_harness.cli._signals import install_interrupt_handler
from eng_harness.cli._wiring import RunIdCell
from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev


class _Exited(BaseException):
    """Sentinel raised by a fake `exit_process` in tests so the test process stays alive."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def test_first_interrupt_requests_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FixedClock(START_MS, 1)
    runs = tmp_path / "runs"

    # Case 1a: empty run-id cell -> first interrupt exits 130 immediately, no stop file
    out, err = io.StringIO(), io.StringIO()
    out.write("buffered")
    exits: list[int] = []

    def fake_exit(code: int) -> NoReturn:
        exits.append(code)
        raise _Exited(code)

    empty = RunIdCell(runs)
    with (
        pytest.raises(_Exited) as caught,
        install_interrupt_handler(empty, clock, out, err, exit_process=fake_exit),
    ):
        signal.raise_signal(signal.SIGINT)
    assert caught.value.code == ExitCode.INTERRUPTED
    assert int(ExitCode.INTERRUPTED) == 130
    assert exits == [130]
    assert not runs.exists()

    # Case 1b: cell filled, but run folder does not exist yet -> first interrupt exits 130, creates nothing
    missing_id = "run_" + "0" * 26
    missing = RunIdCell(runs, missing_id)
    exits.clear()
    with (
        pytest.raises(_Exited) as caught,
        install_interrupt_handler(missing, clock, out, err, exit_process=fake_exit),
    ):
        signal.raise_signal(signal.SIGINT)
    assert caught.value.code == 130
    assert not (runs / missing_id).exists()

    # Case 2: cell filled and run folder exists -> first interrupt writes stop.json, second exits 130
    run_id = "run_" + "1" * 26
    run_dir = runs / run_id
    run_dir.mkdir(parents=True)
    filled = RunIdCell(runs, run_id)
    exits.clear()
    err = io.StringIO()
    with install_interrupt_handler(filled, clock, out, err, exit_process=fake_exit):
        signal.raise_signal(signal.SIGINT)
        assert exits == []
        assert read_stop(run_dir) == StopRequest(requested_at="2026-01-01T00:00:00.000Z", by="signal")
        assert "stop requested" in err.getvalue()
        with pytest.raises(_Exited) as second:
            signal.raise_signal(signal.SIGINT)
        assert second.value.code == 130
    assert exits == [130]

    # Case 3: end-to-end through `run` (before run folder exists -> 130) and `resume` (folder exists -> STOPPED)
    monkeypatch.setattr(os, "_exit", fake_exit)
    rig_run = Rig(tmp_path / "cli_run", on_build=lambda _: signal.raise_signal(signal.SIGINT))
    with pytest.raises(_Exited) as caught:
        rig_run.main("run", WORKFLOW, "--no-report", "--progress", "off")
    assert caught.value.code == 130
    assert rig_run.run_ids() == []

    rig_res = Rig(tmp_path / "cli_res", script=pauses_on_stop)
    assert rig_res.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    [res_id] = rig_res.run_ids()
    write_stop(rig_res.runs / res_id, "cli", clock)  # stale file removed before signal handler runs
    rig_res.on_build = lambda _: signal.raise_signal(signal.SIGINT)
    assert rig_res.main("resume", res_id, "--no-report", "--progress", "off") == ExitCode.STOPPED
    assert not (rig_res.runs / res_id / STOP_FILE).exists()
    reader = JournalReader(rig_res.runs / res_id)
    try:
        assert reader.events()[-1].payload == ev.RunPaused(reason="stop_requested", request_ids=[])
    finally:
        reader.close()
