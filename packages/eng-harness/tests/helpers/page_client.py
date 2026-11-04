"""Loopback client and stub application for the page tests (plan 0006 T6; spec 0006 section 9).

`serving()` starts a real `PageServer` on the loopback interface around a `StubApp` and hands back a `PageClient`
that speaks plain `http.client`. The stub renders approval, choice and setup screens with a form each, so the
security tests need neither the engine nor the real screens (plan tasks T7, T9 and T10 add those).
"""

import http.client
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit

from eng_harness.pages._security import Route

from eng_harness._html import Node, SafeToken, Tag, Text, document, el, href, trusted
from eng_harness.pages import CSRF_FIELD, Kind, PageServer, PageSettings, Reply, Screen, Subject
from eng_harness.pages._css import STYLESHEET

RUN_DATA = "RUN-DATA-MARKER"  # on every page of the stub; a refusal must never show it
FIELDS = frozenset({"decision", "reason"})
# (kind, id) -> (CSRF route kind, hash bound to the screen); two ids per route kind so tokens can be swapped
SPECS: dict[tuple[Kind, str], tuple[Route, str]] = {
    (Kind.REQUEST, "req-1"): ("approval", "a" * 64),
    (Kind.REQUEST, "req-3"): ("approval", "e" * 64),
    (Kind.REQUEST, "req-2"): ("choice", "b" * 64),
    (Kind.REQUEST, "req-4"): ("choice", "f" * 64),
    (Kind.SETUP, "setup-1"): ("setup", "c" * 64),
    (Kind.SETUP, "setup-2"): ("setup", "d" * 64),
}
_TOKEN = re.compile(r'<input type="hidden" name="csrf" value="([A-Za-z0-9_-]+)">')
Headers = Mapping[str, str | None]


class StubApp:
    """A `PageApp` that records what reaches it: `calls` lists the methods called, `submitted` the forms handed on."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.submitted: list[tuple[Kind, str, dict[str, str]]] = []
        self.rebound: dict[tuple[Kind, str], str] = {}  # a screen whose content (hash) changed after it was rendered
        self.failure: Exception | None = None

    def _enter(self, name: str) -> None:
        self.calls.append(name)
        if self.failure is not None:
            raise self.failure

    def index(self) -> Reply:
        self._enter("index")
        return Reply(trusted("Run"), [el(Tag.P, Text(RUN_DATA))])

    def screen(self, kind: Kind, subject_id: str) -> Screen | None:
        self._enter("screen")
        spec = SPECS.get((kind, subject_id))
        if spec is None:
            return None
        route, bound = spec
        subject = Subject(route, subject_id, self.rebound.get((kind, subject_id), bound))
        action = href(SafeToken("setup" if kind is Kind.SETUP else "answer"), SafeToken(subject_id))

        def render(token: str) -> Sequence[Node]:
            form = el(
                Tag.FORM,
                el(Tag.INPUT, type=SafeToken("hidden"), name=SafeToken(CSRF_FIELD), value=SafeToken(token)),
                el(Tag.INPUT, type=SafeToken("text"), name=SafeToken("reason")),
                el(Tag.BUTTON, Text("Send"), type=SafeToken("submit")),
                method=SafeToken("post"),
                action=action,
            )
            return [el(Tag.H1, Text(RUN_DATA)), form, el(Tag.A, Text("Back"), href=href())]

        return Screen(trusted("Screen"), subject, FIELDS, render)

    def report(self) -> str:
        self._enter("report")
        return document(trusted("Report"), [el(Tag.P, Text(RUN_DATA))], STYLESHEET)

    def submit(self, kind: Kind, subject_id: str, form: Mapping[str, str]) -> Reply:
        self._enter("submit")
        self.submitted.append((kind, subject_id, dict(form)))
        return Reply(trusted("Recorded"), [el(Tag.P, Text("answer recorded"))])


@dataclass(frozen=True)
class Result:
    """One response: status, headers in order, and the decoded body."""

    status: int
    headers: list[tuple[str, str]]
    body: str

    def header(self, name: str) -> str | None:
        """The first value of a header, looked up without regard to case."""
        return next((v for k, v in self.headers if k.lower() == name.lower()), None)


class PageClient:
    """Speaks to one server over loopback; keeps the session cookie after `open`."""

    def __init__(self, server: PageServer) -> None:
        self.server = server
        self.port = server.port
        self.cookie: str | None = None

    def request(self, method: str, path: str, *, body: bytes | None = None, headers: Headers | None = None) -> Result:
        """Send one request; a header given as `None` is left out, one given with a value replaces the default."""
        sent: dict[str, str | None] = {"Host": f"127.0.0.1:{self.port}", "Cookie": self.cookie}
        if method == "POST":
            sent["Origin"] = f"http://127.0.0.1:{self.port}"
            sent["Content-Type"] = "application/x-www-form-urlencoded"
        sent.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers={k: v for k, v in sent.items() if v is not None})
            response = connection.getresponse()
            return Result(response.status, response.getheaders(), response.read().decode("utf-8"))
        finally:
            connection.close()

    def get(self, path: str, headers: Headers | None = None) -> Result:
        """GET `path`."""
        return self.request("GET", path, headers=headers)

    def post(
        self, path: str, fields: Mapping[str, str] | Sequence[tuple[str, str]], headers: Headers | None = None
    ) -> Result:
        """POST `fields` as a urlencoded form to `path`."""
        pairs = list(fields.items()) if isinstance(fields, Mapping) else list(fields)
        return self.request("POST", path, body=urlencode(pairs).encode(), headers=headers)

    def open(self) -> Result:
        """Use the launch address once and keep the cookie it sets."""
        parts = urlsplit(self.server.launch_address)
        result = self.get(f"{parts.path}?{parts.query}")
        cookie = result.header("Set-Cookie")
        assert cookie is not None, "the launch address did not open a session"
        self.cookie = cookie.partition(";")[0]
        return result

    def token(self, path: str) -> str:
        """The CSRF token of the form on the screen at `path`."""
        found = _TOKEN.search(self.get(path).body)
        assert found is not None, f"no CSRF token on {path}"
        return found.group(1)


@dataclass(frozen=True)
class Running:
    """A started server, its client (session opened unless asked otherwise) and its stub application."""

    server: PageServer
    client: PageClient
    app: StubApp


@contextmanager
def serving(*, session: bool = True, settings: PageSettings | None = None) -> Iterator[Running]:
    """Run a `PageServer` around a `StubApp` for the length of the block."""
    app = StubApp()
    with PageServer(app, settings) as server:
        client = PageClient(server)
        if session:
            client.open()
        yield Running(server, client, app)
