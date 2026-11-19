"""Result kinds of the harness (spec 0001 section 4.4.1), registered with `KindRegistry.extend` (contract 4.10.1)."""

# ruff: noqa: N815  # B-213: soil-support field names with unit capitals are fixed by spec 0008 section 4.4

from typing import Annotated

from eng_contract.envelope import FileSource
from eng_contract.kinds import NEUTRAL_KINDS
from eng_contract.kinds._common import Name
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from eng_harness.kinds.calcs import CALC_KINDS
from eng_harness.kinds.column_design import COLUMN_DESIGN_KINDS
from eng_harness.kinds.csi import CSI_KINDS
from eng_harness.kinds.edit_cycle import EDIT_CYCLE_KINDS
from eng_harness.kinds.footing import FOOTING_KINDS


class Value(BaseModel):
    """A JSON value stored by reference: journal blobs, run input and run output."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    value: JsonValue


class ApprovalPreview(BaseModel):
    """An approval preview; its fields belong to the `Preview` type of plan task T7, so extras pass through."""

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class SafeSoilProperty(BaseModel):
    """One area-spring property of `harness.safe_soil_supports/1` (spec 0008 section 4.4)."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    name: Name
    stiffness_option: str = Field(min_length=1)
    u1_kN_m3: Annotated[float, Field(allow_inf_nan=False)]
    u2_kN_m3: Annotated[float, Field(allow_inf_nan=False)]
    u3_kN_m3: Annotated[float, Field(allow_inf_nan=False)]
    nonlinear_u3: str = Field(min_length=1)


class SafeSoilAssignment(BaseModel):
    """One area-to-spring assignment; `property` is null when the host value is `None` (AC12)."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    area: Name
    property: Name | None = None


class SafeSoilSupports(BaseModel):
    """`harness.safe_soil_supports/1` (spec 0008 section 4.4, AC12)."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    properties: list[SafeSoilProperty]
    assignments: list[SafeSoilAssignment]


HARNESS_KINDS = NEUTRAL_KINDS.extend(
    {
        "harness.journal_blob/1": Value,
        "harness.run_input/1": Value,
        "harness.run_output/1": Value,
        "harness.approval_preview/1": ApprovalPreview,
        "harness.file_input/1": FileSource,  # an engineer-provided file, hashed (spec 0002 section 4.7)
        "harness.safe_soil_supports/1": SafeSoilSupports,  # plan 0008 T4; spec 0008 section 4.4, AC12
    }
).extend(CALC_KINDS | FOOTING_KINDS | EDIT_CYCLE_KINDS | CSI_KINDS | COLUMN_DESIGN_KINDS)
"""The neutral, harness, calc (0003 4.6 to 4.11), footing (0010 4.2), edit-cycle, CSI (0002 4.6) and column kinds."""
