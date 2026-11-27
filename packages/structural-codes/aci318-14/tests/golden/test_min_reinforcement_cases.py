"""Hand checks of the minimum flexural reinforcement check through `verify_check` (plan 0002 T7; spec §8, MR-AC1).

The case file `tests/data/golden/verification/aci318_14.8_6_1_1.min_flexural_reinforcement.yaml` holds HC-1 to HC-4
and the boundary cases with the spec's absolute tolerances (1e-6 mm2, 1e-9 on ratios). Every hand check and boundary
case passes; the report lists the worked example (gap G-WE) and the SAFE program comparison (needs local test) as
unmet, so the check is not verified.
"""

from pathlib import Path

from structural_codes.pack import Pack, Registry
from structural_codes.verification import CaseFile, verify_check

from aci318_14.checks.min_reinforcement import min_flexural_reinforcement

CASES = Path(__file__).parents[1] / "data" / "golden" / "verification"
CASE_FILE = CASES / "aci318_14.8_6_1_1.min_flexural_reinforcement.yaml"


def test_hand_checks() -> None:
    """HC-1 to HC-4, BD-1 and BD-2 pass within tolerance; WE-1 and PC-1 stay unmet (MR-AC1)."""
    pack = Pack(
        "aci318_14",
        "ACI 318-14",
        "2014",
        "0.1.0.dev0",
        checks=(min_flexural_reinforcement,),
        approvals="approvals.yaml",
    )
    cases = CaseFile.load(CASE_FILE)
    report = verify_check(min_flexural_reinforcement, cases, registry=Registry.of([pack]))
    outcomes = {r.id: (r.outcome, r.detail) for r in report.cases}
    for case_id in ("HC-1", "HC-2", "HC-3", "HC-4", "BD-1.a", "BD-1.b", "BD-2"):
        assert outcomes[case_id] == ("pass", ""), case_id
    assert outcomes["PC-1"] == ("pending", "needs local test")
    assert not report.verified
    assert any(u.startswith("(1) no passing worked_example") for u in report.unmet)
    assert any(u.startswith("(2) program comparisons not passing") and "PC-1" in u for u in report.unmet)
    assert not any(u.startswith("(3)") for u in report.unmet), report.unmet
    assert not any(u.startswith("(6)") for u in report.unmet), report.unmet
