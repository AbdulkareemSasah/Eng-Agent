"""Runner: `evaluate` and `evaluate_batch` (spec 0001 sections 4.4 and 4.12; AC5 to AC7, AC26 to AC29).

Purpose: run a check on one or many subjects and return the `verdicts.set/1` payload. Order: look up the check, refuse
it by mode, validate every item with `validate_input`, then per item the member scope, the preconditions and the body,
then the governing verdict of each subject and the payload. R1 module: a mistake here is a wrong verdict.
Units: none of its own; quantities keep the units of the check's fields.
Errors: `ContractError` (`NOT_FOUND`, `INVALID_ARGUMENT`, and every error of `validate_input`, with `field` prefixed
`items[<k>]` in a batch); `CheckNotUsable`; `CheckDefinitionError` for a body that records no verdict or raises an
undeclared gap. A `ZeroDivisionError`, `OverflowError`, `TraceValueError` or math-domain `ValueError` in an item gives
an `ERROR` verdict for that item; any other exception propagates.
"""

import logging
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, get_args

from eng_contract.envelope import LiteralInput, RefInput
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.params import InputPolicy, ValidatedInput, validate_input
from eng_contract.records import ResultRecord
from eng_contract.refs import RecordSource
from eng_contract.verdicts import Subject, Verdict, VerdictSource, VerdictStatus
from pydantic import ValidationError

from structural_codes._verdict import assign_governing, build_verdict
from structural_codes.check import Check
from structural_codes.content_hash import content_hash
from structural_codes.errors import CheckDefinitionError, CheckNotUsable, NotImplementedGap, TraceValueError
from structural_codes.inputs import CheckInputs
from structural_codes.pack import Registry
from structural_codes.trace import TraceRecorder

__all__ = ["BatchItem", "Evaluation", "Mode", "evaluate", "evaluate_batch"]

State = Literal["draft", "verified", "approved", "withdrawn"]
Mode = Literal["trial", "production"]
"""`trial` runs draft and approved checks; `production` only approved ones (spec 4.8)."""

_log = logging.getLogger(__name__)
_FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CONTAINED = (ZeroDivisionError, OverflowError, TraceValueError, ValueError)


@dataclass(frozen=True, slots=True)
class BatchItem:
    """One subject with its inputs: a raw JSON mapping (may hold `$ref` objects) or an instance of the input model."""

    subject: Subject
    inputs: Mapping[str, Any] | CheckInputs


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Result of an evaluation: the payload, the check's state, its content hash and the provenance per item."""

    payload: VerdictSet
    state: State
    content_sha256: str
    inputs_provenance: tuple[Mapping[str, RefInput | LiteralInput], ...]


class _NoRecords:
    """Record source of an evaluation without references; `evaluate` refuses references before it is asked."""

    def get(self, result_id: str) -> ResultRecord:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "no record source was given")

    def payload(self, result_id: str) -> dict[str, Any]:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "no record source was given")


def _state_of(check: Check) -> State:
    """The lifecycle state of a check; task T11 resolves it from `approvals.yaml`, until then every check is a draft."""
    return "draft"


def _untracked(_model_id: str) -> int | None:
    """Revision function of a caller that tracks no model: every reference is accepted as current."""
    return None


def _prefixed(exc: ContractError, k: int) -> ContractError:
    """Return the same error with `field` prefixed by `items[<k>]` (the contract's field-path form, AC28)."""
    detail = exc.detail
    field = f"items[{k}]" if detail.field is None else f"items[{k}].{detail.field}"
    rest = detail.model_dump(exclude={"code", "message", "retryable", "field"})
    return ContractError(detail.code, detail.message, retryable=detail.retryable, field=field, **rest)


def _raw(check: Check, inputs: Mapping[str, Any] | CheckInputs, source: RecordSource | None) -> Mapping[str, Any]:
    """Return the raw JSON mapping of an item.

    Raises:
        ContractError: `INVALID_ARGUMENT` for inputs that are neither a mapping nor an instance of the check's model,
            or for a reference when no `source` is given.
    """
    if isinstance(inputs, CheckInputs):
        if not isinstance(inputs, check.inputs):
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "inputs is not an instance of the check's input model")
        return inputs.model_dump(mode="json", exclude_unset=True)
    if not isinstance(inputs, Mapping):
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "inputs must be a mapping or the check's input model")
    for name, value in inputs.items():
        if source is None and isinstance(value, Mapping) and "$ref" in value:
            field = name if isinstance(name, str) and _FIELD.fullmatch(name) else None
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, f"{name} is a reference but no source was given", field=field
            )
    return inputs


def _decide(check: Check, inp: Any, t: TraceRecorder, subject: Subject) -> VerdictStatus | None:
    """Run member scope, preconditions and body; return the status of the single framework verdict, or None.

    `None` means the body ran and its recorded verdicts stand (AC5, AC5a, AC6, AC28, AC29).
    """
    meta = check.meta
    if subject.kind not in meta.members:
        scope = sorted(kind.value for kind in meta.members)
        t.note(f"member scope ({meta.clauses[0]}): {subject.kind.value} not in {scope}")
        return VerdictStatus.NOT_APPLICABLE
    try:
        for p in check.preconditions:
            if not p.test(inp, t):
                t.note(f"{p.id} ({p.clause}): {p.description}")
                return VerdictStatus(p.outcome.value)
        check.body(inp, t)
    except NotImplementedGap as gap:
        if gap.gap_id not in {g.id for g in meta.gaps}:
            raise CheckDefinitionError(f"{meta.check_id}: gap {gap.gap_id} is not declared in the metadata") from gap
        t.note(f"{gap.gap_id} ({gap.clause}): {gap.reason}")
        return VerdictStatus.NEEDS_ENGINEER
    except _CONTAINED as exc:
        if isinstance(exc, ValidationError):  # a malformed model inside a body is a defect, not an arithmetic failure
            raise
        _log.warning("check item failed", extra={"check_id": meta.check_id, "error": type(exc).__name__})
        t.note(f"verdict ERROR: {type(exc).__name__}: {str(exc)[:500]}")
        return VerdictStatus.ERROR
    if not t.verdicts:
        raise CheckDefinitionError(f"{meta.check_id}: the body recorded no verdict")
    return None


def _item(
    check: Check, validated: ValidatedInput[Any], subject: Subject, k: int, t: TraceRecorder
) -> tuple[list[Verdict], list[str]]:
    """Evaluate one validated item into its verdicts (`trace_ref` is `#/traces/<k>`) and the trace's output names.

    The outputs are the recorded `demand`, `capacity` and `ratio` names of the body's verdicts, each once (AC9); a
    framework verdict (scope, precondition, gap, error) has none.
    """
    meta = check.meta
    status = _decide(check, validated.model, t, subject)
    if status is not None:
        framework = Verdict(
            source=VerdictSource.CODE_PACK,
            check_id=meta.check_id,
            code=meta.code,
            clause=meta.clauses[0],
            subject=subject,
            status=status,
            trace_ref=f"#/traces/{k}",
            assumptions=list(meta.assumptions),
        )
        return [framework], []
    names = [n for d in t.verdicts for n in (d.demand_name, d.capacity_name, d.ratio_name) if n is not None]
    return [build_verdict(d, meta, subject, trace_index=k) for d in t.verdicts], list(dict.fromkeys(names))


def evaluate_batch(
    check_id: str,
    items: Sequence[BatchItem],
    *,
    mode: Mode = "trial",
    registry: Registry | None = None,
    source: RecordSource | None = None,
    current_revision: Callable[[str], int | None] | None = None,
    policy: InputPolicy | None = None,
) -> Evaluation:
    """Evaluate a check on every item and return the `verdicts.set/1` payload (one trace per item, in order).

    `registry=None` uses `Registry.discover()`; `current_revision(model_id)` gives a model's revision or None
    (untracked, accepted); `policy=None` is `InputPolicy()`. Every item is validated before any is evaluated.

    Raises:
        ContractError: unknown check (`NOT_FOUND`), unknown mode, or an item that fails validation (AC27, AC28).
        CheckNotUsable: the check is not usable in `mode` (until the lifecycle task every check is `draft`).
        CheckDefinitionError: a body records no verdict or raises an undeclared gap, or the check is malformed.
    """
    return _run(check_id, items, True, mode, registry, source, current_revision, policy)


def evaluate(
    check_id: str,
    inputs: Mapping[str, Any] | CheckInputs,
    *,
    subject: Subject,
    mode: Mode = "trial",
    registry: Registry | None = None,
    source: RecordSource | None = None,
    current_revision: Callable[[str], int | None] | None = None,
    policy: InputPolicy | None = None,
) -> Evaluation:
    """Evaluate a check on one subject; see `evaluate_batch`. Error `field` values are not prefixed."""
    return _run(check_id, [BatchItem(subject, inputs)], False, mode, registry, source, current_revision, policy)


def _run(
    check_id: str,
    items: Sequence[BatchItem],
    batched: bool,
    mode: Mode,
    registry: Registry | None,
    source: RecordSource | None,
    current_revision: Callable[[str], int | None] | None,
    policy: InputPolicy | None,
) -> Evaluation:
    """Shared body of `evaluate` and `evaluate_batch`; `batched` prefixes the `field` of an item's error."""
    known = registry or Registry.discover()
    found = known.get(check_id)
    pack = next(p for p in known.packs if p.name == found.meta.pack)
    state = _state_of(found)
    if mode not in get_args(Mode):
        raise ContractError(ErrorCode.INVALID_ARGUMENT, f"unknown mode {str(mode)[:50]!r}", field="mode")
    if mode == "production":
        raise CheckNotUsable(check_id, f"state {state}: production mode needs an approved check")
    model: Any = found.inputs  # a CheckInputs subclass, checked when the check is defined
    validated: list[ValidatedInput[Any]] = []
    for k, item in enumerate(items):
        try:
            validated.append(
                validate_input(
                    model,
                    _raw(found, item.inputs, source),
                    source=source or _NoRecords(),
                    current_revision=current_revision or _untracked,
                    policy=policy or InputPolicy(),
                )
            )
        except ContractError as exc:
            if batched:
                raise _prefixed(exc, k) from exc
            raise
    digest = content_hash(found)
    recorders = [
        TraceRecorder(v, calc_id=check_id, calc_version=pack.version, content_sha256=digest, subject=i.subject)
        for v, i in zip(validated, items, strict=True)
    ]
    done = [
        _item(found, v, i.subject, k, t) for k, (v, i, t) in enumerate(zip(validated, items, recorders, strict=True))
    ]
    flat = assign_governing([v for verdicts, _ in done for v in verdicts])
    traces, start = [], 0
    for t, (verdicts, outputs) in zip(recorders, done, strict=True):
        own = flat[start : start + len(verdicts)]
        start += len(verdicts)
        status = next((v.status for v in own if v.governing), own[0].status)
        traces.append(t.to_trace(outputs=outputs, status=status))
    tally = Counter(v.status for v in flat)
    counts = {s: tally[s] for s in VerdictStatus}
    payload = VerdictSet(verdicts=flat, traces=traces, counts=counts, draft=state != "approved")
    return Evaluation(payload, state, digest, tuple(v.inputs for v in validated))
