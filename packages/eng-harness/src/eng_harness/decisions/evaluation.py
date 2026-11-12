"""Shadow-mode evaluation metrics and eligibility (spec 0009 section 4.10; 12 section 6).

Pure functions over labeled examples: per-provider case counts, agreement, abstention and latency percentiles
(nearest rank, process/05 section 7). Calibration is gap E-G1 until the owner defines a metric (spec 0005 Q4).
"""

import math
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from eng_harness.decisions._labels import LabeledExample
from eng_harness.decisions._record import Suggestion

__all__ = ["EvalReport", "EvalThresholds", "ProviderEvalMetrics", "evaluate_point"]

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
