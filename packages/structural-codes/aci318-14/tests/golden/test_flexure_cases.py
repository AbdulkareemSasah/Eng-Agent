"""Hand checks of the flexure check through `verify_check` (plan 0002 T6; clause spec §8, FL-AC1).

The case file `tests/data/golden/verification/aci318_14.13_2_7_1.flexure_at_column_face.yaml` holds HC-1 to HC-3 and
the boundary cases with the spec's absolute tolerances. Every hand check and boundary case passes; the report lists the
worked example (gap G-WE) and the SAFE program comparison (needs local test) as unmet, so the check is not verified.
"""

from pathlib import Path

from structural_codes.pack import Pack, Registry
from structural_codes.verification import CaseFile, verify_check

from aci318_14.checks.flexure import flexure_at_column_face

NAME = "aci318_14.13_2_7_1.flexure_at_column_face.yaml"
CASES = Path(__file__).parents[1] / "data" / "golden" / "verification" / NAME
CASE_IDS = (
    "HC-1",
    "HC-2",
    "HC-3",
    "BD-1.a",
    "BD-1.b",
    "BD-2",
    "BD-2.b",
    "BD-2.c",
    "BD-2.d",
    "BD-3.a",
    "BD-3.b",
    "BD-3.c",
    "BD-4.a",
    "BD-4.b",
)


def test_hand_checks() -> None:
    """HC-1 to HC-3, BD-1 to BD-4 pass within tolerance; WE-1 and PC-1 stay unmet (FL-AC1)."""
    pack = Pack(
        "aci318_14", "ACI 318-14", "2014", "0.1.0.dev0", checks=(flexure_at_column_face,), approvals="approvals.yaml"
    )
    report = verify_check(flexure_at_column_face, CaseFile.load(CASES), registry=Registry.of([pack]))
    outcomes = {r.id: (r.outcome, r.detail) for r in report.cases}
    for case_id in CASE_IDS:
        assert outcomes[case_id] == ("pass", ""), case_id
    assert outcomes["PC-1"] == ("pending", "needs local test")
    assert not report.verified
    assert any(u.startswith("(1) no passing worked_example") for u in report.unmet)
    assert any(u.startswith("(2) program comparisons not passing") and "PC-1" in u for u in report.unmet)
    assert not any(u.startswith("(3)") for u in report.unmet), report.unmet
    assert not any(u.startswith("(6)") for u in report.unmet), report.unmet
