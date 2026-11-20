"""IDEA calculation on both routes and host-verdict reads (plan 0014 T8; spec 0014 AC11 to AC13, AC18).

Purpose: call `idea_native_calculate` (route native) or `idea_calculate` / `idea_get_check_results` (route rest)
with stub refusal and service-reachable preflight; map a live reply to `harness.idea_check_raw/1` and
`verdicts.set/1`. A connection with a non-empty `errors` list becomes one `idea:connection` verdict `ERROR`
(AC12); never invent a utilization. Units: `check_value` is a host percent (`ratio = check_value / 100`,
declared). Errors: `ContractError` `HOST_NOT_CONNECTED` (preflight), `HOST_ERROR` (`OFFLINE_STUB`,
`UNEXPECTED_REPLY`), mapped host codes via `IdeaErrorMapper`, and `PRECONDITION_FAILED` from the verdict builder.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eng_contract.envelope import Provenance, SuccessEnvelope, make_success
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.store import ResultStore
from eng_contract.verdicts import Subject, SubjectKind, Verdict, VerdictSource, VerdictStatus
from pydantic import JsonValue

from eng_harness.adapters._errors import parse_error_reply
from eng_harness.adapters.idea._errors import IdeaErrorMapper
from eng_harness.adapters.idea._replies import TEXT_LIMIT, cut_text, parse_check_raw, parse_reply_json
from eng_harness.adapters.idea._stub import refuse_stub
from eng_harness.adapters.idea._tools import build_calculate_args, build_native_calculate_args
from eng_harness.adapters.idea._verdicts import HOST_ASSUMPTION, build_verdict_set
from eng_harness.kinds.idea import IdeaCheckRaw
from eng_harness.servers import CallEffect
from eng_harness.servers._session import reply_body

__all__ = [
    "CalculateResult",
    "calculate_native",
    "calculate_rest",
    "get_check_results",
]

_RATIO_LIMIT = 1.0  # contract default (spec 0014 section 4.5)
_REST_CODE_ASSUMPTION = "design code declared in the design basis, not read from the host"
_REST_LOADS_ASSUMPTION = "loads as stored in the opened file"


@dataclass(frozen=True)
class CalculateResult:
    """Stored raw check reply and the host-only `verdicts.set/1` built from it (AC12, AC14)."""

    raw: IdeaCheckRaw
    verdicts: VerdictSet
    raw_envelope: SuccessEnvelope
    verdict_envelope: SuccessEnvelope


def _assumptions(*, route: str, extras: Sequence[str] = ()) -> list[str]:
    items = [HOST_ASSUMPTION, *extras]
    if route == "rest":
        items.extend((_REST_CODE_ASSUMPTION, _REST_LOADS_ASSUMPTION))
    return [cut_text(item, TEXT_LIMIT) for item in items]


def _error_verdict(*, connection_name: str, design_code: str, route: str, errors: Sequence[str]) -> Verdict:
    """One `idea:connection` ERROR verdict from a non-empty host `errors` list (spec 0014 AC12)."""
    joined = "; ".join(str(item) for item in errors if item)
    return Verdict(
        source=VerdictSource.HOST,
        check_id="idea:connection",
        code=design_code,
        clause=None,
        subject=Subject(kind=SubjectKind.JOINT, id=connection_name, station_mm=None, case=None),
        demand=None,
        capacity=None,
        ratio=None,
        ratio_limit=_RATIO_LIMIT,
        status=VerdictStatus.ERROR,
        governing=False,
        trace_ref=None,
        assumptions=_assumptions(route=route, extras=(joined or "host reported errors",)),
    )


def _verdicts_from_connections(
    connections: Sequence[Mapping[str, Any]],
    *,
    design_code: str,
    route: str,
    load_map_confirmed: bool,
) -> VerdictSet:
    """Map connection rows; AC12 error lists become ERROR verdicts before the check-row mapping (AC13/AC14)."""
    error_rows = [
        connection for connection in connections if isinstance(connection, Mapping) and bool(connection.get("errors"))
    ]
    check_rows = [
        connection
        for connection in connections
        if isinstance(connection, Mapping) and not bool(connection.get("errors"))
    ]
    error_verdicts = [
        _error_verdict(
            connection_name=str(connection.get("name") or "connection"),
            design_code=design_code,
            route=route,
            errors=[str(item) for item in (connection.get("errors") or ())],
        )
        for connection in error_rows
    ]
    if check_rows:
        base = build_verdict_set(
            check_rows,
            design_code=design_code,
            route=route,
            load_map_confirmed=load_map_confirmed,
        )
        if not error_verdicts:
            return base
        merged = list(base.verdicts) + error_verdicts
        tally = Counter(v.status for v in merged)
        counts = {status: tally[status] for status in VerdictStatus}
        return VerdictSet(verdicts=merged, traces=[], counts=counts, draft=base.draft)
    if not error_verdicts:
        # No calculated checks and no error rows: the builder raises PRECONDITION_FAILED (AC14).
        return build_verdict_set(
            connections,
            design_code=design_code,
            route=route,
            load_map_confirmed=load_map_confirmed,
        )
    tally = Counter(v.status for v in error_verdicts)
    counts = {status: tally[status] for status in VerdictStatus}
    draft = (not load_map_confirmed) or route == "rest"
    return VerdictSet(verdicts=error_verdicts, traces=[], counts=counts, draft=draft)


def _raise_host(result: Any, *, tool: str, effect: CallEffect, ids: Any, op_id: str = "") -> None:
    dumped = result.model_dump(by_alias=True, mode="json") if hasattr(result, "model_dump") else result
    failure = parse_error_reply(dumped)
    if failure is None:
        raise ContractError(
            ErrorCode.HOST_ERROR,
            f"{tool} failed",
            retryable=False,
            host_code="UNEXPECTED_REPLY",
            host_method=tool,
        )
    detail = IdeaErrorMapper(ids).map(failure, effect=effect, tool=tool, op_id=op_id)
    extra = {
        key: value
        for key in (
            "field",
            "host_code",
            "host_method",
            "op_id",
            "incident_id",
            "hint",
            "precondition",
            "expected",
            "received",
        )
        if (value := getattr(detail, key, None)) is not None
    }
    raise ContractError(detail.code, detail.message, retryable=detail.retryable, **extra)


async def _require_service_reachable(*, sessions: Any, server: str, role: str) -> None:
    """AC11 rest preflight: `idea_status.service.reachable` must be true before any calculate call."""
    result = await sessions.call(server, role, "idea_status", {}, CallEffect.READ)
    if result.is_error:
        raise ContractError(ErrorCode.HOST_NOT_CONNECTED, "idea_status failed")
    body = reply_body(result)
    if body is None:
        raise ContractError(ErrorCode.HOST_NOT_CONNECTED, "idea_status returned no body")
    service = body.get("service")
    reachable = isinstance(service, Mapping) and service.get("reachable") is True
    if not reachable:
        raise ContractError(ErrorCode.HOST_NOT_CONNECTED, "IDEA Connection REST service is not reachable")


def _store_pair(
    *,
    store: ResultStore,
    tool: str,
    raw_payload: dict[str, JsonValue],
    verdicts: VerdictSet,
) -> tuple[SuccessEnvelope, SuccessEnvelope]:
    """Store `harness.idea_check_raw/1` then `verdicts.set/1` with the raw record as parent (AC14)."""
    from eng_contract.ids import FixedClock

    at = FixedClock(1_700_000_000_000, 1).now()
    producer_raw = Provenance(
        tool=f"harness/{tool}",
        tool_version="1",
        host=None,
        inputs={},
        started_at=at,
        duration_ms=0,
    )
    raw_record = store.put("harness.idea_check_raw/1", raw_payload, producer_raw)
    connections_value = raw_payload.get("connections")
    connection_count = len(connections_value) if isinstance(connections_value, list) else 0
    raw_summary: dict[str, JsonValue] = {
        "route": raw_payload.get("route"),
        "connections": connection_count,
    }
    raw_envelope = make_success(raw_record, raw_summary, [])
    producer_verdicts = Provenance(
        tool=f"harness/{tool}",
        tool_version="1",
        host=None,
        inputs={},
        started_at=at,
        duration_ms=0,
    )
    verdict_record = store.put(
        "verdicts.set/1",
        verdicts.model_dump(mode="json"),
        producer_verdicts,
        parents=[raw_record.result_id],
    )
    counts_summary: dict[str, JsonValue] = {
        (key.value if hasattr(key, "value") else str(key)): int(value) for key, value in verdicts.counts.items()
    }
    verdict_summary: dict[str, JsonValue] = {"draft": verdicts.draft, "counts": counts_summary}
    verdict_envelope = make_success(verdict_record, verdict_summary, [])
    return raw_envelope, verdict_envelope


def _looks_like_check_reply(body: Mapping[str, Any]) -> bool:
    """True when the body carries check-reply fields (not a bare unexpected shape)."""
    return any(key in body for key in ("connections", "offline_stub", "backend", "notice"))


async def _process_success(
    result: Any,
    *,
    tool: str,
    design_code: str,
    route: str,
    load_map_confirmed: bool,
    store: ResultStore,
    ids: Any,
) -> CalculateResult:
    """Refuse stubs, shape-check, map verdicts and store both kinds."""
    dumped = result.model_dump(by_alias=True, mode="json") if hasattr(result, "model_dump") else result
    body = parse_reply_json(dumped)
    # AC12: a bare unexpected shape is UNEXPECTED_REPLY, not OFFLINE_STUB (stub markers need a check reply).
    if not _looks_like_check_reply(body):
        raise ContractError(
            ErrorCode.HOST_ERROR,
            "the host reply is not a valid harness.idea_check_raw/1",
            retryable=False,
            host_code="UNEXPECTED_REPLY",
            host_method=tool,
        )
    # Tag route for the stub rule (native replies may omit it; rest must be live).
    tagged = dict(body)
    tagged.setdefault("route", route)
    refuse_stub(tagged, host_method=tool)
    raw = parse_check_raw(tagged)
    verdicts = _verdicts_from_connections(
        [c.model_dump(mode="json") for c in raw.connections],
        design_code=design_code,
        route=route,
        load_map_confirmed=load_map_confirmed,
    )
    raw_envelope, verdict_envelope = _store_pair(
        store=store,
        tool=tool,
        raw_payload=raw.model_dump(mode="json"),
        verdicts=verdicts,
    )
    return CalculateResult(
        raw=raw,
        verdicts=verdicts,
        raw_envelope=raw_envelope,
        verdict_envelope=verdict_envelope,
    )


async def calculate_native(
    *,
    sessions: Any,
    server: str,
    role: str,
    path: Path | str,
    connection_id: str | None,
    design_code: str,
    load_map_confirmed: bool,
    store: ResultStore,
    ids: Any,
) -> CalculateResult:
    """Run `idea_native_calculate` with `save: false` and map host verdicts (spec 0014 AC12)."""
    args = build_native_calculate_args(path=str(path), connection_id=connection_id)
    result = await sessions.call(server, role, "idea_native_calculate", args, CallEffect.READ)
    if result.is_error:
        _raise_host(result, tool="idea_native_calculate", effect=CallEffect.READ, ids=ids)
    return await _process_success(
        result,
        tool="idea_native_calculate",
        design_code=design_code,
        route="native",
        load_map_confirmed=load_map_confirmed,
        store=store,
        ids=ids,
    )


async def calculate_rest(
    *,
    sessions: Any,
    server: str,
    role: str,
    connection_ids: Sequence[int],
    design_code: str,
    load_map_confirmed: bool,
    approved: bool,
    store: ResultStore,
    ids: Any,
) -> CalculateResult:
    """Preflight reachable service, call `idea_calculate`, refuse stubs, map host verdicts (AC11, AC12)."""
    await _require_service_reachable(sessions=sessions, server=server, role=role)
    args = build_calculate_args(connection_ids=connection_ids, approved=approved)
    result = await sessions.call(server, role, "idea_calculate", args, CallEffect.WRITE)
    if result.is_error:
        _raise_host(result, tool="idea_calculate", effect=CallEffect.WRITE, ids=ids)
    return await _process_success(
        result,
        tool="idea_calculate",
        design_code=design_code,
        route="rest",
        load_map_confirmed=load_map_confirmed,
        store=store,
        ids=ids,
    )


async def get_check_results(
    *,
    sessions: Any,
    server: str,
    role: str,
    connection_id: int | None,
    design_code: str,
    load_map_confirmed: bool,
    store: ResultStore,
    ids: Any,
) -> CalculateResult:
    """Preflight reachable service, call `idea_get_check_results`, refuse stubs, map verdicts (AC11)."""
    await _require_service_reachable(sessions=sessions, server=server, role=role)
    args: dict[str, JsonValue] = {}
    if connection_id is not None:
        args["connection_id"] = connection_id
    result = await sessions.call(server, role, "idea_get_check_results", args, CallEffect.READ)
    if result.is_error:
        _raise_host(result, tool="idea_get_check_results", effect=CallEffect.READ, ids=ids)
    return await _process_success(
        result,
        tool="idea_get_check_results",
        design_code=design_code,
        route="rest",
        load_map_confirmed=load_map_confirmed,
        store=store,
        ids=ids,
    )
