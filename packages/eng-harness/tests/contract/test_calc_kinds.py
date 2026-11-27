"""Contract tests of the calc kinds (plan 0003 T4 and T4b; spec 0003 AC47, §4.6 to §4.11)."""

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
}
REPORT_KINDS = {
    "readback_check": "harness.readback_check/1",
    "design_summary": "harness.design_summary/1",
    "section_size": "harness.section_size/1",
    "placement_comparison": "harness.placement_comparison/1",
    "frame_element_map": "harness.frame_element_map/1",
}
Mutation = Callable[[dict[str, Any]], None]


def _load(stem: str) -> dict[str, Any]:
    data = json.loads((DATA / f"{stem}.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


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


def _fp_trace(p: dict[str, Any]) -> None:
    p["trace"]["calc_version"] = "2"


def _fp_sha(p: dict[str, Any]) -> None:
    p["calc"]["content_sha256"] = "1" * 64


def _fp_complete(p: dict[str, Any]) -> None:
    p["sections"][0]["complete"] = False
    p["complete"] = True


def _fp_model_id(p: dict[str, Any]) -> None:
    p["model_id"] = "not-a-model-id"


def _diff_changed_empty(p: dict[str, Any]) -> None:
    row = next(c for c in p["changes"] if c["change"] == "changed")
    row["properties"] = []


def _diff_removed_props(p: dict[str, Any]) -> None:
    row = next(c for c in p["changes"] if c["change"] == "changed")
    row["change"] = "removed"


def _fx_add_pointer(p: dict[str, Any]) -> None:
    p["effects"][1]["pointer"] = "/x"


def _fx_add_scalar(p: dict[str, Any]) -> None:
    p["effects"][1]["value"] = 3


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
    ("model_fingerprint", _fp_trace, "those of calc"),
    ("model_fingerprint", _fp_sha, "those of calc"),
    ("model_fingerprint", _fp_complete, "conjunction"),
    ("model_fingerprint", _fp_model_id, "model_id"),
    ("model_diff", _diff_changed_empty, "exactly for a changed"),
    ("model_diff", _diff_removed_props, "exactly for a changed"),
    ("expected_effects", _fx_add_pointer, "add needs"),
    ("expected_effects", _fx_add_scalar, "add needs"),
]


def test_fixtures() -> None:
    """AC47: every valid fixture passes through its registered kind, every invalid one fails on its rule."""
    for stem, kind in KINDS.items():
        model = HARNESS_KINDS[kind]
        payload = _load(stem)
        parsed = model.model_validate(payload)
        # The result store validates, then stores model_dump(mode="json", exclude_none=False); it must reload.
        assert model.model_validate(parsed.model_dump(mode="json", exclude_none=False)) == parsed
        with pytest.raises(ValidationError, match="Extra inputs"):
            model.model_validate({**payload, "unknown_field": 1})
    for stem, mutate, fragment in INVALID:
        payload = copy.deepcopy(_load(stem))
        mutate(payload)
        with pytest.raises(ValidationError, match=fragment):
            HARNESS_KINDS[KINDS[stem]].model_validate(payload)


def _unsort_members(p: dict[str, Any]) -> None:
    p["members"].reverse()


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


def _rb_clean(p: dict[str, Any]) -> None:
    p["items"] = p["items"][:1]
    p["unexpected"] = []
    p["status"] = "PASS"


def _rb_not_read(p: dict[str, Any]) -> None:
    _rb_clean(p)
    p["items"][0]["result"] = "not_read"


def _rb_incomplete(p: dict[str, Any]) -> None:
    _rb_clean(p)
    p["complete"] = False


def _rb_needs(p: dict[str, Any]) -> None:
    _rb_clean(p)
    p["status"] = "NEEDS_ENGINEER"


def _rb_not_read_needs(p: dict[str, Any]) -> None:
    _rb_not_read(p)
    p["status"] = "NEEDS_ENGINEER"


def _rb_incomplete_needs(p: dict[str, Any]) -> None:
    _rb_incomplete(p)
    p["status"] = "NEEDS_ENGINEER"


def _sum_only_pass(p: dict[str, Any]) -> None:
    """Drop the failing verdict: one PASS verdict is left and the status is PASS."""
    p["counts"]["FAIL"] = 0
    p["failing"] = []
    p["failing_members"] = []
    p["governing_by_group"] = []
    p["governing"] = None
    p["members"] = p["members"][1:]
    p["top"] = {"n": 1, "of_total": 1, "label": "top 1 of 1 by ratio", "rows": p["top"]["rows"][1:]}
    p["changes"]["newly_failing"] = []
    p["status"] = "PASS"


def _sum_not_designed(p: dict[str, Any]) -> None:
    _sum_only_pass(p)
    p["not_designed"] = ["F9"]


def _sum_incomplete(p: dict[str, Any]) -> None:
    _sum_only_pass(p)
    p["complete"] = False


def _sum_empty(p: dict[str, Any]) -> None:
    _sum_only_pass(p)
    p["counts"]["PASS"] = 0
    p["members"] = []
    p["top"] = {"n": 0, "of_total": 0, "label": "top 0 of 0 by ratio", "rows": []}
    p["changes"]["appeared"] = []


def _sum_needs(p: dict[str, Any]) -> None:
    _sum_only_pass(p)
    p["status"] = "NEEDS_ENGINEER"


def _sum_not_designed_needs(p: dict[str, Any]) -> None:
    _sum_not_designed(p)
    p["status"] = "NEEDS_ENGINEER"


def _sum_incomplete_needs(p: dict[str, Any]) -> None:
    _sum_incomplete(p)
    p["status"] = "NEEDS_ENGINEER"


def _sum_empty_needs(p: dict[str, Any]) -> None:
    _sum_empty(p)
    p["status"] = "NEEDS_ENGINEER"


def _sum_attention(p: dict[str, Any]) -> None:
    _sum_only_pass(p)
    row = dict(p["top"]["rows"][0], status="NEEDS_ENGINEER", ratio=None, subject_id="F3")
    p["attention"] = [row]
    p["counts"]["NEEDS_ENGINEER"] = 1
    p["top"] = {"n": 1, "of_total": 2, "label": "top 1 of 2 by ratio", "rows": p["top"]["rows"]}
    p["status"] = "NEEDS_ENGINEER"


def _sum_attention_pass(p: dict[str, Any]) -> None:
    _sum_attention(p)
    p["status"] = "PASS"


def _sum_two_failing(p: dict[str, Any], order: tuple[int, int]) -> None:
    row = p["failing"][0]
    other = dict(row, subject_id="F5", ratio=1.1)
    p["failing"] = [[row, other][i] for i in order]
    p["counts"]["FAIL"] = 2
    p["counts"]["PASS"] = 1
    p["top"]["of_total"] = 3
    p["top"]["label"] = "top 2 of 3 by ratio"
    p["members"] = sorted(
        [*p["members"], {**p["members"][0], "subject_id": "F5", "ratio": 1.1}],
        key=lambda m: m["subject_id"],
    )


def _sum_failing_sorted(p: dict[str, Any]) -> None:
    _sum_two_failing(p, (0, 1))


def _sum_failing_unsorted(p: dict[str, Any]) -> None:
    _sum_two_failing(p, (1, 0))


def _sum_top_n(p: dict[str, Any]) -> None:
    p["top"]["n"] = 1


def _sum_of_total(p: dict[str, Any]) -> None:
    p["top"]["of_total"] = 3
    p["top"]["label"] = "top 2 of 3 by ratio"


def _sum_kind(p: dict[str, Any]) -> None:
    p["governing"]["subject_kind"] = "bogus"


def _sum_check_id(p: dict[str, Any]) -> None:
    p["governing"]["check_id"] = "Bad Id"


def _sum_fail_below_limit(p: dict[str, Any]) -> None:
    p["governing"]["ratio"] = 0.8


def _sum_group_kind(p: dict[str, Any]) -> None:
    p["governing_by_group"][0]["row"]["subject_kind"] = "area"


def _sum_group_check(p: dict[str, Any]) -> None:
    p["governing_by_group"][0]["row"]["check_id"] = "host.csi.other"


def _sum_group_twice(p: dict[str, Any]) -> None:
    p["governing_by_group"].append(copy.deepcopy(p["governing_by_group"][0]))


def _size_valid(p: dict[str, Any]) -> None:
    p["required"]["value"] = 450.0


def _size_nondyadic(p: dict[str, Any]) -> None:
    # N1/N2: required 0.25, increment 0.1, n = 3, size = float(3 x 0.1) = 0.30000000000000004
    p["required"]["value"] = 0.25
    p["increment"]["value"] = 0.1
    p["multiple"] = 3
    p["size"]["value"] = 0.30000000000000004


def _size_nondyadic_wrong(p: dict[str, Any]) -> None:
    _size_nondyadic(p)
    p["size"]["value"] = 0.3


def _sum_ratio_none(p: dict[str, Any]) -> None:
    p["failing"][0]["ratio"] = None


def _sum_counts_missing(p: dict[str, Any]) -> None:
    del p["counts"]["ERROR"]


def _size_below(p: dict[str, Any]) -> None:
    p["size"]["value"] = 400.0
    p["multiple"] = 8


def _size_too_big(p: dict[str, Any]) -> None:
    p["size"]["value"] = 500.0
    p["multiple"] = 10


def _size_not_multiple(p: dict[str, Any]) -> None:
    p["multiple"] = 8


def _pl_difference(p: dict[str, Any]) -> None:
    p["counts"][0]["difference"] = 5


def _pl_equal(p: dict[str, Any]) -> None:
    p["equal"] = True


def _pl_type(p: dict[str, Any]) -> None:
    # Only the type rule fails: the renamed row keeps its place in the sort order and its difference.
    p["counts"][2]["name"] = "slab"
    p["counts"][2]["element"] = "frame"


def _fem_pairs_unsorted(p: dict[str, Any]) -> None:
    p["pairs"].append(
        {
            "frame_id": "F0",
            "unique_id": "U0",
            "element_id": 1,
            "type_id": 2,
            "basis": "geometry",
            "lower_distance_mm": 0.0,
            "upper_distance_mm": 0.0,
        }
    )


def _fem_candidates_unsorted(p: dict[str, Any]) -> None:
    p["ambiguous"][0]["candidates"] = ["U3", "U2"]


REPORT_INVALID: list[tuple[str, Mutation, str]] = [
    ("readback_check", _rb_status, "by rule R4"),
    ("readback_check", _rb_not_read, "must be NEEDS_ENGINEER by rule R4"),
    ("readback_check", _rb_incomplete, "must be NEEDS_ENGINEER by rule R4"),
    ("readback_check", _rb_needs, "must be PASS by rule R4"),
    ("readback_check", _rb_trace, "trace calc_id"),
    ("design_summary", _sum_label, "label must state"),
    ("design_summary", _sum_counts, "counts must match failing and attention"),
    ("design_summary", _unsort_members, "members must be sorted and unique"),
    ("design_summary", _sum_newly, "of newly_failing does not fit"),
    ("design_summary", _sum_status, "by rule S6"),
    ("design_summary", _sum_needs, "must be PASS by rule S6"),
    ("design_summary", _sum_not_designed, "must be NEEDS_ENGINEER by rule S6"),
    ("design_summary", _sum_incomplete, "must be NEEDS_ENGINEER by rule S6"),
    ("design_summary", _sum_empty, "must be NEEDS_ENGINEER by rule S6"),
    ("design_summary", _sum_attention_pass, "must be NEEDS_ENGINEER by rule S6"),
    ("design_summary", _sum_failing_unsorted, "failing must be sorted by ratio"),
    ("design_summary", _sum_top_n, "n must be the number of rows"),
    ("design_summary", _sum_of_total, "counts must add up to top.of_total"),
    ("design_summary", _sum_kind, "Input should be 'joint'"),
    ("design_summary", _sum_check_id, "String should match pattern"),
    ("design_summary", _sum_fail_below_limit, "contradicts ratio"),
    ("design_summary", _sum_group_kind, "does not match its group"),
    ("design_summary", _sum_group_check, "does not match its group"),
    ("design_summary", _sum_group_twice, "governing_by_group must be sorted and unique"),
    ("design_summary", _sum_ratio_none, "requires a ratio"),
    ("design_summary", _sum_counts_missing, "counts needs one entry per status"),
    ("section_size", _size_nondyadic_wrong, "size must be multiple times increment"),
    ("section_size", _size_unit, "must be in mm"),
    ("section_size", _size_multiple, "greater than or equal to 1"),
    ("section_size", _size_below, "size must be at least required"),
    ("section_size", _size_too_big, "size must be less than required plus increment"),
    ("section_size", _size_not_multiple, "size must be multiple times increment"),
    ("placement_comparison", _pl_difference, "difference must be b - a"),
    ("placement_comparison", _pl_equal, "equal must follow rule P6"),
    ("placement_comparison", _pl_type, "is not a type of"),
    ("frame_element_map", _fem_pairs_unsorted, "pairs must be sorted and unique"),
    ("frame_element_map", _fem_candidates_unsorted, "ambiguous candidates must be sorted and unique"),
]

REPORT_VALID: list[tuple[str, Mutation]] = [
    ("readback_check", _rb_clean),
    ("readback_check", _rb_not_read_needs),
    ("readback_check", _rb_incomplete_needs),
    ("design_summary", _sum_only_pass),
    ("design_summary", _sum_not_designed_needs),
    ("design_summary", _sum_incomplete_needs),
    ("design_summary", _sum_empty_needs),
    ("design_summary", _sum_attention),
    ("design_summary", _sum_failing_sorted),
    ("section_size", _size_valid),
    ("section_size", _size_nondyadic),
]


def test_report_valid_variants() -> None:
    """AC47: the status rules R4 and S6 and the section size rules hold on every branch, not only on FAIL."""
    for stem, mutate in REPORT_VALID:
        payload = copy.deepcopy(_load(stem))
        mutate(payload)
        HARNESS_KINDS[REPORT_KINDS[stem]].model_validate(payload)


def test_report_fixtures() -> None:
    """AC47: the four report fixtures pass through their kinds and reload; every invalid one fails on its rule."""
    for stem, kind in REPORT_KINDS.items():
        model = HARNESS_KINDS[kind]
        payload = _load(stem)
        parsed = model.model_validate(payload)
        assert model.model_validate(parsed.model_dump(mode="json", exclude_none=False)) == parsed
        with pytest.raises(ValidationError, match="Extra inputs"):
            model.model_validate({**payload, "unknown_field": 1})
    for stem, mutate, fragment in REPORT_INVALID:
        payload = copy.deepcopy(_load(stem))
        mutate(payload)
        with pytest.raises(ValidationError, match=fragment):
            HARNESS_KINDS[REPORT_KINDS[stem]].model_validate(payload)


def test_calc_kinds_are_harness_family_and_extend_the_registry() -> None:
    """The calc kinds sit in the harness family beside the neutral and engine kinds."""
    assert set(CALC_KINDS) == set(KINDS.values()) | set(REPORT_KINDS.values())
    assert all(name.startswith("harness.") for name in CALC_KINDS)
    for name, model in CALC_KINDS.items():
        assert HARNESS_KINDS[name] is model
    assert "harness.journal_blob/1" in HARNESS_KINDS
    assert "model.stories/1" in HARNESS_KINDS


def test_neutral_family_refused() -> None:
    """AC47: a calc kind in a neutral family is refused by the contract."""
    with pytest.raises(ContractDefinitionError):
        NEUTRAL_KINDS.extend({"model.model_diff/1": ModelDiff})
