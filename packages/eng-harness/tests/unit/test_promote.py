"""Promotion of a working copy by file copy (plan 0001 T16b; AC52, AC53).

`copy_files` is tested over the fake `FileOps`; `ctx.promote` over real files in a temporary folder, with the approval
of a `PROMOTION` request answered through the fake approval port.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from workflows.ctx_flows import flow, reply, request_id
from workflows.modes import FakeFileOps, approved, give_files, mode_rig, promoting, sha, stored_writes
from workflows.rig import request

from eng_harness import errors
from eng_harness.ctx import Approval, ApprovalKind, ModelHandle, Promotion
from eng_harness.engine import PermissionMode, RunStatus
from eng_harness.engine._promote import LocalFileOps, copy_files
from eng_harness.engine._steps import op_id
from eng_harness.journal import EventType
from eng_harness.journal import _events as ev

T = EventType
FOLDER = Path("work")
ORIGINAL, ACCEPTED = b"original", b"accepted"


def _fake(*, corrupt: str | None = None) -> FakeFileOps:
    files = {FOLDER / "a.edb": b"one", FOLDER / "b.edb": b"two", FOLDER / "c.edb": b"three", FOLDER / "d.edb": b"four"}
    return FakeFileOps(files, corrupt)


def _copy(ops: FakeFileOps, origin: str | None = None) -> None:
    origin = origin or ops.sha256([FOLDER / "a.edb", FOLDER / "b.edb"])
    copy_files(ops, [FOLDER / "a.edb", FOLDER / "b.edb"], [FOLDER / "c.edb", FOLDER / "d.edb"], Path("backups"), origin)


def test_copy_files_backs_up_then_replaces() -> None:
    """The originals are backed up, the accepted files are staged under temporary names, then replace the targets."""
    ops = _fake()
    _copy(ops)
    assert ops.ops == [
        "copy a.edb a.edb", "copy b.edb b.edb", "copy c.edb a.edb.promoting", "copy d.edb b.edb.promoting",
        "replace a.edb.promoting a.edb", "replace b.edb.promoting b.edb",
    ]  # fmt: skip
    assert (ops.files[Path("backups/a.edb")], ops.files[Path("backups/b.edb")]) == (b"one", b"two")
    assert (ops.files[FOLDER / "a.edb"], ops.files[FOLDER / "b.edb"]) == (b"three", b"four")
    assert Path("work/a.edb.promoting") not in ops.files


def test_copy_files_conflicts_copy_nothing() -> None:
    """A changed original, another count of files or a copy that does not match its source is `CONFLICT`."""
    changed = _fake()
    with pytest.raises(ContractError) as refused:
        _copy(changed, "0" * 64)
    assert (refused.value.detail.code, refused.value.detail.message) == (
        ErrorCode.CONFLICT, "the original changed since the working copy was taken",
    )  # fmt: skip
    assert changed.ops == []
    short = _fake()
    with pytest.raises(ContractError, match="another count of files"):
        copy_files(short, [FOLDER / "a.edb"], [FOLDER / "c.edb", FOLDER / "d.edb"], Path("backups"), sha(b"one"))
    assert short.ops == []
    for spoiled, step in (("a.edb", "backup"), ("a.edb.promoting", "staged copy")):
        ops = _fake(corrupt=spoiled)
        with pytest.raises(ContractError, match=f"the copy {spoiled} does not match"):
            _copy(ops)
        assert not any(op.startswith("replace") for op in ops.ops), step  # the originals were never replaced
        assert (ops.files[FOLDER / "a.edb"], ops.files[FOLDER / "b.edb"]) == (b"one", b"two"), step


def test_local_file_ops(tmp_path: Path) -> None:
    """The hash is that of the bytes in order, a copy makes its folder, a replace moves over the target."""
    ops = LocalFileOps()
    (tmp_path / "x").write_bytes(b"ab")
    (tmp_path / "y").write_bytes(b"c")
    assert ops.sha256([tmp_path / "x", tmp_path / "y"]) == sha(b"abc") != ops.sha256([tmp_path / "y", tmp_path / "x"])
    ops.copy(tmp_path / "x", tmp_path / "deep" / "z")
    assert (tmp_path / "deep" / "z").read_bytes() == b"ab"
    ops.replace(tmp_path / "deep" / "z", tmp_path / "y")
    assert ((tmp_path / "y").read_bytes(), (tmp_path / "deep" / "z").exists()) == (b"ab", False)


def test_file_copy_promotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC52: the original is backed up in the run folder and the accepted files are copied to the target."""
    rig = mode_rig(tmp_path)
    original, copy = give_files(rig, monkeypatch, tmp_path, "m1", ORIGINAL, ACCEPTED)
    stored_writes(rig, monkeypatch)
    workflow, seen = promoting(rig)
    engine, run_id = approved(rig, workflow)
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    state = rig.host.models["m1.copy"]
    (handle,) = seen
    assert handle == ModelHandle(model_key="m1", model_id=state.model_id or "", revision=1)
    assert (rig.run_dir(run_id) / "backups" / "m1.edb").read_bytes() == ORIGINAL
    assert (original.read_bytes(), copy.read_bytes()) == (ACCEPTED, ACCEPTED)
    assert not list(tmp_path.glob("*.promoting"))
    events = rig.events(run_id)
    (promoted,) = [e for e in events if isinstance(e.payload, ev.ModelSaved) and e.payload.role == "promoted"]
    assert promoted.path == "2"
    # the accepted revision's state as the host reports it: the fake host keeps the hash of the file it copied
    assert promoted.payload == ev.ModelSaved(
        model_key="m1", model_id=state.model_id or "", revision=1, fingerprint="fp1", file_sha256=sha(ORIGINAL),
        file_name="m1.edb", role="promoted", origin_sha256=sha(ORIGINAL), origin_file_names=["m1.edb"],
    )  # fmt: skip
    step = [e.payload for e in events if e.path == "2"]
    assert [type(p) for p in step] == [ev.StepStarted, ev.ModelSaved, ev.StepCompleted]
    assert isinstance(step[0], ev.StepStarted)
    assert (step[0].kind, step[0].name, step[0].model_key) == (
        "promote",
        "file_copy",
        None,
    )  # the host's model is not written
    assert (step[0].effect, step[0].op_id) == ("write", op_id(run_id, "2", 1))  # spec 4.3.2: a promote is a write

    asyncio.run(rig.engine(workflow).resume(run_id))  # an ended run is not run again: nothing is copied twice
    assert (original.read_bytes(), len(seen)) == (ACCEPTED, 1)


def test_conflict_when_the_original_changed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC52: an original whose hash changed since the working copy was taken is `CONFLICT` and nothing is copied."""
    rig = mode_rig(tmp_path)
    original, copy = give_files(rig, monkeypatch, tmp_path, "m1", ORIGINAL, ACCEPTED)
    stored_writes(rig, monkeypatch)

    workflow, seen = promoting(rig)
    engine, run_id = approved(rig, workflow)
    original.write_bytes(b"edited by hand")  # between the approval and the promotion, outside block code
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    (refused,) = seen
    assert isinstance(refused, ContractError)
    assert refused.detail.code is ErrorCode.CONFLICT
    assert (original.read_bytes(), copy.read_bytes()) == (b"edited by hand", ACCEPTED)
    assert not (rig.run_dir(run_id) / "backups").exists()
    assert [e.type for e in rig.events(run_id) if e.path == "2"] == [T.STEP_STARTED, T.STEP_FAILED]


def test_promotion_rechecks_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC52: a copy that differs from the approval's binding is `ApprovalVoid`; a wrong approval is a rule violation."""
    rig = mode_rig(tmp_path)
    original, _ = give_files(rig, monkeypatch, tmp_path, "m1", ORIGINAL, ACCEPTED)
    stored_writes(rig, monkeypatch)

    def edit() -> None:  # the engineer edits the copy while the run waits at the approval page
        state = rig.host.models["m1.copy"]
        rig.host.models["m1.copy"] = state.model_copy(update={"revision": 9, "fingerprint": "fp9"})

    workflow, seen = promoting(rig, between=edit)
    engine, run_id = approved(rig, workflow)
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
    (void,) = seen
    assert isinstance(void, errors.ApprovalVoid)
    assert void.message == f"model m1 changed since approval {request_id(run_id, '1')} was shown"
    assert (original.read_bytes(), (rig.run_dir(run_id) / "backups").exists()) == (ORIGINAL, False)

    for name, kwargs, why in (
        ("change set", {"kind": ApprovalKind.CHANGE_SET}, "is not a promotion approval of this run"),
        ("other model", {"models": ("m2",)}, "is not bound to model m1"),
        ("reused", {"again": True}, "was used by an earlier promotion"),
    ):
        other = mode_rig(tmp_path / name.replace(" ", "-"))
        folder = tmp_path / name.replace(" ", "-")
        folder.mkdir(exist_ok=True)
        files = give_files(other, monkeypatch, folder, "m1", ORIGINAL, ACCEPTED)
        stored_writes(other, monkeypatch)
        workflow, seen = promoting(other, **kwargs)
        engine, run_id = approved(other, workflow)
        assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED
        refused = seen[-1]
        assert isinstance(refused, errors.BlockRuleViolation), name
        assert why in refused.message, name
        assert (files[0].read_bytes() == ORIGINAL) is (name != "reused"), name  # the first promotion of "reused" worked

    rejected = mode_rig(tmp_path / "rejected")
    (tmp_path / "rejected").mkdir(exist_ok=True)
    files = give_files(rejected, monkeypatch, tmp_path / "rejected", "m1", ORIGINAL, ACCEPTED)
    stored_writes(rejected, monkeypatch)
    workflow, seen = promoting(rejected)
    engine = rejected.engine(workflow)
    paused = asyncio.run(engine.start(request(mode=PermissionMode.WORK_ON_COPY)))
    rejected.approvals.script(
        request_id(paused.run_id, "1"), reply(rejected, decision="reject", rejected={"i1": "not this one"})
    )
    assert asyncio.run(engine.resume(paused.run_id)).status is RunStatus.COMPLETED
    assert isinstance(seen[0], errors.BlockRuleViolation)
    assert "is not approved" in seen[0].message
    assert files[0].read_bytes() == ORIGINAL


def test_replay_promotion_is_a_gap(tmp_path: Path) -> None:
    """AC53: promotion by replaying writes is `NOT_IMPLEMENTED` (gap E-G1); no step is journaled and nothing copied."""
    rig = mode_rig(tmp_path)
    caught: list[errors.NotImplementedGap] = []
    handle = ModelHandle(model_key="m1", model_id=rig.host.models["m1"].model_id or "", revision=0)
    approval = Approval(request_id="apr_x", approved=True, rejected_items=(), item_reasons={}, reason=None)

    async def body(ctx: Any) -> list[str]:
        try:
            await ctx.promote(handle, Promotion.REPLAY_WRITES, approval)
        except errors.NotImplementedGap as exc:
            caught.append(exc)
        return []

    outcome = asyncio.run(rig.engine(flow(body)).start(request(mode=PermissionMode.WORK_ON_COPY)))
    assert outcome.status is RunStatus.COMPLETED
    (gap,) = caught
    assert (gap.code, list(gap.evidence)) == (errors.HarnessCode.NOT_IMPLEMENTED, ["E-G1"])
    assert "gap E-G1" in gap.message
    assert not [e for e in rig.events(outcome.run_id) if e.path and not e.path.startswith("@")]
    assert rig.host.ledger == []


def test_promotion_without_a_working_copy_is_refused(tmp_path: Path) -> None:
    """Spec §11 Q42: a model with no working copy has no target; `BlockRuleViolation`, no step journaled."""
    rig = mode_rig(tmp_path)
    caught: list[errors.BlockRuleViolation] = []
    handle = ModelHandle(model_key="m1", model_id=rig.host.models["m1"].model_id or "", revision=0)
    approval = Approval(request_id="apr_x", approved=True, rejected_items=(), item_reasons={}, reason=None)

    async def body(ctx: Any) -> list[str]:
        try:
            await ctx.promote(handle, Promotion.FILE_COPY, approval)
        except errors.BlockRuleViolation as exc:
            caught.append(exc)
        return []

    outcome = asyncio.run(rig.engine(flow(body)).start(request(mode=PermissionMode.WORK_ON_COPY)))
    assert outcome.status is RunStatus.COMPLETED
    assert [c.message for c in caught] == ["model m1 has no working copy to promote"]
    assert not [e for e in rig.events(outcome.run_id) if e.path and not e.path.startswith("@")]
