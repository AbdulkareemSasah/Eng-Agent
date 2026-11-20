"""IDEA adapter check_model integrity issues (plan 0014 T7; spec 0014 AC10, section 4.10).

Purpose: compare a requested loading with the host read-back within
`checks.readback_relative_tolerance_ratio`, and emit the integrity codes of section 4.10 that need no tolerance:
`LOADS_UNCONFIRMED_MAP`, `LOAD_EFFECT_ZERO_DROPPED`, `READBACK_MISMATCH`, `READBACK_UNAVAILABLE`.
Units: host N and N.m compared as floats; tolerance is relative (basis field). Errors: none raised.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from eng_contract.issues import ModelIssue, Severity
from eng_contract.verdicts import Subject, SubjectKind

from eng_harness.adapters.idea._loads import FORCE_KEYS, LoadMap

__all__ = [
    "compare_loads_readback",
    "issues_from_set_loads_reply",
    "load_map_status_issue",
]


def load_map_status_issue(load_map: LoadMap, *, connection: str) -> ModelIssue | None:
    """Info `LOADS_UNCONFIRMED_MAP` when the load map is not confirmed (spec 0014 section 4.10)."""
    if load_map.status == "confirmed":
        return None
    return ModelIssue(
        severity=Severity.INFO,
        code="LOADS_UNCONFIRMED_MAP",
        subject=Subject(kind=SubjectKind.JOINT, id=connection, station_mm=None, case=None),
        message="load map status is unconfirmed (IG-2); verdicts stay draft until the owner confirms it",
    )


def issues_from_set_loads_reply(body: Mapping[str, Any], *, connection: str) -> list[ModelIssue]:
    """Warning `LOAD_EFFECT_ZERO_DROPPED` naming each effect in `dropped_zero` (AC10)."""
    dropped = body.get("dropped_zero") or []
    if not isinstance(dropped, list) or not dropped:
        return []
    names = ", ".join(str(name) for name in dropped if name)
    return [
        ModelIssue(
            severity=Severity.WARNING,
            code="LOAD_EFFECT_ZERO_DROPPED",
            subject=Subject(kind=SubjectKind.JOINT, id=connection, station_mm=None, case=None),
            message=f"host dropped all-zero load effects before the write: {names}",
        )
    ]


def compare_loads_readback(
    *,
    requested: Sequence[Mapping[str, Any]],
    got: Sequence[Mapping[str, Any]] | None,
    tolerance_ratio: float | None,
    connection: str,
) -> list[ModelIssue]:
    """Read-back issues for the six force fields (AC10); `READBACK_UNAVAILABLE` without a tolerance."""
    subject = Subject(kind=SubjectKind.JOINT, id=connection, station_mm=None, case=None)
    if got is None:
        return [
            ModelIssue(
                severity=Severity.ERROR,
                code="READBACK_UNAVAILABLE",
                subject=subject,
                message="load read-back reply was not available",
            )
        ]
    if tolerance_ratio is None or tolerance_ratio <= 0:
        return [
            ModelIssue(
                severity=Severity.ERROR,
                code="READBACK_UNAVAILABLE",
                subject=subject,
                message="no read-back tolerance (checks.readback_relative_tolerance_ratio)",
            )
        ]
    issues: list[ModelIssue] = []
    got_by_name = {str(effect.get("name")): effect for effect in got}
    for want_effect in requested:
        name = str(want_effect.get("name") or "")
        seen = got_by_name.get(name)
        if seen is None:
            issues.append(
                ModelIssue(
                    severity=Severity.ERROR,
                    code="READBACK_MISMATCH",
                    subject=subject,
                    message=f"effect {name!r} is absent on read-back",
                )
            )
            continue
        want_segs = {
            (int(s["beamSegmentId"]), float(s["position"])): s
            for s in (want_effect.get("forcesOnSegments") or [])
            if isinstance(s, Mapping)
        }
        got_segs = {
            (int(s["beamSegmentId"]), float(s["position"])): s
            for s in (seen.get("forcesOnSegments") or [])
            if isinstance(s, Mapping)
        }
        for key, want_seg in want_segs.items():
            got_seg = got_segs.get(key)
            if got_seg is None:
                issues.append(
                    ModelIssue(
                        severity=Severity.ERROR,
                        code="READBACK_MISMATCH",
                        subject=subject,
                        message=f"segment {key} of effect {name!r} is absent on read-back",
                    )
                )
                continue
            for force in FORCE_KEYS:
                wanted = float(want_seg.get(force, 0.0))
                actual = float(got_seg.get(force, 0.0))
                if _differs(wanted, actual, tolerance_ratio):
                    issues.append(
                        ModelIssue(
                            severity=Severity.ERROR,
                            code="READBACK_MISMATCH",
                            subject=subject,
                            message=(
                                f"effect {name!r} segment {key} field {force} reads {actual}, requested {wanted}"
                            ),
                        )
                    )
    return issues


def _differs(wanted: float, actual: float, tolerance_ratio: float) -> bool:
    scale = abs(wanted) if wanted != 0.0 else 1.0
    return abs(actual - wanted) > tolerance_ratio * scale
