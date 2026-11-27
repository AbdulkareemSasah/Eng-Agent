"""Hand checks of `aci318_14.13_3_1_1.bearing_pressure_service` through `verify_check` (plan 0002 T3; BP-AC1).

The case file is the clause spec's §8 (a protected test oracle). Every hand check and boundary case must pass; the
report must still list the check as not verified: no worked example (G-WE), PC-1 pending (needs a local test with
SAFE), no review block.
"""

from pathlib import Path

from structural_codes.pack import Pack, Registry
from structural_codes.verification import CaseFile, verify_check

from aci318_14 import __version__
from aci318_14.checks.bearing_pressure import bearing_pressure_service

_CASES = Path(__file__).parent.parent / "data" / "golden" / "verification"
_CHECK_ID = "aci318_14.13_3_1_1.bearing_pressure_service"


def test_hand_checks() -> None:
    """HC-1 to HC-3 and BD-1 to BD-5 pass within the §8 tolerances; WE-1 and PC-1 stay unmet (BP-AC1)."""
    pack = Pack("aci318_14", "ACI 318-14", "2014", __version__, (bearing_pressure_service,), "approvals.yaml")
    cases = CaseFile.load(_CASES / f"{_CHECK_ID}.yaml")
    report = verify_check(bearing_pressure_service, cases, registry=Registry.of([pack]))
    outcomes = {r.id: (r.outcome, r.detail) for r in report.cases}
    for case_id in ("HC-1", "HC-2", "HC-3", "BD-1", "BD-2", "BD-3", "BD-4", "BD-5"):
        assert outcomes[case_id] == ("pass", ""), case_id
    assert outcomes["PC-1"] == ("pending", "needs local test")
    assert {c.kind for c in cases.cases if c.id.startswith("HC-")} == {"hand_check"}
    assert not report.verified
    assert report.unmet[0].startswith("(1) no passing worked_example")
    assert report.unmet[1].startswith("(2) program comparisons not passing")
    assert "PC-1" in report.unmet[1]
    assert not any(u.startswith(("(3)", "(6)")) for u in report.unmet)  # every precondition and gap is covered
