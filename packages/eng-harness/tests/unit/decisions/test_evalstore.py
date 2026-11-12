"""Evaluation store and release verification (plan 0009 T9; spec 0009 AC41, AC42)."""

import sqlite3
from pathlib import Path
from typing import Literal

import pytest
from eng_contract.ids import FixedClock, SeededIdSource

from eng_harness.decisions._evalstore import EvalStore, ReleaseFinding, labels_sha256, provider_key, verify_releases
from eng_harness.decisions._labels import LabeledExample
from eng_harness.decisions._policy import DecisionPolicy, DecisionSettings, ShadowRelease
from eng_harness.decisions._record import Suggestion
from eng_harness.decisions.evaluation import EvalReport, EvalThresholds, ProviderEvalMetrics, evaluate_point
from eng_harness.decisions.interfaces import ProviderInfo

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
MODEL = ProviderInfo(provider="jev", model="jev-1", version="v1", is_local=False, supports_batch=True)
LLM = ProviderInfo(provider="openrouter", model="mini", version="v1", is_local=False, supports_batch=False)
MODEL_KEY = "model:jev/jev-1@v1"
LLM_KEY = "llm:openrouter/mini@v1"


def _store(root: Path) -> EvalStore:
    clock = FixedClock(START_MS, 1)
    return EvalStore(root, clock, SeededIdSource(b"evals", clock))


def _label(i: int, *, choice: str = "enlarge") -> LabeledExample:
    suggestion = Suggestion(
        tier=2, by=MODEL_KEY, outcome="shadow", choice="enlarge", confidence=0.9, latency_ms=10, shadow=True
    )
    return LabeledExample(
        label_id=f"lbl_{i:03d}", request_id=f"req_{i:03d}", point="footing_fix", point_version=1, run_id="run_1",
        step_path="/s", options=("enlarge", "rebar"), state=None, state_sha256="sha", label=choice, engineer="E",
        suggestions=(suggestion,), source="engineer_decision", created_at="2026-01-01T00:00:00.000Z",
    )  # fmt: skip


def test_append_only_and_reproducible(tmp_path: Path) -> None:
    labels = tuple(_label(i) for i in range(50))
    thresholds = EvalThresholds()
    report = evaluate_point(labels, thresholds)
    digest = labels_sha256(labels)
    assert digest == labels_sha256(tuple(reversed(labels)))  # sorted: order does not matter
    assert digest != labels_sha256((*labels[:-1], _label(49, choice="rebar")))  # a choice changes the hash
    assert len(digest) == 64

    store = _store(tmp_path)
    first = store.append("footing_fix", 1, report, thresholds, digest, "store")
    second = store.append("footing_fix", 1, evaluate_point(labels, thresholds), thresholds, digest, "store")
    assert first != second
    one, two = store.records("footing_fix")
    assert (one.evaluation_id, two.evaluation_id) == (first, second)
    assert one.labels_sha256 == two.labels_sha256 == digest
    assert one.report == two.report == report.model_dump(mode="json")
    assert one.by == (MODEL_KEY,)
    assert one.eligible is False
    assert one.min_confidence == 0.85
    assert one.source == "store"
    assert one.created_at == "2026-01-01T00:00:00.000Z"
    assert store.get(first) == one
    assert store.get("ev_missing") is None
    assert store.records("other_point") == ()

    conn = sqlite3.connect(tmp_path / "decisions" / "evaluations.sqlite")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE evaluations SET eligible = 1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM evaluations")
    conn.close()
    store.close()


def _eligible_report(*keys: str) -> EvalReport:
    metrics = ProviderEvalMetrics(cases=50, answered=50, above=50, agreeing=50, agreement=1.0)
    return EvalReport(by={k: metrics for k in keys}, eligible=True, reasons=())


def _record(
    store: EvalStore,
    *,
    point: str = "footing_fix",
    version: int = 1,
    keys: tuple[str, ...] = (MODEL_KEY, LLM_KEY),
    min_confidence: float = 0.85,
    eligible: bool = True,
) -> str:
    report = _eligible_report(*keys)
    if not eligible:
        report = report.model_copy(update={"eligible": False, "reasons": ("calibration_not_evaluated",)})
    thresholds = EvalThresholds(min_confidence=min_confidence)
    return store.append(point, version, report, thresholds, "0" * 64, "store")


def _verify(
    store: EvalStore,
    releases: dict[str, ShadowRelease],
    *,
    infos: dict[Literal["model", "llm"], ProviderInfo] | None = None,
    policy: DecisionPolicy | None = None,
    versions: dict[str, int] | None = None,
) -> tuple[dict[str, ShadowRelease], tuple[ReleaseFinding, ...]]:
    result = verify_releases(
        DecisionSettings(shadow_released=releases),
        store,
        {"model": MODEL, "llm": LLM} if infos is None else infos,
        {"footing_fix": policy or DecisionPolicy()},
        point_versions={"footing_fix": 1} if versions is None else versions,
    )
    return dict(result.releases), result.findings


def _evaluation(record: str, version: int = 1) -> ShadowRelease:
    return ShadowRelease(point_version=version, basis="evaluation", record=record)


def test_verify_releases(tmp_path: Path) -> None:
    store = _store(tmp_path)
    good = _record(store)
    other_point = _record(store, point="other")
    other_version = _record(store, version=2)
    ineligible = _record(store, eligible=False)
    high = _record(store, min_confidence=0.95)
    model_only = _record(store, keys=(MODEL_KEY,))

    kept, findings = _verify(store, {"footing_fix": _evaluation(good)})
    assert kept == {"footing_fix": _evaluation(good)}
    assert findings == ()
    assert provider_key("model", MODEL) == MODEL_KEY
    assert provider_key("llm", LLM) == LLM_KEY

    def reason(
        release: ShadowRelease,
        infos: dict[Literal["model", "llm"], ProviderInfo] | None = None,
        policy: DecisionPolicy | None = None,
        versions: dict[str, int] | None = None,
    ) -> str:
        kept_, found = _verify(store, {"footing_fix": release}, infos=infos, policy=policy, versions=versions)
        assert kept_ == {}
        assert len(found) == 1
        assert found[0].point == "footing_fix"
        return found[0].reason

    assert reason(_evaluation("ev_unknown")) == "record_missing"
    assert reason(_evaluation(f"{good}, ev_unknown")) == "record_missing"
    assert reason(_evaluation(other_point)) == "record_missing"
    assert reason(_evaluation(ineligible)) == "record_not_eligible"
    assert reason(_evaluation(good, 2)) == "point_version_changed"  # the release names version 2, current is 1
    assert reason(_evaluation(good, 2), versions={"footing_fix": 2}) == "point_version_changed"  # evaluated at 1
    assert reason(_evaluation(good), versions={}) == "point_version_changed"
    changed = MODEL.model_copy(update={"version": "v2"})
    assert reason(_evaluation(good), infos={"model": changed, "llm": LLM}) == "provider_changed"
    assert reason(_evaluation(model_only)) == "provider_changed"
    assert reason(_evaluation(high)) == "threshold_mismatch"
    assert reason(_evaluation(high), policy=DecisionPolicy(min_confidence=0.94)) == "threshold_mismatch"

    # kept: the evaluation's min_confidence equal to or below the policy's; a version-2 release at version 2
    kept, findings = _verify(store, {"footing_fix": _evaluation(high)}, policy=DecisionPolicy(min_confidence=0.95))
    assert (set(kept), findings) == ({"footing_fix"}, ())
    kept, _ = _verify(store, {"footing_fix": _evaluation(good)}, policy=DecisionPolicy(min_confidence=0.95))
    assert set(kept) == {"footing_fix"}
    kept, _ = _verify(store, {"footing_fix": _evaluation(other_version, 2)}, versions={"footing_fix": 2})
    assert set(kept) == {"footing_fix"}
    kept, _ = _verify(store, {"footing_fix": _evaluation(f"{good} {good},{model_only}")}, infos={"model": MODEL})
    assert set(kept) == {"footing_fix"}  # several ids; only the configured provider is required

    # owner basis: kept when its version is current, whatever the store holds
    owner = ShadowRelease(point_version=1, basis="owner", record="owner decision of the day")
    kept, findings = _verify(store, {"footing_fix": owner})
    assert (kept, findings) == ({"footing_fix": owner}, ())
    stale = owner.model_copy(update={"point_version": 2})
    kept, findings = _verify(store, {"footing_fix": stale})
    assert (kept, findings) == ({}, (ReleaseFinding(point="footing_fix", reason="point_version_changed"),))
    blank = owner.model_copy(update={"record": "  "})
    assert _verify(store, {"footing_fix": blank})[1] == (ReleaseFinding(point="footing_fix", reason="record_missing"),)

    # several points: kept ones stay, dropped ones are reported in point order
    kept, findings = _verify(
        store,
        {"zeta": owner, "footing_fix": _evaluation(good), "alpha": _evaluation("ev_unknown")},
        versions={"footing_fix": 1, "zeta": 1, "alpha": 1},
    )
    assert set(kept) == {"footing_fix", "zeta"}
    assert findings == (ReleaseFinding(point="alpha", reason="record_missing"),)
    store.close()
