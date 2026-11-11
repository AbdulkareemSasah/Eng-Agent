"""Tool descriptors: one allowlist entry as data (spec 0002 section 4.5.1).

Purpose: the facts about a host tool that the framework needs before any call, taken from the adapter's reviewed
allowlist file and never from the server's own tool list. Units: none; timeouts are classes, whose seconds come from
`harness.toml`. A `[[unit]]` entry records a unit the server does not switch (AC42). Errors: a malformed entry raises
`pydantic.ValidationError` (wrapped by the loader).
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from eng_harness.servers._config import ReleaseMarked

__all__ = ["ToolDescriptor", "UnitHeader"]


class UnitHeader(BaseModel):
    """One `[[unit]]` entry (spec 0002 section 4.5.1, AC42).

    `unit` is a contract unit token, or absent. It is absent exactly when `unit_status` is `missing`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str = Field(pattern=r"^[a-z][a-z0-9_]*$")  # the same name rule as a tool entry
    field: str
    unit: str | None = None
    unit_status: Literal["declared", "missing", "confirmed"]

    @model_validator(mode="after")
    def _unit_matches_status(self) -> Self:
        if (self.unit_status == "missing") == (self.unit is not None):
            raise ValueError("unit is absent exactly when unit_status is missing")
        return self


class ToolDescriptor(ReleaseMarked):
    """One `[[tool]]` entry; `release` and `release_record` come from `ReleaseMarked` (AC38).

    `result_kind` is `None` for a tool whose reply only feeds an adapter reader or a session operation and is not
    stored as a result by itself.
    """

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: Literal["read", "write", "analysis", "design", "session"]  # S-12 classification, reviewed
    timeout_class: Literal["session", "call", "long"]
    effect: Literal["read", "write"]
    action: Literal["plain", "open", "save", "analysis", "design", "delete", "unlock"]
    args_model: str = Field(pattern=r"^[A-Z][A-Za-z0-9]*$")  # canonical argument model in the adapter's code
    result_kind: str | None = None
    units: Literal["token", "none", "present", "declared_ignored"]
    confirm: Literal["never", "approved", "owned"]
    readback: str | None = Field(default=None, min_length=1)  # read-back helper name
    products: tuple[str, ...] = Field(min_length=1)
    routes: tuple[str, ...] | None = None  # required, and drawn from the header, when the header declares routes
    unit_header: tuple[UnitHeader, ...] = ()  # this tool's [[unit]] entries (AC42); empty when it has none

    @model_validator(mode="after")
    def _write_has_readback(self) -> Self:
        if self.effect == "write" and self.readback is None:
            raise ValueError("readback is required for a write tool")
        return self
