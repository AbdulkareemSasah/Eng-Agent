"""Fixture workflow module: workflow `beta` version 2 (plan 0001 T5). A test double, never shipped."""

from eng_harness.block import workflow
from pydantic import BaseModel


class BetaInput(BaseModel):
    """Input of the fixture workflow."""

    label: str


class BetaOutput(BaseModel):
    """Output of the fixture workflow."""

    label: str


@workflow(
    name="beta",
    version=2,
    description="Fixture workflow that returns its label.",
    required_basis=("limits.drift_ratio",),
    min_server_builds={"fixture-server": "build-1"},
    always_ask=("fixture_unlock",),
)
async def beta(ctx: object, inp: BetaInput) -> BetaOutput:
    return BetaOutput(label=inp.label)
