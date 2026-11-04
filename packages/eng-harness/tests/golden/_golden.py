"""Golden data loader and lint (plan 0003 T6; spec 0003 AC46). Test support, not product code."""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "data" / "golden" / "calcs"
METHOD_REF = r"^§4\.(?:[6-9]|1[01])\s+\S"
"""A rule of spec 0003 sections 4.6 to 4.11, such as "§4.7 D3"."""


class GoldenInputs(BaseModel):
    """The calc input and its metadata; no other key is allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input: dict[str, Any]
    meta: dict[str, Any]


class GoldenCase(BaseModel):
    """One hand-derived golden case; no field outside this schema is allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, pattern=r"\S")
    method_ref: str = Field(pattern=METHOD_REF)
    synthetic: Literal[True]
    derivation: str = Field(min_length=1, pattern=r"\S")
    inputs: GoldenInputs
    expected: dict[str, Any]


def golden_files(directory: Path = GOLDEN_DIR) -> list[Path]:
    """The golden JSON files, sorted by name."""
    return sorted(directory.glob("*.json"))


def load_case(path: Path) -> GoldenCase:
    """Load and validate one golden file; raises ValidationError or JSONDecodeError when it is invalid."""
    return GoldenCase.model_validate(json.loads(path.read_text(encoding="utf-8")))


def lint_golden(path: Path) -> list[str]:
    """Return the problems of one golden file (empty when it passes AC46)."""
    try:
        load_case(path)
    except (ValidationError, json.JSONDecodeError) as error:
        return [str(error)]
    return []
