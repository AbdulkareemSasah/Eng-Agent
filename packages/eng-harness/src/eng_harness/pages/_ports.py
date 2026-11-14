"""The page's state, its ports and its sink (spec 0006 4.4.5, 4.4.6; AC29, AC30, AC36 to AC38).

Purpose: the engine presents a request through a port and awaits its answer there; the page lists the open requests,
checks a posted answer, hands it to the waiting call (held in memory only) and confirms it to the browser only after the
sink has seen the matching event journaled. `PageApprovalPort` owns the `PageHub` that `PageServer` serves and that is
the sink; `PageInputPort` shares it. Units: seconds. Errors: a refused answer is a page, never an exception.
"""

import asyncio
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http import HTTPStatus

from eng_harness import _html as h
from eng_harness._html import SafeToken, Tag, el, trusted
from eng_harness.journal import Event
from eng_harness.journal import _events as ev
from eng_harness.pages._answers import AnswerError, Request, bound_sha256, parse
from eng_harness.pages._css import STYLESHEET
from eng_harness.pages._routes import Kind, Response, Screen, page
from eng_harness.pages._security import RefusalError, Route, Subject
from eng_harness.pages._wait import wait_for
from eng_harness.ports import ApprovalAnswer, ApprovalRequest, InputAnswer, InputRequest

type ScreenBuilder = Callable[[PageHub, Request], Screen]  # T9 and T10 register theirs by `request.kind`
_NO_REPORT = h.document(trusted("Report"), [el(Tag.P, trusted("The report is not available yet."))], STYLESHEET)


def _link(label: h.Trusted, *segments: str) -> h.Element:
    return el(Tag.A, label, href=h.href(*map(SafeToken, segments)))


@dataclass
class _Open:
    request: Request
    event: asyncio.Event  # set on the engine's loop when an answer is accepted
    loop: asyncio.AbstractEventLoop
    answer: ApprovalAnswer | InputAnswer | None = None
    accepted: bool = False  # an answer was taken: no other is (single use)
    recorded: bool = False  # the sink has seen it journaled


class PageHub:
    """What the page serves (a `PageApp`) and the sink that tells it what the journal holds. Thread-safe.

    `builders` maps a request kind to its screen; a kind without one gets the refusal screen. `setup` serves the basis
    screen. `wait_timeout_s` and `ack_timeout_s` are the `--wait-timeout` and `[page] ack_timeout_s` settings.
    """

    def __init__(
        self, *, engineer: str | None, stop_requested: Callable[[], bool], report: Callable[[], str],
        wait_timeout_s: float | None, ack_timeout_s: float, builders: Mapping[str, ScreenBuilder],
        setup: Callable[[str], Screen | None],
    ) -> None:  # fmt: skip
        self.engineer = engineer  # proposed on the forms; the last valid name given, for the session
        self.stop_requested, self.wait_timeout_s = stop_requested, wait_timeout_s
        self._report, self._ack_s, self._builders, self._setup = report, ack_timeout_s, builders, setup
        self._cond = threading.Condition()
        self._open: dict[str, _Open] = {}  # in the order the engine presented them, which is the journal's `seq` order

    def register(self, request: Request) -> None:
        """Open `request` (engine loop); presenting it again, as after a refused answer, opens it afresh."""
        with self._cond:
            self._open[request.request_id] = _Open(request, asyncio.Event(), asyncio.get_running_loop())

    async def take(self, request_id: str, *, wait: bool) -> ApprovalAnswer | InputAnswer | None:
        """The accepted answer, or `None` for no answer, a stop, the wait timeout or `wait=False` (engine loop)."""
        with self._cond:
            entry = self._open.get(request_id)
            if entry is not None and entry.answer is not None:
                return entry.answer  # taken before the loop saw the event
        if entry is None or not await wait_for(
            entry.event, wait=wait, stop_requested=self.stop_requested, timeout_s=self.wait_timeout_s
        ):
            return None
        return entry.answer

    def emit(self, event: Event) -> None:
        """The page sink: an answer the journal now holds is recorded, and its waiting handler goes on."""
        match event.payload:
            case (
                ev.ApprovalResolved(request_id=rid)
                | ev.InputProvided(request_id=rid)
                | ev.DecisionMade(request_id=str(rid))
            ):
                with self._cond:
                    if (entry := self._open.get(rid)) is not None:
                        entry.recorded = True
                        self._cond.notify_all()

    def index(self) -> Response:
        """The open requests in `seq` order, each linked to its own page."""
        with self._cond:
            shown = [e.request for e in self._open.values() if not e.recorded]
        rows = [
            el(Tag.LI, _link(trusted("Open"), "request", r.request_id), h.field(trusted("Request"), r.title))
            for r in shown
        ]
        body = [el(Tag.H1, trusted("Run")), _link(trusted("Report"), "report"), el(Tag.H2, trusted("Open requests"))]
        return page(HTTPStatus.OK, trusted("Run"), [*body, el(Tag.UL, *rows) if rows else el(Tag.P, trusted("None"))])

    def screen(self, kind: Kind, subject_id: str) -> Screen | None:
        """The screen of an open request (its kind's builder, else a refusal screen), or the basis screen."""
        if kind == "setup":
            return self._setup(subject_id)
        with self._cond:
            entry = self._open.get(subject_id)
        if entry is None or entry.recorded:
            return None
        request = entry.request
        if (builder := self._builders.get(request.kind)) is not None:
            return builder(self, request)
        route: Route = "approval" if isinstance(request, ApprovalRequest) else "choice"
        body = [
            el(Tag.H1, trusted("This request cannot be answered here")),
            el(Tag.P, h.field(trusted("Kind"), request.kind)), el(Tag.P, _link(trusted("Back"))),
        ]  # fmt: skip
        return Screen(
            trusted("Request"), Subject(route, subject_id, bound_sha256(request)), frozenset(), lambda _: body
        )

    def report(self) -> str:
        """The report document (`GET /report`)."""
        return self._report()

    def submit(self, kind: Kind, subject_id: str, form: Mapping[str, str]) -> Response:
        """Check a posted answer, hand it to the engine and answer the browser once the journal holds it (AC37)."""
        with self._cond:
            entry = self._open.get(subject_id) if kind == "request" else None
            if entry is None:
                raise RefusalError(HTTPStatus.NOT_FOUND)
            try:
                if entry.accepted or entry.recorded:  # the lock makes the first of two simultaneous answers the one
                    raise AnswerError("this request has been answered already", HTTPStatus.CONFLICT)
                submission = parse(entry.request, form)
            except AnswerError as refused:
                again = el(Tag.P, _link(trusted("Show the request again"), "request", subject_id))
                text = el(Tag.P, h.Text(str(refused)))
                return page(refused.status, trusted("Not accepted"), [el(Tag.H1, trusted("Not accepted")), text, again])
            entry.answer, entry.accepted, self.engineer = submission.answer(), True, submission.by
            entry.loop.call_soon_threadsafe(entry.event.set)
            self._cond.wait_for(lambda: entry.recorded, self._ack_s)  # the lock is free while it waits
            done = entry.recorded
        words = trusted("Answer recorded." if done else "Answer received, not yet recorded.")
        return page(HTTPStatus.OK, trusted("Answer"), [el(Tag.P, words), _link(trusted("Back to the open requests"))])


class PageApprovalPort:
    """The `ApprovalPort` of the page; `hub` is what `PageServer` serves and what the progress fan-out feeds."""

    def __init__(
        self, *, engineer: str | None = None, stop_requested: Callable[[], bool] = lambda: False,
        report: Callable[[], str] = lambda: _NO_REPORT, wait_timeout_s: float | None = None,
        ack_timeout_s: float = 10, builders: Mapping[str, ScreenBuilder] | None = None,
        setup: Callable[[str], Screen | None] = lambda _: None,
    ) -> None:  # fmt: skip
        self.hub = PageHub(
            engineer=engineer, stop_requested=stop_requested, report=report, wait_timeout_s=wait_timeout_s,
            ack_timeout_s=ack_timeout_s, builders=builders or {}, setup=setup,
        )  # fmt: skip

    async def present(self, request: ApprovalRequest) -> None:
        """Show the request on the page."""
        self.hub.register(request)

    async def answer(self, request_id: str, *, wait: bool) -> ApprovalAnswer | None:
        """The engineer's answer; `None` when there is none, on a stop or on the wait timeout (the engine pauses)."""
        given = await self.hub.take(request_id, wait=wait)
        return given if isinstance(given, ApprovalAnswer) else None


class PageInputPort:
    """The `InputPort` of the page, sharing the hub of `approvals`."""

    def __init__(self, approvals: PageApprovalPort) -> None:
        self._hub = approvals.hub

    async def present(self, request: InputRequest) -> None:
        """Show the request on the page."""
        self._hub.register(request)

    async def answer(self, request_id: str, *, wait: bool) -> InputAnswer | None:
        """The engineer's answer; `None` when there is none, on a stop or on the wait timeout (the engine pauses)."""
        given = await self._hub.take(request_id, wait=wait)
        return given if isinstance(given, InputAnswer) else None
