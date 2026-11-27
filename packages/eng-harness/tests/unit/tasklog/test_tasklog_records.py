"""Record and triage-line models of the task log (plan 0015 T1; spec 0015 AC1, AC2, AC37, sections 4.3, 4.3.1)."""

import hashlib
import json
from typing import Any

import pytest
from eng_contract.canonical import canonical_json
from pydantic import TypeAdapter, ValidationError

from eng_harness.tasklog._records import TaskRecord, TriageLine

_RECORD_SCHEMA = "harness.tasklog_record/1"
_TRIAGE_SCHEMA = "harness.tasklog_triage/1"
_TASK_ID = "task_01KDVDNA00EEHMW00B9ZA4ZDSH"
_NEED_ID = "need_01KDVDNA00EEHMW00B9ZA4ZDSH_1"
_OTHER_NEED_ID = "need_01KDVDNA02BX1SJVXRMXPXQSD9_1"
_RUN_ID = "run_01KDVDNA01NEDC4EXH1ZACT2K2"
_AT = "2026-11-14T10:00:00Z"
_ZERO_SHA = "0" * 64
_AGENT = "agent:test-tool"
_ARABIC_TEXT = 'من فضلك ابن النموذج الانشائي كاملا من "الرسومات"'
_ARABIC_GUARDED = "من فضلك ابن <withheld:personal-path:0123456789ab> النموذج"

CATEGORIES = (
    "no_workflow",
    "tool_not_on_allowlist",
    "no_edit_kind",
    "not_implemented",
    "no_calc",
    "calc_not_approved",
    "no_code_pack_check",
    "host_limitation",
    "server_limitation",
    "value_without_source",
    "harness_unavailable",
    "harness_defect",
    "other",
)
OUTCOMES = ("new_spec", "covered", "host_limitation", "out_of_scope", "duplicate", "defect")

_RECORDS = TypeAdapter(TaskRecord)
_TRIAGE = TypeAdapter(TriageLine)


def _sha256_hex(data: bytes) -> str:
    """The SHA-256 of `data` as lowercase hex (spec 0015 4.3: the `*_sha256` fields)."""
    return hashlib.sha256(data).hexdigest()


def _record(kind: str, by: str, **fields: Any) -> dict[str, Any]:
    """One task-record payload: the common fields of spec 0015 4.3 plus the kind's fields."""
    return {
        "schema": _RECORD_SCHEMA,
        "task_id": _TASK_ID,
        "seq": 1,
        "at": _AT,
        "kind": kind,
        "by": by,
        "policy": "full",
        "redactions": [],
        "prev_sha256": _ZERO_SHA,
        **fields,
    }


def _triage(kind: str, by: str, **fields: Any) -> dict[str, Any]:
    """One triage-line payload: the common fields of spec 0015 4.3.1 plus the kind's fields."""
    return {
        "schema": _TRIAGE_SCHEMA,
        "need_id": _NEED_ID,
        "seq": 1,
        "at": _AT,
        "kind": kind,
        "by": by,
        "redactions": [],
        "prev_sha256": _ZERO_SHA,
        **fields,
    }


def _not_found(category: str) -> dict[str, Any]:
    """A `not_found` payload of one category (`not_implemented` needs a gap id, spec 0015 4.3)."""
    payload = _record(
        "not_found",
        _AGENT,
        need_id=_NEED_ID,
        category=category,
        need_en="One workflow from drawings to a model.",
        target="model_from_drawings",
        evidence=["#1"],
        blocking=False,
    )
    if category == "not_implemented":
        payload["gap_id"] = "H-G1"
    if category == "other":
        payload["need_en"] = "Some other missing capability described at length for triage to recategorise."
    return payload


def _record_cases() -> dict[str, dict[str, Any]]:
    """One minimal valid payload per record kind of spec 0015 4.3."""
    owner_text = "Fixture owner words."
    return {
        "task_opened": _record(
            "task_opened",
            _AGENT,
            title_en="Build the model from the drawings.",
            agent={"tool": "test-tool"},
            session={"place": "local"},
            repo_commit=_sha256_hex(b"repo")[:40],
            integration_branch="build/v1",
            harness_version="0.1.0-test",
        ),
        "owner_words": _record(
            "owner_words",
            _AGENT,
            role="request",
            lang="ar",
            text=owner_text,
            text_sha256=_sha256_hex(owner_text.encode("utf-8")),
        ),
        "narration": _record("narration", _AGENT, text_en="Fixture narration."),
        "searched": _record(
            "searched",
            _AGENT,
            for_en="a workflow from drawings",
            where="workflow_registry",
            result="not_found",
            detail_en="No workflow registry in this build.",
            refs=["packages/eng-harness/docs/specs/0007-model-edit-cycle.md"],
            catalog="unavailable",
        ),
        "not_found": _not_found("no_workflow"),
        "did_instead": _record(
            "did_instead",
            _AGENT,
            way="owner_by_hand",
            text_en="The owner runs the tools by hand.",
            refs=[f".eng/tasklog/in/changes.json sha256:{_sha256_hex(b'input')}"],
        ),
        "problem": _record("problem", _AGENT, text_en="The check output names a defect.", evidence=["#1"]),
        "handoff": _record(
            "handoff",
            _AGENT,
            to="owner",
            done_en="Searched and recorded.",
            left_en="Nothing.",
            why_en="Blocked on a missing workflow.",
        ),
        "run_refused": _record(
            "run_refused",
            _AGENT,
            workflow="model_edit_cycle",
            exit_code=2,
            code="NOT_FOUND",
            missing=["models/m1.EDB"],
            message_en="No workflow in this build.",
        ),
        "run_attached": _record(
            "run_attached",
            "harness",
            run_id=_RUN_ID,
            workflow="model_edit_cycle",
            status="PAUSED",
            exit_code=10,
            event_count=9,
            last_seq=9,
            chain_sha256=_sha256_hex(b"chain"),
            report=f"runs/{_RUN_ID}/report/report.html",
            unreleased_tools={},
            timings={"machine_ms": 12, "waiting_ms": 34, "resumes": 1},
            model_files=["m1.EDB"],
        ),
        "run_fact": _record(
            "run_fact", "harness", run_id=_RUN_ID, journal_seq=9, event="run_completed", summary_en="The run completed."
        ),
        "task_closed": _record("task_closed", _AGENT, status="DONE", summary_en="Done.", open_needs=[]),
        "withheld_after": _record(
            "withheld_after",
            "harness",
            target_seq=1,
            field="text",
            rule="personal-path",
            span_sha256=_sha256_hex(b"span"),
            line_sha256_before=_sha256_hex(b"line"),
            reason_en="Withheld after the push.",
        ),
    }


_RECORD_CASES = _record_cases()


def _triaged(outcome: str) -> dict[str, Any]:
    """A `triaged` payload of one outcome (`duplicate_of` exactly for `duplicate`, spec 0015 4.3.1)."""
    text = "Public text for the digest."
    payload = _triage(
        "triaged",
        "dev-session:B-478",
        outcome=outcome,
        public_en=text,
        public_en_sha256=_sha256_hex(text.encode("utf-8")),
    )
    if outcome == "duplicate":
        payload["duplicate_of"] = _OTHER_NEED_ID
    return payload


def _triage_cases() -> dict[str, dict[str, Any]]:
    """One minimal valid payload per triage-line kind of spec 0015 4.3.1."""
    return {
        "triaged": _triaged("new_spec"),
        "public_released": _triage(
            "public_released",
            "dev-session:B-478",
            public_en_sha256=_sha256_hex(b"released public text"),
            public_en_released="owner",
            released_on="2026-11-14",
            reply_sha256=_sha256_hex(b"owner reply"),
        ),
        "answered": _triage(
            "answered",
            "dev-session:B-478",
            release="eng-harness==0.2.0",
            commit=_sha256_hex(b"commit")[:40],
        ),
        "withheld_after": _triage(
            "withheld_after",
            "harness",
            target_seq=1,
            field="public_en",
            rule="personal-path",
            span_sha256=_sha256_hex(b"span"),
            line_sha256_before=_sha256_hex(b"line"),
            reason_en="Withheld after the push.",
        ),
    }


_TRIAGE_CASES = _triage_cases()


def test_kind_set_closed() -> None:
    """AC1: every record kind and `not_found` category validates; any other is refused (spec 0015 4.3)."""
    for kind, payload in _RECORD_CASES.items():
        assert _RECORDS.validate_python(payload).kind == kind
    bogus_kind = {**_RECORD_CASES["narration"], "kind": "bogus_kind"}
    with pytest.raises(ValidationError):
        _RECORDS.validate_python(bogus_kind)
    mapping = _RECORDS.json_schema()["discriminator"]["mapping"]
    assert set(mapping) == set(_RECORD_CASES)
    for category in CATEGORIES:
        assert _RECORDS.validate_python(_not_found(category)).kind == "not_found"
    bogus_category = {**_not_found("no_workflow"), "category": "bogus_category"}
    with pytest.raises(ValidationError):
        _RECORDS.validate_python(bogus_category)


def test_extra_forbidden() -> None:
    """AC1: an unknown field, top-level or nested, is refused (spec 0015 4.3: `extra="forbid"`)."""
    extra_top = {**_RECORD_CASES["narration"], "nonsense": 1}
    with pytest.raises(ValidationError):
        _RECORDS.validate_python(extra_top)
    extra_nested = {**_RECORD_CASES["task_opened"], "agent": {"tool": "test-tool", "nonsense": 1}}
    with pytest.raises(ValidationError):
        _RECORDS.validate_python(extra_nested)


def test_owner_words_bytes_exact_arabic() -> None:
    """AC2: Arabic owner words round-trip byte-exact with the SHA-256 of the input bytes (spec 0015 4.3)."""
    raw = _ARABIC_TEXT.encode("utf-8")
    payload = _record("owner_words", _AGENT, role="request", lang="ar", text=_ARABIC_TEXT, text_sha256=_sha256_hex(raw))
    first = _RECORDS.dump_python(_RECORDS.validate_python(payload), mode="json")
    assert first["text"] == _ARABIC_TEXT
    assert first["text_sha256"] == _sha256_hex(raw)
    again = _RECORDS.dump_python(_RECORDS.validate_python(json.loads(canonical_json(first))), mode="json")
    assert again["text"] == _ARABIC_TEXT
    assert again["text"].encode("utf-8") == raw
    assert again["text_sha256"] == _sha256_hex(raw)
    # AC4: a withheld record keeps the original's hash, so a hash that no longer matches the text still validates.
    guarded = {**payload, "text": _ARABIC_GUARDED}
    kept = _RECORDS.dump_python(_RECORDS.validate_python(guarded), mode="json")
    assert kept["text"] == _ARABIC_GUARDED
    assert kept["text_sha256"] == _sha256_hex(raw)


def test_triage_model_closed() -> None:
    """AC37: the triage kind and outcome sets are closed; unknown fields are refused (spec 0015 4.3.1)."""
    for kind, payload in _TRIAGE_CASES.items():
        assert _TRIAGE.validate_python(payload).kind == kind
    bogus_kind = {**_TRIAGE_CASES["answered"], "kind": "bogus_kind"}
    with pytest.raises(ValidationError):
        _TRIAGE.validate_python(bogus_kind)
    mapping = _TRIAGE.json_schema()["discriminator"]["mapping"]
    assert set(mapping) == set(_TRIAGE_CASES)
    for outcome in OUTCOMES:
        assert _TRIAGE.validate_python(_triaged(outcome)).kind == "triaged"
    with pytest.raises(ValidationError):
        _TRIAGE.validate_python(_triaged("bogus_outcome"))
    missing_link = _triaged("duplicate")
    del missing_link["duplicate_of"]
    with pytest.raises(ValidationError):
        _TRIAGE.validate_python(missing_link)
    stray_link = _triaged("covered")
    stray_link["duplicate_of"] = _OTHER_NEED_ID
    with pytest.raises(ValidationError):
        _TRIAGE.validate_python(stray_link)
    extra_top = {**_TRIAGE_CASES["answered"], "nonsense": 1}
    with pytest.raises(ValidationError):
        _TRIAGE.validate_python(extra_top)
    # Triage lines carry no policy (spec 0015 4.3.1), so one is an unknown field there.
    with_policy = {**_TRIAGE_CASES["answered"], "policy": "full"}
    with pytest.raises(ValidationError):
        _TRIAGE.validate_python(with_policy)


def test_release_binds_text_hash() -> None:
    """AC37: a `public_released` line names the exact `public_en` it releases by SHA-256 (spec 0015 4.3.1)."""
    released = _triage(
        "public_released",
        "dev-session:B-478",
        public_en_sha256=_sha256_hex(b"released public text"),
        public_en_released="owner",
        released_on="2026-11-14",
        reply_sha256=_sha256_hex(b"owner reply"),
    )
    stored = _TRIAGE.dump_python(_TRIAGE.validate_python(released), mode="json")
    assert stored["public_en_sha256"] == _sha256_hex(b"released public text")
    assert stored["public_en_sha256"] != _sha256_hex(b"other public text")
    unnamed = {key: value for key, value in released.items() if key != "public_en_sha256"}
    with pytest.raises(ValidationError):
        _TRIAGE.validate_python(unnamed)


@pytest.mark.parametrize(
    ("model", "snapshot"),
    [pytest.param(TaskRecord, "record-1.json", id="record"), pytest.param(TriageLine, "triage-1.json", id="triage")],
)
def test_schema_snapshot_pins_the_models(model: Any, snapshot: str) -> None:
    """Spec 0015 section 4.3: the committed schema snapshot is pinned against the model's JSON schema."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "data" / "snapshots" / "tasklog" / snapshot
    assert json.loads(path.read_text(encoding="utf-8")) == TypeAdapter(model).json_schema()
