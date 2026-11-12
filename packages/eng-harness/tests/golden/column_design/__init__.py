"""Golden loader for column-workflow calcs (plan 0013 T2; spec 0013 section 3.2)."""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "data" / "golden" / "column_design"
METHOD_REF = r"^§4\.4\.1\s+L[123]$"


class GoldenInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input: dict[str, Any]
    meta: dict[str, Any]


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, pattern=r"\S")
    method_ref: str = Field(pattern=METHOD_REF)
    synthetic: Literal[True]
    derivation: str = Field(min_length=1, pattern=r"\S")
    inputs: GoldenInputs
    expected: dict[str, Any]


def golden_files(directory: Path = GOLDEN_DIR) -> list[Path]:
    return sorted(directory.glob("column-select-*.json"))


def load_case(path: Path) -> GoldenCase:
    return GoldenCase.model_validate(json.loads(path.read_text(encoding="utf-8")))
