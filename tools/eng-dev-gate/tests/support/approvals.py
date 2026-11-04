"""Fixture: a fake approvals port for the normal-mode tests (spec 4.1, ``ApprovalSource``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # not at run time: the base commit of the test-first step does not have the module yet
    from eng_dev_gate.approvals import Review


class FakeApprovals:
    """An ``ApprovalSource`` that returns the reviews it was given and records the pull requests asked for."""

    def __init__(self) -> None:
        self.items: list[Review] = []
        self.asked: list[int] = []

    def reviews(self, number: int) -> list[Review]:
        """Return the configured reviews, whatever the pull request."""
        self.asked.append(number)
        return list(self.items)

    def approve(self, login: str, sha: str, state: str = "APPROVED") -> None:
        """Add a review of ``login`` on commit ``sha``."""
        from eng_dev_gate.approvals import Review

        self.items.append(Review(login=login, state=state, commit_sha=sha))
