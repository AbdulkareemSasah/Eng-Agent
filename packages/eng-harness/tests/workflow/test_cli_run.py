"""`run` with a fake engine: the approval on the page, the report, the ports and the outcomes (spec 0006 AC7, AC71)."""

import json
from pathlib import Path
from typing import cast

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from helpers.cli_deps import (
    REGISTRY,
    WORKFLOW,
    Placeholder,
    Rig,
    Script,
    Session,
    approves,
    approving_opener,
    completes,
)

from eng_harness.cli import CliDeps, ExitCode
from eng_harness.cli._wiring import RunPortSet, default_engine_factory
from eng_harness.engine import Engine, EngineSettings, PermissionMode, RunOutcome, RunStatus
from eng_harness.journal import EventType, JournalReader
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalPort, BasisPort, CalcPort, HostPort, InputPort, RunClass, ToolPort


def _events(rig: Rig, run_id: str) -> list[ev.Event]:
    reader = JournalReader(rig.runs / run_id)
    try:
        return reader.events()
    finally:
        reader.close()


def test_run_completes_and_writes_report(tmp_path: Path) -> None:
    rig = Rig(tmp_path, script=approves(wait=True))
    rig.open_with = approving_opener(rig)
    path = rig.input_file('{"note": "n"}', "utf-8-sig")  # a byte-order mark is read as without it (spec 4.7)
    assert rig.main("run", WORKFLOW, "--input", path, "--json", "--progress", "off") == ExitCode.OK
    result = json.loads(rig.out.getvalue())
    [run_id] = rig.run_ids()
    report = rig.runs / run_id / "report" / "report.html"
    assert result == {
        "run_id": run_id, "workflow": WORKFLOW, "status": "COMPLETED", "exit_code": 0, "pending": [],
        "escalation": None, "report": str(report),
    }  # fmt: skip
    assert report.read_text(encoding="utf-8").startswith("<!doctype html>")
    events = _events(rig, run_id)
    assert events[-1].type is EventType.RUN_COMPLETED
    assert [e.payload.by for e in events if isinstance(e.payload, ev.ApprovalResolved)] == ["engineer:ada"]
    assert "approval page opened in your browser" in rig.err.getvalue()
    assert all(rig.opened[0] not in text for text in (rig.out.getvalue(), rig.err.getvalue()))  # never on a stream
    request = rig.engines[0].run_request
    assert request is not None
    assert (request.input, request.mode, request.run_class) == (
        {"note": "n"},
        PermissionMode.WORK_ON_COPY,
        "production",
    )
    assert request.basis_ref == "res_" + "0" * 26  # a workflow without required basis fields (spec Q23, interim)


def test_ports_entered_around_engine_call(tmp_path: Path) -> None:
    rig = Rig(tmp_path / "returns", script=completes)
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    assert rig.log == ["enter", "start", "exit"]

    async def locked(session: Session) -> RunOutcome:
        raise ContractError(ErrorCode.HOST_LOCKED, "another driver holds the host")

    async def broken(session: Session) -> RunOutcome:
        raise RuntimeError("boom")

    for name, script, code, text in [
        ("locked", locked, ExitCode.RUN_LOCKED, "HOST_LOCKED: another driver holds the host"),
        ("broken", broken, ExitCode.INTERNAL, "internal error err_"),
    ]:
        rig = Rig(tmp_path / name, script=script)
        assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == code, name
        assert rig.log == ["enter", "start", "exit"], name  # the ports are left when the engine raises
        assert text in rig.err.getvalue(), name


def test_outcomes_map_to_exit_codes(tmp_path: Path) -> None:
    def returns(status: RunStatus, **fields: object) -> Script:
        async def script(session: Session) -> RunOutcome:
            return RunOutcome(session.run_id, status, **fields)  # type: ignore[arg-type]

        return script

    escalation = ev.RunEscalated(reason="block_escalation", detail="d\x1b[2Jetail", evidence=[])

    async def input_pause(session: Session) -> RunOutcome:
        return session.paused("awaiting_input", ("in1",))

    async def stop_pause(session: Session) -> RunOutcome:
        return session.paused("stop_requested")

    for name, script, code, text in [
        ("failed", returns(RunStatus.FAILED), ExitCode.RUN_FAILED, ": FAILED"),
        (
            "escalated",
            returns(RunStatus.NEEDS_ENGINEER, escalation=escalation),
            ExitCode.NEEDS_ENGINEER,
            "needs the engineer: block_escalation: d",
        ),
        ("input", input_pause, ExitCode.AWAITING_ENGINEER, ": PAUSED"),
        ("stop", stop_pause, ExitCode.STOPPED, "resume with: eng-harness resume run_"),
    ]:
        rig = Rig(tmp_path / name, script=script)
        assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == code, name
        assert text in rig.out.getvalue(), (name, rig.out.getvalue())
        assert "\x1b" not in rig.out.getvalue(), name  # untrusted text is shown without control characters


def test_generated_options_reach_the_input(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    path = rig.input_file('{"note": "x", "count": 1}')
    argv = ["run", WORKFLOW, "--input", path, "--title", "T", "--count", "3", "--mode", "approve_each_write"]
    assert rig.main(*argv, "--run-class", "trial", "--no-report", "--progress", "off") == ExitCode.OK
    request = rig.engines[0].run_request
    assert request is not None
    assert request.input == {"note": "x", "title": "T", "count": 3}  # an option replaces the file's value
    assert (request.mode, request.run_class) == (PermissionMode.APPROVE_EACH_WRITE, RunClass.TRIAL)


def test_default_engine_factory_is_the_merged_engine(tmp_path: Path) -> None:
    assert CliDeps().engine_factory is default_engine_factory
    clock, root = FixedClock(0, 1), tmp_path / "ws"
    ids, workspace = SeededIdSource(b"x", clock), Workspace(root=root, classification=LocationClass.LOCAL)
    from eng_harness._kinds import HARNESS_KINDS

    ports = RunPortSet(
        tool=cast(ToolPort, Placeholder()), host=cast(HostPort, Placeholder()), calc=cast(CalcPort, Placeholder()),
        basis=cast(BasisPort, Placeholder()), approvals=cast(ApprovalPort, Placeholder()),
        inputs=cast(InputPort, Placeholder()),
    )  # fmt: skip
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    engine = default_engine_factory(workspace, REGISTRY, ports, store, EngineSettings(), clock, ids)
    assert isinstance(engine, Engine)
