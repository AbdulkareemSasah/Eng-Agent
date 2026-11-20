"""Revit read-back and `check_model` (plan 0011 T9; spec 0011 AC19, sections 4.4, 4.8).

Writes record expected items; `check_model` reads them back with the §4.4 tools. Tolerance is the frozen
basis field `checks.readback_relative_tolerance_ratio` handed to `ReadBack` (never a constant here).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from eng_contract.envelope import HostInfo, SuccessEnvelope
from eng_contract.store import ResultStore

from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters.revit._checks import ReadBack, WrittenItems, check_model, expect_write
from eng_harness.adapters.revit._edits import build_edit_args, send_attended_write
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect, ServerManager

from . import _revit_edit_helpers as helpers

SHA = "d" * 64
CHECK = ServerCheck(
    server="revit",
    build="0123456789ab+fedcba987654",
    min_build="",
    fingerprint=SHA,
    expected_fingerprint=SHA,
    ok=True,
    reason=None,
)
TOLERANCE = 0.001  # test input: the value a workflow's frozen basis would hand over
HOST = HostInfo(program="revit", version="2026", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0)


def _issues(envelope: Any) -> list[tuple[str, str, str, str]]:
    assert isinstance(envelope, SuccessEnvelope)
    data: Any = envelope.data
    return [(i["severity"], i["code"], i["subject"]["kind"], i["subject"]["id"]) for i in data["issues"]]


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
                        "guid": "11111111-1111-1111-1111-111111111111",
                    }
                ],
            }
        },
        "types": {
            2001: {
                "family": helpers.FAMILY,
                "name": "C300x300",
                "family_id": 1001,
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
        "family_type_names": {helpers.FAMILY: {"C300x300"}},
    }


def test_commit_unchecked_detected(tmp_path: Path, store: ResultStore) -> None:
    """AC19: success reply with fault commit_unchecked → check_model READBACK_MISMATCH."""
    control = tmp_path / "control.json"
    config = helpers.revit_config(
        tmp_path,
        control,
        faults=[{"fault": "commit_unchecked", "tool": "revit_set_element_parameter_values"}],
    )

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        ledger = WriteLedger(tmp_path / "run")
        written = WrittenItems()
        read_back = ReadBack(written=written, store=store, check=CHECK, tolerance_ratio=TOLERANCE)
        target = await helpers.warm_bound_target(manager, launcher)
        key = "m1"

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
        written.prepare(key, expect_write("revit_set_element_parameter_values", args, unique_id="col-3001"))
        await send_attended_write(
            call,
            ledger,
            tool="revit_set_element_parameter_values",
            host_args=args,
            op_id="op-commit-unchecked",
            bound_path=helpers.BOUND,
            references={3001: "col-3001"},
            element_ids=[3001],
            target=target,
            call_timeout_s=90,
        )
        written.commit(key)

        envelope = await check_model(call, read_back, key, host=HOST, pre_image_warnings=[])
        codes = [i for i in _issues(envelope) if i[1] == "READBACK_MISMATCH"]
        assert codes, _issues(envelope)
        assert codes[0][0] == "error"

    helpers.run_scenario(tmp_path, config, body)


def test_mismatch(tmp_path: Path, store: ResultStore) -> None:
    """AC19: written value then changed behind the harness → READBACK_MISMATCH; clean when equal."""
    control = tmp_path / "control.json"
    config = helpers.revit_config(tmp_path, control)

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        ledger = WriteLedger(tmp_path / "run")
        written = WrittenItems()
        read_back = ReadBack(written=written, store=store, check=CHECK, tolerance_ratio=TOLERANCE)
        target = await helpers.warm_bound_target(manager, launcher)
        key = "m1"

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
        written.prepare(key, expect_write("revit_set_element_parameter_values", args, unique_id="col-3001"))
        await send_attended_write(
            call,
            ledger,
            tool="revit_set_element_parameter_values",
            host_args=args,
            op_id="op-match",
            bound_path=helpers.BOUND,
            references={3001: "col-3001"},
            element_ids=[3001],
            target=target,
            call_timeout_s=90,
        )
        written.commit(key)

        clean = await check_model(call, read_back, key, host=HOST, pre_image_warnings=[])
        assert [i for i in _issues(clean) if i[1] == "READBACK_MISMATCH"] == []

        # Engineer changes the value behind the harness (same book re-recorded).
        written.prepare(key, expect_write("revit_set_element_parameter_values", args, unique_id="col-3001"))
        written.commit(key)
        await helpers.call_dump(
            manager,
            "revit_set_element_parameter_values",
            {
                "elementIds": [3001],
                "parameterName": "b",
                "value": "999.0",
                "valueType": "double",
            },
            CallEffect.WRITE,
            role="write",
        )
        bad = await check_model(call, read_back, key, host=HOST, pre_image_warnings=[])
        assert [i for i in _issues(bad) if i[1] == "READBACK_MISMATCH"]

    helpers.run_scenario(tmp_path, config, body)


def test_check_model_issues(tmp_path: Path, store: ResultStore) -> None:
    """AC19: ELEMENT_MISSING after element_replaced; REVIT_WARNINGS_INCREASED; MODEL_UNSAVED info."""
    seed = helpers.seed_model()
    seed["warnings"] = [{"type": "Unconnected", "count": 1}]
    control = tmp_path / "control.json"
    config = helpers.revit_config(
        tmp_path,
        control,
        seed=seed,
        faults=[{"fault": "element_replaced", "tool": "revit_change_element_type"}],
    )

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        ledger = WriteLedger(tmp_path / "run")
        written = WrittenItems()
        read_back = ReadBack(written=written, store=store, check=CHECK, tolerance_ratio=TOLERANCE)
        target = await helpers.warm_bound_target(manager, launcher)
        key = "m1"

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await helpers.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        # Pre-image has no warnings; the seed already carries some → REVIT_WARNINGS_INCREASED.
        pre_warnings: list[dict[str, Any]] = []
        # Duplicate a type then assign it so element_replaced can fire on change_element_type.
        dup_args = build_edit_args(
            "duplicate_family_type",
            source_type_id=2001,
            new_type_name="C450x450",
            prior=_prior(),
        )
        await send_attended_write(
            call,
            ledger,
            tool="revit_duplicate_family_type",
            host_args=dup_args,
            op_id="op-dup",
            bound_path=helpers.BOUND,
            references={},
            element_ids=None,
            target=target,
            call_timeout_s=90,
        )
        # Discover the new type id from the family list (second read-back tool of §4.4).
        listed = await helpers.call_dump(
            manager,
            "revit_list_family_types_in_family",
            {"family_name": helpers.FAMILY},
            CallEffect.READ,
            role="read",
        )
        from eng_harness.adapters.revit._replies import parse_revit_reply

        types = parse_revit_reply(listed).body.get("items") or parse_revit_reply(listed).body.get("types") or []
        new_type = next(t for t in types if isinstance(t, dict) and t.get("name") == "C450x450")
        new_type_id = int(new_type["type_id"])

        change_args = build_edit_args(
            "change_element_type",
            element_ids=[3001],
            type_id=new_type_id,
            prior=_prior(),
        )
        written.prepare(
            key,
            expect_write("revit_change_element_type", change_args, unique_id="col-3001"),
        )
        await send_attended_write(
            call,
            ledger,
            tool="revit_change_element_type",
            host_args=change_args,
            op_id="op-replaced",
            bound_path=helpers.BOUND,
            references={3001: "col-3001"},
            element_ids=[3001],
            target=target,
            call_timeout_s=90,
        )
        written.commit(key)

        envelope = await check_model(
            call,
            read_back,
            key,
            host=HOST,
            pre_image_warnings=pre_warnings,
            ledger_unique_ids=["col-3001"],
        )
        found = _issues(envelope)
        codes = {i[1] for i in found}
        assert "ELEMENT_MISSING" in codes, found
        assert "REVIT_WARNINGS_INCREASED" in codes, found
        assert "MODEL_UNSAVED" in codes, found
        assert any(i[0] == "info" and i[1] == "MODEL_UNSAVED" for i in found)
        assert any(i[0] == "warning" and i[1] == "REVIT_WARNINGS_INCREASED" for i in found)
        assert any(i[0] == "error" and i[1] == "ELEMENT_MISSING" for i in found)

    helpers.run_scenario(tmp_path, config, body)
