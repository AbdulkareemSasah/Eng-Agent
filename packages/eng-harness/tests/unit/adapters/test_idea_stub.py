"""Stub markers of IDEA calculate replies (plan 0014 T5; spec 0014 AC11)."""

from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.adapters.idea import _stub as idea_stub


def _rest_ok(**changes: Any) -> dict[str, Any]:
    """A live REST check reply with no stub marker (spec 0014 AC11, fake success shape)."""
    body: dict[str, Any] = {
        "route": "rest",
        "backend": "rest",
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
                        "check_value": 35.0,
                        "check_status": True,
                        "skipped": False,
                        "message": "OK",
                        "load_case_id": None,
                    }
                ],
                "errors": [],
                "warnings": [],
            }
        ],
    }
    body.update(changes)
    return body


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        pytest.param({**_rest_ok(), "offline_stub": True}, "offline_stub true", id="offline_stub_true"),
        pytest.param(
            {k: v for k, v in _rest_ok().items() if k != "offline_stub"},
            "offline_stub absent",
            id="offline_stub_absent",
        ),
        pytest.param({**_rest_ok(), "backend": "file"}, "backend file", id="backend_file"),
        pytest.param(
            {**_rest_ok(), "notice": "REST service unreachable; returning offline stub summary."},
            "notice present",
            id="notice",
        ),
        pytest.param(
            {
                **_rest_ok(),
                "connections": [
                    {
                        "connection_id": 1,
                        "name": "CON1",
                        "passed": True,
                        "calculated": True,
                        "checks": [
                            {
                                "name": "Plates",
                                "check_value": 35.0,
                                "check_status": True,
                                "skipped": False,
                                "message": "Offline stub.",
                                "unity_check_message": "Offline stub.",
                                "load_case_id": None,
                            }
                        ],
                        "errors": [],
                        "warnings": [],
                    }
                ],
            },
            "unity_check_message Offline stub.",
            id="unity_check_message",
        ),
    ],
)
def test_stub_markers(reply: dict[str, Any], reason: str) -> None:
    """AC11: each stub marker is detected and refused as HOST_ERROR OFFLINE_STUB; a clean reply is not."""
    assert idea_stub.is_stub_reply(reply), reason
    with pytest.raises(ContractError) as caught:
        idea_stub.refuse_stub(reply, host_method="idea_calculate")
    assert caught.value.detail.code is ErrorCode.HOST_ERROR
    assert caught.value.detail.host_code == "OFFLINE_STUB"
    assert caught.value.detail.host_method == "idea_calculate"
    assert caught.value.detail.retryable is False
    assert caught.value.detail.message == "the host reply is an offline stub; no verdict is produced"

    clean = _rest_ok()
    assert idea_stub.is_stub_reply(clean) is False
    idea_stub.refuse_stub(clean, host_method="idea_calculate")  # does not raise

    native = {
        "route": "native",
        "backend": None,
        "offline_stub": False,
        "connections": clean["connections"],
    }
    assert idea_stub.is_stub_reply(native) is False
    idea_stub.refuse_stub(native, host_method="idea_native_calculate")


def test_stub_markers_skip_non_mapping_connection() -> None:
    """AC11: a non-mapping connection is skipped; a later Offline-stub check is still refused."""
    reply = _rest_ok(
        connections=[
            "not-a-connection",
            {
                "connection_id": 1,
                "name": "CON1",
                "passed": True,
                "calculated": True,
                "checks": [
                    {
                        "name": "Plates",
                        "check_value": 35.0,
                        "check_status": True,
                        "skipped": False,
                        "message": "Offline stub.",
                        "unity_check_message": idea_stub.OFFLINE_STUB_MESSAGE,
                        "load_case_id": None,
                    }
                ],
                "errors": [],
                "warnings": [],
            },
        ]
    )
    assert idea_stub.is_stub_reply(reply) is True
    with pytest.raises(ContractError) as caught:
        idea_stub.refuse_stub(reply, host_method="idea_get_check_results")
    assert caught.value.detail.host_code == "OFFLINE_STUB"
    assert caught.value.detail.message == "the host reply is an offline stub; no verdict is produced"
    assert caught.value.detail.host_method == "idea_get_check_results"
