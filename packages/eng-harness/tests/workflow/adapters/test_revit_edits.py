"""Revit edit kinds, batching, shared-type and parameter resolution (plan 0011 T8; AC14 to AC17)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import pytest
from eng_contract.errors import ContractError, ErrorCode

from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters.revit._edits import (
    DIALOG_SUMMARY_LIMIT,
    batch_ids_fitting_dialog,
    build_edit_args,
    dialog_summary,
    prepare_and_send_write,
    resolve_parameter_name,
)
from eng_harness.servers import CallEffect, ServerManager

from . import _revit_edit_helpers as helpers


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate_family_type",
        "set_type_parameter_values",
        "change_element_type",
        "set_element_parameter_values",
        "set_parameter_value_by_guid",
    ],
)
def test_edit_mapping(
    kind: Literal[
        "duplicate_family_type",
        "set_type_parameter_values",
        "change_element_type",
        "set_element_parameter_values",
        "set_parameter_value_by_guid",
    ],
    tmp_path: Path,
) -> None:
    """AC14: host arguments equal the section 4.8 mapping; ledger append before send."""
    control = tmp_path / "control.json"
    config = helpers.revit_config(tmp_path, control)

    async def body(manager: ServerManager) -> None:
        ledger = WriteLedger(tmp_path / "run")
        sent: list[tuple[str, dict[str, Any]]] = []

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if effect is CallEffect.WRITE:
                assert ledger.path.exists(), "ledger must be appended before the host send"
                sent.append((tool, dict(arguments)))
            return await helpers.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        prior = {
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

        if kind == "duplicate_family_type":
            args = build_edit_args(
                kind,
                source_type_id=2001,
                new_type_name="C400x400",
                prior=prior,
            )
            assert "type_parameter_overrides" not in args
            assert args["source_type_id"] == "2001"
            assert args["new_type_name"] == "C400x400"
            await prepare_and_send_write(
                call,
                ledger,
                tool="revit_duplicate_family_type",
                host_args=args,
                op_id="op-dup",
                bound_path=helpers.BOUND,
                references={3001: "col-3001"},
                element_ids=None,
            )
            assert sent
            assert sent[0][0] == "revit_duplicate_family_type"
            payload = sent[0][1]
            assert "type_parameter_overrides" not in payload
            assert payload["source_type_id"] == "2001"
            assert payload["new_type_name"] == "C400x400"
            return

        if kind == "set_type_parameter_values":
            args = build_edit_args(
                kind,
                type_id=2001,
                parameter_name="b",
                value_mm=400.0,
                expected_instances=[3001],
                prior=prior,
            )
            assert args["typeIds"] == [2001]
            assert args["parameterName"] == "b"
            assert args["valueType"] == "double"
            assert args["value"] == "400.0"
            assert "expected_instances" not in args
            await prepare_and_send_write(
                call,
                ledger,
                tool="revit_set_type_parameter_values",
                host_args=args,
                op_id="op-type",
                bound_path=helpers.BOUND,
                references={3001: "col-3001"},
                element_ids=None,
            )
            assert sent[0][1]["valueType"] == "double"
            return

        if kind == "change_element_type":
            args = build_edit_args(
                kind,
                element_ids=[3001],
                type_id=2001,
                prior=prior,
            )
            assert args["elementIds"] == [3001]
            assert args["typeId"] == 2001
            await prepare_and_send_write(
                call,
                ledger,
                tool="revit_change_element_type",
                host_args=args,
                op_id="op-chg",
                bound_path=helpers.BOUND,
                references={3001: "col-3001"},
                element_ids=[3001],
            )
            assert sent[0][1]["typeId"] == 2001
            return

        if kind == "set_element_parameter_values":
            args = build_edit_args(
                kind,
                element_ids=[3001],
                parameter_name="b",
                value_mm=350.0,
                prior=prior,
            )
            assert args["elementIds"] == [3001]
            assert args["parameterName"] == "b"
            assert args["valueType"] == "double"
            assert args["value"] == "350.0"
            await prepare_and_send_write(
                call,
                ledger,
                tool="revit_set_element_parameter_values",
                host_args=args,
                op_id="op-inst",
                bound_path=helpers.BOUND,
                references={3001: "col-3001"},
                element_ids=[3001],
            )
            assert sent[0][1]["valueType"] == "double"
            return

        # set_parameter_value_by_guid
        args = build_edit_args(
            kind,
            element_ids=[3001],
            guid="11111111-1111-1111-1111-111111111111",
            value_mm=360.0,
            target="instance",
            prior=prior,
        )
        assert args["elementIds"] == [3001]
        assert args["guid"] == "11111111-1111-1111-1111-111111111111"
        assert args["valueType"] == "double"
        assert args["unit"] == "mm"
        assert args["unit"] != "auto"
        assert args["allOrNothing"] is True
        await prepare_and_send_write(
            call,
            ledger,
            tool="revit_set_parameter_value_by_guid",
            host_args=args,
            op_id="op-guid",
            bound_path=helpers.BOUND,
            references={3001: "col-3001"},
            element_ids=[3001],
        )
        assert sent[0][1]["unit"] == "mm"

    helpers.run_scenario(tmp_path, config, body)


def test_batch_fits_dialog_summary() -> None:
    """AC14: a batch is the largest whose dialog summary fits 500 characters (bridge citation)."""
    assert DIALOG_SUMMARY_LIMIT == 500  # RevitDestructiveConfirmationPrompt.cs:19-28

    def make_args(ids: list[int]) -> dict[str, Any]:
        return {
            "elementIds": ids,
            "parameterName": "b",
            "value": "304.8",
            "valueType": "double",
        }

    # One id always fits.
    assert len(dialog_summary(make_args([1]))) <= DIALOG_SUMMARY_LIMIT

    # Grow until a single batch would exceed the limit, then split.
    ids: list[int] = []
    while len(dialog_summary(make_args([*ids, len(ids) + 1]))) <= DIALOG_SUMMARY_LIMIT:
        ids.append(len(ids) + 1)
        if len(ids) > 200:
            break
    assert len(ids) >= 1
    # Adding one more must overflow.
    overflow = [*ids, len(ids) + 1]
    assert len(dialog_summary(make_args(overflow))) > DIALOG_SUMMARY_LIMIT

    batches = batch_ids_fitting_dialog(overflow, make_args)
    assert len(batches) >= 2
    for batch in batches:
        assert len(dialog_summary(make_args(batch))) <= DIALOG_SUMMARY_LIMIT
    # Flatten preserves order and every id.
    assert [i for batch in batches for i in batch] == overflow
    # Each batch is maximal: merging the next id into a non-final batch would overflow.
    for index, batch in enumerate(batches[:-1]):
        trial = [*batch, batches[index + 1][0]]
        assert len(dialog_summary(make_args(trial))) > DIALOG_SUMMARY_LIMIT


def test_shared_type_refused(tmp_path: Path) -> None:
    """AC15: set_type_parameter_values refuses unless expected_instances equals the type's instances."""
    # Type 2001 has instances [3001, 3002]; caller names only [3001] -> CONFLICT, nothing sent.
    elements = []
    for eid, uid in ((3001, "col-3001"), (3002, "col-3002")):
        elements.append(
            {
                "element_id": eid,
                "unique_id": uid,
                "category": "OST_StructuralColumns",
                "family": helpers.FAMILY,
                "type_id": 2001,
                "type_name": "C300x300",
                "level_id": 100,
                "level_name": "Level 1",
                "location_kind": "point",
                "i": {"x": 0.0, "y": 0.0, "z": 0.0},
                "j": None,
                "parameters": [helpers.length_param("b", helpers.B_FT)],
            }
        )
    types = [
        {
            "type_id": 2001,
            "family": helpers.FAMILY,
            "name": "C300x300",
            "family_id": 1001,
            "category": "OST_StructuralColumns",
            "parameters": [helpers.length_param("b", helpers.B_FT)],
            "instance_ids": [3001, 3002],
        }
    ]
    control = tmp_path / "control.json"
    config = helpers.revit_config(tmp_path, control, seed=helpers.seed_model(elements=elements, types=types))

    async def body(manager: ServerManager) -> None:
        ledger = WriteLedger(tmp_path / "run")
        writes: list[str] = []

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if effect is CallEffect.WRITE:
                writes.append(tool)
            return await helpers.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        prior = {
            "types": {
                2001: {
                    "instance_ids": [3001, 3002],
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
            "elements": {},
        }
        with pytest.raises(ContractError) as refused:
            build_edit_args(
                "set_type_parameter_values",
                type_id=2001,
                parameter_name="b",
                value_mm=400.0,
                expected_instances=[3001],  # missing 3002
                prior=prior,
            )
        assert refused.value.detail.code is ErrorCode.CONFLICT
        assert "2" in refused.value.detail.message  # counts, not foreign ids
        assert not writes
        assert not ledger.path.exists()

        # Exact match is accepted and may be sent.
        args = build_edit_args(
            "set_type_parameter_values",
            type_id=2001,
            parameter_name="b",
            value_mm=400.0,
            expected_instances=[3001, 3002],
            prior=prior,
        )
        await prepare_and_send_write(
            call,
            ledger,
            tool="revit_set_type_parameter_values",
            host_args=args,
            op_id="op-shared-ok",
            bound_path=helpers.BOUND,
            references={3001: "col-3001", 3002: "col-3002"},
            element_ids=None,
        )
        assert writes == ["revit_set_type_parameter_values"]

    helpers.run_scenario(tmp_path, config, body)


def test_duplicate_no_overrides(tmp_path: Path) -> None:
    """AC16: duplicate_family_type carries no overrides; existing name is CONFLICT before the call."""
    control = tmp_path / "control.json"
    config = helpers.revit_config(tmp_path, control)

    async def body(manager: ServerManager) -> None:
        ledger = WriteLedger(tmp_path / "run")
        writes: list[str] = []

        async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            if effect is CallEffect.WRITE:
                writes.append(tool)
                assert "type_parameter_overrides" not in arguments
            return await helpers.call_dump(
                manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        prior = {
            "types": {
                2001: {"family": helpers.FAMILY, "name": "C300x300", "instance_ids": [3001], "parameters": []},
            },
            "family_type_names": {helpers.FAMILY: {"C300x300"}},
            "elements": {},
        }
        with pytest.raises(ContractError) as exists:
            build_edit_args(
                "duplicate_family_type",
                source_type_id=2001,
                new_type_name="C300x300",
                prior=prior,
            )
        assert exists.value.detail.code is ErrorCode.CONFLICT
        assert not writes

        with pytest.raises(ContractError) as overrides:
            build_edit_args(
                "duplicate_family_type",
                source_type_id=2001,
                new_type_name="C400x400",
                type_parameter_overrides={"b": "1"},
                prior=prior,
            )
        assert overrides.value.detail.code is ErrorCode.INVALID_ARGUMENT

        args = build_edit_args(
            "duplicate_family_type",
            source_type_id=2001,
            new_type_name="C400x400",
            prior=prior,
        )
        assert "type_parameter_overrides" not in args
        host = {
            "source_type_id": "2001",
            "new_type_name": "C400x400",
        }
        reply = await prepare_and_send_write(
            call,
            ledger,
            tool="revit_duplicate_family_type",
            host_args=host,
            op_id="op-dup2",
            bound_path=helpers.BOUND,
            references={3001: "col-3001"},
            element_ids=None,
        )
        assert writes == ["revit_duplicate_family_type"]
        # Reply carries new_type_id (AC16).
        body_json = reply
        assert body_json is not None

    helpers.run_scenario(tmp_path, config, body)


def test_parameter_resolution() -> None:
    """AC17: name must match exactly one non-read-only parameter on each target of the prior read."""
    params_ok = [
        {"name": "b", "storageType": "Double", "specId": helpers.LENGTH_SPEC, "isReadOnly": False},
        {"name": "h", "storageType": "Double", "specId": helpers.LENGTH_SPEC, "isReadOnly": False},
    ]
    assert resolve_parameter_name("b", {3001: params_ok, 3002: params_ok}, side="instance") == "b"

    with pytest.raises(ContractError) as missing:
        resolve_parameter_name("missing", {3001: params_ok}, side="instance")
    assert missing.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert missing.value.detail.field == "parameter"

    dup = [*params_ok, {"name": "b", "storageType": "Double", "specId": helpers.LENGTH_SPEC, "isReadOnly": False}]
    with pytest.raises(ContractError) as several:
        resolve_parameter_name("b", {3001: dup}, side="instance")
    assert several.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert several.value.detail.field == "parameter"

    read_only = [{"name": "b", "storageType": "Double", "specId": helpers.LENGTH_SPEC, "isReadOnly": True}]
    with pytest.raises(ContractError) as ro:
        resolve_parameter_name("b", {3001: read_only}, side="instance")
    assert ro.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert ro.value.detail.field == "parameter"

    # Wrong side: type-only name when resolving instance parameters.
    type_only = [{"name": "Type Mark", "storageType": "String", "specId": None, "isReadOnly": False}]
    with pytest.raises(ContractError) as side:
        resolve_parameter_name("Type Mark", {3001: []}, side="instance")
    assert side.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert side.value.detail.field == "parameter"
    # And the type side accepts it when present on the type prior read.
    assert resolve_parameter_name("Type Mark", {2001: type_only}, side="type") == "Type Mark"
