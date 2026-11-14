"""Test-local stand-in for the engine's approval and input half (plan 0006 T7; spec 0006 section 9, staged engine).

It drives a page port the way the engine does (journal the request, `present`, `answer`, journal the answer) through the
merged `JournalWriter`, and feeds each committed event to the sink it was given, as the progress fan-out does. The
`release` holds the feed of an answer to the sink while it is cleared, so a test can place the journal commit before
the sink sees it (AC37); a stand-in whose `sink` is `None` feeds nothing. The real
engine half of AC29 and AC37 is re-checked in plan T17.
"""

import asyncio
import sqlite3
import threading
import time
from collections.abc import Callable, Coroutine, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace

from eng_harness._html import SafeToken, Tag, Text, el, href, trusted
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.journal import Event, EventType, JournalReader, JournalWriter
from eng_harness.pages import PageApprovalPort, PageInputPort, PageServer, Screen
from eng_harness.pages._answers import CHOICE, REASON, REJECT, Request, bound_sha256
from eng_harness.pages._ports import PageHub
from eng_harness.pages._security import CSRF_FIELD, Route, Subject
from eng_harness.ports import (
    ApprovalAnswer,
    ApprovalPort,
    ApprovalRequest,
    InputAnswer,
    InputPort,
    InputRequest,
)
from helpers.page_client import PageClient

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
REF = "res_" + "0" * 26
SHA = "a" * 64
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="engine-standin")


def in_thread[T](coro: Coroutine[Any, Any, T]) -> Future[T]:
    """Run `coro` to its end on a thread of its own (the engine's loop), so the test thread can post to the page."""
    return _POOL.submit(asyncio.run, coro)


def until(condition: Callable[[], bool], seconds: float = 5.0) -> None:
    """Wait for `condition`; fail the test when it does not hold within `seconds`."""
    end = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < end, "the condition did not hold in time"
        time.sleep(0.01)


def approval_request(
    rid: str = "apr_one", items: Sequence[str] = ("i1", "i2"), kind: str = "CHANGE_SET", title: str = "Apply the change"
) -> ApprovalRequest:
    """A request as `Approvals` builds it: the hash is the one the answer must quote."""
    return ApprovalRequest(
        request_id=rid, run_id="run_standin", kind=kind, title=title, preview_ref=REF,
        shown_sha256=SHA, binding=(), items=tuple(items),
    )  # fmt: skip


def input_request(rid: str = "dec_one", kind: str = "engine.decision") -> InputRequest:
    """A choice request with one question."""
    schema = {"type": "object", "x-eng-input": "choice", "properties": {"q": {"type": "string", "enum": ["a", "b"]}}}
    return InputRequest.model_validate({"request_id": rid, "kind": kind, "title": "Choose", "fields_schema": schema})


class EngineStandIn:
    """Journals the requests and answers of one stand-in run under `root` and feeds `sink` after each commit."""

    def __init__(self, root: Path, sink: Callable[[Event], None] | None = None) -> None:
        clock = FixedClock(START_MS, 1)
        self.ids = SeededIdSource(b"harness", clock)
        self.clock = clock
        workspace = Workspace(root=root / "ws", classification=LocationClass.LOCAL)
        self.store = ResultStore(workspace, HARNESS_KINDS, self.ids, clock)
        self.run_dir = workspace.root / "runs" / "run_standin"
        self.run_dir.mkdir(parents=True)
        self.sink = sink
        self.release = threading.Event()
        self.release.set()
        self._lock = threading.Lock()
        self._fed = 0
        self._writer = JournalWriter(
            self.run_dir, self.store, clock, self.ids,
            connect=lambda path: sqlite3.connect(path, isolation_level=None, check_same_thread=False),
        )  # fmt: skip

    def close(self) -> None:
        """Close the journal."""
        self._writer.close()

    def journal(self, type_: EventType, body: dict[str, Any]) -> None:
        """Append one event and hand every new committed event to the sink (an answer waits for `release` first)."""
        with self._lock:
            self._writer.append(type_, body)
            reader = JournalReader(self.run_dir)
            try:
                events = reader.events(after_seq=self._fed)
            finally:
                reader.close()
            self._fed = events[-1].seq
        if type_ in (EventType.APPROVAL_RESOLVED, EventType.INPUT_PROVIDED):
            self.release.wait()
        for event in events:
            if self.sink is not None:
                self.sink(event)

    async def approve(
        self, port: ApprovalPort, request: ApprovalRequest, *, wait: bool = True
    ) -> ApprovalAnswer | None:
        """`Approvals` as the page sees it: journal, present, answer, journal `approval_resolved` for an answer."""
        self.journal(
            EventType.APPROVAL_REQUESTED,
            {
                "request_id": request.request_id, "kind": request.kind, "title": request.title,
                "preview_ref": REF, "shown_sha256": request.shown_sha256, "binding": {}, "items": list(request.items),
            },
        )  # fmt: skip
        await port.present(request)
        answer = await port.answer(request.request_id, wait=wait)
        if answer is not None:
            body = answer.model_dump(mode="json") | {"by": "engineer:" + answer.by}
            self.journal(EventType.APPROVAL_RESOLVED, body)
        return answer

    async def ask(self, port: InputPort, request: InputRequest, *, wait: bool = True) -> InputAnswer | None:
        """The same for an input request: `input_requested`, then `input_provided` for an answer."""
        asked = {"request_id": request.request_id, "kind": request.kind, "title": request.title}
        self.journal(EventType.INPUT_REQUESTED, asked | {"fields_schema_sha256": request.fields_schema_sha256})
        await port.present(request)
        answer = await port.answer(request.request_id, wait=wait)
        if answer is not None:
            self.journal(
                EventType.INPUT_PROVIDED,
                {"request_id": request.request_id, "answer_ref": REF, "by": "engineer:" + answer.by},
            )
        return answer


def form_screen(hub: PageHub, request: Request) -> Screen:
    """A test screen builder: one form with the CSRF token and every field an answer may post."""
    route: Route = "approval" if isinstance(request, ApprovalRequest) else "choice"
    items = request.items if isinstance(request, ApprovalRequest) else ()
    names = {"shown_sha256", "by", "decision", "reason", "acknowledged_unreleased", CHOICE + "q"}
    names |= {prefix + item for item in items for prefix in (REJECT, REASON)}
    action = href(SafeToken("answer"), SafeToken(request.request_id))

    def render(token: str) -> list[Any]:
        csrf = el(Tag.INPUT, type=SafeToken("hidden"), name=SafeToken(CSRF_FIELD), value=SafeToken(token))
        form = el(
            Tag.FORM,
            csrf,
            el(Tag.BUTTON, Text("Send"), type=SafeToken("submit")),
            method=SafeToken("post"),
            action=action,
        )
        return [el(Tag.H1, Text(request.title)), form]

    return Screen(
        trusted("Request"), Subject(route, request.request_id, bound_sha256(request)), frozenset(names), render
    )


@dataclass(frozen=True)
class Wired:
    """The page ports, the stand-in engine, a client with an open session and the server's port."""

    approvals: PageApprovalPort
    inputs: PageInputPort
    engine: EngineStandIn
    client: PageClient

    def open(self, request: ApprovalRequest) -> Future[ApprovalAnswer | None]:
        """Start the stand-in engine at `request` and wait until the page shows it."""
        future = in_thread(self.engine.approve(self.approvals, request))
        until(lambda: self.approvals.hub.screen("request", request.request_id) is not None)
        return future

    def form(self, request: Request, **fields: str) -> dict[str, str]:
        """A form for `request` with the right hash, a name and the CSRF token of the page now, plus `fields`."""
        token = self.client.token(f"/request/{request.request_id}")
        return {CSRF_FIELD: token, "shown_sha256": bound_sha256(request), "by": "ada", "decision": "approve"} | fields

    def answer(self, request: Request, **fields: str) -> int:
        """Post `form(request, **fields)` to the answer route; return the status."""
        return self.client.post(f"/answer/{request.request_id}", self.form(request, **fields)).status


@contextmanager
def wired(root: Path, **settings: Any) -> Iterator[Wired]:
    """A `PageServer` around the hub of new page ports, the stand-in engine feeding its sink, and a client."""
    approvals = PageApprovalPort(builders={"CHANGE_SET": form_screen, "engine.decision": form_screen}, **settings)
    engine = EngineStandIn(root, approvals.hub.emit)
    with PageServer(approvals.hub) as server:
        client = PageClient(server)
        client.open()
        try:
            yield Wired(approvals, PageInputPort(approvals), engine, client)
        finally:
            engine.close()
