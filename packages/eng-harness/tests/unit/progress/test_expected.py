"""Expected times from earlier journals (plan 0006 T4; spec 0006 AC15)."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore

from eng_harness.journal import EventType, JournalWriter
from eng_harness.progress import Estimate, ExpectedTimes

T = EventType
REF = "res_" + "0" * 26
SHA = "a" * 64
ERR = {"error": {"harness_code": "NEEDS_ENGINEER", "message": "m"}, "retryable": False, "duration_ms": 1}


def _header(workflow: str) -> dict[str, Any]:
    return {
        "run_id": "run_x", "workflow": workflow, "block": {"name": "b", "version": "1", "code_sha256": SHA},
        "input_ref": REF, "input_sha256": SHA, "basis_ref": REF, "mode": "work_on_copy", "run_class": "trial",
        "engine_version": "1", "contract_version": "eng-contract/1", "settings_sha256": SHA, "servers": [],
        "always_ask": [],
    }  # fmt: skip


def _done(ms: int) -> dict[str, Any]:
    return {"result": {"ref": REF, "summary": {}, "warnings": [], "complete": True}, "duration_ms": ms}


def _run(
    workspace: Path, store: ResultStore, ids: SeededIdSource, workflow: str, steps: list[tuple[str, int]],
    *, end: T | None = T.RUN_COMPLETED,
) -> None:  # fmt: skip
    """Write one journal; a negative duration makes the step fail."""
    run_dir = workspace / "runs" / f"run_{ids.new_ulid()}"
    run_dir.mkdir(parents=True)
    writer = JournalWriter(run_dir, store, FixedClock(1_767_225_600_000, 1), ids)
    writer.append(T.RUN_STARTED, _header(workflow))
    for i, (name, ms) in enumerate(steps):
        started = {"kind": "tool", "name": name, "args": {}, "args_sha256": SHA, "effect": "read"}
        writer.append(T.STEP_STARTED, started, path=str(i), attempt=1)
        if ms < 0:
            writer.append(T.STEP_FAILED, ERR, path=str(i), attempt=1)
        else:
            writer.append(T.STEP_COMPLETED, _done(ms), path=str(i), attempt=1)
    if end is T.RUN_COMPLETED:
        writer.append(T.RUN_COMPLETED, {"output_ref": REF, "output_sha256": SHA, "draft": True})
    elif end is T.RUN_FAILED:
        writer.append(T.RUN_FAILED, {"reason": "abandoned", "by": "engineer:x"})


def _settings(history_runs: int = 20, min_samples: int = 3) -> Any:
    return SimpleNamespace(history_runs=history_runs, min_samples=min_samples)


def test_median_range_and_min_samples(tmp_path: Path, store: ResultStore, ids: SeededIdSource) -> None:
    for ms in (130_000, 65_000, 280_000):
        _run(tmp_path, store, ids, "w", [("analyze", ms), ("flaky", -1)])
    _run(tmp_path, store, ids, "other", [("analyze", 999_999_000)])  # another workflow
    _run(tmp_path, store, ids, "w", [("analyze", 999_999_000)], end=None)  # not ended
    _run(tmp_path, store, ids, "w", [("analyze", 999_999_000)], end=T.RUN_FAILED)  # ended FAILED
    times = ExpectedTimes.build(tmp_path, "w", _settings())
    assert times.lookup("tool", "analyze") == Estimate(median_ms=130_000, min_ms=65_000, max_ms=280_000, samples=3)
    assert times.describe("tool", "analyze") == "expected ~02:10 (01:05 to 04:40, 3 earlier runs)"
    assert times.lookup("tool", "flaky") is None  # a failed step contributes nothing
    assert times.describe("tool", "flaky") == "no estimate"
    assert times.describe("tool", "never_seen") == "no estimate"
    assert ExpectedTimes.build(tmp_path, "w", _settings(min_samples=4)).lookup("tool", "analyze") is None


def test_history_runs_takes_the_latest(tmp_path: Path, store: ResultStore, ids: SeededIdSource) -> None:
    for ms in (1000, 2000, 3000, 4000):
        _run(tmp_path, store, ids, "w", [("s", ms)])
    est = ExpectedTimes.build(tmp_path, "w", _settings(history_runs=3)).lookup("tool", "s")
    assert est == Estimate(median_ms=3000, min_ms=2000, max_ms=4000, samples=3)


def test_no_runs_folder_gives_no_estimate(tmp_path: Path) -> None:
    assert ExpectedTimes.build(tmp_path, "w", _settings()).lookup("tool", "s") is None
