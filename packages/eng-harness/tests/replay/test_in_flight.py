"""In-flight steps at a resume: reconciliation of writes and the rerun of reads (plan 0001 T11b; spec 0001 4.5.3).

Covers AC31 (a write in flight is reconciled before the block is called: `applied`, `not_applied`, and every other
outcome as a stop with an engineer request; a write found applied whose result cannot be read stays in flight) and AC32
(a read or calc in flight runs again after `step_rerun`). The runs are forged by hand, because a cut-off between a
step's start and its end cannot be reached through the public API: the journal holds the steps up to the cut, and a
new engine resumes it as a new process would. The fake host's reconciler answers per `op_id`; its call log and the
rig's port-call log show what the resume asked of the ports.
"""

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import pytest
from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode, ErrorDetail
from fakes.ports import failure
from pydantic import BaseModel, JsonValue
from workflows.chain import ORIGINAL, ChainOutput, chain
from workflows.ctx_flows import change_set, flow, request_id, success
from workflows.hoststate import (
    INSTANCE,
    OP,
    REF,
    ScriptedHost,
    answer,
    bound,
    done,
    failed,
    forge,
    options,
    resume,
    scripted_rig,
    start,
    trace,
)
from workflows.modes import approved, give_files, mode_rig, promoting, stored_writes
from workflows.rig import Rig, asking, make_rig

from eng_harness.calc import CalcStatus
from eng_harness.ctx import ModelHandle
from eng_harness.engine import RunStatus
from eng_harness.engine._steps import op_id
from eng_harness.errors import HarnessCode, JournalIntegrityError, RunRefused
from eng_harness.journal import EventType, JournalReader, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import (
    CalcInfo,
    HostLease,
    HostModelState,
    InputAnswer,
    Reconciliation,
    ServerCheck,
    UnitsState,
)

T = EventType
WRITE_ARGS: dict[str, JsonValue] = {"n": 1, "model": "m1"}


def _cut_off_write(root: Path) -> tuple[Rig, ScriptedHost, str]:
    """A run of `ORIGINAL` cut off while its write was in flight: read done, write started, model bound."""
    rig, host = scripted_rig(root)
    host.add_model("m1", INSTANCE)
    steps = (
        start("0", "read_a", {"n": 0}),
        done("0"),
        start("1", "write_b", WRITE_ARGS, write=True),
        bound("m1", INSTANCE),
    )
    return rig, host, forge(rig, chain(ORIGINAL), *steps)


def _events[P: ev.StepReconciled | ev.InputProvided | ev.RunFailed](rig: Rig, run_id: str, kind: type[P]) -> list[P]:
    return [e.payload for e in rig.events(run_id) if isinstance(e.payload, kind)]


@pytest.mark.parametrize("found", ["applied", "applied_without_result", "not_applied"])
def test_write_in_flight(tmp_path: Path, found: str) -> None:
    rig, host, run_id = _cut_off_write(tmp_path)
    reply = success(rig, {"tool": "write_b"})
    host.reconciliations[OP] = {
        "applied": Reconciliation(outcome="applied", result=reply),
        "applied_without_result": Reconciliation(outcome="applied"),
        "not_applied": Reconciliation(outcome="not_applied"),
    }[found]
    before = len(rig.events(run_id))
    outcome = resume(rig, chain(ORIGINAL), run_id)
    assert outcome.status is RunStatus.COMPLETED
    assert isinstance(outcome.output, ChainOutput)
    (closing,) = _events(rig, run_id, ev.StepReconciled)
    assert (closing.op_id, closing.decided_by) == (OP, "adapter")  # asked with the op_id the journal holds
    assert [c for c in host.calls if c[0] == "reconcile"] == [("reconcile", OP, None)]
    reconciled = [("run_resumed", None, None), ("step_reconciled", "1", 1)]
    if found == "not_applied":  # runs again as the next attempt, with a new op_id
        assert (closing.outcome, closing.result) == ("not_applied", None)
        assert trace(rig, run_id, before) == [
            *reconciled,
            ("step_started", "1", 2),
            ("step_completed", "1", 2),
            ("step_started", "2", 1),
            ("step_completed", "2", 1),
            ("step_started", "~end.check_model.m1", 1),
            ("step_completed", "~end.check_model.m1", 1),
            ("check_enforced", "~end.check_model.m1", None),
            ("run_completed", None, None),
        ]  # fmt: skip
        assert [(c.tool, c.op_id) for c in host.ledger][:1] == [("write_b", op_id(run_id, "1", 2))]
        assert op_id(run_id, "1", 2) != OP
        return
    assert closing.outcome == "applied"  # returns the reconciled result: no call
    assert trace(rig, run_id, before) == [
        *reconciled,
        ("step_started", "2", 1),
        ("step_completed", "2", 1),
        ("step_started", "~end.check_model.m1", 1),
        ("step_completed", "~end.check_model.m1", 1),
        ("check_enforced", "~end.check_model.m1", None),
        ("run_completed", None, None),
    ]  # fmt: skip
    assert [c.tool for c in host.ledger] == ["read_c"]
    assert closing.result is not None
    assert outcome.output.refs[:2] == [REF, closing.result.ref]
    if found == "applied":
        assert closing.result.ref == reply.result_id
    else:  # the adapter found the write applied but gave no result, and has no read-back: an empty summary
        assert closing.result.summary == {}


def _cannot_reconcile(host: ScriptedHost, reason: str) -> None:
    """Arrange that the adapter cannot decide the in-flight write, for one of the four reasons of AC31."""
    if reason == "no_reconciler":
        host.unsupported.add("write_b")
    elif reason == "reconciler_error":
        host.reconcile_error = ContractError(ErrorCode.HOST_ERROR, "the reconciler failed", retryable=False)
    else:
        host.reconciliations[OP] = Reconciliation(
            outcome="partial" if reason == "partial" else "unknown", missing=("x",)
        )


REASONS = ["partial", "unknown", "no_reconciler", "reconciler_error"]


@pytest.mark.parametrize("reason", REASONS)
def test_write_in_flight_stops_for_the_engineer(tmp_path: Path, reason: str) -> None:
    rig, host, run_id = _cut_off_write(tmp_path)
    _cannot_reconcile(host, reason)
    before = len(rig.events(run_id))
    stopped = resume(rig, chain(ORIGINAL), run_id)
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "needs_reconciliation"
    asked = rig.inputs.presented[-1]
    assert (asked.kind, asked.fields_schema["x-eng-input"]) == ("engine.in_flight", "choice")
    assert options(asked, "outcome") == ["applied", "not_applied", "abandon"]
    assert stopped.escalation.request_id == asked.request_id
    assert host.ledger == []  # the write is not sent again, and the block did not run on
    assert trace(rig, run_id, before) == [
        ("run_resumed", None, None),
        ("input_requested", None, None),
        ("run_escalated", None, None),
    ]
    reader = JournalReader(rig.run_dir(run_id))
    assert reader.run().pending == (asked.request_id,)
    reader.close()
    again = resume(rig, chain(ORIGINAL), run_id)  # no answer yet: presented again with the same request id (AC36)
    assert again.status is RunStatus.NEEDS_ENGINEER
    assert [r.request_id for r in rig.inputs.presented] == [asked.request_id] * 2
    assert [e.type for e in rig.events(run_id)].count(T.INPUT_REQUESTED) == 1


@pytest.mark.parametrize("choice", ["applied", "not_applied", "abandon"])
def test_engineer_resolves_a_write_in_flight(tmp_path: Path, choice: str) -> None:
    rig, host, run_id = _cut_off_write(tmp_path)
    _cannot_reconcile(host, "unknown")
    resume(rig, chain(ORIGINAL), run_id)
    asked = rig.inputs.presented[-1]
    rig.inputs.script(asked.request_id, answer(asked, choice, "outcome"))
    outcome = resume(rig, chain(ORIGINAL), run_id)
    (provided,) = _events(rig, run_id, ev.InputProvided)
    assert (provided.request_id, provided.by) == (asked.request_id, "engineer:test")
    if choice == "abandon":
        assert (outcome.status, host.ledger) == (RunStatus.FAILED, [])
        assert _events(rig, run_id, ev.RunFailed) == [ev.RunFailed(reason="abandoned", by="engineer:test")]
        return
    assert outcome.status is RunStatus.COMPLETED
    (closing,) = _events(rig, run_id, ev.StepReconciled)
    assert (closing.outcome, closing.decided_by) == (choice, "engineer:test")
    if choice == "applied":  # nothing is sent; the adapter has no read-back, so the summary is empty
        assert [c.tool for c in host.ledger] == ["read_c"]
        assert closing.result is not None
        assert closing.result.summary == {}
        assert "tool.read_back" in rig.log
    else:
        assert [(c.tool, c.op_id) for c in host.ledger][:1] == [("write_b", op_id(run_id, "1", 2))]


def test_a_refused_answer_leaves_the_request_open(tmp_path: Path) -> None:
    rig, host, run_id = _cut_off_write(tmp_path)
    _cannot_reconcile(host, "unknown")
    resume(rig, chain(ORIGINAL), run_id)
    asked = rig.inputs.presented[-1]
    rig.inputs.script(asked.request_id, answer(asked, "maybe", "outcome"))  # not one of the options
    outcome = resume(rig, chain(ORIGINAL), run_id)
    assert outcome.status is RunStatus.NEEDS_ENGINEER
    assert _events(rig, run_id, ev.InputProvided) == []
    assert rig.inputs.presented[-1].request_id == asked.request_id
    assert host.ledger == []


def test_second_not_applied_stops_for_the_engineer(tmp_path: Path) -> None:
    """The rerun of a write the adapter reconciled `not_applied`, reconciled so again, goes to the engineer (AC71)."""
    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)
    reconciled: dict[str, JsonValue] = {
        "op_id": OP,
        "outcome": "not_applied",
        "result": None,
        "decided_by": "adapter",
        "evidence": [],
    }
    steps = (
        start("0", "read_a", {"n": 0}),
        done("0"),
        start("1", "write_b", WRITE_ARGS, write=True),
        bound("m1", INSTANCE),
        (T.STEP_RECONCILED, "1", 1, reconciled),
        start("1", "write_b", WRITE_ARGS, attempt=2, write=True),
    )
    run_id = forge(rig, chain(ORIGINAL), *steps)
    host.reconciliations[OP] = Reconciliation(outcome="not_applied")
    before = len(rig.events(run_id))
    stopped = resume(rig, chain(ORIGINAL), run_id)
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "needs_reconciliation"
    asked = rig.inputs.presented[-1]
    assert (asked.kind, options(asked, "outcome")) == ("engine.in_flight", ["applied", "not_applied", "abandon"])
    assert stopped.escalation.request_id == asked.request_id
    assert host.ledger == []  # the write is not sent again
    assert trace(rig, run_id, before) == [
        ("run_resumed", None, None),
        ("input_requested", None, None),
        ("run_escalated", None, None),
    ]  # no step_reconciled from the adapter
    rig.inputs.script(asked.request_id, answer(asked, "not_applied", "outcome"))
    outcome = resume(rig, chain(ORIGINAL), run_id)
    assert outcome.status is RunStatus.COMPLETED
    closing = _events(rig, run_id, ev.StepReconciled)[-1]
    assert (closing.outcome, closing.decided_by) == ("not_applied", "engineer:test")
    assert [(c.tool, c.op_id) for c in host.ledger][:1] == [("write_b", op_id(run_id, "1", 3))]  # the engineer's rerun


@pytest.mark.parametrize("attempt", [1, 2])
def test_read_in_flight(tmp_path: Path, attempt: int) -> None:
    rig, host = scripted_rig(tmp_path)
    cut = [start("2", "read_c", {"n": 2}, attempt=attempt)]
    if attempt == 2:  # the first attempt failed and was retried; the retry was in flight
        cut = [start("2", "read_c", {"n": 2}), failed("2"), *cut]
    steps = (start("0", "read_a", {"n": 0}), done("0"), start("1", "write_b", WRITE_ARGS, write=True), done("1"), *cut)
    run_id = forge(rig, chain(ORIGINAL), *steps)
    before = len(rig.events(run_id))
    outcome = resume(rig, chain(ORIGINAL), run_id)
    assert outcome.status is RunStatus.COMPLETED
    assert trace(rig, run_id, before) == [
        ("run_resumed", None, None),
        ("step_rerun", "2", attempt),
        ("step_started", "2", attempt),
        ("step_completed", "2", attempt),
        ("step_started", "~end.check_model.m1", 1),
        ("step_completed", "~end.check_model.m1", 1),
        ("check_enforced", "~end.check_model.m1", None),
        ("run_completed", None, None),
    ]  # fmt: skip
    (rerun,) = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.StepRerun)]
    assert rerun.reason == "read_in_flight"
    assert [(c.tool, c.op_id) for c in host.ledger] == [("read_c", op_id(run_id, "2", attempt))]  # the same attempt
    assert "tool.reconcile" not in rig.log  # a read has no side effect to reconcile
    assert all(c[0] != "reconcile" for c in host.calls)


def test_reconciliation_gets_the_full_arguments_of_a_large_write(tmp_path: Path) -> None:
    big: dict[str, JsonValue] = {"n": 1, "model": "m1", "text": "x" * 20_000}  # stored by reference in the journal
    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)
    workflow = chain([("read_a", {"n": 0}), ("write_b", big), ("read_c", {"n": 2})])
    steps = (start("0", "read_a", {"n": 0}), done("0"), start("1", "write_b", big, write=True), bound("m1", INSTANCE))
    run_id = forge(rig, workflow, *steps)
    started = next(e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.StepStarted) and e.path == "1")
    assert started.args is None
    assert started.args_ref is not None
    assert resume(rig, workflow, run_id).status is RunStatus.COMPLETED
    assert host.reconciled_args == [big]


def test_a_write_without_an_op_id_is_a_journal_error(tmp_path: Path) -> None:
    rig, host = scripted_rig(tmp_path)
    kind, path, attempt, body = start("1", "write_b", WRITE_ARGS, write=True)
    run_id = forge(rig, chain(ORIGINAL), (kind, path, attempt, body | {"op_id": None}))
    with pytest.raises(JournalIntegrityError):
        resume(rig, chain(ORIGINAL), run_id)
    assert host.calls == []


def test_calc_in_flight(tmp_path: Path) -> None:
    rig, _ = scripted_rig(tmp_path)
    rig.calc_infos.append(
        CalcInfo(
            id="harness.demo", version=1, content_sha256="c" * 64, status=CalcStatus.APPROVED,
            engineering_params=(), basis_fields=(), ref_rules={},
        )
    )  # fmt: skip
    rig.calc_results["harness.demo"] = success(rig, {"y": 1})

    async def body(ctx: Any) -> list[str]:
        return [(await ctx.calc("harness.demo", {"a": 1})).ref.ref]

    args: dict[str, JsonValue] = {"a": 1}
    cut = (
        T.STEP_STARTED,
        "0",
        1,
        {"kind": "calc", "name": "harness.demo", "args": args, "args_sha256": payload_sha256(args), "effect": "none"},
    )
    run_id = forge(rig, flow(body), cut)
    before = len(rig.events(run_id))
    assert resume(rig, flow(body), run_id).status is RunStatus.COMPLETED
    assert trace(rig, run_id, before) == [
        ("run_resumed", None, None), ("step_rerun", "0", 1), ("step_started", "0", 1),
        ("step_completed", "0", 1), ("run_completed", None, None),
    ]  # fmt: skip
    assert rig.calc_runs == [("harness.demo", args)]


def test_a_partial_result_is_not_the_result_of_a_write_found_applied(tmp_path: Path) -> None:
    rig, host, run_id = _cut_off_write(tmp_path)
    partial = success(rig, {"tool": "write_b"})
    host.reconciliations[OP] = Reconciliation(outcome="partial", result=partial)
    resume(rig, chain(ORIGINAL), run_id)
    asked = rig.inputs.presented[-1]
    rig.inputs.script(asked.request_id, answer(asked, "applied", "outcome"))
    assert resume(rig, chain(ORIGINAL), run_id).status is RunStatus.COMPLETED
    (closing,) = _events(rig, run_id, ev.StepReconciled)
    assert closing.result is not None
    assert closing.result.ref != partial.result_id  # what the adapter found half done is not the write's result
    assert closing.result.summary == {}


UNREADABLE = ["adapter_result", "read_back", "read_back_raises", "engineer"]


def _found_applied_but_unreadable(host: ScriptedHost, cause: str) -> str:
    """Arrange that the write in flight is found applied and its result cannot be read; the code of the failure."""
    if cause == "engineer":  # the adapter cannot decide and the engineer will say `applied`
        _cannot_reconcile(host, "unknown")
    else:
        failed_result = failure(ErrorCode.HOST_BUSY) if cause == "adapter_result" else None
        host.reconciliations[OP] = Reconciliation(outcome="applied", result=failed_result)
    if cause == "read_back_raises":
        host.read_back_reply = ContractError(ErrorCode.HOST_ERROR, "the read-back failed", retryable=False)
        return "HOST_ERROR"
    if cause != "adapter_result":
        host.read_back_reply = failure(ErrorCode.HOST_BUSY)
    return "HOST_BUSY"


@pytest.mark.parametrize("cause", UNREADABLE)
def test_a_write_found_applied_whose_result_cannot_be_read_stays_in_flight(tmp_path: Path, cause: str) -> None:
    rig, host, run_id = _cut_off_write(tmp_path)
    code = _found_applied_but_unreadable(host, cause)
    if cause == "engineer":
        resume(rig, chain(ORIGINAL), run_id)
        asked = rig.inputs.presented[-1]
        rig.inputs.script(asked.request_id, answer(asked, "applied", "outcome"))
    stopped = resume(rig, chain(ORIGINAL), run_id)
    assert stopped.status is RunStatus.NEEDS_ENGINEER  # a failure is not "no read-back": nothing is journaled as done
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "needs_reconciliation"
    assert code in stopped.escalation.detail
    assert _events(rig, run_id, ev.StepReconciled) == []
    assert host.ledger == []  # the write is not sent again, and the block did not run on
    presented = len(rig.inputs.presented)
    reply = success(rig, {"tool": "write_b"})  # the read-back works at the next resume: the step is reconciled then
    host.read_back_reply = reply
    if cause != "engineer":
        host.reconciliations[OP] = Reconciliation(outcome="applied")
    assert resume(rig, chain(ORIGINAL), run_id).status is RunStatus.COMPLETED
    (closing,) = _events(rig, run_id, ev.StepReconciled)
    assert closing.outcome == "applied"
    assert closing.decided_by == ("engineer:test" if cause == "engineer" else "adapter")
    assert closing.result is not None
    assert closing.result.ref == reply.result_id
    # an answer given at the earlier resume is read from the journal: no second answer event, no new presentation
    assert len(_events(rig, run_id, ev.InputProvided)) == (1 if cause == "engineer" else 0)
    assert len(rig.inputs.presented) == presented


_ORDER = ("host.preflight", "host.acquire", "host.read_units", "tool.reconcile", "host.model_state", "tool.describe")


def test_resume_order_guards_reconciliation(tmp_path: Path) -> None:
    """A failing preflight, a refused lease or differing units stop the resume before any reconciliation (AC62)."""
    rig, host, run_id = _cut_off_write(tmp_path)
    workflow = chain(ORIGINAL)
    check = ServerCheck(
        server="csi", build="old", min_build="b", fingerprint="a", expected_fingerprint="a", ok=False, reason="old"
    )  # fmt: skip
    differ = UnitsState(loaded=True, ok=False, present="unit-system-b", expected="unit-system-a")
    held = HostLease(host_key="csi", lease_id="other-run")

    def stopped(leases: dict[str, HostLease], *, escalated: bool) -> None:
        """The write is still in flight, and nothing reconciled or compared the model (steps 7 and 8 did not run)."""
        assert not {"tool.reconcile", "host.model_state"} & set(rig.log)
        assert _events(rig, run_id, ev.StepReconciled) == []
        assert [e.type for e in rig.events(run_id)].count(T.RUN_ESCALATED) == int(escalated)
        assert host.ledger == []
        assert host.leases == leases  # a lease taken for the resume is released, another run's is not touched

    host.preflight_checks = [check]  # (a) step 4
    with pytest.raises(RunRefused) as refused:
        resume(rig, workflow, run_id)
    assert refused.value.code is HarnessCode.SERVER_CHECK_FAILED
    assert "host.acquire" not in rig.log  # no lease is taken after a failed check
    stopped({}, escalated=False)
    host.preflight_checks = None
    host.leases["csi"] = held  # (b) step 5
    with pytest.raises(ContractError) as locked:
        resume(rig, workflow, run_id)
    assert locked.value.detail.code is ErrorCode.HOST_LOCKED
    assert "host.read_units" not in rig.log  # units are read only for a leased host
    stopped({"csi": held}, escalated=False)
    del host.leases["csi"]
    host.units["m1"] = differ  # (c) step 6
    units = resume(rig, workflow, run_id)
    assert (units.status, units.escalation is not None and units.escalation.reason) == (
        RunStatus.NEEDS_ENGINEER, "units_mismatch",
    )  # fmt: skip
    stopped({}, escalated=True)
    host.units["m1"] = UnitsState(loaded=True, ok=True, present="unit-system-a", expected="unit-system-a")
    del rig.log[:]
    assert resume(rig, workflow, run_id).status is RunStatus.COMPLETED  # all three pass: the write is reconciled
    (closing,) = _events(rig, run_id, ev.StepReconciled)
    assert closing.op_id == OP
    ordered = [line for line in rig.log if line in _ORDER]
    assert ordered[:6] == list(_ORDER)  # preflight, acquire, units, reconcile, model state, then the first block call
    assert host.leases == {}


def test_approval_in_flight_is_presented_again_not_reconciled(tmp_path: Path) -> None:
    """Spec 4.5.3: an approval whose `step_started` has no end is marked for a rerun; the journal's answer stands."""
    rig = make_rig(tmp_path)
    shown = change_set(rig, "i1")

    async def body(ctx: Any) -> list[str]:
        await ctx.approve("Apply", shown)
        return []

    engine = rig.engine(flow(body))
    run_id = asyncio.run(engine.start(asking())).run_id
    rid, args = request_id(run_id, "0"), shown.model_dump(mode="json", by_alias=True)
    resolved = ev.ApprovalResolved(
        request_id=rid, shown_sha256=rig.approvals.presented[-1].shown_sha256, decision="approve",
        rejected_items=[], by="engineer:ada",
    )  # fmt: skip
    began = {
        "kind": "approve",
        "name": "change_set",
        "args": args,
        "args_sha256": payload_sha256(args),
        "effect": "none",
    }
    writer = JournalWriter(rig.run_dir(run_id), rig.store, rig.clock, rig.ids)
    writer.append(T.APPROVAL_RESOLVED, resolved)  # the crash came after the answer, inside the step
    writer.append(T.STEP_STARTED, began, path="0", attempt=1)
    writer.close()
    before = len(rig.events(run_id))
    outcome = asyncio.run(engine.resume(run_id))
    assert outcome.status is RunStatus.COMPLETED
    assert [t for t in trace(rig, run_id, before) if t[1] == "0"] == [
        ("step_rerun", "0", 1),
        ("step_started", "0", 1),
        ("step_completed", "0", 1),
    ]
    (rerun,) = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.StepRerun)]
    assert rerun.reason == "read_in_flight"
    assert len(rig.approvals.answers.get(rid, [])) == 0  # the journal's answer was used, the port was not asked
    assert [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.ApprovalResolved)] == [resolved]  # once


class Size(BaseModel):
    """The fields of the ask in `test_ask_in_flight_is_asked_again`."""

    width: str


def test_ask_in_flight_is_asked_again(tmp_path: Path) -> None:
    """Spec 4.5.3, AC36: an ask whose `step_started` has no end is marked for a rerun and presented again."""
    rig = make_rig(tmp_path)

    async def body(ctx: Any) -> list[str]:
        return [(await ctx.ask(Size, title="Size")).ref.ref]

    engine = rig.engine(flow(body))
    run_id = asyncio.run(engine.start(asking())).run_id
    ask = "ask_" + hashlib.sha256(f"{run_id}\n0".encode()).hexdigest()[:32]
    args = {"title": "Size", "fields": Size.model_json_schema()}
    began = {"kind": "ask", "name": "Size", "args": args, "args_sha256": payload_sha256(args), "effect": "none"}
    writer = JournalWriter(rig.run_dir(run_id), rig.store, rig.clock, rig.ids)
    writer.append(T.STEP_STARTED, began, path="0", attempt=1)  # the crash came after the step began
    writer.close()
    asked = rig.inputs.presented[-1]
    rig.inputs.script(
        ask, InputAnswer(request_id=ask, shown_sha256=asked.fields_schema_sha256, values={"width": "3"}, by="ada")
    )
    before = len(rig.events(run_id))
    outcome = asyncio.run(engine.resume(run_id))
    assert outcome.status is RunStatus.COMPLETED
    assert [t for t in trace(rig, run_id, before) if t[1] == "0"] == [
        ("step_rerun", "0", 1),
        ("step_started", "0", 1),
        ("step_completed", "0", 1),
    ]
    (rerun,) = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.StepRerun)]
    assert rerun.reason == "read_in_flight"
    assert [p.request_id for p in _events(rig, run_id, ev.InputProvided)] == [ask]  # answered once, not reconciled


class PowerCut(BaseException):
    """The process dies in the middle of the file copy: nothing in the engine may catch it."""


def _cut_promotion(
    root: Path, patch: pytest.MonkeyPatch, at: str
) -> tuple[Rig, Any, Any, str, list[object], tuple[Path, Path]]:
    """A run cut off in the file copy of its promotion: before any copy (`at` `copy`) or after the replace."""
    from eng_harness.engine import _promote  # here, so that the other tests of this file load without the module

    rig = mode_rig(root)
    files = give_files(rig, patch, root, "m1", b"original", b"accepted")
    stored_writes(rig, patch)

    class Cut(_promote.LocalFileOps):
        def copy(self, source: Path, target: Path) -> None:
            if at == "copy":
                raise PowerCut("the power was cut")
            super().copy(source, target)

        def replace(self, source: Path, target: Path) -> None:
            super().replace(source, target)
            raise PowerCut("the power was cut")

    workflow, seen = promoting(rig)
    engine, run_id = approved(rig, workflow)
    with patch.context() as cut:
        cut.setattr(_promote, "LocalFileOps", Cut)
        with pytest.raises(PowerCut, match="power"):
            asyncio.run(engine.resume(run_id))
    return rig, engine, workflow, run_id, seen, files


@pytest.mark.parametrize(("choice", "at"), [("applied", "replace"), ("not_applied", "copy"), ("abandon", "copy")])
def test_promote_in_flight_goes_to_the_engineer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, choice: str, at: str
) -> None:
    """Spec 4.5.3, §11 Q40: a promotion in flight is a write with no reconciler; the engineer says what became of it."""
    rig, engine, _, run_id, seen, (original, copy) = _cut_promotion(tmp_path, monkeypatch, at)
    (began,) = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.StepStarted) and e.path == "2"]
    assert (began.kind, began.effect, began.op_id) == ("promote", "write", op_id(run_id, "2", 1))
    stopped = asyncio.run(engine.resume(run_id))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    asked = rig.inputs.presented[-1]
    assert (asked.kind, options(asked, "outcome")) == ("engine.in_flight", ["applied", "not_applied", "abandon"])
    assert not {"tool.reconcile", "tool.read_back"} & set(rig.log)  # a file copy is never sent to the tool port
    rig.inputs.script(asked.request_id, answer(asked, choice, "outcome"))
    outcome = asyncio.run(engine.resume(run_id))
    state = rig.host.models["m1.copy"]
    if choice == "abandon":
        assert (outcome.status, seen) == (RunStatus.FAILED, [])
        return
    assert outcome.status is RunStatus.COMPLETED
    (closing,) = _events(rig, run_id, ev.StepReconciled)
    assert (closing.outcome, closing.decided_by) == (choice, "engineer:test")
    handle = ModelHandle(model_key="m1", model_id=state.model_id or "", revision=state.revision or 0)
    assert seen == [handle]
    assert (original.read_bytes(), copy.read_bytes()) == (b"accepted", b"accepted")
    assert (rig.run_dir(run_id) / "backups" / "m1.edb").read_bytes() == b"original"
    last = [e for e in rig.events(run_id) if e.path == "2"][-1]
    if choice == "applied":  # the result is the handle of the working copy's state, with no copy made again
        assert closing.result is not None
        assert closing.result.summary == handle.model_dump(mode="json")
        assert last.attempt == 1
    else:  # run again as attempt 2 under its own op_id; the approval its first attempt used does not bar it
        assert (last.type, last.attempt) == (T.STEP_COMPLETED, 2)


def test_a_promotion_found_applied_needs_the_working_copy_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec §11 Q40: `applied` completes the promotion from the working copy's state; with none the step stays open."""
    rig, engine, _, run_id, seen, _ = _cut_promotion(tmp_path, monkeypatch, "replace")
    asyncio.run(engine.resume(run_id))
    asked = rig.inputs.presented[-1]
    rig.inputs.script(asked.request_id, answer(asked, "applied", "outcome"))
    rig.host.models["m1.copy"] = HostModelState(loaded=False)
    stopped = asyncio.run(engine.resume(run_id))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.detail == (
        "the promotion at step 2 was found applied, but the working copy m1.copy is not open"
    )
    assert (_events(rig, run_id, ev.StepReconciled), seen) == (
        [],
        [],
    )  # still in flight: the next resume reads it again


def test_a_failing_copy_leaves_the_promotion_in_flight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec 4.5.3: a write step whose call raises is in flight at once, as `Ctx.tool` leaves it (a file still held)."""
    from eng_harness.engine import _promote

    rig = mode_rig(tmp_path)
    give_files(rig, monkeypatch, tmp_path, "m1", b"original", b"accepted")
    stored_writes(rig, monkeypatch)

    class Held(_promote.LocalFileOps):
        def replace(self, source: Path, target: Path) -> None:
            raise PermissionError("the file is held by the host program")

    workflow, seen = promoting(rig)
    engine, run_id = approved(rig, workflow)
    monkeypatch.setattr(_promote, "LocalFileOps", Held)
    stopped = asyncio.run(engine.resume(run_id))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "needs_reconciliation"
    assert "held by the host program" in stopped.escalation.detail
    assert [e for e in rig.events(run_id) if e.path == "2"][-1].type is T.STEP_STARTED  # no step_failed
    assert (T.STEP_FAILED not in [e.type for e in rig.events(run_id)], seen) == (True, [])
    again = asyncio.run(engine.resume(run_id))  # the next resume asks the engineer what became of the copy
    assert again.status is RunStatus.NEEDS_ENGINEER
    assert rig.inputs.presented[-1].kind == "engine.in_flight"


def test_a_not_applied_promotion_of_a_replaced_original_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec Q40, interim reading: `not_applied` runs the copy again; its hash check refuses a replaced original."""
    rig, engine, _, run_id, seen, (original, _) = _cut_promotion(tmp_path, monkeypatch, "replace")
    asyncio.run(engine.resume(run_id))
    asked = rig.inputs.presented[-1]
    rig.inputs.script(asked.request_id, answer(asked, "not_applied", "outcome"))
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    (closing,) = _events(rig, run_id, ev.StepReconciled)
    assert closing.outcome == "not_applied"
    last = [e for e in rig.events(run_id) if e.path == "2"][-1]
    assert (last.type, last.attempt) == (T.STEP_FAILED, 2)
    assert isinstance(last.payload, ev.StepFailed)
    assert isinstance(last.payload.error, ErrorDetail)
    assert last.payload.error.code is ErrorCode.CONFLICT
    assert [type(x) for x in seen] == [ContractError]
    assert original.read_bytes() == b"accepted"  # the replaced original is left as it is
    assert (rig.run_dir(run_id) / "backups" / "m1.edb").read_bytes() == b"original"  # and the backup is kept
