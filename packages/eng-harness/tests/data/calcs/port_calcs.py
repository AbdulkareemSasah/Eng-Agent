"""Test-double calc for the CalcPort tests (plan 0003 T5). Never registered in `REGISTRY`; no engineering content.

The values are synthetic. The module is loaded by path (it is test data), also by the child processes of the
determinism test.
"""

from eng_contract.kinds import KindRegistry
from eng_contract.params import eng_param
from pydantic import BaseModel, ConfigDict

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import CalcInput, InputMeta, NotImplementedGap, TraceBuilder, calc
from eng_harness.kinds.calcs import CalcPayload

OUTPUT_KIND = "harness.port_out/1"
CALC_ID = "harness.port_sum"
SOURCE_KIND = "harness.run_output/1"
OTHER_KIND = "harness.run_input/1"
GAP_ID = "G-TEST-1"


class PortBody(BaseModel):
    """The payload of the fixture calc without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total: float
    items: int
    complete: bool


class PortOut(CalcPayload, PortBody):
    """The stored payload: the body with the identity, draft mark and trace the framework adds."""


class PortIn(CalcInput):
    """Input: a required reference-only length, an optional older length (`stale_ok`), a list and literals."""

    span_mm: float = eng_param(
        unit="mm",
        ge=0,
        bounds_source="Test double bound, not a project value",
        ref_capable=True,
        engineering_quantity=True,
        ref_kinds={SOURCE_KIND},
    )
    older_mm: float = eng_param(0.0, unit="mm", ref_capable=True, stale_ok=True)
    rows: list[float] = eng_param([], ref_capable=True)
    offset: float = 0.0
    whole: bool = True
    gap: bool = False
    boom: bool = False


@calc(
    id=CALC_ID,
    version=2,
    output_kind=OUTPUT_KIND,
    title="Port sum",
    method_source="Test double: total is span plus older plus offset (no engineering content)",
)
def port_sum(inp: PortIn, meta: InputMeta, trace: TraceBuilder) -> PortBody:
    """Add the lengths and record the trace; `gap` reaches a path marked not implemented."""
    if inp.gap:
        raise NotImplementedGap(f"{GAP_ID}: this path is not implemented")
    if inp.boom:
        raise RuntimeError("defect")
    trace.input("span_mm", inp.span_mm, unit="mm", ref=f"{meta.refs['span_mm'].result_id}#/value/span_mm")
    trace.input("offset", inp.offset)
    total = inp.span_mm + inp.older_mm + inp.offset
    trace.step(
        "total",
        total,
        unit="mm",
        formula="span_mm + older_mm + offset",
        source="fixture rule R1",
        uses=["span_mm", "offset"],
    )
    trace.output("total")
    return PortBody(total=total, items=len(inp.rows), complete=inp.whole)


def kinds() -> KindRegistry:
    """The harness kinds with the fixture calc's output kind."""
    return HARNESS_KINDS.extend({OUTPUT_KIND: PortOut})
