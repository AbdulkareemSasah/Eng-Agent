"""Revit active-document check before a write (plan 0011 T8; spec 0011 AC13)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode, Precondition

from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters.revit._edits import prepare_and_send_write
from eng_harness.servers import CallEffect

from . import _revit_edit_helpers as helpers


def test_active_document_checked(tmp_path: Path) -> None:
    """AC13: after the working copy is bound, metadata path must equal the bound path or PRECONDITION_FAILED."""
    other = r"C:\models\other.rvt"
    host_args = {
        "elementIds": [3001],
        "parameterName": "b",
        "value": "350.0",
        "valueType": "double",
    }

    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    control_bad = bad_dir / "control.json"
    config_bad = helpers.revit_config(
        bad_dir,
        control_bad,
        seed=helpers.seed_model(active_path=other, document_path=other),
    )

    async def body_bad(manager) -> None:
        ledger = WriteLedger(bad_dir / "run-ledger")
        writes: list[str] = []

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if effect is CallEffect.WRITE:
                writes.append(tool)
            return await helpers.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        with pytest.raises(ContractError) as wrong:
            await prepare_and_send_write(
                call,
                ledger,
                tool="revit_set_element_parameter_values",
                host_args=host_args,
                op_id="op-active-bad",
                bound_path=helpers.BOUND,
                references={3001: "col-3001"},
                element_ids=[3001],
            )
        assert wrong.value.detail.code is ErrorCode.PRECONDITION_FAILED
        assert wrong.value.detail.precondition is Precondition.model_open
        assert not writes
        assert not ledger.path.exists()

    helpers.run_scenario(bad_dir, config_bad, body_bad)

    ok_dir = tmp_path / "ok"
    ok_dir.mkdir()
    control_ok = ok_dir / "control.json"
    config_ok = helpers.revit_config(ok_dir, control_ok, seed=helpers.seed_model())

    async def body_ok(manager) -> None:
        ledger = WriteLedger(ok_dir / "run-ledger")
        writes: list[str] = []

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if effect is CallEffect.WRITE:
                writes.append(tool)
            return await helpers.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        await prepare_and_send_write(
            call,
            ledger,
            tool="revit_set_element_parameter_values",
            host_args=host_args,
            op_id="op-active-ok",
            bound_path=helpers.BOUND,
            references={3001: "col-3001"},
            element_ids=[3001],
        )
        assert writes == ["revit_set_element_parameter_values"]

    helpers.run_scenario(ok_dir, config_ok, body_ok)
