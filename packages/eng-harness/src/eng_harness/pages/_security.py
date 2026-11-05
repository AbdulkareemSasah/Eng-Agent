"""Page server security: launch code, session, request checks, CSRF tokens and lockdown (spec 0006 4.4.1, 4.4.2)."""

import hashlib
import hmac
import logging
import secrets
import threading
from dataclasses import dataclass
from email.message import Message
from http import HTTPStatus
from typing import Literal, NoReturn

LOOPBACK = "127.0.0.1"
CSRF_FIELD = "csrf"
type Route = Literal["approval", "choice", "setup"]
_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Subject:
    """What a CSRF token binds: the kind of POST, its request or setup id and the SHA-256 of the content shown."""

    route: Route
    subject_id: str
    bound_sha256: str


class RefusalError(Exception):
    """A refused request: `status` is the HTTP status to answer with; the body never holds run data."""

    def __init__(self, status: HTTPStatus) -> None:
        super().__init__(status.phrase)
        self.status = status


def _same(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def _cookie(headers: Message, name: str) -> str | None:
    pairs = (p.strip().partition("=") for line in headers.get_all("Cookie", []) for p in line.split(";"))
    return next((value for key, _, value in pairs if key == name), None)


class PageSecurity:
    """The secrets and checks of one page server; thread-safe."""

    def __init__(self, port: int, max_failed: int) -> None:
        self._host = f"{LOOPBACK}:{port}"
        self._origin = f"http://{self._host}"
        self.cookie_name = f"eh_{port}_session"
        self._code, self._session, self._key = (secrets.token_urlsafe(32) for _ in range(3))
        self.launch_address = f"http://{self._host}/launch?code={self._code}"  # a secret: never log or print it
        self._max_failed = max_failed
        self._failed = 0
        self._used = False
        self._lock = threading.Lock()

    def fail(self, status: HTTPStatus) -> NoReturn:
        """Count one refused request toward lockdown and refuse it. Raises: RefusalError."""
        with self._lock:
            self._failed += 1
            locking = self._failed == self._max_failed
        if locking:
            _LOG.warning("page server locked after %d refused requests", self._max_failed)
        raise RefusalError(status)

    def check(self, method: str, path: str, headers: Message) -> str:
        """Run the checks in order, return the session value (empty for `/launch`). Raises: RefusalError (503 locked,
        421 Host, 403 Origin, Sec-Fetch-Site or cookie)."""
        with self._lock:
            if self._failed >= self._max_failed:
                raise RefusalError(HTTPStatus.SERVICE_UNAVAILABLE)
        if headers.get_all("Host", []) != [self._host]:
            self.fail(HTTPStatus.MISDIRECTED_REQUEST)
        site = headers.get_all("Sec-Fetch-Site", [])
        if method == "POST" and (headers.get_all("Origin", []) != [self._origin] or site not in ([], ["same-origin"])):
            self.fail(HTTPStatus.FORBIDDEN)
        if path == "/launch":
            return ""
        session = _cookie(headers, self.cookie_name)
        if session is None or not _same(session, self._session):
            self.fail(HTTPStatus.FORBIDDEN)
        return session

    def open_session(self, code: str | None) -> str:
        """Spend the launch code and return the `Set-Cookie` value. Raises: RefusalError (403) if wrong or used."""
        with self._lock:
            valid = not self._used and code is not None and _same(code, self._code)
            self._used = self._used or valid
        if not valid:
            self.fail(HTTPStatus.FORBIDDEN)
        return f"{self.cookie_name}={self._session}; HttpOnly; SameSite=Strict; Path=/"

    def csrf_token(self, subject: Subject, session: str) -> str:
        """HMAC-SHA256 over route, id, bound hash and session, as 64 hex characters (spec 4.4.2)."""
        text = "\n".join((subject.route, subject.subject_id, subject.bound_sha256, session))
        return hmac.new(self._key.encode(), text.encode(), hashlib.sha256).hexdigest()

    def verify_csrf(self, subject: Subject, session: str, token: str | None) -> None:
        """Raises: RefusalError (403, counted) when `token` is missing or not the token of `subject` for `session`."""
        if token is None or not _same(token, self.csrf_token(subject, session)):
            self.fail(HTTPStatus.FORBIDDEN)
