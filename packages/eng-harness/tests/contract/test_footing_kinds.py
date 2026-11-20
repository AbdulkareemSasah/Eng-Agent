"""Contract tests of the footing kinds (plan 0010 T1; spec 0010 AC33, section 4.2)."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from eng_contract.verdicts import VerdictStatus
from pydantic import ValidationError

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.kinds.footing import (
    FOOTING_KINDS,
    Families,
    Family,
    PatternRow,
    ReactionsToJointLoads,
)

DATA = Path(__file__).resolve().parents[1] / "data" / "kinds" / "footing"
KINDS = {
    "subjects": "harness.footing_subjects/1",
    "dims": "harness.footing_dims/1",
    "design": "harness.footing_design/1",
    "status": "harness.footing_status/1",
    "schedule": "harness.footing_schedule/1",
    "safe_equilibrium": "harness.safe_equilibrium/1",
    "reactions_to_joint_loads": "harness.reactions_to_joint_loads/1",
}
Mutation = Callable[[dict[str, Any]], None]


def _load(stem: str) -> dict[str, Any]:
    data = json.loads((DATA / f"{stem}.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _set(path: list[str | int], value: Any) -> Mutation:
    def mutate(p: dict[str, Any]) -> None:
        node: Any = p
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return mutate


def _duplicate_ids(p: dict[str, Any]) -> None:
    p["footings"][1]["id"] = p["footings"][0]["id"]


def _unsorted(p: dict[str, Any]) -> None:
    p["footings"].reverse()


def _closure_passed_with_fail(p: dict[str, Any]) -> None:
    p["footings"][1]["closure"] = "passed"


def _closure_failing_without_fail(p: dict[str, Any]) -> None:
    p["footings"][0]["closure"] = "failing"


def _state_differs(p: dict[str, Any]) -> None:
    p["footings"][0]["state"]["bearing"] = "FAIL"


def _subject_dup(p: dict[str, Any]) -> None:
    p["subjects"][1]["id"] = "J1"


INVALID: list[tuple[str, Mutation, str]] = [
    ("subjects", _set(["subjects", 0, "cx_mm"], 0.0), "cx_mm"),
    ("subjects", _set(["subjects", 0, "x_mm"], float("nan")), "x_mm"),
    ("subjects", _set(["excluded", 0, "reason"], ""), "reason"),
    ("subjects", _subject_dup, "subjects must be sorted"),
    ("dims", _set(["footings", 0, "Lx_mm"], -1.0), "Lx_mm"),
    ("dims", _set(["footings", 0, "source"], "magic"), "source"),
    ("dims", _set(["footings", 0, "plan_at_max"], "yes"), "plan_at_max"),
    ("dims", _duplicate_ids, "footings must be sorted"),
    ("dims", _unsorted, "footings must be sorted"),
    ("dims", _set(["trace", "calc_version"], "2"), "trace.calc_version|those of calc"),
    ("design", _set(["footings", 0, "db_mm"], 0.0), "db_mm"),
    ("design", _set(["footings", 0, "n_x"], -1), "n_x"),
    ("design", _set(["footings", 0, "d_mm"], 0.0), "d_mm"),
    ("design", _set(["footings", 0, "reaction_height_mm"], "high"), "reaction_height_mm"),
    ("status", _set(["footings", 0, "families", "bearing", "status"], "MAYBE"), "status"),
    ("status", _set(["footings", 0, "closure"], "done"), "closure"),
    ("status", _closure_passed_with_fail, "closure"),
    ("status", _closure_failing_without_fail, "closure"),
    ("status", _state_differs, "state"),
    ("status", _unsorted, "footings must be sorted"),
    ("schedule", _set(["footings", 0, "verdict_sets", 0], "not-a-result"), "verdict_sets"),
    ("schedule", _set(["footings", 0, "closure"], "done"), "closure"),
    ("schedule", _set(["footings", 0, "closure"], "failing"), "closure"),
    ("schedule", _set(["footings", 0, "design", "h_mm"], 0.0), "h_mm"),
    ("safe_equilibrium", _set(["tolerance"], -0.1), "tolerance"),
    ("safe_equilibrium", _set(["patterns", 0, "status"], "NOT_COMPARED"), "self_weight"),
    ("safe_equilibrium", _set(["patterns", 1, "status"], "PASS"), "self_weight"),
    ("safe_equilibrium", _set(["patterns", 0, "status"], "MAYBE"), "status"),
    ("reactions_to_joint_loads", _set(["axes"], "local"), "axes"),
    ("reactions_to_joint_loads", _set(["loads", 0, "punch_x_mm"], 0.0), "punch_x_mm"),
    ("reactions_to_joint_loads", _set(["loads", 0, "joint"], ""), "joint"),
]


def test_fixtures() -> None:
    """AC33: every valid fixture passes through its registered kind, every invalid one fails naming its field."""
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


def test_registration() -> None:
    """The footing kinds are exactly `FOOTING_KINDS` and are registered with the harness kinds."""
    assert set(FOOTING_KINDS) == set(KINDS.values())
    for kind, model in FOOTING_KINDS.items():
        assert HARNESS_KINDS[kind] is model


def test_reactions_ok_has_null_reason_and_needs_engineer_carries_reason() -> None:
    """Spec 0010 §4.2 / §4.9: OK has reason null; NEEDS_ENGINEER carries each soft reason."""
    model = ReactionsToJointLoads
    ok = model.model_validate(_load("reactions_to_joint_loads"))
    assert (ok.status, ok.reason) == ("OK", None)
    for reason in ("UNMATCHED", "PATTERN_MISSING", "COMBO_CONFLICT"):
        payload = copy.deepcopy(_load("reactions_to_joint_loads"))
        payload["status"] = "NEEDS_ENGINEER"
        payload["reason"] = reason
        payload["loads"] = []
        payload["combinations_to_add"] = []
        parsed = model.model_validate(payload)
        assert (parsed.status, parsed.reason, parsed.loads, parsed.combinations_to_add) == (
            "NEEDS_ENGINEER",
            reason,
            [],
            [],
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        model.model_validate({**_load("reactions_to_joint_loads"), "unknown_field": True})


def test_families_closure_passed_failing_and_needs_engineer() -> None:
    """Spec 0010 §4.4.5: passed when all PASS; failing when any FAIL; else needs_engineer."""
    all_pass = {
        name: Family(status=VerdictStatus.PASS, ratio=0.5)
        for name in (
            "bearing",
            "one_way_shear",
            "punching",
            "flexure",
            "min_steel",
            "development",
        )
    }
    assert Families.model_validate(all_pass).closure() == "passed"
    failing = dict(all_pass)
    failing["bearing"] = Family(status=VerdictStatus.FAIL, ratio=1.2)
    assert Families.model_validate(failing).closure() == "failing"
    needs = dict(all_pass)
    needs["flexure"] = Family(status=VerdictStatus.NEEDS_ENGINEER, ratio=None)
    assert Families.model_validate(needs).closure() == "needs_engineer"
    needs_and_fail = dict(needs)
    needs_and_fail["punching"] = Family(status=VerdictStatus.FAIL, ratio=1.1)
    assert Families.model_validate(needs_and_fail).closure() == "failing"


def test_pattern_row_self_weight_matches_not_compared_only() -> None:
    """self_weight patterns, and only they, are NOT_COMPARED (spec 0010 §4.9 step 6)."""
    PatternRow.model_validate(
        {"pattern": "DEAD", "self_weight": False, "applied_kN": 1.0, "reaction_kN": 1.0, "status": "PASS"}
    )
    PatternRow.model_validate(
        {
            "pattern": "SELF",
            "self_weight": True,
            "applied_kN": 0.0,
            "reaction_kN": -10.0,
            "status": "NOT_COMPARED",
        }
    )
    with pytest.raises(ValidationError, match="self_weight"):
        PatternRow.model_validate(
            {
                "pattern": "DEAD",
                "self_weight": False,
                "applied_kN": 1.0,
                "reaction_kN": 1.0,
                "status": "NOT_COMPARED",
            }
        )
    with pytest.raises(ValidationError, match="self_weight"):
        PatternRow.model_validate(
            {
                "pattern": "SELF",
                "self_weight": True,
                "applied_kN": 0.0,
                "reaction_kN": -10.0,
                "status": "PASS",
            }
        )
