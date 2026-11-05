"""The page server: a loopback `ThreadingHTTPServer` around the route table (spec 0006 4.4.1; AC22, AC28).

Raises:
    PageBindError: the server was asked to bind an address other than the loopback address.
"""

import logging
import socketserver
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Annotated, Self

from eng_contract.errors import ContractError, ErrorCode
from pydantic import BaseModel, ConfigDict, Field

from eng_harness.pages._css import STYLESHEET
from eng_harness.pages._routes import PageApp, Response, Router, error_page
from eng_harness.pages._security import LOOPBACK, PageSecurity, RefusalError

_LOG = logging.getLogger(__name__)
_HEADERS = (  # of every response, errors included (spec 4.4.2)
    (
        "Content-Security-Policy",
        f"default-src 'none'; style-src {STYLESHEET.csp_source}; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'",
    ),
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("X-Frame-Options", "DENY"),
    ("Content-Type", "text/html; charset=utf-8"),
)
Count = Annotated[int, Field(strict=True, ge=1)]


class PageSettings(BaseModel):
    """Software limits of the page server (the `[page]` section of spec 0006 4.2.4); none is an engineering value."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    max_body_bytes: Count = 32768  # POST body limit, bytes
    max_failed_requests: Count = 20  # refused requests before lockdown


class PageBindError(ContractError):
    """The page server was asked to bind an address other than the loopback address (`INVALID_ARGUMENT`)."""

    def __init__(self, address: str) -> None:
        super().__init__(ErrorCode.INVALID_ARGUMENT, f"the page server binds {LOOPBACK} only", received=address[:64])


class _HttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # on Windows a reusable port could be shared with another process

    def __init__(self, app: PageApp, settings: PageSettings) -> None:
        super().__init__((LOOPBACK, 0), _Handler)
        self.security = PageSecurity(self.server_port, settings.max_failed_requests)
        self.router = Router(self.security, app, settings.max_body_bytes)

    def server_bind(self) -> None:
        """Bind to an operating-system port, then check the address really is the loopback one (no name lookup)."""
        socketserver.TCPServer.server_bind(self)
        host, self.server_port = self.socket.getsockname()[:2]
        self.server_name = host
        if host != LOOPBACK:
            raise PageBindError(host)

    def handle_error(self, request: object, client_address: object) -> None:
        """Log a failed connection (a browser that went away, for example) instead of printing it."""
        _LOG.exception("page connection failed")


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # one request per connection
    timeout = 10  # socket timeout of one request, s
    server: _HttpServer

    def _serve(self) -> None:
        try:
            response = self.server.router.handle(self.command, self.path, self.headers, self.rfile.read)
        except RefusalError as refusal:
            response = error_page(refusal.status)
        except Exception:
            _LOG.exception("page request failed")  # the response says nothing about why
            response = error_page(HTTPStatus.INTERNAL_SERVER_ERROR)
        self._send(response)

    def __getattr__(self, name: str) -> Callable[[], None]:
        if name.startswith("do_"):  # every method is routed; those the table does not list get 405
            return self._serve
        raise AttributeError(name)

    def _send(self, response: Response) -> None:
        body = response.body.encode("utf-8")
        self.send_response(response.status)
        for name, value in (*_HEADERS, *response.headers):
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        """Answer a request the parser refused with the same headers and a page that holds no run data."""
        self._send(error_page(HTTPStatus(code)))

    def log_message(self, format: str, *args: object) -> None:
        """Silent: the access log of the base class quotes the request line, query string and launch code included."""


class PageServer:
    """A loopback page server for one run: binds on creation, serves from `start`, frees the port on `close`.

    Attributes:
        address: The address the listening socket is bound to (always `127.0.0.1`).
        port: The port the operating system chose.
        launch_address: The address that opens the session once; hand it to the opener only (spec 4.4.4), never to
            a stream, a log or the journal.

    Raises:
        PageBindError: `address` is not `127.0.0.1` (checked before any socket exists, so a name is never resolved).
        OSError: the operating system could not bind a port.
    """

    address: str
    port: int

    def __init__(self, app: PageApp, settings: PageSettings | None = None, *, address: str = LOOPBACK) -> None:
        if address != LOOPBACK:
            raise PageBindError(address)
        self._http = _HttpServer(app, settings or PageSettings())
        self.address, self.port = self._http.socket.getsockname()[:2]
        self.launch_address = self._http.security.launch_address
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        """True while the serving thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Serve in a daemon thread; a second call does nothing."""
        if self._thread is None:
            serve = self._http.serve_forever  # polls for a shutdown request every 0.05 s
            self._thread = threading.Thread(target=serve, args=(0.05,), name="eng-harness-page", daemon=True)
            self._thread.start()

    def close(self) -> None:
        """Stop serving, join the thread and close the socket so the port is free; safe to call twice."""
        if self._thread is not None:
            self._http.shutdown()
            self._thread.join()
            self._thread = None
        self._http.server_close()

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
