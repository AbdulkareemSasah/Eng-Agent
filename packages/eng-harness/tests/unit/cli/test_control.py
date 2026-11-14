"""The stop file: written by rename, read, removed, and seen by the run control (plan 0006 T7b; spec 0006 4.4.8)."""

import json
import os
from pathlib import Path

import pytest
from eng_contract.ids import FixedClock
from eng_harness.cli._control import STOP_FILE, FileRunControl, StopRequest, read_stop, remove_stop, write_stop
from pydantic import ValidationError

AT = "2026-01-01T00:00:00.000Z"
CLOCK_MS = 1_767_225_600_000


def _clock() -> FixedClock:
    return FixedClock(CLOCK_MS, 1)


def test_stop_file_written_by_rename_and_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str, dict[str, str]]] = []
    real = os.replace

    def spy(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        seen.append((str(src), str(dst), json.loads(Path(src).read_text(encoding="utf-8"))))  # whole before the rename
        real(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    write_stop(tmp_path, "cli", _clock())
    (src, dst, content) = seen[0]
    assert len(seen) == 1
    assert Path(dst) == tmp_path / STOP_FILE
    assert STOP_FILE == "stop.json"
    assert Path(src).parent == tmp_path
    assert Path(src) != Path(dst)
    assert content == {"requested_at": AT, "by": "cli"}
    assert [p.name for p in tmp_path.iterdir()] == ["stop.json"]  # no temporary file is left
    assert json.loads((tmp_path / STOP_FILE).read_text(encoding="utf-8")) == {"requested_at": AT, "by": "cli"}
    assert read_stop(tmp_path) == StopRequest(requested_at=AT, by="cli")
    remove_stop(tmp_path)
    assert not (tmp_path / STOP_FILE).exists()
    assert read_stop(tmp_path) is None
    remove_stop(tmp_path)  # removing what is not there is no error


def test_write_replaces_an_earlier_request(tmp_path: Path) -> None:
    write_stop(tmp_path, "cli", _clock())
    write_stop(tmp_path, "signal", FixedClock(CLOCK_MS + 5_000, 1))
    assert read_stop(tmp_path) == StopRequest(requested_at="2026-01-01T00:00:05.000Z", by="signal")
    assert [p.name for p in tmp_path.iterdir()] == [STOP_FILE]


def test_stop_request_has_exactly_two_members() -> None:
    assert set(StopRequest.model_fields) == {"requested_at", "by"}
    for bad in ({"requested_at": AT, "by": "cli", "x": 1}, {"requested_at": AT, "by": "other"}, {"by": "cli"}):
        with pytest.raises(ValidationError):
            StopRequest.model_validate(bad)
    with pytest.raises(ValidationError):
        StopRequest.model_validate({"requested_at": "yesterday", "by": "cli"})


def test_read_refuses_a_damaged_file(tmp_path: Path) -> None:
    (tmp_path / STOP_FILE).write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="stop"):
        read_stop(tmp_path)


def test_run_control_follows_the_file(tmp_path: Path) -> None:
    control = FileRunControl(tmp_path)
    run = tmp_path / "run_a"
    run.mkdir()
    assert control.stop_requested("run_a") is False
    assert control.stop_requested("run_missing") is False  # no run folder: no stop
    write_stop(run, "signal", _clock())
    assert control.stop_requested("run_a") is True
    assert control.stop_requested("run_b") is False  # another run is not stopped
    remove_stop(run)
    assert control.stop_requested("run_a") is False


def test_run_control_ignores_the_content(tmp_path: Path) -> None:
    run = tmp_path / "run_a"
    run.mkdir()
    (run / STOP_FILE).write_text("not json", encoding="utf-8")
    assert FileRunControl(tmp_path).stop_requested("run_a") is True
