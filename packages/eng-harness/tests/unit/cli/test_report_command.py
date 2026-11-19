"""`report` command: atomic write, `--out`/`--force`, integrity and cycle timings (AC12, AC69, AC71; plan T16)."""

import json
import sqlite3
from pathlib import Path

from eng_contract.envelope import Provenance
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from helpers.cli_deps import START_MS, WORKFLOW, Rig, completes

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.cli import ExitCode
from eng_harness.journal import EventType, JournalReader, JournalWriter

SHA = "a" * 64


PRODUCER = Provenance(tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0)


def test_report_atomic_replacement(tmp_path: Path, monkeypatch) -> None:
    """`report --force` keeps the destination intact when rename fails, then replaces through the same path."""
    import pytest
    from eng_harness.report import _write

    rig = Rig(tmp_path / "ws_atomic", script=completes)
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    [run_id] = rig.run_ids()
    target = tmp_path / "existing.html"
    target.write_text("original", encoding="utf-8")

    def interrupted(source, destination):
        assert Path(destination).read_text(encoding="utf-8") == "original"
        assert Path(source).read_text(encoding="utf-8").startswith("<!doctype html>")
        raise OSError("interrupted")

    monkeypatch.setattr(_write.os, "replace", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        Rig(tmp_path / "ws_atomic").main("report", run_id, "--out", str(target), "--force")
    assert target.read_text(encoding="utf-8") == "original"

    monkeypatch.undo()
    assert Rig(tmp_path / "ws_atomic").main("report", run_id, "--out", str(target), "--force") == ExitCode.OK
    assert target.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_output_rules(tmp_path: Path) -> None:
    # 1. Create a run without writing a report yet.
    rig = Rig(tmp_path / "ws_case", script=completes)
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    [run_id] = rig.run_ids()
    run_dir = rig.runs / run_id
    default_report = run_dir / "report" / "report.html"
    assert not default_report.exists()

    # 2. `report <run_id>` writes `<run>/report/report.html` atomically (no .tmp left behind).
    rep = Rig(tmp_path / "ws_case")
    assert rep.main("report", run_id) == ExitCode.OK
    first_html = default_report.read_text(encoding="utf-8")
    assert first_html.startswith("<!doctype html>")
    assert [p.name for p in (run_dir / "report").iterdir()] == ["report.html"]

    # Re-running without `--out` overwrites `<run>/report/report.html` without `--force`.
    assert Rig(tmp_path / "ws_case").main("report", run_id) == ExitCode.OK
    assert default_report.read_text(encoding="utf-8").startswith("<!doctype html>")

    # 3. `--out FILE` writes to FILE, refuses existing FILE without `--force`, and overwrites with `--force`.
    custom = tmp_path / "custom" / "out.html"
    assert Rig(tmp_path / "ws_case").main("report", run_id, "--out", str(custom)) == ExitCode.OK
    assert custom.read_text(encoding="utf-8").startswith("<!doctype html>")

    custom.write_text("sentinel", encoding="utf-8")
    refused = Rig(tmp_path / "ws_case")
    assert refused.main("report", run_id, "--out", str(custom)) == ExitCode.USAGE
    assert custom.read_text(encoding="utf-8") == "sentinel"
    assert "exists" in refused.err.getvalue().lower()

    assert Rig(tmp_path / "ws_case").main("report", run_id, "--out", str(custom), "--force") == ExitCode.OK
    assert custom.read_text(encoding="utf-8").startswith("<!doctype html>")

    # 4. Altered journal gives exit 5 and writes nothing.
    default_report.unlink()
    conn = sqlite3.connect(run_dir / "journal.sqlite")
    try:
        conn.execute("DROP TRIGGER events_no_update")
        conn.execute("UPDATE events SET chain_sha256 = ? WHERE seq = 2", ("f" * 64,))
        conn.commit()
    finally:
        conn.close()
    tampered_out = tmp_path / "should_not_exist.html"
    bad = Rig(tmp_path / "ws_case")
    assert bad.main("report", run_id, "--out", str(tampered_out)) == ExitCode.JOURNAL_INTEGRITY
    assert not default_report.exists()
    assert not tampered_out.exists()
    assert not (run_dir / "report" / "cycle-timings.json").exists()

    # 5. Unknown run id exits 6.
    missing_id = "run_" + "0" * 26
    assert Rig(tmp_path / "ws_case").main("report", missing_id) == ExitCode.NOT_FOUND

    # 6. Invalid workspace exits 2 with message and remedy, nothing created (AC71).
    nows = Rig(tmp_path / "no_ws")
    assert nows.main("report", missing_id, environ={}) == ExitCode.USAGE
    assert "no workspace is configured (set ENG_WORKSPACE)" in nows.err.getvalue()
    assert not nows.workspace.exists()


def test_cycle_timings_file(tmp_path: Path) -> None:
    from eng_harness.report import edit_cycle_timings, write_cycle_timings

    # 1. Run with an edit cycle writes `<run>/report/cycle-timings.json` even when `--out` is passed.
    rig = Rig(tmp_path / "cycles")
    rig.workspace.mkdir(parents=True)
    ws = Workspace(root=rig.workspace, classification=LocationClass.LOCAL)
    clock = FixedClock(START_MS, 5_000)
    ids = SeededIdSource(b"cyc", clock)
    store = ResultStore(ws, HARNESS_KINDS, ids, clock)
    run_id = f"run_{ids.new_ulid()}"
    run_dir = rig.runs / run_id
    run_dir.mkdir(parents=True)
    base_ref = store.put("harness.journal_blob/1", {"value": 1}, PRODUCER).result_id

    writer = JournalWriter(run_dir, store, clock, ids)
    writer.append(
        EventType.RUN_STARTED,
        {
            "run_id": run_id,
            "workflow": "model_edit_cycle",
            "block": {"name": "model_edit_cycle", "version": "1", "code_sha256": SHA},
            "input_ref": base_ref,
            "input_sha256": SHA,
            "basis_ref": base_ref,
            "mode": "work_on_copy",
            "run_class": "trial",
            "engine_version": "1",
            "contract_version": "eng-contract/1",
            "settings_sha256": SHA,
            "servers": [],
            "always_ask": [],
        },
    )
    writer.append(
        EventType.STEP_STARTED,
        {
            "kind": "block",
            "name": "edit_cycle_once",
            "args": {},
            "args_sha256": SHA,
            "effect": "none",
            "child": {"name": "edit_cycle_once", "version": "1", "code_sha256": SHA},
        },
        path="1/0/0",
        attempt=1,
    )
    writer.append(
        EventType.STEP_STARTED,
        {"kind": "tool", "name": "csi_read_model_state", "args": {}, "args_sha256": SHA, "effect": "read"},
        path="1/0/0/0",
        attempt=1,
    )
    writer.append(EventType.STEP_COMPLETED, {"duration_ms": 2_000}, path="1/0/0/0", attempt=1)
    writer.append(EventType.STEP_COMPLETED, {"duration_ms": 10_000}, path="1/0/0", attempt=1)
    writer.append(EventType.RUN_COMPLETED, {"output_ref": base_ref, "output_sha256": SHA, "draft": False})
    writer.close()

    custom = tmp_path / "elsewhere" / "custom.html"
    assert rig.main("report", run_id, "--out", str(custom)) == ExitCode.OK
    assert custom.is_file()
    timings_path = run_dir / "report" / "cycle-timings.json"
    assert timings_path.is_file()

    expected_path = tmp_path / "expected.json"
    reader = JournalReader(run_dir)
    try:
        write_cycle_timings(edit_cycle_timings(reader, store), expected_path)
    finally:
        reader.close()
    assert json.loads(timings_path.read_text(encoding="utf-8")) == json.loads(expected_path.read_text(encoding="utf-8"))

    # 2. Run without an edit cycle writes no `cycle-timings.json`.
    plain = Rig(tmp_path / "plain", script=completes)
    assert plain.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    [plain_id] = plain.run_ids()
    assert plain.main("report", plain_id) == ExitCode.OK
    assert (plain.runs / plain_id / "report" / "report.html").is_file()
    assert not (plain.runs / plain_id / "report" / "cycle-timings.json").exists()


def test_report_refuses_directory_target_and_missing_store_ref(tmp_path: Path) -> None:
    rig = Rig(tmp_path / "edge", script=completes, keep_basis_ref=True)
    assert rig.main("run", WORKFLOW, "--no-report", "--progress", "off") == ExitCode.OK
    [run_id] = rig.run_ids()

    # `--out` pointing to an existing directory is refused with USAGE.
    out_dir = tmp_path / "existing_dir"
    out_dir.mkdir()
    bad_dir = Rig(tmp_path / "edge")
    assert bad_dir.main("report", run_id, "--out", str(out_dir), "--force") == ExitCode.USAGE
    assert "directory" in bad_dir.err.getvalue().lower()

    # A journal whose `basis_ref` cannot be found in the store maps to NOT_FOUND.
    missing_ref = Rig(tmp_path / "edge")
    assert missing_ref.main("report", run_id) == ExitCode.NOT_FOUND
    assert "REF_NOT_FOUND" in missing_ref.err.getvalue()
