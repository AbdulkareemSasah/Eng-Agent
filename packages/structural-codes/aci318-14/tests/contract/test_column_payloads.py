"""Contract test of the three column checks on one column section (plan 0004 T5; CK-AC4)."""

from pathlib import Path

from eng_contract.canonical import canonical_json
from eng_contract.kinds.verdicts import VerdictSet
from structural_codes import evaluate
from structural_codes.pack import Registry
from structural_codes.verification import CaseFile

from aci318_14 import PACK

_CASES = Path(__file__).parents[1] / "data" / "golden" / "verification"
_COUNTS = {
    "aci318_14.22_4_2_1.max_axial_strength": 1,
    "aci318_14.22_4_1_1.axial_flexure_uniaxial": 1,
    "aci318_14.10_6_1_1.longitudinal_reinforcement_limits": 2,
}


def test_column_checks_payload() -> None:
    """Each column payload validates as verdicts.set/1, is a draft and holds the expected verdict count (CK-AC4)."""
    registry = Registry.of([PACK])
    for check_id, count in _COUNTS.items():
        case = next(c for c in CaseFile.load(_CASES / f"{check_id}.yaml").cases if c.id == "HC-1")
        payload = evaluate(check_id, case.inputs, subject=case.subject, registry=registry).payload
        reloaded = VerdictSet.model_validate_json(canonical_json(payload.model_dump(mode="json")))
        assert reloaded == payload
        assert payload.draft is True
        assert len(payload.verdicts) == count, check_id
