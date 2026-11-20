"""Hand-derived IDEA check-row mapping cases (plan 0014 T5; spec 0014 AC13, section 4.5)."""

from typing import Any

import pytest
from eng_contract.verdicts import VerdictStatus

from eng_harness.adapters.idea import _verdicts as idea_verdicts

# Hand-derived from AC13: check_value (host percent), check_status, skipped → status and ratio.
_CASES: list[tuple[dict[str, Any], VerdictStatus, float | None]] = [
    ({"name": "Plates", "check_value": 87.5, "check_status": True, "skipped": False}, VerdictStatus.PASS, 0.875),
    ({"name": "Bolts", "check_value": 103.0, "check_status": True, "skipped": False}, VerdictStatus.NEEDS_ENGINEER, 1.03),
    ({"name": "Welds", "check_value": 80.0, "check_status": False, "skipped": False}, VerdictStatus.NEEDS_ENGINEER, 0.8),
    ({"name": "Buckling", "check_value": 0.0, "check_status": True, "skipped": False}, VerdictStatus.NEEDS_ENGINEER, 0.0),
    ({"name": "Concrete", "check_value": 112.0, "check_status": False, "skipped": False}, VerdictStatus.FAIL, 1.12),
    ({"name": "Skipped", "check_value": 50.0, "check_status": True, "skipped": True}, VerdictStatus.NOT_APPLICABLE, 0.5),
]


@pytest.mark.parametrize(("check", "status", "ratio"), _CASES, ids=[c[0]["name"] for c in _CASES])
def test_mapping_cases(check: dict[str, Any], status: VerdictStatus, ratio: float | None) -> None:
    """AC13: host status wins when consistent with ratio_limit 1.0; disagreements and zero/true go to the engineer."""
    verdict = idea_verdicts.map_check(
        check,
        connection_name="CON1",
        design_code="AISC",
        route="native",
    )
    assert verdict.source.value == "host"
    assert verdict.status is status
    assert verdict.ratio == ratio
    assert verdict.ratio_limit == 1.0
    assert verdict.code == "AISC"
    assert verdict.clause is None
    assert verdict.subject.kind.value == "joint"
    assert verdict.subject.id == "CON1"
    assert verdict.check_id.startswith("idea:")
    assert "host-native check of IDEA StatiCa; not merged with code-pack verdicts" in verdict.assumptions
    if check["check_value"] == 0.0 and check["check_status"] is True and not check["skipped"]:
        assert any("utilization is exactly zero" in a for a in verdict.assumptions)
