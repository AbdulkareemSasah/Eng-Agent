"""Contract tests of the column-workflow kinds and requests (plan 0013 T1; spec 0013 AC3, sections 4.2 and 4.3)."""

import json
from pathlib import Path
from typing import Any

import pytest
from eng_harness.kinds.column_design import COLUMN_DESIGN_KINDS as KIND_MODELS
from eng_harness.workflows.column_design import (
    ColumnLayoutRequest,
    ColumnProposalRequest,
    ColumnScopeRequest,
    request_refusal,
)
from pydantic import BaseModel, ValidationError

from eng_harness.kinds import COLUMN_DESIGN_KINDS

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
_NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


def _load(name: str) -> dict[str, Any]:
    data = json.loads((DATA / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_request_models() -> None:
    """AC3: valid answers parse; unknown fields, low counts and unitless values are refused; the two gaps parse."""
    valids = [
        ("requests/scope.valid.json", ColumnScopeRequest),
        ("requests/scope.frames.json", ColumnScopeRequest),
        ("requests/layout.valid.json", ColumnLayoutRequest),
        ("requests/proposal.valid.json", ColumnProposalRequest),
    ]
    for name, model in valids:
        parsed = model.model_validate(_load(name))
        assert request_refusal(parsed) is None
        assert model.model_validate(parsed.model_dump(mode="json")) == parsed
    refused: list[tuple[str, type[BaseModel], str]] = [
        ("requests/scope.unknown.json", ColumnScopeRequest, "Extra inputs"),
        ("requests/scope.count.json", ColumnScopeRequest, "combinations"),
        ("requests/layout.count.json", ColumnLayoutRequest, "n_bars_b"),
        ("requests/layout.unit.json", ColumnLayoutRequest, "unit"),
        ("requests/proposal.count.json", ColumnProposalRequest, "columns"),
        ("requests/proposal.unknown.json", ColumnProposalRequest, "Extra inputs"),
        ("requests/proposal.unit.json", ColumnProposalRequest, "unit"),
    ]
    for name, model, fragment in refused:
        with pytest.raises(ValidationError, match=fragment):
            model.model_validate(_load(name))
    seismic = ColumnScopeRequest.model_validate(_load("requests/scope.seismic.json"))
    spiral = ColumnLayoutRequest.model_validate(_load("requests/layout.spiral.json"))
    assert request_refusal(seismic) == (_NOT_IMPLEMENTED, "CK Q10")
    assert request_refusal(spiral) == (_NOT_IMPLEMENTED, "CK Q4")


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
