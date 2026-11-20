"""Revit attended write dialog outcomes (plan 0011 T9; spec 0011 AC18, sections 4.2 rule 1, 4.7).

Writes go through `send_attended_write` on the write role (`attended` class). Declined and unanswered dialogs
are faults of the synthetic fake; the unanswered case is tested twice: write timeout above the add-in deadline
(`HOST_BUSY` / `MODAL_DIALOG`) and below it (`TIMEOUT_UNKNOWN_OUTCOME`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters.revit._edits import build_edit_args, send_attended_write
from eng_harness.adapters.revit._errors import write_certainty
from eng_harness.servers import CallEffect, ServerManager

from . import _revit_edit_helpers as helpers

# Spec 0011 section 4.2 rule 1 / E/Runtime/MainThreadRequestQueue.cs:25 (doctor cites the same 60 s).
_ADDIN_DEADLINE_S = 60


def _prior() -> dict[str, Any]:
    return {
        "elements": {
            3001: {
                "unique_id": "col-3001",
                "parameters": [
                    {
                        "name": "b",
                        "storageType": "Double",
                        "specId": helpers.LENGTH_SPEC,
                        "isReadOnly": False,
                    }
                ],
            }
        },
        "types": {
            2001: {
                "family": helpers.FAMILY,
                "name": "C300x300",
                "instance_ids": [3001],
                "parameters": [
                    {
                        "name": "b",
                        "storageType": "Double",
                        "specId": helpers.LENGTH_SPEC,
                        "isReadOnly": False,
                    }
                ],
            }
        },
    }


def test_declined_not_applied(tmp_path: Path) -> None:
    """AC18: fault dialog_declined → CONFIRMATION_REQUIRED, certain not applied, never retried, model unchanged."""
    control = tmp_path / "control.json"
    config = helpers.revit_config(
        tmp_path,
        control,
        faults=[{"fault": "dialog_declined", "tool": "revit_set_element_parameter_values"}],
    )

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        ledger = WriteLedger(tmp_path / "run")
        target = await helpers.warm_bound_target(manager, launcher)
        writes = 0

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            nonlocal writes
            if effect is CallEffect.WRITE:
                writes += 1
            return await helpers.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        args = build_edit_args(
            "set_element_parameter_values",
            element_ids=[3001],
            parameter_name="b",
            value_mm=450.0,
            prior=_prior(),
        )
        with pytest.raises(ContractError) as raised:
            await send_attended_write(
                call,
                ledger,
                tool="revit_set_element_parameter_values",
                host_args=args,
                op_id="op-declined",
                bound_path=helpers.BOUND,
                references={3001: "col-3001"},
                element_ids=[3001],
                target=target,
                call_timeout_s=90,
            )
        detail = raised.value.detail
        assert detail.code is ErrorCode.CONFIRMATION_REQUIRED
        assert "declined in Revit" in detail.message
        assert detail.retryable is False
        assert write_certainty(detail) == "not_applied"
        assert writes == 1  # one attempt; never retried

        # Model unchanged: b still 1.0 ft raw.
        params = await helpers.call_dump(
            manager, "revit_get_element_parameters", {"elementIds": [3001]}, CallEffect.READ, role="read"
        )
        from eng_harness.adapters.revit._replies import parse_revit_reply

        parsed = parse_revit_reply(params).body
        items = parsed["items"]
        assert isinstance(items, list) and items
        row = next(p for p in items[0]["parameters"] if p.get("name") == "b")  # type: ignore[index]
        raw = row.get("rawValue", row.get("value"))
        assert float(raw) == pytest.approx(helpers.B_FT)

    helpers.run_scenario(tmp_path, config, body)


def test_unanswered_is_busy(tmp_path: Path) -> None:
    """AC18: dialog_unanswered with write timeout above the add-in deadline → HOST_BUSY / MODAL_DIALOG."""
    control = tmp_path / "control.json"
    assert 90 > _ADDIN_DEADLINE_S
    config = helpers.revit_config(
        tmp_path,
        control,
        faults=[
            {
                "fault": "dialog_unanswered",
                "tool": "revit_set_element_parameter_values",
                "reply": "busy",
            }
        ],
    )

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        ledger = WriteLedger(tmp_path / "run")
        target = await helpers.warm_bound_target(manager, launcher)

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await helpers.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        args = build_edit_args(
            "set_element_parameter_values",
            element_ids=[3001],
            parameter_name="b",
            value_mm=450.0,
            prior=_prior(),
        )
        with pytest.raises(ContractError) as raised:
            await send_attended_write(
                call,
                ledger,
                tool="revit_set_element_parameter_values",
                host_args=args,
                op_id="op-unanswered-busy",
                bound_path=helpers.BOUND,
                references={3001: "col-3001"},
                element_ids=[3001],
                target=target,
                call_timeout_s=90,
            )
        detail = raised.value.detail
        assert detail.code is ErrorCode.HOST_BUSY
        assert detail.host_code == "MODAL_DIALOG"
        assert write_certainty(detail) == "not_applied"

        params = await helpers.call_dump(
            manager, "revit_get_element_parameters", {"elementIds": [3001]}, CallEffect.READ, role="read"
        )
        from eng_harness.adapters.revit._replies import parse_revit_reply

        parsed = parse_revit_reply(params).body
        items = parsed["items"]
        assert isinstance(items, list) and items
        row = next(p for p in items[0]["parameters"] if p.get("name") == "b")  # type: ignore[index]
        raw = row.get("rawValue", row.get("value"))
        assert float(raw) == pytest.approx(helpers.B_FT)

    helpers.run_scenario(tmp_path, config, body)


def test_short_timeout_is_unknown(tmp_path: Path) -> None:
    """AC18: dialog_unanswered with write timeout below the add-in deadline → TIMEOUT_UNKNOWN_OUTCOME."""
    control = tmp_path / "control.json"
    short = 2
    assert short < _ADDIN_DEADLINE_S
    # Short client timeout: fake withholds longer than the role backstop so the session times out.
    config = helpers.revit_config(
        tmp_path,
        control,
        faults=[
            {
                "fault": "dialog_unanswered",
                "tool": "revit_set_element_parameter_values",
                "seconds": 5.0,
            }
        ],
    )
    # Override write role timeout below the add-in deadline (spec 0011 §4.2 rule 1).
    section = config.servers["revit"]
    roles = dict(section.roles)
    roles["write"] = roles["write"].model_copy(update={"call_timeout_s": short})
    config = config.model_copy(
        update={
            "servers": {
                **config.servers,
                "revit": section.model_copy(update={"roles": roles, "client_grace_s": 1}),
            }
        }
    )

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        ledger = WriteLedger(tmp_path / "run")
        target = await helpers.warm_bound_target(manager, launcher)

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await helpers.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        args = build_edit_args(
            "set_element_parameter_values",
            element_ids=[3001],
            parameter_name="b",
            value_mm=450.0,
            prior=_prior(),
        )
        with pytest.raises(ContractError) as raised:
            await send_attended_write(
                call,
                ledger,
                tool="revit_set_element_parameter_values",
                host_args=args,
                op_id="op-unanswered-short",
                bound_path=helpers.BOUND,
                references={3001: "col-3001"},
                element_ids=[3001],
                target=target,
                call_timeout_s=short,
            )
        detail = raised.value.detail
        assert detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME
        assert write_certainty(detail) == "unknown"

    helpers.run_scenario(tmp_path, config, body)
