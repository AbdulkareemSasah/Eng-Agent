"""The sanitized policy stub: gap TL-G1 until the owner defines its rules (spec 0015 section 4.4).

Purpose: `sanitized_policy` is the `POLICIES` factory of `sanitized`; it always raises `NotImplementedGap`.
Units: none.
Errors: `NotImplementedGap` `TL-G1` (spec 0015 §6, §11).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eng_harness.errors import NotImplementedGap

if TYPE_CHECKING:
    from eng_harness.tasklog.privacy import PolicyConfig, PrivacyPolicy

__all__ = ["sanitized_policy"]

_GAP_ID = "TL-G1"
"""The spec gap of the sanitized policy (spec 0015 §11)."""


def sanitized_policy(cfg: PolicyConfig) -> PrivacyPolicy:
    """Raise `NotImplementedGap` TL-G1: the sanitized rules are undefined (spec 0015 §4.4, §11)."""
    raise NotImplementedGap(f"the sanitized policy is not implemented (gap {_GAP_ID})", evidence=(_GAP_ID,))
