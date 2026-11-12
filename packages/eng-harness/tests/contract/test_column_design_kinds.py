"""Contract tests of the column-workflow kinds (plan 0013 T1; spec 0013 AC3, section 4.2)."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from eng_harness.kinds import COLUMN_DESIGN_KINDS
from eng_harness.kinds.column_design import COLUMN_DESIGN_KINDS as KIND_MODELS

DATA = Path(__file__).resolve().parents[1] / "data" / "kinds" / "column_design"
KINDS = {
    "column_selection": "harness.column_selection/1",
    "column_check_items": "harness.column_check_items/1",
    "column_review": "harness.column_review/1",
    "column_match": "harness.column_match/1",
    "generated_change_set": "harness.generated_change_set/1",
    "revit_column_update": "harness.revit_column_update/1",
    "revit_column_readback": "harness.revit_column_readback/1",
    "column_design_record": "harness.column_design_record/1",
}


def _load(name: str) -> dict[str, Any]:
    data = json.loads((DATA / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_kind_fixtures() -> None:
    """AC3: each kind of section 4.2 has one valid fixture and one invalid fixture, and is registered on the package."""
    assert COLUMN_DESIGN_KINDS is KIND_MODELS
    assert set(COLUMN_DESIGN_KINDS) == set(KINDS.values())
    assert all(name.startswith("harness.") for name in COLUMN_DESIGN_KINDS)
    for stem, kind in KINDS.items():
        model = COLUMN_DESIGN_KINDS[kind]
        payload = _load(f"{stem}.json")
        parsed = model.model_validate(payload)
        assert model.model_validate(parsed.model_dump(mode="json", exclude_none=False)) == parsed
        with pytest.raises(ValidationError, match="Extra inputs"):
            model.model_validate({**payload, "unknown_field": 1})
        with pytest.raises(ValidationError):
            model.model_validate(_load(f"{stem}.invalid.json"))
