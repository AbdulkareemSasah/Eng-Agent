"""Hand checks of the maximum axial strength check through `verify_check` (plan 0004 T2; clause spec §8, MA-AC1).

The case file `tests/data/golden/verification/aci318_14.22_4_2_1.max_axial_strength.yaml` holds HC-1 to HC-3 and the
boundary cases with the spec's absolute tolerances. Every hand check and boundary case passes; the report lists the
worked example (gap G-WE) and the ETABS program comparison (needs local test) as unmet, so the check is not verified.
"""

from pathlib import Path

from structural_codes.pack import Pack, Registry
from structural_codes.verification import CaseFile, verify_check

from aci318_14.checks.max_axial import max_axial_strength

CASES = Path(__file__).parents[1] / "data" / "golden" / "verification" / "aci318_14.22_4_2_1.max_axial_strength.yaml"
CASE_IDS = (
    "HC-1",
    "HC-2",
    "HC-3",
    "HC-4",
    "BD-1.a",
    "BD-1.b",
    "BD-1.c",
    "BD-1.d",
    "BD-2.a",
    "BD-2.b",
    "BD-2.c",
    "BD-3.a",
    "BD-3.b",
    "BD-3.c",
)


def test_hand_checks() -> None:
    """HC-1 to HC-4, BD-1 to BD-3 pass within tolerance; WE-1 and PC-1 stay unmet (MA-AC1)."""
    pack = Pack(
        "aci318_14", "ACI 318-14", "2014", "0.1.0.dev0", checks=(max_axial_strength,), approvals="approvals.yaml"
    )
    report = verify_check(max_axial_strength, CaseFile.load(CASES), registry=Registry.of([pack]))
    outcomes = {r.id: (r.outcome, r.detail) for r in report.cases}
    for case_id in CASE_IDS:
        assert outcomes[case_id] == ("pass", ""), case_id
    assert outcomes["PC-1"] == ("pending", "needs local test")
    assert not report.verified
    assert any(u.startswith("(1) no passing worked_example") for u in report.unmet)
    assert any(u.startswith("(2) program comparisons not passing") and "PC-1" in u for u in report.unmet)
    assert not any(u.startswith("(3)") for u in report.unmet), report.unmet
    assert not any(u.startswith("(6)") for u in report.unmet), report.unmet
