"""In-flight steps at a resume: reconciliation of writes and the rerun of reads (plan 0001 T11b; spec 0001 4.5.3).

Covers AC31 (a write in flight is reconciled before the block is called: `applied`, `not_applied`, and every other
outcome as a stop with an engineer request) and AC32 (a read or calc in flight runs again after `step_rerun`). The runs
are forged by hand, because a cut-off between a step's start and its end cannot be reached through the public API: the
journal holds the steps up to the cut, and a new engine resumes it as a new process would. The fake host's reconciler
answers per `op_id`; its call log and the rig's port-call log show what the resume asked of the ports.
"""

from pathlib import Path
from typing import Any

import pytest
from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode
from pydantic import JsonValue
from workflows.chain import ORIGINAL, ChainOutput, chain
from workflows.ctx_flows import flow, success
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
from workflows.rig import Rig

from eng_harness.calc import CalcStatus
from eng_harness.engine import RunStatus
from eng_harness.engine._steps import op_id
from eng_harness.errors import JournalIntegrityError
from eng_harness.journal import EventType, JournalReader
from eng_harness.journal import _events as ev
from eng_harness.ports import CalcInfo, Reconciliation

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
            *reconciled, ("step_started", "1", 2), ("step_completed", "1", 2),
            ("step_started", "2", 1), ("step_completed", "2", 1), ("run_completed", None, None),
        ]  # fmt: skip
        assert [(c.tool, c.op_id) for c in host.ledger][:1] == [("write_b", op_id(run_id, "1", 2))]
        assert op_id(run_id, "1", 2) != OP
        return
    assert closing.outcome == "applied"  # returns the reconciled result: no call
    assert trace(rig, run_id, before) == [
        *reconciled, ("step_started", "2", 1), ("step_completed", "2", 1), ("run_completed", None, None),
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
        ("run_resumed", None, None), ("step_rerun", "2", attempt), ("step_started", "2", attempt),
        ("step_completed", "2", attempt), ("run_completed", None, None),
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
