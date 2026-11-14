"""A pause cannot be swallowed by block code (plan 0001 T15; spec 0001 AC10).

An approval without an answer pauses the run with a stop that derives from `BaseException`, so a block that wraps
`ctx.approve` in `except Exception` still stops at the request.
"""

import asyncio
from pathlib import Path
from typing import Any

from workflows.ctx_flows import change_set, flow, request_id
from workflows.rig import make_rig, request

from eng_harness.engine import RunStatus
from eng_harness.journal import _events as ev


def test_except_exception_cannot_swallow_pause(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    shown = change_set(rig, "i1")
    swallowed: list[str] = []
    after: list[str] = []

    async def body(ctx: Any) -> list[str]:
        try:
            await ctx.approve("Apply", shown)
        except Exception as exc:  # the block tries to carry on without the engineer
            swallowed.append(repr(exc))
        after.append("went on")
        return []

    paused = asyncio.run(rig.engine(flow(body)).start(request()))
    rid = request_id(paused.run_id, "0")
    assert (paused.status, paused.pending) == (RunStatus.PAUSED, (rid,))
    assert (swallowed, after) == ([], [])  # the pause propagated: the block never saw it
    last = rig.events(paused.run_id)[-1]
    assert last.payload == ev.RunPaused(reason="awaiting_approval", request_ids=[rid])
