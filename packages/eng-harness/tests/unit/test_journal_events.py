"""Journal event payload models and the harness kinds (plan 0001 T3; spec 0001 section 4.4.2, the models of AC26)."""

from typing import Any

import pytest
from eng_contract.errors import ErrorCode, ErrorDetail
from pydantic import BaseModel, ValidationError

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.errors import HarnessCode
from eng_harness.journal import PAYLOAD_MODELS, EventType
from eng_harness.journal._events import (
    ApprovalResolved,
    CheckEnforced,
    DecisionMade,
    HarnessError,
    InputRequested,
    ModelBound,
    ModelSaved,
    RunEscalated,
    RunHeader,
    RunResumed,
    StepFailed,
    StepStarted,
)

REF = "res_" + "0" * 26
SHA = "a" * 64
STAMP = "2026-01-01T00:00:00.000Z"
BLOCK = {"name": "b", "version": "1", "code_sha256": SHA}
SPEC_TYPES = [
    "run_started",
    "step_started",
    "step_completed",
    "step_failed",
    "step_reconciled",
    "step_rerun",
    "decision_made",
    "input_requested",
    "input_provided",
    "approval_requested",
    "approval_resolved",
    "host_started",
    "model_bound",
    "check_enforced",
    "model_saved",
    "run_paused",
    "run_resumed",
    "run_escalated",
    "run_completed",
    "run_failed",
    "signed_off",
]
SAMPLES: dict[str, dict[str, Any]] = {
    "run_started": {
        "run_id": "run_x",
        "workflow": "w",
        "block": BLOCK,
        "input_ref": REF,
        "input_sha256": SHA,
        "basis_ref": REF,
        "mode": "work_on_copy",
        "run_class": "trial",
        "engine_version": "1",
        "contract_version": "eng-contract/1",
        "settings_sha256": SHA,
        "servers": [],
        "always_ask": [],
    },
    "step_started": {"kind": "tool", "name": "t", "args": {"a": 1}, "args_sha256": SHA, "effect": "read"},
    "step_completed": {"result": {"ref": REF, "summary": {}, "warnings": [], "complete": True}, "duration_ms": 3},
    "step_failed": {
        "error": {"harness_code": "NEEDS_ENGINEER", "message": "m"},
        "retryable": False,
        "duration_ms": 1,
    },
    "step_reconciled": {"op_id": "o", "outcome": "applied", "decided_by": "adapter", "evidence": [REF]},
    "step_rerun": {"reason": "read_in_flight"},
    "decision_made": {
        "point": "p",
        "options": ["a", "b"],
        "choice": "a",
        "decided_by": "rule",
        "confidence": None,
        "latency_ms": 0,
        "state_sha256": SHA,
        "suggestions": [],
    },
    "input_requested": {"request_id": "r", "kind": "block", "title": "t", "fields_schema_sha256": SHA},
    "input_provided": {"request_id": "r", "answer_ref": REF, "by": "engineer:x"},
    "approval_requested": {
        "request_id": "r",
        "kind": "INFO",
        "title": "t",
        "preview_ref": REF,
        "shown_sha256": SHA,
        "binding": {},
        "items": [],
    },
    "approval_resolved": {
        "request_id": "r",
        "shown_sha256": SHA,
        "decision": "approve",
        "rejected_items": [],
        "by": "mode:autonomous_logged",
    },
    "host_started": {"host_key": "h", "instance_id": "i", "pid": 7, "process_started_at": STAMP, "program": "etabs"},
    "model_bound": {
        "model_key": "m",
        "host_key": "h",
        "instance_id": "i",
        "reason": "first_use",
        "file_names": ["a.edb"],
    },
    "check_enforced": {"invariant": 1, "model_key": "m", "outcome": "pass"},
    "model_saved": {
        "model_key": "m",
        "model_id": "mdl_" + "0" * 26,
        "revision": 1,
        "fingerprint": "f",
        "file_sha256": SHA,
        "file_name": "a.edb",
        "role": "working_copy",
        "origin_sha256": SHA,
        "origin_file_names": ["a.edb"],
    },
    "run_paused": {"reason": "awaiting_input", "request_ids": ["r"]},
    "run_resumed": {"resume_no": 1, "code_hash_changed": False, "servers": [], "restored_to_seq": None},
    "run_escalated": {"reason": "attempts_exhausted", "detail": "d", "evidence": []},
    "run_completed": {"output_ref": REF, "output_sha256": SHA, "draft": True},
    "run_failed": {"reason": "abandoned", "by": "engineer:x"},
    "signed_off": {"outputs": [REF], "approval_request_id": "r", "by": "engineer:x"},
}


def test_every_event_type_has_a_model() -> None:
    assert [t.value for t in EventType] == SPEC_TYPES  # the 21 types of spec 4.4.2, in table order
    assert set(PAYLOAD_MODELS) == set(EventType)
    assert set(SAMPLES) == set(SPEC_TYPES)
    for name in SPEC_TYPES:
        model = PAYLOAD_MODELS[EventType(name)]
        assert issubclass(model, BaseModel)
        assert isinstance(model.model_validate(SAMPLES[name]), model)
    assert len({PAYLOAD_MODELS[t] for t in EventType}) == 21  # one model per type


@pytest.mark.parametrize("name", SPEC_TYPES)
def test_event_models_forbid_extra_fields(name: str) -> None:
    model = PAYLOAD_MODELS[EventType(name)]
    assert model.model_config.get("extra") == "forbid"
    with pytest.raises(ValidationError, match="unknown_field"):
        model.model_validate({**SAMPLES[name], "unknown_field": 1})
    required = next(n for n, f in model.model_fields.items() if f.is_required())
    with pytest.raises(ValidationError):
        model.model_validate({k: v for k, v in SAMPLES[name].items() if k != required})


def test_harness_kinds_are_registered() -> None:
    for name in ("run_input", "run_output", "approval_preview", "journal_blob"):
        assert f"harness.{name}/1" in HARNESS_KINDS
    assert "model.stories/1" in HARNESS_KINDS  # the neutral kinds stay registered
    blob = HARNESS_KINDS["harness.journal_blob/1"].model_validate({"value": {"a": [1, 2]}})
    assert blob.model_dump() == {"value": {"a": [1, 2]}}
    with pytest.raises(ValidationError):
        HARNESS_KINDS["harness.run_input/1"].model_validate({"value": 1, "other": 2})
    preview = HARNESS_KINDS["harness.approval_preview/1"].model_validate({"title": "t", "rows": []})
    assert preview.model_dump() == {"title": "t", "rows": []}  # its fields belong to plan task T7: extras pass through


def test_b068_run_header_fields() -> None:
    header = RunHeader.model_validate(SAMPLES["run_started"])
    assert header.run_class == "trial"
    assert header.unreleased_tools == {}  # empty when none
    assert header.decision_runtime == {}
    full = RunHeader.model_validate(
        {
            **SAMPLES["run_started"],
            "run_class": "production",
            "unreleased_tools": {"t": {"r": 1}},
            "decision_runtime": {"p": 1},
        }
    )
    assert full.run_class == "production"
    assert full.unreleased_tools == {"t": {"r": 1}}
    assert full.decision_runtime == {"p": 1}
    for bad in ({"run_class": "other"}, {"mode": "other"}):
        with pytest.raises(ValidationError):
            RunHeader.model_validate({**SAMPLES["run_started"], **bad})
    with pytest.raises(ValidationError):
        RunHeader.model_validate({k: v for k, v in SAMPLES["run_started"].items() if k != "run_class"})


def test_b068_run_resumed_records_only_changes() -> None:
    resumed = RunResumed.model_validate(SAMPLES["run_resumed"])
    assert resumed.unreleased_tools is None
    assert resumed.decision_runtime is None
    changed = RunResumed.model_validate(
        {**SAMPLES["run_resumed"], "unreleased_tools": {}, "decision_runtime": {"a": 1}}
    )
    assert changed.unreleased_tools == {}  # an empty mapping is a recorded change, distinct from absent
    assert changed.decision_runtime == {"a": 1}
    with pytest.raises(ValidationError):
        RunResumed.model_validate({**SAMPLES["run_resumed"], "resume_no": 0})


def test_b068_approval_resolved_fields() -> None:
    default = ApprovalResolved.model_validate(SAMPLES["approval_resolved"])
    assert default.item_reasons == {}
    assert default.acknowledged_unreleased is False
    assert default.reason is None
    full = ApprovalResolved.model_validate(
        {
            **SAMPLES["approval_resolved"],
            "decision": "reject",
            "rejected_items": ["i1"],
            "item_reasons": {"i1": "too thin"},
            "acknowledged_unreleased": True,
            "by": "engineer:ann",
        }
    )
    assert full.item_reasons == {"i1": "too thin"}
    assert full.acknowledged_unreleased is True
    for by in ("someone", "engineer:", "mode:"):
        with pytest.raises(ValidationError):
            ApprovalResolved.model_validate({**SAMPLES["approval_resolved"], "by": by})


def test_b068_decision_request_id_and_engine_decision_kind() -> None:
    assert DecisionMade.model_validate(SAMPLES["decision_made"]).request_id is None  # null for another tier
    assert DecisionMade.model_validate({**SAMPLES["decision_made"], "request_id": "req1"}).request_id == "req1"
    request = InputRequested.model_validate({**SAMPLES["input_requested"], "kind": "engine.decision"})
    assert request.kind == "engine.decision"
    for kind in ("block", "engine.in_flight", "engine.host_state", "engine.escalation"):
        InputRequested.model_validate({**SAMPLES["input_requested"], "kind": kind})
    with pytest.raises(ValidationError):
        InputRequested.model_validate({**SAMPLES["input_requested"], "kind": "engine.other"})


def test_b068_file_name_fields_hold_base_names_only() -> None:
    assert ModelBound.model_validate(SAMPLES["model_bound"]).file_names == ["a.edb"]
    assert ModelSaved.model_validate(SAMPLES["model_saved"]).origin_file_names == ["a.edb"]
    unset = {k: v for k, v in SAMPLES["model_saved"].items() if k not in ("origin_sha256", "origin_file_names")}
    saved = ModelSaved.model_validate(unset)
    assert saved.origin_file_names == []
    assert saved.origin_sha256 is None
    for bad in ("dir/a.edb", "dir\\a.edb", "/a.edb"):
        with pytest.raises(ValidationError):
            ModelBound.model_validate({**SAMPLES["model_bound"], "file_names": [bad]})
        with pytest.raises(ValidationError):
            ModelSaved.model_validate({**SAMPLES["model_saved"], "file_name": bad})
        with pytest.raises(ValidationError):
            ModelSaved.model_validate({**SAMPLES["model_saved"], "origin_file_names": [bad]})


def test_step_started_holds_exactly_one_of_args_and_args_ref() -> None:
    inline = StepStarted.model_validate(SAMPLES["step_started"])
    assert inline.args == {"a": 1}
    assert inline.args_ref is None
    by_ref = {k: v for k, v in SAMPLES["step_started"].items() if k != "args"}
    assert StepStarted.model_validate({**by_ref, "args_ref": REF}).args is None
    with pytest.raises(ValidationError, match="exactly one"):
        StepStarted.model_validate(by_ref)
    with pytest.raises(ValidationError, match="exactly one"):
        StepStarted.model_validate({**SAMPLES["step_started"], "args_ref": REF})


def test_step_failed_error_is_contract_detail_or_harness_error() -> None:
    contract = {"code": ErrorCode.NOT_FOUND, "message": "m", "retryable": False}
    assert isinstance(StepFailed.model_validate({**SAMPLES["step_failed"], "error": contract}).error, ErrorDetail)
    harness = StepFailed.model_validate(SAMPLES["step_failed"]).error
    assert isinstance(harness, HarnessError)
    assert harness.harness_code is HarnessCode.NEEDS_ENGINEER
    with pytest.raises(ValidationError):
        StepFailed.model_validate({**SAMPLES["step_failed"], "duration_ms": -1})


def test_bounded_fields() -> None:
    for invariant in (0, 11):
        with pytest.raises(ValidationError):
            CheckEnforced.model_validate({**SAMPLES["check_enforced"], "invariant": invariant})
    for invariant in (1, 10):
        CheckEnforced.model_validate({**SAMPLES["check_enforced"], "invariant": invariant})
    reasons = (
        "replay_divergence",
        "needs_reconciliation",
        "host_state_mismatch",
        "units_mismatch",
        "attempts_exhausted",
        "block_escalation",
        "block_rule_violation",
        "unhandled_error",
    )
    for reason in reasons:
        assert RunEscalated.model_validate({**SAMPLES["run_escalated"], "reason": reason}).request_id is None
    with pytest.raises(ValidationError):
        RunEscalated.model_validate({**SAMPLES["run_escalated"], "reason": "other"})
    with pytest.raises(ValidationError):
        PAYLOAD_MODELS[EventType.STEP_COMPLETED].model_validate({**SAMPLES["step_completed"], "duration_ms": -1})
    with pytest.raises(ValidationError):
        PAYLOAD_MODELS[EventType.HOST_STARTED].model_validate({**SAMPLES["host_started"], "pid": 0})
    with pytest.raises(ValidationError):
        PAYLOAD_MODELS[EventType.RUN_STARTED].model_validate({**SAMPLES["run_started"], "input_sha256": "xyz"})
