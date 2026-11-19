"""`status` command: run states, heartbeat liveness, integrity and read-only check (AC11, AC18, AC71; plan T16)."""

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from eng_contract.envelope import Provenance
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from helpers.cli_deps import START_MS, Rig

from eng_harness._kinds import HARNESS_KINDS
from eng_harness._runlock import RunLock
from eng_harness.cli import ExitCode
from eng_harness.journal import EventType, JournalWriter

SHA = "a" * 64
PRODUCER = Provenance(tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0)


def _header(run_id: str, base_ref: str, *, workflow: str = "edit_flow") -> dict[str, Any]:
    return {
        "run_id": run_id,
        "workflow": workflow,
        "block": {"name": workflow, "version": "1", "code_sha256": SHA},
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
    }


def _make_run(
    runs_dir: Path,
    store: ResultStore,
    clock: FixedClock,
    ids: SeededIdSource,
    run_id: str,
    *,
    workflow: str = "edit_flow",
) -> tuple[Path, JournalWriter, str]:
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    base_ref = store.put("harness.journal_blob/1", {"value": 1}, PRODUCER).result_id
    writer = JournalWriter(run_dir, store, clock, ids)
    writer.append(EventType.RUN_STARTED, _header(run_id, base_ref, workflow=workflow))
    return run_dir, writer, base_ref


def _snapshot(run_dir: Path) -> tuple[bytes, int, set[str]]:
    journal = run_dir / "journal.sqlite"
    entries = {p.name for p in run_dir.iterdir() if not p.name.startswith("journal.sqlite-")}
    return journal.read_bytes(), journal.stat().st_mtime_ns, entries


def test_states_and_read_only(tmp_path: Path) -> None:
    clock = FixedClock(START_MS, 1_000)
    ids = SeededIdSource(b"st", clock)
    ws_root = tmp_path / "ws"
    ws_root.mkdir()
    workspace = Workspace(root=ws_root, classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    runs_dir = ws_root / "runs"

    # 0. Empty workspace (no `runs/` folder yet): list mode succeeds and creates nothing.
    empty_rig = Rig(tmp_path / "empty")
    empty_rig.workspace.mkdir(parents=True)
    assert empty_rig.main("status", "--json") == ExitCode.OK
    assert json.loads(empty_rig.out.getvalue()) == []
    assert not empty_rig.runs.exists()

    # 1. Live run (`RUNNING`) with fresh heartbeat, then stale heartbeat (`no heartbeat` with age).
    live_id = f"run_{ids.new_ulid()}"
    live_dir, live_w, _ = _make_run(runs_dir, store, clock, ids, live_id)
    live_w.append(
        EventType.STEP_STARTED,
        {"kind": "tool", "name": "csi_read_model_state", "args": {}, "args_sha256": SHA, "effect": "read"},
        path="0",
        attempt=1,
    )
    live_w.close()
    lock = RunLock(live_dir)
    lock.acquire()
    try:
        (live_dir / "heartbeat.json").write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "at": "2026-01-01T00:00:01.000Z",
                    "step": "csi_read_model_state",
                    "step_started_at": "2026-01-01T00:00:01.000Z",
                    "seq": 2,
                }
            ),
            encoding="utf-8",
        )
        fresh_clock = FixedClock(START_MS + 11_000, 1)  # 10 s after beat (stale_after = 3 * 10 = 30 s)
        rig_fresh = Rig(tmp_path)
        assert rig_fresh.main("status", live_id, "--json", clock=fresh_clock) == ExitCode.OK
        fresh_json = json.loads(rig_fresh.out.getvalue())
        assert fresh_json["run_id"] == live_id
        assert fresh_json["status"] == "RUNNING"
        assert fresh_json["steps_in_progress"][0]["name"] == "csi_read_model_state"
        assert fresh_json["heartbeat"]["state"] == "running"
        assert fresh_json["heartbeat"]["age_ms"] == 10_000
        assert "stop" in fresh_json["next_command"]

        stale_clock = FixedClock(START_MS + 35_000, 1)  # 34 s after beat > 30 s
        rig_stale = Rig(tmp_path)
        assert rig_stale.main("status", live_id, clock=stale_clock) == ExitCode.OK
        stale_text = rig_stale.out.getvalue()
        assert "RUNNING" in stale_text
        assert "no heartbeat" in stale_text.lower()
        assert "00:34" in stale_text
        assert "csi_read_model_state" in stale_text
        assert "http" not in stale_text
    finally:
        lock.release()

    # 2. Interrupted run (`INTERRUPTED`: non-terminal, not locked).
    inter_id = f"run_{ids.new_ulid()}"
    inter_dir, inter_w, _ = _make_run(runs_dir, store, clock, ids, inter_id)
    inter_w.append(
        EventType.STEP_STARTED,
        {"kind": "calc", "name": "harness.model_diff", "args": {}, "args_sha256": SHA, "effect": "none"},
        path="1",
        attempt=1,
    )
    inter_w.close()

    # 3. Paused run (`PAUSED`) with pending approval & input requests.
    paused_id = f"run_{ids.new_ulid()}"
    paused_dir, paused_w, base_ref = _make_run(runs_dir, store, clock, ids, paused_id)
    paused_w.append(
        EventType.APPROVAL_REQUESTED,
        {
            "request_id": "apr_1",
            "kind": "change_set",
            "title": "Approve edits",
            "preview_ref": base_ref,
            "shown_sha256": SHA,
            "binding": {},
            "items": ["i1"],
        },
    )
    paused_w.append(
        EventType.INPUT_REQUESTED,
        {"request_id": "inp_1", "kind": "block", "title": "Need loads", "fields_schema_sha256": SHA},
    )
    paused_w.append(EventType.RUN_PAUSED, {"reason": "awaiting_approval", "request_ids": ["apr_1", "inp_1"]})
    paused_w.close()

    # 4. Escalated run (`NEEDS_ENGINEER`) with control sequence in detail (must be sanitized).
    esc_id = f"run_{ids.new_ulid()}"
    esc_dir, esc_w, _ = _make_run(runs_dir, store, clock, ids, esc_id)
    esc_w.append(
        EventType.RUN_ESCALATED,
        {"reason": "needs_reconciliation", "detail": "host\x1b[2J hung", "evidence": []},
    )
    esc_w.close()

    # 5. Completed run (`COMPLETED`).
    done_id = f"run_{ids.new_ulid()}"
    done_dir, done_w, done_ref = _make_run(runs_dir, store, clock, ids, done_id)
    done_w.append(EventType.RUN_COMPLETED, {"output_ref": done_ref, "output_sha256": SHA, "draft": False})
    done_w.close()

    # 6. Failed run (`FAILED`).
    fail_id = f"run_{ids.new_ulid()}"
    fail_dir, fail_w, _ = _make_run(runs_dir, store, clock, ids, fail_id)
    fail_w.append(
        EventType.RUN_FAILED,
        {"reason": "abandoned", "by": "engineer:ada"},
    )
    fail_w.close()

    # Verify all non-live states (both JSON and table) and read-only invariant.
    for run_id, run_dir, expected_status, expected_next in [
        (inter_id, inter_dir, "INTERRUPTED", f"resume {inter_id}"),
        (paused_id, paused_dir, "PAUSED", f"resume {paused_id}"),
        (esc_id, esc_dir, "NEEDS_ENGINEER", f"resume {esc_id}"),
        (done_id, done_dir, "COMPLETED", f"report {done_id}"),
        (fail_id, fail_dir, "FAILED", f"report {fail_id}"),
    ]:
        before_bytes, before_mtime, before_files = _snapshot(run_dir)
        before_hash = hashlib.sha256(before_bytes).hexdigest()

        rig_json = Rig(tmp_path)
        assert rig_json.main("status", run_id, "--json") == ExitCode.OK
        data = json.loads(rig_json.out.getvalue())
        assert data["status"] == expected_status
        assert expected_next in data["next_command"]

        rig_tab = Rig(tmp_path)
        assert rig_tab.main("status", run_id) == ExitCode.OK
        table = rig_tab.out.getvalue()
        assert expected_status in table
        assert expected_next in table
        assert "\x1b" not in table
        assert "http" not in table
        assert "launch" not in table.lower()
        assert "token" not in table.lower()

        after_bytes, after_mtime, after_files = _snapshot(run_dir)
        assert hashlib.sha256(after_bytes).hexdigest() == before_hash
        assert after_mtime == before_mtime
        assert after_files == before_files

    # Check paused pending requests (kind and title) and escalation details specifically.
    rig_p = Rig(tmp_path)
    assert rig_p.main("status", paused_id, "--json") == ExitCode.OK
    p_data = json.loads(rig_p.out.getvalue())
    assert [(item["kind"], item["title"]) for item in p_data["pending"]] == [
        ("change_set", "Approve edits"),
        ("block", "Need loads"),
    ]
    rig_e = Rig(tmp_path)
    assert rig_e.main("status", esc_id, "--json") == ExitCode.OK
    e_data = json.loads(rig_e.out.getvalue())
    assert e_data["escalation"]["reason"] == "needs_reconciliation"
    assert "\x1b" not in e_data["escalation"]["detail"]

    # List mode: returns at most 20 most recent runs.
    for idx in range(18):
        extra_id = f"run_{ids.new_ulid()}"
        _, ew, er = _make_run(runs_dir, store, clock, ids, extra_id, workflow=f"wf_{idx}")
        ew.append(EventType.RUN_COMPLETED, {"output_ref": er, "output_sha256": SHA, "draft": False})
        ew.close()
    rig_list = Rig(tmp_path)
    assert rig_list.main("status", "--json") == ExitCode.OK
    listed = json.loads(rig_list.out.getvalue())
    assert len(listed) == 20
    rig_list_txt = Rig(tmp_path)
    assert rig_list_txt.main("status") == ExitCode.OK
    assert listed[0]["run_id"] in rig_list_txt.out.getvalue()

    # 7. Altered journal exits 5 naming the first bad `seq`, and leaves journal bytes untouched.
    conn = sqlite3.connect(fail_dir / "journal.sqlite")
    try:
        conn.execute("UPDATE events SET chain_sha256 = ? WHERE seq = 2", ("f" * 64,))
    except sqlite3.DatabaseError:
        # Triggers prevent UPDATE; drop trigger temporarily to simulate tampering on disk.
        conn.execute("DROP TRIGGER events_no_update")
        conn.execute("UPDATE events SET chain_sha256 = ? WHERE seq = 2", ("f" * 64,))
        conn.commit()
    finally:
        conn.close()
    tampered_bytes = (fail_dir / "journal.sqlite").read_bytes()
    rig_bad = Rig(tmp_path)
    assert rig_bad.main("status", fail_id) == ExitCode.JOURNAL_INTEGRITY
    assert "seq 2" in rig_bad.err.getvalue()
    assert (fail_dir / "journal.sqlite").read_bytes() == tampered_bytes

    # 8. Unknown id exits 6.
    missing_id = "run_" + "0" * 26
    for bad_id in (missing_id, "../escape"):
        rig_miss = Rig(tmp_path)
        assert rig_miss.main("status", bad_id) == ExitCode.NOT_FOUND
        assert bad_id in rig_miss.err.getvalue()

    # 9. Invalid workspace exits 2 with message and remedy, nothing created (AC71).
    rig_nows = Rig(tmp_path / "no_ws")
    assert rig_nows.main("status", environ={}) == ExitCode.USAGE
    assert "no workspace is configured (set ENG_WORKSPACE)" in rig_nows.err.getvalue()
    assert not rig_nows.workspace.exists()


def test_status_list_skips_non_runs_handles_tampered_and_boundary(tmp_path: Path) -> None:
    clock = FixedClock(START_MS, 1_000)
    ids = SeededIdSource(b"sb", clock)
    ws_root = tmp_path / "ws"
    ws_root.mkdir()
    workspace = Workspace(root=ws_root, classification=LocationClass.LOCAL)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    runs_dir = ws_root / "runs"

    # Empty workspace with `runs/` missing: human mode prints "no runs".
    empty_rig = Rig(tmp_path / "empty")
    empty_rig.workspace.mkdir(parents=True)
    assert empty_rig.main("status") == ExitCode.OK
    assert empty_rig.out.getvalue() == "no runs\n"

    # Non-run entries in `runs/` are ignored; tampered run in list reports JOURNAL_INTEGRITY.
    runs_dir.mkdir(parents=True)
    (runs_dir / "stray.txt").write_text("x", encoding="utf-8")
    (runs_dir / "not_a_run").mkdir()
    bad_id = f"run_{ids.new_ulid()}"
    bad_dir, bad_w, _ = _make_run(runs_dir, store, clock, ids, bad_id)
    bad_w.close()
    conn = sqlite3.connect(bad_dir / "journal.sqlite")
    try:
        conn.execute("DROP TRIGGER events_no_update")
        conn.execute("UPDATE events SET chain_sha256 = ? WHERE seq = 1", ("f" * 64,))
        conn.commit()
    finally:
        conn.close()

    live_id = f"run_{ids.new_ulid()}"
    live_dir, live_w, _ = _make_run(runs_dir, store, clock, ids, live_id)
    live_w.close()
    lock = RunLock(live_dir)
    lock.acquire()
    try:
        (live_dir / "heartbeat.json").write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "at": "2026-01-01T00:00:00.000Z",
                    "step": None,
                    "step_started_at": None,
                    "seq": 1,
                }
            ),
            encoding="utf-8",
        )
        # Exactly 30_000 ms (3 * 10 s) is still running; 30_001 ms is no_heartbeat.
        rig_at = Rig(tmp_path)
        assert rig_at.main("status", live_id, "--json", clock=FixedClock(START_MS + 30_000, 1)) == ExitCode.OK
        assert json.loads(rig_at.out.getvalue())["heartbeat"]["state"] == "running"

        rig_past = Rig(tmp_path)
        assert rig_past.main("status", live_id, "--json", clock=FixedClock(START_MS + 30_001, 1)) == ExitCode.OK
        assert json.loads(rig_past.out.getvalue())["heartbeat"]["state"] == "no_heartbeat"
    finally:
        lock.release()

    rig_list = Rig(tmp_path)
    assert rig_list.main("status", "--json") == ExitCode.OK
    listed = json.loads(rig_list.out.getvalue())
    by_id = {item["run_id"]: item for item in listed}
    assert set(by_id) == {live_id, bad_id}
    assert by_id[bad_id]["status"] == "JOURNAL_INTEGRITY"
    assert "seq 1" in by_id[bad_id]["error"]
