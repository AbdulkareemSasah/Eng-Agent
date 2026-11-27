"""The approvals port (spec 4.1, 4.5 steps 8 to 10) and its GitHub REST adapter; used only with bootstrap off.

Who must approve is process/01 section 5. A review counts only when it is the login's latest approving state and was
given on the head commit; the author's own review never counts (AW08). The owner's approval stands for every role
(spec 4.4, AW03: "or by the owner"). The family of a reviewer model and the security prompt cannot be read from a
GitHub review in 0.1, so those two roles are covered by the owner only.
"""

from __future__ import annotations

import http.client
import json
import re
from collections.abc import Callable, Iterable, Mapping
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, ValidationError

from eng_dev_gate.config import GateConfig
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import GateError, UsageError

PAGE_SIZE = 100  # reviews per page: the maximum of the GitHub REST API
MAX_PAGES = 30  # a pull request with more than 3000 reviews is an error, not an endless loop
TIMEOUT_SECONDS = 30.0  # per request
DEFAULT_API_URL = "https://api.github.com"
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
Fetch = Callable[[str, str], tuple[int, bytes]]


class Role(StrEnum):
    """A kind of approval that process/01 section 5 asks for."""

    OWNER = "owner"
    REVIEWER = "reviewer bot"
    SECOND_FAMILY = "second reviewer family"
    SECURITY = "security reviewer"


class Review(BaseModel):
    """One review of a pull request: the reviewer's login, its state and the commit it was given on."""

    model_config = ConfigDict(frozen=True)

    login: str
    state: str
    commit_sha: str


class ApprovalSource(Protocol):
    """Port to the reviews of a pull request (GitHub in CI, a fake in tests)."""

    def reviews(self, number: int) -> list[Review]:
        """Return the reviews of pull request ``number``, oldest first.

        Raises:
            ApprovalSourceError: the source cannot be read.
        """
        ...


class ApprovalSourceError(GateError):
    """The reviews could not be read or were malformed (exit 3)."""


def required_approvers(gate: str, risk: Iterable[str], *, large: bool = False) -> frozenset[Role]:
    """Roles that must approve at ``gate`` (``G1`` spec, ``G2`` plan, ``G3`` merge): the strictest over ``risk``.

    Args:
        gate: ``G1``, ``G2`` or ``G3`` (process/01 section 5).
        risk: the risk classes ``r0`` to ``r3`` that apply together.
        large: for ``G2``, whether the plan is large (the owner approves it).

    Raises:
        ValueError: ``gate`` is none of the three.
    """
    classes = set(risk)
    roles: set[Role] = {Role.REVIEWER}
    if gate == "G2":
        return frozenset({Role.OWNER} if large else roles)
    if gate not in ("G1", "G3"):
        raise ValueError(f"unknown gate {gate!r}")
    if gate == "G1" and classes & {"r1", "r2"}:
        roles = {Role.OWNER}
    if "r3" in classes:
        roles |= {Role.REVIEWER, Role.SECURITY}
    if gate == "G3" and "r1" in classes:
        roles.add(Role.SECOND_FAMILY)
    return frozenset(roles)


def approved_logins(reviews: Iterable[Review], head_sha: str) -> set[str]:
    """Logins whose latest approving or blocking review is an approval given on ``head_sha``; comments are ignored."""
    latest: dict[str, Review] = {}
    for review in reviews:
        if review.state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[review.login] = review
    return {login for login, r in latest.items() if r.state == "APPROVED" and r.commit_sha == head_sha}


class Approvals:
    """The approvals of one pull request, read once from the port and judged against the identities of the config."""

    def __init__(self, source: ApprovalSource, config: GateConfig, *, number: int, author: str, head_sha: str) -> None:
        self._source, self._config, self._number = source, config, number
        self.author, self._head = author, head_sha
        self._approved: set[str] | None = None

    def _logins(self) -> set[str]:
        if self._approved is None:
            self._approved = approved_logins(self._source.reviews(self._number), self._head) - {self.author}
        return self._approved

    def owner_approved(self) -> bool:
        """Whether the owner (not the author) approved the head commit."""
        return self._config.identities.owner_login in self._logins()

    def missing(self, required: frozenset[Role]) -> list[Role]:
        """The roles of ``required`` that no approval covers, sorted; the owner covers all of them."""
        if self.owner_approved():
            return []
        covered = {Role.REVIEWER} if self._config.identities.reviewer_app in self._logins() else set()
        return sorted(required - covered)


def approval_findings(
    approvals: Approvals, required: frozenset[Role], what: str, path: str | None = None
) -> list[Finding]:
    """GC015 naming the roles still missing for ``what``; nothing when ``required`` is covered."""
    roles = approvals.missing(required)
    message = f"approval missing for {what}: {', '.join(roles)}"
    return [Finding(code="GC015", severity=Severity.ERROR, path=path, message=message)] if roles else []


def _http_get(url: str, token: str) -> tuple[int, bytes]:
    """GET ``url`` (HTTPS only) with a bearer token; return the status and body."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise UsageError("the GitHub API URL must be an https URL")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "eng-gate",
    }
    connection = http.client.HTTPSConnection(parts.netloc, timeout=TIMEOUT_SECONDS)
    try:
        connection.request("GET", parts.path + (f"?{parts.query}" if parts.query else ""), headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    except OSError as error:
        raise ApprovalSourceError(f"cannot reach the GitHub API: {type(error).__name__}") from error
    finally:
        connection.close()


class _RawReview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user: Mapping[str, object] | None = None
    state: str
    commit_id: str = ""


class GitHubApprovals:
    """``ApprovalSource`` over the GitHub REST API (``GET /repos/{repo}/pulls/{n}/reviews``), standard library only."""

    def __init__(self, repo: str, token: str, api_url: str = DEFAULT_API_URL, fetch: Fetch = _http_get) -> None:
        self._repo, self._token, self._api, self._fetch = repo, token, api_url.rstrip("/"), fetch

    def reviews(self, number: int) -> list[Review]:
        """Read every page of the reviews; reviews of deleted users are left out.

        Raises:
            ApprovalSourceError: a non-200 answer, malformed JSON, or more than ``MAX_PAGES`` pages.
            UsageError: the API URL is not https.
        """
        found: list[Review] = []
        for page in range(1, MAX_PAGES + 1):
            url = f"{self._api}/repos/{self._repo}/pulls/{number}/reviews?per_page={PAGE_SIZE}&page={page}"
            status, body = self._fetch(url, self._token)
            if status != 200:
                raise ApprovalSourceError(f"GitHub answered {status} for the reviews of pull request {number}")
            try:
                raw = json.loads(body)
                items = [_RawReview.model_validate(item) for item in raw]
            except (ValueError, TypeError, ValidationError) as error:
                raise ApprovalSourceError(f"unreadable reviews of pull request {number}") from error
            found += [
                Review(login=str(i.user["login"]), state=i.state, commit_sha=i.commit_id)
                for i in items
                if i.user and "login" in i.user
            ]
            if len(items) < PAGE_SIZE:
                return found
        raise ApprovalSourceError(f"more than {MAX_PAGES} pages of reviews for pull request {number}")


def source_from_env(env: Mapping[str, str]) -> GitHubApprovals:
    """Build the GitHub adapter from ``GITHUB_REPOSITORY``, ``GITHUB_TOKEN`` and ``GITHUB_API_URL`` (Actions set them).

    Raises:
        UsageError: the repository or the token is missing, or the repository is not ``owner/name``.
    """
    repo, token = env.get("GITHUB_REPOSITORY", ""), env.get("GITHUB_TOKEN", "")
    if not _REPOSITORY.fullmatch(repo) or not token:
        raise UsageError("bootstrap is off: set GITHUB_REPOSITORY (owner/name) and GITHUB_TOKEN to read the approvals")
    return GitHubApprovals(repo, token, env.get("GITHUB_API_URL", DEFAULT_API_URL))
