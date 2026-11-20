"""Revit unique_id check before a write (plan 0011 T8; spec 0011 AC12)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters.revit._edits import prepare_and_send_write
from eng_harness.servers import CallEffect, ServerManager

from . import _revit_edit_helpers as helpers


def test_unique_id_verified_before_write(tmp_path: Path) -> None:
    """AC12: get_element_details uniqueId must match the reference; mismatch is CONFLICT and nothing is sent."""
    # Seed element 3001 as col-3001; the caller claims unique_id col-OTHER.
    control = tmp_path / "control.json"
    config = helpers.revit_config(tmp_path, control)

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        ledger = WriteLedger(tmp_path / "run")
        writes: list[str] = []

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if effect is CallEffect.WRITE:
                writes.append(tool)
            return await helpers.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        host_args = {
            "elementIds": [3001],
            "parameterName": "b",
            "value": "350.0",
            "valueType": "double",
        }
        with pytest.raises(ContractError) as mismatch:
            await prepare_and_send_write(
                call,
                ledger,
                tool="revit_set_element_parameter_values",
                host_args=host_args,
                op_id="op-id-mismatch",
                bound_path=helpers.BOUND,
                references={3001: "col-OTHER"},
                element_ids=[3001],
            )
        assert mismatch.value.detail.code is ErrorCode.CONFLICT
        assert not writes
        assert not ledger.path.exists()

        # Matching unique_id allows the write and ledgers first.
        await prepare_and_send_write(
            call,
            ledger,
            tool="revit_set_element_parameter_values",
            host_args=host_args,
            op_id="op-id-ok",
            bound_path=helpers.BOUND,
            references={3001: "col-3001"},
            element_ids=[3001],
        )
        assert writes == ["revit_set_element_parameter_values"]
        assert ledger.path.exists()

    helpers.run_scenario(tmp_path, config, body)


def test_missing_element_reference_refuses(tmp_path: Path) -> None:
    """AC12: every written element id must have a unique_id reference; omit → refuse, nothing sent."""
    control = tmp_path / "control.json"
    config = helpers.revit_config(tmp_path, control)

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        ledger = WriteLedger(tmp_path / "run")
        writes: list[str] = []

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if effect is CallEffect.WRITE:
                writes.append(tool)
            return await helpers.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        host_args = {
            "elementIds": [3001],
            "parameterName": "b",
            "value": "350.0",
            "valueType": "double",
        }
        with pytest.raises(ContractError) as missing:
            await prepare_and_send_write(
                call,
                ledger,
                tool="revit_set_element_parameter_values",
                host_args=host_args,
                op_id="op-no-ref",
                bound_path=helpers.BOUND,
                references={},  # element 3001 absent
                element_ids=[3001],
            )
        assert missing.value.detail.code is ErrorCode.INVALID_ARGUMENT
        assert missing.value.detail.field == "references"
        assert not writes
        assert not ledger.path.exists()

    helpers.run_scenario(tmp_path, config, body)


def test_ledger_target_is_bound_instance(tmp_path: Path) -> None:
    """Ledger HostTarget.pid is the bound MCP instance pid (spec 0002 §4.5.2), never an invented value."""
    control = tmp_path / "control.json"
    config = helpers.revit_config(tmp_path, control)

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        ledger = WriteLedger(tmp_path / "run")
        target = await helpers.warm_bound_target(manager, launcher)

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await helpers.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        host_args = {
            "elementIds": [3001],
            "parameterName": "b",
            "value": "350.0",
            "valueType": "double",
        }
        # Must ledger the bound HostTarget (opened MCP pid), not a placeholder.
        await prepare_and_send_write(
            call,
            ledger,
            tool="revit_set_element_parameter_values",
            host_args=host_args,
            op_id="op-bound-target",
            bound_path=helpers.BOUND,
            references={3001: "col-3001"},
            element_ids=[3001],
            target=target,
        )
        entry = ledger.find("op-bound-target")
        assert entry is not None
        assert entry.target.product == "revit"
        assert entry.target.pid == target.pid
        assert entry.target.pid == launcher.started[0].pid

    helpers.run_scenario(tmp_path, config, body)
