"""Progress text in the three modes against the snapshots (plan 0006 T4; spec 0006 AC16)."""

from pathlib import Path
from typing import Any

from eng_harness.journal import PAYLOAD_MODELS, Event, EventType
from eng_harness.progress import Estimate, ExpectedTimes, ProgressRenderer

SNAPSHOTS = Path(__file__).resolve().parents[1] / "data" / "snapshots" / "progress"
START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
SHA = "a" * 64
REF = "res_" + "0" * 26
T = EventType
HEADER: dict[str, Any] = {
    "run_id": "run_x", "workflow": "w", "block": {"name": "b", "version": "1", "code_sha256": SHA},
    "input_ref": REF, "input_sha256": SHA, "basis_ref": REF, "mode": "work_on_copy", "run_class": "trial",
    "engine_version": "1", "contract_version": "eng-contract/1", "settings_sha256": SHA, "servers": [],
    "always_ask": [],
}  # fmt: skip
STARTED = {"kind": "tool", "args": {}, "args_sha256": SHA, "effect": "read"}
REQUEST = {
    "request_id": "a1", "kind": "INFO", "title": "Apply change", "preview_ref": REF, "shown_sha256": SHA,
    "binding": {}, "items": [],
}  # fmt: skip
RESOLVED = {"request_id": "a1", "shown_sha256": SHA, "decision": "approve", "rejected_items": [], "by": "engineer:x"}
SAVED = {
    "model_key": "m", "model_id": "mdl_" + "0" * 26, "revision": 1, "fingerprint": "f", "file_sha256": SHA,
    "file_name": "a.edb", "role": "working_copy",
}  # fmt: skip


def _at(seconds: int) -> str:
    return f"2026-01-01T00:{seconds // 60:02d}:{seconds % 60:02d}.000Z"


def _events() -> list[Event]:
    rows: list[tuple[int, T, dict[str, Any], str | None]] = [
        (0, T.RUN_STARTED, HEADER, None),
        (0, T.STEP_STARTED, {**STARTED, "name": "read_model"}, "0"),
        (5, T.STEP_COMPLETED, {"output_ref": REF, "duration_ms": 5000}, "0"),
        (5, T.STEP_STARTED, {**STARTED, "name": "analyze"}, "1"),
        (20, T.APPROVAL_REQUESTED, REQUEST, None),
        (50, T.APPROVAL_RESOLVED, RESOLVED, None),
        (65, T.STEP_COMPLETED, {"output_ref": REF, "duration_ms": 60000}, "1"),
        (65, T.MODEL_SAVED, SAVED, None),
        (70, T.RUN_COMPLETED, {"output_ref": REF, "output_sha256": SHA, "draft": True}, None),
    ]  # fmt: skip
    return [
        Event(i, kind, path, 1 if path is not None else None, _at(sec), PAYLOAD_MODELS[kind].model_validate(body))
        for i, (sec, kind, body, path) in enumerate(rows, start=1)
    ]


def _expected() -> ExpectedTimes:
    return ExpectedTimes({("tool", "analyze"): Estimate(50_000, 40_000, 70_000, 3)})


def _chunks(mode: Any) -> list[str]:
    renderer = ProgressRenderer(mode, _expected())
    return [renderer.feed(e) for e in _events()]


def _visible(chunk: str) -> str:
    return chunk.replace("\r", "<CR>").replace("\x1b[2K", "<ERASE>")


def _snapshot(name: str) -> str:
    return (SNAPSHOTS / name).read_text(encoding="utf-8")


def test_tty_plain_json() -> None:
    terminal = "\n".join(_visible(c).rstrip("\n") for c in _chunks("terminal") if c) + "\n"
    assert terminal == _snapshot("terminal.txt")
    assert "".join(_chunks("plain")) == _snapshot("plain.txt")
    assert "".join(_chunks("json")) == _snapshot("json.txt")


def test_heartbeat_line() -> None:
    renderer = ProgressRenderer("plain", _expected())
    for event in _events()[:4]:
        renderer.feed(event)
    line = renderer.heartbeat_line(START_MS + 35_000, 4)
    assert (
        line
        == "heartbeat: analyze still running, 00:30, expected ~00:50 (00:40 to 01:10, 3 earlier runs), journal seq 4\n"
    )
