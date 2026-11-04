"""Fixture block module: block `alpha` version 1 (plan 0001 T5). A test double, never shipped."""

from pydantic import BaseModel

from eng_harness.block import block


class AlphaInput(BaseModel):
    """Input of the fixture block."""

    count: int


class AlphaOutput(BaseModel):
    """Output of the fixture block."""

    count: int


@block(name="alpha", version=1)
async def alpha(ctx: object, inp: AlphaInput) -> AlphaOutput:
    return AlphaOutput(count=inp.count)
