"""The step registry of ``check`` (spec 4.12). A later task adds its step to ``STEPS`` in ``STEP_ORDER`` order."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from eng_dev_gate.checks import generated, licenses, tests_step, tool_steps
from eng_dev_gate.report import Finding
from eng_dev_gate.toolrun import ToolRunner
from eng_dev_gate.workspace import Member

# The 14 steps in the order of spec 4.12.
STEP_ORDER: tuple[str, ...] = (
    "lock", "config", "format", "lint", "types", "forbidden", "imports", "ratchet", "secrets", "tests",
    "docs-fresh", "licenses", "mutation", "workflows",
)  # fmt: skip


@dataclass(frozen=True)
class StepContext:
    """What a step sees: workspace ``root``, ``gate_root`` (policy files), the ``member`` for package steps."""

    root: Path
    gate_root: Path
    member: Member | None
    runner: ToolRunner


@dataclass(frozen=True)
class Step:
    """A step: ``level`` ``root`` runs once, ``package`` once per selected member; ``run`` returns its findings."""

    name: str
    level: Literal["root", "package"]
    run: Callable[[StepContext], list[Finding]]


STEPS: tuple[Step, ...] = (
    Step("lock", "root", tool_steps.lock),
    Step("format", "package", tool_steps.format_),
    Step("lint", "package", tool_steps.lint),
    Step("types", "package", tool_steps.types),
    Step("tests", "package", tests_step.tests),
    Step("docs-fresh", "package", generated.generated),
    Step("licenses", "package", licenses.licenses),
)
