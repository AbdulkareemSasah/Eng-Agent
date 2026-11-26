"""Privacy policies: required selection and the sanitized gap (plan 0015 T2; spec 0015 AC8, §4.4)."""

from dataclasses import dataclass

import pytest
from eng_harness.tasklog.privacy import POLICIES, policy_for

from eng_harness.errors import HarnessCode, NotImplementedGap
from eng_harness.servers import ConfigError


@dataclass(frozen=True)
class _PolicyName:
    """Stand-in for the T4a tasklog config: `policy_for` reads only `policy` (spec 0015 §4.4)."""

    policy: str | None


def test_policy_required() -> None:
    """AC8: the registry holds full/sanitized; full resolves; missing/unknown refused (§4.4, §4.6)."""
    assert set(POLICIES) == {"full", "sanitized"}
    full = policy_for(_PolicyName("full"))
    assert full.name == "full"
    assert full.publishable is False
    assert callable(full.transform)
    with pytest.raises(ConfigError) as missing:
        policy_for(_PolicyName(None))
    assert missing.value.key == "tasklog.policy"
    with pytest.raises(ConfigError) as unknown:
        policy_for(_PolicyName("bogus-policy"))
    assert unknown.value.key == "tasklog.policy"


def test_sanitized_gap_tl_g1() -> None:
    """AC8: selecting sanitized raises NotImplementedGap TL-G1 (spec 0015 §4.4, §6, §11 TL-G1)."""
    assert "sanitized" in POLICIES
    with pytest.raises(NotImplementedGap) as gap:
        policy_for(_PolicyName("sanitized"))
    assert gap.value.code == HarnessCode.NOT_IMPLEMENTED
    assert "TL-G1" in gap.value.evidence
