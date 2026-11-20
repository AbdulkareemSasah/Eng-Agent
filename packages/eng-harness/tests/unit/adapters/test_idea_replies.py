"""IDEA reply helpers and kind payload validation (plan 0014 T5; spec 0014 section 4.5)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from pydantic import ValidationError

from eng_harness.adapters.idea import _replies as idea_replies
from eng_harness.kinds.idea import (
    IDEA_KINDS,
    IdeaCheckRaw,
    IdeaLoads,
    IdeaProject,
    IdeaStatus,
)

_SHA = "a" * 64


def _tool_result(body: object, *, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(body)}], "isError": is_error}


def test_cut_text() -> None:
    """Section 4.5: free texts are cut to 500 characters before storage."""
    short = "ok"
    assert idea_replies.cut_text(short) == short
    long = "x" * (idea_replies.TEXT_LIMIT + 25)
    cut = idea_replies.cut_text(long)
    assert len(cut) == idea_replies.TEXT_LIMIT
    assert cut == long[: idea_replies.TEXT_LIMIT]
    assert idea_replies.cut_text(long, limit=10) == "x" * 10


def test_reduce_paths() -> None:
    """A11 / section 4.5: absolute paths become base names; relative strings stay; texts are cut."""
    payload = {
        "file": "/projects/model.idea",
        "win": r"C:\data\conn.idea",
        "relative": "subdir/file.idea",
        "nested": [{"path": "/data/inner.txt", "note": "y" * 600}],
    }
    reduced = idea_replies.reduce_paths(payload)
    assert reduced["file"] == "model.idea"
    assert reduced["win"] == "conn.idea"
    assert reduced["relative"] == "subdir/file.idea"
    assert reduced["nested"][0]["path"] == "inner.txt"
    assert len(reduced["nested"][0]["note"]) == idea_replies.TEXT_LIMIT


def test_parse_reply_json_success_and_error() -> None:
    """AC12 shape: one JSON object success; any other shape is HOST_ERROR / UNEXPECTED_REPLY."""
    body = {"offline_stub": False, "route": "native", "backend": None, "connections": []}
    parsed = idea_replies.parse_reply_json(_tool_result(body))
    assert parsed["offline_stub"] is False
    assert parsed["connections"] == []

    with pytest.raises(ContractError) as bad:
        idea_replies.parse_reply_json(_tool_result({"code": "boom"}, is_error=True))
    assert bad.value.detail.code is ErrorCode.HOST_ERROR
    assert bad.value.detail.host_code == "boom"


def test_parse_status_project_loads_check_raw() -> None:
    """Section 4.5 kind validators: valid payloads parse; absolute paths reduce; stub check_raw refused."""
    status = idea_replies.parse_status(
        {
            "installed": [{"version": "25.0", "has_rest_api": True, "hidden_calculator": False}],
            "service": {"reachable": True, "service_version": "1"},
            "read_only": False,
            "script_enabled": False,
        }
    )
    assert isinstance(status, IdeaStatus)
    assert status.read_only is False

    project = idea_replies.parse_project(
        {
            "backend": None,
            "service_reachable": True,
            "live_project": True,
            "connections": [{"id": 1, "name": "CON1", "calculated": True}],
        }
    )
    assert isinstance(project, IdeaProject)
    assert project.connections[0].name == "CON1"

    loads = idea_replies.parse_loads(
        {
            "connection": "CON1",
            "effects": [
                {
                    "id": "LE1",
                    "name": "LC1",
                    "check_equilibrium": True,
                    "segments": [
                        {
                            "beam_segment_id": 1,
                            "position_host": 0.0,
                            "N_kN": 1.0,
                            "Qy_kN": 0.0,
                            "Qz_kN": 0.0,
                            "Mx_kNm": 0.0,
                            "My_kNm": 0.0,
                            "Mz_kNm": 0.0,
                        }
                    ],
                }
            ],
            "percentage_segments_present": True,
            "file_sha256": _SHA,
        }
    )
    assert isinstance(loads, IdeaLoads)
    assert loads.file_sha256 == _SHA

    check_raw = idea_replies.parse_check_raw(
        {
            "route": "rest",
            "backend": "/projects/model.idea",
            "offline_stub": False,
            "connections": [
                {
                    "connection_id": 1,
                    "name": "CON1",
                    "passed": True,
                    "calculated": True,
                    "checks": [
                        {
                            "name": "Plates",
                            "check_value": 87.5,
                            "check_status": True,
                            "skipped": False,
                            "message": "OK",
                            "load_case_id": "LC1",
                        }
                    ],
                    "errors": [],
                    "warnings": [],
                }
            ],
        }
    )
    assert isinstance(check_raw, IdeaCheckRaw)
    assert check_raw.backend == "model.idea"
    assert check_raw.offline_stub is False

    with pytest.raises(ContractError) as stub:
        idea_replies.parse_check_raw(
            {
                "route": "rest",
                "backend": "rest",
                "offline_stub": True,
                "connections": [],
            }
        )
    assert stub.value.detail.code is ErrorCode.HOST_ERROR
    assert stub.value.detail.host_code == "UNEXPECTED_REPLY"


def test_idea_kinds_registry_and_forbid_extra() -> None:
    """IDEA_KINDS names the four /1 kinds; models forbid extra fields (section 4.5)."""
    assert set(IDEA_KINDS) == {
        "harness.idea_status/1",
        "harness.idea_project/1",
        "harness.idea_loads/1",
        "harness.idea_check_raw/1",
    }
    with pytest.raises(ValidationError):
        IdeaStatus.model_validate(
            {
                "installed": [],
                "service": {"reachable": False},
                "read_only": False,
                "script_enabled": False,
                "extra": True,
            }
        )
