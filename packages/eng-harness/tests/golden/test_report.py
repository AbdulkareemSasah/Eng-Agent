"""Report sections against the snapshot (plan 0006 T12; spec 0006 AC51).

The fixture run has two model revisions, a change set with a rejected item, a rejected change set, verdicts,
a model check, drift rows, a decision and a resume. T12 snapshots sections 2 to 5; T13 extends the snapshot to the
whole document.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eng_contract.envelope import Provenance
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore

from eng_harness.journal import EventType, JournalReader, JournalWriter
from eng_harness.report._model import ReportModel, fold_report

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "snapshots" / "report" / "report.html"
_CALC = Path(__file__).resolve().parents[1] / "data" / "kinds" / "calcs"
SHA = "a" * 64
MODEL = "mdl_" + "0" * 26
START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
_PRODUCER = Provenance(
    tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
)
_HEADER: dict[str, Any] = {
    "run_id": "run_x", "workflow": "w", "block": {"name": "b", "version": "1", "code_sha256": SHA},
    "input_sha256": SHA, "mode": "work_on_copy", "run_class": "trial",
    "engine_version": "1", "contract_version": "eng-contract/1", "settings_sha256": SHA, "servers": [],
    "always_ask": [],
}  # fmt: skip
_RUNTIME: dict[str, Any] = {
    "providers": [
        {"name": "local1", "model": "m-7b", "version": "2", "is_local": True, "tier": "shadow", "status": "ok"}
    ],
    "released": {"cycle.turn": {"point": "cycle.turn", "release": "r1"}},
    "dropped": [{"point": "cycle.next", "reason": "PR-G1"}],
}


@dataclass
class SectionsRun:
    """The folded fixture and the open reader the section renderers read."""

    model: ReportModel
    reader: JournalReader

    def close(self) -> None:
        """Close the reader."""
        self.reader.close()


def section(html: str, heading: str, following: str | None = None) -> str:
    """The fragment from ``<h2>heading</h2>`` up to the next named heading, or through the end."""
    start = html.index(f"<h2>{heading}</h2>")
    if following is None:
        return html[start:]
    return html[start : html.index(f"<h2>{following}</h2>")]


def _saved(revision: int, fingerprint: str, file_name: str, role: str, **extra: Any) -> dict[str, Any]:
    return {
        "model_key": "m", "model_id": MODEL, "revision": revision, "fingerprint": fingerprint,
        "file_sha256": SHA, "file_name": file_name, "role": role, **extra,
    }  # fmt: skip


def _done(result_id: str) -> dict[str, Any]:
    return {"result": {"ref": result_id, "summary": {}, "warnings": [], "complete": True}, "duration_ms": 1_000}


def _step(name: str, **extra: Any) -> dict[str, Any]:
    return {"kind": "tool", "name": name, "args": {}, "args_sha256": SHA, "effect": "read", **extra}


def load_sections_run(
    run_dir: Path, store: ResultStore, ids: SeededIdSource, runtime: dict[str, Any] | None = None
) -> SectionsRun:
    """Write the AC51 fixture and fold it. The caller closes the returned reader."""
    blob = store.put(
        "harness.journal_blob/1",
        {"value": {"a": {"b": {"c": {"d": "hidden-leaf"}}}}},
        _PRODUCER,
    )
    basis = store.put(
        "basis.design_basis/1",
        {
            "template": {"name": "office_rc", "version": "1", "sha256": SHA},
            "fields": {
                "limits.drift_ratio": {
                    "value": 0.02,
                    "unit": "1",
                    "source": "template:office_rc@1",
                    "confirmed": True,
                    "citation": "ASCE 7-16 Table 12.12-1",
                },
            },
        },
        _PRODUCER,
    )
    engineer = store.put(
        "basis.engineer_input/1",
        {
            "step": "basis.confirm",
            "fields": {
                "cover": {
                    "value": 40,
                    "unit": "mm",
                    "entered_by": "A. Engineer",
                    "entered_at": "2026-01-15T10:30:00.000Z",
                },
            },
        },
        _PRODUCER,
    )
    diff_body = json.loads((_CALC / "model_diff.json").read_text(encoding="utf-8"))
    read_body = json.loads((_CALC / "readback_check.json").read_text(encoding="utf-8"))
    diff = store.put("harness.model_diff/1", diff_body, _PRODUCER)
    readback = store.put("harness.readback_check/1", read_body, _PRODUCER)
    verdicts = store.put(
        "verdicts.set/1",
        {
            "verdicts": [
                {
                    "source": "host",
                    "check_id": "steel:stress-ratio",
                    "code": "AISC",
                    "subject": {"kind": "frame", "id": "C1"},
                    "ratio": 1.2,
                    "ratio_limit": 1.0,
                    "status": "FAIL",
                    "governing": True,
                }
            ],
            "traces": [],
            "counts": {"PASS": 0, "FAIL": 1, "NOT_APPLICABLE": 0, "NEEDS_ENGINEER": 0, "ERROR": 0},
            "draft": False,
        },
        _PRODUCER,
    )
    check = store.put(
        "issues.model_check/1",
        {
            "summary": {"errors": 1, "warnings": 0, "infos": 0, "clean": False},
            "issues": [
                {
                    "severity": "error",
                    "code": "FRAME_ZERO_LENGTH",
                    "subject": {"kind": "frame", "id": "B9"},
                    "message": "end points coincide",
                }
            ],
        },
        _PRODUCER,
    )
    drifts = store.put(
        "forces.story_drifts/1",
        {
            "rows": [
                {
                    "story": "S1",
                    "case": {"case": "EQX", "case_type": "load_case", "step": "Max"},
                    "direction": "X",
                    "drift_ratio": 0.004,
                    "point": "J5",
                    "x_mm": 0.0,
                    "y_mm": 0.0,
                    "z_mm": 3000.0,
                }
            ]
        },
        _PRODUCER,
    )
    preview = store.put(
        "harness.approval_preview/1",
        {
            "items": [
                {"id": "i1", "label": "Set section", "refs": []},
                {"id": "i2", "label": "Remove frame", "refs": []},
            ],
            "diff_ref": diff.result_id,
            "models": [{"model_key": "m", "model_id": MODEL, "revision": 2}],
        },
        _PRODUCER,
    )
    empty = store.put("harness.approval_preview/1", {"items": [], "diff_ref": None, "models": []}, _PRODUCER)
    clock = FixedClock(START_MS, 1_000)
    writer = JournalWriter(run_dir, store, clock, ids)

    def add(type_: EventType, payload: dict[str, Any], path: str | None = None) -> None:
        writer.append(type_, payload, path=path, attempt=1 if path else None)

    kinds = EventType
    header = {**_HEADER, "decision_runtime": _RUNTIME if runtime is None else runtime}
    add(kinds.RUN_STARTED, {**header, "input_ref": blob.result_id, "basis_ref": basis.result_id})
    add(kinds.MODEL_SAVED, _saved(1, "fp-1", "rev-1.edb", "revision"))
    add(kinds.MODEL_SAVED, _saved(2, "fp-2", "rev-2.edb", "revision"))
    add(kinds.STEP_STARTED, _step("verdicts"), "0")
    add(kinds.STEP_COMPLETED, _done(verdicts.result_id), "0")
    add(kinds.STEP_STARTED, _step("model_check"), "1")
    add(kinds.STEP_COMPLETED, _done(check.result_id), "1")
    add(kinds.STEP_STARTED, _step("drifts"), "2")
    add(kinds.STEP_COMPLETED, _done(drifts.result_id), "2")
    add(kinds.APPROVAL_REQUESTED, {
        "request_id": "ap1", "kind": "change_set", "title": "Apply", "preview_ref": preview.result_id,
        "shown_sha256": SHA, "binding": {
            "model_key": "m", "model_id": MODEL, "revision": 2, "fingerprint": "fp-bind", "file_sha256": SHA,
        },
        "items": ["i1", "i2"],
    })  # fmt: skip
    add(kinds.APPROVAL_RESOLVED, {
        "request_id": "ap1", "shown_sha256": SHA, "decision": "approve", "rejected_items": ["i2"],
        "item_reasons": {"i2": "too thin <b>x</b>"}, "reason": "keep i1", "by": "engineer:ada",
    })  # fmt: skip
    add(kinds.STEP_STARTED, {**_step("apply_change", effect="write", under="ap1", item="i1")}, "3")
    add(kinds.STEP_COMPLETED, _done(readback.result_id), "3")
    add(kinds.APPROVAL_REQUESTED, {
        "request_id": "ap3", "kind": "change_set", "title": "Again", "preview_ref": empty.result_id,
        "shown_sha256": SHA, "binding": {}, "items": ["i3", "i4"],
    })  # fmt: skip
    add(kinds.APPROVAL_RESOLVED, {
        "request_id": "ap3", "shown_sha256": SHA, "decision": "reject", "rejected_items": ["i3"],
        "item_reasons": {"i3": "thin"}, "reason": "stop", "by": "engineer:ada",
    })  # fmt: skip
    add(kinds.INPUT_REQUESTED, {"request_id": "in1", "kind": "block", "title": "cover", "fields_schema_sha256": SHA})
    add(kinds.INPUT_PROVIDED, {"request_id": "in1", "answer_ref": engineer.result_id, "by": "engineer:ada"})
    add(kinds.DECISION_MADE, {
        "point": "cycle.turn", "options": ["accept", "more_edits"], "choice": "accept",
        "decided_by": "engineer:ada", "confidence": None, "latency_ms": 0, "state_sha256": SHA, "suggestions": [],
    })  # fmt: skip
    add(kinds.RUN_ESCALATED, {
        "reason": "needs_reconciliation", "detail": "host moved", "evidence": [], "request_id": None,
    })  # fmt: skip
    add(kinds.STEP_RECONCILED, {"op_id": "op1", "outcome": "applied", "decided_by": "engineer:ada", "evidence": []})
    add(kinds.RUN_RESUMED, {"resume_no": 1, "code_hash_changed": False, "servers": []})
    add(kinds.MODEL_SAVED, _saved(
        3, "fp-promoted", "promoted.edb", "promoted", origin_sha256=SHA, origin_file_names=["original.edb"],
    ))  # fmt: skip
    add(kinds.APPROVAL_REQUESTED, {
        "request_id": "ap2", "kind": "promotion", "title": "Promote", "preview_ref": empty.result_id,
        "shown_sha256": SHA, "binding": {}, "items": [],
    })  # fmt: skip
    add(kinds.APPROVAL_RESOLVED, {
        "request_id": "ap2", "shown_sha256": SHA, "decision": "approve", "rejected_items": [], "by": "engineer:ada",
    })  # fmt: skip
    writer.close()
    reader = JournalReader(run_dir)
    return SectionsRun(fold_report(reader, store), reader)


def test_report_snapshot(run_dir: Path, store: ResultStore, ids: SeededIdSource) -> None:
    """AC51: the fixture run report matches the snapshot."""
    from eng_contract.ids import FixedClock

    from eng_harness import __version__
    from eng_harness.report import ReleaseMarks, build_report

    run = load_sections_run(run_dir, store, ids)
    clock = FixedClock(START_MS, 1_000)
    try:
        assert [saved.saved.role for saved in run.reader.models()] == ["revision", "revision", "promoted"]
        assert [item.resume_no for item in run.model.resumes] == [1]
        assert len(run.model.decisions) == 1
        html = build_report(run.reader, store, ReleaseMarks(records={}), clock, __version__)
        headings = ("Status", "Changes", "Results summary", "Sources", "Decisions", "Timings", "Run events")
        places = [html.index(f"<h2>{title}</h2>") for title in headings]
        assert places == sorted(places)
        assert html == SNAPSHOT.read_text(encoding="utf-8")
    finally:
        run.close()


def _status_html(run_dir: Path, store: ResultStore, ids: SeededIdSource, runtime: dict[str, Any]) -> str:
    from eng_contract.ids import FixedClock

    from eng_harness import __version__
    from eng_harness.report import ReleaseMarks, build_report

    run = load_sections_run(run_dir, store, ids, runtime)
    try:
        html = build_report(run.reader, store, ReleaseMarks(records={}), FixedClock(START_MS, 1_000), __version__)
    finally:
        run.close()
    return section(html, "Status", "Changes")


def test_status_decision_runtime_caps(run_dir: Path, store: ResultStore, ids: SeededIdSource, tmp_path: Path) -> None:
    """Spec 4.6.1: at most 200 rows, then one "N more" row; deeper entries count as omitted; empty adds nothing."""
    deep = {"a": {"b": {"c": {"d": {"e": 1, "f": 2}}}}}
    status = _status_html(run_dir, store, ids, {"p": {f"k{i}": i for i in range(205)}, **deep})
    assert status.count("Decision runtime /") == 200
    assert '<td><bdi dir="auto">7 more</bdi></td>' in status
    assert "/p/k0<" in status
    assert "/a/b/c/d" not in status
    empty_dir = tmp_path / "runs" / f"run_{ids.new_ulid()}"
    empty_dir.mkdir(parents=True)
    assert "Decision runtime" not in _status_html(empty_dir, store, ids, {})
