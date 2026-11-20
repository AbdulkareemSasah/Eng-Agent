"""Revit reply parsing: _warning, truncated, RESPONSE_TOO_LARGE (plan 0011 T5; spec 0011 AC5, §4.5)."""

import json

import pytest
from eng_contract.errors import ContractError, ErrorCode, WarningCode


def _tool_result(body: dict[str, object] | str, *, is_error: bool = False) -> dict[str, object]:
    text = body if isinstance(body, str) else json.dumps(body)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def test_parse_warning_truncated() -> None:
    # AC5: extract_raw_reply; _warning → contract warning (not data); truncated → complete false + PARTIAL_DATA;
    # RESPONSE_TOO_LARGE → LIMIT_EXCEEDED with the narrowing hint (spec 0011 §4.5, §4.7).
    from eng_harness.adapters.revit._replies import parse_revit_reply

    warned = parse_revit_reply(
        _tool_result({"items": [1, 2], "count": 2, "_warning": "reply exceeded soft limit; truncated fields omitted"})
    )
    assert "_warning" not in warned.body
    assert warned.body == {"items": [1, 2], "count": 2}
    assert warned.complete is True
    assert len(warned.warnings) == 1
    assert warned.warnings[0].code is WarningCode.HOST_WARNING
    assert "soft limit" in warned.warnings[0].message

    truncated = parse_revit_reply(_tool_result({"items": list(range(5)), "count": 5, "truncated": True}))
    assert truncated.complete is False
    assert any(w.code is WarningCode.PARTIAL_DATA for w in truncated.warnings)

    with pytest.raises(ContractError) as raised:
        parse_revit_reply(_tool_result("RESPONSE_TOO_LARGE: the reply exceeded the transport limit.", is_error=True))
    assert raised.value.detail.code is ErrorCode.LIMIT_EXCEEDED
    assert raised.value.detail.hint is not None
    assert "narrow" in raised.value.detail.hint.lower()
