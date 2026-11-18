"""Contract tests of the edit-cycle kinds (plan 0007 T1a; spec 0007 section 4.2, AC3)."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.kinds.edit_cycle import EDIT_CYCLE_KINDS

DATA = Path(__file__).resolve().parents[1] / "data" / "kinds" / "edit_cycle"
KINDS = {
    "change_set_check": "harness.change_set_check/1",
    "analysis_summary": "harness.analysis_summary/1",
    "csi_name_lists": "harness.csi_name_lists/1",
    "host_design_verdicts": "harness.host_design_verdicts/1",
}
Mutation = Callable[[dict[str, Any]], None]


def _load(stem: str) -> dict[str, Any]:
    data = json.loads((DATA / f"{stem}.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _check_status(p: dict[str, Any]) -> None:
    p["issues"].append({"item_id": "i1", "severity": "error", "code": "EMPTY_SELECTION", "detail": "x", "gap": None})


def _check_fail_without_error(p: dict[str, Any]) -> None:
    p["status"] = "FAIL"


def _check_gap_missing(p: dict[str, Any]) -> None:
    p["status"] = "FAIL"
    p["issues"] = [{"item_id": "i1", "severity": "error", "code": "NOT_IMPLEMENTED", "detail": "x", "gap": None}]


def _check_gap_extra(p: dict[str, Any]) -> None:
    p["issues"][0]["gap"] = "H-G1"


def _check_targets(p: dict[str, Any]) -> None:
    p["resolved"][0]["targets"] = ["F2", "F1"]


def _check_ref_number(p: dict[str, Any]) -> None:
    p["resolved"][1]["values"][0]["ref"] = "12.5"


def _check_dup_item(p: dict[str, Any]) -> None:
    p["resolved"][1]["item_id"] = "i1"


def _check_code(p: dict[str, Any]) -> None:
    p["issues"][0]["code"] = "bad code"


def _sum_counts(p: dict[str, Any]) -> None:
    p["has_errors"] = True


def _sum_unclassified(p: dict[str, Any]) -> None:
    p["has_unclassified"] = True


def _sum_status_pass(p: dict[str, Any]) -> None:
    p["status"] = "PASS"


def _sum_status_fail(p: dict[str, Any]) -> None:
    p["counts"]["error"] = 1
    p["has_errors"] = True


def _sum_exceeding_below(p: dict[str, Any]) -> None:
    p["exceeding"][0]["ratio"] = 0.005


def _sum_exceeding_unsorted(p: dict[str, Any]) -> None:
    p["exceeding"].insert(0, {"direction": "Y", "story": "S1", "case": "EQY", "ratio": 0.02})


def _sum_negative(p: dict[str, Any]) -> None:
    p["counts"]["info"] = -1


def _names_unsorted(p: dict[str, Any]) -> None:
    p["frame_sections"] = ["C40", "B30"]


def _names_duplicate(p: dict[str, Any]) -> None:
    p["patterns"] = ["Dead", "Dead"]


def _names_empty(p: dict[str, Any]) -> None:
    p["materials"] = [""]


def _hdv_counts(p: dict[str, Any]) -> None:
    p["counts"]["PASS"] = 2


def _hdv_status_contradicts_ratio(p: dict[str, Any]) -> None:
    p["verdicts"][1]["status"] = "PASS"


def _hdv_trace_out_of_range(p: dict[str, Any]) -> None:
    p["verdicts"][0]["trace_ref"] = "#/traces/1"


def _hdv_trace_not_local(p: dict[str, Any]) -> None:
    p["verdicts"][0]["trace_ref"] = "res_00000000000000000000000001#/steps/0"


def _hdv_other_calc_trace(p: dict[str, Any]) -> None:
    p["trace"]["calc_id"] = "harness.analysis_summary"


def _hdv_no_calc(p: dict[str, Any]) -> None:
    del p["calc"]


def _hdv_no_draft(p: dict[str, Any]) -> None:
    del p["draft"]


def _hdv_no_traces(p: dict[str, Any]) -> None:
    del p["traces"]


INVALID: list[tuple[str, Mutation, str]] = [
    ("change_set_check", _check_status, "status"),
    ("change_set_check", _check_fail_without_error, "status"),
    ("change_set_check", _check_gap_missing, "gap"),
    ("change_set_check", _check_gap_extra, "gap"),
    ("change_set_check", _check_targets, "sorted"),
    ("change_set_check", _check_ref_number, "ref"),
    ("change_set_check", _check_dup_item, "duplicate"),
    ("change_set_check", _check_code, "code"),
    ("analysis_summary", _sum_counts, "has_errors"),
    ("analysis_summary", _sum_unclassified, "has_unclassified"),
    ("analysis_summary", _sum_status_pass, "status"),
    ("analysis_summary", _sum_status_fail, "status"),
    ("analysis_summary", _sum_exceeding_below, "limit"),
    ("analysis_summary", _sum_exceeding_unsorted, "sorted"),
    ("analysis_summary", _sum_negative, "info"),
    ("csi_name_lists", _names_unsorted, "sorted"),
    ("csi_name_lists", _names_duplicate, "sorted"),
    ("csi_name_lists", _names_empty, "materials"),
    ("host_design_verdicts", _hdv_counts, "counts must match"),
    ("host_design_verdicts", _hdv_status_contradicts_ratio, "contradicts"),
    ("host_design_verdicts", _hdv_trace_out_of_range, "out of range"),
    ("host_design_verdicts", _hdv_trace_not_local, "LocalTraceRef"),
    ("host_design_verdicts", _hdv_other_calc_trace, "those of calc"),
    ("host_design_verdicts", _hdv_no_calc, "calc"),
    ("host_design_verdicts", _hdv_no_draft, "draft"),
    ("host_design_verdicts", _hdv_no_traces, "traces"),
]


def test_fixtures() -> None:
    """AC3: every valid fixture passes through its registered kind, every invalid one fails on its rule."""
    for stem, kind in KINDS.items():
        model = HARNESS_KINDS[kind]
        payload = _load(stem)
        parsed = model.model_validate(payload)
        assert model.model_validate(parsed.model_dump(mode="json", exclude_none=False)) == parsed
        with pytest.raises(ValidationError, match="Extra inputs"):
            model.model_validate({**payload, "unknown_field": 1})
    for stem, mutate, fragment in INVALID:
        payload = copy.deepcopy(_load(stem))
        mutate(payload)
        with pytest.raises(ValidationError, match=fragment):
            HARNESS_KINDS[KINDS[stem]].model_validate(payload)


def test_kinds_are_harness_family_and_registered() -> None:
    """The edit-cycle kinds sit in the harness family and extend the registry."""
    assert set(EDIT_CYCLE_KINDS) == set(KINDS.values())
    assert all(name.startswith("harness.") for name in EDIT_CYCLE_KINDS)
    for name, model in EDIT_CYCLE_KINDS.items():
        assert HARNESS_KINDS[name] is model
    assert "harness.expected_effects/1" in HARNESS_KINDS
