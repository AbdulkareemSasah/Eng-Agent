"""One request takes one answer: of two simultaneous ones exactly one is accepted (plan 0006 T7; AC30)."""

import threading
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from pathlib import Path

from helpers.engine_standin import approval_request, wired

from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev


def test_concurrent_answers_one_wins(tmp_path: Path) -> None:
    request = approval_request()
    with wired(tmp_path) as w:
        future = w.open(request)
        barrier = threading.Barrier(2)

        def post(name: str) -> int:
            token = w.client.token(f"/request/{request.request_id}")
            barrier.wait(timeout=5)
            form = {"csrf": token, "shown_sha256": request.shown_sha256, "by": name, "decision": "approve"}
            return w.client.post(f"/answer/{request.request_id}", form).status

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = [f.result(timeout=10) for f in [pool.submit(post, "ann"), pool.submit(post, "bob")]]
        given = future.result(timeout=5)
    assert sorted(statuses) == [HTTPStatus.OK, HTTPStatus.CONFLICT]
    assert given is not None
    resolved = [
        e.payload for e in JournalReader(w.engine.run_dir).events() if isinstance(e.payload, ev.ApprovalResolved)
    ]
    assert [(r.by, r.decision) for r in resolved] == [("engineer:" + given.by, "approve")]  # one record, the winner's
    assert statuses[0 if given.by == "ann" else 1] == HTTPStatus.OK  # and its poster got the 200
