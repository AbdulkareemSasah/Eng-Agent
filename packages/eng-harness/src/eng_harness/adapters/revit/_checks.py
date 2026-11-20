"""Revit read-back helpers and `check_model` (plan 0011 T9; spec 0011 AC19, sections 4.4, 4.8).

Every item written since the last check is read back with the §4.4 tool and compared with the requested
state: a length within `ReadBack.tolerance_ratio` (the frozen basis field
`checks.readback_relative_tolerance_ratio`, never a constant here; without it a quantity is
`READBACK_UNAVAILABLE`), an integer, string, element id or type assignment for equality. Integrity
checks need no tolerance: `ELEMENT_MISSING`, `TYPE_UNDEFINED`, `REVIT_WARNINGS_INCREASED`,
`MODEL_UNSAVED` (info, always, R-G1).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope, make_success
from eng_contract.errors import ContractError
from eng_contract.ids import SystemClock
from eng_contract.issues import CheckModelSummary, ModelIssue, Severity
from eng_contract.kinds.issues import ModelCheck
from eng_contract.store import ResultStore
from eng_contract.verdicts import Subject, SubjectKind

from eng_harness.adapters.revit._replies import parse_revit_reply
from eng_harness.adapters.revit._units import convert_parameter
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect

__all__ = [
    "Expect",
    "ReadBack",
    "WrittenItems",
    "check_model",
    "compare",
    "expect_write",
    "integrity",
]

Want = dict[str, Any]
HostCall = Callable[[str, dict[str, Any], CallEffect], Awaitable[Mapping[str, Any]]]
_ERROR = Severity.ERROR

# Spec 0011 section 4.4: read-back tools per write tool (duplicate has two).
_READBACK_TOOL: dict[str, str] = {
    "revit_set_element_parameter_values": "revit_get_element_parameters",
    "revit_set_type_parameter_values": "revit_get_type_parameters",
    "revit_set_parameter_value_by_guid": "revit_get_element_parameters",
    "revit_change_element_type": "revit_get_element_details",
    "revit_duplicate_family_type": "revit_list_family_types_in_family",
}


@dataclass(frozen=True)
class Expect:
    """One written item: the read-back helper, its subject and the wanted fields (contract units)."""

    helper: str
    subject: Subject
    want: Want | None
    tool: str = ""
    host_args: Mapping[str, Any] = field(default_factory=dict)
    # Second read-back for duplicate_family_type (spec 0011 §4.4 / L-B232-1).
    second_helper: str | None = None


@dataclass
class WrittenItems:
    """The items written since the last check, per model key: `prepare` before the send, `commit` after."""

    def __init__(self) -> None:
        self._prepared: dict[str, Expect] = {}
        self._written: dict[str, list[Expect]] = {}

    def prepare(self, key: str, item: Expect) -> None:
        self._prepared[key] = item

    def commit(self, key: str) -> None:
        item = self._prepared.pop(key, None)
        if item is not None:
            self._written.setdefault(key, []).append(item)

    def items(self, key: str) -> list[Expect]:
        return list(self._written.get(key, ()))

    def clear(self, key: str) -> None:
        self._written.pop(key, None)


@dataclass(frozen=True)
class ReadBack:
    """What `check_model` needs: the book of written items, the result store, the server build, tolerance.

    `tolerance_ratio` is the frozen value of `checks.readback_relative_tolerance_ratio` (0002 G-2); `None`
    while the workflow gives none.
    """

    written: WrittenItems
    store: ResultStore
    check: ServerCheck
    tolerance_ratio: float | None = None


def expect_write(tool: str, host_args: Mapping[str, Any], *, unique_id: str | None = None) -> Expect:
    """Build the read-back expectation for one §4.8 write from its host arguments (AC19)."""
    helper = _READBACK_TOOL.get(tool)
    if helper is None:
        raise ValueError(f"no read-back helper for {tool}")

    if tool == "revit_set_element_parameter_values":
        eid = int(host_args["elementIds"][0])
        name = str(host_args["parameterName"])
        want = _want_parameter(host_args, name)
        subject = Subject(kind=SubjectKind.FRAME, id=unique_id or str(eid))
        return Expect(helper, subject, want, tool=tool, host_args=dict(host_args))

    if tool == "revit_set_type_parameter_values":
        tid = int(host_args["typeIds"][0])
        name = str(host_args["parameterName"])
        want = _want_parameter(host_args, name)
        subject = Subject(kind=SubjectKind.SECTION, id=str(tid))
        return Expect(helper, subject, want, tool=tool, host_args=dict(host_args))

    if tool == "revit_set_parameter_value_by_guid":
        eid = int(host_args["elementIds"][0])
        guid = str(host_args["guid"])
        want = _want_parameter(host_args, guid, key="guid")
        subject = Subject(kind=SubjectKind.FRAME, id=unique_id or str(eid))
        return Expect(helper, subject, want, tool=tool, host_args=dict(host_args))

    if tool == "revit_change_element_type":
        eid = int(host_args["elementIds"][0])
        want = {"type_id": int(host_args["typeId"])}
        subject = Subject(kind=SubjectKind.FRAME, id=unique_id or str(eid))
        return Expect(helper, subject, want, tool=tool, host_args=dict(host_args))

    # duplicate_family_type: list types by name, then get_type_parameters (spec 0011 §4.4).
    name = str(host_args["new_type_name"])
    subject = Subject(kind=SubjectKind.SECTION, id=name)
    return Expect(
        helper,
        subject,
        {"name": name},
        tool=tool,
        host_args=dict(host_args),
        second_helper="revit_get_type_parameters",
    )


def _want_parameter(host_args: Mapping[str, Any], field_name: str, *, key: str = "name") -> Want:
    value_type = str(host_args.get("valueType") or "")
    raw = host_args["value"]
    if value_type == "double":
        return {field_name: float(raw)}
    if value_type == "integer":
        return {field_name: int(raw)}
    if value_type == "elementId":
        return {field_name: int(raw)}
    return {field_name: str(raw)}


def _differs(got: Want, want: Want, tolerance: float) -> bool:
    for name, wanted in want.items():
        seen = got.get(name)
        if isinstance(wanted, float):
            if not isinstance(seen, int | float) or not abs(float(seen) - wanted) <= tolerance * abs(wanted):
                return True
        elif seen != wanted:
            return True
    return False


def _param_row(parameters: Sequence[Mapping[str, Any]], *, name: str | None, guid: str | None) -> dict[str, Any] | None:
    for row in parameters:
        if guid is not None and row.get("guid") == guid:
            return dict(row)
        if name is not None and row.get("name") == name:
            return dict(row)
    return None


def _as_raw_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Prefer `rawValue` (spec 0011 §4.6); fall back to `value` for older fake rows."""
    data = dict(row)
    if "rawValue" not in data and "value" in data:
        data["rawValue"] = data["value"]
    return data


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return None


async def _observe(call: HostCall, item: Expect) -> Want | None:
    """Read the written item back; `None` when absent."""
    args = item.host_args
    if item.helper == "revit_get_element_parameters":
        reply = await call("revit_get_element_parameters", {"elementIds": list(args["elementIds"])}, CallEffect.READ)
        body = parse_revit_reply(dict(reply)).body
        items = body.get("items")
        if not isinstance(items, list) or not items:
            return None
        first = items[0]
        if not isinstance(first, Mapping):
            return None
        params = first.get("parameters")
        if not isinstance(params, list):
            return None
        guid = str(args["guid"]) if item.tool == "revit_set_parameter_value_by_guid" else None
        name = None if guid is not None else str(args["parameterName"])
        row = _param_row([p for p in params if isinstance(p, Mapping)], name=name, guid=guid)
        if row is None:
            return None
        return _read_param_want(row, item)

    if item.helper == "revit_get_type_parameters":
        type_ids = list(args.get("typeIds") or [args.get("source_type_id")])
        reply = await call("revit_get_type_parameters", {"typeIds": [int(x) for x in type_ids]}, CallEffect.READ)
        body = parse_revit_reply(dict(reply)).body
        items = body.get("items")
        if not isinstance(items, list) or not items:
            return None
        first = items[0]
        if not isinstance(first, Mapping):
            return None
        params = first.get("parameters")
        if not isinstance(params, list):
            return None
        row = _param_row(
            [p for p in params if isinstance(p, Mapping)],
            name=str(args["parameterName"]),
            guid=None,
        )
        if row is None:
            return None
        return _read_param_want(row, item)

    if item.helper == "revit_get_element_details":
        try:
            reply = await call("revit_get_element_details", {"elementIds": list(args["elementIds"])}, CallEffect.READ)
            body = parse_revit_reply(dict(reply)).body
        except ContractError:
            # Element replaced / not found (fault element_replaced): absent for read-back (AC19).
            return None
        items = body.get("items")
        if not isinstance(items, list) or not items:
            return None
        first = items[0]
        if not isinstance(first, Mapping):
            return None
        # Identity after change_element_type is by unique_id (AC19); missing unique_id → absent.
        if item.subject.id and first.get("unique_id") != item.subject.id:
            return None
        type_id = _as_int(first.get("type_id"))
        return None if type_id is None else {"type_id": type_id}

    if item.helper == "revit_list_family_types_in_family":
        # Host args carry source_type_id only; list without a family filter and match by name.
        reply = await call("revit_list_family_types_in_family", {}, CallEffect.READ)
        body = parse_revit_reply(dict(reply)).body
        rows = body.get("items")
        if not isinstance(rows, list):
            return None
        wanted_name = str(args["new_type_name"])
        match = next((r for r in rows if isinstance(r, Mapping) and r.get("name") == wanted_name), None)
        if match is None:
            return None
        type_id = _as_int(match.get("type_id"))
        if type_id is None:
            return None
        got: Want = {"name": str(match["name"])}
        if item.second_helper == "revit_get_type_parameters":
            # L-B232-1 / spec 0011 §4.4: second read-back of the new type's parameters.
            params_reply = await call(
                "revit_get_type_parameters",
                {"typeIds": [type_id]},
                CallEffect.READ,
            )
            params_body = parse_revit_reply(dict(params_reply)).body
            param_items = params_body.get("items")
            if not isinstance(param_items, list) or not param_items:
                raise KeyError("second read-back of duplicate_family_type returned no parameters")
            got["parameters_present"] = True
        return got

    raise KeyError(f"unknown read-back helper {item.helper}")


def _read_param_want(row: Mapping[str, Any], item: Expect) -> Want:
    if item.want is None:
        raise ValueError("expect with no want cannot be read as a parameter")
    field_name = next(iter(item.want))
    wanted = item.want[field_name]
    raw_row = _as_raw_row(row)
    if isinstance(wanted, float):
        converted, issue = convert_parameter(raw_row, subject=item.subject)
        if issue is not None or converted is None:
            raise ValueError(issue.message if issue is not None else "no converted value")
        return {field_name: float(converted)}
    if isinstance(wanted, int) and not isinstance(wanted, bool):
        value = raw_row.get("rawValue", raw_row.get("value"))
        parsed = _as_int(value)
        if parsed is None:
            raise ValueError(f"parameter {field_name} is not an integer")
        return {field_name: parsed}
    value = raw_row.get("rawValue", raw_row.get("value"))
    return {field_name: str(value)}


def compare(item: Expect, got: Want | None, tolerance: float | None) -> ModelIssue | None:
    """The read-back issue of one written item, or `None` when it shows the requested state."""

    def issue(code: str, message: str, severity: Severity = _ERROR) -> ModelIssue:
        return ModelIssue(severity=severity, code=code, subject=item.subject, message=message)

    name = item.subject.id
    if item.want is None:
        return None if got is None else issue("READBACK_MISMATCH", f"{name} is still present")
    if got is None:
        return issue("READBACK_MISMATCH", f"{name} is absent")
    if tolerance is None and any(isinstance(wanted, float) for wanted in item.want.values()):
        return issue("READBACK_UNAVAILABLE", "no read-back tolerance (checks.readback_relative_tolerance_ratio)")
    if _differs(got, item.want, tolerance or 0.0):
        return issue(
            "READBACK_MISMATCH",
            f"{name} reads { ({k: got.get(k) for k in item.want}) }, requested {item.want}",
        )
    return None


def integrity(
    *,
    ledger_unique_ids: Sequence[str],
    present_unique_ids: set[str],
    type_ids_in_family: set[int],
    element_type_ids: Mapping[str, int],
    pre_image_warnings: Sequence[Mapping[str, Any]],
    current_warnings: Sequence[Mapping[str, Any]],
) -> list[ModelIssue]:
    """Tolerance-free checks of spec 0011 section 4.8."""

    def issue(code: str, kind: SubjectKind, subject_id: str, message: str, severity: Severity = _ERROR) -> ModelIssue:
        return ModelIssue(severity=severity, code=code, subject=Subject(kind=kind, id=subject_id), message=message)

    found: list[ModelIssue] = []
    for uid in ledger_unique_ids:
        if uid not in present_unique_ids:
            found.append(issue("ELEMENT_MISSING", SubjectKind.FRAME, uid, f"element {uid} is absent by unique_id"))
    for uid, type_id in element_type_ids.items():
        if type_id not in type_ids_in_family:
            found.append(
                issue(
                    "TYPE_UNDEFINED",
                    SubjectKind.FRAME,
                    uid,
                    f"type {type_id} is not in the family",
                )
            )
    pre_counts = _warning_counts(pre_image_warnings)
    cur_counts = _warning_counts(current_warnings)
    for warning_type, count in cur_counts.items():
        if count > pre_counts.get(warning_type, 0):
            found.append(
                issue(
                    "REVIT_WARNINGS_INCREASED",
                    SubjectKind.MODEL,
                    "model",
                    f"warning {warning_type} increased from {pre_counts.get(warning_type, 0)} to {count}",
                    Severity.WARNING,
                )
            )
    # Spec 0011 §4.8 / R-G1: MODEL_UNSAVED info, always.
    found.append(
        issue(
            "MODEL_UNSAVED",
            SubjectKind.MODEL,
            "model",
            "Revit has no save tool; edits stay unsaved (R-G1)",
            Severity.INFO,
        )
    )
    return found


def _warning_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        name = str(row.get("type") or row.get("name") or "unknown")
        counts[name] = counts.get(name, 0) + int(row.get("count") or 1)
    return counts


async def check_model(
    call: HostCall,
    read_back: ReadBack,
    model_key: str,
    *,
    host: HostInfo,
    pre_image_warnings: Sequence[Mapping[str, Any]] = (),
    ledger_unique_ids: Sequence[str] | None = None,
) -> SuccessEnvelope:
    """Read back every written item of `model_key` and return `issues.model_check/1` (AC19)."""
    started, began = SystemClock().now(), SystemClock().now_ms()
    issues: list[ModelIssue] = []
    for item in read_back.written.items(model_key):
        try:
            got = await _observe(call, item)
        except KeyError, TypeError, ValueError, IndexError:
            issues.append(
                ModelIssue(
                    severity=_ERROR,
                    code="READBACK_UNAVAILABLE",
                    subject=item.subject,
                    message=f"the read-back of {item.helper} could not be read",
                )
            )
            continue
        found = compare(item, got, read_back.tolerance_ratio)
        if found is not None:
            issues.append(found)

    present_unique_ids, element_type_ids, type_ids = await _structure_snapshot(call)
    warnings_reply = await call("revit_get_model_warnings_summary", {}, CallEffect.READ)
    warnings_body = parse_revit_reply(dict(warnings_reply)).body
    current = warnings_body.get("warnings")
    current_warnings = [w for w in current if isinstance(w, Mapping)] if isinstance(current, list) else []
    issues.extend(
        integrity(
            ledger_unique_ids=list(ledger_unique_ids or []),
            present_unique_ids=present_unique_ids,
            type_ids_in_family=type_ids,
            element_type_ids=element_type_ids,
            pre_image_warnings=pre_image_warnings,
            current_warnings=current_warnings,
        )
    )

    tally = Counter(issue.severity for issue in issues)
    counts = {"errors": tally[_ERROR], "warnings": tally[Severity.WARNING], "infos": tally[Severity.INFO]}
    summary = CheckModelSummary(**counts, clean=not tally[_ERROR])
    payload = ModelCheck(summary=summary, issues=issues).model_dump(mode="json")
    producer = Provenance(
        tool="harness/check_model",
        tool_version=read_back.check.build,
        host=host,
        inputs={},
        started_at=started,
        duration_ms=SystemClock().now_ms() - began,
    )
    record = read_back.store.put("issues.model_check/1", payload, producer)
    read_back.written.clear(model_key)
    return make_success(record, summary.model_dump(mode="json"), [])


async def _structure_snapshot(
    call: HostCall,
) -> tuple[set[str], dict[str, int], set[int]]:
    """unique_ids present, element unique_id→type_id, and type ids in the model."""
    present: set[str] = set()
    element_types: dict[str, int] = {}
    type_ids: set[int] = set()
    for category in ("OST_StructuralColumns", "OST_StructuralFraming"):
        listed = await call("revit_list_elements", {"category": category}, CallEffect.READ)
        body = parse_revit_reply(dict(listed)).body
        rows = body.get("items") or body.get("elements") or []
        if not isinstance(rows, list):
            continue
        ids: list[int] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            eid = _as_int(row.get("element_id"))
            if eid is not None:
                ids.append(eid)
        if not ids:
            continue
        details = await call("revit_get_element_details", {"elementIds": ids}, CallEffect.READ)
        detail_body = parse_revit_reply(dict(details)).body
        items = detail_body.get("items")
        if not isinstance(items, list):
            continue
        for row in items:
            if not isinstance(row, Mapping):
                continue
            uid = row.get("unique_id")
            if isinstance(uid, str) and uid:
                present.add(uid)
                tid = _as_int(row.get("type_id"))
                if tid is not None:
                    element_types[uid] = tid
    types_reply = await call("revit_get_available_family_types", {}, CallEffect.READ)
    types_body = parse_revit_reply(dict(types_reply)).body
    type_rows = types_body.get("items") or types_body.get("types") or []
    if isinstance(type_rows, list):
        for row in type_rows:
            if not isinstance(row, Mapping):
                continue
            tid = _as_int(row.get("type_id"))
            if tid is not None:
                type_ids.add(tid)
    return present, element_types, type_ids
