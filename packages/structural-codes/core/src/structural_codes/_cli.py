"""Command line `python -m structural_codes verify|hash --pack P` (spec 0001, section 4.9.3; AC33).

`P` is a pack project root. Exit codes: 0 success, 1 a failing case (`verify` only), 2 any data, definition or usage
error, reported as one line on the error stream.
"""

import argparse
import tomllib
from pathlib import Path
from typing import Any, NoReturn, TextIO

from structural_codes.check import Check
from structural_codes.content_hash import content_hash, lint_scope_violations
from structural_codes.errors import CheckDefinitionError, VerificationDataError
from structural_codes.pack import ENTRY_POINT_GROUP, Registry
from structural_codes.verification import CaseFile, VerificationReport, verify_check, verify_pack

_CASES = Path("tests/data/golden/verification")


class _CliError(Exception):
    """A resolution or usage error of the command line (exit 2)."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise _CliError(f"usage: {message}")


def _read(root: Path) -> tuple[str, list[str]]:
    """Return the single pack entry-point name and `check_modules` of `root/pyproject.toml`."""
    try:
        data: dict[str, Any] = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise _CliError(f"cannot read pyproject.toml in {root}: {exc}") from exc
    names = data.get("project", {}).get("entry-points", {}).get(ENTRY_POINT_GROUP, {})
    modules = data.get("tool", {}).get("eng-gate", {}).get("check_modules")
    if len(names) != 1:
        raise _CliError(f"pyproject.toml needs exactly one entry point in {ENTRY_POINT_GROUP}, found {len(names)}")
    if not isinstance(modules, list) or not all(isinstance(m, str) for m in modules):
        raise _CliError("pyproject.toml has no [tool.eng-gate] check_modules list of strings")
    return next(iter(names)), modules


def _resolve(root: Path) -> tuple[Registry, str, list[str]]:
    name, modules = _read(root)
    registry = Registry.discover()
    if all(p.name != name for p in registry.packs):
        raise _CliError(f"pack {name!r} not found by discovery")
    return registry, name, modules


def _overlay_report(check: Check, directory: Path, registry: Registry) -> VerificationReport:
    path = directory / f"{check.meta.check_id}.yaml"
    if path.is_file():
        return verify_check(check, CaseFile.load(path), registry=registry)
    return VerificationReport(check.meta.check_id, content_hash(check), (), (f"no case file {path.name}",))


def _verify(root: Path, out: TextIO) -> int:
    registry, name, modules = _resolve(root)
    pack = next(p for p in registry.packs if p.name == name)
    for check in pack.checks:
        if violations := lint_scope_violations(check, modules):
            raise _CliError(f"{check.meta.check_id}: modules outside check_modules: {', '.join(violations)}")
    if pack.overlay is None:
        reports = verify_pack(pack, root / _CASES)
    else:
        reports = tuple(_overlay_report(c, root / _CASES, registry) for c in registry.checks if c.meta.pack == name)
    for r in reports:
        counts = [sum(c.outcome == o for c in r.cases) for o in ("pass", "fail", "pending")]
        state = "verified" if r.verified else "not verified"
        unmet = f" unmet: {'; '.join(r.unmet)}" if r.unmet else ""
        out.write(f"{r.check_id} {state} pass={counts[0]} fail={counts[1]} pending={counts[2]}{unmet}\n")
    return 1 if any(c.outcome == "fail" for r in reports for c in r.cases) else 0


def _hash(root: Path, out: TextIO) -> int:
    registry, name, _ = _resolve(root)
    for check in registry.checks:
        if check.meta.pack == name:
            out.write(f"{check.meta.check_id} {content_hash(check)}\n")
    return 0


def main(argv: list[str], out: TextIO, err: TextIO) -> int:
    """Run the command line and return the exit code; output goes to `out`, error lines to `err`."""
    parser = _Parser(prog="structural_codes", add_help=False)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("verify", "hash"):
        sub.add_parser(command, add_help=False).add_argument("--pack", required=True, type=Path)
    try:
        args = parser.parse_args(argv)
        return (_verify if args.command == "verify" else _hash)(args.pack, out)
    except (_CliError, CheckDefinitionError, VerificationDataError) as exc:
        err.write(" ".join(str(exc).split()) + "\n")
        return 2
