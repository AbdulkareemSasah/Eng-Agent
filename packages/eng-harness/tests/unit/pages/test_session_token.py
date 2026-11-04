"""Launch code, session cookie and CSRF token (plan 0006 T6; AC23, AC25 token inputs; spec 0006 section 4.4.1)."""

import base64
import hmac
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from helpers.page_client import RUN_DATA, serving

from eng_harness.pages._security import PageSecurity, RefusalError, Subject

_COOKIE = re.compile(r"eh_(\d+)_session=([A-Za-z0-9_-]+); HttpOnly; SameSite=Strict; Path=/")


def _code(address: str) -> str:
    return parse_qs(urlsplit(address).query)["code"][0]


def _bits(value: str) -> int:
    return 8 * len(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))


def test_launch_code_once() -> None:
    with serving(session=False) as page:
        client = page.client
        assert client.get("/").status == 403  # no cookie yet
        opened = client.open()
        assert 300 <= opened.status < 400
        assert opened.header("Location") == "/"
        cookie = _COOKIE.fullmatch(opened.header("Set-Cookie") or "")
        assert cookie is not None, "name carries the port; HttpOnly; SameSite=Strict; no Secure"
        assert cookie.group(1) == str(page.server.port)
        assert client.get("/").status == 200  # the cookie opens the session
        again = client.get(urlsplit(page.server.launch_address).path + "?code=" + _code(page.server.launch_address))
        assert again.status == 403  # a second use of the code
        assert RUN_DATA not in again.body
        assert client.get("/launch?code=wrong").status == 403
        assert client.get("/launch").status == 403


def test_wrong_code_does_not_use_up_the_launch_code() -> None:
    with serving(session=False) as page:
        assert page.client.get("/launch?code=" + "x" * 43).status == 403
        assert page.client.get("/launch?code=").status == 403
        page.client.open()
        assert page.client.get("/").status == 200


def test_requests_without_the_servers_own_cookie_get_403_with_no_run_data() -> None:
    with serving() as page, serving() as other:
        assert page.client.cookie is not None
        assert other.client.cookie is not None
        name, _, session = page.client.cookie.partition("=")
        refused = [None, "", f"{name}=", f"{name}={session}x", f"{name}=x{session}", f"eh_1_session={session}"]
        refused += [other.client.cookie, f"x{name}={session}"]  # another server's cookie; a name that only ends alike
        for cookie in refused:
            result = page.client.get("/", headers={"Cookie": cookie})
            assert result.status == 403, cookie
            assert RUN_DATA not in result.body
        assert page.client.get("/", headers={"Cookie": f"other=1; {page.client.cookie}"}).status == 200


def test_launch_code_and_session_have_at_least_256_bits_and_differ_between_servers() -> None:
    with serving(session=False) as first, serving(session=False) as second:
        codes = [_code(first.server.launch_address), _code(second.server.launch_address)]
        first.client.open()
        second.client.open()
        sessions = [first.client.cookie, second.client.cookie]
        assert None not in sessions
        values = [*codes, *(s.partition("=")[2] for s in sessions if s)]
        assert all(_bits(v) >= 256 for v in values)
        assert len(set(values)) == 4


def test_secrets_are_compared_with_compare_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    real = hmac.compare_digest
    seen: set[bytes] = set()

    def spy(left: bytes, right: bytes) -> bool:
        seen.update((left, right))
        return real(left, right)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    with serving(session=False) as page:
        code = _code(page.server.launch_address)
        page.client.open()
        session = (page.client.cookie or "").partition("=")[2]
        token = page.client.token("/request/req-1")
        assert page.client.post("/answer/req-1", {"csrf": token, "reason": "x"}).status == 200
    assert {code.encode(), session.encode(), token.encode()} <= seen


def test_token_depends_on_route_subject_hash_and_session() -> None:
    security = PageSecurity(port=50000, max_failed=100)
    base = Subject("approval", "req-1", "a" * 64)
    token = security.csrf_token(base, "session-1")
    assert token == security.csrf_token(base, "session-1")
    variants = [
        (Subject("choice", "req-1", "a" * 64), "session-1"),
        (Subject("approval", "req-2", "a" * 64), "session-1"),
        (Subject("approval", "req-1", "b" * 64), "session-1"),
        (base, "session-2"),
    ]
    assert len({security.csrf_token(s, session) for s, session in variants} | {token}) == 5
    security.verify_csrf(base, "session-1", token)  # does not raise
    for subject, session in variants:
        with pytest.raises(RefusalError) as refused:
            security.verify_csrf(subject, session, token)
        assert refused.value.status == 403
    for bad in (None, "", token[:-1], token + "0", token.upper()):
        with pytest.raises(RefusalError):
            security.verify_csrf(base, "session-1", bad)
    other = PageSecurity(port=50000, max_failed=100)  # another server (another key) issues other tokens
    assert other.csrf_token(base, "session-1") != token
