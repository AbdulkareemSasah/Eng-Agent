"""The ``docs-fresh`` step (spec 4.12): generated documents equal their regeneration (GF001, GF002), then drift."""

from __future__ import annotations

import difflib
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import TypeAdapter, ValidationError

from eng_dev_gate import agents
from eng_dev_gate.config import load_gate_config
from eng_dev_gate.config.package_config import GeneratedEntry
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import EnvironmentFaultError, UsageError
from eng_dev_gate.toolrun import python_module
from eng_dev_gate.workspace import Member, discover_members

if TYPE_CHECKING:
    from eng_dev_gate.checks.registry import StepContext

_ENTRIES = TypeAdapter(list[GeneratedEntry])
DIFF_LINES = 20  # lines of unified diff quoted in GF001; presentation only


def _table(member_dir: Path) -> dict[str, object]:
    try:
        data = tomllib.loads((member_dir / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise UsageError(f"cannot read {member_dir / 'pyproject.toml'}: {error}") from error
    table = data.get("tool", {}).get("eng-gate", {})
    return table if isinstance(table, dict) else {}


def _package_names(root: Path) -> set[str]:
    """Top-level import names of the workspace packages: project names and declared ``import_names``."""
    names: set[str] = set()
    for member in discover_members(root):
        names.add(member.name.replace("-", "_").lower())
        imports = _table(member.directory).get("import_names", [])
        if isinstance(imports, list):
            names.update(i for i in imports if isinstance(i, str))
    return names


def _lf(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n")


def _generate(ctx: StepContext, member: Member, entry: GeneratedEntry) -> str:
    top = entry.module.split(".")[0]
    if " " in entry.module or top not in _package_names(ctx.root):
        raise EnvironmentFaultError(
            f"GF002 {entry.path}: module {entry.module!r} is not a module of a workspace package"
        )
    done = ctx.runner.run(python_module(entry.module, *entry.args), member.directory)
    if done.exit_code != 0:
        raise EnvironmentFaultError(f"GF002 {entry.path}: {entry.module} exited {done.exit_code}: {done.output[:500]}")
    return _lf(done.output.encode("utf-8"))


def generated(ctx: StepContext) -> list[Finding]:
    """Regenerate each ``[[tool.eng-gate.generated]]`` document and compare it with the committed file (GF001).

    The generator is ``python -m <module> <args>`` in the package directory; its output (standard output and error
    together, as the tool runner returns them) is compared after normalizing line endings to LF. Then the AGENTS.md
    of the package is compared with its rendering (AG004, AG006).

    Raises:
        EnvironmentFaultError: GF002, a generator is not a workspace module or does not run (exit 3).
        UsageError: an entry is invalid, or an AGENTS.md configuration is (exit 2).
    """
    assert ctx.member is not None  # noqa: S101 - package steps always have a member
    member = ctx.member
    try:
        entries = _ENTRIES.validate_python(_table(member.directory).get("generated", []))
    except ValidationError as error:
        raise UsageError(f"invalid [[tool.eng-gate.generated]] in {member.path}: {error}") from error
    findings: list[Finding] = []
    for entry in entries:
        rendered = _generate(ctx, member, entry)
        target = member.directory / entry.path
        shown = f"{member.path}/{entry.path}"
        committed = _lf(target.read_bytes()) if target.is_file() else None
        if committed != rendered:
            diff = difflib.unified_diff(
                (committed or "").splitlines(), rendered.splitlines(), "committed", "regenerated", lineterm=""
            )
            text = "\n".join(list(diff)[:DIFF_LINES])
            message = f"differs from its regeneration ({entry.module}); regenerate and commit it\n{text}"
            findings.append(Finding(code="GF001", severity=Severity.ERROR, path=shown, message=message))
    units = [u for u in agents.units_of(ctx.root) if u.path == member.path]
    limit = load_gate_config(ctx.gate_root).limits.diff_lines
    return findings + agents.drift_findings(ctx.root, units, [], [], limit)
