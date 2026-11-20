"""Revit reconciliation by reading (plan 0011 T10; spec 0011 AC20, AC21, section 4.10).

`RevitReconciler` decides what became of a write cut off by a timeout from the state of its targets,
read with the same helpers as `check_model` (`_checks.expect_write`, `_observe`, `compare`), so units
and tolerance are the read-back's: floats compare within `tolerance_ratio`, the frozen basis field
`checks.readback_relative_tolerance_ratio`, never a constant here (without it a quantity is
`unknown`). Rules per tool are the table of §4.10. `reconcile` first reads `revit_get_model_metadata`
(active document is the bound one, else `unknown`). A host read that times out is `unknown`.
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


class RevitReconciler:
    """The `Reconciler` of the Revit write tools: `tolerance_ratio` is the read-back tolerance.

    `bound_path` is the document the adapter is bound to (§4.10: active document must match, else
    `unknown`). `unique_ids` maps element id → `unique_id` for `change_element_type` identity (AC12).
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
        if name != "revit_open_model" and not self._active_is_bound(meta):
            return Decision(
                outcome="unknown",
                evidence={
                    "reason": "active document is not the bound document",
                    "path": meta.get("path"),
                    "active_path": meta.get("active_path"),
                    "bound": None if self._bound is None else str(self._bound),
                },
            )
        if name == "revit_open_model":
            return await self._open_model(lost, meta)
        if name == "revit_duplicate_family_type":
            return await self._duplicate(lost, read)
        if name == "revit_change_element_type":
            return await self._change_type(lost, read)
        if name in _SETTERS:
            return await self._setters(lost, read)
        return Decision(outcome="unknown", evidence={"reason": f"no reconcile rule for {name}"})

    async def observe(self, lost: LostWrite, read: HostRead) -> dict[str, JsonValue] | None:
        """The state `lost`'s tool left as `{"observed": ...}`; `None` when there is no read-back."""
        name = lost.descriptor.name
        if name == "revit_open_model":
            meta = await read("revit_get_model_metadata", {}, CallEffect.READ)
            path = meta.get("path")
            return {"observed": {"path": path if isinstance(path, str) else None}}
        if name == "revit_duplicate_family_type":
            got = await self._observe_item(lost, read)
            if got is not None and got.get("type_id") is None and isinstance(lost.model, DuplicateFamilyTypeArgs):
                type_id = await self._type_id_by_name(read, lost.model.new_type_name)
                if type_id is not None:
                    got = dict(got)
                    got["type_id"] = type_id
            return {"observed": cast(JsonValue, got)}
        if name == "revit_change_element_type" or name in _SETTERS:
            got = await self._observe_item(lost, read)
            return {"observed": cast(JsonValue, got)}
        return None

    def _active_is_bound(self, meta: Mapping[str, Any]) -> bool:
        if self._bound is None:
            return True
        bound = str(self._bound)
        active = meta.get("active_path")
        path = meta.get("path")
        if isinstance(active, str) and active:
            return active == bound
        return isinstance(path, str) and path == bound

    async def _call(
        self, read: HostRead, tool: str, arguments: dict[str, Any], effect: CallEffect
    ) -> Mapping[str, Any]:
        body = await read(tool, arguments, effect)
        return _as_mcp(body)

    async def _observe_item(self, lost: LostWrite, read: HostRead) -> Want | None:
        item = self._expect(lost)
        try:
            return await _observe(lambda t, a, e: self._call(read, t, a, e), item)
        except KeyError, TypeError, ValueError, IndexError:
            return None

    def _expect(self, lost: LostWrite) -> Expect:
        host_args = _host_args(lost.model)
        unique_id: str | None = None
        if isinstance(lost.model, (SetElementParameterValuesArgs, SetParameterValueByGuidArgs, ChangeElementTypeArgs)):
            eid = int(lost.model.element_ids[0])
            unique_id = self._unique_ids.get(eid)
        return expect_write(lost.descriptor.name, host_args, unique_id=unique_id)

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

    async def _setters(self, lost: LostWrite, read: HostRead) -> Decision:
        """Setters: applied when every target equals the request; not_applied when every equals the pre-image."""
        item = self._expect(lost)
        got = await self._observe_item(lost, read)
        base: dict[str, JsonValue] = {
            "requested": cast(JsonValue, item.want),
            "observed": cast(JsonValue, got),
            "pre_image_known": lost.known,
            "pre_image": lost.pre_image,
        }
        shows = self._shows_requested(item, got)
        if shows is None:
            return Decision(outcome="unknown", evidence=base | {"reason": "read-back unavailable"})
        if shows:
            # Spec §4.10: checked first, so a no-op write (request equals pre-image) is applied.
            return Decision(outcome="applied", evidence=base)
        if lost.known and self._equals_pre_image(item, got, lost.pre_image):
            return Decision(outcome="not_applied", evidence=base)
        return Decision(outcome="unknown", evidence=base)

    async def _change_type(self, lost: LostWrite, read: HostRead) -> Decision:
        """change_element_type by unique_id: mixed → partial; not found by unique_id → unknown (L8)."""
        if not isinstance(lost.model, ChangeElementTypeArgs):
            return Decision(outcome="unknown", evidence={"reason": "not a change-element-type model"})
        outcomes: list[_Outcome] = []
        missing: list[str] = []
        observed_rows: list[JsonValue] = []
        requested = int(lost.model.type_id)
        for eid in lost.model.element_ids:
            uid = self._unique_ids.get(int(eid))
            host_args = build_change_element_type_args(element_ids=[int(eid)], type_id=requested)
            item = expect_write("revit_change_element_type", host_args, unique_id=uid)
            try:
                got = await _observe(lambda t, a, e: self._call(read, t, a, e), item)
            except KeyError, TypeError, ValueError, IndexError:
                got = None
            observed_rows.append(cast(JsonValue, got))
            if got is None:
                # Spec §4.10: element not found by unique_id → unknown (Revit may replace it, L8).
                outcomes.append("unknown")
                continue
            subject = uid or str(eid)
            if got.get("type_id") == requested:
                outcomes.append("applied")
                continue
            pre = lost.pre_image
            if lost.known and isinstance(pre, dict) and pre.get("type_id") == got.get("type_id"):
                outcomes.append("not_applied")
                missing.append(subject)
                continue
            if lost.known and pre is None:
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
        # Spec §4.10: `missing` lists targets only for a partial outcome.
        return Decision(
            outcome=combined,
            missing=tuple(missing) if combined == "partial" else (),
            evidence=evidence,
        )

    async def _type_id_by_name(self, read: HostRead, name: str) -> int | None:
        """The type id of `name` from `revit_list_family_types_in_family` (§4.10: id returned from the read)."""
        body = await read("revit_list_family_types_in_family", {}, CallEffect.READ)
        rows = body.get("items")
        if not isinstance(rows, list):
            return None
        match = next((r for r in rows if isinstance(r, Mapping) and r.get("name") == name), None)
        if not isinstance(match, Mapping):
            return None
        raw = match.get("type_id")
        if isinstance(raw, bool) or raw is None:
            return None
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float | str):
            return int(raw)
        return None

    async def _duplicate(self, lost: LostWrite, read: HostRead) -> Decision:
        """duplicate_family_type: applied when the name exists and was absent in the pre-image (§4.10 / AC21)."""
        if not isinstance(lost.model, DuplicateFamilyTypeArgs):
            return Decision(outcome="unknown", evidence={"reason": "not a duplicate-family-type model"})
        got = await self._observe_item(lost, read)
        if got is not None and got.get("type_id") is None:
            type_id = await self._type_id_by_name(read, lost.model.new_type_name)
            if type_id is not None:
                got = dict(got)
                got["type_id"] = type_id
        base: dict[str, JsonValue] = {
            "requested": {"name": lost.model.new_type_name},
            "observed": cast(JsonValue, got),
            "pre_image_known": lost.known,
            "pre_image": lost.pre_image,
        }
        present = got is not None and got.get("name") == lost.model.new_type_name
        if present:
            if not lost.known:
                # Spec §4.10: present but no pre-image to confirm it was absent → unknown.
                return Decision(outcome="unknown", evidence=base | {"reason": "pre_image not known"})
            if lost.pre_image is None:
                return Decision(outcome="applied", evidence=base)
            # Present with other values / already existed before → unknown (AC21).
            return Decision(outcome="unknown", evidence=base | {"reason": "type present with other values"})
        if lost.known and lost.pre_image is None:
            return Decision(outcome="not_applied", evidence=base)
        return Decision(outcome="unknown", evidence=base)

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
        if isinstance(path, str) and path == requested:
            return Decision(outcome="applied", evidence=evidence)
        if isinstance(path, str) and path != requested:
            # Spec §4.10: the path is another document → not_applied.
            return Decision(outcome="not_applied", evidence=evidence)
        return Decision(outcome="unknown", evidence=evidence)

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
