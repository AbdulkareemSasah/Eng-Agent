"""The host-state check before live execution, instance binding, and lost or reopened models (plan 0001 T11c).

Covers spec 0001 AC34 (the three choices `accept`, `restore`, `abandon`), AC63 (a host crash with a write in flight:
no reconciliation, `model_not_loaded`, `restore` binds the new instance and reads units against it before any live
step) and AC64 (the `first_use` binding, and a model reopened in another instance), with the resume order of 4.5.1
steps 6 to 8. The runs are forged by hand (`workflows/hoststate.py`): the journal holds the steps up to the stop and
the fake host holds the state the test wants to find; a new engine resumes the run as a new process would. The host's
call log names the instance of every `read_units` and `model_state`. A process that dies between the journal writes
of a restore is forged by making the journal refuse the write (`DiedError`): the next resume must stay safe at each.
"""

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from eng_contract.canonical import payload_sha256
from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.errors import ErrorCode
from fakes.ports import failure
from pydantic import BaseModel, JsonValue
from workflows.chain import ORIGINAL, ChainOutput, chain
from workflows.hoststate import (
    INSTANCE,
    OP,
    REF,
    REOPENED,
    Forged,
    ScriptedHost,
    answer,
    bound,
    done,
    forge,
    options,
    resume,
    saved,
    scripted_rig,
    start,
)
from workflows.rig import Rig, request

from eng_harness.block import BlockDef
from eng_harness.engine import RunStatus
from eng_harness.engine._inflight import ResumeIndex
from eng_harness.engine._steps import op_id
from eng_harness.journal import EventType, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import Reconciliation, UnitsState

T = EventType
M1: dict[str, JsonValue] = {"n": 1, "model": "m1"}
M2: dict[str, JsonValue] = {"n": 1, "model": "m2"}


def _drift(host: ScriptedHost, model: str = "m1") -> None:
    """The engineer changed the model while the run was stopped: another revision and fingerprint."""
    host.models[model] = host.models[model].model_copy(update={"revision": 5, "fingerprint": "fp5"})


def _result(rig: Rig, host: ScriptedHost, revision: int | None = None, *, hosted: bool = True) -> str:
    """Store the result of a write on m1 and return its id; `provenance.host` names the revision (the host's)."""
    state = host.models["m1"]
    wrote = state.revision or 0 if revision is None else revision
    info = HostInfo(program="csi", version="1", model_id=state.model_id or "", model_revision=wrote)
    producer = Provenance(
        tool="harness", tool_version="fake", host=info if hosted else None, inputs={}, started_at=rig.clock.now(),
        duration_ms=0,
    )  # fmt: skip
    return rig.store.put("harness.run_output/1", {"value": {}}, producer).result_id


def _written(root: Path, *, completed: bool = True, wrote: int | None = None) -> tuple[Rig, ScriptedHost, str]:
    """A run of `ORIGINAL` stopped after its write: m1 bound, saved, then written (completed, or still in flight).

    The result of a completed write names the host's revision at that time, or `wrote` when given.
    """
    rig, host = scripted_rig(root)
    host.add_model("m1", INSTANCE)
    steps: list[Forged] = [start("0", "read_a", {"n": 0}), done("0"), bound("m1", INSTANCE), saved(rig, "m1")]
    steps += [start("1", "write_b", M1, write=True), *([done("1", ref=_result(rig, host, wrote))] if completed else [])]
    return rig, host, forge(rig, chain(ORIGINAL), *steps)


def _kinds(rig: Rig, run_id: str, *kinds: EventType) -> list[Any]:
    return [e.payload for e in rig.events(run_id) if e.type in kinds]


def _bound_before_step(rig: Rig, run_id: str) -> bool:
    """True when the first `model_bound` of the run precedes the first `step_started` addressed to m1 (AC64)."""
    events = rig.events(run_id)
    bound_at = next(e.seq for e in events if e.type is T.MODEL_BOUND)
    began = (e.seq for e in events if isinstance(e.payload, ev.StepStarted) and e.payload.model_key == "m1")
    return bound_at < next(began)


def _housekeeping(rig: Rig, run_id: str, number: int) -> list[str]:
    """The paths of the `@resume<number>` steps, in order of their start."""
    paths = [e.path or "" for e in rig.events(run_id) if e.type is T.STEP_STARTED]
    return [path for path in paths if path.startswith(f"@resume{number}.")]


@pytest.mark.parametrize("choice", ["accept", "restore", "abandon"])
def test_three_choices(tmp_path: Path, choice: str) -> None:
    rig, host, run_id = _written(tmp_path)
    _drift(host)
    stopped = resume(rig, chain(ORIGINAL), run_id)
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "host_state_mismatch"
    asked = rig.inputs.presented[-1]
    assert (asked.kind, asked.fields_schema["x-eng-input"]) == ("engine.host_state", "choice")
    assert options(asked, "state") == ["accept", "restore", "abandon"]
    assert stopped.escalation.request_id == asked.request_id
    assert host.ledger == []  # nothing ran live
    assert ("model_state", "m1", "csi-1") in host.calls
    assert _housekeeping(rig, run_id, 1) == ["@resume1.units.m1", "@resume1.model_state.m1"]
    rig.inputs.script(asked.request_id, answer(asked, choice, "state"))
    mark = len(rig.events(run_id))
    outcome = resume(rig, chain(ORIGINAL), run_id)
    (provided,) = _kinds(rig, run_id, T.INPUT_PROVIDED)
    assert (provided.request_id, provided.by) == (asked.request_id, "engineer:test")
    if choice == "abandon":
        assert (outcome.status, host.ledger) == (RunStatus.FAILED, [])
        assert _kinds(rig, run_id, T.RUN_FAILED) == [ev.RunFailed(reason="abandoned", by="engineer:test")]
        return
    assert outcome.status is RunStatus.COMPLETED
    if (
        choice == "accept"
    ):  # the differences are the engineer's: a new baseline, and the run goes on with nothing replayed
        (baseline,) = _kinds(rig, run_id, T.MODEL_SAVED)[1:]
        assert (baseline.role, baseline.revision, baseline.fingerprint) == ("baseline", 5, "fp5")
        assert [c.tool for c in host.ledger] == ["read_c"]
        return
    # restore: the saved copy comes back in a new instance; the write after the save runs again as a new attempt
    saved_seq = next(e.seq for e in rig.events(run_id) if e.type is T.MODEL_SAVED)
    (resumed,) = [p for p in _kinds(rig, run_id, T.RUN_RESUMED) if p.restored_to_seq is not None]
    assert resumed.restored_to_seq == saved_seq
    events = rig.events(run_id)[mark:]
    (rebound,) = [e.payload for e in events if isinstance(e.payload, ev.ModelBound)]
    assert (rebound.reason, rebound.instance_id) == ("restored", "csi-1+r")
    assert [e.payload.instance_id for e in events if isinstance(e.payload, ev.HostStarted)] == ["csi-1+r"]
    assert [(c.tool, c.op_id) for c in host.ledger] == [
        ("write_b", op_id(run_id, "1", 2)), ("read_c", op_id(run_id, "2", 1)),
    ]  # fmt: skip
    assert host.models["m1"].revision == 1  # applied once, on the restored copy
    assert isinstance(outcome.output, ChainOutput)
    assert outcome.output.refs[0] == REF


def test_matching_state_continues_without_a_request(tmp_path: Path) -> None:
    rig, host, run_id = _written(tmp_path)
    outcome = resume(rig, chain(ORIGINAL), run_id)
    assert outcome.status is RunStatus.COMPLETED
    assert rig.inputs.presented == []
    assert _housekeeping(rig, run_id, 1) == ["@resume1.units.m1", "@resume1.model_state.m1"]
    assert [c for c in host.calls if c[0] in ("read_units", "model_state")] == [
        ("read_units", "m1", "csi-1"), ("model_state", "m1", "csi-1"),
    ]  # fmt: skip
    assert [c.tool for c in host.ledger] == ["read_c"]


def test_restore_is_not_offered_after_another_model_was_written(tmp_path: Path) -> None:
    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)
    host.add_model("m2", INSTANCE)
    steps = (
        start("0", "write_b", M1, write=True),
        done("0"),
        bound("m1", INSTANCE),
        bound("m2", INSTANCE),
        saved(rig, "m1"),
        start("1", "write_b", M2, write=True),
        done("1"),
    )
    run_id = forge(rig, chain(ORIGINAL), *steps)  # m2 was written after m1's last save
    _drift(host)
    resume(rig, chain(ORIGINAL), run_id)  # a restore of m1 would repeat the write on m2
    assert options(rig.inputs.presented[-1], "state") == ["accept", "abandon"]


@pytest.mark.parametrize(("revision", "matches"), [(1, True), (2, False)])
def test_a_reconciled_write_is_compared_with_its_result(tmp_path: Path, revision: int, matches: bool) -> None:
    rig, host, run_id = _written(tmp_path, completed=False)
    state = host.models["m1"]
    host.models["m1"] = state.model_copy(update={"revision": revision, "fingerprint": f"fp{revision}"})
    info = HostInfo(program="csi", version="1", model_id=state.model_id or "", model_revision=1)
    producer = Provenance(
        tool="harness", tool_version="fake", host=info, inputs={}, started_at=rig.clock.now(), duration_ms=0
    )
    stored = rig.store.put("harness.run_output/1", {"value": {}}, producer)
    reply = SuccessEnvelope(
        contract="eng-contract/1", ok=True, result_id=stored.result_id, kind="harness.run_output/1", summary={},
        complete=True, provenance=producer,
    )  # fmt: skip
    host.reconciliations[OP] = Reconciliation(outcome="applied", result=reply)  # the write made revision 1
    outcome = resume(rig, chain(ORIGINAL), run_id)
    # the host is at the revision the reconciled result names, not at the last save's: no mismatch; at another: one
    assert (outcome.status is RunStatus.COMPLETED) is matches
    assert (rig.inputs.presented == []) is matches


@pytest.mark.parametrize(("revision", "matches"), [(1, True), (2, False)])
def test_a_completed_write_is_compared_with_its_result(tmp_path: Path, revision: int, matches: bool) -> None:
    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)
    steps = [start("0", "read_a", {"n": 0}), done("0"), bound("m1", INSTANCE), saved(rig, "m1")]  # saved at revision 0
    steps += [start("1", "write_b", M1, write=True), done("1", ref=_result(rig, host, 1))]  # the write made revision 1
    run_id = forge(rig, chain(ORIGINAL), *steps)
    host.models["m1"] = host.models["m1"].model_copy(update={"revision": revision, "fingerprint": f"fp{revision}"})
    outcome = resume(rig, chain(ORIGINAL), run_id)
    # the host is at the revision the write's result names, not at the save's: no mismatch; at another: one
    assert (outcome.status is RunStatus.COMPLETED) is matches
    assert (rig.inputs.presented == []) is matches


@pytest.mark.parametrize("drifted", [False, True])
def test_a_result_without_host_info_leaves_the_save_as_the_comparison(tmp_path: Path, drifted: bool) -> None:
    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)
    steps = [start("0", "read_a", {"n": 0}), done("0"), bound("m1", INSTANCE), saved(rig, "m1")]
    steps += [start("1", "write_b", M1, write=True), done("1", ref=_result(rig, host, hosted=False))]
    run_id = forge(rig, chain(ORIGINAL), *steps)
    if drifted:
        _drift(host)
    outcome = resume(rig, chain(ORIGINAL), run_id)  # nothing to compare with but the save: it decides
    assert (outcome.status is RunStatus.NEEDS_ENGINEER) is drifted
    assert (rig.inputs.presented == []) is not drifted


def test_a_second_mismatch_after_a_restore_is_a_new_request(tmp_path: Path) -> None:
    rig, host, run_id = _written(tmp_path)
    _drift(host)
    resume(rig, chain(ORIGINAL), run_id)
    first = rig.inputs.presented[-1]
    rig.inputs.script(first.request_id, answer(first, "restore", "state"))
    host.restored_units = UnitsState(loaded=True, ok=False, present="unit-system-b", expected="unit-system-a")
    assert resume(rig, chain(ORIGINAL), run_id).escalation is not None  # restored, then stopped on the units
    host.units["m1"] = UnitsState(loaded=True, ok=True, present="unit-system-a", expected="unit-system-a")
    _drift(host)  # the engineer changes the restored model again
    stopped = resume(rig, chain(ORIGINAL), run_id)
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "host_state_mismatch"
    assert rig.inputs.presented[-1].request_id != first.request_id  # the earlier answer does not decide this one
    assert host.ledger == []


def test_host_crash_with_write_in_flight(tmp_path: Path) -> None:
    rig, host, run_id = _written(tmp_path, completed=False)
    host.crash("csi")  # every model is reported not loaded; the write after the save was in flight
    stopped = resume(rig, chain(ORIGINAL), run_id)
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "host_state_mismatch"
    asked = rig.inputs.presented[-1]
    assert (asked.kind, options(asked, "state")) == ("engine.host_state", ["restore", "abandon"])  # nothing to accept
    assert all(c[0] != "reconcile" for c in host.calls)  # a lost model is never reconciled
    assert "tool.reconcile" not in rig.log
    assert ("locate", "m1", None) in host.calls
    assert host.ledger == []
    assert _kinds(rig, run_id, T.STEP_RECONCILED) == []  # the write stays in flight
    rig.inputs.script(asked.request_id, answer(asked, "restore", "state"))
    outcome = resume(rig, chain(ORIGINAL), run_id)
    assert outcome.status is RunStatus.COMPLETED
    events = rig.events(run_id)
    (restored,) = [e for e in events if isinstance(e.payload, ev.ModelBound) and e.payload.reason == "restored"]
    assert isinstance(restored.payload, ev.ModelBound)
    assert restored.payload.instance_id == "csi-1+r"
    units = next(e for e in events if e.path == "@resume2.units_restored.m1" and e.type is T.STEP_STARTED)
    units_done = next(e for e in events if e.path == "@resume2.units_restored.m1" and e.type is T.STEP_COMPLETED)
    assert isinstance(units_done.payload, ev.StepCompleted)
    assert units_done.payload.result is not None
    assert units_done.payload.result.summary["loaded"] is True
    assert ("read_units", "m1", "csi-1+r") in host.calls  # read against the new instance
    rerun = next(e for e in events if e.type is T.STEP_RERUN)
    assert isinstance(rerun.payload, ev.StepRerun)
    assert (rerun.path, rerun.attempt, rerun.payload.reason) == ("1", 1, "restored")
    live = next(e for e in events if e.type is T.STEP_STARTED and (e.path, e.attempt) == ("1", 2))
    assert (
        restored.seq < units.seq < rerun.seq < live.seq
    )  # bound, then units, then the rerun, then the first live step
    assert [(c.tool, c.op_id) for c in host.ledger][:1] == [("write_b", op_id(run_id, "1", 2))]
    assert all(c[0] != "reconcile" for c in host.calls)


def test_units_after_a_restore_that_differ_stop_the_run(tmp_path: Path) -> None:
    rig, host, run_id = _written(tmp_path, completed=False)
    host.crash("csi")
    host.restored_units = UnitsState(loaded=True, ok=False, present="unit-system-b", expected="unit-system-a")
    resume(rig, chain(ORIGINAL), run_id)
    asked = rig.inputs.presented[-1]
    rig.inputs.script(asked.request_id, answer(asked, "restore", "state"))
    stopped = resume(rig, chain(ORIGINAL), run_id)
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "units_mismatch"
    assert host.ledger == []  # no live step ran on a model whose units differ
    resume(rig, chain(ORIGINAL), run_id)  # the restore is journaled: the next resume reads the restored instance
    assert [p.resume_no for p in _kinds(rig, run_id, T.RUN_RESUMED)] == [
        1,
        2,
        2,
        3,
    ]  # the cut shares its resume's number
    assert "@resume3.units.m1" in _housekeeping(rig, run_id, 3)


def test_units_that_differ_stop_the_run_before_reconciliation(tmp_path: Path) -> None:
    rig, host, run_id = _written(tmp_path, completed=False)
    host.units["m1"] = UnitsState(loaded=True, ok=False, present="unit-system-b", expected="unit-system-a")
    stopped = resume(rig, chain(ORIGINAL), run_id)
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    assert stopped.escalation is not None
    assert (stopped.escalation.reason, stopped.escalation.request_id) == ("units_mismatch", None)
    assert all(c[0] != "reconcile" for c in host.calls)
    assert _kinds(rig, run_id, T.STEP_RECONCILED) == []  # the write is still in flight for the next resume
    assert host.ledger == []


def test_first_use_binding(tmp_path: Path) -> None:
    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)  # the engine did not start this instance
    host.script("read_c", failure(ErrorCode.HOST_BUSY))  # the run stops after its write, at its last step
    stopped = asyncio.run(rig.engine(chain(ORIGINAL)).start(request(values={"count": 3})))
    assert stopped.status is RunStatus.NEEDS_ENGINEER
    run_id = stopped.run_id
    (first,) = _kinds(rig, run_id, T.MODEL_BOUND)  # once, for the first step addressed to the model
    assert first == ev.ModelBound(
        model_key="m1", host_key="csi", instance_id="csi-1", reason="first_use", file_names=["m1.edb"]
    )
    assert _bound_before_step(rig, run_id)  # the binding lands before the `step_started` of the step addressed to m1
    named = [c[:2] for c in host.calls if c[1] in ("m1", "write_b")]
    assert named == [("locate", "m1"), ("read_units", "m1"), ("call", "write_b")]  # located and verified, then written
    assert resume(rig, chain(ORIGINAL), run_id).status is RunStatus.COMPLETED
    assert [c for c in host.calls if c[0] in ("read_units", "model_state")] == [
        ("read_units", "m1", "csi-1"), ("read_units", "m1", "csi-1"), ("model_state", "m1", "csi-1"),
    ]  # fmt: skip  # the first use, then the resume: every read names the instance of the first use
    assert len(_kinds(rig, run_id, T.MODEL_BOUND)) == 1  # the binding is not repeated at the resume


def test_units_recorded_before_the_step_started(tmp_path: Path) -> None:
    """A process that died between the units of a first use and the step itself: the resume finds the recorded units."""
    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)
    args = {"model_key": "m1"}
    units = {"kind": "read", "name": "units", "args": args, "args_sha256": payload_sha256(args), "effect": "read"}
    units |= {"model_key": "m1"}
    path = "1~pre.units.m1"
    run_id = forge(rig, chain(ORIGINAL), bound("m1", INSTANCE), (T.STEP_STARTED, path, 1, units), done(path))
    assert resume(rig, chain(ORIGINAL), run_id).status is RunStatus.COMPLETED  # the recorded step is visited
    started = [e.path for e in rig.events(run_id) if e.type is T.STEP_STARTED]
    assert started.count(path) == 1
    assert [c[:2] for c in host.calls if c[0] == "read_units"] == [("read_units", "m1")]  # the resume's, not a second


SECOND: dict[str, JsonValue] = {"n": 2, "model": "m1"}
TWO_WRITES: list[tuple[str, dict[str, JsonValue]]] = [
    ("read_a", {"n": 0}),
    ("write_b", M1),
    ("write_b", SECOND),
    ("read_c", {"n": 3}),
]


def _reopened(root: Path, after_save: str) -> tuple[Rig, ScriptedHost, BlockDef[Any, Any], str]:
    """A run stopped after its first write and a save of m1, then a second write (none, completed or in flight).

    The engineer closed the host and reopened the model's last saved file: a new instance holds the saved state.
    """
    rig, host = scripted_rig(root)
    host.add_model("m1", INSTANCE)
    host.models["m1"] = host.models["m1"].model_copy(update={"revision": 1, "fingerprint": "fp1"})  # the first write
    workflow = chain(TWO_WRITES)
    steps: list[Forged] = [start("0", "read_a", {"n": 0}), done("0"), bound("m1", INSTANCE)]
    steps += [start("1", "write_b", M1, write=True), done("1"), saved(rig, "m1")]
    if after_save != "none":
        steps += [start("2", "write_b", SECOND, write=True), *([done("2")] if after_save == "completed" else [])]
    run_id = forge(rig, workflow, *steps)
    host.bound["m1"] = REOPENED.instance_id
    host.instances["csi"].append(REOPENED)
    return rig, host, workflow, run_id


@pytest.mark.parametrize("after_save", ["none", "completed", "in_flight"])
def test_reopened_in_new_instance(tmp_path: Path, after_save: str) -> None:
    live, lhost = scripted_rig(tmp_path / "live")
    lhost.add_model("m1", INSTANCE)  # first the run binds the model at its first use, before the step that addresses it
    first = asyncio.run(live.engine(chain(TWO_WRITES)).start(request(values={"count": 3})))
    assert first.status is RunStatus.COMPLETED
    assert _bound_before_step(live, first.run_id)
    assert [p.reason for p in _kinds(live, first.run_id, T.MODEL_BOUND)] == ["first_use"]
    rig, host, workflow, run_id = _reopened(tmp_path, after_save)
    outcome = resume(rig, workflow, run_id)
    rebound = [p for p in _kinds(rig, run_id, T.MODEL_BOUND) if p.reason == "reopened"]
    assert [(p.model_key, p.instance_id) for p in rebound] == [("m1", "csi-2")]  # journaled in every case
    assert [c for c in host.calls if c[0] in ("read_units", "model_state")][:2] == [
        ("read_units", "m1", "csi-1"),
        ("read_units", "m1", "csi-2"),
    ]  # the old instance does not have it; the units are read against the new binding
    assert _housekeeping(rig, run_id, 1)[:2] == ["@resume1.units.m1", "@resume1.units_reopened.m1"]
    assert all(c[2] in (None, "csi-2") for c in host.calls if c[0] == "model_state")
    assert all(c[0] != "reconcile" for c in host.calls)  # the host's memory since the save is gone: no reconciler
    if after_save == "none":  # the check compares with that save; on a match the run goes on with no request
        assert outcome.status is RunStatus.COMPLETED
        assert rig.inputs.presented == []
        assert ("model_state", "m1", "csi-2") in host.calls
        return
    assert outcome.status is RunStatus.NEEDS_ENGINEER  # the reopened file cannot hold the write
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "host_state_mismatch"
    asked = rig.inputs.presented[-1]
    assert options(asked, "state") == ["restore", "abandon"]
    assert host.ledger == []
    again = resume(rig, workflow, run_id)  # a resume with no answer yet finds the same difference: nothing runs on
    assert again.escalation is not None
    assert (again.escalation.reason, again.escalation.request_id) == ("host_state_mismatch", asked.request_id)
    assert all(c[0] != "reconcile" for c in host.calls)
    assert host.ledger == []


def test_units_of_a_reopened_model_that_differ_stop_the_run(tmp_path: Path) -> None:
    rig, host, workflow, run_id = _reopened(tmp_path, "none")
    host.units["m1"] = UnitsState(loaded=True, ok=False, present="unit-system-b", expected="unit-system-a")
    stopped = resume(rig, workflow, run_id)
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "units_mismatch"
    assert ("read_units", "m1", "csi-2") in host.calls  # read against the new binding
    assert rig.inputs.presented == []
    assert host.ledger == []


def test_restore_in_the_instance_that_holds_the_model(tmp_path: Path) -> None:
    rig, host, workflow, run_id = _reopened(tmp_path, "completed")
    host.in_place = True  # the reopened instance still runs: restore does not start another
    resume(rig, workflow, run_id)
    asked = rig.inputs.presented[-1]
    rig.inputs.script(asked.request_id, answer(asked, "restore", "state"))
    outcome = resume(rig, workflow, run_id)
    assert outcome.status is RunStatus.COMPLETED
    assert _kinds(rig, run_id, T.HOST_STARTED) == []  # the engine started no instance
    assert [(p.reason, p.instance_id) for p in _kinds(rig, run_id, T.MODEL_BOUND)] == [
        ("first_use", "csi-1"), ("reopened", "csi-2"), ("restored", "csi-2"),
    ]  # fmt: skip
    assert [(c.tool, c.op_id) for c in host.ledger][:1] == [("write_b", op_id(run_id, "2", 2))]  # a new attempt


def test_a_lost_model_without_a_save_offers_only_abandon(tmp_path: Path) -> None:
    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)
    run_id = forge(rig, chain(ORIGINAL), start("1", "write_b", M1, write=True), bound("m1", INSTANCE))
    host.crash("csi")  # nothing was saved: there is no state to restore
    resume(rig, chain(ORIGINAL), run_id)
    assert options(rig.inputs.presented[-1], "state") == ["abandon"]
    assert all(c[0] != "reconcile" for c in host.calls)


def test_the_cut_of_a_restore_leaves_the_new_attempt_to_later_resumes(tmp_path: Path) -> None:
    rig, host, run_id = _written(tmp_path)
    _drift(host)
    resume(rig, chain(ORIGINAL), run_id)
    asked = rig.inputs.presented[-1]
    rig.inputs.script(asked.request_id, answer(asked, "restore", "state"))
    assert resume(rig, chain(ORIGINAL), run_id).status is RunStatus.COMPLETED
    index = ResumeIndex(rig.events(run_id))
    found = index.lookup("1", "tool", "write_b", payload_sha256(M1))
    assert found is not None
    assert found.attempt == 2  # the write after the restore, not the one the cut superseded
    assert isinstance(found.outcome, ev.StepResult)
    index.lookup("0", "tool", "read_a", payload_sha256({"n": 0}))
    index.lookup("2", "tool", "read_c", payload_sha256({"n": 2}))
    index.lookup("~end.check_model.m1", "read", "check_model", payload_sha256({"model": "m1"}))
    index.finish()  # every recorded path was visited: nothing hidden, nothing left over


class DiedError(Exception):
    """The process died before a journal write (a test double): that write did not happen."""


_RESTORE_WRITES = (T.RUN_RESUMED, T.HOST_STARTED, T.MODEL_BOUND)  # the cut, the instance and the binding of a restore


def _die_in_restore(monkeypatch: pytest.MonkeyPatch, host: ScriptedHost, allowed: int) -> None:
    """Make the process die at the journal write of a restore that follows `allowed` of them (from `restore` on)."""
    real, seen = JournalWriter.append, 0

    def append(
        self: JournalWriter,
        type_: EventType,
        payload: BaseModel | Mapping[str, object],
        *,
        path: str | None = None,
        attempt: int | None = None,
    ) -> int:
        nonlocal seen
        if type_ in _RESTORE_WRITES and any(call[0] == "restore" for call in host.calls):
            seen += 1
            if seen > allowed:
                raise DiedError
        return real(self, type_, payload, path=path, attempt=attempt)

    monkeypatch.setattr(JournalWriter, "append", append)


@pytest.mark.parametrize("allowed", [0, 1, 2])
@pytest.mark.parametrize("after_save", ["completed", "in_flight"])
def test_a_crash_inside_the_restore_is_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, after_save: str, allowed: int
) -> None:
    """The process dies after `allowed` of the journal writes of a restore (the cut, `host_started`, `model_bound`).

    The host has restored the saved copy by then. Whatever the journal holds, the next resume never reconciles the
    write after the save against the restored model, never offers `accept` (the journal holds writes the restored
    model lacks), and the write after the save runs again as a new attempt (4.5.4).
    """
    rig, host, run_id = _written(tmp_path, completed=after_save == "completed", wrote=1)
    if after_save == "completed":
        _drift(host)  # the engineer changed the model: the write's result names revision 1, the host is at 5
    else:
        host.crash("csi")  # the host crashed with the write in flight: the model is not loaded
    resume(rig, chain(ORIGINAL), run_id)
    asked = rig.inputs.presented[-1]
    rig.inputs.script(asked.request_id, answer(asked, "restore", "state"))
    _die_in_restore(monkeypatch, host, allowed)
    with pytest.raises(DiedError):
        resume(rig, chain(ORIGINAL), run_id)
    monkeypatch.undo()
    for _ in range(3):
        outcome = resume(rig, chain(ORIGINAL), run_id)
        if outcome.status is not RunStatus.NEEDS_ENGINEER:
            break
        again = rig.inputs.presented[-1]  # the file the host reopened lacks the write: restore it again or abandon
        assert options(again, "state") == ["restore", "abandon"]
        rig.inputs.script(again.request_id, answer(again, "restore", "state"))
    assert outcome.status is RunStatus.COMPLETED
    assert all(c[0] != "reconcile" for c in host.calls)  # the restored model is never reconciled
    assert [(c.tool, c.op_id) for c in host.ledger] == [
        ("write_b", op_id(run_id, "1", 2)), ("read_c", op_id(run_id, "2", 1)),
    ]  # fmt: skip


COPY = "0~post.working_copy.m1"


def _open(path: str = "0", *, flag: bool | None = True) -> Forged:
    """The `step_started` of a write `open` of m1; `flag` is its recorded `opens_model_without_writing` (B-562)."""
    kind, at, attempt, body = start(path, "open_w", {"model": "m1"}, write=True)
    marked = {} if flag is None else {"opens_model_without_writing": flag}
    return kind, at, attempt, body | {"action": "open"} | marked


def _copy_saved(rig: Rig, host: ScriptedHost, copy: str = "m1@copy", role: str = "working_copy") -> Forged:
    host.add_model(copy, INSTANCE)
    kind, _, _, body = saved(rig, copy, role)
    return kind, COPY, None, body


def _handoff(rig: Rig, host: ScriptedHost, case: str) -> list[Forged]:
    """A forged EC1 handoff of m1 to `m1@copy` (engine 4.5.4), altered by `case`."""
    args: dict[str, JsonValue] = {"model": "m1"}
    copy_start = (T.STEP_STARTED, COPY, 1, {
        "kind": "read", "name": "working_copy", "args": args, "args_sha256": payload_sha256(args), "effect": "read",
        "model_key": "m1",
    })  # fmt: skip
    summary = {"model": "m2" if case == "other_origin" else "m1", "copy": "m1" if case == "same_key" else "m1@copy"}
    copy_done = (T.STEP_COMPLETED, COPY, 1, {
        "result": {"ref": REF, "summary": summary, "warnings": [], "complete": True}, "duration_ms": 0,
    })  # fmt: skip
    applied: dict[str, Any] = {"op_id": OP, "outcome": "applied", "decided_by": "engineer:test", "evidence": []}
    closing: Forged = {
        "applied": (T.STEP_RECONCILED, "0", 1, applied | {"result": done("0")[3]["result"]}),
        "not_applied": (T.STEP_RECONCILED, "0", 1, applied | {"outcome": "not_applied", "result": None}),
    }.get(case, done("0"))
    saved_copy = _copy_saved(rig, host, role="revision" if case == "other_role" else "working_copy")
    events: list[Forged] = [_open(flag=None if case == "legacy" else case != "unflagged"), closing]
    events += [bound("m1", INSTANCE), copy_start, saved_copy, copy_done]
    if case == "pending":
        events.remove(closing)
    elif case == "copy_cut_off":
        events.remove(copy_done)
    elif case == "save_outside":
        events[3:5] = [saved_copy, copy_start]
    elif case == "before_outcome":
        events[1:4] = [bound("m1", INSTANCE), copy_start, closing]
    elif case == "rebound":
        events.append(bound("m1", REOPENED, "reopened"))
    elif case == "content_write":
        events += [start("1", "write_b", M1, write=True), done("1")]
    elif case == "pending_write":
        events.append(start("1", "write_b", M1, write=True))
    elif case == "restored":
        events.append((T.RUN_RESUMED, None, None, {"resume_no": 1, "code_hash_changed": False, "servers": [],
                                                  "restored_to_seq": 1}))  # fmt: skip
    return events


@pytest.mark.parametrize(
    ("case", "proven"),
    [
        ("complete", True), ("applied", True), ("legacy", False), ("unflagged", False), ("pending", False),
        ("not_applied", False), ("copy_cut_off", False), ("same_key", False), ("other_origin", False),
        ("other_role", False), ("save_outside", False), ("before_outcome", False), ("rebound", False),
        ("content_write", False), ("pending_write", False), ("restored", False),
    ],
)  # fmt: skip
def test_the_ec1_handoff_needs_its_whole_journal_proof(tmp_path: Path, case: str, proven: bool) -> None:
    """Engine 4.5.4 (B-562): the unloaded original is left out of the check only on the journaled EC1 handoff."""
    from eng_harness.engine._hoststate import handed_off
    from eng_harness.engine._inflight import Fold

    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)
    run_id = forge(rig, chain(ORIGINAL), *_handoff(rig, host, case))
    assert handed_off(Fold(rig.events(run_id)), "m1") is proven
    assert handed_off(Fold(rig.events(run_id)), "m2") is False  # a model with no write


@pytest.mark.parametrize(
    ("flag", "closed", "counted"),
    [(True, "done", False), (True, "applied", False), (True, None, True), (False, "done", True), (None, "done", True)],
)
def test_content_writes_leave_out_only_resolved_content_free_opens(
    tmp_path: Path, flag: bool | None, closed: str | None, counted: bool
) -> None:
    """Engine 4.5.4 (B-562): the content view drops a marked open that completed or was applied; a pending one, a
    legacy one and an unmarked one stay, also among the writes a reopened file lacks. The raw view keeps them all."""
    from eng_harness.engine._inflight import Fold

    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)
    ending = {"done": [done("0")], None: []}.get(closed, [(T.STEP_RECONCILED, "0", 1, {
        "op_id": OP, "outcome": "applied", "decided_by": "adapter", "evidence": [], "result": done("0")[3]["result"],
    })])  # fmt: skip
    steps = [bound("m1", INSTANCE), saved(rig, "m1"), _open(flag=flag), *ending, bound("m1", REOPENED, "reopened")]
    f = Fold(rig.events(forge(rig, chain(ORIGINAL), *steps)))
    assert [s.path for s in f.writes("m1")] == ["0"]
    assert [s.path for s in f.content("m1")] == (["0"] if counted else [])
    assert [s.path for s in f.lacking("m1")] == (["0"] if counted else [])


def test_a_later_content_free_open_keeps_the_earlier_write_as_the_comparison(tmp_path: Path) -> None:
    """Engine 4.5.4 (B-562): the result of a marked open is not the latest write result the state is compared with."""
    from types import SimpleNamespace

    from eng_harness.engine._hoststate import _difference
    from eng_harness.engine._inflight import Fold

    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)
    steps = [bound("m1", INSTANCE), saved(rig, "m1"), start("1", "write_b", M1, write=True)]
    steps += [done("1", ref=_result(rig, host, 1)), _open("2"), done("2", ref=_result(rig, host, 9))]
    f = Fold(rig.events(forge(rig, chain(ORIGINAL), *steps)))
    at = host.models["m1"].model_copy(update={"revision": 1, "fingerprint": "fp1"})
    rt: Any = SimpleNamespace(store=rig.store)
    assert _difference(rt, f, "m1", at) is None  # the edit's revision 1, not the open's 9
    assert _difference(rt, f, "m1", at.model_copy(update={"revision": 9})) == (
        "model_differs", "m1 is at revision 9 (fp1), the journal has 1",
    )  # fmt: skip


def test_a_pending_content_free_open_on_a_lost_model_still_needs_recovery(tmp_path: Path) -> None:
    """Engine 4.5.4 (B-562): a marked open that a lost binding keeps from being reconciled is no handoff."""
    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)
    run_id = forge(rig, chain(ORIGINAL), _open("1"), bound("m1", INSTANCE))
    host.crash("csi")
    stopped = resume(rig, chain(ORIGINAL), run_id)
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "host_state_mismatch"
    assert options(rig.inputs.presented[-1], "state") == ["abandon"]
    assert all(c[0] != "reconcile" for c in host.calls)
    assert ("model_state", "m1", "csi-1") in host.calls


@pytest.mark.parametrize(("case", "asked_about"), [("complete", "m1@copy"), ("legacy", "m1")])
def test_after_the_handoff_the_copy_is_still_checked(tmp_path: Path, case: str, asked_about: str) -> None:
    """Engine 4.5.4 (B-562): the handed-off original reads no state at the resume and its copy's writes are compared;
    without the recorded guarantee the unloaded original is a lost model."""
    rig, host = scripted_rig(tmp_path)
    host.add_model("m1", INSTANCE)
    steps = _handoff(rig, host, case)
    steps += [bound("m1@copy", INSTANCE), start("1", "write_b", {"n": 1, "model": "m1@copy"}, write=True)]
    steps.append(done("1", ref=_result(rig, host, hosted=False)))
    run_id = forge(rig, chain(ORIGINAL), *steps)
    host.models["m1"] = host.models["m1"].model_copy(update={"loaded": False})  # the instance holds the copy now
    _drift(host, "m1@copy")
    stopped = resume(rig, chain(ORIGINAL), run_id)
    assert stopped.escalation is not None
    assert stopped.escalation.reason == "host_state_mismatch"
    assert rig.inputs.presented[-1].title == f"A model changed while the run was stopped ({asked_about})"
    assert (("model_state", "m1", "csi-1") in host.calls) is (case == "legacy")
    assert host.ledger == []
