"""Host, Origin, Fetch Metadata and CSRF checks run before any handler (plan 0006 T6; AC24, AC25)."""

import pytest
from tests.helpers.page_client import PageClient, serving

from eng_harness.pages import CSRF_FIELD, Kind, PageSettings

MANY = PageSettings(max_failed_requests=1000)  # these tests refuse many requests on purpose
FORM = {"decision": "approve", "reason": "ok"}
REFUSED = {403, 421}


def test_host_origin_fetch_metadata() -> None:
    with serving(settings=MANY) as page:
        client, app, port = page.client, page.app, page.server.port
        token = client.token("/request/req-1")
        app.calls.clear()
        form = {**FORM, CSRF_FIELD: token}
        hosts = [f"localhost:{port}", f"127.0.0.1:{port + 1}", "127.0.0.1", f"127.0.0.1:{port}.evil.example", ""]
        hosts += [f"evil.example:{port}", f"127.0.0.1:{port}, evil.example", f"127.0.0.1:{port} "]
        for host in hosts:
            assert client.get("/", headers={"Host": host}).status in REFUSED, host
            assert client.post("/answer/req-1", form, headers={"Host": host}).status in REFUSED, host
        origins = [None, "", "null", f"http://localhost:{port}", f"http://127.0.0.1:{port + 1}", "http://127.0.0.1"]
        origins += [f"https://127.0.0.1:{port}", f"http://127.0.0.1:{port}/", f"http://127.0.0.1:{port}.evil.example"]
        for origin in origins:
            assert client.post("/answer/req-1", form, headers={"Origin": origin}).status in REFUSED, origin
        for site in ("cross-site", "same-site", "none", "", "same-origin, cross-site", "Same-Origin"):
            assert client.post("/answer/req-1", form, headers={"Sec-Fetch-Site": site}).status in REFUSED, site
        assert app.calls == []  # no handler ran for any of them
        assert app.submitted == []
        # an older browser sends the right Origin and no Fetch Metadata; a current one says same-origin
        assert client.post("/answer/req-1", form).status == 200
        assert client.post("/answer/req-1", form, headers={"Sec-Fetch-Site": "same-origin"}).status == 200
        assert len(app.submitted) == 2
        # a navigation (the launch address, a typed address) says `none`; the Fetch Metadata check is for POST
        assert client.get("/", headers={"Sec-Fetch-Site": "none"}).status == 200


# (route kind, page, post path, kind and id the app knows it by, page of a sibling of the same kind)
KINDS = [
    pytest.param("approval", "/request/req-1", "/answer/req-1", Kind.REQUEST, "req-1", "/request/req-3", id="approval"),
    pytest.param("choice", "/request/req-2", "/answer/req-2", Kind.REQUEST, "req-2", "/request/req-4", id="choice"),
    pytest.param("setup", "/setup/setup-1", "/setup/setup-1", Kind.SETUP, "setup-1", "/setup/setup-2", id="setup"),
]
PAGES = {"approval": "/request/req-1", "choice": "/request/req-2", "setup": "/setup/setup-1"}


@pytest.mark.parametrize(("route", "screen", "post", "kind", "subject_id", "sibling"), KINDS)
def test_csrf_bound_to_request_and_hash(
    route: str, screen: str, post: str, kind: Kind, subject_id: str, sibling: str
) -> None:
    with serving(settings=MANY) as page:
        client, app = page.client, page.app
        token = client.token(screen)
        other_kinds = [client.token(path) for name, path in PAGES.items() if name != route]
        flipped = token[:-1] + ("0" if token[-1] != "0" else "1")
        refused: list[str | None] = [None, "", flipped, "x" * 64, token.upper(), *other_kinds, client.token(sibling)]
        for bad in refused:  # missing, wrong, for another route kind, for another request or setup id
            fields = FORM if bad is None else {**FORM, CSRF_FIELD: bad}
            assert client.post(post, fields).status == 403, bad
        stranger = PageClient(page.server)  # another session: a valid token without the session's cookie
        assert stranger.post(post, {**FORM, CSRF_FIELD: token}).status == 403
        assert app.submitted == []  # nothing reached the application

        app.rebound[(kind, subject_id)] = "9" * 64  # the content shown changed after the form was rendered
        assert client.post(post, {**FORM, CSRF_FIELD: token}).status == 403  # the token is for the old hash
        assert app.submitted == []

        fresh = client.token(screen)  # the same screen rendered again carries a token for the new content
        assert fresh != token
        assert client.post(post, {**FORM, CSRF_FIELD: fresh}).status == 200
        assert [(k, i) for k, i, _ in app.submitted] == [(kind, subject_id)]
        assert CSRF_FIELD not in app.submitted[0][2]  # the application sees the answer fields only
