"""Route table of the page server and the app it serves (spec 0006 4.4.3; AC26, AC27). The app decides every answer.

Raises: RefusalError for 404, 405, 400 (form), 413 (size) and 415 (content type), besides the security checks' own.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from email.message import Message
from http import HTTPStatus
from typing import Literal, Protocol
from urllib.parse import parse_qs, parse_qsl, urlsplit

from eng_harness._html import Node, Tag, Text, document, el, trusted
from eng_harness.pages._css import STYLESHEET
from eng_harness.pages._security import CSRF_FIELD, PageSecurity, RefusalError, Subject

type Kind = Literal["request", "setup"]  # what the id of a route names: an open request or a basis setup
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}", re.ASCII)
_GET, _POST = frozenset({"GET"}), frozenset({"POST"})
_FIXED = {"/launch": _GET, "/": _GET, "/report": _GET}
_BY_ID: dict[str, tuple[Kind, frozenset[str]]] = {
    "request": ("request", _GET),
    "answer": ("request", _POST),
    "setup": ("setup", _GET | _POST),
}


@dataclass(frozen=True)
class Response:
    """One response: status, body markup and the headers beyond the security headers."""

    status: HTTPStatus
    body: str
    headers: tuple[tuple[str, str], ...] = ()


def page(status: HTTPStatus, title: Node, body: Sequence[Node]) -> Response:
    """A complete page (one style element, no script) with `status`; the only way an app answers with markup."""
    return Response(status, document(title, body, STYLESHEET))


def error_page(status: HTTPStatus) -> Response:
    """The page of a refusal: the status and its standard phrase, never run data."""
    return page(status, trusted("Request refused"), [el(Tag.MAIN, el(Tag.H1, Text(f"{status.value} {status.phrase}")))])


@dataclass(frozen=True)
class Screen:
    """A request or setup screen: `subject` is what its form token binds, `fields` the form fields it accepts."""

    title: Node
    subject: Subject
    fields: frozenset[str]
    render: Callable[[str], Sequence[Node]]  # takes the CSRF token of the viewing session


class PageApp(Protocol):
    """What the server asks of the app, from handler threads: the `index`, the `screen` of an existing request or setup
    (else None), the `report` document, and `submit` with an answer's form fields (CSRF field removed)."""

    def index(self) -> Response: ...
    def screen(self, kind: Kind, subject_id: str, *, answering: bool = False) -> Screen | None: ...
    def report(self) -> str: ...
    def submit(self, kind: Kind, subject_id: str, form: Mapping[str, str]) -> Response: ...


def _form(headers: Message, read_body: Callable[[int], bytes], names: frozenset[str], limit: int) -> dict[str, str]:
    length = headers.get("Content-Length", "")
    if not (length.isascii() and length.isdigit()):
        raise RefusalError(HTTPStatus.BAD_REQUEST)
    if int(length) > limit:
        raise RefusalError(HTTPStatus.CONTENT_TOO_LARGE)
    raw = read_body(int(length))
    if headers.get("Content-Type", "").partition(";")[0].strip().lower() != "application/x-www-form-urlencoded":
        raise RefusalError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
    try:
        pairs = parse_qsl(raw.decode("utf-8"), keep_blank_values=True, strict_parsing=True)
    except ValueError as error:  # includes UnicodeDecodeError
        raise RefusalError(HTTPStatus.BAD_REQUEST) from error
    form = dict(pairs)
    if len(form) != len(pairs) or not form.keys() <= names:  # a repeated or an unknown field
        raise RefusalError(HTTPStatus.BAD_REQUEST)
    return form


class Router:
    """Checks, routes and answers requests for one `PageApp`; `max_body_bytes` limits a POST body."""

    def __init__(self, security: PageSecurity, app: PageApp, max_body_bytes: int) -> None:
        self._security, self._app, self._limit = security, app, max_body_bytes

    def handle(self, method: str, target: str, headers: Message, read_body: Callable[[int], bytes]) -> Response:
        """Check, route and answer one request; `read_body(n)` reads at most n body bytes. Raises: RefusalError."""
        url = urlsplit(target)
        session = self._security.check(method, url.path, headers)
        allowed = _FIXED.get(url.path)
        kind: Kind | None = None
        subject_id = ""
        if allowed is None:
            match url.path.split("/"):
                case ["", name, subject_id] if name in _BY_ID and _ID.fullmatch(subject_id):
                    kind, allowed = _BY_ID[name]
                case _:
                    raise RefusalError(HTTPStatus.NOT_FOUND)
        if method not in allowed:
            raise RefusalError(HTTPStatus.METHOD_NOT_ALLOWED)
        if kind is None:
            return self._fixed(url.path, url.query)
        screen = self._app.screen(kind, subject_id, answering=method == "POST")
        if screen is None:
            raise RefusalError(HTTPStatus.NOT_FOUND)
        if method == "GET":
            return page(HTTPStatus.OK, screen.title, screen.render(self._security.csrf_token(screen.subject, session)))
        form = _form(headers, read_body, screen.fields | {CSRF_FIELD}, self._limit)
        self._security.verify_csrf(screen.subject, session, form.pop(CSRF_FIELD, None))
        return self._app.submit(kind, subject_id, form)

    def _fixed(self, path: str, query: str) -> Response:
        if path == "/launch":
            codes = parse_qs(query).get("code", [])
            cookie = self._security.open_session(codes[0] if len(codes) == 1 else None)
            return Response(HTTPStatus.SEE_OTHER, "", (("Location", "/"), ("Set-Cookie", cookie)))
        return Response(HTTPStatus.OK, self._app.report()) if path == "/report" else self._app.index()
