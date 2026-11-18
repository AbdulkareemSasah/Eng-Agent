"""A model key in previews and promotion (plan 0001 T23; AC72).

Block code has no `ModelHandle`; it names a model by its key. The rig is the fake host of `work_on_copy` with real
files, as in `tests/unit/test_promote.py`.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from workflows.ctx_flows import flow, reply, request_id
from workflows.modes import give_files, mode_rig, stored_writes
from workflows.rig import request

from eng_harness.ctx import ApprovalKind, ModelHandle, Preview, PreviewItem, Promotion
from eng_harness.engine import PermissionMode, RunStatus
from eng_harness.journal import _events as ev


def _keyed(item: str) -> Preview:
    return Preview(items=(PreviewItem(id=item, label=f"Change {item}", refs=()),), diff_ref=None, models=("m1",))


def test_preview_and_promote_take_a_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC72: a preview and a promotion that name the model by its key bind and promote as a handle of that key does."""
    rig = mode_rig(tmp_path)
    original, copy = give_files(rig, monkeypatch, tmp_path, "m1", b"original", b"accepted")
    stored_writes(rig, monkeypatch)
    seen: list[ModelHandle] = []

    async def body(ctx: Any) -> list[str]:
        change = await ctx.approve("Apply", _keyed("i1"), kind=ApprovalKind.CHANGE_SET)
        await ctx.tool("write_b", {"n": 1, "model": "m1"}, under=change)  # takes the working copy
        approval = await ctx.approve("Promote", _keyed("i2"), kind=ApprovalKind.PROMOTION)
        seen.append(await ctx.promote("m1", Promotion.FILE_COPY, approval))
        return []

    engine = rig.engine(flow(body))
    paused = asyncio.run(engine.start(request(mode=PermissionMode.WORK_ON_COPY)))
    run_id = paused.run_id
    rig.approvals.script(request_id(run_id, "0"), reply(rig))
    asked_again = asyncio.run(engine.resume(run_id))
    assert asked_again.status is RunStatus.PAUSED
    rig.approvals.script(request_id(run_id, "2"), reply(rig))
    assert asyncio.run(engine.resume(run_id)).status is RunStatus.COMPLETED

    state = rig.host.models["m1.copy"]
    assert seen == [ModelHandle(model_key="m1", model_id=state.model_id or "", revision=1)]
    assert (original.read_bytes(), copy.read_bytes()) == (b"accepted", b"accepted")
    requested = [e.payload for e in rig.events(run_id) if isinstance(e.payload, ev.ApprovalRequested)]
    assert [list(r.binding) for r in requested] == [["m1"], ["m1"]]
    for r in requested:  # the stored preview holds the key, no model id and no revision
        assert rig.store.payload(r.preview_ref)["models"] == ["m1"]
