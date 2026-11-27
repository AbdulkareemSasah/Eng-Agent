"""The page's state, its ports and its sink (spec 0006 4.4.5, 4.4.6; AC29, AC30, AC36 to AC38).

Purpose: the engine presents a request through a port and awaits its answer there; the page lists the open requests,
checks a posted answer, hands it to the waiting call (held in memory only) and confirms it to the browser only after the
sink has seen the matching event journaled. `PageApprovalPort` owns the `PageHub` that `PageServer` serves and that is
the sink; `PageInputPort` shares it. Units: seconds. Errors: a refused answer is a page, never an exception.
"""

import asyncio
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

from eng_contract.ids import Clock, SystemClock

from eng_harness import _html as h
from eng_harness._html import SafeToken, Tag, el, trusted
from eng_harness.basis import BasisSetupAnswer, BasisSetupView
from eng_harness.errors import HarnessCode
from eng_harness.journal import Event
from eng_harness.journal import _events as ev
from eng_harness.pages._answers import AnswerError, Request, bound_sha256, parse
from eng_harness.pages._css import STYLESHEET
from eng_harness.pages._routes import Kind, Response, Screen, page
from eng_harness.pages._security import RefusalError, Route, Subject
from eng_harness.pages._wait import POLL_S, wait_for
from eng_harness.ports import ApprovalAnswer, ApprovalRequest, InputAnswer, InputRequest
from eng_harness.report._lineage import ReleaseMarks  # not `eng_harness.report`: its document module imports pages._css

type ScreenBuilder = Callable[[PageHub, Request], Screen]  # T9, T9b and T10 register theirs by `request.kind`
type FormCheck = Callable[[PageHub, Request, Mapping[str, str]], None]  # raises `AnswerError`; by `request.kind`
_VOIDABLE = frozenset(
    {"change_set", "promotion", "CHANGE_SET", "PROMOTION"}
)  # the approvals that bind a model (spec 0006 4.4.5); the engine journals the lower-case values, B-545 accepts both
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


@dataclass
class _Setup:
    view: BasisSetupView
    setups_dir: Path | None
    clock: Clock
    answer: BasisSetupAnswer | None = None
    accepted: bool = False
    recorded: bool = False


class PageHub:
    """What the page serves (a `PageApp`) and the sink that tells it what the journal holds. Thread-safe.

    `builders` maps a request kind to its screen (none: the refusal screen), `checks` a kind to the check of a posted
    form (sign-off), `marks` are the unreleased tools. `setup` serves the basis screen. `wait_timeout_s` and
    `ack_timeout_s` are the `--wait-timeout` and `[page] ack_timeout_s` settings.
    """

    def __init__(
        self, *, engineer: str | None, stop_requested: Callable[[], bool], report: Callable[[], str],
        wait_timeout_s: float | None, ack_timeout_s: float, builders: Mapping[str, ScreenBuilder],
        setup: Callable[[str], Screen | None], marks: ReleaseMarks, checks: Mapping[str, FormCheck],
    ) -> None:  # fmt: skip
        self.engineer = engineer  # proposed on the forms; the last valid name given, for the session
        self.marks, self._checks = marks, checks
        self.stop_requested, self.wait_timeout_s = stop_requested, wait_timeout_s
        self._report, self._ack_s, self._builders, self._setup = report, ack_timeout_s, builders, setup
        self._cond = threading.Condition()
        self._open: dict[str, _Open] = {}  # in the order the engine presented them, which is the journal's `seq` order
        self._setups: dict[str, _Setup] = {}  # basis setup views presented before a run exists (spec 0006 4.4.7)
        self._approved: list[str] = []  # approved `CHANGE_SET` and `PROMOTION` requests, in the order they resolved
        self._voided: dict[str, str] = {}  # request id -> the message of the void (untrusted)
        self._run_message: str | None = None  # a void with no request in this process (spec 0006 4.4.5)

    def register(self, request: Request) -> None:
        """Open `request` (engine loop); presenting it again, as after a refused answer, opens it afresh."""
        with self._cond:
            self._open[request.request_id] = _Open(request, asyncio.Event(), asyncio.get_running_loop())

    def register_setup(self, view: BasisSetupView, *, setups_dir: Path | None, clock: Clock) -> None:
        """Open a basis confirmation `view`; presenting it again opens it afresh."""
        with self._cond:
            self._setups[view.setup_id] = _Setup(view, setups_dir, clock)

    def take_setup(self, setup_id: str, *, wait: bool) -> BasisSetupAnswer | None:
        """The accepted basis answer, or `None` for no answer, a stop, the wait timeout or `wait=False`."""
        end = None if self.wait_timeout_s is None else time.monotonic() + self.wait_timeout_s
        with self._cond:
            while True:
                entry = self._setups.get(setup_id)
                if entry is None:
                    return None
                if entry.answer is not None:
                    return entry.answer
                left = None if end is None else end - time.monotonic()
                if not wait or self.stop_requested() or (left is not None and left <= 0):
                    return None
                self._cond.wait(POLL_S if left is None else min(POLL_S, left))

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
        """The page sink: an answer the journal now holds is recorded, and its waiting handler goes on; an
        `APPROVAL_VOID` failure marks the most recent approved change set or promotion voided."""
        match event.payload:
            case ev.StepFailed(error=ev.HarnessError(harness_code=HarnessCode.APPROVAL_VOID, message=message)):
                with self._cond:
                    if self._approved:
                        self._voided[self._approved[-1]] = message
                    else:
                        self._run_message = message
            case (
                ev.ApprovalResolved(request_id=rid)
                | ev.InputProvided(request_id=rid)
                | ev.DecisionMade(request_id=str(rid))
            ):
                with self._cond:
                    if (entry := self._open.get(rid)) is not None:
                        entry.recorded = True
                        resolved = event.payload
                        if (
                            isinstance(resolved, ev.ApprovalResolved)
                            and resolved.decision == "approve"
                            and entry.request.kind in _VOIDABLE
                        ):
                            self._approved.append(rid)
                        self._cond.notify_all()

    def index(self) -> Response:
        """The open requests in `seq` order, each linked to its own page."""
        with self._cond:
            setups = [e.view for e in self._setups.values() if not e.recorded]
            shown = [e.request for e in self._open.values() if not e.recorded]
            message = self._run_message
        rows = [
            el(Tag.LI, _link(trusted("Open"), "setup", s.setup_id), h.field(trusted("Basis setup"), s.workflow))
            for s in setups
        ]
        rows.extend(
            el(Tag.LI, _link(trusted("Open"), "request", r.request_id), h.field(trusted("Request"), r.title))
            for r in shown
        )
        body = [el(Tag.H1, trusted("Run")), _link(trusted("Report"), "report")]
        if message is not None:
            body.append(el(Tag.P, h.field(trusted("Voided approval"), message)))
        body.append(el(Tag.H2, trusted("Open requests")))
        return page(HTTPStatus.OK, trusted("Run"), [*body, el(Tag.UL, *rows) if rows else el(Tag.P, trusted("None"))])

    def screen(self, kind: Kind, subject_id: str, *, answering: bool = False) -> Screen | None:
        """The screen of an open request (its kind's builder, else a refusal screen), or the basis screen. A recorded
        request has none, except for `answering`: its form token still binds, and `submit` refuses with 409 (AC30)."""
        if kind == "setup":
            with self._cond:
                setup = self._setups.get(subject_id)
            if setup is not None:
                if setup.recorded and not answering:
                    return None
                from eng_harness.pages._screens_basis import basis_screen

                return basis_screen(self, setup.view)
            return self._setup(subject_id)
        with self._cond:
            entry = self._open.get(subject_id)
            voided = self._voided.get(subject_id)
        if entry is None:
            return None
        request = entry.request
        if voided is not None:
            body = [
                el(Tag.H1, trusted("Voided")),
                el(Tag.P, h.field(trusted("Reason"), voided)),
                _link(trusted("Back")),
            ]
            return Screen(
                trusted("Voided"), Subject("approval", subject_id, bound_sha256(request)), frozenset(), lambda _: body
            )
        if entry.recorded and not answering:
            return None
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
        if kind == "setup":
            return self._submit_setup(subject_id, form)
        with self._cond:
            entry = self._open.get(subject_id)
            if entry is None:
                raise RefusalError(HTTPStatus.NOT_FOUND)
            try:
                if entry.accepted or entry.recorded:  # the lock makes the first of two simultaneous answers the one
                    raise AnswerError("this request has been answered already", HTTPStatus.CONFLICT)
                submission = parse(entry.request, form)
                if (check := self._checks.get(entry.request.kind)) is not None:
                    check(self, entry.request, form)
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

    def _submit_setup(self, subject_id: str, form: Mapping[str, str]) -> Response:
        from eng_harness.pages._screens_basis import append_setup_log, parse_setup

        with self._cond:
            setup = self._setups.get(subject_id)
            if setup is None:
                raise RefusalError(HTTPStatus.NOT_FOUND)
            try:
                if setup.accepted or setup.recorded:
                    raise AnswerError("this setup has been answered already", HTTPStatus.CONFLICT)
                answer = parse_setup(setup.view, form, setup.clock)
            except AnswerError as refused:
                again = el(Tag.P, _link(trusted("Show the setup again"), "setup", subject_id))
                text = el(Tag.P, h.Text(str(refused)))
                return page(refused.status, trusted("Not accepted"), [el(Tag.H1, trusted("Not accepted")), text, again])
            if setup.setups_dir is not None:
                append_setup_log(setup.setups_dir, answer, answer.at or setup.clock.now())
            setup.answer, setup.accepted, setup.recorded = answer, True, True
            if answer.by is not None:
                self.engineer = answer.by
            self._cond.notify_all()
        return page(
            HTTPStatus.OK,
            trusted("Basis confirmation"),
            [el(Tag.P, trusted("Basis decision recorded.")), _link(trusted("Back"))],
        )


class PageApprovalPort:
    """The `ApprovalPort` of the page; `hub` is what `PageServer` serves and what the progress fan-out feeds."""

    def __init__(
        self, *, engineer: str | None = None, stop_requested: Callable[[], bool] = lambda: False,
        report: Callable[[], str] = lambda: _NO_REPORT, wait_timeout_s: float | None = None,
        ack_timeout_s: float = 10, builders: Mapping[str, ScreenBuilder] | None = None,
        setup: Callable[[str], Screen | None] = lambda _: None, marks: ReleaseMarks | None = None,
        checks: Mapping[str, FormCheck] | None = None,
    ) -> None:  # fmt: skip
        self.hub = PageHub(
            engineer=engineer, stop_requested=stop_requested, report=report, wait_timeout_s=wait_timeout_s,
            ack_timeout_s=ack_timeout_s, builders=builders or {}, setup=setup,
            marks=marks or ReleaseMarks(records={}), checks=checks or {},
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


class PageBasisSetupPort:
    """The `BasisSetupPort` of the page, sharing the hub of `approvals` when given (spec 0006 4.4.7)."""

    def __init__(
        self,
        approvals: PageApprovalPort | None = None,
        *,
        setups_dir: Path | None = None,
        clock: Clock | None = None,
        engineer: str | None = None,
        stop_requested: Callable[[], bool] = lambda: False,
        wait_timeout_s: float | None = None,
    ) -> None:
        self.hub = (
            approvals.hub
            if approvals is not None
            else PageApprovalPort(engineer=engineer, stop_requested=stop_requested, wait_timeout_s=wait_timeout_s).hub
        )
        self._setups_dir = setups_dir
        self._clock: Clock = clock or SystemClock()

    def present(self, view: BasisSetupView) -> None:
        """Show the basis draft `view` on the page."""
        self.hub.register_setup(view, setups_dir=self._setups_dir, clock=self._clock)

    def answer(self, setup_id: str, *, wait: bool) -> BasisSetupAnswer | None:
        """The engineer's answer; `None` when there is none, on a stop or on the wait timeout."""
        return self.hub.take_setup(setup_id, wait=wait)
