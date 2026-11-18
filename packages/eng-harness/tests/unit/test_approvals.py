"""Approvals: binding, single use, the re-check before the write, items and expiry (plan 0001 T15; AC54 to AC56).

The fake approval port stands for the page of spec 0006: it holds the request the engine presented and the answers the
test scripts. The block is a plain test body wrapped as a workflow; a write result carries the revision it produced in
`provenance.host`, as an adapter's result does.
"""

import asyncio
import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal

import pytest
from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import new_model_id
from eng_contract.refs import Ref
from fakes.ports import Raise
from pydantic import JsonValue, ValidationError
from workflows.ctx_flows import (
    ChildInput,
    answer,
    change_set,
    child,
    flow,
    need_approval,
    reply,
    request_id,
    success,
    written,
)
from workflows.rig import Rig, make_rig
from workflows.rig import asking as request

from eng_harness import errors
from eng_harness.ctx import Approval, ApprovalKind, Preview, PreviewItem
from eng_harness.engine import RunStatus
from eng_harness.engine._steps import op_id
from eng_harness.journal import EventType, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalAnswer, HostModelState, Reconciliation

T = EventType


def _resolved(rig: Rig, run_id: str) -> list[ev.ApprovalResolved]:
    return [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.ApprovalResolved)]


def test_binding_and_single_use(tmp_path: Path) -> None:
    """AC54: a request carries its binding; a refused answer changes nothing; an answer is used once."""
    rig = make_rig(tmp_path)
    shown = change_set(rig, "i1", "i2")
    got: list[Approval] = []

    async def body(ctx: Any) -> list[str]:
        got.append(await ctx.approve("Apply the change set", shown))
        return []

    engine = rig.engine(flow(body))
    paused = asyncio.run(engine.start(request()))
    run_id = paused.run_id
    rid = request_id(run_id, "0")
    assert rid == "apr_" + hashlib.sha256(f"{run_id}\n0".encode()).hexdigest()[:32]
    assert (paused.status, paused.pending) == (RunStatus.PAUSED, (rid,))
    asked, state = rig.approvals.presented[-1], rig.host.models["m1"]
    assert (asked.request_id, asked.run_id, asked.kind) == (rid, run_id, "change_set")
    assert (asked.title, asked.items) == ("Apply the change set", ("i1", "i2"))
    (bound,) = asked.binding
    assert (bound.model_key, bound.model_id, bound.revision) == ("m1", state.model_id, 0)
    assert (bound.fingerprint, bound.file_sha256) == ("fp0", "0" * 64)
    record = rig.store.get(asked.preview_ref)
    assert record.kind == "harness.approval_preview/1"
    assert asked.shown_sha256 == record.payload_sha256 == payload_sha256(shown.model_dump(mode="json", by_alias=True))
    requested = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.ApprovalRequested)]
    assert len(requested) == 1
    assert (requested[0].request_id, requested[0].kind, requested[0].title) == (rid, "change_set", asked.title)
    assert (requested[0].preview_ref, requested[0].items) == (asked.preview_ref, ["i1", "i2"])
    assert requested[0].binding == {
        "m1": {"model_id": state.model_id, "revision": 0, "fingerprint": "fp0", "file_sha256": "0" * 64}
    }
    assert rig.events(run_id)[-1].payload == ev.RunPaused(reason="awaiting_approval", request_ids=[rid])

    with pytest.raises(ValidationError):  # a rejected item without a reason is no answer at all
        ApprovalAnswer.model_validate(
            {
                "request_id": rid,
                "shown_sha256": asked.shown_sha256,
                "decision": "reject",
                "rejected_items": ["i1"],
                "by": "a",
            }
        )
    refused = [
        reply(rig, sha="b" * 64),  # another preview than the one shown
        reply(rig, rid="inp_1"),  # an answer to another request, such as an input request
        reply(rig, notes={"i9": "no such item"}),  # a reason for something that is no item of the request
        reply(rig, rejected={"i9": "no such item"}),  # a rejected item that is no item of the request
    ]
    for bad in refused:
        rig.approvals.script(rid, bad)
        shown_before = len(rig.approvals.presented)
        again = asyncio.run(engine.resume(run_id))
        assert (again.status, again.pending) == (RunStatus.PAUSED, (rid,))
        assert len(rig.approvals.presented) == shown_before + 2  # presented at the resume, and again after the refusal
        assert rig.approvals.presented[-1] == asked  # the same request, the same binding, the same stored preview
        assert _resolved(rig, run_id) == []
        assert got == []
    assert [e.type for e in rig.events(run_id)].count(T.APPROVAL_REQUESTED) == 1  # asked once, whatever the resumes

    good = reply(rig, rejected={"i2": "too thin"}, notes={"i1": "accepted with an exception"}, acknowledged=True)
    rig.approvals.script(rid, good)
    done = asyncio.run(engine.resume(run_id))
    assert done.status is RunStatus.COMPLETED
    assert _resolved(rig, run_id) == [
        ev.ApprovalResolved(
            request_id=rid, shown_sha256=asked.shown_sha256, decision="approve", rejected_items=["i2"],
            item_reasons={"i2": "too thin", "i1": "accepted with an exception"}, acknowledged_unreleased=True,
            reason="because", by="engineer:ada",
        )
    ]  # fmt: skip
    (approval,) = got
    assert (approval.request_id, approval.approved, approval.rejected_items) == (rid, True, ("i2",))
    assert approval.item_reasons == {"i2": "too thin", "i1": "accepted with an exception"}
    assert (approval.reason, approval.accepts("i1"), approval.accepts("i2")) == ("because", True, False)
    steps = [e for e in rig.events(run_id) if e.path == "0"]
    assert [e.type for e in steps] == [T.STEP_STARTED, T.STEP_COMPLETED]
    started, completed = steps[0].payload, steps[1].payload
    assert isinstance(started, ev.StepStarted)
    assert isinstance(completed, ev.StepCompleted)
    assert (started.kind, started.name, started.effect) == ("approve", "change_set", "none")
    assert started.args_sha256 == asked.shown_sha256  # the step is matched at replay on what was shown (spec 4.5.2)
    assert completed.result is not None
    assert completed.result.ref == asked.preview_ref
    assert completed.result.summary == {"request_id": rid, "approved": True}

    rig.approvals.script(rid, reply(rig, decision="reject"))  # a second answer to a resolved request
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED  # the recorded outcome, nothing asked
    assert len(rig.approvals.answers[rid]) == 1
    assert len(_resolved(rig, run_id)) == 1
    _single_use_across_a_resume_and_a_crash(tmp_path / "again")


def _single_use_across_a_resume_and_a_crash(tmp_path: Path) -> None:
    """AC54: an answer already journaled is the answer, whatever the port says now; a resume never asks again."""
    rig = make_rig(tmp_path)
    shown = change_set(rig, "i1")
    seen: list[Approval] = []

    async def body(ctx: Any) -> list[str]:
        seen.append(await ctx.approve("First", shown))
        await ctx.approve("Second", shown)
        return []

    engine = rig.engine(flow(body))
    run_id = asyncio.run(engine.start(request())).run_id
    first, second = request_id(run_id, "0"), request_id(run_id, "1")
    rig.approvals.script(first, reply(rig))
    paused = asyncio.run(engine.resume(run_id))  # the first is answered, the second is asked
    assert (paused.status, paused.pending) == (RunStatus.PAUSED, (second,))
    rig.approvals.script(first, reply(rig, rid=first, decision="reject"))  # a duplicate delivery for the first
    answers = len(rig.approvals.answers[first])
    asyncio.run(engine.resume(run_id))
    assert (len(rig.approvals.answers[first]), len(_resolved(rig, run_id))) == (answers, 1)  # never asked again
    assert seen[-1].approved

    # a crash after `approval_resolved` and before the step is journaled: the journal's answer stands (AC54)
    writer = JournalWriter(rig.run_dir(run_id), rig.store, rig.clock, rig.ids)
    resolved = ev.ApprovalResolved(
        request_id=second, shown_sha256=rig.approvals.presented[-1].shown_sha256, decision="reject",
        rejected_items=[], by="engineer:ada",
    )  # fmt: skip
    writer.append(T.APPROVAL_RESOLVED, resolved)
    writer.close()
    rig.approvals.script(second, reply(rig, rid=second))  # the port now says approve; the journal said reject
    seen.clear()
    done = asyncio.run(engine.resume(run_id))
    assert done.status is RunStatus.COMPLETED
    assert [r.decision for r in _resolved(rig, run_id)] == ["approve", "reject"]  # no second record for `second`
    assert len(rig.approvals.answers[second]) == 1  # the scripted answer was never read


def _guarded(
    tmp_path: Path, *, mutate: Callable[[Rig], None] | None = None, between: Callable[[Rig], None] | None = None,
    silent: bool = False,
) -> tuple[Rig, str, list[str], list[str]]:  # fmt: skip
    """Run an approved change set that writes `m1` twice under it; return the rig, run id, trail and result refs.

    `mutate` changes the host after the approval is shown and before the answer is read; `between` after the first
    write; `silent` gives the writes no `provenance.host`.
    """
    rig = make_rig(tmp_path)
    trail: list[str] = []
    refs: list[str] = []
    shown = change_set(rig, "i1")
    rig.host.script("write_b", *[success(rig, {}) if silent else written(rig, "m1", n + 1) for n in range(2)])

    async def body(ctx: Any) -> list[str]:
        approval = await ctx.approve("Apply", shown)
        for n in range(2):
            try:
                refs.append((await ctx.tool("write_b", {"n": n, "model": "m1"}, under=approval, item="i1")).ref.ref)
            except errors.ApprovalVoid as void:
                trail.append(void.message)
                break
            if n == 0 and between is not None:
                between(rig)
        return []

    engine = rig.engine(flow(body))
    run_id = asyncio.run(engine.start(request())).run_id
    if mutate is not None:
        mutate(rig)
    rig.approvals.script(request_id(run_id, "0"), reply(rig))
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    return rig, run_id, trail, refs


def _calls(rig: Rig) -> list[str]:
    return [c.tool for c in rig.host.ledger]


def _set(**fields: Any) -> Callable[[Rig], None]:
    """A change of the host's model `m1`: the given fields of its state."""

    def change(rig: Rig) -> None:
        rig.host.models["m1"] = rig.host.models["m1"].model_copy(update=fields)

    return change


def test_recheck_before_write(tmp_path: Path) -> None:
    """AC55: the bound model's revision, fingerprint, file or identity changed: `ApprovalVoid`, no port call."""
    rig, run_id, trail, refs = _guarded(tmp_path / "ok")
    assert (trail, len(refs), _calls(rig)) == ([], 2, ["write_b", "write_b"])  # nothing changed: both writes are made
    rid = request_id(run_id, "0")
    started = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.StepStarted)]
    writes = [s for s in started if s.effect == "write"]
    assert [(w.under, w.item) for w in writes] == [(rid, "i1"), (rid, "i1")]  # recorded for the report (spec 4.4.2)

    changes = {
        "revision and fingerprint": _set(revision=1, fingerprint="fp1"),
        "fingerprint": _set(fingerprint="other"),
        "revision": _set(revision=1),
        "file": _set(file_sha256="1" * 64),
    }
    for name, change in changes.items():
        rig, run_id, trail, refs = _guarded(tmp_path / name.replace(" ", "-"), mutate=change)
        assert trail == [f"model m1 changed since approval {request_id(run_id, '0')} was shown"], name
        assert (refs, _calls(rig), rig.log.count("tool.call")) == ([], [], 0), name  # the port was not called
        assert [e for e in rig.events(run_id) if e.path == "1"] == [], name  # the voided write left no step behind

    def other_model(rig: Rig) -> None:
        _set(model_id=new_model_id(rig.ids))(rig)

    rig, run_id, trail, refs = _guarded(tmp_path / "identity", mutate=other_model)
    assert (len(trail), _calls(rig)) == (1, [])

    # the second write finds the revision its predecessor produced, or the approval is void (spec 4.9)
    later: dict[str, dict[str, Any]] = {
        "outside": {"between": _set(revision=5)},
        "gone": {"between": lambda r: r.host.models.update(m1=HostModelState(loaded=False))},
        "unknown": {"silent": True},  # a result that does not say which revision it produced
    }
    for name, kwargs in later.items():
        rig, run_id, trail, refs = _guarded(tmp_path / name, **kwargs)
        assert (len(refs), _calls(rig), len(trail)) == (1, ["write_b"], 1), name
        assert trail[0] == f"model m1 changed since approval {request_id(run_id, '0')} was shown", name


def test_per_item_rejection_and_expiry(tmp_path: Path) -> None:
    """AC56: an accepted item is written, a rejected one is refused; an approval expires at a check or its scope."""
    rig = make_rig(tmp_path)
    shown = change_set(rig, "i1", "i2")
    rig.host.script("write_b", written(rig, "m1", 1), written(rig, "m1", 2))
    box: list[Approval] = []
    seen: dict[str, str | None] = {}

    async def kid(ctx: Any) -> list[str]:
        box.append(await ctx.approve("Child", shown))
        return []

    inner = child(kid)

    async def body(ctx: Any) -> list[str]:
        approval = await ctx.approve("Apply", shown)
        forged = Approval(request_id="apr_forged", approved=True, rejected_items=(), item_reasons={}, reason=None)

        numbers = iter(range(100))  # the arguments of a step are the same at each replay

        async def attempt(label: str, tool: str, args: dict[str, Any], **using: Any) -> None:
            try:
                await ctx.tool(tool, {"n": next(numbers), **args}, **using)
            except errors.BlockRuleViolation as stop:
                seen[label] = stop.message
            else:
                seen[label] = None

        await attempt("accepted", "write_b", {"model": "m1"}, under=approval, item="i1")
        await attempt("rejected", "write_b", {"model": "m1"}, under=approval, item="i2")
        await attempt("unknown_item", "write_b", {"model": "m1"}, under=approval, item="i9")
        await attempt("whole", "write_b", {"model": "m1"}, under=approval)
        await attempt("no_approval", "write_b", {"model": "m1"}, item="i1")
        await attempt("other_model", "write_b", {"model": "m2"}, under=approval, item="i1")
        await attempt("forged", "write_b", {"model": "m1"}, under=forged, item="i1")
        await attempt("read", "read_a", {}, under=approval)
        await ctx.block(inner, ChildInput())  # the child's approval is asked, and its first check expires `approval`
        await attempt("after_check", "write_b", {"model": "m1"}, under=approval, item="i1")
        await attempt("after_scope", "write_b", {"model": "m1"}, under=box[0], item="i1")
        return []

    engine = rig.engine(flow(body))
    run_id = asyncio.run(engine.start(request())).run_id
    rig.approvals.script(request_id(run_id, "0"), reply(rig, rejected={"i2": "too thin"}))
    paused = asyncio.run(engine.resume(run_id))  # runs up to the child's approval
    assert paused.status is RunStatus.PAUSED
    assert len(rig.approvals.presented) > 1
    rig.approvals.script(rig.approvals.presented[-1].request_id, reply(rig))
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED  # replays everything before the pause
    assert seen["accepted"] is None
    assert seen["whole"] is None
    assert "rejected" in str(seen["rejected"])
    assert "i2" in str(seen["rejected"])
    assert "i9" in str(seen["unknown_item"])
    assert "under" in str(seen["no_approval"])
    assert "m2" in str(seen["other_model"])
    assert "apr_forged" in str(seen["forged"])
    assert "write" in str(seen["read"])
    assert "expired" in str(seen["after_check"])
    assert "expired" in str(seen["after_scope"])
    assert _calls(rig) == ["write_b", "write_b"]  # the two allowed writes only: every refusal came before the port
    refused = [label for label, why in seen.items() if why is not None]
    assert len(refused) == 8
    assert rig.log.count("tool.call") == 2


def test_rejected_approval_is_returned_not_raised(tmp_path: Path) -> None:
    """A rejected approval returns `approved: false` to the block; a write under it is refused (spec 4.9)."""
    rig = make_rig(tmp_path)
    shown = change_set(rig, "i1")
    got: list[Approval] = []
    refused: list[str] = []

    async def body(ctx: Any) -> list[str]:
        got.append(await ctx.approve("Apply", shown))
        try:
            await ctx.tool("write_b", {"n": 0, "model": "m1"}, under=got[0], item="i1")
        except errors.BlockRuleViolation as stop:
            refused.append(stop.message)
        return []

    engine = rig.engine(flow(body))
    run_id = asyncio.run(engine.start(request())).run_id
    rig.approvals.script(request_id(run_id, "0"), reply(rig, decision="reject", by="engineer:ada"))
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    assert (got[0].approved, got[0].rejected_items, got[0].accepts("i1")) == (False, (), False)
    assert [r.by for r in _resolved(rig, run_id)] == ["engineer:ada"]  # the prefix is not doubled
    assert refused == [f"approval {request_id(run_id, '0')} is not an approved request of this run"]
    assert rig.host.ledger == []


def test_a_preview_the_journal_does_not_hold_and_an_unopened_model(tmp_path: Path) -> None:
    """The request is shown with the same preview at every resume; a bound model must be open; the type is checked."""
    rig = make_rig(tmp_path)
    first, other = change_set(rig, "i1"), change_set(rig, "i1", "i2")

    def shows(preview: Any, name: str = "chain") -> Any:
        async def body(ctx: Any) -> list[str]:
            await ctx.approve("Apply", preview)
            return []

        return flow(body, name=name)

    run_id = asyncio.run(rig.engine(shows(first)).start(request())).run_id
    stopped = asyncio.run(rig.engine(shows(other)).resume(run_id))  # the journal shows the request with `first`
    assert (stopped.status, stopped.escalation.reason if stopped.escalation else None) == (
        RunStatus.NEEDS_ENGINEER,
        "replay_divergence",
    )
    assert "another preview" in (stopped.escalation.detail if stopped.escalation else "")
    assert [e.type for e in rig.events(run_id)].count(T.APPROVAL_REQUESTED) == 1

    closed = make_rig(tmp_path / "closed")
    shown = change_set(closed, "i1")
    closed.host.models["m1"] = HostModelState(loaded=False)  # no instance holds it
    with pytest.raises(ContractError) as unopened:
        asyncio.run(closed.engine(shows(shown)).start(request()))
    assert unopened.value.detail.code is ErrorCode.PRECONDITION_FAILED
    assert "the model m1 is not open in any host instance" in unopened.value.detail.message
    assert closed.approvals.presented == []
    assert not [r for r in closed.run_ids() for e in closed.events(r) if e.type is T.APPROVAL_REQUESTED]

    async def untyped(ctx: Any) -> list[str]:
        await ctx.approve("Apply", {"items": []})
        return []

    refused = asyncio.run(make_rig(tmp_path / "untyped").engine(flow(untyped)).start(request()))
    assert (refused.status, refused.escalation.reason if refused.escalation else None) == (
        RunStatus.NEEDS_ENGINEER,
        "block_rule_violation",
    )


def test_references_of_a_preview_are_resolved(tmp_path: Path) -> None:
    """Invariant 3: a reference in an item or in the diff must resolve before the request is made."""
    rig = make_rig(tmp_path)
    gone = Ref.model_validate({"$ref": "res_" + "1" * 26})
    refs = {
        "item": Preview(items=(PreviewItem(id="i1", label="A", refs=(gone,)),), diff_ref=None, models=()),
        "diff": Preview(items=(), diff_ref=gone, models=()),
    }
    for name, shown in refs.items():

        async def body(ctx: Any, shown: Preview = shown) -> list[str]:
            await ctx.approve("Apply", shown)
            return []

        with pytest.raises(ContractError) as raised:  # the contract's code leaves the root block, as for any read
            asyncio.run(rig.engine(flow(body)).start(request()))
        assert raised.value.detail.code is ErrorCode.REF_NOT_FOUND, name
        assert rig.approvals.presented == [], name


def test_signed_off_for_an_approved_sign_off(tmp_path: Path) -> None:
    """An approved `SIGN_OFF` also journals `signed_off` once; a rejected one, and any other kind, do not."""
    rig = make_rig(tmp_path)
    done_ref = rig.store.put("harness.run_output/1", {"value": 1}, written(rig, "m1", 1).provenance).result_id
    refs = {
        "i1": Ref.model_validate({"$ref": done_ref}),
        "i2": Ref.model_validate({"$ref": done_ref + "#/value"}),
        "i3": Ref.model_validate({"$ref": done_ref}),
    }
    items = tuple(PreviewItem(id=k, label=k, refs=(v,)) for k, v in refs.items())
    shown = Preview(items=items, diff_ref=None, models=())
    kinds: dict[str, tuple[ApprovalKind, Literal["approve", "reject"], bool]] = {
        "sign": (ApprovalKind.SIGN_OFF, "approve", True),
        "refused": (ApprovalKind.SIGN_OFF, "reject", False),
        "info": (ApprovalKind.INFO, "approve", False),
        "change": (ApprovalKind.CHANGE_SET, "approve", False),
    }
    for name, (kind, decision, signed) in kinds.items():

        async def body(ctx: Any, kind: ApprovalKind = kind) -> list[str]:
            await ctx.approve("Sign", shown, kind=kind)
            return []

        engine = rig.engine(flow(body))
        run_id = asyncio.run(engine.start(request())).run_id
        rig.approvals.script(
            request_id(run_id, "0"),
            reply(rig, decision=decision, rejected={"i2": "an exception"} if decision == "approve" else None),
        )
        assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED, name
        asyncio.run(engine.resume(run_id))  # a terminal run is not signed again
        sign_offs = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.SignedOff)]
        if signed:
            assert sign_offs == [
                ev.SignedOff(outputs=[done_ref], approval_request_id=request_id(run_id, "0"), by="engineer:ada")
            ], name
        else:
            assert sign_offs == [], name


def test_replayed_writes_leave_the_revision_the_next_write_must_find(tmp_path: Path) -> None:
    """A run paused between two writes under one approval resumes: the replayed write's revision is the one expected."""
    rig = make_rig(tmp_path)
    shown = change_set(rig, "i1")
    rig.host.script("write_b", written(rig, "m1", 1), written(rig, "m1", 2))
    voided: list[str] = []

    async def body(ctx: Any) -> list[str]:
        approval = await ctx.approve("Apply", shown)
        await ctx.tool("write_b", {"n": 0, "model": "m1"}, under=approval, item="i1")
        await need_approval(rig.approvals, "apr_stub")  # a pause that checks nothing, so the approval stays valid
        try:
            await ctx.tool("write_b", {"n": 1, "model": "m1"}, under=approval, item="i1")
        except errors.ApprovalVoid as void:
            voided.append(void.message)
        return []

    engine = rig.engine(flow(body))
    run_id = asyncio.run(engine.start(request())).run_id
    rig.approvals.script(request_id(run_id, "0"), reply(rig))
    assert asyncio.run(engine.resume(run_id)).pending == ("apr_stub",)  # one write is made, then the stub pauses
    rig.approvals.script("apr_stub", answer("apr_stub"))
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    assert (voided, _calls(rig)) == (
        [],
        ["write_b", "write_b"],
    )  # the second write found revision 1, as the first left it


def test_signed_off_is_journaled_once_across_a_crash(tmp_path: Path) -> None:
    """A crash after `approval_resolved` of a sign-off leaves `signed_off` to the resume, and only once."""
    rig = make_rig(tmp_path)
    shown = change_set(rig, "i1")

    async def body(ctx: Any) -> list[str]:
        await ctx.approve("Sign", shown, kind=ApprovalKind.SIGN_OFF)
        return []

    engine = rig.engine(flow(body))
    for name, signed_before in (("late", False), ("early", True)):
        run_id = asyncio.run(engine.start(request())).run_id
        rid = request_id(run_id, "0")
        resolved = ev.ApprovalResolved(
            request_id=rid, shown_sha256=rig.approvals.presented[-1].shown_sha256, decision="approve",
            rejected_items=[], by="engineer:ada",
        )  # fmt: skip
        writer = JournalWriter(rig.run_dir(run_id), rig.store, rig.clock, rig.ids)
        writer.append(T.APPROVAL_RESOLVED, resolved)
        if signed_before:
            writer.append(T.SIGNED_OFF, {"outputs": [], "approval_request_id": rid, "by": "engineer:ada"})
        writer.close()
        assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED, name
        sign_offs = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.SignedOff)]
        assert [s.approval_request_id for s in sign_offs] == [rid], name


def test_a_reconciled_write_leaves_its_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A write under an approval whose call raised and was reconciled `applied` leaves the revision of its result."""
    rig = make_rig(tmp_path)
    shown = change_set(rig, "i1")
    rig.host.script("write_b", Raise(OSError("the call was lost")))
    voided: list[str] = []

    async def body(ctx: Any) -> list[str]:
        approval = await ctx.approve("Apply", shown)
        for n in range(2):
            try:
                await ctx.tool("write_b", {"n": n, "model": "m1"}, under=approval, item="i1")
            except errors.ApprovalVoid as void:
                voided.append(void.message)
        return []

    engine = rig.engine(flow(body))
    run_id = asyncio.run(engine.start(request())).run_id
    first = op_id(run_id, "1", 1)
    rig.host.reconciliations[first] = Reconciliation(outcome="applied", result=written(rig, "m1", 1))
    reconcile = rig.host.reconcile

    async def applied(tool: str, args: Mapping[str, JsonValue], op: str) -> Reconciliation:
        rig.host.models["m1"] = rig.host.models["m1"].model_copy(update={"revision": 1, "fingerprint": "fp1"})
        return await reconcile(tool, args, op)  # the lost call had been applied after all

    monkeypatch.setattr(rig.host, "reconcile", applied)
    rig.approvals.script(request_id(run_id, "0"), reply(rig))
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    assert voided == []  # the second write found revision 1, which the reconciled first write left
    assert next(c.op_id for c in rig.host.ledger) == first
    assert len(rig.host.ledger) == 2
