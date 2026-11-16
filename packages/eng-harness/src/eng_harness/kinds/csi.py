"""Payload models of the CSI harness kinds, as the host gave them (plan 0002 T21; spec 0002 4.6; spec 0003 4.3)."""

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictInt


class CsiModelStatus(BaseModel):
    """`harness.csi_model_status/1` (spec 0002 section 4.6.4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    units: str
    locked: bool | None = None
    object_counts: dict[str, int] = Field(default_factory=dict)
    program_version: str = ""
    file_name: str = Field(min_length=1)


class _Host(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CsiAnalysisRun(_Host):
    """`harness.csi_analysis_run/1`: `started`, which the host reports only after the analysis finished (S-12 5)."""

    started: StrictBool


class CaseStatus(_Host):
    """The raw status code of one case, not decoded (spec 0002 section 4.6.1)."""

    case: str = Field(min_length=1)
    status_code: StrictInt


class CsiAnalysisStatus(_Host):
    """`harness.csi_analysis_status/1`: the host's per-case status codes."""

    cases: list[CaseStatus]


class CsiDesignRun(_Host):
    """`harness.csi_design_run/1`: the host's reply to the design run, as it is."""

    reply: dict[str, JsonValue]


class CsiRows(_Host):
    """`harness.csi_design_results/1` (design output, never a verdict, design 06 section 9) and
    `harness.csi_analysis_messages/1` (rows of the `Analysis Messages` table): the host's rows as read.
    """

    rows: list[dict[str, JsonValue]]


CSI_KINDS: dict[str, type[BaseModel]] = {
    "harness.csi_model_status/1": CsiModelStatus,
    "harness.csi_analysis_run/1": CsiAnalysisRun,
    "harness.csi_analysis_status/1": CsiAnalysisStatus,
    "harness.csi_design_run/1": CsiDesignRun,
    "harness.csi_design_results/1": CsiRows,
    "harness.csi_analysis_messages/1": CsiRows,
}
