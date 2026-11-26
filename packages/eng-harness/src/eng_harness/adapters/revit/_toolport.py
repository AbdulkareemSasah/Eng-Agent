"""Revit write tool port on the shared adapter framework (plan 0011 T14b; spec 0011 §4.8, §4.12).

Caller arguments carry references (amendment B-617): `element_ids` selects whole rows of
`harness.revit_structure/1` or `harness.frame_element_map/1` keeping `element_id` and `unique_id`;
`value_mm` is an engineering quantity reference for lengths; type references select `type_id` rows.
Resolved before the host request; the durable ledger target is the pipe and the bound document (Q10);
`expected_instances` is required and non-empty with an exact-set check (Q11). Attended writes use
T9's mapping and read-back helpers with T10's `RevitReconciler`; the shared PID `HostTarget`
contract stays for `Binding`, following IDEA B-612 Q13.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Envelope, HostInfo, LiteralInput, RefInput, SuccessEnvelope, make_failure
from eng_contract.errors import ContractError, ErrorCode, ErrorDetail, Precondition
from eng_contract.ids import Clock, IdSource, Timestamp
from eng_contract.params import ParamModel, eng_param
from eng_contract.refs import Ref, RefRule, parse_ref, resolve_ref
from eng_contract.store import ResultStore
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from eng_harness.adapters._allowlist import Allowlist
from eng_harness.adapters._args import validate_call
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._envelope import make_envelope, parse_reply
from eng_harness.adapters._errors import WEDGING_CODES, HostHealth, parse_error_reply
from eng_harness.adapters._toolport import AdapterToolPort, Binding, Decision, HostCaller, LostWrite
from eng_harness.adapters.revit import _tools as _host_tools
from eng_harness.adapters.revit._checks import WrittenItems, expect_write
from eng_harness.adapters.revit._edits import build_edit_args, check_active_document, verify_unique_ids
from eng_harness.adapters.revit._errors import RevitErrorMapper
from eng_harness.adapters.revit._reconcile import RevitReconciler
from eng_harness.adapters.revit._replies import parse_revit_reply
from eng_harness.adapters.revit._state import LIST_LIMIT
from eng_harness.adapters.revit._units import load_specs
from eng_harness.basis import BasisInvalid
from eng_harness.ctx import ModelHandle, Preview, PreviewItem
from eng_harness.errors import JournalIntegrityError, ToolFailed
from eng_harness.kinds.revit import RevitWriteResult, WriteTarget
from eng_harness.ports import Reconciliation, ServerCheck, ToolInfo
from eng_harness.servers import CallEffect, ServersConfig

__all__ = ["RevitToolPort"]

_SET = "revit_set_element_parameter_values"
_SET_TYPE = "revit_set_type_parameter_values"
_SET_GUID = "revit_set_parameter_value_by_guid"
_DUPLICATE = "revit_duplicate_family_type"
_CHANGE_TYPE = "revit_change_element_type"
_WRITE_RESULT = "harness.revit_write_result/1"
_RUN_OUTPUT = "harness.run_output/1"
_STRUCTURE = "harness.revit_structure/1"
_MAP = "harness.frame_element_map/1"
_OBSERVED_SUFFIX = "#/value/observed"
_SENT_SUFFIX = "#/value/sent"
_TOLERANCE_FIELD = "checks.readback_relative_tolerance_ratio"
_BOUNDS_SOURCE = "spec 0011 section 5: a written length is positive"
_CUSTOM_WRITES = frozenset({_SET, _SET_TYPE, _SET_GUID, _DUPLICATE, _CHANGE_TYPE})
_Obj = Mapping[str, JsonValue]
_Inputs = Mapping[str, RefInput | LiteralInput]
_Revision = Callable[[str], int | None]
_ValueType = Literal["string", "integer", "double", "elementId"]
_LengthUnit = Literal["mm", "internal"]
_GuidTarget = Literal["instance", "type"]


def _untracked(model_id: str) -> int | None:
    """No revision: historical references are read for values, never checked for age (CSI reconcile)."""
    return None


class _SetElementCaller(ParamModel):
    """Instance setter caller shape (§4.8): row refs, literal name, length ref or explicit value."""

    model: str
    element_ids: list[Ref] = Field(min_length=1)
    parameter_name: str = Field(min_length=1)
    value_mm: float | None = eng_param(
        default=None,
        unit="mm",
        ref_capable=True,
        engineering_quantity=True,
        gt=0,
        bounds_source=_BOUNDS_SOURCE,
    )
    value: str | int | None = None
    value_type: str | None = None


class _SetTypeCaller(ParamModel):
    """Type setter caller shape (§4.8, Q11): one type ref, non-empty expected set, length ref or value."""

    model: str
    type_ids: list[Ref] = Field(min_length=1, max_length=1)
    expected_instances: list[int] = Field(min_length=1)
    parameter_name: str = Field(min_length=1)
    value_mm: float | None = eng_param(
        default=None,
        unit="mm",
        ref_capable=True,
        engineering_quantity=True,
        gt=0,
        bounds_source=_BOUNDS_SOURCE,
    )
    value: str | int | None = None
    value_type: str | None = None


class _SetGuidCaller(ParamModel):
    """Shared-parameter setter caller shape (§4.8): row refs, GUID, length ref or value."""

    model: str
    element_ids: list[Ref] = Field(min_length=1)
    guid: str = Field(min_length=1)
    target: Literal["instance", "type"] = "instance"
    value_mm: float | None = eng_param(
        default=None,
        unit="mm",
        ref_capable=True,
        engineering_quantity=True,
        gt=0,
        bounds_source=_BOUNDS_SOURCE,
    )
    value: str | int | None = None
    value_type: str | None = None


class _DuplicateCaller(ParamModel):
    """Duplicate caller shape (§4.8): one type-id ref (or plain id) and the new name, never overrides."""

    model: str
    source_type_id: int = eng_param(ref_capable=True)
    new_type_name: str = Field(min_length=1)


class _ChangeCaller(ParamModel):
    """Type-assignment caller shape (§4.8): row refs and one type-id ref (or plain id), no engineering value."""

    model: str
    element_ids: list[Ref] = Field(min_length=1)
    type_id: int = eng_param(ref_capable=True)


_MODELS: Mapping[str, type[ParamModel]] = {
    "SetElementParameterValuesArgs": _SetElementCaller,
    "SetTypeParameterValuesArgs": _SetTypeCaller,
    "SetParameterValueByGuidArgs": _SetGuidCaller,
    "DuplicateFamilyTypeArgs": _DuplicateCaller,
    "ChangeElementTypeArgs": _ChangeCaller,
    "ConnectionStatusArgs": _host_tools.ConnectionStatusArgs,
    "PingArgs": _host_tools.PingArgs,
    "GetCurrentTargetArgs": _host_tools.GetCurrentTargetArgs,
    "ListAvailableTargetsArgs": _host_tools.ListAvailableTargetsArgs,
    "GetModelMetadataArgs": _host_tools.GetModelMetadataArgs,
    "ListLevelsArgs": _host_tools.ListLevelsArgs,
    "ListGridsArgs": _host_tools.ListGridsArgs,
    "ListElementsArgs": _host_tools.ListElementsArgs,
    "GetElementDetailsArgs": _host_tools.GetElementDetailsArgs,
    "GetElementParametersArgs": _host_tools.GetElementParametersArgs,
    "GetTypeParametersArgs": _host_tools.GetTypeParametersArgs,
    "GetAvailableFamilyTypesArgs": _host_tools.GetAvailableFamilyTypesArgs,
    "ListFamilyTypesInFamilyArgs": _host_tools.ListFamilyTypesInFamilyArgs,
    "ListWorksetsArgs": _host_tools.ListWorksetsArgs,
    "GetModelWarningsSummaryArgs": _host_tools.GetModelWarningsSummaryArgs,
    "OpenModelArgs": _host_tools.OpenModelArgs,
}


class _RevitTarget(BaseModel):
    """Durable ledger target (Q10): the configured pipe and the bound document, not a PID."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pipe_name: str = Field(min_length=1)
    document: str = Field(min_length=1)


class _RevitLedgerEntry(BaseModel):
    """One write about to be sent, tied to the caller args hash and the pre-image evidence (0002 §4.5.7)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    op_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    args_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target: _RevitTarget
    pre_image_ref: str | None
    sent_at: Timestamp


class _RevitWriteLedger:
    """Append before sending (§4.12, Q10): `run/adapter/ops.jsonl`, each entry `fsync`ed like the shared ledger."""

    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / "adapter" / "ops.jsonl"

    def append(self, entry: _RevitLedgerEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        created = not self.path.exists()
        with self.path.open("ab") as handle:
            handle.write(entry.model_dump_json().encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        if created and os.name == "posix":
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)

    def find(self, op_id: str) -> _RevitLedgerEntry | None:
        found: _RevitLedgerEntry | None = None
        if not self.path.exists():
            return None
        with self.path.open("rb") as handle:
            for line in handle:
                try:
                    entry = _RevitLedgerEntry.model_validate_json(line)
                except ValidationError:
                    continue
                if entry.op_id == op_id:
                    found = entry
        return found


@dataclass(frozen=True)
class _Resolved:
    """Caller references resolved to host ids, kept together through AC12 and read-back (§4.8)."""

    eids: tuple[int, ...]
    unique_ids: dict[int, str]
    tids: tuple[int, ...]
    value_mm: float | None
    value: str | int | None
    value_type: str | None
    inputs: dict[str, RefInput | LiteralInput]


def _raised(detail: ErrorDetail) -> ContractError:
    names = ("incident_id", "host_code", "host_method", "precondition", "field", "hint", "op_id")
    extra = {name: value for name in names if (value := getattr(detail, name)) is not None}
    return ContractError(detail.code, detail.message, retryable=detail.retryable, **extra)


def _check_map_sources(result_id: str, store: ResultStore, current_revision: _Revision) -> None:
    """Staleness of a map pair's sources (§4.11): any `REF_STALE` input makes the pair stale."""
    try:
        record = store.get(result_id)
    except ContractError:
        return
    for item in record.producer.inputs.values():
        if not isinstance(item, RefInput):
            continue
        try:
            resolve_ref(item.ref, RefRule(stale_ok=False), store, current_revision)
        except ContractError as error:
            if error.detail.code is ErrorCode.REF_STALE:
                raise
        except OSError, ValueError:
            continue


def _element_row(ref: str, store: ResultStore, current_revision: _Revision) -> tuple[int, str]:
    """One `element_ids` entry: the whole structure or map row, keeping `element_id` and `unique_id` (§4.8)."""
    rule = RefRule(kinds=frozenset({_STRUCTURE, _MAP}), field="element_ids")
    resolved = resolve_ref(ref, rule, store, current_revision)
    _, tokens = parse_ref(ref, field="element_ids")
    if resolved.record_kind == _MAP:
        _check_map_sources(resolved.result_id, store, current_revision)
        if len(tokens) != len(("pairs", "0")) or tokens[0] != "pairs":
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, "element ref must select a whole map pair", field="element_ids"
            )
    elif len(tokens) != len(("elements", "0")) or tokens[0] != "elements":
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT, "element ref must select a whole structure row", field="element_ids"
        )
    value = resolved.value
    if not isinstance(value, Mapping):
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "element ref must select a whole row", field="element_ids")
    eid, uid = value.get("element_id"), value.get("unique_id")
    if isinstance(eid, bool) or not isinstance(eid, int) or not isinstance(uid, str) or not uid:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT, "element row lacks element_id and unique_id", field="element_ids"
        )
    return int(eid), uid


def _type_id(ref: str, store: ResultStore, current_revision: _Revision, *, field: str) -> int:
    """One type-id entry: `#/types/<i>/type_id` of structure or `#/targets/<i>/type_id` of a write result (§4.8)."""
    rule = RefRule(kinds=frozenset({_STRUCTURE, _WRITE_RESULT}), field=field)
    resolved = resolve_ref(ref, rule, store, current_revision)
    _, tokens = parse_ref(ref, field=field)
    if resolved.record_kind == _STRUCTURE:
        if len(tokens) != len(("types", "0", "type_id")) or tokens[0] != "types" or tokens[2] != "type_id":
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "type ref must select a structure type_id", field=field)
    elif len(tokens) != len(("targets", "0", "type_id")) or tokens[0] != "targets" or tokens[2] != "type_id":
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "type ref must select a write-result type_id", field=field)
    value = resolved.value
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "type ref must resolve to an integer type_id", field=field)
    return int(value)


def _model_key(args: _Obj, model: str | None) -> str:
    raw = args.get("model")
    arg_key = raw if isinstance(raw, str) else None
    if arg_key is not None and model is not None and arg_key != model:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "the model selectors disagree", field="model")
    resolved = arg_key if arg_key is not None else model
    if resolved is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "missing model key", field="model")
    return resolved


class RevitToolPort(AdapterToolPort):
    """Write tool port for Revit: reference callers, attended dispatch, evidence and reconciliation (§4.12)."""

    def __init__(
        self,
        *,
        config: ServersConfig,
        allowlist: Allowlist,
        server: str,
        caller: HostCaller,
        host: Any,
        store: ResultStore,
        run_dir: Path,
        clock: Clock,
        ids: IdSource,
        check: ServerCheck,
        written: WrittenItems,
        tolerance: Callable[[], float | None],
    ) -> None:
        # Bypass the PID-ledger base initializer (IDEA B-612 Q13): dispatch is Revit-specific (Q10).
        self._config, self._allowlist, self._server, self._caller = config, allowlist, server, caller
        self._store, self._clock, self._ids, self._check, self._models = store, clock, ids, check, _MODELS
        self._health, self._errors = HostHealth(), RevitErrorMapper(ids)
        self._host, self._run_dir = host, run_dir.resolve()
        self._revit_ledger = _RevitWriteLedger(self._run_dir)
        self._written, self._tolerance = written, tolerance

    async def describe(self, tool: str) -> ToolInfo:
        """As the shared describe, with `attended` for the `attended` class (spec §4.4, AC18)."""
        info = await super().describe(tool)
        descriptor = self._find(tool)
        return info.model_copy(update={"attended": descriptor.timeout_class == "attended"})

    def _tolerance_value(self) -> float | None:
        try:
            return self._tolerance()
        except BasisInvalid, JournalIntegrityError, OSError, ValueError:
            return None

    def _pipe(self) -> str:
        pipe = self._config.servers[self._server].pipe_name
        if not pipe:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "pipe_name is required for Revit", field="pipe_name")
        return pipe

    def _bound_path(self, model_key: str) -> Path:
        files = self._host.model_files(model_key)
        if not files:
            raise ContractError(ErrorCode.PRECONDITION_FAILED, "not open", precondition=Precondition.model_open)
        return cast(Path, files[0])

    def _store_result(
        self,
        tool: str,
        kind: str,
        payload: dict[str, JsonValue],
        host: HostInfo | None,
        inputs: _Inputs,
        timing: tuple[Timestamp, int],
        reply: _Obj | None = None,
        summary: dict[str, JsonValue] | None = None,
    ) -> SuccessEnvelope:
        started, began = timing
        return make_envelope(
            self._store,
            tool=f"{self._allowlist.adapter}/{tool}",
            kind=kind,
            payload=payload,
            summary=summary or {},
            reply=reply or {},
            check=self._check,
            host=host,
            inputs=dict(inputs),
            started_at=started,
            duration_ms=self._clock.now_ms() - began,
        )

    def _timing(self) -> tuple[Timestamp, int]:
        return self._clock.now(), self._clock.now_ms()

    async def _read(self, tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
        """A read on the `call` role; host failures mapped, session loss as `ContractError` for the reconciler."""
        role = next(name for name, item in self._config.servers[self._server].roles.items() if "call" in item.classes)
        try:
            result = await self._caller.call(self._server, role, tool, arguments, effect)
        except ToolFailed as error:
            raise _raised(error.detail) from error
        dumped = result.model_dump(by_alias=True, mode="json")
        if (failure := parse_error_reply(dumped)) is not None:
            mapper = self._errors
            if mapper is None:
                raise ContractError(ErrorCode.INTERNAL, "no Revit error mapping", incident_id=self._ids.new_ulid())
            raise _raised(mapper.map(failure, effect=effect, tool=tool, op_id=""))
        return parse_reply(dumped)

    def _resolve(
        self,
        tool: str,
        validated: Any,
        args: _Obj,
        current_revision: _Revision,
    ) -> tuple[_Resolved, dict[str, RefInput | LiteralInput]]:
        """Resolve reference lists with kind and pointer rules; scalar refs already resolved by `validate_call`."""
        base: dict[str, RefInput | LiteralInput] = dict(validated.inputs)
        raw_elements: list[Any] = []
        raw_types: list[Any] = []
        single_type: str | None = None
        single_field = ""
        if tool in {_SET, _CHANGE_TYPE, _SET_GUID}:
            raw = args.get("element_ids")
            raw_elements = list(raw) if isinstance(raw, list) else []
        if tool == _SET_TYPE:
            raw = args.get("type_ids")
            raw_types = list(raw) if isinstance(raw, list) else []
        if tool == _DUPLICATE:
            node = args.get("source_type_id")
            raw_ref = node.get("$ref") if isinstance(node, Mapping) else None
            single_type = raw_ref if isinstance(raw_ref, str) else None
            single_field = "source_type_id"
        if tool == _CHANGE_TYPE:
            node = args.get("type_id")
            raw_ref = node.get("$ref") if isinstance(node, Mapping) else None
            single_type = raw_ref if isinstance(raw_ref, str) else None
            single_field = "type_id"
        eids: list[int] = []
        unique_ids: dict[int, str] = {}
        for index, node in enumerate(raw_elements):
            ref = node.get("$ref") if isinstance(node, Mapping) else None
            if not isinstance(ref, str):
                raise ContractError(
                    ErrorCode.INVALID_ARGUMENT, "element_ids entries must be references", field="element_ids"
                )
            eid, uid = _element_row(ref, self._store, current_revision)
            eids.append(eid)
            unique_ids[eid] = uid
            base[f"element_ids[{index}]"] = RefInput(ref=ref)
        base.pop("element_ids", None)
        tids: list[int] = []
        for index, node in enumerate(raw_types):
            ref = node.get("$ref") if isinstance(node, Mapping) else None
            if not isinstance(ref, str):
                raise ContractError(ErrorCode.INVALID_ARGUMENT, "type_ids entries must be references", field="type_ids")
            tids.append(_type_id(ref, self._store, current_revision, field="type_ids"))
            base[f"type_ids[{index}]"] = RefInput(ref=ref)
        base.pop("type_ids", None)
        if single_type is not None:
            tids.append(_type_id(single_type, self._store, current_revision, field=single_field))
            base[single_field] = RefInput(ref=single_type)
        elif single_field:
            plain = getattr(validated.model, single_field)
            if isinstance(plain, bool) or not isinstance(plain, int):
                raise ContractError(
                    ErrorCode.INVALID_ARGUMENT, "type id must be a reference or an integer id", field=single_field
                )
            tids.append(int(plain))
        model = validated.model
        value_mm = getattr(model, "value_mm", None)
        number: float | None = None
        if value_mm is not None:
            if isinstance(value_mm, bool) or not isinstance(value_mm, (int, float)):
                raise ContractError(ErrorCode.INVALID_ARGUMENT, "value_mm must resolve to a number", field="value_mm")
            number = float(value_mm)
        value = getattr(model, "value", None)
        value_type = getattr(model, "value_type", None)
        if value is not None and not isinstance(value, (str, int)):
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "value must be a string or integer", field="value")
        if isinstance(value, bool):
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "value must be a string or integer", field="value")
        if value_type is not None and not isinstance(value_type, str):
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "value_type must be a string", field="value_type")
        resolved = _Resolved(
            tuple(eids),
            unique_ids,
            tuple(tids),
            number,
            value if isinstance(value, (str, int)) else None,
            value_type if isinstance(value_type, str) else None,
            dict(base),
        )
        return resolved, base

    async def _instances_of(self, tid: int) -> list[int]:
        """All element ids whose current type is `tid`, by scanning the two structural lists (AC15)."""
        found: set[int] = set()
        for category in ("OST_StructuralColumns", "OST_StructuralFraming"):
            body = await self._read("revit_list_elements", {"category": category, "limit": LIST_LIMIT}, CallEffect.READ)
            if body.get("truncated") is True:
                raise ContractError(ErrorCode.LIMIT_EXCEEDED, "element list truncated during AC15 scan")
            rows = body.get("items")
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                eid, current = row.get("element_id"), row.get("type_id")
                if isinstance(eid, int) and not isinstance(eid, bool) and current == tid:
                    found.add(int(eid))
        return sorted(found)

    async def _prior(self, tool: str, resolved: _Resolved, args: _Obj) -> dict[str, Any]:
        """Prior reads for `build_edit_args`: parameters, instances, or family names in this epoch."""
        if tool == _SET:
            body = await self._read(
                "revit_get_element_parameters", {"elementIds": list(resolved.eids)}, CallEffect.READ
            )
            items = body.get("items")
            by_id: dict[int, list[Any]] = {}
            if isinstance(items, list):
                for row in items:
                    if isinstance(row, Mapping) and isinstance(row.get("id"), int):
                        listed = row.get("parameters")
                        by_id[int(row["id"])] = list(listed) if isinstance(listed, list) else []
            elements = {
                eid: {"unique_id": resolved.unique_ids.get(eid, ""), "parameters": by_id.get(eid, [])}
                for eid in resolved.eids
            }
            return {"elements": elements, "types": {}}
        if tool == _SET_TYPE:
            tid = resolved.tids[0]
            body = await self._read("revit_get_type_parameters", {"typeIds": [tid]}, CallEffect.READ)
            items = body.get("items")
            type_params: list[Any] = []
            if isinstance(items, list):
                for row in items:
                    if isinstance(row, Mapping) and row.get("id") == tid:
                        raw = row.get("parameters")
                        type_params = list(raw) if isinstance(raw, list) else []
                        break
            return {
                "types": {tid: {"instance_ids": await self._instances_of(tid), "parameters": type_params}},
                "elements": {},
            }
        if tool == _DUPLICATE:
            body = await self._read("revit_list_family_types_in_family", {}, CallEffect.READ)
            if body.get("truncated") is True:
                raise ContractError(ErrorCode.LIMIT_EXCEEDED, "family type list truncated")
            rows = body.get("items")
            listed = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
            source = resolved.tids[0]
            family: str | None = None
            for row in listed:
                if row.get("type_id") == source and isinstance(row.get("family"), str):
                    family = str(row["family"])
                    break
            names = (
                {str(row["name"]) for row in listed if isinstance(row.get("name"), str) and row.get("family") == family}
                if family
                else set()
            )
            types = {source: {"family": family}} if family else {}
            families = {family: names} if family else {}
            return {"types": types, "family_type_names": families, "elements": {}}
        return {"elements": {}, "types": {}}

    def _require_value_choice(
        self, tool: str, prior: Mapping[str, Any], resolved: _Resolved, parameter_name: str
    ) -> None:
        """Scalar length validation (§4.8): a length needs `value_mm` and refuses `value`, and conversely."""
        if tool not in {_SET, _SET_TYPE, _SET_GUID}:
            return
        if tool == _SET_GUID:
            if resolved.value_mm is None or resolved.value is not None:
                raise ContractError(
                    ErrorCode.INVALID_ARGUMENT,
                    "a length needs value_mm, not value",
                    field="value_mm" if resolved.value_mm is None else "value",
                )
            return
        params: list[Mapping[str, Any]] = []
        if tool == _SET and resolved.eids:
            row = (
                prior.get("elements", {}).get(resolved.eids[0], {})
                if isinstance(prior.get("elements"), Mapping)
                else {}
            )
            raw = row.get("parameters") if isinstance(row, Mapping) else None
            params = [item for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []
        elif tool == _SET_TYPE and resolved.tids:
            row = prior.get("types", {}).get(resolved.tids[0], {}) if isinstance(prior.get("types"), Mapping) else {}
            raw = row.get("parameters") if isinstance(row, Mapping) else None
            params = [item for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []
        match = next((row for row in params if row.get("name") == parameter_name), None)
        if match is None:
            return
        storage = str(match.get("storageType") or "")
        spec = match.get("specId")
        entry = load_specs().by_id.get(spec) if isinstance(spec, str) else None
        is_length = storage.strip().lower() == "double" and entry is not None and entry.kind == "length"
        is_double = storage.strip().lower() == "double"
        if is_length:
            if resolved.value_mm is None or resolved.value is not None or resolved.value_type is not None:
                field = "value_mm" if resolved.value_mm is None else "value"
                raise ContractError(ErrorCode.INVALID_ARGUMENT, "a length needs value_mm, not value", field=field)
        elif not is_double and (resolved.value is None or resolved.value_type is None or resolved.value_mm is not None):
            field = "value" if resolved.value is None else "value_mm"
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "a non-length needs value and value_type", field=field)
        # A non-length double falls through to `build_edit_args`, which raises `NotImplementedGap` (R-G6).

    def _host_args(
        self, tool: str, validated: Any, resolved: _Resolved, prior: Mapping[str, Any], args: _Obj
    ) -> dict[str, JsonValue]:
        """Host request via the merged builders; `expected_instances` and overrides never go on the wire."""
        model = validated.model
        if tool == _SET:
            kwargs: dict[str, Any] = {
                "element_ids": list(resolved.eids),
                "parameter_name": str(model.parameter_name),
                "prior": prior,
            }
            if resolved.value_mm is not None:
                kwargs["value_mm"] = resolved.value_mm
            if resolved.value is not None:
                kwargs["value"] = resolved.value
            sent = build_edit_args("set_element_parameter_values", **kwargs)
            self._check_value_type(sent, resolved)
            return sent
        if tool == _SET_TYPE:
            expected = list(model.expected_instances)
            kwargs = {
                "type_id": resolved.tids[0],
                "parameter_name": str(model.parameter_name),
                "expected_instances": expected,
                "prior": prior,
            }
            if resolved.value_mm is not None:
                kwargs["value_mm"] = resolved.value_mm
            if resolved.value is not None:
                kwargs["value"] = resolved.value
            sent = build_edit_args("set_type_parameter_values", **kwargs)
            self._check_value_type(sent, resolved)
            return sent
        if tool == _SET_GUID:
            kwargs = {
                "element_ids": list(resolved.eids),
                "guid": str(model.guid),
                "target": str(model.target),
                "prior": prior,
            }
            if resolved.value_mm is not None:
                kwargs["value_mm"] = resolved.value_mm
            if resolved.value is not None:
                kwargs["value"] = resolved.value
            return build_edit_args("set_parameter_value_by_guid", **kwargs)
        if tool == _DUPLICATE:
            return build_edit_args(
                "duplicate_family_type",
                source_type_id=resolved.tids[0],
                new_type_name=str(model.new_type_name),
                prior=prior,
            )
        return build_edit_args(
            "change_element_type", element_ids=list(resolved.eids), type_id=resolved.tids[0], prior=prior
        )

    @staticmethod
    def _check_value_type(sent: Mapping[str, Any], resolved: _Resolved) -> None:
        if resolved.value_type is not None and sent.get("valueType") != resolved.value_type:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, "value_type does not match the parameter storage", field="value_type"
            )

    def _host_model(self, tool: str, sent: Mapping[str, Any], resolved: _Resolved, validated: Any) -> Any:
        """Host ParamModel for the reconciler's read-back, from the prepared request."""
        if tool == _SET:
            return _host_tools.SetElementParameterValuesArgs(
                element_ids=list(resolved.eids),
                parameter_name=str(sent["parameterName"]),
                value=str(sent["value"]),
                value_type=cast(_ValueType, str(sent["valueType"])),
            )
        if tool == _SET_TYPE:
            return _host_tools.SetTypeParameterValuesArgs(
                parameter_name=str(sent["parameterName"]),
                value=str(sent["value"]),
                value_type=cast(_ValueType, str(sent["valueType"])),
                type_ids=list(resolved.tids),
                expected_instances=list(validated.model.expected_instances),
            )
        if tool == _SET_GUID:
            unit = sent.get("unit")
            return _host_tools.SetParameterValueByGuidArgs(
                element_ids=list(resolved.eids),
                guid=str(sent["guid"]),
                value=str(sent["value"]),
                value_type=cast(_ValueType, str(sent["valueType"])),
                unit=cast(_LengthUnit, str(unit)) if isinstance(unit, str) else None,
                target=cast(_GuidTarget, str(sent.get("target") or "instance")),
                all_or_nothing=True,
            )
        if tool == _DUPLICATE:
            return _host_tools.DuplicateFamilyTypeArgs(
                source_type_id=str(sent["source_type_id"]), new_type_name=str(sent["new_type_name"])
            )
        return _host_tools.ChangeElementTypeArgs(element_ids=list(resolved.eids), type_id=resolved.tids[0])

    async def _observe_current(
        self, descriptor: ToolDescriptor, host_model: Any, binding: Binding, unique_ids: Mapping[int, str], bound: Path
    ) -> JsonValue:
        """Pre-image observation through T10's reconciler; `None` reads stay a known absence (§4.10)."""
        reconciler = RevitReconciler(
            tolerance_ratio=self._tolerance_value(), bound_path=bound, unique_ids=dict(unique_ids)
        )
        lost = LostWrite(descriptor, host_model, binding, False, None)
        observed = await reconciler.observe(lost, self._read)
        if observed is None:
            return None
        inner = observed.get("observed")
        return inner if inner is not None else None

    async def _check_bound_document(self, model_key: str, bound: Path) -> None:
        """AC13: metadata `path` and the active document must both be the bound copy, pre-send."""
        body = await self._read("revit_get_model_metadata", {}, CallEffect.READ)
        path = body.get("path")
        check_active_document(str(path) if isinstance(path, str) else None, bound)
        active = body.get("active_path")
        if isinstance(active, str) and active:
            check_active_document(active, bound)

    async def _check_identities(self, tool: str, resolved: _Resolved) -> None:
        """AC12: every written element's `uniqueId` must match its row reference, pre-send."""
        if tool not in {_SET, _CHANGE_TYPE, _SET_GUID} or not resolved.eids:
            return
        body = await self._read("revit_get_element_details", {"elementIds": list(resolved.eids)}, CallEffect.READ)
        items = body.get("items")
        if not isinstance(items, list):
            raise ContractError(ErrorCode.HOST_ERROR, "element details reply has no items")
        verify_unique_ids(
            [row for row in items if isinstance(row, Mapping)], {eid: resolved.unique_ids[eid] for eid in resolved.eids}
        )

    def supports_reconcile(self, tool: str) -> bool:
        """True for a write tool of the allowlist; the reconciler is built per call (§4.10)."""
        try:
            descriptor = self._allowlist.descriptor(tool)
        except KeyError:
            return False
        return descriptor.effect == "write"

    async def preview(self, tool: str, args: _Obj) -> Preview:
        """Canonical arguments and the observed pre-image, without sending a write (§4.12)."""
        descriptor = self._find(tool)
        if tool not in _CUSTOM_WRITES:
            return await self._preview_read(descriptor, args)
        validated = validate_call(
            self._models[descriptor.args_model], args, source=self._store, current_revision=self._host.revision
        )
        key = args.get("model")
        model_key = key if isinstance(key, str) else None
        binding = await self._host.binding(self._config.servers[self._server].host_key, model_key, descriptor)
        if binding.host is None:
            raise ContractError(ErrorCode.PRECONDITION_FAILED, "not open", precondition=Precondition.model_open)
        resolved, _ = self._resolve(tool, validated, args, self._host.revision)
        bound = self._bound_path(model_key or "")
        prior = await self._prior(tool, resolved, args)
        parameter = getattr(validated.model, "parameter_name", None)
        if isinstance(parameter, str):
            self._require_value_choice(tool, prior, resolved, parameter)
        sent = self._host_args(tool, validated, resolved, prior, args)
        host_model = self._host_model(tool, sent, resolved, validated)
        pre_inner = await self._observe_current(descriptor, host_model, binding, resolved.unique_ids, bound)
        timing = self._timing()
        canonical = self._store_result(
            tool,
            _RUN_OUTPUT,
            {"value": validated.model.model_dump(mode="json", exclude_none=True)},
            binding.host,
            dict(validated.inputs),
            timing,
        )
        before = self._store_result(tool, _RUN_OUTPUT, {"value": {"observed": pre_inner}}, binding.host, {}, timing)
        refs = (
            Ref.model_validate({"$ref": canonical.result_id}),
            Ref.model_validate({"$ref": f"{before.result_id}{_OBSERVED_SUFFIX}"}),
        )
        handle = ModelHandle(
            model_key=model_key or "", model_id=binding.host.model_id, revision=binding.host.model_revision
        )
        label = f"{tool}: {model_key or 'host'}"
        return Preview(items=(PreviewItem(id=tool, label=label, refs=refs),), models=(handle,), diff_ref=None)

    async def _preview_read(self, descriptor: ToolDescriptor, args: _Obj) -> Preview:
        validated = validate_call(
            self._models[descriptor.args_model], dict(args), source=self._store, current_revision=self._host.revision
        )
        key = args.get("model")
        model_key = key if isinstance(key, str) else None
        host: HostInfo | None = None
        models: tuple[ModelHandle, ...] = ()
        if model_key is not None:
            binding = await self._host.binding(self._config.servers[self._server].host_key, model_key, descriptor)
            host = binding.host
            if host is not None:
                models = (ModelHandle(model_key=model_key, model_id=host.model_id, revision=host.model_revision),)
        timing = self._timing()
        stored = self._store_result(
            descriptor.name,
            _RUN_OUTPUT,
            {"value": validated.model.model_dump(mode="json", exclude_none=True)},
            host,
            dict(validated.inputs),
            timing,
        )
        return Preview(
            items=(
                PreviewItem(
                    id=descriptor.name, label=descriptor.name, refs=(Ref.model_validate({"$ref": stored.result_id}),)
                ),
            ),
            models=models,
            diff_ref=None,
        )

    async def read_back(self, tool: str, args: _Obj) -> Envelope | None:
        """The state a write left, as stored `value.observed`; `None` without a read-back (§4.8)."""
        descriptor = self._find(tool)
        if tool not in _CUSTOM_WRITES:
            return None
        validated = validate_call(
            self._models[descriptor.args_model], args, source=self._store, current_revision=_untracked
        )
        resolved, provenance = self._resolve(tool, validated, args, _untracked)
        model_key = _model_key(args, None)
        binding = await self._host.binding(self._config.servers[self._server].host_key, model_key, descriptor)
        bound = self._bound_path(model_key)
        prior = await self._prior(tool, resolved, args)
        parameter = getattr(validated.model, "parameter_name", None)
        if isinstance(parameter, str):
            with contextlib.suppress(ContractError):
                self._require_value_choice(tool, prior, resolved, parameter)
        sent = self._host_args(tool, validated, resolved, prior, args)
        host_model = self._host_model(tool, sent, resolved, validated)
        reconciler = RevitReconciler(
            tolerance_ratio=self._tolerance_value(), bound_path=bound, unique_ids=dict(resolved.unique_ids)
        )
        lost = LostWrite(descriptor, host_model, binding, False, None)
        observed = await reconciler.observe(lost, self._read)
        if observed is None:
            return None
        return self._store_result(tool, _RUN_OUTPUT, {"value": observed}, binding.host, provenance, self._timing())

    async def call(self, tool: str, args: _Obj, *, op_id: str, model: str | None) -> Envelope:
        """Call `tool`; a write is evidenced and ledgered before it is sent (Q10)."""
        descriptor = self._find(tool)
        try:
            return await self._call(descriptor, args, op_id, model)
        except (ContractError, ToolFailed) as error:
            return make_failure(error.detail)

    async def _call(self, descriptor: ToolDescriptor, args: _Obj, op_id: str, model: str | None) -> Envelope:
        host_key = self._config.servers[self._server].host_key
        self._health.check(host_key)
        epoch = self._host.session_epoch(host_key)
        try:
            if descriptor.name in _CUSTOM_WRITES:
                return await self._attended(descriptor, args, op_id, model)
            if descriptor.effect == "read":
                return await self._read_dispatch(descriptor, args, model)
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, f"{descriptor.name} is not served via the tool port", field="tool"
            )
        except (ContractError, ToolFailed) as error:
            detail = error.detail
            if detail.code in WEDGING_CODES:
                bumped = self._host.session_epoch(host_key) == epoch
                raise self._lost(detail, host_key, op_id, bump_epoch=bumped) from error
            raise

    async def _read_dispatch(self, descriptor: ToolDescriptor, args: _Obj, model: str | None) -> Envelope:
        server = self._config.servers[self._server]
        role = next(name for name, item in server.roles.items() if descriptor.timeout_class in item.classes)
        started, began = self._clock.now(), self._clock.now_ms()
        validated = validate_call(
            self._models[descriptor.args_model], dict(args), source=self._store, current_revision=self._host.revision
        )
        key = _model_key(dict(args), model) if "model" in args or model is not None else None
        binding = await self._host.binding(server.host_key, key, descriptor)
        sent = validated.model.model_dump(mode="json", exclude_none=True)
        try:
            result = await self._caller.call(self._server, role, descriptor.name, sent, CallEffect.READ)
        except ToolFailed as error:
            raise self._lost(error.detail, server.host_key, "", bump_epoch=False) from error
        dumped = result.model_dump(by_alias=True, mode="json")
        if (failure := parse_error_reply(dumped)) is not None:
            mapper = self._errors
            if mapper is None:
                raise ContractError(ErrorCode.INTERNAL, "no Revit error mapping", incident_id=self._ids.new_ulid())
            detail = mapper.map(failure, effect=CallEffect.READ, tool=descriptor.name, op_id="")
            raise self._lost(detail, server.host_key, "", bump_epoch=True)
        reply = parse_revit_reply(dumped).body
        return make_envelope(
            self._store,
            tool=f"{self._allowlist.adapter}/{descriptor.name}",
            kind=descriptor.result_kind or _RUN_OUTPUT,
            payload={"value": reply},
            summary={},
            reply=reply,
            check=self._check,
            host=binding.host,
            inputs=dict(validated.inputs),
            started_at=started,
            duration_ms=self._clock.now_ms() - began,
        )

    async def _attended(self, descriptor: ToolDescriptor, args: _Obj, op_id: str, model: str | None) -> Envelope:
        """Validated attended write: AC13 and AC12, pre-send evidence, ledger, send, settlement (§4.12)."""
        tool = descriptor.name
        timing = self._timing()
        validated = validate_call(
            self._models[descriptor.args_model], args, source=self._store, current_revision=self._host.revision
        )
        model_key = _model_key(args, model)
        binding = await self._host.binding(self._config.servers[self._server].host_key, model_key, descriptor)
        if binding.host is None:
            raise ContractError(ErrorCode.PRECONDITION_FAILED, "not open", precondition=Precondition.model_open)
        resolved, provenance = self._resolve(tool, validated, args, self._host.revision)
        bound = self._bound_path(model_key)
        await self._check_bound_document(model_key, bound)
        await self._check_identities(tool, resolved)
        prior = await self._prior(tool, resolved, args)
        parameter = getattr(validated.model, "parameter_name", None)
        if isinstance(parameter, str):
            self._require_value_choice(tool, prior, resolved, parameter)
        sent = self._host_args(tool, validated, resolved, prior, args)
        host_model = self._host_model(tool, sent, resolved, validated)
        pre_inner = await self._observe_current(descriptor, host_model, binding, resolved.unique_ids, bound)
        evidence = self._store_result(
            tool, _RUN_OUTPUT, {"value": {"observed": pre_inner, "sent": sent}}, binding.host, provenance, timing
        )
        entry = _RevitLedgerEntry(
            op_id=op_id,
            tool=tool,
            args_sha256=payload_sha256(dict(args)),
            target=_RevitTarget(pipe_name=self._pipe(), document=str(bound)),
            pre_image_ref=f"{evidence.result_id}{_OBSERVED_SUFFIX}",
            sent_at=self._clock.now(),
        )
        try:
            self._revit_ledger.append(entry)
        except OSError as error:
            raise ContractError(
                ErrorCode.INTERNAL, f"{tool} not sent, ledger: {error}", incident_id=self._ids.new_ulid()
            ) from error
        server = self._config.servers[self._server]
        role = next(name for name, item in server.roles.items() if descriptor.timeout_class in item.classes)
        result = await self._caller.call(self._server, role, tool, dict(sent), CallEffect.WRITE)
        dumped = result.model_dump(by_alias=True, mode="json")
        if (failure := parse_error_reply(dumped)) is not None:
            mapper = self._errors
            if mapper is None:
                raise ContractError(ErrorCode.INTERNAL, "no Revit error mapping", incident_id=self._ids.new_ulid())
            detail = mapper.map(failure, effect=CallEffect.WRITE, tool=tool, op_id=op_id)
            raise ToolFailed(detail)
        body = parse_revit_reply(dumped).body
        unique: str | None = None
        if resolved.eids:
            unique = resolved.unique_ids.get(resolved.eids[0])
        self._written.prepare(model_key, expect_write(tool, dict(sent), unique_id=unique))
        self._written.commit(model_key)
        payload = await self._write_result(tool, op_id, dict(sent), resolved, body, validated)
        return self._store_result(tool, _WRITE_RESULT, payload, binding.host, provenance, timing)

    async def _write_result(
        self,
        tool: str,
        op_id: str,
        sent: Mapping[str, Any],
        resolved: _Resolved,
        body: Mapping[str, Any],
        validated: Any,
    ) -> dict[str, JsonValue]:
        """`harness.revit_write_result/1` from the request, the resolved identities and the host reply (§4.5)."""
        targets: list[WriteTarget] = []
        if tool in {_SET, _SET_GUID}:
            targets = [WriteTarget(unique_id=resolved.unique_ids[eid], element_id=eid) for eid in resolved.eids]
        elif tool == _SET_TYPE:
            targets = [WriteTarget(type_id=tid) for tid in resolved.tids]
        elif tool == _CHANGE_TYPE:
            tid = resolved.tids[0]
            targets = [
                WriteTarget(unique_id=resolved.unique_ids[eid], element_id=eid, type_id=tid) for eid in resolved.eids
            ]
        elif tool == _DUPLICATE:
            raw = body.get("type_id", body.get("new_type_id"))
            new_id = raw if isinstance(raw, int) and not isinstance(raw, bool) else None
            if new_id is None:
                listed = await self._read("revit_list_family_types_in_family", {}, CallEffect.READ)
                rows = listed.get("items")
                wanted = str(validated.model.new_type_name)
                if isinstance(rows, list):
                    match = next(
                        (
                            row
                            for row in rows
                            if isinstance(row, Mapping)
                            and row.get("name") == wanted
                            and isinstance(row.get("type_id"), int)
                        ),
                        None,
                    )
                    if isinstance(match, Mapping):
                        new_id = int(match["type_id"])
            if new_id is None:
                raise ContractError(
                    ErrorCode.HOST_ERROR,
                    "duplicate reply has no new type id",
                    retryable=False,
                    host_code="UNEXPECTED_REPLY",
                    host_method=tool,
                )
            targets = [WriteTarget(type_id=int(new_id))]
        summary = f"{tool} ok"
        return RevitWriteResult(tool=tool, op_id=op_id, targets=targets, reply_summary=summary).model_dump(mode="json")

    def _lost_request(self, tool: str, args: _Obj, op_id: str) -> tuple[dict[str, Any], JsonValue, Path] | None:
        """Recorded request, pre-image and bound document for `op_id`; `None` when evidence is invalid (Q10)."""
        try:
            entry = self._revit_ledger.find(op_id)
            if (
                entry is None
                or entry.tool != tool
                or entry.args_sha256 != payload_sha256(dict(args))
                or not entry.pre_image_ref
                or not entry.pre_image_ref.endswith(_OBSERVED_SUFFIX)
            ):
                return None
            rule = RefRule(kinds=frozenset({_RUN_OUTPUT}), stale_ok=True)
            pre = resolve_ref(entry.pre_image_ref, rule, self._store, _untracked).value
            sent_ref = entry.pre_image_ref.removesuffix(_OBSERVED_SUFFIX) + _SENT_SUFFIX
            sent = resolve_ref(sent_ref, rule, self._store, _untracked).value
            if not isinstance(sent, dict) or "confirm" in sent:
                return None
            bound = Path(entry.target.document)
            if not str(entry.target.pipe_name) or not str(entry.target.document):
                return None
            return dict(sent), pre, bound
        except ContractError, OSError, ValueError:
            return None

    async def reconcile(self, tool: str, args: _Obj, op_id: str) -> Reconciliation:
        """Decide a lost write from the recorded request and the current state (§4.10, Q10)."""
        descriptor = self._find(tool)
        timing = self._timing()
        decision = Decision(outcome="unknown", evidence={"reason": "no valid Revit write evidence"})
        host: HostInfo | None = None
        found = self._lost_request(tool, args, op_id) if tool in _CUSTOM_WRITES else None
        if found is not None:
            sent, pre_image, bound = found
            try:
                validated = validate_call(
                    self._models[descriptor.args_model], args, source=self._store, current_revision=_untracked
                )
                resolved, provenance = self._resolve(tool, validated, args, _untracked)
                model_key = _model_key(args, None)
                binding = await self._host.binding(self._config.servers[self._server].host_key, model_key, descriptor)
                host = binding.host
                host_model = self._sent_model(tool, sent, resolved, validated)
                reconciler = RevitReconciler(
                    tolerance_ratio=self._tolerance_value(), bound_path=bound, unique_ids=dict(resolved.unique_ids)
                )
                lost = LostWrite(descriptor, host_model, binding, True, pre_image)
                try:
                    decision = await reconciler.decide(lost, self._read)
                except ContractError as error:
                    if error.detail.code not in {ErrorCode.TIMEOUT_NO_EFFECT, ErrorCode.TIMEOUT_UNKNOWN_OUTCOME}:
                        raise
                    decision = Decision(outcome="unknown", evidence={"read_failed": error.detail.code.value})
                evidence = self._store_result(
                    tool, _RUN_OUTPUT, {"value": dict(decision.evidence)}, host, provenance, timing
                )
                self._health.reconciled(op_id)
                return Reconciliation(
                    outcome=decision.outcome,
                    missing=decision.missing,
                    evidence=(Ref.model_validate({"$ref": evidence.result_id}),),
                )
            except ContractError as error:
                if error.detail.code not in {
                    ErrorCode.TIMEOUT_NO_EFFECT,
                    ErrorCode.TIMEOUT_UNKNOWN_OUTCOME,
                    ErrorCode.PRECONDITION_FAILED,
                    ErrorCode.INVALID_ARGUMENT,
                    ErrorCode.REF_NOT_FOUND,
                    ErrorCode.REF_KIND_MISMATCH,
                    ErrorCode.REF_POINTER_INVALID,
                    ErrorCode.REF_STALE,
                }:
                    raise
                decision = Decision(outcome="unknown", evidence={"reason": "no valid Revit write evidence"})
        evidence = self._store_result(tool, _RUN_OUTPUT, {"value": dict(decision.evidence)}, host, {}, timing)
        self._health.reconciled(op_id)
        return Reconciliation(
            outcome=decision.outcome,
            missing=decision.missing,
            evidence=(Ref.model_validate({"$ref": evidence.result_id}),),
        )

    def _sent_model(self, tool: str, sent: Mapping[str, Any], resolved: _Resolved, validated: Any) -> Any:
        """Host model for reconciliation from the recorded request, not the current arguments (Q10)."""
        if tool == _SET:
            eids = [int(item) for item in sent["elementIds"]] if isinstance(sent.get("elementIds"), list) else []
            if not eids:
                raise ContractError(ErrorCode.INVALID_ARGUMENT, "recorded elementIds are invalid", field="elementIds")
            return _host_tools.SetElementParameterValuesArgs(
                element_ids=eids,
                parameter_name=str(sent["parameterName"]),
                value=str(sent["value"]),
                value_type=cast(_ValueType, str(sent["valueType"])),
            )
        if tool == _SET_TYPE:
            tids = [int(item) for item in sent["typeIds"]] if isinstance(sent.get("typeIds"), list) else []
            if not tids:
                raise ContractError(ErrorCode.INVALID_ARGUMENT, "recorded typeIds are invalid", field="typeIds")
            return _host_tools.SetTypeParameterValuesArgs(
                parameter_name=str(sent["parameterName"]),
                value=str(sent["value"]),
                value_type=cast(_ValueType, str(sent["valueType"])),
                type_ids=tids,
                expected_instances=list(validated.model.expected_instances),
            )
        if tool == _SET_GUID:
            eids = [int(item) for item in sent["elementIds"]] if isinstance(sent.get("elementIds"), list) else []
            unit = sent.get("unit")
            return _host_tools.SetParameterValueByGuidArgs(
                element_ids=eids,
                guid=str(sent["guid"]),
                value=str(sent["value"]),
                value_type=cast(_ValueType, str(sent["valueType"])),
                unit=cast(_LengthUnit, str(unit)) if isinstance(unit, str) else None,
                target=cast(_GuidTarget, str(sent.get("target") or "instance")),
                all_or_nothing=True,
            )
        if tool == _DUPLICATE:
            return _host_tools.DuplicateFamilyTypeArgs(
                source_type_id=str(sent["source_type_id"]), new_type_name=str(sent["new_type_name"])
            )
        eids = [int(item) for item in sent["elementIds"]] if isinstance(sent.get("elementIds"), list) else []
        return _host_tools.ChangeElementTypeArgs(element_ids=eids, type_id=int(sent["typeId"]))
