"""The ``evaluate`` command (plan 0009 T9; spec 0009 AC43, AC44)."""

from pathlib import Path

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource

from eng_harness.decisions._evalstore import EvalStore, StoredEvaluation, labels_sha256
from eng_harness.decisions._labels import LabeledExample, LabelStore
from eng_harness.decisions._policy import DecisionSettings
from eng_harness.decisions._record import Suggestion
from eng_harness.decisions.evaluation import EvalThresholds, evaluate_point, main

START_MS = 1_767_225_600_000
MODEL_KEY = "model:jev/jev-1@v1"


def _label(i: int, *, point: str = "footing_fix", version: int = 1, agree: bool = True) -> LabeledExample:
    suggestion = Suggestion(
        tier=2, by=MODEL_KEY, outcome="shadow", choice="enlarge" if agree else "rebar", confidence=0.9,
        latency_ms=10 + i, shadow=True,
    )  # fmt: skip
    return LabeledExample(
        label_id=f"lbl_{i:03d}", request_id=f"req_{i:03d}", point=point, point_version=version, run_id="run_1",
        step_path="/s", options=("enlarge", "rebar"), state=None, state_sha256=f"sha_{i}", label="enlarge",
        engineer="Engineer", suggestions=(suggestion,), source="engineer_decision",
        created_at="2026-01-01T00:00:00.000Z",
    )  # fmt: skip


def _workspace(root: Path) -> LabelStore:
    clock = FixedClock(START_MS, 1)
    store = LabelStore(root, DecisionSettings(export_enabled=True), clock, SeededIdSource(b"labels", clock))
    for i in range(6):
        store.append(_label(i, agree=i != 5), [])
    store.append(_label(9, version=2), [])  # another version: never read
    store.append(_label(10, point="other"), [])  # another point: never read
    return store


def _files(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _records(root: Path, point: str = "footing_fix") -> tuple[StoredEvaluation, ...]:
    clock = FixedClock(START_MS, 1)
    store = EvalStore(root, clock, SeededIdSource(b"read", clock))
    try:
        return store.records(point)
    finally:
        store.close()


def test_evaluate_writes_record_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    labels = _workspace(tmp_path)
    expected = labels.read("footing_fix", 1)
    labels.close()
    before = _files(tmp_path)

    code = main(["evaluate", "footing_fix", "--workspace", str(tmp_path), "--point-version", "1"])

    assert code == 0
    after = _files(tmp_path)
    assert set(after) - set(before) == {"decisions/evaluations.sqlite"}
    assert {k: v for k, v in after.items() if k in before} == before  # nothing else changed
    assert not (tmp_path / "harness.toml").exists()
    (record,) = _records(tmp_path)
    report = evaluate_point(expected, EvalThresholds())
    assert record.source == "store"
    assert record.report == report.model_dump(mode="json")
    assert record.labels_sha256 == labels_sha256(expected)
    assert record.point_version == 1
    out = capsys.readouterr().out
    assert "footing_fix" in out
    assert "eligible: false" in out
    assert "too_few_cases" in out
    assert "calibration_not_evaluated" in out
    assert record.evaluation_id in out
    assert "released" in out  # the verdict says that the owner releases, never the system


def test_evaluate_from_export(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    workspace, folder = tmp_path / "ws", tmp_path / "evals"
    labels = _workspace(workspace)
    export = labels.export_labels("footing_fix", folder)
    labels.close()
    assert "request_id" not in export.read_text(encoding="utf-8")

    assert main(["evaluate", "footing_fix", "--workspace", str(workspace), "--point-version", "1"]) == 0
    assert main(["evaluate", "footing_fix", "--workspace", str(workspace), "--point-version", "1",
                 "--from-export", str(export)]) == 0  # fmt: skip
    from_store, from_export = _records(workspace)
    assert from_store.source == "store"
    assert from_export.source == "export"
    assert from_export.report == from_store.report
    assert from_export.by == from_store.by
    assert "eligible: false" in capsys.readouterr().out

    export.write_text("not json\n", encoding="utf-8")
    with pytest.raises(ContractError) as info:
        main(["evaluate", "footing_fix", "--workspace", str(workspace), "--point-version", "1",
              "--from-export", str(export)])  # fmt: skip
    assert info.value.code is ErrorCode.INVALID_ARGUMENT
