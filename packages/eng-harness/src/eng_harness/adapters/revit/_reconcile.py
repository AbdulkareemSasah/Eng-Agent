"""Revit reconciliation by reading (plan 0011 T10; spec 0011 AC20, AC21, section 4.10).

`RevitReconciler` decides what became of a write cut off by a timeout from the state of its targets,
read with the same helpers as `check_model` (`_checks.expect_write`, `_observe`, `compare`), so units
and tolerance are the read-back's: floats compare within `tolerance_ratio`, the frozen basis field
`checks.readback_relative_tolerance_ratio`, never a constant here (without it a quantity is
`unknown`). Rules per tool are the table of §4.10. `reconcile` first reads `revit_get_model_metadata`
(active document is the bound one, else `unknown`). A host read that times out, fails, is truncated
or cannot be compared is `unknown` — never a certain `applied` or `not_applied`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast

from eng_contract.params import ParamModel
from pydantic import JsonValue

from eng_harness.adapters._toolport import Decision, HostRead, LostWrite
from eng_harness.adapters.revit._checks import Expect, Want, _observe, compare, expect_write
from eng_harness.adapters.revit._state import revit_document_loaded
from eng_harness.adapters.revit._tools import (
    ChangeElementTypeArgs,
    DuplicateFamilyTypeArgs,
    OpenModelArgs,
    SetElementParameterValuesArgs,
    SetParameterValueByGuidArgs,
    SetTypeParameterValuesArgs,
    build_change_element_type_args,
    build_duplicate_family_type_args,
    build_set_element_parameter_values_args,
    build_set_parameter_value_by_guid_args,
    build_set_type_parameter_values_args,
)
from eng_harness.servers import CallEffect

__all__ = ["RevitReconciler"]

_Outcome = Literal["applied", "not_applied", "partial", "unknown"]
_SETTERS = frozenset(
    {
        "revit_set_element_parameter_values",
        "revit_set_type_parameter_values",
        "revit_set_parameter_value_by_guid",
    }
)
_UNAVAILABLE = "READBACK_UNAVAILABLE"
_PAGE = 100  # host default max_types for revit_list_family_types_in_family (S-12 / ListFamilyTypesInFamilyArgs)
# Adapter paging guard, not an engineering number: stop a host that keeps answering `truncated`
# from looping forever; reaching it is a read issue (unknown, §4.10).
_MAX_PAGES = 50


class _ReadError(Exception):
    """A host read that failed, was truncated or could not be compared (§4.10 → unknown)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _host_args(model: ParamModel) -> dict[str, JsonValue]:
    """Canonical ParamModel → host arguments (camelCase) for `expect_write`."""
    if isinstance(model, SetElementParameterValuesArgs):
        return build_set_element_parameter_values_args(
            element_ids=model.element_ids,
            parameter_name=model.parameter_name,
            value=model.value,
            value_type=model.value_type,
        )
    if isinstance(model, SetTypeParameterValuesArgs):
        return build_set_type_parameter_values_args(
            type_ids=list(model.type_ids or ()),
            parameter_name=model.parameter_name,
            value=model.value,
            value_type=model.value_type,
            expected_instances=list(model.expected_instances),
            element_ids=list(model.element_ids) if model.element_ids is not None else None,
        )
    if isinstance(model, SetParameterValueByGuidArgs):
        return build_set_parameter_value_by_guid_args(
            element_ids=model.element_ids,
            guid=model.guid,
            value=model.value,
            value_type=model.value_type,
            unit=model.unit,
            target=model.target,
            all_or_nothing=model.all_or_nothing,
        )
    if isinstance(model, ChangeElementTypeArgs):
        return build_change_element_type_args(element_ids=model.element_ids, type_id=model.type_id)
    if isinstance(model, DuplicateFamilyTypeArgs):
        return build_duplicate_family_type_args(
            source_type_id=model.source_type_id,
            new_type_name=model.new_type_name,
        )
    if isinstance(model, OpenModelArgs):
        return {"path": model.path, "activate": model.activate}
    raise TypeError(f"no host args for {type(model).__name__}")


def _as_mcp(body: Mapping[str, Any]) -> dict[str, Any]:
    """Wrap a parsed host body so `_observe` can run `parse_revit_reply` on it."""
    return {"content": [{"type": "text", "text": json.dumps(dict(body))}], "isError": False}


def _as_int(raw: object) -> int | None:
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float | str):
        try:
            return int(raw)
        except TypeError, ValueError:
            return None
    return None


class RevitReconciler:
    """The `Reconciler` of the Revit write tools: `tolerance_ratio` is the read-back tolerance.

    `bound_path` is the document the adapter is bound to (§4.10: active document must match, else
    `unknown`). When it is missing the bound document cannot be checked, so non-`open_model` writes
    are `unknown`. `unique_ids` maps element id → `unique_id` for `change_element_type` identity (AC12).
    """

    def __init__(
        self,
        *,
        tolerance_ratio: float | None,
        bound_path: Path | None = None,
        unique_ids: Mapping[int, str] | None = None,
    ) -> None:
        self._tolerance = tolerance_ratio
        self._bound = bound_path
        self._unique_ids = dict(unique_ids or {})

    async def decide(self, lost: LostWrite, read: HostRead) -> Decision:
        """The outcome of `lost` (spec 0011 §4.10); the evidence is what was read."""
        name = lost.descriptor.name
        meta = await read("revit_get_model_metadata", {}, CallEffect.READ)
        # open_model changes which document is active; its own path rules decide (§4.10 table).
        if name != "revit_open_model":
            if self._bound is None:
                return Decision(
                    outcome="unknown",
                    evidence={"reason": "bound document is not known"},
                )
            if not self._active_is_bound(meta):
                return Decision(
                    outcome="unknown",
                    evidence={
                        "reason": "active document is not the bound document",
                        "path": meta.get("path"),
                        "bound": str(self._bound),
                    },
                )
        try:
            if name == "revit_open_model":
                return await self._open_model(lost, meta)
            if name == "revit_duplicate_family_type":
                return await self._duplicate(lost, read)
            if name == "revit_change_element_type":
                return await self._change_type(lost, read)
            if name in _SETTERS:
                return await self._setters(lost, read)
        except _ReadError as exc:
            return Decision(outcome="unknown", evidence={"reason": exc.reason})
        return Decision(outcome="unknown", evidence={"reason": f"no reconcile rule for {name}"})

    async def observe(self, lost: LostWrite, read: HostRead) -> dict[str, JsonValue] | None:
        """The state `lost`'s tool left as `{"observed": ...}`; `None` when there is no read-back.

        A failed or incomplete read returns `None` so the ledger does not store unreadable state as
        a known absence (§4.10).
        """
        name = lost.descriptor.name
        try:
            if name == "revit_open_model":
                meta = await read("revit_get_model_metadata", {}, CallEffect.READ)
                path = meta.get("path")
                return {"observed": {"path": path if isinstance(path, str) else None}}
            if name == "revit_duplicate_family_type":
                if not isinstance(lost.model, DuplicateFamilyTypeArgs):
                    return None
                got = await self._duplicate_observe(lost.model, read)
                return {"observed": cast(JsonValue, got)}
            if name == "revit_change_element_type":
                if not isinstance(lost.model, ChangeElementTypeArgs):
                    return None
                by_element = await self._change_type_observe(lost.model, read)
                return {"observed": cast(JsonValue, {"by_element": by_element})}
            if name in _SETTERS:
                by_target = await self._setters_observe(lost, read)
                return {"observed": cast(JsonValue, {"by_target": by_target})}
        except _ReadError:
            return None
        return None

    def _active_is_bound(self, meta: Mapping[str, Any]) -> bool:
        # Spec 0011 §4.10 / AC13: get_model_metadata `path` (inventory key), Windows path semantics.
        path = meta.get("path")
        return self._bound is not None and revit_document_loaded(path if isinstance(path, str) else None, self._bound)

    async def _call(
        self, read: HostRead, tool: str, arguments: dict[str, Any], effect: CallEffect
    ) -> Mapping[str, Any]:
        body = await read(tool, arguments, effect)
        if not isinstance(body, Mapping):
            raise _ReadError(f"{tool} reply is not a mapping")
        if body.get("truncated") is True:
            raise _ReadError(f"{tool} reply was truncated")
        return _as_mcp(body)

    def _shows_requested(self, item: Expect, got: Want | None) -> bool | None:
        issue = compare(item, got, self._tolerance)
        if issue is not None and issue.code == _UNAVAILABLE:
            return None
        return issue is None

    def _equals_pre_image(self, item: Expect, got: Want | None, pre_image: JsonValue) -> bool:
        if pre_image is None:
            return got is None
        if not isinstance(pre_image, dict):
            return False
        pre_item = Expect(
            item.helper, item.subject, cast(Want | None, dict(pre_image)), tool=item.tool, host_args=item.host_args
        )
        return compare(pre_item, got, self._tolerance) is None

    def _setter_targets(self, lost: LostWrite) -> list[int]:
        model = lost.model
        if isinstance(model, SetTypeParameterValuesArgs):
            return [int(tid) for tid in (model.type_ids or ())]
        if isinstance(model, (SetElementParameterValuesArgs, SetParameterValueByGuidArgs)):
            return [int(eid) for eid in model.element_ids]
        return []

    def _expect_one(self, lost: LostWrite, target_id: int) -> Expect:
        model = lost.model
        unique_id: str | None = None
        if isinstance(model, SetElementParameterValuesArgs):
            host_args = build_set_element_parameter_values_args(
                element_ids=[target_id],
                parameter_name=model.parameter_name,
                value=model.value,
                value_type=model.value_type,
            )
            unique_id = self._unique_ids.get(target_id)
        elif isinstance(model, SetParameterValueByGuidArgs):
            host_args = build_set_parameter_value_by_guid_args(
                element_ids=[target_id],
                guid=model.guid,
                value=model.value,
                value_type=model.value_type,
                unit=model.unit,
                target=model.target,
                all_or_nothing=model.all_or_nothing,
            )
            unique_id = self._unique_ids.get(target_id)
        elif isinstance(model, SetTypeParameterValuesArgs):
            host_args = build_set_type_parameter_values_args(
                type_ids=[target_id],
                parameter_name=model.parameter_name,
                value=model.value,
                value_type=model.value_type,
                expected_instances=list(model.expected_instances),
                element_ids=list(model.element_ids) if model.element_ids is not None else None,
            )
        else:
            raise TypeError(f"not a setter model: {type(model).__name__}")
        return expect_write(lost.descriptor.name, host_args, unique_id=unique_id)

    def _pre_for_target(self, lost: LostWrite, target_id: int) -> JsonValue:
        """Per-target pre-image; a single want dict applies to every target (homogeneous batch)."""
        pre = lost.pre_image
        if not isinstance(pre, dict):
            return pre
        by_target = pre.get("by_target")
        if isinstance(by_target, dict):
            return by_target.get(str(target_id))
        return pre

    async def _observe_one(self, read: HostRead, item: Expect) -> Want | None:
        try:
            return await _observe(lambda t, a, e: self._call(read, t, a, e), item)
        except _ReadError:
            raise
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise _ReadError(f"read-back of {item.helper} failed: {exc}") from exc

    async def _setters_observe(self, lost: LostWrite, read: HostRead) -> dict[str, JsonValue]:
        rows: dict[str, JsonValue] = {}
        for tid in self._setter_targets(lost):
            item = self._expect_one(lost, tid)
            got = await self._observe_one(read, item)
            rows[str(tid)] = cast(JsonValue, got)
        return rows

    async def _setters(self, lost: LostWrite, read: HostRead) -> Decision:
        """Setters: every target equals the request → applied; every equals pre-image → not_applied; mixed → partial."""
        targets = self._setter_targets(lost)
        if not targets:
            return Decision(outcome="unknown", evidence={"reason": "no setter targets"})
        outcomes: list[_Outcome] = []
        missing: list[str] = []
        observed_rows: dict[str, JsonValue] = {}
        requested: Want | None = None
        for tid in targets:
            item = self._expect_one(lost, tid)
            if requested is None:
                requested = item.want
            subject = item.subject.id or str(tid)
            try:
                got = await self._observe_one(read, item)
            except _ReadError:
                outcomes.append("unknown")
                observed_rows[str(tid)] = None
                continue
            observed_rows[str(tid)] = cast(JsonValue, got)
            shows = self._shows_requested(item, got)
            if shows is None:
                outcomes.append("unknown")
                continue
            if shows:
                # Spec §4.10: checked first, so a no-op write (request equals pre-image) is applied.
                outcomes.append("applied")
                continue
            if not lost.known:
                outcomes.append("unknown")
                continue
            pre = self._pre_for_target(lost, tid)
            if self._equals_pre_image(item, got, pre):
                outcomes.append("not_applied")
                missing.append(subject)
                continue
            outcomes.append("unknown")
        combined = self._combine(outcomes)
        evidence: dict[str, JsonValue] = {
            "requested": cast(JsonValue, requested),
            "observed": cast(JsonValue, observed_rows),
            "pre_image_known": lost.known,
            "pre_image": lost.pre_image,
        }
        return Decision(
            outcome=combined,
            missing=tuple(missing) if combined == "partial" else (),
            evidence=evidence,
        )

    def _pre_type_for_element(self, lost: LostWrite, eid: int) -> int | object | None:
        """Return the pre-image type_id for `eid`, or a sentinel when it cannot be compared.

        `None` means a known absence (element had no readable type). The sentinel `_NO_PRE` means
        the pre-image does not give a type for this element, so not_applied cannot be claimed.
        """
        pre = lost.pre_image
        if not lost.known:
            return _NO_PRE
        if pre is None:
            # Known absence for the whole write: no per-element type to compare (§4.10 needs each).
            return _NO_PRE
        if not isinstance(pre, dict):
            return _NO_PRE
        by_element = pre.get("by_element")
        if isinstance(by_element, dict):
            row = by_element.get(str(eid))
            if row is None:
                return _NO_PRE
            if not isinstance(row, dict):
                return _NO_PRE
            if "type_id" not in row:
                return _NO_PRE
            raw = row.get("type_id")
            if raw is None:
                return None
            parsed = _as_int(raw)
            return parsed if parsed is not None else _NO_PRE
        if "type_id" in pre:
            raw = pre.get("type_id")
            if raw is None:
                return None
            parsed = _as_int(raw)
            return parsed if parsed is not None else _NO_PRE
        return _NO_PRE

    async def _change_type_observe(self, model: ChangeElementTypeArgs, read: HostRead) -> dict[str, JsonValue]:
        rows: dict[str, JsonValue] = {}
        for eid in model.element_ids:
            uid = self._unique_ids.get(int(eid))
            host_args = build_change_element_type_args(element_ids=[int(eid)], type_id=int(model.type_id))
            item = expect_write("revit_change_element_type", host_args, unique_id=uid)
            got = await self._observe_one(read, item)
            rows[str(int(eid))] = cast(JsonValue, got)
        return rows

    async def _change_type(self, lost: LostWrite, read: HostRead) -> Decision:
        """change_element_type by unique_id: mixed → partial; not found by unique_id → unknown (L8)."""
        if not isinstance(lost.model, ChangeElementTypeArgs):
            return Decision(outcome="unknown", evidence={"reason": "not a change-element-type model"})
        outcomes: list[_Outcome] = []
        missing: list[str] = []
        observed_rows: dict[str, JsonValue] = {}
        requested = int(lost.model.type_id)
        for eid in lost.model.element_ids:
            uid = self._unique_ids.get(int(eid))
            host_args = build_change_element_type_args(element_ids=[int(eid)], type_id=requested)
            item = expect_write("revit_change_element_type", host_args, unique_id=uid)
            try:
                got = await self._observe_one(read, item)
            except _ReadError:
                outcomes.append("unknown")
                observed_rows[str(int(eid))] = None
                continue
            observed_rows[str(int(eid))] = cast(JsonValue, got)
            if got is None:
                # Spec §4.10: element not found by unique_id → unknown (Revit may replace it, L8).
                outcomes.append("unknown")
                continue
            subject = uid or str(eid)
            if got.get("type_id") == requested:
                outcomes.append("applied")
                continue
            pre_type = self._pre_type_for_element(lost, int(eid))
            if pre_type is _NO_PRE:
                outcomes.append("unknown")
                continue
            if pre_type is None:
                # Known pre-image of None: no type to compare → unknown (§4.10: every element has its pre-image type).
                outcomes.append("unknown")
                continue
            if got.get("type_id") == pre_type:
                outcomes.append("not_applied")
                missing.append(subject)
                continue
            outcomes.append("unknown")
        combined = self._combine(outcomes)
        evidence: dict[str, JsonValue] = {
            "requested": {"type_id": requested},
            "observed": cast(JsonValue, observed_rows),
            "pre_image_known": lost.known,
            "pre_image": lost.pre_image,
        }
        return Decision(
            outcome=combined,
            missing=tuple(missing) if combined == "partial" else (),
            evidence=evidence,
        )

    async def _list_family_types(
        self,
        read: HostRead,
        *,
        family_id: str | None = None,
        family_name: str | None = None,
    ) -> list[Mapping[str, Any]]:
        """Page `revit_list_family_types_in_family` until complete; truncated mid-page is a read issue."""
        collected: list[Mapping[str, Any]] = []
        start = 0
        pages = 0
        while True:
            arguments: dict[str, Any] = {
                "include_parameter_values": True,
                "start_index": start,
                "max_types": _PAGE,
            }
            if family_id is not None:
                arguments["family_id"] = family_id
            if family_name is not None:
                arguments["family_name"] = family_name
            body = await read("revit_list_family_types_in_family", arguments, CallEffect.READ)
            if not isinstance(body, Mapping):
                raise _ReadError("revit_list_family_types_in_family reply is not a mapping")
            rows = body.get("items")
            if not isinstance(rows, list):
                raise _ReadError("revit_list_family_types_in_family items are not a list")
            for row in rows:
                if isinstance(row, Mapping):
                    collected.append(row)
            truncated = body.get("truncated") is True
            if not truncated:
                return collected
            # Incomplete page: never treat a truncated reply as a complete absence (§4.10).
            if not rows:
                raise _ReadError("revit_list_family_types_in_family truncated with no rows")
            pages += 1
            if pages > _MAX_PAGES:
                raise _ReadError("revit_list_family_types_in_family paging did not complete")
            start += len(rows)

    async def _source_family(self, read: HostRead, source_type_id: str | int) -> tuple[str | None, str | None]:
        """Family id/name of the source type (§4.10: exists in the family)."""
        wanted = _as_int(source_type_id)
        if wanted is None:
            raise _ReadError("source_type_id is not an integer")
        rows = await self._list_family_types(read)
        match = next((r for r in rows if _as_int(r.get("type_id")) == wanted), None)
        if match is None:
            raise _ReadError(f"source type {wanted} was not found in the family list")
        family_id = match.get("family_id")
        family_name = match.get("family")
        # Inventory schema: `family_id` of revit_list_family_types_in_family is a string.
        fid: str | None = (
            str(family_id) if isinstance(family_id, (int, str)) and not isinstance(family_id, bool) else None
        )
        fname = family_name if isinstance(family_name, str) and family_name else None
        if fid is None and fname is None:
            raise _ReadError(f"source type {wanted} has no family id or name")
        return fid, fname

    async def _type_row_by_name(
        self,
        read: HostRead,
        name: str,
        *,
        family_id: str | None,
        family_name: str | None,
    ) -> Mapping[str, Any] | None:
        rows = await self._list_family_types(read, family_id=family_id, family_name=family_name)
        return next((r for r in rows if isinstance(r, Mapping) and r.get("name") == name), None)

    async def _type_parameters(self, read: HostRead, type_id: int) -> list[Mapping[str, Any]]:
        body = await read("revit_get_type_parameters", {"typeIds": [type_id]}, CallEffect.READ)
        if not isinstance(body, Mapping):
            raise _ReadError("revit_get_type_parameters reply is not a mapping")
        if body.get("truncated") is True:
            raise _ReadError("revit_get_type_parameters reply was truncated")
        items = body.get("items")
        if not isinstance(items, list) or not items:
            raise _ReadError("revit_get_type_parameters returned no items")
        first = items[0]
        if not isinstance(first, Mapping):
            raise _ReadError("revit_get_type_parameters item is not a mapping")
        params = first.get("parameters")
        if not isinstance(params, list):
            raise _ReadError("revit_get_type_parameters parameters are not a list")
        return [p for p in params if isinstance(p, Mapping)]

    @staticmethod
    def _param_fingerprint(params: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Comparable name → rawValue map (duplicate has no overrides, §4.8)."""
        out: dict[str, Any] = {}
        for row in params:
            name = row.get("name")
            if not isinstance(name, str) or not name:
                continue
            out[name] = row.get("rawValue", row.get("value"))
        return out

    async def _duplicate_observe(self, model: DuplicateFamilyTypeArgs, read: HostRead) -> Want | None:
        family_id, family_name = await self._source_family(read, model.source_type_id)
        match = await self._type_row_by_name(read, model.new_type_name, family_id=family_id, family_name=family_name)
        if match is None:
            return None
        type_id = _as_int(match.get("type_id"))
        if type_id is None:
            raise _ReadError(f"type {model.new_type_name!r} has no type_id")
        # Confirm parameters are readable (failed second read → unknown, not absent).
        await self._type_parameters(read, type_id)
        return {"name": str(match["name"]), "type_id": type_id, "parameters_present": True}

    async def _duplicate(self, lost: LostWrite, read: HostRead) -> Decision:
        """duplicate_family_type: applied when the name exists, was absent, and matches the source (§4.10 / AC21)."""
        if not isinstance(lost.model, DuplicateFamilyTypeArgs):
            return Decision(outcome="unknown", evidence={"reason": "not a duplicate-family-type model"})
        family_id, family_name = await self._source_family(read, lost.model.source_type_id)
        match = await self._type_row_by_name(
            read, lost.model.new_type_name, family_id=family_id, family_name=family_name
        )
        base: dict[str, JsonValue] = {
            "requested": {"name": lost.model.new_type_name},
            "pre_image_known": lost.known,
            "pre_image": lost.pre_image,
            "family_id": family_id,
            "family_name": family_name,
        }
        if match is None:
            got = None
            base["observed"] = None
            if lost.known and lost.pre_image is None:
                return Decision(outcome="not_applied", evidence=base)
            return Decision(outcome="unknown", evidence=base)
        type_id = _as_int(match.get("type_id"))
        if type_id is None:
            raise _ReadError(f"type {lost.model.new_type_name!r} has no type_id")
        got = {"name": str(match["name"]), "type_id": type_id, "parameters_present": True}
        base["observed"] = cast(JsonValue, got)
        if not lost.known:
            return Decision(outcome="unknown", evidence=base | {"reason": "pre_image not known"})
        if lost.pre_image is not None:
            # Already present before the write → unknown (AC21 / §4.10 present with other values).
            return Decision(outcome="unknown", evidence=base | {"reason": "type present with other values"})
        # Absent in pre-image and present now: compare parameters with the source (AC21 conservative).
        source_id = _as_int(lost.model.source_type_id)
        if source_id is None:
            raise _ReadError("source_type_id is not an integer")
        source_params = await self._type_parameters(read, source_id)
        new_params = await self._type_parameters(read, type_id)
        if self._param_fingerprint(source_params) != self._param_fingerprint(new_params):
            return Decision(
                outcome="unknown",
                evidence=base | {"reason": "type exists with other parameters"},
            )
        return Decision(outcome="applied", evidence=base)

    async def _open_model(self, lost: LostWrite, meta: Mapping[str, Any]) -> Decision:
        """revit_open_model: applied when metadata path equals the file; another document → not_applied."""
        if not isinstance(lost.model, OpenModelArgs):
            return Decision(outcome="unknown", evidence={"reason": "not an open-model model"})
        path = meta.get("path")
        requested = lost.model.path
        evidence: dict[str, JsonValue] = {
            "requested": {"path": requested},
            "observed": {"path": path if isinstance(path, str) else None},
            "pre_image_known": lost.known,
            "pre_image": lost.pre_image,
            "path": path if isinstance(path, str) else None,
        }
        if not isinstance(path, str) or not path:
            # No document path read: cannot show another document is active (§4.10 otherwise unknown).
            return Decision(outcome="unknown", evidence=evidence)
        if revit_document_loaded(path, Path(requested)):
            return Decision(outcome="applied", evidence=evidence)
        # Spec §4.10: the path is another document → not_applied.
        return Decision(outcome="not_applied", evidence=evidence)

    @staticmethod
    def _combine(outcomes: Sequence[_Outcome]) -> _Outcome:
        if not outcomes:
            return "unknown"
        if all(o == "applied" for o in outcomes):
            return "applied"
        if all(o == "not_applied" for o in outcomes):
            return "not_applied"
        if any(o == "unknown" for o in outcomes):
            return "unknown"
        if "applied" in outcomes and "not_applied" in outcomes:
            return "partial"
        return "unknown"


_NO_PRE = object()
