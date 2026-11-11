"""Result kinds of the harness (spec 0001 section 4.4.1), registered with `KindRegistry.extend` (contract 4.10.1)."""

from eng_contract.envelope import FileSource
from eng_contract.kinds import NEUTRAL_KINDS
from pydantic import BaseModel, ConfigDict, JsonValue

from eng_harness.kinds.calcs import CALC_KINDS
from eng_harness.kinds.edit_cycle import EDIT_CYCLE_KINDS
from eng_harness.kinds.footing import FOOTING_KINDS


class Value(BaseModel):
    """A JSON value stored by reference: journal blobs, run input and run output."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    value: JsonValue


class ApprovalPreview(BaseModel):
    """An approval preview; its fields belong to the `Preview` type of plan task T7, so extras pass through."""

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


HARNESS_KINDS = NEUTRAL_KINDS.extend(
    {
        "harness.journal_blob/1": Value,
        "harness.run_input/1": Value,
        "harness.run_output/1": Value,
        "harness.approval_preview/1": ApprovalPreview,
        "harness.file_input/1": FileSource,  # an engineer-provided file, hashed (spec 0002 section 4.7)
    }
).extend(CALC_KINDS | FOOTING_KINDS | EDIT_CYCLE_KINDS)
"""The neutral, harness, calc (0003 4.6 to 4.11), footing (0010 4.2) and edit-cycle kinds."""
