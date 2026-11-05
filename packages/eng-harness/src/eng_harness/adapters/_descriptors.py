"""Tool descriptors: one allowlist entry as data (spec 0002 section 4.5.1).

Purpose: the facts about a host tool that the framework needs before any call, taken from the adapter's reviewed
allowlist file and never from the server's own tool list. Units: none; timeouts are classes, whose seconds come from
`harness.toml`. Errors: a malformed entry raises `pydantic.ValidationError` (wrapped by the loader).
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from eng_harness.servers._config import ReleaseMarked

__all__ = ["ToolDescriptor"]


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

    @model_validator(mode="after")
    def _write_has_readback(self) -> Self:
        if self.effect == "write" and self.readback is None:
            raise ValueError("readback is required for a write tool")
        return self
