"""Test-double calcs for the framework tests (plan 0003 T1). Never registered in `REGISTRY`; no engineering content."""

from eng_contract.params import eng_param
from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from pydantic import BaseModel, ConfigDict

OUTPUT_KIND = "harness.fixture_out/1"
SYNTHETIC_ID = "res_00000000000000000000000000"


class FixtureOut(BaseModel):
    """Payload of the fixture calc."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total: float


class FixtureIn(CalcInput):
    """Input of the fixture calc: one reference-capable length and one literal."""

    span_mm: float = eng_param(unit="mm", ref_capable=True)
    offset: float = 0.0


@calc(
    id="harness.fixture_sum",
    version=3,
    output_kind=OUTPUT_KIND,
    title="Fixture sum",
    method_source="Test double: total is span plus offset (no engineering content)",
)
def fixture_sum(inp: FixtureIn, meta: InputMeta, trace: TraceBuilder) -> FixtureOut:
    """Add the offset to the span and record the trace."""
    trace.input("span_mm", inp.span_mm, unit="mm", ref=f"{meta.refs['span_mm'].result_id}#/value")
    trace.input("offset", inp.offset)
    total = inp.span_mm + inp.offset
    trace.step(
        "total", total, unit="mm", formula="span_mm + offset", source="fixture rule R1", uses=["span_mm", "offset"]
    )
    trace.output("total")
    return FixtureOut(total=total)
