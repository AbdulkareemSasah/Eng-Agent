"""The full policy: identity (spec 0015 section 4.4).

Purpose: `FullPolicy` stores every record unchanged and is never publishable; `full_policy` is its factory.
Units: none.
Errors: none.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from eng_harness.tasklog._records import TaskRecord
    from eng_harness.tasklog.privacy import PolicyConfig, PolicyContext, PrivacyPolicy

__all__ = ["FullPolicy", "full_policy"]


@dataclass(frozen=True)
class FullPolicy:
    """The full policy: identity, never publishable (spec 0015 §4.4)."""

    name: Literal["full", "sanitized"] = "full"
    publishable: bool = False

    def transform(self, record: TaskRecord, ctx: PolicyContext) -> TaskRecord:
        """Return `record` unchanged (spec 0015 §4.4)."""
        return record


def full_policy(cfg: PolicyConfig) -> PrivacyPolicy:
    """Build the full policy; `cfg` carries no full-specific settings (spec 0015 §4.4)."""
    return FullPolicy()
