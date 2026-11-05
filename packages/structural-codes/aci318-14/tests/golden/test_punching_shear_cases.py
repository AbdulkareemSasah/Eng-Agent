"""Hand checks of the punching shear check through `verify_check` (plan 0002 T5; clause spec §8, PS-AC1).

The case file `tests/data/golden/verification/aci318_14.22_6_5_2.punching_shear.yaml` holds HC-1 to HC-3 and the
boundary cases with the spec's absolute tolerances. Every hand check and boundary case passes; the report lists the
worked example (gap G-WE) and the SAFE program comparison (needs local test) as unmet, so the check is not verified.
The trace note of each hand check names the governing expression of Table 22.6.5.2: (a), (b), (c) in turn.
"""

from pathlib import Path

from eng_contract.verdicts import Subject, SubjectKind
from structural_codes import evaluate
from structural_codes.pack import Pack, Registry
from structural_codes.verification import CaseFile, verify_check

from aci318_14.checks.punching_shear import punching_shear

CASES = Path(__file__).parents[1] / "data" / "golden" / "verification" / "aci318_14.22_6_5_2.punching_shear.yaml"
CASE_IDS = ("HC-1", "HC-2", "HC-3", "BD-1.a", "BD-1.b", "BD-2.a", "BD-2.b")
CASE_IDS += ("BD-3.a", "BD-3.b", "BD-3.c", "BD-3.d", "BD-3.e")


def test_hand_checks() -> None:
    """HC-1 to HC-3 and BD-1 to BD-3 pass within tolerance; WE-1 and PC-1 stay unmet; notes name (a), (b), (c)."""
    pack = Pack("aci318_14", "ACI 318-14", "2014", "0.1.0.dev0", checks=(punching_shear,), approvals="approvals.yaml")
    registry = Registry.of([pack])
    cases = CaseFile.load(CASES)
    report = verify_check(punching_shear, cases, registry=registry)
    outcomes = {r.id: (r.outcome, r.detail) for r in report.cases}
    for case_id in CASE_IDS:
        assert outcomes[case_id] == ("pass", ""), case_id
    assert outcomes["PC-1"] == ("pending", "needs local test")
    assert not report.verified
    assert any(u.startswith("(1) no passing worked_example") for u in report.unmet)
    assert any(u.startswith("(2) program comparisons not passing") and "PC-1" in u for u in report.unmet)
    assert not any(u.startswith("(3)") for u in report.unmet), report.unmet
    assert not any(u.startswith("(6)") for u in report.unmet), report.unmet
    by_id = {c.id: c for c in cases.cases}
    footing = Subject(kind=SubjectKind.FOOTING, id="F1")
    for case_id, expression in (("HC-1", "(a)"), ("HC-2", "(b)"), ("HC-3", "(c)")):
        trace = evaluate(punching_shear.meta.check_id, by_id[case_id].inputs, subject=footing, registry=registry)
        notes = trace.payload.traces[0].messages
        assert [m for m in notes if m.startswith("governing: Table 22.6.5.2 ")] == [
            f"governing: Table 22.6.5.2 {expression}"
        ], case_id
