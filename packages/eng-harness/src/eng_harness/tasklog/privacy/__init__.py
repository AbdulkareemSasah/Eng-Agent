"""Task-log privacy policies: the protocol, the registry and the selection (spec 0015 section 4.4).

Purpose: `PrivacyPolicy` is the pure per-record transform every policy implements; `POLICIES` maps each policy
name to its factory; `policy_for` resolves the `[tasklog] policy` key (`full` today, `sanitized` as gap `TL-G1`).
Units: none.
Errors: `ConfigError` (`tasklog.policy`) for a missing or unknown name; `NotImplementedGap` `TL-G1` for
`sanitized` (spec 0015 §4.4, §6, §11).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from eng_harness.servers import ConfigError
from eng_harness.tasklog._records import TaskRecord
from eng_harness.tasklog.privacy._full import full_policy
from eng_harness.tasklog.privacy._sanitized import sanitized_policy

__all__ = ["POLICIES", "PolicyConfig", "PolicyContext", "PrivacyPolicy", "policy_for"]

_POLICY_KEY = "tasklog.policy"
"""The configuration key that names the policy (spec 0015 §4.6)."""


class PolicyConfig(Protocol):
    """The configuration `policy_for` reads: only the policy name (spec 0015 §4.4; T4a owns the full model)."""

    @property
    def policy(self) -> str | None:
        """The configured policy name, else None when the key is absent."""
        ...


@dataclass(frozen=True)
class PolicyContext:
    """The context of a policy transform; `sanitized` (T13) carries its placeholder map here (spec 0015 §4.4)."""


class PrivacyPolicy(Protocol):
    """A pure per-record privacy transform (spec 0015 §4.4)."""

    @property
    def name(self) -> Literal["full", "sanitized"]:
        """The policy name."""
        ...

    @property
    def publishable(self) -> bool:
        """Whether records under this policy may be published."""
        ...

    def transform(self, record: TaskRecord, ctx: PolicyContext) -> TaskRecord:
        """Return the record as stored under this policy; pure (spec 0015 §4.4)."""
        ...


POLICIES: Mapping[str, Callable[[PolicyConfig], PrivacyPolicy]] = {
    "full": full_policy,
    "sanitized": sanitized_policy,
}
"""The policy factories by name (spec 0015 §4.4)."""


def policy_for(cfg: PolicyConfig) -> PrivacyPolicy:
    """Resolve the policy named by `cfg` (spec 0015 §4.4, §4.6).

    Raises:
        ConfigError: `tasklog.policy` is missing or names no known policy (exit 3).
        NotImplementedGap: `sanitized` is gap `TL-G1` (spec 0015 §11).
    """
    name = cfg.policy
    if name is None:
        raise ConfigError(_POLICY_KEY, "policy is required: expected full or sanitized")
    if name not in POLICIES:
        raise ConfigError(_POLICY_KEY, f"unknown policy {name!r}: expected full or sanitized")
    return POLICIES[name](cfg)
