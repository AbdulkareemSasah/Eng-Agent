"""``agents render``, ``agents keys`` and ``agents drift`` (spec 4.13, AC55 to AC58).

A ``.gate/agents.yml`` names a template, an output file and the values of the template placeholders. Rendering is a
single pass of plain substitution; the committed ``AGENTS.md`` must equal its rendering, or ``drift`` fails (AG004).
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from eng_dev_gate import report
from eng_dev_gate.config.gate_config import load_gate_config
from eng_dev_gate.gitio import GIT_TIMEOUT_SECONDS, GitError
from eng_dev_gate.globs import matches_any
from eng_dev_gate.report import CommandResult, Finding, Severity, StepResult
from eng_dev_gate.results import ExitCode, GateError, Status, UsageError
from eng_dev_gate.workspace import discover_members

PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
VERSION_KEY = "template-version"
POINTER = "@AGENTS.md\n"  # whole content of the CLAUDE.md next to a managed file (CLAUDE.template.md)


class RenderError(GateError):
    """Rendering failed with diagnostics ``codes`` as ``(code, message)``; exit 2 if AG007 is among them, else 1."""

    def __init__(self, codes: list[tuple[str, str]]) -> None:
        super().__init__("; ".join(f"{code} {message}" for code, message in codes))
        self.codes = codes
        self.exit_code = ExitCode.USAGE if any(code == "AG007" for code, _ in codes) else ExitCode.FAILED


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: str
    output: str
    values: dict[str, str]


class Unit(BaseModel):
    """One managed output: ``name`` and ``path`` of its package (``""`` and ``.`` for the root), the output path
    relative to the workspace root (POSIX), the template path as written and the values."""

    name: str
    path: str
    output: str
    template: str
    values: dict[str, str]


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n")


def template_version(template: str) -> str:
    """Return ``sha256:`` plus the first 12 hex digits of the SHA-256 of the LF-normalized template."""
    return "sha256:" + hashlib.sha256(_lf(template).encode("utf-8")).hexdigest()[:12]


def _keys(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1) for m in PLACEHOLDER.finditer(text)))


def render_template(template: str, values: dict[str, str]) -> str:
    """Substitute every placeholder of ``template`` (LF normalized) by its value, in one pass.

    A placeholder alone on its line with the value ``""`` removes the line with its newline.

    Raises:
        RenderError: AG001 (missing values, all listed), AG002 (unused values), AG003 (stale ``template-version``),
            AG007 (a value contains ``{{``). Nothing is returned on error.
    """
    text = _lf(template)
    keys = _keys(text)
    codes: list[tuple[str, str]] = []
    if missing := [k for k in keys if k not in values]:
        codes.append(("AG001", f"no value for placeholder(s): {missing!r}"))
    if unused := [k for k in values if k not in keys]:
        codes.append(("AG002", f"value(s) without a placeholder: {unused!r}"))
    if recursive := [k for k, v in values.items() if "{{" in v]:
        codes.append(("AG007", f"value(s) contain '{{{{': {recursive!r}"))
    if VERSION_KEY in values and values[VERSION_KEY] != template_version(text):
        codes.append(("AG003", f"{VERSION_KEY} is {values[VERSION_KEY]!r}, the template is {template_version(text)}"))
    if codes:
        raise RenderError(codes)
    parts: list[str] = []
    pos = 0
    for match in PLACEHOLDER.finditer(text):
        value = values[match.group(1)]
        parts.append(text[pos : match.start()])
        pos = match.end()
        alone = (match.start() == 0 or text[match.start() - 1] == "\n") and text[pos : pos + 1] in ("\n", "")
        if value == "" and alone:
            pos += 1  # the newline of the removed line (or the end of the text)
        else:
            parts.append(value)
    parts.append(text[pos:])
    return "".join(parts)


def keys_skeleton(template: str) -> str:
    """Return a YAML ``values`` skeleton: every placeholder once, in template order, as a JSON-quoted key.

    The ``template-version`` entry carries the version of ``template``; all others are ``""``.
    """
    text = _lf(template)
    lines = ["values:"]
    for key in _keys(text):
        value = template_version(text) if key == VERSION_KEY else ""
        lines.append(f"  {json.dumps(key, ensure_ascii=False)}: {json.dumps(value)}")
    return "\n".join(lines) + "\n"


def _inside(root: Path, path: Path, what: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise UsageError(f"{what} {path} is outside the workspace root")
    return resolved


def _read_text(path: Path) -> str:
    try:
        return _lf(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        raise UsageError(f"cannot read {path}: {error}") from error


def _load_unit(root: Path, directory: Path, name: str, path: str) -> Unit | None:
    config_path = directory / ".gate" / "agents.yml"
    if not config_path.is_file():
        return None
    try:
        config = _Config.model_validate(yaml.safe_load(_read_text(config_path)))
    except (yaml.YAMLError, ValidationError) as error:
        raise UsageError(f"invalid {config_path}: {error}") from error
    output = _inside(root, directory / config.output, "output")
    rel = PurePosixPath(output.relative_to(root.resolve()).as_posix()).as_posix()
    return Unit(name=name, path=path, output=rel, template=str(directory / config.template), values=config.values)


def units_of(root: Path) -> list[Unit]:
    """Return the managed outputs: the root's, then each workspace member's, from their ``.gate/agents.yml``.

    Raises:
        UsageError: an ``agents.yml`` is unreadable or invalid, or a path leaves the workspace root.
    """
    found = [_load_unit(root, root, "", ".")]
    found += [_load_unit(root, m.directory, m.name, m.path) for m in discover_members(root)]
    return [u for u in found if u is not None]


def render_unit(root: Path, unit: Unit) -> str:
    """Render one unit in memory. Raises ``UsageError`` (template outside root or unreadable), ``RenderError``."""
    return render_template(_read_text(_inside(root, Path(unit.template), "template")), unit.values)


def tracked_files(root: Path) -> list[str]:
    """Return the POSIX paths from ``git ls-files`` in ``root``. Raises ``GitError`` (exit 3)."""
    command = ["git", "-c", "core.quotepath=off", "ls-files", "-z"]
    try:
        done = subprocess.run(  # noqa: S603  # B-033: no shell; the caller passes a fixed argument list
            command, cwd=root, capture_output=True, timeout=GIT_TIMEOUT_SECONDS, check=False
        )
        if done.returncode != 0:
            raise GitError(f"git ls-files failed with exit {done.returncode}")
        return [p for p in done.stdout.decode("utf-8").split("\0") if p]
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError) as error:
        raise GitError(f"git ls-files could not run: {error}") from error


def drift_findings(
    root: Path, units: list[Unit], tracked: list[str], unmanaged_ok: list[str], diff_lines: int
) -> list[Finding]:
    """Compare every managed output with its rendering (AG004), list unmanaged tracked ``AGENTS.md`` (AG005) and
    managed outputs without the ``CLAUDE.md`` pointer (AG006).

    Raises:
        RenderError: a rendering has AG007 (exit 2). Other render errors become findings.
    """

    def error(code: str, path: str, message: str) -> Finding:
        return Finding(code=code, severity=Severity.ERROR, path=path, message=message)

    findings: list[Finding] = []
    for unit in units:
        try:
            rendered = render_unit(root, unit)
        except RenderError as failure:
            if failure.exit_code is ExitCode.USAGE:
                raise
            findings += [error(code, unit.output, message) for code, message in failure.codes]
            continue
        target = root / unit.output
        committed = _read_text(target) if target.is_file() else None
        if committed != rendered:
            diff = list(
                difflib.unified_diff(
                    (committed or "").splitlines(), rendered.splitlines(), "committed", "rendering", lineterm=""
                )
            )
            shown = "\n".join(diff[:diff_lines])
            findings.append(error("AG004", unit.output, f"differs from its rendering; run agents render\n{shown}"))
        pointer = target.parent / "CLAUDE.md"
        if not pointer.is_file() or _read_text(pointer) != POINTER:
            findings.append(error("AG006", unit.output, "the directory has no CLAUDE.md that holds only '@AGENTS.md'"))
    managed = {u.output for u in units}
    for path in sorted(tracked):
        if PurePosixPath(path).name == "AGENTS.md" and path not in managed and not matches_any(path, unmanaged_ok):
            findings.append(error("AG005", path, "tracked AGENTS.md that no .gate/agents.yml manages"))
    return findings


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the ``render``, ``keys`` and ``drift`` subcommands to the ``agents`` parser."""
    sub = parser.add_subparsers(dest="agents_command", required=True)
    render_parser = sub.add_parser("render", help="write the AGENTS.md of the root, a package or all")
    group = render_parser.add_mutually_exclusive_group()
    group.add_argument("--package", help="package name or path")
    group.add_argument("--all", action="store_true", help="every managed output")
    sub.add_parser("keys", help="print a values skeleton").add_argument("template")
    sub.add_parser("drift", help="compare committed AGENTS.md files with their rendering")


def _select(root: Path, units: list[Unit], args: argparse.Namespace) -> list[Unit]:
    if args.all:
        return units
    wanted = args.package or "."
    chosen = [u for u in units if wanted in (u.name, u.path)]
    if not chosen:
        raise UsageError(f"no .gate/agents.yml for {wanted!r}")
    return chosen


def handle(args: argparse.Namespace) -> Status:
    """Run ``agents render|keys|drift``. Errors raise typed ``GateError`` subclasses (exit 1, 2 or 3)."""
    root = Path(args.root)
    if args.agents_command == "keys":
        template = _inside(root, root / args.template, "template")
        sys.stdout.write(keys_skeleton(_read_text(template)))
        return Status.PASS
    units = units_of(root)
    if args.agents_command == "render":
        chosen = _select(root, units, args)
        rendered = [(u, render_unit(root, u)) for u in chosen]  # all or nothing: write only after every render
        for unit, text in rendered:
            try:
                (root / unit.output).write_bytes(text.encode("utf-8"))
            except OSError as error:
                raise UsageError(f"cannot write {unit.output}: {error}") from error
            sys.stdout.write(f"wrote {unit.output}\n")
        return Status.PASS
    config = load_gate_config(Path(args.gate_root or args.root))
    findings = drift_findings(root, units, tracked_files(root), config.agents.unmanaged_ok, config.limits.diff_lines)
    result = CommandResult(
        command="agents drift", mode=config.mode.value, steps=[StepResult(name="agents-drift", findings=findings)]
    )
    report.render(result, args.format, sys.stdout, os.environ)
    return result.status
