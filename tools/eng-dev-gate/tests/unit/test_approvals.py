"""Tests of the approvals port, its rules and the GitHub adapter (spec 4.1, 4.5 steps 8 to 10; AC3, AC16, AC17)."""

from __future__ import annotations

import http.client
import json
from collections.abc import Callable
from typing import Any

import pytest
from eng_dev_gate import approvals as module
from eng_dev_gate.approvals import (
    Approvals,
    ApprovalSourceError,
    GitHubApprovals,
    Review,
    Role,
    approved_logins,
    required_approvers,
    source_from_env,
)
from eng_dev_gate.config import GateConfig, load_gate_config
from eng_dev_gate.results import ExitCode, UsageError
from support.approvals import FakeApprovals
from support.pullrequest import gate_yml

HEAD = "a" * 40
Fetch = Callable[[str, str], tuple[int, bytes]]


@pytest.mark.parametrize(
    ("gate", "risk", "large", "roles"),
    [
        ("G1", ["r0"], False, {Role.REVIEWER}),
        ("G1", ["r1"], False, {Role.OWNER}),
        ("G1", ["r2"], False, {Role.OWNER}),
        ("G1", ["r3"], False, {Role.REVIEWER, Role.SECURITY}),
        ("G1", ["r3", "r1"], False, {Role.OWNER, Role.REVIEWER, Role.SECURITY}),
        ("G2", ["r1"], False, {Role.REVIEWER}),
        ("G2", ["r3"], True, {Role.OWNER}),
        ("G3", ["r0"], False, {Role.REVIEWER}),
        ("G3", ["r1"], False, {Role.REVIEWER, Role.SECOND_FAMILY}),
        ("G3", ["r2"], False, {Role.REVIEWER}),
        ("G3", ["r3"], False, {Role.REVIEWER, Role.SECURITY}),
        ("G3", ["r1", "r3"], False, {Role.REVIEWER, Role.SECOND_FAMILY, Role.SECURITY}),
    ],
)
def test_required_approvers_by_risk_set(gate: str, risk: list[str], large: bool, roles: set[Role]) -> None:
    """Process/01 section 5: the strictest row over the risk set decides who must approve."""
    assert required_approvers(gate, risk, large=large) == roles


def _reviews(*items: tuple[str, str, str]) -> list[Review]:
    return [Review(login=login, state=state, commit_sha=sha) for login, state, sha in items]


def test_approved_logins_take_the_latest_state_on_the_head_commit() -> None:
    """A later change request, a dismissal or an approval of an older commit removes an approval; comments do not."""
    reviews = _reviews(
        ("a", "APPROVED", HEAD),
        ("b", "APPROVED", HEAD),
        ("b", "CHANGES_REQUESTED", HEAD),
        ("c", "APPROVED", "b" * 40),
        ("d", "APPROVED", HEAD),
        ("d", "DISMISSED", HEAD),
        ("e", "APPROVED", HEAD),
        ("e", "COMMENTED", HEAD),
    )
    assert approved_logins(reviews, HEAD) == {"a", "e"}


@pytest.fixture
def normal(tmp_path_factory: pytest.TempPathFactory) -> GateConfig:
    """A gate configuration with bootstrap off; owner `owner`, reviewer app `reviewer`, agent `agent`."""
    root = tmp_path_factory.mktemp("cfg")
    (root / ".gate").mkdir()
    (root / ".gate" / "gate.yml").write_text(gate_yml(bootstrap=False), encoding="utf-8")
    return load_gate_config(root)


def _verifier(normal: GateConfig, fake: FakeApprovals, author: str = "agent") -> Approvals:
    return Approvals(fake, normal, number=7, author=author, head_sha=HEAD)


def test_owner_approval_satisfies_every_role(normal: GateConfig, approvals: FakeApprovals) -> None:
    """The owner's approving review on the head commit stands for any set of roles; nothing else does for OWNER."""
    everything = frozenset(Role)
    assert _verifier(normal, approvals).missing(everything) == sorted(everything)
    approvals.approve("owner", HEAD)
    assert _verifier(normal, approvals).missing(everything) == []
    assert _verifier(normal, approvals).owner_approved()


def test_reviewer_app_covers_only_the_reviewer_role(normal: GateConfig, approvals: FakeApprovals) -> None:
    """Without a way to read a model family or the security prompt, only the owner covers those roles (0.1)."""
    approvals.approve("reviewer", HEAD)
    verifier = _verifier(normal, approvals)
    assert verifier.missing(frozenset({Role.REVIEWER})) == []
    both = frozenset({Role.REVIEWER, Role.SECOND_FAMILY, Role.SECURITY})
    assert set(verifier.missing(both)) == {Role.SECOND_FAMILY, Role.SECURITY}
    assert not verifier.owner_approved()


def test_the_authors_own_approval_never_counts(normal: GateConfig, approvals: FakeApprovals) -> None:
    """AW08: approvals come from a login other than the author's; the reviews are read once per verifier."""
    approvals.approve("reviewer", HEAD)
    approvals.approve("owner", HEAD)
    verifier = _verifier(normal, approvals, author="owner")
    assert verifier.missing(frozenset({Role.OWNER})) == [Role.OWNER]
    assert not verifier.owner_approved()
    assert verifier.missing(frozenset({Role.REVIEWER})) == []
    assert approvals.asked == [7]


def _page(count: int) -> bytes:
    items = [{"user": {"login": f"u{i}"}, "state": "APPROVED", "commit_id": HEAD, "body": "x"} for i in range(count)]
    return json.dumps([*items, {"user": None, "state": "APPROVED", "commit_id": HEAD}]).encode()


def test_github_adapter_pages_and_parses_reviews() -> None:
    """The adapter asks the reviews endpoint page by page, sends the token, and skips reviews of deleted users."""
    seen: list[tuple[str, str]] = []
    pages = [_page(module.PAGE_SIZE - 1), b"[]"]  # the first page holds PAGE_SIZE entries with the deleted user

    def fetch(url: str, token: str) -> tuple[int, bytes]:
        seen.append((url, token))
        return 200, pages[len(seen) - 1]

    reviews = GitHubApprovals("o/r", "tok", "https://api.example.invalid", fetch).reviews(7)
    assert len(reviews) == module.PAGE_SIZE - 1
    assert reviews[0] == Review(login="u0", state="APPROVED", commit_sha=HEAD)
    assert seen[0] == ("https://api.example.invalid/repos/o/r/pulls/7/reviews?per_page=100&page=1", "tok")
    assert seen[1][0].endswith("page=2")


def _failing(status: int, body: bytes) -> Fetch:
    return lambda url, token: (status, body)


@pytest.mark.parametrize(
    "fetch",
    [_failing(403, b"{}"), _failing(200, b"not json"), _failing(200, b'{"a": 1}'), _failing(200, b'[{"state": 1}]')],
)
def test_github_adapter_errors_are_environment_errors_without_the_token(fetch: Fetch) -> None:
    """An error status or a malformed answer is an ApprovalSourceError (exit 3) that never prints the token."""
    with pytest.raises(ApprovalSourceError) as caught:
        GitHubApprovals("o/r", "secret-token", "https://api.example.invalid", fetch).reviews(7)
    assert caught.value.exit_code is ExitCode.ENVIRONMENT
    assert "secret-token" not in str(caught.value)


def test_github_adapter_stops_at_the_page_limit() -> None:
    """A source that never ends is an error, not an endless loop."""
    source = GitHubApprovals("o/r", "t", "https://api.example.invalid", _failing(200, _page(module.PAGE_SIZE)))
    with pytest.raises(ApprovalSourceError):
        source.reviews(7)


class _Connection:
    """Stands in for ``http.client.HTTPSConnection`` and records the request."""

    sent: list[tuple[str, str, dict[str, str]]] = []

    def __init__(self, host: str, timeout: float) -> None:
        self.host = host

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        self.sent.append((self.host + path, method, headers))

    def getresponse(self) -> Any:
        return type("Response", (), {"status": 200, "read": lambda self: b"[]"})()

    def close(self) -> None:
        return None


def test_default_fetch_uses_https_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real fetch speaks HTTPS to the configured API host with a bearer token; http:// is refused."""
    monkeypatch.setattr(http.client, "HTTPSConnection", _Connection)
    assert GitHubApprovals("o/r", "tok", "https://api.example.invalid").reviews(3) == []
    target, method, headers = _Connection.sent[0]
    assert method == "GET"
    assert target.startswith("api.example.invalid/repos/o/r/pulls/3/reviews")
    assert headers["Authorization"] == "Bearer tok"
    with pytest.raises(UsageError):
        GitHubApprovals("o/r", "tok", "http://api.example.invalid").reviews(3)


def test_source_from_env() -> None:
    """The adapter is built from GITHUB_REPOSITORY and GITHUB_TOKEN; a missing or odd value exits 2."""
    ok = {"GITHUB_REPOSITORY": "o/r", "GITHUB_TOKEN": "tok"}
    assert isinstance(source_from_env(ok), GitHubApprovals)
    for broken in ({"GITHUB_REPOSITORY": "o/r"}, {"GITHUB_TOKEN": "tok"}, {**ok, "GITHUB_REPOSITORY": "o/r/../x"}):
        with pytest.raises(UsageError):
            source_from_env(broken)
