"""`run --no-wait`, `resume` and the stop-file removals of `run` and `resume` (spec 0006 AC8, AC9; plan 0006 T14)."""

import json
from pathlib import Path

from eng_contract.ids import FixedClock
from helpers.cli_deps import START_MS, WORKFLOW, Rig, Session, approves, approving_opener, pauses_on_stop

from eng_harness.cli import ExitCode
from eng_harness.cli._control import STOP_FILE, write_stop
from eng_harness.engine import RunOutcome
from eng_harness.journal import EventType, JournalReader
from eng_harness.journal import _events as ev

REPORT = "report/report.html"


def _last(rig: Rig, run_id: str) -> ev.Event:
    reader = JournalReader(rig.runs / run_id)
    try:
        return reader.events()[-1]
    finally:
        reader.close()


def test_no_wait_then_resume(tmp_path: Path) -> None:
    rig = Rig(tmp_path, script=approves(wait=False))
    assert rig.main("run", WORKFLOW, "--no-wait", "--json", "--progress", "off") == ExitCode.AWAITING_ENGINEER
    [run_id] = rig.run_ids()
    first = json.loads(rig.out.getvalue())
    assert first["status"] == "PAUSED"
    assert first["pending"] == [{"request_id": "apr_one", "title": "Apply the change"}]
    assert (rig.runs / run_id / REPORT).is_file()  # the report is written on a pause too (spec 4.2.2 step 6)
    assert _last(rig, run_id).payload == ev.RunPaused(reason="awaiting_approval", request_ids=["apr_one"])
    assert rig.opened == []  # the page was not served
    # the human summary names the request and the command, and holds no address and no token
    rig.out.truncate(0)
    rig.out.seek(0)
    other = Rig(tmp_path / "text", script=approves(wait=False))
    assert other.main("run", WORKFLOW, "--no-wait", "--progress", "off") == ExitCode.AWAITING_ENGINEER
    [other_id] = other.run_ids()
    text = other.out.getvalue()
    assert f"waiting for you: Apply the change [apr_one]\nresume with: eng-harness resume {other_id}\n" in text
    assert "http" not in text + other.err.getvalue()
    # a later resume, answered on the page, completes the run
    rig.script = approves(wait=True)
    rig.open_with = approving_opener(rig)
    rig.out.truncate(0)
    assert rig.main("resume", run_id, "--json", "--progress", "off") == ExitCode.OK
    assert json.loads(rig.out.getvalue())["status"] == "COMPLETED"
    assert _last(rig, run_id).type is EventType.RUN_COMPLETED
    assert rig.log == ["enter", "start", "exit", "enter", "resume", "exit"]
    assert len(rig.opened) == 1


def test_stop_file_removed_on_return_and_before_resume(tmp_path: Path) -> None:
    clock = FixedClock(START_MS)

    async def stops_itself(session: Session) -> RunOutcome:
        write_stop(session.engine.workspace.root / "runs" / session.run_id, "cli", clock)
        return session.completed()

    rig = Rig(tmp_path / "run", script=stops_itself)  # `run`: the file is removed when `Engine.start` returns
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    [run_id] = rig.run_ids()
    assert not (rig.runs / run_id / STOP_FILE).exists()

    rig = Rig(tmp_path / "resume", script=approves(wait=False))
    assert rig.main("run", WORKFLOW, "--no-wait", "--no-report", "--progress", "off") == ExitCode.AWAITING_ENGINEER
    [run_id] = rig.run_ids()
    run_dir = rig.runs / run_id
    write_stop(run_dir, "cli", clock)  # a stale file from an earlier stop
    present_when_built: list[bool] = []

    def build(runs: Path) -> None:
        present_when_built.append((runs / run_id / STOP_FILE).exists())
        write_stop(runs / run_id, "signal", clock)  # the first interrupt, after the stale file was removed

    rig.on_build, rig.script = build, pauses_on_stop
    assert rig.main("resume", run_id, "--no-report", "--progress", "off") == ExitCode.STOPPED
    assert present_when_built == [False]  # removed at the start of the command, before the ports were built
    assert _last(rig, run_id).payload == ev.RunPaused(
        reason="stop_requested", request_ids=[]
    )  # and the new one was seen
    assert not (run_dir / STOP_FILE).exists()  # removed when `Engine.resume` returned
