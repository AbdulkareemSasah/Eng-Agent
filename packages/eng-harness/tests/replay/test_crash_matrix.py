"""The crash matrix: a worker process killed at each crash point of every step, then resumed (plan 0001 T19, AC30).

A worker process (`_worker.py`) runs the mixed workflow and ends itself with `os._exit` at S-10's four crash points of
each step: before `step_started` (on the event committed just before it), after `step_started`, after the call has
returned (before its result is journaled) and after `step_completed` or `step_failed`. This process resumes the run
with a new engine and compares it with an uninterrupted run: every write was applied exactly once (the ledger file
that the dead process wrote shows each call), the output is the same and the step identities are the same. Nothing here
is timed: a worker is waited for, never polled against a deadline.
"""

import asyncio
import importlib
import multiprocessing
from pathlib import Path
from typing import Any

from eng_harness.engine import RunStatus
from eng_harness.engine._steps import op_id
from eng_harness.journal import EventType, JournalReader
from eng_harness.journal import _events as ev

# Imported by name at run time: the folder has no `__init__.py`, so a static import gives the file two module names.
# The spawned worker finds `replay._worker` through the `tests` folder on the path it inherits.
worker = importlib.import_module("replay._worker")
Crash = Any

T = EventType
POINTS = ("before_started", "after_started", "after_effect", "after_completed")


def _work(root: Path, crash: Crash) -> int | None:
    """Run the worker in a process of its own (started by `spawn`, so it shares nothing) and wait for it to end."""
    root.mkdir(parents=True)
    process = multiprocessing.get_context("spawn").Process(target=worker.run_worker, args=(str(root), crash))
    process.start()
    process.join()
    return process.exitcode


def _resume(root: Path) -> Any:
    """Resume the only run of the workspace with a new engine, as a new process would, and return its outcome."""
    rig = worker.worker_rig(root, 1, None)
    (run_id,) = rig.run_ids()
    return asyncio.run(worker.build_engine(rig, None).resume(run_id))


def _journal(root: Path) -> tuple[str, list[ev.Event], set[tuple[str, str, str]]]:
    """The run id, the events and the identities (path, kind, name) of the block's steps of the run in `root`.

    The housekeeping steps of a resume (paths that start with `@`) belong to the resume, not to the workflow.
    """
    run_dir = next((root / "ws" / "runs").glob("run_*"))
    reader = JournalReader(run_dir)
    try:
        return (
            run_dir.name,
            reader.events(),
            {(s.path, s.kind, s.name) for s in reader.steps() if not s.path.startswith("@")},
        )
    finally:
        reader.close()


def _writes(root: Path) -> list[tuple[str, str, str | None]]:
    """The writes that the host applied, as (tool, arguments, model), sorted; an op_id may not repeat among them."""
    done = [e for e in worker.read_ledger(root / "host-ledger.jsonl") if e["effect"] == "write" and e["ok"]]
    assert len({e["op_id"] for e in done}) == len(done), "a write was applied twice under one op_id"
    return sorted((e["tool"], str(sorted(e["args"].items())), e["model"]) for e in done)


def _matrix(root: Path) -> dict[tuple[str, int], Crash]:
    """The crash points of every step of the uninterrupted run in `root`, from its journal and its ledger file."""
    run_id, events, _ = _journal(root)
    calls = {e["op_id"]: n for n, e in enumerate(worker.read_ledger(root / "host-ledger.jsonl"), start=1)}
    cases: dict[tuple[str, int], Crash] = {}
    for event in events:
        if event.type is not T.STEP_STARTED:
            continue
        assert event.path is not None
        assert event.attempt is not None
        ended = next(
            e for e in events
            if e.path == event.path and e.attempt == event.attempt and e.type in (T.STEP_COMPLETED, T.STEP_FAILED)
        )  # fmt: skip
        points = {
            "before_started": worker.Crash("before_started", seq=event.seq - 1),
            "after_started": worker.Crash("after_started", seq=event.seq),
            "after_completed": worker.Crash("after_completed", seq=ended.seq),
        }
        call = calls.get(op_id(run_id, event.path, event.attempt))
        if call is not None:
            points["after_effect"] = worker.Crash("after_effect", call=call)
        for name, crash in points.items():
            cases.setdefault((name, crash.seq if crash.seq is not None else -(crash.call or 0)), crash)
    return cases


def test_crash_matrix(tmp_path: Path) -> None:
    """AC30: each crash point of each step, resumed: writes applied once, same output, same step identities."""
    base = tmp_path / "uninterrupted"
    assert _work(base, None) == 0
    expected = _resume(base)
    assert expected.status is RunStatus.COMPLETED
    _, _, identities = _journal(base)
    writes = _writes(base)
    assert [(w[0], w[2]) for w in writes] == [("write_b", "m1"), ("write_b", "m1"), ("write_b", "m2")]
    cases = _matrix(base)
    assert {crash.point for crash in cases.values()} == set(POINTS)  # every point is exercised, writes included
    assert len(cases) >= 20  # six steps with four points each, less the points that two steps share
    for number, (key, crash) in enumerate(sorted(cases.items())):
        root = tmp_path / f"case-{number}"
        assert _work(root, crash) == worker.CRASH_EXIT, f"the worker did not reach {key}"
        outcome = _resume(root)
        assert outcome.status is RunStatus.COMPLETED, key
        assert outcome.output == expected.output, key
        assert _journal(root)[2] == identities, key
        assert _writes(root) == writes, key
