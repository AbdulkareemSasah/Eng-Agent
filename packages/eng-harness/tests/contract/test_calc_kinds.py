"""Contract tests of the calc kinds (plan 0003 T4; spec 0003 AC47, §4.6 to §4.11)."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from eng_contract.kinds import NEUTRAL_KINDS
from eng_contract.params import ContractDefinitionError
from pydantic import ValidationError

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.kinds.calcs import CALC_KINDS, ModelDiff

DATA = Path(__file__).resolve().parents[1] / "data" / "kinds" / "calcs"
KINDS = {
    "model_fingerprint": "harness.model_fingerprint/1",
    "model_diff": "harness.model_diff/1",
    "expected_effects": "harness.expected_effects/1",
    "readback_check": "harness.readback_check/1",
    "design_summary": "harness.design_summary/1",
    "section_size": "harness.section_size/1",
    "placement_comparison": "harness.placement_comparison/1",
}
Mutation = Callable[[dict[str, Any]], None]


def _load(stem: str) -> dict[str, Any]:
    data = json.loads((DATA / f"{stem}.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _unsort_members(p: dict[str, Any]) -> None:
    p["members"].reverse()


def _fp_covered(p: dict[str, Any]) -> None:
    p["covered"] = ["model.stories/1"]


def _fp_reverse(p: dict[str, Any]) -> None:
    p["sections"].reverse()
    p["covered"].reverse()


def _fp_form(p: dict[str, Any]) -> None:
    p["fingerprint"] = "fp1:" + "D" * 64


def _fp_short(p: dict[str, Any]) -> None:
    p["fingerprint"] = "fp1:abc"


def _diff_counts(p: dict[str, Any]) -> None:
    p["counts"]["model.frame_placements/1"]["removed"] = 0


def _diff_unsorted(p: dict[str, Any]) -> None:
    p["changes"].reverse()


def _diff_identical(p: dict[str, Any]) -> None:
    p["identical"] = True


def _fx_no_pointer(p: dict[str, Any]) -> None:
    p["effects"][0]["pointer"] = None


def _fx_duplicate(p: dict[str, Any]) -> None:
    p["effects"][1]["item_id"] = "i1"


def _fx_section(p: dict[str, Any]) -> None:
    p["effects"][0]["section"] = "verdicts.set/1"


def _fx_remove_value(p: dict[str, Any]) -> None:
    p["effects"][2]["value"] = 1


def _rb_status(p: dict[str, Any]) -> None:
    p["status"] = "PASS"


def _rb_trace(p: dict[str, Any]) -> None:
    p["trace"]["calc_id"] = "harness.other"


def _sum_label(p: dict[str, Any]) -> None:
    p["top"]["label"] = "top 2 by ratio"


def _sum_counts(p: dict[str, Any]) -> None:
    p["counts"]["FAIL"] = 0


def _sum_newly(p: dict[str, Any]) -> None:
    p["changes"]["newly_failing"][0]["previous_status"] = "FAIL"


def _sum_status(p: dict[str, Any]) -> None:
    p["status"] = "PASS"


def _size_unit(p: dict[str, Any]) -> None:
    p["size"] = {"value": 0.45, "unit": "m"}


def _size_multiple(p: dict[str, Any]) -> None:
    p["multiple"] = 0


def _pl_difference(p: dict[str, Any]) -> None:
    p["counts"][0]["difference"] = 5


def _pl_equal(p: dict[str, Any]) -> None:
    p["equal"] = True


def _pl_type(p: dict[str, Any]) -> None:
    p["counts"][2]["name"] = "slab"


INVALID: list[tuple[str, Mutation, str]] = [
    ("model_fingerprint", _fp_form, "fp1"),
    ("model_fingerprint", _fp_short, "fp1"),
    ("model_fingerprint", _fp_reverse, "sorted"),
    ("model_fingerprint", _fp_covered, "covered"),
    ("model_diff", _diff_counts, "counts"),
    ("model_diff", _diff_unsorted, "sorted"),
    ("model_diff", _diff_identical, "identical"),
    ("expected_effects", _fx_no_pointer, "pointer"),
    ("expected_effects", _fx_duplicate, "duplicate"),
    ("expected_effects", _fx_section, "section"),
    ("expected_effects", _fx_remove_value, "remove"),
    ("readback_check", _rb_status, "status"),
    ("readback_check", _rb_trace, "calc_id"),
    ("design_summary", _sum_label, "label"),
    ("design_summary", _sum_counts, "counts"),
    ("design_summary", _unsort_members, "sorted"),
    ("design_summary", _sum_newly, "newly_failing"),
    ("design_summary", _sum_status, "status"),
    ("section_size", _size_unit, "mm"),
    ("section_size", _size_multiple, "greater than or equal to 1"),
    ("placement_comparison", _pl_difference, "difference"),
    ("placement_comparison", _pl_equal, "equal"),
    ("placement_comparison", _pl_type, "type"),
]


def test_fixtures() -> None:
    """AC47: every valid fixture passes through its registered kind, every invalid one fails on its rule."""
    for stem, kind in KINDS.items():
        model = HARNESS_KINDS[kind]
        payload = _load(stem)
        assert model.model_validate(payload).model_dump(mode="json", exclude_none=False) is not None
        with pytest.raises(ValidationError, match="Extra inputs"):
            model.model_validate({**payload, "unknown_field": 1})
    for stem, mutate, fragment in INVALID:
        payload = copy.deepcopy(_load(stem))
        mutate(payload)
        with pytest.raises(ValidationError, match=fragment):
            HARNESS_KINDS[KINDS[stem]].model_validate(payload)


def test_calc_kinds_are_harness_family_and_extend_the_registry() -> None:
    """The calc kinds sit in the harness family beside the neutral and engine kinds."""
    assert set(CALC_KINDS) == set(KINDS.values())
    assert all(name.startswith("harness.") for name in CALC_KINDS)
    for name, model in CALC_KINDS.items():
        assert HARNESS_KINDS[name] is model
    assert "harness.journal_blob/1" in HARNESS_KINDS
    assert "model.stories/1" in HARNESS_KINDS


def test_neutral_family_refused() -> None:
    """AC47: a calc kind in a neutral family is refused by the contract."""
    with pytest.raises(ContractDefinitionError):
        NEUTRAL_KINDS.extend({"model.model_diff/1": ModelDiff})
