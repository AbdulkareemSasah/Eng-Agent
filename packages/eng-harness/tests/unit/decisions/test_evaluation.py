"""Evaluation thresholds, metrics and eligibility (plan 0009 T8; spec 0009 AC37 to AC40)."""

import json
from pathlib import Path
from typing import Literal

import pytest
from pydantic import ValidationError

from eng_harness.decisions._labels import LabeledExample
from eng_harness.decisions._record import Suggestion
from eng_harness.decisions.evaluation import EvalThresholds, evaluate_point

THRESHOLDS_GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden" / "evaluation_thresholds_defaults.json"
REPORT_GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden" / "evaluation_fixture_report.json"

MODEL_BY = "model:jev/jev-1@v1"
LLM_BY = "llm:openrouter/mini@v1"
_STATE_SHA = "sha_fixture"


def _suggestion(
    by: str,
    outcome: str,
    *,
    choice: str | None = None,
    confidence: float | None = None,
    latency_ms: int = 0,
) -> Suggestion:
    return Suggestion.model_validate(
        {
            "tier": 2 if by.startswith("model:") else 3,
            "by": by,
            "outcome": outcome,
            "choice": choice,
            "confidence": confidence,
            "latency_ms": latency_ms,
            "shadow": outcome == "shadow",
        }
    )


def _label(
    request_id: str,
    label: str,
    *,
    suggestions: tuple[Suggestion, ...],
    source: Literal["engineer_decision", "engineer_override"] = "engineer_decision",
) -> LabeledExample:
    return LabeledExample(
        label_id=f"lbl_{request_id}",
        request_id=request_id,
        point="footing_fix",
        point_version=1,
        run_id="run_1",
        step_path="/step",
        options=("enlarge", "rebar"),
        state=None,
        state_sha256=_STATE_SHA,
        label=label,
        engineer="Engineer",
        suggestions=suggestions,
        source=source,
        created_at="2026-01-01T00:00:00.000Z",
    )


def _metrics_fixture_labels() -> tuple[LabeledExample, ...]:
    return (
        _label(
            "req_1",
            "enlarge",
            suggestions=(
                _suggestion(MODEL_BY, "shadow", choice="enlarge", confidence=0.90, latency_ms=100),
                _suggestion(LLM_BY, "shadow", choice="enlarge", confidence=0.88, latency_ms=120),
            ),
        ),
        _label(
            "req_2",
            "rebar",
            suggestions=(
                _suggestion(MODEL_BY, "accepted", choice="enlarge", confidence=0.92, latency_ms=200),
                _suggestion(LLM_BY, "skipped_local_only", latency_ms=0),
            ),
        ),
        _label(
            "req_3",
            "enlarge",
            suggestions=(
                _suggestion(MODEL_BY, "below_threshold", choice="enlarge", confidence=0.80, latency_ms=50),
                _suggestion(LLM_BY, "error", choice=None, latency_ms=300),
            ),
        ),
        _label(
            "req_4",
            "enlarge",
            suggestions=(
                _suggestion(MODEL_BY, "skipped_redaction", latency_ms=0),
                _suggestion(LLM_BY, "shadow", choice="rebar", confidence=0.86, latency_ms=80),
            ),
        ),
        _label(
            "req_5",
            "enlarge",
            suggestions=(
                _suggestion(MODEL_BY, "shadow", choice="enlarge", confidence=0.99, latency_ms=10),
                _suggestion(LLM_BY, "shadow", choice="enlarge", confidence=0.91, latency_ms=30),
            ),
        ),
    )


def test_thresholds_defaults_and_bounds() -> None:
    golden = json.loads(THRESHOLDS_GOLDEN.read_text(encoding="utf-8"))
    assert "12-decision-layer.md" in golden["source"]
    assert EvalThresholds().model_dump() == golden["defaults"]
    assert EvalThresholds(min_above_threshold=5).min_above_threshold == 5
    assert EvalThresholds(min_cases=50, min_agreement=1.0, min_confidence=1.0).model_dump()["min_agreement"] == 1.0

    with pytest.raises(ValidationError):
        EvalThresholds(min_cases=49)
    with pytest.raises(ValidationError):
        EvalThresholds(min_agreement=0.9499)
    with pytest.raises(ValidationError):
        EvalThresholds(min_confidence=0.84)
    with pytest.raises(ValidationError):
        EvalThresholds(min_agreement=1.01)
    with pytest.raises(ValidationError):
        EvalThresholds(min_confidence=1.01)
    with pytest.raises(ValidationError):
        EvalThresholds.model_validate({"unknown": 1})


def test_metrics_match_fixture() -> None:
    golden = json.loads(REPORT_GOLDEN.read_text(encoding="utf-8"))
    assert golden["source"].startswith("hand-computed")
    report = evaluate_point(_metrics_fixture_labels(), EvalThresholds())
    assert report.model_dump(mode="json") == golden["report"]
    assert set(report.by) == {MODEL_BY, LLM_BY}


def _provider_label(
    request_id: str,
    *,
    model_agree: bool = True,
    model_confidence: float = 0.90,
) -> LabeledExample:
    choice = "enlarge" if model_agree else "rebar"
    engineer = "enlarge"
    return _label(
        request_id,
        engineer,
        suggestions=(
            _suggestion(
                MODEL_BY,
                "shadow",
                choice=choice,
                confidence=model_confidence,
                latency_ms=10,
            ),
        ),
    )


def _many_labels(n: int, *, disagree: int = 0) -> tuple[LabeledExample, ...]:
    labels: list[LabeledExample] = []
    for i in range(n):
        labels.append(_provider_label(f"req_{i}", model_agree=i < n - disagree))
    return tuple(labels)


def test_eligibility_and_boundaries() -> None:
    few = evaluate_point(_many_labels(49), EvalThresholds())
    assert few.eligible is False
    assert "too_few_cases" in few.reasons
    assert "calibration_not_evaluated" in few.reasons

    enough = evaluate_point(_many_labels(50), EvalThresholds())
    assert "too_few_cases" not in enough.reasons
    assert enough.eligible is False
    assert "calibration_not_evaluated" in enough.reasons

    # 0.94 agreement fails; 0.95 passes (calibration still blocks eligibility).
    disagree_51 = evaluate_point(_many_labels(100, disagree=6), EvalThresholds())
    metrics = disagree_51.by[MODEL_BY]
    assert metrics.agreement is not None
    assert metrics.agreement == pytest.approx(0.94)
    assert "agreement_below_threshold" in disagree_51.reasons

    agree_exact = evaluate_point(_many_labels(100, disagree=5), EvalThresholds())
    metrics_ok = agree_exact.by[MODEL_BY]
    assert metrics_ok.agreement == 0.95
    assert "agreement_below_threshold" not in agree_exact.reasons
    assert agree_exact.eligible is False
    assert "calibration_not_evaluated" in agree_exact.reasons

    no_above = evaluate_point(
        tuple(
            _label(
                f"req_{i}",
                "enlarge",
                suggestions=(_suggestion(MODEL_BY, "below_threshold", choice="enlarge", confidence=0.5, latency_ms=1),),
            )
            for i in range(50)
        ),
        EvalThresholds(),
    )
    assert "no_answers_above_threshold" in no_above.reasons

    need_more = evaluate_point(_many_labels(50), EvalThresholds(min_above_threshold=51))
    assert "too_few_above_threshold" in need_more.reasons


def test_override_counts_as_disagreement() -> None:
    decision = _label(
        "req_ov",
        "enlarge",
        suggestions=(_suggestion(MODEL_BY, "accepted", choice="enlarge", confidence=0.92, latency_ms=5),),
    )
    override = _label(
        "req_ov",
        "rebar",
        suggestions=(),
        source="engineer_override",
    )
    report = evaluate_point((decision, override), EvalThresholds())
    metrics = report.by[MODEL_BY]
    assert metrics.cases == 1
    assert metrics.answered == 1
    assert metrics.above == 1
    assert metrics.agreeing == 0
    assert metrics.agreement == 0.0
