"""Validate the SBC clause map and build safest-available checks (spec 0003 §§4.1 to 4.3).

Every explicit unconfirmed row and every missing row stops before any ACI calculation.
The builder delegates inherited checks to the core overlay and its approval lifecycle.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from structural_codes.applicability import Outcome, Precondition
from structural_codes.check import Check, check
from structural_codes.errors import CheckDefinitionError, NotImplementedGap
from structural_codes.inputs import CheckInputs
from structural_codes.meta import CheckMeta, GapDecl, clause_token
from structural_codes.overlay import Inherited, Overlay, Overridden
from structural_codes.pack import Pack
from structural_codes.trace import TraceRecorder

_PACK = "sbc304_2018"
_CODE = "SBC 304-2018"
_EDITION = "2018"
_BASE_CODE = "ACI 318-14"
_SPEC = "sbc304_2018/clause-map.md"
_GAP_ID = re.compile(r"^G-[1-9][0-9]*$")
_MISSING_GAP = "G-0"


class MapStatus(StrEnum):
    """The row statuses allowed by spec 0003 §4.1."""

    INHERITED = "inherited"
    UNCONFIRMED = "unconfirmed"


class GapReason(StrEnum):
    """The reasons for a check to stop at the SBC confirmation gap (spec 0003 §4.3)."""

    SBC_CLAUSE_UNCONFIRMED = "SBC_CLAUSE_UNCONFIRMED"
    SBC_ROW_MISSING = "SBC_ROW_MISSING"


@dataclass(frozen=True, slots=True)
class MapRow:
    """A clause-map row as specified in clause-map.md §2."""

    base_check_id: str
    status: MapStatus
    sbc_clause: str | None
    sbc_source: str | None
    gap_id: str | None
    base_clauses: tuple[str, ...]
    confirm: str


def _validate_row(row: MapRow, base: Check) -> None:
    check_id = row.base_check_id
    if row.status == MapStatus.INHERITED:
        if not row.sbc_clause or not row.sbc_source:
            raise CheckDefinitionError(f"{check_id}: inherited rows require sbc_clause and sbc_source")
        if row.gap_id is not None:
            raise CheckDefinitionError(f"{check_id}: inherited rows cannot declare gap_id")
    elif row.status == MapStatus.UNCONFIRMED:
        if row.sbc_clause is not None or row.sbc_source is not None:
            raise CheckDefinitionError(f"{check_id}: unconfirmed rows cannot declare sbc_clause or sbc_source")
        if not _GAP_ID.fullmatch(row.gap_id or ""):
            raise CheckDefinitionError(f"{check_id}: unconfirmed gap_id must match {_GAP_ID.pattern}")
    else:
        raise CheckDefinitionError(f"{check_id}: status must be inherited or unconfirmed")

    if not row.confirm:
        raise CheckDefinitionError(f"{check_id}: confirm must be non-empty")
    if not row.base_clauses or not all(row.base_clauses):
        raise CheckDefinitionError(f"{check_id}: base_clauses must contain non-empty clauses")
    first, *_ = row.base_clauses
    expected, *_ = base.meta.clauses
    if first != expected:
        raise CheckDefinitionError(f"{check_id}: base_clauses must start with {expected!r}")


def _index_rows(rows: Iterable[MapRow], base_checks: dict[str, Check]) -> dict[str, MapRow]:
    indexed: dict[str, MapRow] = {}
    gaps: set[str] = set()
    for row in rows:
        check_id = row.base_check_id
        if check_id in indexed:
            raise CheckDefinitionError(f"{check_id}: duplicate base_check_id {check_id!r}")
        if check_id not in base_checks:
            raise CheckDefinitionError(f"{check_id}: base check is absent from the base pack")
        _validate_row(row, base_checks[check_id])
        if row.gap_id is not None:
            if row.gap_id in gaps:
                raise CheckDefinitionError(f"{check_id}: duplicate gap_id {row.gap_id!r}")
            gaps.add(row.gap_id)
        indexed[check_id] = row
    return indexed


def _unconfirmed_body(_inputs: CheckInputs, _trace: TraceRecorder) -> None:
    """The confirmation precondition always raises its declared gap."""
    raise CheckDefinitionError("SBC unconfirmed check body is unreachable")


def _gap_check(base: Check, base_clause: str, clause: str, row: MapRow | None) -> Check:
    base_id = base.meta.check_id
    _, _, short_name = base_id.rpartition(".")
    if row is None:
        gap_id = _MISSING_GAP
        reason_code = GapReason.SBC_ROW_MISSING
        confirm = "add a clause map row for this base check"
    else:
        gap_id = cast("str", row.gap_id)  # _validate_row requires a valid id for an unconfirmed row.
        reason_code = GapReason.SBC_CLAUSE_UNCONFIRMED
        confirm = row.confirm
    reason = (
        f"{reason_code}: {_CODE} clause not confirmed for {base_id} ({_BASE_CODE} {base_clause}); "
        f"to confirm: {confirm} and the common items of clause-map §3"
    )
    meta = CheckMeta(
        check_id=f"{_PACK}.{clause_token(clause)}.{short_name}",
        pack=_PACK,
        code=_CODE,
        edition=_EDITION,
        clauses=(clause,),
        title=f"{_CODE}, unconfirmed: {base.meta.title}",
        members=base.meta.members,
        spec=_SPEC,
        gaps=(GapDecl(id=gap_id, clause=clause, reason=reason),),
    )

    def require_confirmation(_inputs: CheckInputs, _trace: TraceRecorder) -> bool:
        raise NotImplementedGap(gap_id, clause, reason)

    precondition = Precondition("SBC_CONFIRMED", Outcome.NEEDS_ENGINEER, clause, reason, require_confirmation)
    return check(meta=meta, inputs=base.inputs, preconditions=(precondition,))(_unconfirmed_body)


def build_overlay(rows: Iterable[MapRow], base_pack: Pack) -> tuple[tuple[Check, ...], Overlay]:
    """Return the pack's own checks and a core overlay with one entry per base check.

    Missing rows get an unconfirmed G-0 gap. The core resolves inherited entries when it builds the registry.
    """
    base_checks = {base.meta.check_id: base for base in base_pack.checks}
    indexed = _index_rows(rows, base_checks)
    checks: list[Check] = []
    entries: list[Inherited | Overridden] = []
    clauses: dict[str, str | None] = {}
    for base_id, base in base_checks.items():
        row = indexed.get(base_id)
        base_clause, *_ = base.meta.clauses
        if row is not None and row.status == MapStatus.INHERITED:
            clause = cast("str", row.sbc_clause)  # _validate_row requires a clause for an inherited row.
            entries.append(Inherited(base_id, clause))
        else:
            clause = f"unconfirmed ({_BASE_CODE} {base_clause})"
            override = _gap_check(base, base_clause, clause, row)
            checks.append(override)
            entries.append(Overridden(base_id, override))
        clauses[clause] = base_clause
    return tuple(checks), Overlay(base_pack.name, clauses, tuple(entries))
