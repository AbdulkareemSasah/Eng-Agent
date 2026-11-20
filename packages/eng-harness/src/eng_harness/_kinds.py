"""Result kinds of the harness (spec 0001 section 4.4.1), registered with `KindRegistry.extend` (contract 4.10.1)."""

from typing import Annotated

from eng_contract.envelope import FileSource
from eng_contract.kinds import NEUTRAL_KINDS
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

from eng_harness.kinds.calcs import CALC_KINDS
from eng_harness.kinds.column_design import COLUMN_DESIGN_KINDS
from eng_harness.kinds.csi import CSI_KINDS
from eng_harness.kinds.edit_cycle import EDIT_CYCLE_KINDS
from eng_harness.kinds.footing import FOOTING_KINDS
from eng_harness.kinds.revit import REVIT_KINDS

# Same constraints as eng_contract.kinds._common.Name (contract 4.10.1); that symbol is not a public_modules export.
Name = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class Value(BaseModel):
    """A JSON value stored by reference: journal blobs, run input and run output."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    value: JsonValue


class ApprovalPreview(BaseModel):
    """An approval preview; its fields belong to the `Preview` type of plan task T7, so extras pass through."""

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class SafeSoilProperty(BaseModel):
    """One area-spring property of `harness.safe_soil_supports/1` (spec 0008 section 4.4).

    Wire names `u1_kN_m3`, `u2_kN_m3` and `u3_kN_m3` are fixed by the spec; Python attributes stay snake_case
    so N815 needs no new noqa (ratchet RT001).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        serialize_by_alias=True,
        validate_by_name=True,
    )

    name: Name
    stiffness_option: str = Field(min_length=1)
    u1_kn_m3: Annotated[float, Field(allow_inf_nan=False, alias="u1_kN_m3")]
    u2_kn_m3: Annotated[float, Field(allow_inf_nan=False, alias="u2_kN_m3")]
    u3_kn_m3: Annotated[float, Field(allow_inf_nan=False, alias="u3_kN_m3")]
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


class ModelPoint(BaseModel):
    """One point of `harness.model_points/1` (spec 0008 section 4.4)."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    name: Name
    x_mm: Annotated[float, Field(allow_inf_nan=False)]
    y_mm: Annotated[float, Field(allow_inf_nan=False)]
    z_mm: Annotated[float, Field(allow_inf_nan=False)]


class ModelPoints(BaseModel):
    """`harness.model_points/1` from `csi_list_points` (spec 0008 section 4.4, AC9)."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    points: list[ModelPoint]


class JointLoad(BaseModel):
    """One row of `harness.joint_loads/1` (spec 0008 section 4.3).

    Wire names `FX_kN`..`MZ_kNm` and `punch_*_mm` are fixed by the spec; Python attributes stay snake_case.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        serialize_by_alias=True,
        validate_by_name=True,
    )

    joint: Name
    pattern: Name
    fx_kn: Annotated[float, Field(allow_inf_nan=False, alias="FX_kN")]
    fy_kn: Annotated[float, Field(allow_inf_nan=False, alias="FY_kN")]
    fz_kn: Annotated[float, Field(allow_inf_nan=False, alias="FZ_kN")]
    mx_knm: Annotated[float, Field(allow_inf_nan=False, alias="MX_kNm")]
    my_knm: Annotated[float, Field(allow_inf_nan=False, alias="MY_kNm")]
    mz_knm: Annotated[float, Field(allow_inf_nan=False, alias="MZ_kNm")]
    punch_x_mm: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    punch_y_mm: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None


class JointLoads(BaseModel):
    """`harness.joint_loads/1` (spec 0008 section 4.3, 4.4; AC9)."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    axes: Annotated[str, Field(pattern=r"^global$")] = "global"
    loads: list[JointLoad]


HARNESS_KINDS = NEUTRAL_KINDS.extend(
    {
        "harness.journal_blob/1": Value,
        "harness.run_input/1": Value,
        "harness.run_output/1": Value,
        "harness.approval_preview/1": ApprovalPreview,
        "harness.file_input/1": FileSource,  # an engineer-provided file, hashed (spec 0002 section 4.7)
        "harness.safe_soil_supports/1": SafeSoilSupports,  # plan 0008 T4; spec 0008 section 4.4, AC12
        "harness.model_points/1": ModelPoints,  # plan 0008 T5; spec 0008 section 4.4, AC9
        "harness.joint_loads/1": JointLoads,  # plan 0008 T5; spec 0008 section 4.3, 4.4, AC9
    }
).extend(CALC_KINDS | FOOTING_KINDS | EDIT_CYCLE_KINDS | CSI_KINDS | COLUMN_DESIGN_KINDS | REVIT_KINDS)
"""Neutral, harness, calc, footing, edit-cycle, CSI, column and Revit kinds (0011 §4.5)."""
