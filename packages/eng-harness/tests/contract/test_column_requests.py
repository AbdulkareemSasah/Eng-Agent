"""Contract tests of column-workflow request models (plan 0013 T1b; spec 0013 AC3, section 4.3)."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from eng_harness.workflows.column_design import (
    ColumnLayoutRequest,
    ColumnProposalRequest,
    ColumnScopeRequest,
    request_refusal,
)

DATA = Path(__file__).resolve().parents[1] / "data" / "kinds" / "column_design"
_NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
type _RequestModel = type[ColumnScopeRequest] | type[ColumnLayoutRequest] | type[ColumnProposalRequest]


def _load(name: str) -> dict[str, Any]:
    data = json.loads((DATA / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_request_models() -> None:
    """AC3: valid answers parse; unknown fields, low counts and unitless values are refused; the two gaps parse."""
    valids: list[tuple[str, _RequestModel]] = [
        ("requests/scope.valid.json", ColumnScopeRequest),
        ("requests/scope.frames.json", ColumnScopeRequest),
        ("requests/layout.valid.json", ColumnLayoutRequest),
        ("requests/proposal.valid.json", ColumnProposalRequest),
    ]
    for name, request in valids:
        parsed = request.model_validate(_load(name))
        assert request_refusal(parsed) is None
        assert request.model_validate(parsed.model_dump(mode="json")) == parsed
    refused: list[tuple[str, type[BaseModel], str]] = [
        ("requests/scope.unknown.json", ColumnScopeRequest, "Extra inputs"),
        ("requests/scope.count.json", ColumnScopeRequest, "combinations"),
        ("requests/layout.count.json", ColumnLayoutRequest, "n_bars_b"),
        ("requests/layout.unit.json", ColumnLayoutRequest, "unit"),
        ("requests/proposal.count.json", ColumnProposalRequest, "columns"),
        ("requests/proposal.unknown.json", ColumnProposalRequest, "Extra inputs"),
        ("requests/proposal.unit.json", ColumnProposalRequest, "unit"),
    ]
    for name, refused_model, fragment in refused:
        with pytest.raises(ValidationError, match=fragment):
            refused_model.model_validate(_load(name))
    seismic = ColumnScopeRequest.model_validate(_load("requests/scope.seismic.json"))
    spiral = ColumnLayoutRequest.model_validate(_load("requests/layout.spiral.json"))
    assert request_refusal(seismic) == (_NOT_IMPLEMENTED, "CK Q10")
    assert request_refusal(spiral) == (_NOT_IMPLEMENTED, "CK Q4")
