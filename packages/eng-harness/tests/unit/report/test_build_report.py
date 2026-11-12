"""Report document build: inputs only, determinism, integrity and live banner (spec 0006 AC50, AC57)."""

import ast
import importlib.util
import os
import sqlite3
import stat
from pathlib import Path

import pytest
from eng_contract.envelope import Provenance
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ResultStore
from fixtures.report_run import build_report_run

from eng_harness import __version__
from eng_harness._runlock import RunLock
from eng_harness.errors import JournalIntegrityError
from eng_harness.journal import EventType, JournalReader, JournalWriter
from eng_harness.report import ReleaseMarks, build_report

_FORBIDDEN = frozenset(
    {
        "fcntl",
        "ftplib",
        "gzip",
        "http",
        "io",
        "mmap",
        "multiprocessing",
        "os",
        "pathlib",
        "pickle",
        "select",
        "shelve",
        "shutil",
        "signal",
        "socket",
        "subprocess",
        "tarfile",
        "tempfile",
        "urllib",
        "zipfile",
    }
)
_SHA = "a" * 64
_MARKS = ReleaseMarks(records={})


def _top_level_imports(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                found.add(node.module.split(".", 1)[0])
    return found


def test_inputs_only_and_deterministic(
    run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: FixedClock
) -> None:
    """AC50: `_document` imports no file or process module; the same inputs give the same bytes."""
    document = Path(importlib.util.find_spec("eng_harness.report._document").origin)  # type: ignore[union-attr]
    assert _top_level_imports(document).isdisjoint(_FORBIDDEN)
    build_report_run(run_dir, store, ids)
    (run_dir / "notes.txt").write_text("irrelevant", encoding="utf-8")
    os.chmod(run_dir / "notes.txt", 0)
    reader = JournalReader(run_dir)
    try:
        first = build_report(reader, store, _MARKS, clock, __version__)
        second = build_report(reader, store, _MARKS, clock, __version__)
    finally:
        os.chmod(run_dir / "notes.txt", stat.S_IWUSR | stat.S_IRUSR)
        reader.close()
    assert first == second
    assert first.startswith("<!doctype html>")


def test_tampered_refused_live_banner(
    run_dir: Path, store: ResultStore, ids: SeededIdSource, clock: FixedClock
) -> None:
    """AC57: an altered journal is refused; a live run states progress as of the last seq."""
    producer = Provenance(
        tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
    )
    base = store.put("harness.journal_blob/1", {"value": 1}, producer).result_id
    header = {
        "run_id": "run_x",
        "workflow": "w",
        "block": {"name": "b", "version": "1", "code_sha256": _SHA},
        "input_sha256": _SHA,
        "mode": "work_on_copy",
        "run_class": "production",
        "engine_version": "1",
        "contract_version": "eng-contract/1",
        "settings_sha256": _SHA,
        "servers": [],
        "always_ask": [],
    }
    writer = JournalWriter(run_dir, store, clock, ids)
    writer.append(EventType.RUN_STARTED, {**header, "input_ref": base, "basis_ref": base})
    writer.append(EventType.STEP_STARTED, {"kind": "tool", "name": "t", "args": {}, "args_sha256": _SHA, "effect": "read"}, path="0", attempt=1)  # fmt: skip
    writer.close()
    with sqlite3.connect(run_dir / "journal.sqlite") as conn:
        conn.execute("UPDATE events SET chain_sha256 = ? WHERE seq = 2", ("b" * 64,))
        conn.commit()
    with pytest.raises(JournalIntegrityError):
        build_report(JournalReader(run_dir), store, _MARKS, clock, __version__)
    lock = RunLock(run_dir)
    lock.acquire()
    try:
        reader = JournalReader(run_dir)
        try:
            html = build_report(reader, store, _MARKS, clock, __version__)
        finally:
            reader.close()
        assert "run in progress as of seq 2" in html
    finally:
        lock.release()
