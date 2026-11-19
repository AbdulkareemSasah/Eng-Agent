"""Golden cases of the column-workflow calcs (plan 0013 T2; spec 0013 section 3.2): loader, test support.

A case file `<prefix>-<name>.json` holds one hand-derived case of a calc of spec 0013 section 4.4: the input as the
resolved payloads, the result id of each referenced record, and the expected body. Every value is synthetic and says
so. The later column calcs (plan 0013 T3, T4, T5, T7, T8) add their prefixes to `test_golden.py`.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from eng_contract.refs import parse_ref
from pydantic import BaseModel, ConfigDict, Field

from eng_harness.calc import InputMeta, RefMeta

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "data" / "golden" / "column_design"
METHOD_REF = r"^§4\.4\.[1-6]\s+\S"
"""A rule of spec 0013 sections 4.4.1 to 4.4.6, such as "§4.4.1 L2"."""


class ColumnGoldenCase(BaseModel):
    """One golden case; no field outside this schema is allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, pattern=r"\S")
    method_ref: str = Field(pattern=METHOD_REF)
    synthetic: Literal[True]
    derivation: str = Field(min_length=1, pattern=r"\S")
    input: dict[str, Any]
    refs: dict[str, str]
    expected: dict[str, Any]


def golden_files(directory: Path = GOLDEN_DIR) -> dict[str, Path]:
    """The case files by stem, sorted by name."""
    return {path.stem: path for path in sorted(directory.glob("*.json"))}


def load_case(path: Path) -> ColumnGoldenCase:
    """One case file, validated against the schema."""
    return ColumnGoldenCase.model_validate(json.loads(path.read_text(encoding="utf-8")))


def input_meta(refs: Mapping[str, str], kinds: Mapping[str, str]) -> InputMeta:
    """`InputMeta` for the given result ids; `kinds` names the record kind of each input field."""
    return InputMeta(
        refs={
            name: RefMeta(
                result_id=parse_ref(result_id)[0],
                ref=result_id,
                kind=kinds[name],
                complete=True,
                model_id=None,
                model_revision=None,
                parents=(),
                producer_tool="fixture_tool",
            )
            for name, result_id in refs.items()
        }
    )
