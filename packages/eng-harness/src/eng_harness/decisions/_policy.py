"""Decision policy and settings (spec 0005 section 4.3; 12 section 3).

Units: timeouts in milliseconds, confidence as a ratio. Errors: pydantic ``ValidationError`` for out-of-bounds fields.
"""

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DecisionPolicy(BaseModel):
    """Per-point policy; defaults are those of 12 section 3 (golden file ``decision_policy_defaults.json``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: bool = True  # 12 section 3: allows tier 2
    llm: bool = False  # 12 section 3: allows tier 3
    # ratio; raised per point, never lowered (12 section 6)
    min_confidence: float = Field(default=0.85, ge=0.85, le=1.0)
    shadow: bool = True  # effective shadow also needs a ShadowRelease (spec 4.3)
    timeout_ms_model: int = Field(default=1500, ge=1)  # milliseconds, tier 2 (12 section 3)
    timeout_ms_llm: int = Field(default=20000, ge=1)  # milliseconds, tier 3 (12 section 3)
    require_engineer: bool = False  # no provider is consulted when no rule matches


class ShadowRelease(BaseModel):
    """The release of one point version from shadow mode (spec 4.3); ``record`` names the evaluation or decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    point_version: int = Field(ge=1)
    basis: Literal["evaluation", "owner"]
    record: str = Field(min_length=1)


class DecisionSettings(BaseModel):
    """Software settings of the decision layer (read from ``harness.toml`` by spec 0006); not engineering values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_options: int = Field(default=32, ge=1)  # count; spec 4.2, open question Q11
    max_state_bytes: int = Field(default=4096, ge=1)  # bytes of canonical JSON; spec 4.2, Q11
    local_only: bool = False  # 16 section 2: disables non-local providers
    sensitive_values: tuple[str, ...] = ()  # strings that must never leave the machine
    extra_denied_tokens: tuple[str, ...] = ()  # extends the deny list of spec 4.10
    shadow_released: Mapping[str, ShadowRelease] = Field(default_factory=dict)  # keyed by point name
    export_enabled: bool = False
