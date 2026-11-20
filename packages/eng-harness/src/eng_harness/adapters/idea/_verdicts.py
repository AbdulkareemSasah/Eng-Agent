"""IDEA host-verdict mapping (plan 0014 T5; spec 0014 AC13 to AC15, section 4.5).

Purpose: map IDEA check rows to contract `Verdict` values with `source: host` and assemble one `verdicts.set/1`.
This module is engineering content: it stays draft and the owner reviews it. The adapter never recomputes a host
status and never changes a host `FAIL` to `PASS`.
Units: `ratio = check_value / 100` (host utilization percent → contract ratio); `ratio_limit` is the contract default
1.0. Errors: `ContractError` `PRECONDITION_FAILED` (`analysis_current`) when no connection is calculated; `ValueError`
when a code-pack verdict is offered to a host-only set (AC14).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.verdicts import Subject, SubjectKind, Verdict, VerdictSource, VerdictStatus

from eng_harness.adapters.idea._replies import TEXT_LIMIT, cut_text

__all__ = [
    "HOST_ASSUMPTION",
    "ZERO_UTILIZATION_ASSUMPTION",
    "build_verdict_set",
    "map_check",
    "require_host_only",
    "slug",
]

HOST_ASSUMPTION = "host-native check of IDEA StatiCa; not merged with code-pack verdicts"
"""Always present on every IDEA host verdict (spec 0014 section 4.5)."""

ZERO_UTILIZATION_ASSUMPTION = "utilization is exactly zero; the value may be missing in the host reply"
"""AC13 / §4.5: check_value 0 with check_status true cannot be told from a Sasaah-filled missing value."""

_REST_CODE_ASSUMPTION = "design code declared in the design basis, not read from the host"
_REST_LOADS_ASSUMPTION = "loads as stored in the opened file"
_RATIO_LIMIT = 1.0
_SLUG_BAD = re.compile(r"[^a-z0-9_.-]+")


def slug(name: str) -> str:
    """Lower-case check name with characters outside `[a-z0-9_.-]` replaced by `_`; `check` when empty (§4.5)."""
    cleaned = _SLUG_BAD.sub("_", name.strip().lower())
    return cleaned or "check"


def _assumptions(*, route: str, extras: Sequence[str] = ()) -> list[str]:
    items = [HOST_ASSUMPTION, *extras]
    if route == "rest":
        items.extend((_REST_CODE_ASSUMPTION, _REST_LOADS_ASSUMPTION))
    return [cut_text(item, TEXT_LIMIT) for item in items]


def map_check(
    check: Mapping[str, Any],
    *,
    connection_name: str,
    design_code: str,
    route: str,
) -> Verdict:
    """Map one IDEA check row to a host `Verdict` (spec 0014 AC13, section 4.5).

    `skipped` → `NOT_APPLICABLE`. Otherwise the host `check_status` becomes `PASS`/`FAIL` only when consistent with
    `ratio <= ratio_limit` (1.0); disagreements, a negative value, or zero with `check_status` true →
    `NEEDS_ENGINEER`; a non-finite value → `ERROR`. The adapter never upgrades a host fail to pass.
    """
    skipped = bool(check.get("skipped", False))
    host_pass = bool(check.get("check_status", False))
    raw_value = check.get("check_value", 0)
    name = str(check.get("name") or "")
    case = check.get("load_case_id")
    case_str = None if case is None else str(case)[:200] or None
    extras: list[str] = []

    try:
        value = float(raw_value)
    except TypeError, ValueError:
        value = float("nan")

    if not math.isfinite(value):
        status = VerdictStatus.ERROR
        ratio: float | None = None
    elif skipped:
        status = VerdictStatus.NOT_APPLICABLE
        ratio = value / 100.0 if value >= 0 else None
    else:
        ratio = value / 100.0 if value >= 0 else None
        if value < 0:
            status = VerdictStatus.NEEDS_ENGINEER
        elif value == 0.0 and host_pass:
            status = VerdictStatus.NEEDS_ENGINEER
            extras.append(ZERO_UTILIZATION_ASSUMPTION)
        elif host_pass:
            # Host says pass: keep PASS only when ratio <= limit; else NEEDS_ENGINEER (never invent FAIL).
            status = VerdictStatus.PASS if ratio is not None and ratio <= _RATIO_LIMIT else VerdictStatus.NEEDS_ENGINEER
        else:
            # Host says fail: keep FAIL only when ratio > limit; never upgrade to PASS (AC13).
            status = VerdictStatus.FAIL if ratio is not None and ratio > _RATIO_LIMIT else VerdictStatus.NEEDS_ENGINEER

    return Verdict(
        source=VerdictSource.HOST,
        check_id=f"idea:{slug(name)}",
        code=design_code,
        clause=None,
        subject=Subject(kind=SubjectKind.JOINT, id=connection_name, station_mm=None, case=case_str),
        demand=None,
        capacity=None,
        ratio=ratio,
        ratio_limit=_RATIO_LIMIT,
        status=status,
        governing=False,
        trace_ref=None,
        assumptions=_assumptions(route=route, extras=extras),
    )


def require_host_only(verdicts: Sequence[Verdict]) -> None:
    """Raise `ValueError` when any verdict is not `source: host` (AC14 construction error)."""
    for verdict in verdicts:
        if verdict.source is not VerdictSource.HOST:
            raise ValueError("a verdicts.set of IDEA host checks may not contain a code_pack verdict")


def _connection_passed_agrees(connection: Mapping[str, Any], check_verdicts: Sequence[Verdict]) -> bool:
    """True when `passed` matches the non-skipped check statuses (any FAIL or NEEDS_ENGINEER from a fail disagrees)."""
    if not bool(connection.get("passed", False)):
        return True
    for verdict in check_verdicts:
        if verdict.status in (VerdictStatus.FAIL, VerdictStatus.ERROR):
            return False
        if (
            verdict.status is VerdictStatus.NEEDS_ENGINEER
            and verdict.ratio is not None
            and verdict.ratio > _RATIO_LIMIT
        ):
            return False
    return True


def _mark_governing(verdicts: list[Verdict]) -> list[Verdict]:
    """Set `governing` on the largest-ratio non-skipped verdicts per connection (ties all) (AC14)."""
    by_subject: dict[str, list[int]] = {}
    for index, verdict in enumerate(verdicts):
        if verdict.status is VerdictStatus.NOT_APPLICABLE:
            continue
        if verdict.check_id == "idea:connection":
            continue
        by_subject.setdefault(verdict.subject.id, []).append(index)
    out = list(verdicts)
    for indexes in by_subject.values():
        ratios = [out[i].ratio for i in indexes]
        finite = [r for r in ratios if r is not None]
        if not finite:
            continue
        best = max(finite)
        for i in indexes:
            if out[i].ratio == best:
                out[i] = out[i].model_copy(update={"governing": True})
    return out


def build_verdict_set(
    connections: Sequence[Mapping[str, Any]],
    *,
    design_code: str,
    route: str,
    load_map_confirmed: bool,
) -> VerdictSet:
    """Build one `verdicts.set/1` from IDEA connection rows (AC14, AC15, section 4.5).

    Raises:
        ContractError: `PRECONDITION_FAILED` (`analysis_current`) when no connection is calculated.
    """
    calculated = [c for c in connections if bool(c.get("calculated"))]
    if not calculated:
        raise ContractError(
            ErrorCode.PRECONDITION_FAILED,
            "no calculated connection in the host reply",
            precondition=Precondition.analysis_current,
        )

    verdicts: list[Verdict] = []
    for connection in calculated:
        name = str(connection.get("name") or "connection")
        checks = connection.get("checks") or ()
        check_verdicts = [
            map_check(check, connection_name=name, design_code=design_code, route=route)
            for check in checks
            if isinstance(check, Mapping)
        ]
        verdicts.extend(check_verdicts)
        if not _connection_passed_agrees(connection, check_verdicts):
            verdicts.append(
                Verdict(
                    source=VerdictSource.HOST,
                    check_id="idea:connection",
                    code=design_code,
                    clause=None,
                    subject=Subject(kind=SubjectKind.JOINT, id=name, station_mm=None, case=None),
                    demand=None,
                    capacity=None,
                    ratio=None,
                    ratio_limit=_RATIO_LIMIT,
                    status=VerdictStatus.NEEDS_ENGINEER,
                    governing=False,
                    trace_ref=None,
                    assumptions=_assumptions(
                        route=route,
                        extras=["connection passed disagrees with its checks"],
                    ),
                )
            )

    require_host_only(verdicts)
    verdicts = _mark_governing(verdicts)
    tally = Counter(v.status for v in verdicts)
    counts = {status: tally[status] for status in VerdictStatus}
    draft = (not load_map_confirmed) or route == "rest"
    return VerdictSet(verdicts=verdicts, traces=[], counts=counts, draft=draft)
