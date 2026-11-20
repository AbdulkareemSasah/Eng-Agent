"""Hand checks of the one-way shear check through `verify_check` (plan 0002 T4; clause spec §8, OS-AC1).

The case file `tests/data/golden/verification/aci318_14.22_5_5_1.one_way_shear.yaml` holds HC-1 to HC-3 and the
boundary cases with the spec's absolute tolerances. Every hand check and boundary case passes; the report lists the
worked example (gap G-WE) and the SAFE program comparison (needs local test) as unmet, so the check is not verified.
"""

from pathlib import Path

from structural_codes.pack import Pack, Registry
from structural_codes.verification import CaseFile, verify_check

from aci318_14.checks.one_way_shear import one_way_shear

CASES = Path(__file__).parents[1] / "data" / "golden" / "verification" / "aci318_14.22_5_5_1.one_way_shear.yaml"


def test_hand_checks() -> None:
    """HC-1 to HC-3, BD-1 to BD-4 pass within tolerance; WE-1 and PC-1 stay unmet (OS-AC1)."""
    pack = Pack("aci318_14", "ACI 318-14", "2014", "0.1.0.dev0", checks=(one_way_shear,), approvals="approvals.yaml")
    cases = CaseFile.load(CASES)
    report = verify_check(one_way_shear, cases, registry=Registry.of([pack]))
    outcomes = {r.id: (r.outcome, r.detail) for r in report.cases}
    for case_id in ("HC-1", "HC-2", "HC-3", "BD-1", "BD-2.a", "BD-2.b", "BD-3", "BD-4.a", "BD-4.b"):
        assert outcomes[case_id] == ("pass", ""), case_id
    assert outcomes["PC-1"] == ("pending", "needs local test")
    assert not report.verified
    assert any(u.startswith("(1) no passing worked_example") for u in report.unmet)
    assert any(u.startswith("(2) program comparisons not passing") and "PC-1" in u for u in report.unmet)
    assert not any(u.startswith("(3)") for u in report.unmet), report.unmet
    assert not any(u.startswith("(6)") for u in report.unmet), report.unmet
