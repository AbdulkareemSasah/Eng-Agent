"""The ``forbidden`` step (spec 4.8): the policy from the gate root applied to the sources of one member."""

from __future__ import annotations

from typing import TYPE_CHECKING

from eng_dev_gate.checks.forbidden.engine import parse_config, scan_member
from eng_dev_gate.checks.forbidden.rules_a import RULES_A
from eng_dev_gate.checks.forbidden.rules_b import RULES_B
from eng_dev_gate.config import load_gate_config
from eng_dev_gate.report import Finding
from eng_dev_gate.results import UsageError

if TYPE_CHECKING:
    from eng_dev_gate.checks.registry import StepContext

RULES = (*RULES_A, *RULES_B)


def run_step(ctx: StepContext) -> list[Finding]:
    """Scan the member of ``ctx`` with the ``.gate/forbidden.yml`` and the spike globs of the gate root.

    Raises:
        UsageError: the policy file is unreadable or invalid, or a source file cannot be read (exit 2).
    """
    assert ctx.member is not None  # noqa: S101  # B-039: package steps always have a member
    policy = ctx.gate_root / ".gate" / "forbidden.yml"
    try:
        text = policy.read_text(encoding="utf-8")
    except OSError as error:
        raise UsageError(f"cannot read {policy}: {error}") from error
    spikes = load_gate_config(ctx.gate_root).spike_globs
    return scan_member(ctx.root, ctx.member, parse_config(text, str(policy)), RULES, spikes)
