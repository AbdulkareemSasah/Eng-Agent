"""Test blocks and the engine builder of the calc step workflow tests (plan 0003 T5; spec 0003 AC17).

Test doubles; never shipped. The engine is the real one, the CalcPort the real `HarnessCalcPort`; only the host is the
fake. Plan 0003 T8 adds its older-revision block here.
"""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from eng_contract.refs import Ref
from fakes.ports import FakeApprovalPort, FakeBasisPort, FakeInputPort

from eng_harness.block import BlockDef, Registry
from eng_harness.engine import Engine, EnginePorts, EngineSettings
from eng_harness.ports import CalcPort
from workflows.chain import ChainInput, ChainOutput
from workflows.ctx_flows import flow
from workflows.rig import Rig, Spy

Body = Callable[[Any], Awaitable[Sequence[str]]]


def engine(rig: Rig, port: CalcPort, *workflows: BlockDef[Any, Any]) -> Engine:
    """An engine over the rig's fake host and `port`, with the rig's store, clock and ids."""
    ports = EnginePorts(
        tool=Spy("tool", rig.host, rig.log),
        host=Spy("host", rig.host, rig.log),
        calc=Spy("calc", port, rig.log),
        basis=Spy("basis", FakeBasisPort({}), rig.log),
        approvals=Spy("approvals", FakeApprovalPort(), rig.log),
        inputs=Spy("inputs", FakeInputPort(), rig.log),
    )
    return Engine(rig.workspace, Registry(workflows), ports, rig.store, EngineSettings(), rig.clock, rig.ids)


def diff_step(body: Body) -> BlockDef[ChainInput, ChainOutput]:
    """Workflow wrapper for the older-revision difference-report test (spec 0003 AC48)."""

    async def wrapper(ctx: Any) -> Sequence[str]:
        return await body(ctx)

    return flow(wrapper)


def calc_step(calc_id: str, offset: float) -> BlockDef[ChainInput, ChainOutput]:
    """A workflow that reads with `read_a`, runs `calc_id` on the read result, reads the calc result back.

    Its output holds the reference of the calc result and, as a second entry, the value read back at `/total`.
    """

    async def body(ctx: Any) -> Sequence[str]:
        read = await ctx.tool("read_a", {"n": 0})
        span = Ref.model_validate({"$ref": f"{read.ref.ref}#/value/span_mm"})
        result = await ctx.calc(calc_id, {"span_mm": span, "offset": offset})
        total = await ctx.read(result, "/total")
        return [result.ref.ref, repr(total.value)]

    return flow(body)
