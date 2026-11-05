"""Contract test of the six checks on one footing (plan 0002 T9; PK-AC5)."""

from pathlib import Path

from eng_contract.canonical import canonical_json
from eng_contract.kinds.verdicts import VerdictSet
from structural_codes import evaluate
from structural_codes.pack import Registry
from structural_codes.verification import CaseFile

from aci318_14 import PACK

_CASES = Path(__file__).parents[1] / "data" / "golden" / "verification"
_COUNTS = {
    "aci318_14.13_3_1_1.bearing_pressure_service": 1,
    "aci318_14.22_5_5_1.one_way_shear": 2,
    "aci318_14.22_6_5_2.punching_shear": 1,
    "aci318_14.13_2_7_1.flexure_at_column_face": 2,
    "aci318_14.8_6_1_1.min_flexural_reinforcement": 2,
    "aci318_14.25_4_2_3.development_length_bottom_bars": 2,
}


def test_all_checks_payload() -> None:
    """Each check's payload validates as verdicts.set/1, is a draft and holds the expected verdict count (PK-AC5)."""
    registry = Registry.of([PACK])
    for check_id, count in _COUNTS.items():
        case = next(c for c in CaseFile.load(_CASES / f"{check_id}.yaml").cases if c.id == "HC-1")
        payload = evaluate(check_id, case.inputs, subject=case.subject, registry=registry).payload
        reloaded = VerdictSet.model_validate_json(canonical_json(payload.model_dump(mode="json")))
        assert reloaded == payload
        assert payload.draft is True
        assert len(payload.verdicts) == count, check_id
