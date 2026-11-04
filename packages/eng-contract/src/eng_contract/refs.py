"""References to stored results and their resolution rules (spec 4.6; 04 sections 3.2 and 3.4).

Purpose: parse `res_<id>#<pointer>` references and resolve them against a record source, checking kind, unit and
staleness. Units: none of its own; unit symbols are those of `units`. Errors: `ContractError` with `INVALID_ARGUMENT`
(malformed result id), `REF_POINTER_INVALID`, `REF_NOT_FOUND`, `REF_KIND_MISMATCH`, `REF_UNIT_MISMATCH`, `REF_STALE`,
and `INTERNAL` (a model older than the record, an integrity failure).
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

from eng_contract._pointer import JsonPointer
from eng_contract._types import FieldPath, KindName
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import IdSource, ModelId, ResultId, SystemClock, SystemIdSource
from eng_contract.units import kind_for_field

if TYPE_CHECKING:
    from eng_contract.records import ResultRecord

_ID = r"res_[0-7][0-9A-HJKMNP-TV-Z]{25}"
_MAX_REF = 2000
_REF = re.compile(rf"({_ID})(?:#(.*))?", re.DOTALL)
_LOCAL = re.compile(r"#/traces/(0|[1-9][0-9]*)")
_MODEL = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=False)

RefString = Annotated[str, StringConstraints(max_length=_MAX_REF, pattern=rf"^{_ID}(#(?s:.*))?$")]
"""A result id, optionally followed by `#` and an RFC 6901 pointer (JSON string form)."""
LocalTraceRef = Annotated[str, StringConstraints(pattern=r"^#/traces/(0|[1-9][0-9]*)$")]
"""Pointer from inside a payload to one of its own traces (spec 4.6.3); rebased before resolution."""

__all__ = [
    "JsonPointer",
    "LocalTraceRef",
    "RecordSource",
    "Ref",
    "RefRule",
    "RefString",
    "ResolvedRef",
    "parse_ref",
    "rebase_local_ref",
    "resolve_ref",
]


class Ref(BaseModel):
    """Input given as a reference: exactly the key `"$ref"` with a `RefString`."""

    model_config = _MODEL | ConfigDict(serialize_by_alias=True)

    ref: RefString = Field(alias="$ref")


class RefRule(BaseModel):
    """What a parameter accepts: kinds (empty means any), canonical unit symbol or null, `stale_ok`, field name."""

    model_config = _MODEL

    kinds: frozenset[KindName] = frozenset()
    unit: str | None = None
    stale_ok: bool = False
    field: FieldPath | None = None


class ResolvedRef(BaseModel):
    """A resolved reference. Provenance records `ref`, never `value`."""

    model_config = _MODEL

    ref: RefString
    value: JsonValue
    record_kind: KindName
    result_id: ResultId
    model_id: ModelId | None
    model_revision: int | None


class RecordSource(Protocol):
    """Where records come from; `ResultStore` implements it. `get` raises `REF_NOT_FOUND` for a missing id."""

    def get(self, result_id: str) -> ResultRecord:
        """The record, whose `payload` is null when it is stored in its own file."""
        ...

    def payload(self, result_id: str) -> dict[str, JsonValue]:
        """The record's payload, loaded from its own file when split."""
        ...


def _bad_id(text: str, field: str | None) -> ContractError:
    return ContractError(ErrorCode.INVALID_ARGUMENT, "malformed result id", field=field, received=text[:200])


def parse_ref(text: str, *, field: str | None = None) -> tuple[str, tuple[str, ...]]:
    """Split a reference into its result id and pointer tokens (`res_X` and `res_X#` are the whole payload).

    Raises:
        ContractError: `INVALID_ARGUMENT` for a malformed result id or text over 2000 characters;
            `REF_POINTER_INVALID` for a malformed pointer.
    """
    match = _REF.fullmatch(text)
    if match is None or len(text) > _MAX_REF:
        raise _bad_id(text, field)
    return match[1], JsonPointer.parse(match[2] or "", field)


def rebase_local_ref(result_id: str, local: LocalTraceRef) -> RefString:
    """Turn a payload-local trace reference into a full reference to `result_id` (spec 4.6.3).

    Raises:
        ContractError: `INVALID_ARGUMENT` for a malformed result id; `REF_POINTER_INVALID` if `local` is not
            `#/traces/<index>`.
    """
    if re.fullmatch(_ID, result_id) is None:
        raise _bad_id(result_id, None)
    if _LOCAL.fullmatch(local) is None:
        raise ContractError(ErrorCode.REF_POINTER_INVALID, "not a local trace reference", received=local)
    return f"{result_id}{local}"


def _is_number(value: JsonValue) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _check_unit(value: JsonValue, tokens: tuple[str, ...], rule: RefRule, unit: str) -> None:
    """Spec 4.6.2 step 5: a quantity object carries its unit; a bare number takes that of the nearest suffixed key."""
    found: str | None
    if isinstance(value, dict):
        symbol = value.get("unit")
        if not isinstance(symbol, str) or not _is_number(value.get("value")):
            return
        found = symbol
    elif _is_number(value):
        found = next((kind.canonical_unit for t in reversed(tokens) if (kind := kind_for_field(t))), None)
    else:
        return
    if found != unit:
        raise ContractError(
            ErrorCode.REF_UNIT_MISMATCH,
            f"expected unit {unit}",
            field=rule.field,
            expected={"unit": unit},
            received=value,
        )


def _check_revision(
    record: ResultRecord, rule: RefRule, current_revision: Callable[[ModelId], int | None], ids: IdSource | None
) -> None:
    """Spec 4.6.2 step 6: a result of a host model is stale when the model has moved on."""
    host = record.producer.host
    current = None if host is None else current_revision(host.model_id)
    if host is None or current is None or current == host.model_revision:
        return
    seen = {"model_id": host.model_id, "record_revision": host.model_revision, "current_revision": current}
    if current < host.model_revision:
        source = ids or SystemIdSource(SystemClock())
        raise ContractError(
            ErrorCode.INTERNAL,
            "the model revision is older than the record's",
            field=rule.field,
            received=seen,
            incident_id=source.new_ulid(),
        )
    if not rule.stale_ok:
        raise ContractError(ErrorCode.REF_STALE, "the model changed after the result", field=rule.field, received=seen)


def resolve_ref(
    ref: Ref | str,
    rule: RefRule,
    source: RecordSource,
    current_revision: Callable[[ModelId], int | None],
    *,
    ids: IdSource | None = None,
) -> ResolvedRef:
    """Resolve a reference; the first failing step of spec 4.6.2 wins.

    `current_revision(model_id)` gives the model's revision, or None for a model the caller does not track
    (accepted). `ids` supplies the incident id of an integrity failure (default: the system source).

    Raises:
        ContractError: `INVALID_ARGUMENT`, `REF_POINTER_INVALID`, `REF_NOT_FOUND`, `REF_KIND_MISMATCH`,
            `REF_UNIT_MISMATCH`, `REF_STALE`, or `INTERNAL`; errors of the source other than a missing id propagate.
    """
    text = ref.ref if isinstance(ref, Ref) else ref
    result_id, tokens = parse_ref(text, field=rule.field)
    try:
        record = source.get(result_id)
    except ContractError as exc:
        if exc.detail.code is not ErrorCode.REF_NOT_FOUND:
            raise
        raise ContractError(ErrorCode.REF_NOT_FOUND, f"no result {result_id}", field=rule.field, received=text) from exc
    if rule.kinds and record.kind not in rule.kinds:
        raise ContractError(
            ErrorCode.REF_KIND_MISMATCH,
            f"result kind {record.kind} is not accepted",
            field=rule.field,
            expected={"kinds": sorted(rule.kinds)},
            received=record.kind,
        )
    payload = record.payload if record.payload is not None else source.payload(result_id)
    value = JsonPointer.evaluate(payload, tokens, rule.field)
    if rule.unit is not None:
        _check_unit(value, tokens, rule, rule.unit)
    _check_revision(record, rule, current_revision, ids)
    host = record.producer.host
    return ResolvedRef(
        ref=text,
        value=value,
        record_kind=record.kind,
        result_id=result_id,
        model_id=host.model_id if host else None,
        model_revision=host.model_revision if host else None,
    )
