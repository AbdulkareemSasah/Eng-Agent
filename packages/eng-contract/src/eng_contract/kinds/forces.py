"""The `forces.*` kinds, version 1 (spec 4.10.2): analysis results read from the host, as the host reports them.

Units: kN, kN.m, mm as the field suffixes say; `drift_ratio` has no unit.
Errors: `pydantic.ValidationError` for every violated rule. These kinds are frozen: any change is a new version.
"""

from typing import Annotated, Literal

from pydantic import Field

from eng_contract.kinds._common import CaseRef, Name, Payload

_NonNegative = Annotated[float, Field(ge=0)]


class JointReaction(Payload):
    """Reaction of one joint for one case, in global axes."""

    joint: Name
    case: CaseRef
    FX_kN: float
    FY_kN: float
    FZ_kN: float
    MX_kNm: float
    MY_kNm: float
    MZ_kNm: float


class JointReactions(Payload):
    """`forces.joint_reactions/1`."""

    axes: Literal["global"]
    rows: list[JointReaction]


class MemberEndForce(Payload):
    """Internal forces of a member at `station_mm` from its i end; `end` is set when the row is an end value."""

    member: Name
    case: CaseRef
    end: Literal["i", "j"] | None
    station_mm: _NonNegative
    P_kN: float
    V2_kN: float
    V3_kN: float
    T_kNm: float
    M2_kNm: float
    M3_kNm: float


class MemberEnd(Payload):
    """`forces.member_end/1`: signs follow the host's local axes (gap G-3), recorded by `sign_convention`."""

    sign_convention: Literal["host_local/1"]
    rows: list[MemberEndForce]


class StoryDrift(Payload):
    """Drift of one story in one direction; `point` and its coordinates are those of the governing joint."""

    story: Name
    case: CaseRef
    direction: Literal["X", "Y"]
    drift_ratio: _NonNegative
    point: Name | None = None
    x_mm: float | None = None
    y_mm: float | None = None
    z_mm: float | None = None


class StoryDrifts(Payload):
    """`forces.story_drifts/1`."""

    rows: list[StoryDrift]
