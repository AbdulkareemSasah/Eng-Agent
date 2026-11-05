"""An open request shows "waiting for engineer" and nothing else (spec 0006 AC17)."""

from typing import Any

from eng_harness.journal import PAYLOAD_MODELS, Event, EventType
from eng_harness.progress import Estimate, ExpectedTimes, ProgressRenderer

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
REQUEST: dict[str, Any] = {
    "request_id": "a1", "kind": "INFO", "title": "Apply change", "preview_ref": "res_" + "0" * 26,
    "shown_sha256": "a" * 64, "binding": {}, "items": [],
}  # fmt: skip


def _requested(title: str) -> Event:
    payload = PAYLOAD_MODELS[EventType.APPROVAL_REQUESTED].model_validate({**REQUEST, "title": title})
    return Event(1, EventType.APPROVAL_REQUESTED, None, None, "2026-01-01T00:00:20.000Z", payload)


def test_waiting_shows_no_expected_or_url() -> None:
    expected = ExpectedTimes({("tool", "t"): Estimate(50_000, 40_000, 70_000, 3)})
    renderer = ProgressRenderer("terminal", expected)
    out = renderer.feed(_requested("Apply change"))
    assert "waiting for engineer: Apply change, 00:00" in out
    live = renderer.tick(START_MS + 50_000)  # thirty seconds after the request
    assert live == "\r\x1b[2Kwaiting for engineer: Apply change, 00:30"
    for text in (out, live):
        assert "expected" not in text
        assert "http" not in text
        assert "127.0.0.1" not in text


def test_waiting_title_is_sanitized() -> None:
    out = ProgressRenderer("plain", ExpectedTimes({})).feed(_requested("a\x1b[31mb"))
    assert "\x1b" not in out
    assert "<U+001B>" in out
