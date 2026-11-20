"""Revit reconciliation by reading (plan 0011 T10; spec 0011 AC20, AC21, section 4.10).

A write cut off by a lost reply is decided from the state read back. The reconciler import sits inside each
test so a missing module fails the test (ImportError) rather than collection.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import ParamModel
from pydantic import JsonValue

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._envelope import parse_reply
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding, Decision, LostWrite
from eng_harness.adapters.revit import revit_allowlist
from eng_harness.adapters.revit._edits import build_edit_args, send_attended_write
from eng_harness.adapters.revit._tools import (
    ChangeElementTypeArgs,
    DuplicateFamilyTypeArgs,
    OpenModelArgs,
    SetElementParameterValuesArgs,
    SetParameterValueByGuidArgs,
    SetTypeParameterValuesArgs,
)
from eng_harness.servers import CallEffect, ServerManager, ServersConfig

from . import _revit_edit_helpers as helpers

TOLERANCE = 0.001  # test input: the value a workflow's frozen basis would hand over
GUID = "11111111-1111-1111-1111-111111111111"
# Short backstop so lost-reply faults (withhold forever) surface as TIMEOUT_UNKNOWN_OUTCOME quickly.
# Keep enough headroom for write-role start under load (status + grace); fault sleep stays longer.
_SHORT_S = 8
_FAULT_HOLD_S = 20.0
COPY = Path(r"C:\models\copy.rvt")

HostRead = Callable[[str, dict[str, Any], CallEffect], Awaitable[dict[str, Any]]]


def _short_write_timeout(config: ServersConfig) -> ServersConfig:
    """Write-role timeout below the withhold delay (pattern of test_revit_dialog short timeout)."""
    section = config.servers["revit"]
    roles = dict(section.roles)
    roles["write"] = roles["write"].model_copy(update={"call_timeout_s": _SHORT_S})
    return config.model_copy(
        update={
            "servers": {
                **config.servers,
                "revit": section.model_copy(update={"roles": roles, "client_grace_s": 2}),
            }
        }
    )


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
                        "guid": GUID,
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
            },
            2002: {
                "family": helpers.FAMILY,
                "name": "C400x400",
                "family_id": 1001,
                "instance_ids": [],
                "parameters": [
                    {
                        "name": "b",
                        "storageType": "Double",
                        "specId": helpers.LENGTH_SPEC,
                        "isReadOnly": False,
                    }
                ],
            },
        },
        "family_type_names": {helpers.FAMILY: {"C300x300", "C400x400"}},
    }


def _seed_two_types() -> dict[str, Any]:
    seed = helpers.seed_model()
    seed["types"] = list(seed["types"]) + [
        {
            "type_id": 2002,
            "family": helpers.FAMILY,
            "name": "C400x400",
            "family_id": 1001,
            "category": "OST_StructuralColumns",
            "parameters": [helpers.length_param("b", helpers.B_FT), helpers.length_param("h", helpers.H_FT)],
            "instance_ids": [],
        }
    ]
    return seed


def _descriptor(tool: str) -> ToolDescriptor:
    return revit_allowlist(role="write").descriptor(tool)


def _model_for(tool: str, host_args: Mapping[str, Any]) -> ParamModel:
    if tool == "revit_set_element_parameter_values":
        return SetElementParameterValuesArgs(
            element_ids=[int(x) for x in host_args["elementIds"]],
            parameter_name=str(host_args["parameterName"]),
            value=str(host_args["value"]),
            value_type=str(host_args["valueType"]),  # type: ignore[arg-type]
        )
    if tool == "revit_set_type_parameter_values":
        return SetTypeParameterValuesArgs(
            parameter_name=str(host_args["parameterName"]),
            value=str(host_args["value"]),
            value_type=str(host_args["valueType"]),  # type: ignore[arg-type]
            type_ids=[int(x) for x in host_args["typeIds"]],
            expected_instances=[3001],
        )
    if tool == "revit_set_parameter_value_by_guid":
        return SetParameterValueByGuidArgs(
            element_ids=[int(x) for x in host_args["elementIds"]],
            guid=str(host_args["guid"]),
            value=str(host_args["value"]),
            value_type=str(host_args["valueType"]),  # type: ignore[arg-type]
            unit=str(host_args["unit"]) if host_args.get("unit") is not None else None,  # type: ignore[arg-type]
            target=str(host_args.get("target") or "instance"),  # type: ignore[arg-type]
            all_or_nothing=bool(host_args.get("allOrNothing", True)),
        )
    if tool == "revit_change_element_type":
        return ChangeElementTypeArgs(
            element_ids=[int(x) for x in host_args["elementIds"]],
            type_id=int(host_args["typeId"]),
        )
    if tool == "revit_duplicate_family_type":
        return DuplicateFamilyTypeArgs(
            source_type_id=str(host_args["source_type_id"]),
            new_type_name=str(host_args["new_type_name"]),
        )
    if tool == "revit_open_model":
        return OpenModelArgs(path=str(host_args["path"]), activate=bool(host_args.get("activate", True)))
    raise AssertionError(f"no model for {tool}")


def _binding(target: HostTarget) -> Binding:
    return Binding(target=target, owned=True)


def _lost(
    tool: str,
    host_args: Mapping[str, Any],
    target: HostTarget,
    *,
    known: bool,
    pre_image: JsonValue,
) -> LostWrite:
    return LostWrite(
        _descriptor(tool),
        _model_for(tool, host_args),
        _binding(target),
        known,
        pre_image,
    )


def _arm(control: Path, fault: str, tool: str, **extra: Any) -> None:
    data = json.loads(control.read_text(encoding="utf-8"))
    row = {"fault": fault, "tool": tool, **extra}
    data.setdefault("faults", []).append(row)
    control.write_text(json.dumps(data), encoding="utf-8")


async def _read_body(manager: ServerManager, tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
    dumped = await helpers.call_dump(
        manager, tool, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
    )
    return parse_reply(dumped)


async def _warm_write_role(manager: ServerManager) -> None:
    """Start the write role before arming a lost-reply fault (status must not race the withhold)."""
    await helpers.call_dump(manager, "revit_get_model_metadata", {}, CallEffect.READ, role="write")


def _write_args(tool: str) -> dict[str, Any]:
    prior = _prior()
    if tool == "revit_set_element_parameter_values":
        return build_edit_args(
            "set_element_parameter_values",
            element_ids=[3001],
            parameter_name="b",
            value_mm=450.0,
            prior=prior,
        )
    if tool == "revit_set_type_parameter_values":
        return build_edit_args(
            "set_type_parameter_values",
            type_id=2001,
            parameter_name="b",
            value_mm=450.0,
            expected_instances=[3001],
            prior=prior,
        )
    if tool == "revit_set_parameter_value_by_guid":
        return build_edit_args(
            "set_parameter_value_by_guid",
            element_ids=[3001],
            guid=GUID,
            value_mm=450.0,
            prior=prior,
        )
    if tool == "revit_change_element_type":
        return build_edit_args(
            "change_element_type",
            element_ids=[3001],
            type_id=2002,
            prior=prior,
        )
    if tool == "revit_duplicate_family_type":
        return build_edit_args(
            "duplicate_family_type",
            source_type_id=2001,
            new_type_name="C450x450",
            prior=prior,
        )
    if tool == "revit_open_model":
        return {"path": str(COPY), "activate": True}
    raise AssertionError(tool)


WRITE_TOOLS = (
    "revit_set_element_parameter_values",
    "revit_set_type_parameter_values",
    "revit_set_parameter_value_by_guid",
    "revit_change_element_type",
    "revit_duplicate_family_type",
    "revit_open_model",
)


async def _pre_image_value(
    read: HostRead,
    tool: str,
    host_args: Mapping[str, Any],
) -> JsonValue:
    """The observed state before the write, as `observe` would store it (AC20)."""
    from eng_harness.adapters.revit._reconcile import RevitReconciler

    reconciler = RevitReconciler(
        tolerance_ratio=TOLERANCE,
        bound_path=helpers.BOUND,
        unique_ids={3001: "col-3001"},
    )
    lost = _lost(tool, host_args, HostTarget(product="revit", pid=1), known=False, pre_image=None)
    observed = await reconciler.observe(lost, read)
    if observed is None:
        return None
    return observed.get("observed")


@pytest.mark.parametrize("tool", WRITE_TOOLS)
@pytest.mark.parametrize(
    ("applied", "expected"),
    ((True, "applied"), (False, "not_applied")),
    ids=["applied", "not_applied"],
)
def test_outcomes_per_tool(tool: str, applied: bool, expected: str, tmp_path: Path) -> None:
    """AC20: each write tool reconciles applied / not_applied from the state read after a lost reply."""
    control = tmp_path / "control.json"
    seed = _seed_two_types() if tool == "revit_change_element_type" else helpers.seed_model()
    config = _short_write_timeout(helpers.revit_config(tmp_path, control, seed=seed))

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        from eng_harness.adapters.revit._reconcile import RevitReconciler

        ledger = WriteLedger(tmp_path / "run")
        target = await helpers.warm_bound_target(manager, launcher)
        host_args = _write_args(tool)

        async def read(tool_name: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await _read_body(manager, tool_name, arguments, effect)

        async def call(tool_name: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await helpers.call_dump(
                manager, tool_name, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        pre = await _pre_image_value(read, tool, host_args)
        await _warm_write_role(manager)
        _arm(control, "lost_pipe", tool, applied=applied, seconds=_FAULT_HOLD_S)

        element_ids = [int(x) for x in host_args["elementIds"]] if "elementIds" in host_args else None
        references = {3001: "col-3001"} if element_ids else {}
        with pytest.raises(ContractError) as raised:
            await send_attended_write(
                call,
                ledger,
                tool=tool,
                host_args=host_args,
                op_id=f"op-{tool}-{'a' if applied else 'n'}",
                bound_path=helpers.BOUND,
                references=references,
                element_ids=element_ids,
                target=target,
                call_timeout_s=_SHORT_S,
            )
        assert raised.value.detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME

        reconciler = RevitReconciler(
            tolerance_ratio=TOLERANCE,
            bound_path=helpers.BOUND,
            unique_ids={3001: "col-3001"},
        )
        found = await reconciler.decide(
            _lost(tool, host_args, target, known=True, pre_image=pre),
            read,
        )
        assert isinstance(found, Decision)
        assert found.outcome == expected
        assert found.missing == ()
        assert "requested" in found.evidence or "path" in found.evidence or "observed" in found.evidence

    helpers.run_scenario(tmp_path, config, body)


def test_retry_duplicate_setter_applied(tmp_path: Path) -> None:
    """AC20: a setter applied twice by fault retry_duplicate is applied by the read."""
    control = tmp_path / "control.json"
    config = _short_write_timeout(helpers.revit_config(tmp_path, control))
    tool = "revit_set_element_parameter_values"

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        from eng_harness.adapters.revit._reconcile import RevitReconciler

        ledger = WriteLedger(tmp_path / "run")
        target = await helpers.warm_bound_target(manager, launcher)
        host_args = _write_args(tool)

        async def read(tool_name: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await _read_body(manager, tool_name, arguments, effect)

        async def call(tool_name: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await helpers.call_dump(
                manager, tool_name, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        pre = await _pre_image_value(read, tool, host_args)
        await _warm_write_role(manager)
        _arm(control, "retry_duplicate", tool, applied_twice=True, lose_reply=True, seconds=_FAULT_HOLD_S)
        with pytest.raises(ContractError) as raised:
            await send_attended_write(
                call,
                ledger,
                tool=tool,
                host_args=host_args,
                op_id="op-retry-dup",
                bound_path=helpers.BOUND,
                references={3001: "col-3001"},
                element_ids=[3001],
                target=target,
                call_timeout_s=_SHORT_S,
            )
        assert raised.value.detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME

        reconciler = RevitReconciler(
            tolerance_ratio=TOLERANCE,
            bound_path=helpers.BOUND,
            unique_ids={3001: "col-3001"},
        )
        found = await reconciler.decide(_lost(tool, host_args, target, known=True, pre_image=pre), read)
        assert found.outcome == "applied"
        assert found.missing == ()

    helpers.run_scenario(tmp_path, config, body)


def test_retry_token_consumed_applied(tmp_path: Path) -> None:
    """AC20: write applied once then resend fails with consumed token → applied by the read, never not_applied."""
    control = tmp_path / "control.json"
    config = _short_write_timeout(helpers.revit_config(tmp_path, control))
    tool = "revit_set_element_parameter_values"

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        from eng_harness.adapters.revit._reconcile import RevitReconciler

        ledger = WriteLedger(tmp_path / "run")
        target = await helpers.warm_bound_target(manager, launcher)
        host_args = _write_args(tool)

        async def read(tool_name: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await _read_body(manager, tool_name, arguments, effect)

        async def call(tool_name: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await helpers.call_dump(
                manager, tool_name, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        pre = await _pre_image_value(read, tool, host_args)
        await _warm_write_role(manager)
        _arm(control, "retry_token_consumed", tool, seconds=_FAULT_HOLD_S)
        with pytest.raises(ContractError) as raised:
            await send_attended_write(
                call,
                ledger,
                tool=tool,
                host_args=host_args,
                op_id="op-token",
                bound_path=helpers.BOUND,
                references={3001: "col-3001"},
                element_ids=[3001],
                target=target,
                call_timeout_s=_SHORT_S,
            )
        assert raised.value.detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME

        reconciler = RevitReconciler(
            tolerance_ratio=TOLERANCE,
            bound_path=helpers.BOUND,
            unique_ids={3001: "col-3001"},
        )
        found = await reconciler.decide(_lost(tool, host_args, target, known=True, pre_image=pre), read)
        assert found.outcome == "applied"
        assert found.outcome != "not_applied"
        assert found.missing == ()

    helpers.run_scenario(tmp_path, config, body)


def test_duplicate_type_after_retry(tmp_path: Path) -> None:
    """AC21: duplicate_family_type retry_duplicate 'already exists' → applied when type exists and was absent."""
    control = tmp_path / "control.json"
    config = helpers.revit_config(tmp_path, control)
    tool = "revit_duplicate_family_type"

    async def body(manager: ServerManager, launcher: helpers.RecordingLauncher) -> None:
        from eng_harness.adapters.revit._reconcile import RevitReconciler

        ledger = WriteLedger(tmp_path / "run")
        target = await helpers.warm_bound_target(manager, launcher)
        host_args = _write_args(tool)

        async def read(tool_name: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await _read_body(manager, tool_name, arguments, effect)

        async def call(tool_name: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            return await helpers.call_dump(
                manager, tool_name, arguments, effect, role="write" if effect is CallEffect.WRITE else "read"
            )

        pre = await _pre_image_value(read, tool, host_args)
        assert pre is None  # type was absent before the write

        _arm(control, "retry_duplicate", tool, applied_twice=True)
        with pytest.raises(ContractError) as raised:
            await send_attended_write(
                call,
                ledger,
                tool=tool,
                host_args=host_args,
                op_id="op-dup-retry",
                bound_path=helpers.BOUND,
                references={},
                element_ids=None,
                target=target,
                call_timeout_s=90,
            )
        # Spec 0011 §4.7: invalid_request "already exists" after a resend; the type was created by the first attempt.
        assert raised.value.detail.code in {ErrorCode.INVALID_ARGUMENT, ErrorCode.TIMEOUT_UNKNOWN_OUTCOME}
        assert "already exists" in raised.value.detail.message.lower()

        reconciler = RevitReconciler(
            tolerance_ratio=TOLERANCE,
            bound_path=helpers.BOUND,
            unique_ids={3001: "col-3001"},
        )
        found = await reconciler.decide(_lost(tool, host_args, target, known=True, pre_image=pre), read)
        assert found.outcome == "applied"
        assert found.missing == ()
        observed = found.evidence.get("observed")
        assert isinstance(observed, dict)
        assert observed.get("name") == "C450x450"
        assert observed.get("type_id") is not None

        # Present with other parameters (pre-image already held the name) is unknown (AC21).
        again = await reconciler.decide(
            _lost(tool, host_args, target, known=True, pre_image={"name": "C450x450", "type_id": 1}),
            read,
        )
        assert again.outcome == "unknown"

    helpers.run_scenario(tmp_path, config, body)
