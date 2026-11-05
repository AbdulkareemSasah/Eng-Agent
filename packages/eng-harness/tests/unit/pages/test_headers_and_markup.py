"""Every response carries the security headers; the markup holds no active content (plan 0006 T6; AC26)."""

import base64
import hashlib
from html.parser import HTMLParser

from helpers.page_client import RUN_DATA, Result, serving

from eng_harness.pages import PageSettings
from eng_harness.pages._css import STYLESHEET
from eng_harness.pages._security import CSRF_FIELD

FORBIDDEN_TAGS = {"script", "iframe", "object", "embed", "link", "img"}
URL_ATTRIBUTES = {"href", "action", "src", "data", "formaction", "poster", "srcset", "cite", "ping", "background"}


class _Scan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []
        self.styles: list[str] = []
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._in_style = tag == "style"
        if tag in FORBIDDEN_TAGS:
            self.problems.append(f"<{tag}>")
        for name, value in attrs:
            if name == "style" or name.startswith("on"):
                self.problems.append(f"attribute {name}")
            target = value or ""
            if name in URL_ATTRIBUTES and (not target.startswith("/") or target.startswith("//")):
                self.problems.append(f"url {name}={value}")

    def handle_endtag(self, tag: str) -> None:
        self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.styles.append(data)


def _style_source() -> str:
    css = STYLESHEET.render().removeprefix("<style>").removesuffix("</style>")  # independent of csp_source
    return "'sha256-" + base64.b64encode(hashlib.sha256(css.encode("utf-8")).digest()).decode("ascii") + "'"


def _expected(style: str) -> dict[str, str]:
    policy = f"default-src 'none'; style-src {style}; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    return {
        "Content-Security-Policy": policy,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "X-Frame-Options": "DENY",
        "Content-Type": "text/html; charset=utf-8",
    }


def _check(label: str, result: Result) -> None:
    expected = _expected(_style_source())
    for name, value in expected.items():
        assert result.header(name) == value, (label, name)
    scan = _Scan()
    scan.feed(result.body)
    scan.close()
    assert scan.problems == [], (label, scan.problems)
    for css in scan.styles:  # the one inline style element is the one the policy names
        digest = base64.b64encode(hashlib.sha256(css.encode("utf-8")).digest()).decode("ascii")
        assert f"'sha256-{digest}'" in expected["Content-Security-Policy"], label


def test_csp_and_no_active_content() -> None:
    with serving(settings=PageSettings(max_failed_requests=1000)) as page:
        client = page.client
        token = client.token("/request/req-1")
        form = {"decision": "approve", "reason": "ok", CSRF_FIELD: token}
        shown = {
            "index": client.get("/"),
            "approval screen": client.get("/request/req-1"),
            "choice screen": client.get("/request/req-2"),
            "setup screen": client.get("/setup/setup-1"),
            "report": client.get("/report"),
            "answer reply": client.post("/answer/req-1", form),
        }
        for label, result in shown.items():
            assert result.status == 200, label
            _check(label, result)
        assert "<form" in shown["approval screen"].body  # the scan looked at a page with a form
        errors = {
            "404": client.get("/nowhere"),
            "404 id": client.get("/request/missing"),
            "405": client.request("PUT", "/"),
            "403 token": client.post("/answer/req-1", {"decision": "approve", "reason": "ok"}),
            "403 session": client.get("/", headers={"Cookie": None}),
            "403 origin": client.post("/answer/req-1", form, headers={"Origin": None}),
            "421 host": client.get("/", headers={"Host": "evil.example"}),
            "415": client.post("/answer/req-1", form, headers={"Content-Type": "text/plain"}),
            "400": client.post("/answer/req-1", {**form, "extra": "1"}),
            "413": client.request("POST", "/answer/req-1", headers={"Content-Length": "999999"}),
            "403 launch": client.get("/launch?code=wrong"),
        }
        assert {label: r.status for label, r in errors.items()} == {
            "404": 404, "404 id": 404, "405": 405, "403 token": 403, "403 session": 403, "403 origin": 403,
            "421 host": 421, "415": 415, "400": 400, "413": 413, "403 launch": 403,
        }  # fmt: skip
        for label, result in errors.items():
            _check(label, result)
            assert RUN_DATA not in result.body, label


def test_locked_server_answers_with_the_same_headers() -> None:
    with serving(settings=PageSettings(max_failed_requests=1)) as page:
        assert page.client.get("/", headers={"Host": "evil.example"}).status == 421
        locked = page.client.get("/")
        assert locked.status == 503
        _check("503", locked)
        assert RUN_DATA not in locked.body
