"""The ``[tool.eng-gate]`` table of a member's ``pyproject.toml`` (spec section 5)."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, model_validator

from eng_dev_gate.config.floors import FLOORS
from eng_dev_gate.config.gate_config import ConfigError

Percent = Annotated[StrictInt, Field(ge=0, le=100)]
Globs = list[Annotated[str, Field(min_length=1)]]


class GeneratedEntry(BaseModel):
    """A generated document: file ``path``, producing ``module`` and its ``args`` (process/05 section 1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    module: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)


class PackageConfig(BaseModel):
    """``[tool.eng-gate]``: unknown keys are rejected, so a package cannot carry the mode or relax a rule.

    Coverage and ``mutation_min`` are percentages; ``*_modules`` are globs relative to the package.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: Literal["contract", "server", "codes", "harness", "tool"]
    layer: StrictInt | Literal["tool", "product"]
    import_names: list[str] = Field(min_length=1)
    public_modules: list[str] = Field(default_factory=list)
    coverage_line: Percent
    coverage_branch: Percent
    r1_modules: Globs = Field(default_factory=list)
    r2_modules: Globs = Field(default_factory=list)
    mutation_min: Percent | None = None
    check_modules: Globs = Field(default_factory=list)
    calc_modules: Globs = Field(default_factory=list)
    block_modules: Globs = Field(default_factory=list)
    rule_modules: Globs = Field(default_factory=list)
    windows_tests: list[str] = Field(default_factory=list)
    generated: list[GeneratedEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _layer_matches_profile(self) -> Self:
        if self.layer != FLOORS[self.profile].layer:
            raise ValueError(f"layer {self.layer!r} is not the layer {FLOORS[self.profile].layer!r} of {self.profile}")
        return self


def parse_package_config(table: Mapping[str, Any]) -> PackageConfig:  # Any: TOML values at the boundary
    """Validate a ``[tool.eng-gate]`` table.

    Raises:
        ConfigError: CF001, the table is invalid (unknown key, wrong type, bound or layer).
    """
    try:
        return PackageConfig.model_validate(dict(table))
    except ValidationError as error:
        raise ConfigError("CF001", f"invalid [tool.eng-gate]: {error}") from error


def load_package_config(pyproject: Path) -> PackageConfig:
    """Read and validate ``[tool.eng-gate]`` from ``pyproject``.

    Raises:
        ConfigError: CF001 for an unreadable or malformed file or table, CF006 when the table is missing.
    """
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError("CF001", f"cannot read {pyproject}: {error}") from error
    table = data.get("tool", {}).get("eng-gate")
    if table is None:
        raise ConfigError("CF006", f"{pyproject} has no [tool.eng-gate] table")
    if not isinstance(table, dict):
        raise ConfigError("CF001", f"[tool.eng-gate] in {pyproject} is not a table")
    return parse_package_config(table)
