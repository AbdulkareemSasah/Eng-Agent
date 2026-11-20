"""Payload models of the IDEA harness kinds (plan 0014 T5; spec 0014 section 4.5).

Purpose: validate host-shaped IDEA status, project, loads and check-raw payloads (`extra="forbid"`, versioned `/1`).
Units: load effects of `harness.idea_loads/1` are in kN and kN.m as declared; `position_host` is opaque (IG-9).
Errors: `pydantic.ValidationError`.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StringConstraints

__all__ = [
    "IDEA_KINDS",
    "IdeaCheck",
    "IdeaCheckConnection",
    "IdeaCheckRaw",
    "IdeaConnectionSummary",
    "IdeaInstalledVersion",
    "IdeaLoadEffect",
    "IdeaLoadSegment",
    "IdeaLoads",
    "IdeaProject",
    "IdeaServiceStatus",
    "IdeaStatus",
]

_Str = Annotated[str, StringConstraints(min_length=1, max_length=200)]
_Msg = Annotated[str, StringConstraints(max_length=500)]
_Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class _Host(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class IdeaInstalledVersion(_Host):
    """One installed IDEA StatiCa version from `idea_status`."""

    version: _Str
    has_rest_api: StrictBool
    hidden_calculator: StrictBool


class IdeaServiceStatus(_Host):
    """Reachability of the Connection REST service."""

    reachable: StrictBool
    service_version: str | None = None


class IdeaStatus(_Host):
    """`harness.idea_status/1` (spec 0014 section 4.5)."""

    installed: list[IdeaInstalledVersion]
    service: IdeaServiceStatus
    read_only: StrictBool
    script_enabled: StrictBool


class IdeaConnectionSummary(_Host):
    """One connection listed on a project reply (no paths)."""

    id: StrictInt
    name: _Str
    calculated: StrictBool


class IdeaProject(_Host):
    """`harness.idea_project/1` (spec 0014 section 4.5)."""

    backend: str | None
    service_reachable: StrictBool
    live_project: StrictBool
    connections: list[IdeaConnectionSummary]


class IdeaLoadSegment(_Host):
    """One segment force row of a load effect; `position_host` is opaque (IG-9)."""

    beam_segment_id: StrictInt
    position_host: StrictFloat
    N_kN: StrictFloat
    Qy_kN: StrictFloat
    Qz_kN: StrictFloat
    Mx_kNm: StrictFloat
    My_kNm: StrictFloat
    Mz_kNm: StrictFloat


class IdeaLoadEffect(_Host):
    """One load effect of `harness.idea_loads/1`."""

    id: _Str
    name: _Str
    check_equilibrium: StrictBool
    segments: list[IdeaLoadSegment]


class IdeaLoads(_Host):
    """`harness.idea_loads/1` (spec 0014 section 4.5)."""

    connection: _Str
    effects: list[IdeaLoadEffect]
    percentage_segments_present: StrictBool
    file_sha256: _Sha


class IdeaCheck(_Host):
    """One check row inside `harness.idea_check_raw/1`."""

    name: str = ""
    check_value: StrictFloat
    check_status: StrictBool
    skipped: StrictBool
    message: _Msg = ""
    load_case_id: str | None = None


class IdeaCheckConnection(_Host):
    """One connection result inside `harness.idea_check_raw/1`."""

    connection_id: StrictInt | str
    name: _Str
    passed: StrictBool
    calculated: StrictBool
    checks: list[IdeaCheck]
    errors: list[_Msg] = Field(default_factory=list)
    warnings: list[_Msg] = Field(default_factory=list)


class IdeaCheckRaw(_Host):
    """`harness.idea_check_raw/1` (spec 0014 section 4.5); stored replies keep `offline_stub` false."""

    route: Literal["rest", "native"]
    backend: str | None
    offline_stub: Literal[False]
    connections: list[IdeaCheckConnection]


IDEA_KINDS: dict[str, type[BaseModel]] = {
    "harness.idea_status/1": IdeaStatus,
    "harness.idea_project/1": IdeaProject,
    "harness.idea_loads/1": IdeaLoads,
    "harness.idea_check_raw/1": IdeaCheckRaw,
}
