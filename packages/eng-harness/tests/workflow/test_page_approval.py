"""The page approval end to end against the engine stand-in: hash binding and confirmation after the commit (plan 0006
T7; AC29, AC37). The real-engine half of both is re-checked in plan T17."""

import time
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from pathlib import Path

from helpers.engine_standin import SHA, approval_request, until, wired

from eng_harness.journal import JournalReader
from eng_harness.journal import _events as ev


def _resolved(run_dir: Path) -> list[ev.ApprovalResolved]:
    return [e.payload for e in JournalReader(run_dir).events() if isinstance(e.payload, ev.ApprovalResolved)]


def test_answer_bound_to_hash(tmp_path: Path) -> None:
    request = approval_request()
    with wired(tmp_path) as w:
        future = w.open(request)
        assert w.answer(request, shown_sha256="b" * 64, decision="approve") == HTTPStatus.CONFLICT
        assert not future.done()
        assert request.request_id in w.client.get("/").body  # still open, shown again
        assert w.client.get(f"/request/{request.request_id}").status == HTTPStatus.OK
        assert w.answer(request, decision="approve", by="Ada") == HTTPStatus.OK
        answer = future.result(timeout=5)
    assert answer is not None
    assert (answer.request_id, answer.shown_sha256, answer.decision) == (request.request_id, SHA, "approve")
    assert [(r.request_id, r.shown_sha256, r.by, r.decision) for r in _resolved(w.engine.run_dir)] == [
        (request.request_id, SHA, "engineer:Ada", "approve")
    ]


def test_page_confirms_after_commit(tmp_path: Path) -> None:
    request = approval_request()
    with wired(tmp_path, ack_timeout_s=10) as w:
        w.engine.release.clear()  # the journal commits the answer, the sink is not told yet
        future = w.open(request)
        with ThreadPoolExecutor(max_workers=1) as pool:
            posted = pool.submit(w.client.post, f"/answer/{request.request_id}", w.form(request))
            until(lambda: len(_resolved(w.engine.run_dir)) == 1)
            time.sleep(0.2)
            assert not posted.done()  # committed, but the page has not seen it: the browser still waits
            w.engine.release.set()
            result = posted.result(timeout=5)
        assert future.result(timeout=5) is not None
    assert result.status == HTTPStatus.OK
    assert "Answer recorded." in result.body
    assert "not yet recorded" not in result.body

    with wired(tmp_path / "late", ack_timeout_s=0.3) as w:  # the sink never reports the commit
        w.engine.sink = None
        w.open(request)
        began = time.monotonic()
        late = w.client.post(f"/answer/{request.request_id}", w.form(request))
        waited = time.monotonic() - began
    assert late.status == HTTPStatus.OK
    assert "Answer received, not yet recorded." in late.body
    assert 'href="/"' in late.body
    assert 0.25 <= waited < 5


def test_per_item_reject_end_to_end(tmp_path: Path) -> None:
    raise AssertionError("T17: per-item reject end-to-end re-check not yet written")


def test_void_after_model_change(tmp_path: Path) -> None:
    raise AssertionError("T17: void-after-model-change re-check not yet written")


def test_answer_bound_to_hash_real_engine(tmp_path: Path) -> None:
    raise AssertionError("T17: answer-bound-to-hash real-engine re-check not yet written")


def test_page_confirms_after_commit_real_engine(tmp_path: Path) -> None:
    raise AssertionError("T17: page-confirms-after-commit real-engine re-check not yet written")

