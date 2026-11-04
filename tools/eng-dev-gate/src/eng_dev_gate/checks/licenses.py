"""The ``licenses`` step (spec 4.12): allowed licenses of the dependency closure (LC001 to LC003).

The closure is read from ``importlib.metadata`` of the active environment, starting at the package's runtime
dependencies and dependency groups. Allowed (process/04 section 7): MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0.
"""

from __future__ import annotations

import argparse
import re
import tomllib
from importlib.metadata import Distribution, distributions
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eng_dev_gate.config import load_gate_config
from eng_dev_gate.config.gate_config import LicenseException
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import Status, UsageError
from eng_dev_gate.toolrun import ToolRunner
from eng_dev_gate.workspace import discover_members

if TYPE_CHECKING:
    from eng_dev_gate.checks.check import Handler
    from eng_dev_gate.checks.registry import StepContext

SEARCH_PATH: list[str] | None = (
    None  # where distributions are looked up; None is ``sys.path`` (tests point it elsewhere)
)

ALLOWED = frozenset({"mit", "bsd-2-clause", "bsd-3-clause", "apache-2.0", "isc", "psf-2.0", "python-2.0", "mpl-2.0"})
# Free-text and trove-classifier spellings of the allowed licenses (a bare "BSD License" does not name its clauses).
ALIASES = {
    "mit license": "mit", "bsd license": "bsd-3-clause", "bsd": "bsd-3-clause", "apache software license": "apache-2.0",
    "apache 2.0": "apache-2.0", "apache license 2.0": "apache-2.0", "apache license, version 2.0": "apache-2.0",
    "isc license (iscl)": "isc", "isc license": "isc", "python software foundation license": "psf-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "mpl-2.0",
}  # fmt: skip
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_TOKEN = re.compile(r"\(|\)|[^\s()]+")
MAX_FIELD_LENGTH = 100  # a longer ``License`` field is license text, not a name; presentation limit


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


class _Expression:
    """Evaluates an SPDX-like expression: ``OR`` needs one allowed side, ``AND`` all; ``WITH`` is never allowed."""

    def __init__(self, text: str) -> None:
        self._tokens = _TOKEN.findall(text)
        self._at = 0

    def allowed(self) -> bool:
        """Return whether the whole expression is allowed; a malformed expression is not."""
        result = self._or()
        return result and self._at == len(self._tokens)

    def _peek(self) -> str:
        return self._tokens[self._at].upper() if self._at < len(self._tokens) else ""

    def _or(self) -> bool:
        result = self._and()
        while self._peek() == "OR":
            self._at += 1
            result = self._and() or result
        return result

    def _and(self) -> bool:
        result = self._atom()
        while self._peek() == "AND":
            self._at += 1
            result = self._atom() and result
        return result

    def _atom(self) -> bool:
        if self._peek() == "(":
            self._at += 1
            inner = self._or()
            if self._peek() != ")":
                return False
            self._at += 1
            return inner
        if self._at >= len(self._tokens):
            return False
        name = self._tokens[self._at].lower()
        self._at += 1
        if self._peek() == "WITH":
            self._at += 2
            return False
        return ALIASES.get(name, name) in ALLOWED


def _declared(dist: Distribution) -> tuple[str, bool] | None:
    """Return the license text and whether it is allowed (expression, then ``License`` field, then classifiers)."""
    meta = dist.metadata
    expression = (meta.get("License-Expression") or "").strip()
    if expression:
        return expression, _Expression(expression).allowed()
    text = (meta.get("License") or "").strip()
    if text and text.upper() != "UNKNOWN" and "\n" not in text and len(text) <= MAX_FIELD_LENGTH:
        return text, _Expression(ALIASES.get(text.lower(), text)).allowed()
    names = [c.rsplit("::", 1)[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    if names:
        return "; ".join(names), all(ALIASES.get(n.lower(), n.lower()) in ALLOWED for n in names)
    return None


def _requirements(directory: Path) -> list[str]:
    """Runtime dependencies and dependency-group entries (``include-group`` followed) of a member's pyproject."""
    try:
        data: dict[str, Any] = tomllib.loads((directory / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise UsageError(f"cannot read {directory / 'pyproject.toml'}: {error}") from error
    groups: dict[str, list[Any]] = data.get("dependency-groups", {})
    found: list[str] = list(data.get("project", {}).get("dependencies", []))
    pending, seen = list(groups), set[str]()
    while pending:
        group = pending.pop(0)
        if group in seen:
            continue
        seen.add(group)
        for entry in groups.get(group, []):
            if isinstance(entry, str):
                found.append(entry)
            elif isinstance(entry, dict) and "include-group" in entry:
                pending.append(str(entry["include-group"]))
    return found


def _split(requirement: str) -> tuple[str, bool] | None:
    """Return the normalized name and whether a non-extra marker guards it; None for an extra-only requirement."""
    head, _, marker = requirement.partition(";")
    match = _NAME.match(head.strip())
    if match is None or "extra" in marker:
        return None
    return _normalize(match.group()), bool(marker.strip())


def _finding(code: str, path: str, message: str) -> Finding:
    return Finding(code=code, severity=Severity.ERROR, path=path, message=message)


def _judge(
    name: str, dist: Distribution | None, exceptions: dict[str, LicenseException], root: Path, path: str
) -> Finding | None:
    declared = _declared(dist) if dist else None
    if declared is None:
        return _finding("LC002", path, f"{name}: no license metadata (License-Expression, License or classifier)")
    text, allowed = declared
    if allowed:
        return None
    exception = exceptions.get(name)
    if exception is None or exception.license != text:
        return _finding(
            "LC001", path, f"{name}: license {text!r} is not allowed (MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0)"
        )
    if not (root / exception.adr).is_file():
        return _finding("LC003", path, f"{name}: license {text!r} is excepted by {exception.adr}, which does not exist")
    return None


def licenses(ctx: StepContext) -> list[Finding]:
    """Check every distribution of the dependency closure of the member; workspace members are not checked.

    A requirement guarded by an environment marker is followed only when it is installed; an extra is not followed.

    Raises:
        UsageError: a ``pyproject.toml`` is unreadable (exit 2).
        ConfigError: ``.gate/gate.yml`` of the gate root is invalid (exit 2).
    """
    assert ctx.member is not None  # noqa: S101  # B-048: package steps always have a member
    exceptions = {_normalize(e.distribution): e for e in load_gate_config(ctx.gate_root).license_exceptions}
    members = {_normalize(m.name) for m in discover_members(ctx.root)}
    installed = {
        _normalize(d.metadata["Name"]): d for d in (distributions(path=SEARCH_PATH) if SEARCH_PATH else distributions())
    }
    queue = [r for r in map(_split, _requirements(ctx.member.directory)) if r]
    seen: set[str] = set()
    findings: list[Finding] = []
    while queue:
        name, guarded = queue.pop(0)
        dist = installed.get(name)
        if name in seen or name in members or (guarded and dist is None):
            continue
        seen.add(name)
        if finding := _judge(name, dist, exceptions, ctx.root, ctx.member.path):
            findings.append(finding)
        queue += [r for r in map(_split, (dist.requires or []) if dist else []) if r]
    return findings


def make_handler(runner: ToolRunner | None = None) -> Handler:
    """Return the ``licenses`` command handler: the ``check`` handler restricted to the ``licenses`` step."""
    from eng_dev_gate.checks.check import make_handler as make_check_handler

    check = make_check_handler(runner)

    def handler(args: argparse.Namespace) -> Status:
        return check(argparse.Namespace(**{**vars(args), "only": ["licenses"], "skip": [], "fail_fast": False}))

    return handler
