"""Shadow-mode evaluation metrics, eligibility and the ``evaluate`` command (spec 0009 section 4.10; 12 section 6).

Pure functions over labeled examples: per-provider case counts, agreement, abstention and latency percentiles
(nearest rank, process/05 section 7). Calibration is gap E-G1 until the owner defines a metric (spec 0005 Q4)."""

import argparse
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import SystemClock, SystemIdSource
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from eng_harness.decisions import _points
from eng_harness.decisions._evalstore import (
    EvalStore,
    ReleaseFinding,
    ReleaseVerification,
    StoredEvaluation,
    labels_sha256,
    provider_key,
    verify_releases,
)
from eng_harness.decisions._labels import LabeledExample, LabelStore
from eng_harness.decisions._policy import DecisionSettings
from eng_harness.decisions._record import Suggestion

__all__ = [
    "EvalReport",
    "EvalStore",
    "EvalThresholds",
    "ProviderEvalMetrics",
    "ReleaseFinding",
    "ReleaseVerification",
    "StoredEvaluation",
    "evaluate_point",
    "labels_from_export",
    "labels_sha256",
    "main",
    "provider_key",
    "verify_releases",
]

_SKIPPED_OUTCOMES = frozenset({"skipped_local_only", "skipped_redaction"})
_ANSWERED_OUTCOMES = frozenset({"shadow", "accepted", "below_threshold"})
_ELIGIBILITY_REASON = Literal[
    "too_few_cases",
    "no_answers_above_threshold",
    "too_few_above_threshold",
    "agreement_below_threshold",
    "calibration_not_evaluated",
]


class EvalThresholds(BaseModel):
    """Minimum evidence before a point may leave shadow mode (12 section 6; section 3 ``min_confidence``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_cases: int = Field(default=50, ge=50)  # count; 12 section 6
    min_agreement: float = Field(default=0.95, ge=0.95, le=1.0)  # ratio; 12 section 6
    min_confidence: float = Field(default=0.85, ge=0.85, le=1.0)  # ratio; 12 section 3 and section 6
    min_above_threshold: int | None = Field(default=None, ge=1)  # optional owner floor (spec Q4)


class ProviderEvalMetrics(BaseModel):
    """Counts and ratios for one provider key (``by``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cases: int = Field(ge=0)
    answered: int = Field(ge=0)
    above: int = Field(ge=0)
    agreeing: int = Field(ge=0)
    agreement: float | None = None
    abstention_rate: float | None = None
    latency_p50_ms: int | None = None
    latency_p95_ms: int | None = None


class EvalReport(BaseModel):
    """Evaluation of one point and version; one entry per provider key with labeled cases."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    by: Mapping[str, ProviderEvalMetrics]
    eligible: bool
    reasons: tuple[_ELIGIBILITY_REASON, ...]


def evaluate_point(labels: Sequence[LabeledExample], thresholds: EvalThresholds) -> EvalReport:
    """Compute per-provider metrics and eligibility from append-ordered labels (spec AC38, AC39)."""
    rows = _effective_rows(labels)
    provider_keys = _provider_keys(rows)
    by: dict[str, ProviderEvalMetrics] = {}
    all_reasons: set[_ELIGIBILITY_REASON] = set()
    for key in sorted(provider_keys):
        metrics = _metrics_for(key, rows, thresholds)
        if metrics.cases == 0:
            continue
        by[key] = metrics
        all_reasons.update(_reasons_for(metrics, thresholds))
    reasons = tuple(sorted(all_reasons))
    eligible = len(reasons) == 0
    return EvalReport(by=by, eligible=eligible, reasons=reasons)


def _effective_rows(labels: Sequence[LabeledExample]) -> list[tuple[LabeledExample, tuple[Suggestion, ...]]]:
    grouped: dict[str, list[LabeledExample]] = {}
    for label in labels:
        grouped.setdefault(label.request_id, []).append(label)
    rows: list[tuple[LabeledExample, tuple[Suggestion, ...]]] = []
    for group in grouped.values():
        override = next((label for label in group if label.source == "engineer_override"), None)
        decision = next((label for label in group if label.source == "engineer_decision"), None)
        if override is not None:
            if decision is None:
                continue
            rows.append((override, decision.suggestions))
        elif decision is not None:
            rows.append((decision, decision.suggestions))
    return rows


def _provider_keys(rows: Sequence[tuple[LabeledExample, tuple[Suggestion, ...]]]) -> set[str]:
    keys: set[str] = set()
    for _, suggestions in rows:
        for suggestion in suggestions:
            if suggestion.outcome not in _SKIPPED_OUTCOMES:
                keys.add(suggestion.by)
    return keys


def _metrics_for(
    provider: str,
    rows: Sequence[tuple[LabeledExample, tuple[Suggestion, ...]]],
    thresholds: EvalThresholds,
) -> ProviderEvalMetrics:
    cases = answered = above = agreeing = 0
    latencies: list[int] = []
    for engineer_label, suggestions in rows:
        suggestion = next((s for s in suggestions if s.by == provider), None)
        if suggestion is None or suggestion.outcome in _SKIPPED_OUTCOMES:
            continue
        cases += 1
        latencies.append(suggestion.latency_ms)
        if suggestion.outcome in _ANSWERED_OUTCOMES:
            answered += 1
            confidence = suggestion.confidence
            if confidence is not None and confidence >= thresholds.min_confidence:
                above += 1
                if suggestion.choice == engineer_label.label:
                    agreeing += 1
    agreement = (agreeing / above) if above else None
    abstention = (1.0 - above / cases) if cases else None
    return ProviderEvalMetrics(
        cases=cases,
        answered=answered,
        above=above,
        agreeing=agreeing,
        agreement=agreement,
        abstention_rate=abstention,
        latency_p50_ms=_nearest_rank(latencies, 50) if latencies else None,
        latency_p95_ms=_nearest_rank(latencies, 95) if latencies else None,
    )


def _nearest_rank(values: Sequence[int], percentile: float) -> int:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile / 100 * len(ordered)) - 1)
    return ordered[index]


def _reasons_for(metrics: ProviderEvalMetrics, thresholds: EvalThresholds) -> set[_ELIGIBILITY_REASON]:
    reasons: set[_ELIGIBILITY_REASON] = set()
    if metrics.cases < thresholds.min_cases:
        reasons.add("too_few_cases")
    if metrics.above == 0:
        reasons.add("no_answers_above_threshold")
    elif thresholds.min_above_threshold is not None and metrics.above < thresholds.min_above_threshold:
        reasons.add("too_few_above_threshold")
    if metrics.above > 0 and metrics.agreement is not None and metrics.agreement < thresholds.min_agreement:
        reasons.add("agreement_below_threshold")
    reasons.add("calibration_not_evaluated")
    return reasons


def labels_from_export(path: Path, point: str, point_version: int) -> tuple[LabeledExample, ...]:
    """Read anonymized export lines (spec 0005 AC39) of one point version as labels (AC44).

    The export has no ids, engineer, run or step: each line gets ``export_<n>`` ids (a line is one request) and fixed
    placeholders for the others, so an override line is never paired with a decision, as in the store.

    Raises:
        ContractError: ``INVALID_ARGUMENT`` (field ``from_export``) when the file or a line cannot be read.
    """
    labels: list[LabeledExample] = []
    try:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            data: dict[str, Any] = json.loads(line)
            ids = {"label_id": f"export_{number}", "request_id": f"export_{number}"}
            placeholders = {"engineer": "export", "run_id": "export", "step_path": "export"}
            label = LabeledExample.model_validate({**data, **ids, **placeholders})
            if label.point == point and label.point_version == point_version:
                labels.append(label)
    except (OSError, ValueError, TypeError, ValidationError) as exc:  # json errors are ValueError
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT, "the label export cannot be read", field="from_export",
            hint=type(exc).__name__,
        ) from exc  # fmt: skip
    return tuple(labels)


def _current_version(point: str) -> int:
    found = _points.discover().get(point)
    if found is None:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT, "unknown decision point", field="point", hint="pass --point-version"
        )
    return found.version


def _print_report(point: str, version: int, source: str, report: EvalReport, evaluation_id: str) -> None:
    lines = [f"point: {point} v{version} (labels from the {source})"]
    lines += [f"{key}: {metrics.model_dump_json()}" for key, metrics in report.by.items()]
    lines += [
        f"eligible: {str(report.eligible).lower()}",
        f"reasons: {', '.join(report.reasons) or 'none'}",
        "verdict: the owner releases a point (12 section 6); this command never does",
        f"record: {evaluation_id}",
    ]
    sys.stdout.write("".join(f"{line}\n" for line in lines))


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``evaluate POINT [--workspace DIR] [--point-version N] [--from-export FILE]`` (AC43, AC44); return 0.

    Prints the report and appends one record to ``evaluations.sqlite``; no other file is written.

    Raises:
        ContractError: ``INVALID_ARGUMENT`` for an unknown point or an unreadable export; ``StoreWriteError``.
    """
    parser = argparse.ArgumentParser(prog="eng_harness.decisions.evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("evaluate")
    cmd.add_argument("point")
    cmd.add_argument("--workspace", type=Path, default=Path.cwd())
    cmd.add_argument("--point-version", type=int, default=None)
    cmd.add_argument("--from-export", type=Path, default=None)
    args = parser.parse_args(argv)
    version = args.point_version if args.point_version is not None else _current_version(args.point)
    clock = SystemClock()
    ids = SystemIdSource(clock)
    labels: tuple[LabeledExample, ...] = ()
    if args.from_export is not None:
        labels = labels_from_export(args.from_export, args.point, version)
    elif (args.workspace / "decisions" / "decisions.sqlite").exists():  # a missing store is not created here
        label_store = LabelStore(args.workspace, DecisionSettings(), clock, ids)
        try:
            labels = label_store.read(args.point, version)
        finally:
            label_store.close()
    thresholds = EvalThresholds()
    report = evaluate_point(labels, thresholds)
    source: Literal["store", "export"] = "store" if args.from_export is None else "export"
    store = EvalStore(args.workspace, clock, ids)
    try:
        evaluation_id = store.append(args.point, version, report, thresholds, labels_sha256(labels), source)
    finally:
        store.close()
    _print_report(args.point, version, source, report, evaluation_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
