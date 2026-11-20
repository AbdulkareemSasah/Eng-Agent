"""Revit active-document check before a write (plan 0011 T8; spec 0011 AC13)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode, Precondition

from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters.revit._edits import prepare_and_send_write
from eng_harness.servers import CallEffect

from . import _revit_edit_helpers as H


def test_active_document_checked(tmp_path: Path) -> None:
    """AC13: after the working copy is bound, metadata path must equal the bound path or PRECONDITION_FAILED."""
    other = r"C:\models\other.rvt"
    control = tmp_path / "control.json"
    # Active document is another file; bound working copy is H.BOUND.
    config = H.revit_config(
        tmp_path,
        control,
        seed=H.seed_model(active_path=other, document_path=other),
    )

    async def body(manager) -> None:
        ledger = WriteLedger(tmp_path / "run")
        writes: list[str] = []

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if effect is CallEffect.WRITE:
                writes.append(tool)
            return await H.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        host_args = {
            "elementIds": [3001],
            "parameterName": "b",
            "value": "350.0",
            "valueType": "double",
        }
        with pytest.raises(ContractError) as wrong:
            await prepare_and_send_write(
                call,
                ledger,
                tool="revit_set_element_parameter_values",
                host_args=host_args,
                op_id="op-active-bad",
                bound_path=H.BOUND,
                references={3001: "col-3001"},
                element_ids=[3001],
            )
        assert wrong.value.detail.code is ErrorCode.PRECONDITION_FAILED
        assert wrong.value.detail.precondition is Precondition.model_open
        assert not writes
        assert not ledger.path.exists()

        # When active path equals the bound document, the write proceeds.
        control2 = tmp_path / "control-ok.json"
        config_ok = H.revit_config(tmp_path / "ok", control2, seed=H.seed_model())

        async def body_ok(manager_ok) -> None:
            ledger_ok = WriteLedger(tmp_path / "ok-run")
            writes_ok: list[str] = []

            async def call_ok(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
                if effect is CallEffect.WRITE:
                    writes_ok.append(tool)
                return await H.call_dump(
                    manager_ok, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
                )

            await prepare_and_send_write(
                call_ok,
                ledger_ok,
                tool="revit_set_element_parameter_values",
                host_args=host_args,
                op_id="op-active-ok",
                bound_path=H.BOUND,
                references={3001: "col-3001"},
                element_ids=[3001],
            )
            assert writes_ok == ["revit_set_element_parameter_values"]

        H.run_scenario(tmp_path / "ok", config_ok, body_ok)

    H.run_scenario(tmp_path, config, body)
