"""Event to line latency of the terminal sink (plan 0006 T5; spec 0006 AC20, 11 section 10)."""

import threading
import time

from eng_harness.journal import PAYLOAD_MODELS, Event, EventType
from eng_harness.progress import ExpectedTimes, ProgressRenderer, TerminalProgress

SHA = "a" * 64
SAVED = {
    "model_key": "m", "model_id": "mdl_" + "0" * 26, "revision": 1, "fingerprint": "f", "file_sha256": SHA,
    "file_name": "a.edb", "role": "working_copy",
}  # fmt: skip
EVENTS = 200
LIMIT_S = 0.200  # AC20: p95 under 200 ms


class _Stamping:
    """Records the arrival time of each written line."""

    def __init__(self) -> None:
        self.arrived: dict[str, float] = {}
        self.done = threading.Event()

    def write(self, text: str) -> int:
        now = time.perf_counter()
        for line in text.splitlines():
            self.arrived[line.split()[2]] = now
        if len(self.arrived) >= EVENTS:
            self.done.set()
        return len(text)

    def flush(self) -> None:
        return None


def test_event_to_line_p95() -> None:
    stream = _Stamping()
    sink = TerminalProgress(ProgressRenderer("plain", ExpectedTimes({})), stream, mode="plain", queue_lines=1000)
    emitted: dict[str, float] = {}
    for i in range(EVENTS):
        name = f"m{i}.edb"
        payload = PAYLOAD_MODELS[EventType.MODEL_SAVED].model_validate({**SAVED, "file_name": name})
        event = Event(i + 1, EventType.MODEL_SAVED, None, None, "2026-01-01T00:00:00.000Z", payload)
        emitted[name] = time.perf_counter()
        sink.emit(event)
        time.sleep(0.001)
    assert stream.done.wait(10)
    sink.close()
    latencies = sorted(stream.arrived[name] - emitted[name] for name in emitted)
    assert latencies[int(0.95 * EVENTS) - 1] < LIMIT_S
