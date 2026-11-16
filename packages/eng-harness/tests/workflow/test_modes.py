"""Permission modes: the working copy, the approval before a write, the always-ask list (plan 0001 T16; AC48 to AC51).

The fake host stands for the adapter: `working_copy` opens `<model>.copy` on the same instance, and `preview` answers
with the preview the test scripts. The block bodies are plain test code wrapped as workflows.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode, Precondition
from pydantic import JsonValue
from workflows.chain import chain
from workflows.ctx_flows import change_set, flow, reply, request_id, written
from workflows.modes import mode_rig, stored_writes
from workflows.rig import Rig, request

from eng_harness import errors
from eng_harness.ctx import ApprovalKind
from eng_harness.engine import PermissionMode, RunStatus
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev

T = EventType
COPY = PermissionMode.WORK_ON_COPY
MODES = (COPY, PermissionMode.APPROVE_EACH_WRITE, PermissionMode.AUTONOMOUS_LOGGED)


def _started(rig: Rig, run_id: str, path: str) -> ev.StepStarted:
    (found,) = [e.payload for e in rig.events(run_id) if e.path == path and isinstance(e.payload, ev.StepStarted)]
    return found


def _resolved(rig: Rig, run_id: str) -> list[ev.ApprovalResolved]:
    return [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.ApprovalResolved)]


def test_work_on_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC48: the copy is taken and saved before the first write; every later step on the model goes to the copy."""
    rig = mode_rig(tmp_path)
    folders: list[Path] = []
    take = rig.host.working_copy

    async def watched(model_key: str, folder: Path) -> str:
        folders.append(folder)
        return await take(model_key, folder)

    monkeypatch.setattr(rig.host, "working_copy", watched)

    async def body(ctx: Any) -> list[str]:
        steps = [("read_m", {"model": "m1"}), ("write_b", {"n": 1, "model": "m1"})]
        steps += [("write_b", {"n": 2, "model": "m1"}), ("read_m", {"model": "m1"}), ("read_a", {"n": 3})]
        return [(await ctx.tool(name, args)).ref.ref for name, args in steps]

    outcome = asyncio.run(rig.engine(flow(body)).start(request(mode=COPY)))
    run_id = outcome.run_id
    assert outcome.status is RunStatus.COMPLETED
    assert [(e.tool, e.model) for e in rig.host.ledger] == [
        ("read_m", "m1"), ("write_b", "m1.copy"), ("write_b", "m1.copy"), ("read_m", "m1.copy"), ("read_a", None),
    ]  # fmt: skip
    assert [e.args.get("model") for e in rig.host.ledger[:4]] == ["m1", "m1.copy", "m1.copy", "m1.copy"]
    assert (rig.host.models["m1"].revision, rig.host.models["m1.copy"].revision) == (0, 2)  # the original is untouched
    assert folders == [rig.run_dir(run_id) / "copies"]  # one copy, in the run folder
    events = rig.events(run_id)
    copied = [e for e in events if isinstance(e.payload, ev.ModelSaved)]
    (saved,) = copied
    state = rig.host.models["m1.copy"]
    assert saved.path == "1~pre.working_copy.m1"
    assert saved.payload == ev.ModelSaved(
        model_key="m1.copy", model_id=state.model_id or "", revision=0, fingerprint="fp0", file_sha256="0" * 64,
        file_name="m1.copy.edb", role="working_copy", origin_sha256="0" * 64, origin_file_names=["m1.edb"],
    )  # fmt: skip
    order = [(e.type, e.path) for e in events if e.path and e.path.startswith("1")]
    assert order[0] == (T.STEP_STARTED, "1~pre.working_copy.m1")  # before the first write, and before its units read
    assert order.index((T.MODEL_SAVED, "1~pre.working_copy.m1")) < order.index((T.STEP_STARTED, "1"))
    began = _started(rig, run_id, "1")
    assert (began.model_key, (began.args or {})["model"], began.effect) == ("m1.copy", "m1.copy", "write")
    assert (_started(rig, run_id, "0").model_key, _started(rig, run_id, "3").model_key) == ("m1", "m1.copy")
    assert [e.path for e in events if e.path and "working_copy" in e.path and e.type is T.STEP_STARTED] == [
        "1~pre.working_copy.m1"
    ]  # no second copy for the second write


def test_working_copy_is_replayed_and_new_models_get_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC48: a resume replays the copy from the journal and calls no host to take it again; a closed model gets none."""
    rig = mode_rig(tmp_path)
    stored_writes(rig, monkeypatch)

    async def body(ctx: Any) -> list[str]:
        first = await ctx.tool("write_b", {"n": 1, "model": "m1"})
        await ctx.approve("Check the first write", change_set(rig, "i1"))
        second = await ctx.tool("write_b", {"n": 2, "model": "m1"})
        return [first.ref.ref, second.ref.ref]

    engine = rig.engine(flow(body))
    paused = asyncio.run(engine.start(request(mode=COPY)))
    rid = request_id(paused.run_id, "1")
    assert (paused.status, paused.pending) == (RunStatus.PAUSED, (rid,))
    asked = rig.approvals.presented[-1]
    assert [(b.model_key, b.model_id) for b in asked.binding] == [("m1", rig.host.models["m1.copy"].model_id)]
    rig.approvals.script(rid, reply(rig))
    mark = len(rig.log)
    done = asyncio.run(engine.resume(paused.run_id))
    assert done.status is RunStatus.COMPLETED
    assert "host.working_copy" not in rig.log[mark:]
    assert rig.log.count("host.working_copy") == 1
    assert [(e.model, e.args["model"]) for e in rig.host.ledger] == [("m1.copy", "m1.copy")] * 2

    other = mode_rig(tmp_path / "other")
    with pytest.raises(ContractError) as refused:  # a write to a model no instance holds: refused, no copy taken
        asyncio.run(other.engine(chain([("write_b", {"n": 1, "model": "new"})])).start(request(mode=COPY)))
    assert refused.value.detail.code is ErrorCode.PRECONDITION_FAILED
    assert refused.value.detail.precondition is Precondition.model_open
    assert "host.working_copy" not in other.log


def test_approve_each_write(tmp_path: Path) -> None:
    """AC49: an approval of the preview precedes each write; a rejection raises `ApprovalRejected`, no call is made."""
    rig = mode_rig(tmp_path)
    rig.host.previews["write_b"] = change_set(rig, "i1")
    engine = rig.engine(chain([("read_a", {"n": 0}), ("write_b", {"n": 1, "model": "m1"})]))
    paused = asyncio.run(engine.start(request(mode=PermissionMode.APPROVE_EACH_WRITE)))
    run_id, rid = paused.run_id, request_id(paused.run_id, "1~pre.approve")
    assert (paused.status, paused.pending) == (RunStatus.PAUSED, (rid,))
    asked = rig.approvals.presented[-1]
    assert (asked.kind, asked.title, asked.items) == ("change_set", "Apply write_b", ("i1",))
    assert [e.tool for e in rig.host.ledger] == ["read_a"]  # the write waits for the answer
    rig.approvals.script(rid, reply(rig))
    done = asyncio.run(engine.resume(run_id))
    assert done.status is RunStatus.COMPLETED
    assert [(e.tool, e.model) for e in rig.host.ledger] == [("read_a", None), ("write_b", "m1")]
    assert _started(rig, run_id, "1").under == rid  # the write ran under the approval, which was checked before it
    assert [r.by for r in _resolved(rig, run_id)] == ["engineer:ada"]

    refused = mode_rig(tmp_path / "refused")
    refused.host.previews["write_b"] = change_set(refused, "i1")
    caught: list[errors.ApprovalRejected] = []

    async def body(ctx: Any) -> list[str]:
        try:
            await ctx.tool("write_b", {"n": 1, "model": "m1"})
        except errors.ApprovalRejected as exc:
            caught.append(exc)
        return []

    again = rig_engine = refused.engine(flow(body))
    first = asyncio.run(again.start(request(mode=PermissionMode.APPROVE_EACH_WRITE)))
    no = request_id(first.run_id, "0~pre.approve")
    refused.approvals.script(no, reply(refused, decision="reject", rejected={"i1": "too much"}))
    assert asyncio.run(rig_engine.resume(first.run_id)).status is RunStatus.COMPLETED
    (exc,) = caught
    assert (exc.code, list(exc.evidence)) == (errors.HarnessCode.APPROVAL_REJECTED, [no])
    assert refused.host.ledger == []  # the write was not called
    assert "tool.call" not in refused.log


def test_autonomous_logged(tmp_path: Path) -> None:
    """AC50: a write is called without approval; an `INFO` or `CHANGE_SET` approval is resolved by the mode."""
    rig = mode_rig(tmp_path)
    got: list[bool] = []

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("write_b", {"n": 1, "model": "m1"})
        info = await ctx.approve("Note", change_set(rig, "i1"), kind=ApprovalKind.INFO)
        changes = await ctx.approve("Changes", change_set(rig, "i2"), kind=ApprovalKind.CHANGE_SET)
        got.extend([info.approved, changes.approved, changes.accepts("i2")])
        await ctx.approve("Sign off", change_set(rig, "i3"), kind=ApprovalKind.SIGN_OFF)
        return []

    engine = rig.engine(flow(body))
    paused = asyncio.run(engine.start(request(mode=PermissionMode.AUTONOMOUS_LOGGED)))
    run_id = paused.run_id
    assert [(e.tool, e.model) for e in rig.host.ledger] == [("write_b", "m1")]  # no copy, no approval
    assert not [e for e in rig.events(run_id) if e.path and ("working_copy" in e.path or "~pre.approve" in e.path)]
    assert got == [True, True, True]
    (resolved_info, resolved_changes) = _resolved(rig, run_id)
    assert (resolved_info.by, resolved_changes.by) == ("mode:autonomous_logged", "mode:autonomous_logged")
    assert (resolved_info.decision, resolved_changes.rejected_items) == ("approve", [])
    assert [(p.kind, p.title) for p in rig.approvals.presented] == [("sign_off", "Sign off")]  # only this one asks
    assert (paused.status, paused.pending) == (RunStatus.PAUSED, (request_id(run_id, "3"),))
    rig.approvals.script(request_id(run_id, "3"), reply(rig))
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    assert [r.by for r in _resolved(rig, run_id)] == ["mode:autonomous_logged"] * 2 + ["engineer:ada"]  # not again


ALWAYS: dict[str, list[tuple[str, dict[str, JsonValue]]]] = {
    "delete": [("delete_d", {"n": 0, "model": "m1"})],
    "save over the original": [("save_s", {"n": 0, "model": "m1", "target": "original"})],
    "listed tool": [("write_b", {"n": 0, "model": "m1"})],
}


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", sorted(ALWAYS))
def test_always_ask_in_every_mode(tmp_path: Path, mode: PermissionMode, case: str) -> None:
    """AC51: a delete, a save over an original and a tool of `always_ask` need an approval in every mode."""
    rig = mode_rig(tmp_path)
    (tool, _), *_ = ALWAYS[case]
    rig.host.previews[tool] = change_set(rig, "i1")
    rig.host.script("save_s", written(rig, "m1", 1))  # a tool save names its revision (engine 4.6 "Tool saves")
    engine = rig.engine(chain(ALWAYS[case], always_ask=("write_b",)))
    paused = asyncio.run(engine.start(request(mode=mode)))
    run_id, rid = paused.run_id, request_id(paused.run_id, "0~pre.approve")
    assert (paused.status, paused.pending) == (RunStatus.PAUSED, (rid,))
    assert (rig.approvals.presented[-1].kind, rig.host.ledger) == ("change_set", [])  # asked before the tool ran
    rig.approvals.script(rid, reply(rig))
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    assert [r.by for r in _resolved(rig, run_id)] == ["engineer:ada"]  # no mode resolves it
    (call,) = rig.host.ledger
    copied = "m1.copy" if mode is COPY else "m1"
    assert (call.tool, call.model, _started(rig, run_id, "0").under) == (tool, copied, rid)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("kind", [ApprovalKind.PROMOTION, ApprovalKind.SIGN_OFF])
def test_promotion_and_sign_off_ask_in_every_mode(
    tmp_path: Path, mode: PermissionMode, kind: ApprovalKind, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC51: no mode resolves a `PROMOTION` or `SIGN_OFF` approval; it is asked after the always-ask write before it."""
    rig = mode_rig(tmp_path)
    stored_writes(rig, monkeypatch)
    rig.host.previews["write_b"] = change_set(rig, "i1")

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("write_b", {"n": 1, "model": "m1"})
        await ctx.approve("Final", change_set(rig, "i2"), kind=kind)
        return []

    engine = rig.engine(flow(body, always_ask=("write_b",)))
    paused = asyncio.run(engine.start(request(mode=mode)))
    run_id, first = paused.run_id, request_id(paused.run_id, "0~pre.approve")
    assert paused.pending == (first,)
    rig.approvals.script(first, reply(rig))
    paused = asyncio.run(engine.resume(run_id))
    final = request_id(run_id, "1")
    assert (paused.status, paused.pending) == (RunStatus.PAUSED, (final,))
    assert [(p.kind, p.title) for p in rig.approvals.presented][-1] == (kind.value, "Final")
    rig.approvals.script(final, reply(rig))
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    assert [r.by for r in _resolved(rig, run_id)] == ["engineer:ada", "engineer:ada"]


@pytest.mark.parametrize("mode", [COPY, PermissionMode.AUTONOMOUS_LOGGED])
def test_a_save_to_a_new_file_is_not_asked(tmp_path: Path, mode: PermissionMode) -> None:
    """AC51: only a save over an original is always-ask; a save to another file goes on in every mode but each-write."""
    rig = mode_rig(tmp_path)
    flow_of = chain([("save_s", {"n": 0, "model": "m1", "target": "new"}), ("delete_d", {"n": 1, "model": "m2"})])
    rig.host.previews["delete_d"] = change_set(rig, "i1", models=["m2"])
    rig.host.script("save_s", written(rig, "m1", 1))
    paused = asyncio.run(rig.engine(flow_of).start(request(mode=mode)))
    assert [e.tool for e in rig.host.ledger] == ["save_s"]  # the save ran; the delete after it waits
    assert [p.title for p in rig.approvals.presented] == ["Apply delete_d"]
    assert paused.pending == (request_id(paused.run_id, "1~pre.approve"),)


class _Cut(BaseException):
    """A process death between the start of a write and its end (an `Exception` would be the write's own failure)."""


def _attempts(rig: Rig, run_id: str) -> list[Any]:
    return [e for e in rig.events(run_id) if isinstance(e.payload, ev.StepStarted) and e.path == "0"]


@pytest.mark.parametrize("changed", [False, True])
def test_an_inserted_approval_covers_the_rerun_of_a_write_in_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: bool
) -> None:
    """AC49, spec 4.9: a write that ran under `p~pre.approve`, cut off and reconciled not applied, runs again as the
    next attempt under the same approval, re-checked before the write; a model that changed voids it."""
    rig = mode_rig(tmp_path)
    rig.host.previews["write_b"] = change_set(rig, "i1")
    voided: list[str] = []

    async def body(ctx: Any) -> list[str]:
        try:
            return [(await ctx.tool("write_b", {"n": 1, "model": "m1"})).ref.ref]
        except errors.ApprovalVoid as void:
            voided.append(void.message)
            return []

    engine = rig.engine(flow(body))
    paused = asyncio.run(engine.start(request(mode=PermissionMode.APPROVE_EACH_WRITE)))
    run_id, rid = paused.run_id, request_id(paused.run_id, "0~pre.approve")
    rig.approvals.script(rid, reply(rig))
    call = rig.host.call

    async def cut(tool: str, args: Any, *, op_id: str, model: str | None) -> Any:
        raise _Cut

    monkeypatch.setattr(rig.host, "call", cut)
    with pytest.raises(_Cut):
        asyncio.run(engine.resume(run_id))
    monkeypatch.setattr(rig.host, "call", call)
    assert [e.payload.under for e in _attempts(rig, run_id)] == [rid]
    if changed:
        rig.host.models["m1"] = rig.host.models["m1"].model_copy(update={"revision": 7})
    done = asyncio.run(engine.resume(run_id))
    assert done.status is RunStatus.COMPLETED
    assert [(e.attempt, e.payload.under) for e in _attempts(rig, run_id)] == [(1, rid)] + (
        [] if changed else [(2, rid)]
    )
    assert (len(voided), len(rig.host.ledger)) == ((1, 0) if changed else (0, 1))  # a void ends before the call


def test_a_working_copy_with_no_model_file_is_refused_by_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A copy the port opened but cannot name a file for is a `ContractError` that names it, not an `IndexError`."""
    rig = mode_rig(tmp_path)
    monkeypatch.setattr(rig.host, "model_files", lambda key: () if key == "m1.copy" else (Path(f"{key}.edb"),))
    with pytest.raises(ContractError) as refused:
        asyncio.run(rig.engine(chain([("write_b", {"n": 1, "model": "m1"})])).start(request(mode=COPY)))
    assert refused.value.detail.code is ErrorCode.PRECONDITION_FAILED
    assert refused.value.detail.precondition is Precondition.model_open
    assert "m1.copy" in refused.value.detail.message
    assert [e.tool for e in rig.host.ledger] == []
