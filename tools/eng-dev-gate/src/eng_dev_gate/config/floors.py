"""Coverage and mutation floors per profile (spec 4.12, from process/05 section 2).

A package may set a higher value, never a lower one. The ``tool`` row and the ``mutation_min`` rules of the other
profiles are not in process/05 section 2 (spec Q2, owner queue); the gate applies the stricter pair to itself and 80
to any declared ``mutation_min``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from eng_dev_gate.report import Finding, Severity

if TYPE_CHECKING:
    from eng_dev_gate.config.package_config import PackageConfig

MUTATION_FLOOR = 80  # percent; spec 4.12 and process/05 section 2 ("at least 80")


@dataclass(frozen=True)
class Floor:
    """Floor of a profile: ``layer``, ``line`` and ``branch`` coverage (percent), ``mutation_required`` always."""

    layer: int | str
    line: int
    branch: int
    mutation_required: bool


FLOORS: dict[str, Floor] = {  # source: process/05 section 2, spec 4.12 table
    "contract": Floor(1, 95, 90, True),
    "server": Floor(2, 85, 75, False),
    "codes": Floor(3, 95, 90, True),
    "harness": Floor(4, 85, 75, False),
    "tool": Floor("tool", 95, 90, False),
}


def check_floors(config: PackageConfig, path: str) -> list[Finding]:
    """Return one CF002 finding per threshold of ``config`` that is below the floor of its profile.

    Args:
        config: the parsed ``[tool.eng-gate]`` table.
        path: POSIX path of the ``pyproject.toml`` the table came from, used in the findings.

    Returns:
        The findings, empty when every threshold meets its floor. ``mutation_min`` is required (CF002 when absent)
        for ``contract`` and ``codes`` and whenever ``r1_modules`` or ``r2_modules`` is non-empty.
    """
    floor = FLOORS[config.profile]
    messages = []
    for name, value, minimum in (
        ("coverage_line", config.coverage_line, floor.line),
        ("coverage_branch", config.coverage_branch, floor.branch),
    ):
        if value < minimum:
            messages.append(f"{name} {value} is below the floor {minimum} of profile {config.profile}")
    required = floor.mutation_required or bool(config.r1_modules or config.r2_modules)
    if config.mutation_min is None:
        if required:
            messages.append(f"mutation_min is required for profile {config.profile} with R1 or R2 modules")
    elif config.mutation_min < MUTATION_FLOOR:
        messages.append(f"mutation_min {config.mutation_min} is below the floor {MUTATION_FLOOR}")
    return [Finding(code="CF002", severity=Severity.ERROR, path=path, message=m) for m in messages]
