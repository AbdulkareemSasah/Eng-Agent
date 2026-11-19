from eng_contract.refs import parse_ref
"""Golden cases of the edit-cycle calcs (plan 0007 T2; spec 0007 section 3.2): loader and runner, test support.

A case file holds one hand-derived case of a calc of spec 0007 section 4.4: the input as the resolved payloads, the
result ids of the referenced records, and the expected body. Every value is synthetic and says so.
"""

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from eng_harness.calc import InputMeta, RefMeta, TraceBuilder
from eng_harness.calcs.edit_cycle.change_set_check import CheckInput, change_set_check

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "data" / "golden" / "edit_cycle"
METHOD_REF = r"^§4\.4\.[1-4]\s+\S"
"""A rule of spec 0007 sections 4.4.1 to 4.4.4, such as "§4.4.1 K4"."""
CHECK_KINDS = {
    "change_set": "basis.engineer_input/1",
    "frames": "model.frame_placements/1",
    "areas": "model.area_placements/1",
    "sections": "model.sections/1",
    "restraints": "model.joint_restraints/1",
    "names": "harness.csi_name_lists/1",
    "diff": "harness.model_diff/1",
    "basis": "basis.design_basis/1",
}
"""The record kind of each input field of `harness.change_set_check`."""


class EditCycleGoldenCase(BaseModel):
    """One golden case; no field outside this schema is allowed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1, pattern=r"\S")
    method_ref: str = Field(pattern=METHOD_REF)
    synthetic: Literal[True]
    derivation: str = Field(min_length=1, pattern=r"\S")
    input: dict[str, Any]
    refs: dict[str, str]
    expected: dict[str, Any]


def load_cases(prefix: str) -> dict[str, EditCycleGoldenCase]:
    """The cases of the files `<prefix>-*.json`, by file stem, sorted by name."""
    return {
        path.stem: EditCycleGoldenCase.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(GOLDEN_DIR.glob(f"{prefix}-*.json"))
    }


def input_meta(refs: Mapping[str, str], incomplete: frozenset[str] = frozenset()) -> InputMeta:
    """`InputMeta` for the given result ids; the fields named in `incomplete` come from incomplete records."""
    return InputMeta(
        refs={
            name: RefMeta(
                result_id=parse_ref(result_id)[0],
                ref=result_id,
                kind=CHECK_KINDS[name],
                complete=name not in incomplete,
                model_id=None,
                model_revision=None,
                parents=(),
                producer_tool="fixture_tool",
            )
            for name, result_id in refs.items()
        }
    )


def run_check(
    case: EditCycleGoldenCase,
    *,
    items: list[dict[str, Any]] | None = None,
    trace: TraceBuilder | None = None,
    meta: InputMeta | None = None,
    **changes: Any,
) -> dict[str, Any]:
    """Run `harness.change_set_check` on the case input, with `items` or other input fields replaced."""
    raw = copy.deepcopy(case.input) | changes
    if items is not None:
        raw["change_set"] = {"items": items}
    result = change_set_check(CheckInput.model_validate(raw), meta or input_meta(case.refs), trace or TraceBuilder())
    return result.model_dump(mode="json")
