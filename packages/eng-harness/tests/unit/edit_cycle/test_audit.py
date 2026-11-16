"""The A3 value-source audit over a scripted journal (plan 0007 T10; spec 0007 section 4.9, AC25 unit part).

The engineering parameter names are passed explicitly: a forged literal at a listed parameter is reported, a literal at
an unlisted one is not.
"""

from pathlib import Path
from typing import Any

from eng_contract.ids import IdSource
from eng_contract.store import ResultStore
from fixtures.report_run import HEADER, SHA

from eng_harness.journal import EventType, JournalReader

from .journal_script import PRODUCER, Script

_PARAMS = {"csi_frame_section": frozenset({"depth_mm", "width_mm"}), "csi_other": frozenset({"depth_mm"})}


def _basis(store: ResultStore, kind: str, field: str) -> dict[str, str]:
    body = {"value": 300, "unit": "mm", "source": "template:t@1", "confirmed": True, "citation": "c"}
    payload: dict[str, Any] = {"template": {"name": "t", "version": "1", "sha256": SHA}, "fields": {field: body}}
    if kind == "basis.engineer_input/1":
        payload = {
            "step": "1",
            "fields": {
                field: {"value": 300, "unit": "mm", "entered_by": "x", "entered_at": "2026-01-01T00:00:00.000Z"}
            },
        }
    return {"$ref": f"{store.put(kind, payload, PRODUCER).result_id}#/fields/{field}/value"}


def test_audit_finds_literal(run_dir: Path, store: ResultStore, ids: IdSource) -> None:
    """Only a write step's literal (or non-basis reference) at a listed engineering parameter is a finding."""
    from eng_harness.report._edit_cycle import SourceFinding, audit_value_sources

    s = Script(run_dir, store, ids)
    s.at(0, EventType.RUN_STARTED, {**HEADER, "input_ref": s.base, "basis_ref": s.base})
    design = _basis(store, "basis.design_basis/1", "geometry.depth_mm")
    entered = _basis(store, "basis.engineer_input/1", "geometry.width_mm")
    blob = {"$ref": f"{s.base}#/value"}
    write: dict[str, Any] = {"effect": "write"}
    s.step(
        "0", "tool", "csi_frame_section", 1, 10, **write, args={"model": "m", "depth_mm": design, "width_mm": entered}
    )
    s.step("1", "tool", "csi_frame_section", 2, 10, **write, args={"model": "m", "depth_mm": 300, "width_mm": entered})
    s.step(
        "2", "tool", "csi_frame_section", 3, 10, **write, args={"frames": ["B1"], "depth_mm": blob, "width_mm": 250.5}
    )
    s.step("3", "tool", "csi_frame_section", 4, 10, args={"depth_mm": 300})
    s.step("4", "tool", "csi_unlisted", 5, 10, **write, args={"depth_mm": 300})
    s.step("5", "tool", "csi_other", 6, 10, **write, args={"depth_mm": [design, 20], "width_mm": 1})
    s.step("6", "tool", "csi_other", 7, 10, **write, args={"depth_mm": None})
    s.step("7", "calc", "csi_frame_section", 8, 10, **write, args={"depth_mm": 300})
    long = {"model": "m", "depth_mm": 301, "note": "x" * 5000}
    s.step("8", "tool", "csi_frame_section", 9, 10, **write, args=long)
    gone = {"$ref": "res_" + "0" * 26}
    s.step("9", "tool", "csi_frame_section", 10, 10, **write, args={"depth_mm": gone})
    s.writer.close()
    found = audit_value_sources(JournalReader(run_dir), store, _PARAMS)
    assert found == [
        SourceFinding("1", "csi_frame_section", "depth_mm"),
        SourceFinding("2", "csi_frame_section", "depth_mm"),
        SourceFinding("2", "csi_frame_section", "width_mm"),
        SourceFinding("5", "csi_other", "depth_mm"),
        SourceFinding("8", "csi_frame_section", "depth_mm"),
        SourceFinding("9", "csi_frame_section", "depth_mm"),
    ]
    assert audit_value_sources(JournalReader(run_dir), store, {}) == []
