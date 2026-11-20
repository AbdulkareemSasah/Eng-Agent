"""Golden cases of the footing calcs (plan 0010 T3; spec 0010 section 3.3): loader and lint, test support.

A case file holds one hand-derived case of a calc of spec 0010 section 4.4: the input as the resolved payloads, the
result ids of the referenced records, and the expected body. Every value is synthetic and says so.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from eng_contract.refs import parse_ref
from pydantic import BaseModel, ConfigDict, Field

from eng_harness.calc import InputMeta, RefMeta

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "data" / "golden" / "footing"
METHOD_REF = r"^§4\.4\.[1-6]\s+\S"
"""A rule of spec 0010 sections 4.4.1 to 4.4.6, such as "§4.4.1 S5"."""


class FootingGoldenCase(BaseModel):
    """One golden case; no field outside this schema is allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, pattern=r"\S")
    method_ref: str = Field(pattern=METHOD_REF)
    synthetic: Literal[True]
    derivation: str = Field(min_length=1, pattern=r"\S")
    input: dict[str, Any]
    refs: dict[str, str]
    expected: dict[str, Any]


def load_cases(prefix: str) -> dict[str, FootingGoldenCase]:
    """The cases of the files `<prefix>-*.json`, by file stem, sorted by name."""
    return {
        path.stem: FootingGoldenCase.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(GOLDEN_DIR.glob(f"{prefix}-*.json"))
    }


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
