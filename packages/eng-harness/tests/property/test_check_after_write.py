"""Every generated step program checks a model after writing it, before using it (plan 0001 T12; spec 0001 AC37)."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from hypothesis import example, given, settings
from hypothesis import strategies as st
from workflows.ctx_flows import flow, success
from workflows.rig import make_rig, request

from eng_harness.calc import CalcStatus
from eng_harness.engine import RunStatus
from eng_harness.journal import Event
from eng_harness.journal import _events as ev
from eng_harness.ports import CalcInfo, ToolInfo

_SHA = "cd" * 32
_OP = st.tuples(st.sampled_from(["write", "read", "calc"]), st.sampled_from(["m1", "m2"]))


def _unchecked(events: list[Event]) -> str | None:
    """Why a write is still dirty at a read of that model, a calc, or the block's return."""
    dirty: set[str] = set()
    started: dict[str, ev.StepStarted] = {}
    for event in events:
        payload, path = event.payload, event.path
        if isinstance(payload, ev.StepStarted) and path is not None:
            started[path] = payload
            if payload.kind == "calc" and dirty:
                return f"calc at {path} while {sorted(dirty)} are dirty"
            if payload.kind == "tool" and payload.effect == "read" and payload.model_key in dirty:
                return f"read of {payload.model_key} at {path} while it is dirty"
        elif isinstance(payload, ev.StepCompleted) and path in started:
            began = started[path]
            if began.name == "check_model" and began.model_key:
                dirty.discard(began.model_key)
            elif began.effect == "write" and began.model_key:
                dirty.add(began.model_key)
        elif isinstance(payload, ev.RunCompleted) and dirty:
            return f"the block returned while {sorted(dirty)} were dirty"
    return None


def _run(root: Path, program: list[tuple[str, str]]) -> str | None:
    rig = make_rig(root)
    specs: tuple[tuple[str, Literal["read", "write"]], ...] = (("write_m", "write"), ("read_m", "read"))
    for name, effect in specs:
        rig.host._tools[name] = ToolInfo(name=name, effect=effect, action="plain", host_key="csi", model_param="model")
    rig.calc_infos.append(
        CalcInfo(
            id="c", version=1, content_sha256=_SHA, status=CalcStatus.APPROVED, engineering_params=(),
            basis_fields=(), ref_rules={},
        )
    )  # fmt: skip
    rig.calc_results["c"] = success(rig, {"ok": True})

    async def body(ctx: Any) -> list[str]:
        for op, model in program:
            if op == "calc":
                await ctx.calc("c", {})
            else:
                await ctx.tool("write_m" if op == "write" else "read_m", {"model": model})
        return []

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.COMPLETED, outcome.escalation
    return _unchecked(rig.events(outcome.run_id))


@settings(derandomize=True, max_examples=20, deadline=None)
@example([("write", "m1")])
@example([("write", "m1"), ("read", "m1")])
@example([("write", "m2"), ("calc", "m1")])
@given(st.lists(_OP, min_size=1, max_size=5))
def test_no_unchecked_use_after_write(program: list[tuple[str, str]]) -> None:
    with TemporaryDirectory() as tmp:
        reason = _run(Path(tmp), program)
    assert reason is None, reason
