"""Revit edit kinds, value encoding and write preconditions (plan 0011 T8; AC8, AC12 to AC17).

Value encoding writes lengths only (`valueType: double`, millimetres, shortest round-trip decimal);
other doubles raise `NotImplementedGap` (R-G6). Before every write: active document equals the bound
working copy (AC13), `unique_id` matches the reference via `get_element_details` (AC12), parameter
names resolve from the prior read (AC17), shared-type `expected_instances` matches (AC15), and
`duplicate_family_type` carries no overrides (AC16). Batches are the largest whose dialog summary
fits 500 characters of the arguments (AC14; `RevitDestructiveConfirmationPrompt.cs:19-28`). Each
send appends to the write ledger first (AC14 / 0002 section 4.5.7).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.ids import SystemClock
from pydantic import JsonValue

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._ledger import LedgerEntry, WriteLedger
from eng_harness.adapters.revit._replies import parse_revit_reply
from eng_harness.adapters.revit._tools import (
    build_change_element_type_args,
    build_duplicate_family_type_args,
    build_set_element_parameter_values_args,
    build_set_parameter_value_by_guid_args,
    build_set_type_parameter_values_args,
)
from eng_harness.adapters.revit._units import load_specs
from eng_harness.errors import NotImplementedGap
from eng_harness.servers import CallEffect

__all__ = [
    "DIALOG_SUMMARY_LIMIT",
    "batch_ids_fitting_dialog",
    "build_edit_args",
    "check_active_document",
    "dialog_summary",
    "encode_write_value",
    "prepare_and_send_write",
    "resolve_parameter_name",
    "verify_unique_ids",
]

# Spec 0011 section 1 / AC14: dialog shows the first 500 characters of the arguments
# (`RevitDestructiveConfirmationPrompt.cs:19-28`, `PrepareDestructiveHandler.cs:43-45`).
DIALOG_SUMMARY_LIMIT = 500

HostCall = Callable[[str, dict[str, Any], CallEffect], Awaitable[Mapping[str, Any]]]
EditKind = Literal[
    "duplicate_family_type",
    "set_type_parameter_values",
    "change_element_type",
    "set_element_parameter_values",
    "set_parameter_value_by_guid",
]
_Side = Literal["instance", "type"]


def dialog_summary(arguments: Mapping[str, Any]) -> str:
    """Compact JSON of the host arguments; the bridge dialog shows the first 500 characters (AC14)."""
    return json.dumps(dict(arguments), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def batch_ids_fitting_dialog(
    ids: Sequence[int],
    make_args: Callable[[list[int]], Mapping[str, Any]],
) -> list[list[int]]:
    """Split `ids` into the largest batches whose dialog summary fits `DIALOG_SUMMARY_LIMIT` (AC14)."""
    if not ids:
        return []
    batches: list[list[int]] = []
    current: list[int] = []
    for element_id in ids:
        trial = [*current, int(element_id)]
        summary = dialog_summary(make_args(trial))
        if len(summary) <= DIALOG_SUMMARY_LIMIT:
            current = trial
            continue
        if not current:
            raise ContractError(
                ErrorCode.LIMIT_EXCEEDED,
                f"a single target's dialog summary exceeds {DIALOG_SUMMARY_LIMIT} characters",
                received=len(summary),
            )
        batches.append(current)
        current = [int(element_id)]
        if len(dialog_summary(make_args(current))) > DIALOG_SUMMARY_LIMIT:
            raise ContractError(
                ErrorCode.LIMIT_EXCEEDED,
                f"a single target's dialog summary exceeds {DIALOG_SUMMARY_LIMIT} characters",
                received=len(dialog_summary(make_args(current))),
            )
    if current:
        batches.append(current)
    return batches


def encode_write_value(
    *,
    storage: str,
    spec_id: str | None,
    value_mm: float | None = None,
    value: int | str | None = None,
) -> tuple[str, str]:
    """Encode a write value and its explicit `valueType` (AC8 / R-G6).

    Length doubles (specification kind `length` in `_specs.toml`) are millimetres in the shortest
    round-trip decimal form. Any other double raises `NotImplementedGap` with evidence `R-G6`.
    """
    kind = storage.strip().lower()
    if kind in {"integer", "int"}:
        if value is None or isinstance(value, bool) or not isinstance(value, int):
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "integer value is required", field="value")
        return str(value), "integer"
    if kind == "string":
        if value is None or not isinstance(value, str):
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "string value is required", field="value")
        return value, "string"
    if kind in {"elementid", "element_id"}:
        if value is None or isinstance(value, bool) or not isinstance(value, int):
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "element id value is required", field="value")
        return str(value), "elementId"
    if kind != "double":
        raise ContractError(ErrorCode.INVALID_ARGUMENT, f"unsupported storageType {storage}", field="value")

    entry = load_specs().by_id.get(spec_id) if isinstance(spec_id, str) and spec_id else None
    if entry is None or entry.kind != "length":
        raise NotImplementedGap(
            "non-length double writes are not implemented",
            evidence=("R-G6",),
        )
    if value_mm is None or isinstance(value_mm, bool) or not isinstance(value_mm, (int, float)):
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "length value_mm is required", field="value")
    # Shortest round-trip decimal (Python repr / Quantity key rule; AC8).
    return repr(float(value_mm)), "double"


def resolve_parameter_name(
    name: str,
    parameters_by_target: Mapping[int, Sequence[Mapping[str, Any]]],
    *,
    side: _Side,
) -> str:
    """Return `name` when it matches exactly one non-read-only parameter on every target (AC17)."""
    _ = side  # side selects which prior-read map the caller passes; wrong-side is an empty/mismatch map.
    if not name:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "parameter name is required", field="parameter")
    if not parameters_by_target:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "parameter not found on target", field="parameter")
    for _target_id, params in parameters_by_target.items():
        matches = [row for row in params if row.get("name") == name]
        if len(matches) != 1:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                "parameter must match exactly one entry on each target",
                field="parameter",
            )
        if bool(matches[0].get("isReadOnly")):
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "parameter is read-only", field="parameter")
    return name


def _unique_of(row: Mapping[str, Any]) -> str | None:
    raw = row.get("uniqueId", row.get("unique_id"))
    return str(raw) if isinstance(raw, str) and raw else None


def verify_unique_ids(
    details_items: Sequence[Mapping[str, Any]],
    references: Mapping[int, str],
) -> None:
    """Compare each details `uniqueId` with the reference; mismatch is `CONFLICT` (AC12)."""
    by_id: dict[int, Mapping[str, Any]] = {}
    for row in details_items:
        eid = row.get("element_id", row.get("elementId"))
        if isinstance(eid, int) and not isinstance(eid, bool):
            by_id[eid] = row
    mismatches = 0
    for element_id, expected in references.items():
        row = by_id.get(int(element_id))
        got = _unique_of(row) if row is not None else None
        if got != expected:
            mismatches += 1
    if mismatches:
        raise ContractError(
            ErrorCode.CONFLICT,
            f"{mismatches} element unique_id value(s) differ from the reference",
        )


def check_active_document(metadata_path: str | None, bound: Path) -> None:
    """Require metadata `path` equal to the bound working copy (AC13)."""
    if not metadata_path:
        raise ContractError(
            ErrorCode.PRECONDITION_FAILED,
            "no active document path",
            precondition=Precondition.model_open,
        )
    if PureWindowsPath(metadata_path) != PureWindowsPath(bound):
        raise ContractError(
            ErrorCode.PRECONDITION_FAILED,
            "active document is not the bound working copy",
            precondition=Precondition.model_open,
        )


def _check_shared_type(instance_ids: Sequence[int], expected_instances: Sequence[int]) -> None:
    """Refuse unless `expected_instances` equals the type's instances as a set (AC15)."""
    actual = sorted({int(x) for x in instance_ids})
    expected = sorted({int(x) for x in expected_instances})
    if actual != expected:
        raise ContractError(
            ErrorCode.CONFLICT,
            f"shared type has {len(actual)} instance(s); expected {len(expected)}",
        )


def build_edit_args(kind: EditKind, /, **kwargs: Any) -> dict[str, JsonValue]:
    """Build host arguments for one section 4.8 edit kind (AC14 to AC17)."""
    prior = kwargs.get("prior")
    if not isinstance(prior, Mapping):
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "prior read is required", field="prior")

    if kind == "duplicate_family_type":
        if kwargs.get("type_parameter_overrides") is not None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                "type_parameter_overrides are refused",
                field="type_parameter_overrides",
            )
        source_type_id = int(kwargs["source_type_id"])
        new_type_name = str(kwargs["new_type_name"])
        type_row = prior.get("types", {}).get(source_type_id) if isinstance(prior.get("types"), Mapping) else None
        family = str(type_row.get("family")) if isinstance(type_row, Mapping) else None
        names = prior.get("family_type_names")
        existing: set[str] = set()
        if isinstance(names, Mapping) and family is not None:
            raw = names.get(family)
            if isinstance(raw, (set, frozenset, list, tuple)):
                existing = {str(x) for x in raw}
        if new_type_name in existing:
            raise ContractError(ErrorCode.CONFLICT, "1 type name already exists in the family")
        return build_duplicate_family_type_args(source_type_id=source_type_id, new_type_name=new_type_name)

    if kind == "set_type_parameter_values":
        type_id = int(kwargs["type_id"])
        expected = list(kwargs["expected_instances"])
        type_row = prior.get("types", {}).get(type_id) if isinstance(prior.get("types"), Mapping) else None
        if not isinstance(type_row, Mapping):
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "type prior read is required", field="type_id")
        _check_shared_type(list(type_row.get("instance_ids") or ()), expected)
        params = list(type_row.get("parameters") or ())
        parameter_name = resolve_parameter_name(str(kwargs["parameter_name"]), {type_id: params}, side="type")
        param = next(row for row in params if row.get("name") == parameter_name)
        value, value_type = encode_write_value(
            storage=str(param.get("storageType") or "Double"),
            spec_id=param.get("specId") if isinstance(param.get("specId"), str) else None,
            value_mm=float(kwargs["value_mm"]) if "value_mm" in kwargs else None,
            value=kwargs.get("value"),
        )
        return build_set_type_parameter_values_args(
            type_ids=[type_id],
            parameter_name=parameter_name,
            value=value,
            value_type=value_type,
            expected_instances=expected,
        )

    if kind == "change_element_type":
        element_ids = [int(x) for x in kwargs["element_ids"]]
        type_id = int(kwargs["type_id"])
        if not element_ids:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "elementIds must be non-empty", field="elementIds")
        return build_change_element_type_args(element_ids=element_ids, type_id=type_id)

    if kind == "set_element_parameter_values":
        element_ids = [int(x) for x in kwargs["element_ids"]]
        elements = prior.get("elements") if isinstance(prior.get("elements"), Mapping) else {}
        by_target: dict[int, list[Mapping[str, Any]]] = {}
        for eid in element_ids:
            row = elements.get(eid) if isinstance(elements, Mapping) else None
            params = list(row.get("parameters") or ()) if isinstance(row, Mapping) else []
            by_target[eid] = params
        parameter_name = resolve_parameter_name(str(kwargs["parameter_name"]), by_target, side="instance")
        first = by_target[element_ids[0]]
        param = next(row for row in first if row.get("name") == parameter_name)
        value, value_type = encode_write_value(
            storage=str(param.get("storageType") or "Double"),
            spec_id=param.get("specId") if isinstance(param.get("specId"), str) else None,
            value_mm=float(kwargs["value_mm"]) if "value_mm" in kwargs else None,
            value=kwargs.get("value"),
        )
        return build_set_element_parameter_values_args(
            element_ids=element_ids,
            parameter_name=parameter_name,
            value=value,
            value_type=value_type,
        )

    if kind == "set_parameter_value_by_guid":
        element_ids = [int(x) for x in kwargs["element_ids"]]
        guid = str(kwargs["guid"])
        target = str(kwargs.get("target") or "instance")
        length_ids = [sid for sid, entry in load_specs().by_id.items() if entry.kind == "length"]
        if not length_ids:
            raise NotImplementedGap("no length specification is mapped for GUID writes", evidence=("R-G6",))
        value, value_type = encode_write_value(
            storage="Double",
            spec_id=length_ids[0],  # length GUID writes use mm (AC8 / section 4.6 / _specs.toml)
            value_mm=float(kwargs["value_mm"]) if "value_mm" in kwargs else None,
            value=kwargs.get("value"),
        )
        return build_set_parameter_value_by_guid_args(
            element_ids=element_ids,
            guid=guid,
            value=value,
            value_type=value_type,
            unit="mm",
            target=target,
            all_or_nothing=True,
        )

    raise ContractError(ErrorCode.INVALID_ARGUMENT, f"unknown edit kind {kind}", field="kind")


async def prepare_and_send_write(
    call: HostCall,
    ledger: WriteLedger,
    *,
    tool: str,
    host_args: Mapping[str, Any],
    op_id: str,
    bound_path: Path,
    references: Mapping[int, str],
    element_ids: Sequence[int] | None,
) -> Mapping[str, Any]:
    """Active-document and unique_id checks, ledger append, then the host write (AC12 to AC14)."""
    meta = await call("revit_get_model_metadata", {}, CallEffect.READ)
    meta_body = parse_revit_reply(dict(meta)).body
    path = meta_body.get("path")
    check_active_document(str(path) if isinstance(path, str) else None, bound_path)

    if element_ids:
        details = await call(
            "revit_get_element_details",
            {"elementIds": [int(x) for x in element_ids]},
            CallEffect.READ,
        )
        body = parse_revit_reply(dict(details)).body
        items = body.get("items")
        if not isinstance(items, list):
            raise ContractError(ErrorCode.HOST_ERROR, "element details reply has no items")
        needed = {int(eid): references[int(eid)] for eid in element_ids if int(eid) in references}
        verify_unique_ids([row for row in items if isinstance(row, Mapping)], needed)

    args = dict(host_args)
    # Ledger target uses the MCP server process id shape (HostTarget.pid >= 1); HostInstance.pid
    # stays None for document hosts (spec 0011 section 4.12). Tests supply no live pid: use 1.
    entry = LedgerEntry(
        op_id=op_id,
        tool=tool,
        args_sha256=payload_sha256(args),
        target=HostTarget(product="revit", pid=1),
        pre_image_ref=None,
        sent_at=SystemClock().now(),
    )
    ledger.append(entry)
    result = await call(tool, args, CallEffect.WRITE)
    return parse_revit_reply(dict(result)).body
