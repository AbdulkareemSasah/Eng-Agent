"""Hand checks of the development length check through `verify_check` (plan 0002 T8; clause spec §8, DL-AC1).

The case file `tests/data/golden/verification/aci318_14.25_4_2_3.development_length_bottom_bars.yaml` holds HC-1 to
HC-4 and the boundary cases with the spec's absolute tolerances. Every hand check and boundary case passes; the report
lists the worked example (gap G-WE) as unmet, so the check is not verified. No program comparison applies: the case
file states `program_comparison.not_available` (plan §6 Q11), so requirement (2) is met.
"""

from pathlib import Path

from structural_codes.pack import Pack, Registry
from structural_codes.verification import CaseFile, verify_check

from aci318_14.checks.development_length import development_length_bottom_bars

CASES = (
    Path(__file__).parents[1]
    / "data"
    / "golden"
    / "verification"
    / "aci318_14.25_4_2_3.development_length_bottom_bars.yaml"
)
_IDS = ("HC-1", "HC-2", "HC-3", "HC-4", "BD-1", "BD-2.a", "BD-2.b", "BD-2.c", "BD-3.a", "BD-3.b", "BD-3.c", "BD-3.d")


def test_hand_checks() -> None:
    """HC-1 to HC-4 and BD-1 to BD-3 pass within tolerance; WE-1 stays unmet (DL-AC1)."""
    check = development_length_bottom_bars
    pack = Pack("aci318_14", "ACI 318-14", "2014", "0.1.0.dev0", checks=(check,), approvals="approvals.yaml")
    cases = CaseFile.load(CASES)
    report = verify_check(check, cases, registry=Registry.of([pack]))
    outcomes = {r.id: (r.outcome, r.detail) for r in report.cases}
    for case_id in _IDS:
        assert outcomes[case_id] == ("pass", ""), case_id
    assert cases.program_comparison is not None
    assert not report.verified
    assert any(u.startswith("(1) no passing worked_example") for u in report.unmet)
    for number in ("(2)", "(3)", "(6)"):
        assert not any(u.startswith(number) for u in report.unmet), report.unmet
