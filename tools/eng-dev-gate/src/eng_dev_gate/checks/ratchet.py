"""The ``ratchet`` step and command (spec 4.9): suppression and skip counts that may only fall.

Markers are found with ``tokenize`` (comments) and ``ast`` (pytest and unittest markers). Counts per package and
bucket are compared with ``.gate/ratchet.json`` (RT001), each marker needs an issue reference (RT002, RT006) and,
for skips and expected failures, a valid unexpired date (RT003, RT004). A rise of the file against the gate root's
copy is AW05 (spec 4.4).
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import sys
import tokenize
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from eng_dev_gate.config import GateConfig, Mode, awaiting_finding, load_gate_config
from eng_dev_gate.gate_root import GateContext
from eng_dev_gate.report import CommandResult, Finding, Severity, StepResult, render
from eng_dev_gate.results import Status, UsageError
from eng_dev_gate.workspace import Member, discover_members

if TYPE_CHECKING:
    from eng_dev_gate.checks.registry import StepContext

BUCKETS = ("noqa", "type_ignore", "pragma_no_cover", "skip", "xfail")
RATCHET_FILE = ".gate/ratchet.json"
ISSUE = re.compile(r"#\d+|\bB-\d+\b")  # an issue reference (spec 4.9)
EXPIRES = re.compile(r"\bexpires (\d{4}-\d{2}-\d{2})\b")
COMMENT_BUCKETS = (
    ("noqa", re.compile(r"#\s*(?:(?:ruff|flake8):\s*)?noqa\b", re.IGNORECASE)),
    ("type_ignore", re.compile(r"#\s*(?:type:\s*ignore|mypy:\s*ignore-errors)")),
    ("pragma_no_cover", re.compile(r"#\s*pragma:\s*no (?:cover|branch)")),
)
SKIP_NAMES = {"pytest.mark.skip", "pytest.mark.skipif", "pytest.skip", "pytest.importorskip"}
XFAIL_NAMES = {"pytest.mark.xfail", "pytest.xfail"}


class RatchetFileError(UsageError):
    """RT005: ``.gate/ratchet.json`` is not valid (exit 2)."""

    def __init__(self, message: str) -> None:
        super().__init__(f"RT005 {message}")


class Clock(Protocol):
    """Port to the date, so that expiry tests are deterministic."""

    def today(self) -> date:
        """Return today's date."""
        ...


class SystemClock:
    """:class:`Clock` over the system date."""

    def today(self) -> date:
        """Return the local date."""
        return date.today()


class RatchetFile(BaseModel):
    """``.gate/ratchet.json``: ``counts`` per package directory and bucket; absent means zero."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    counts: dict[
        str, dict[Literal["noqa", "type_ignore", "pragma_no_cover", "skip", "xfail"], Annotated[int, Field(ge=0)]]
    ]


@dataclass(frozen=True)
class Marker:
    """One counted occurrence: ``bucket``, 1-based ``line`` and ``text`` (the comment or the reason string)."""

    bucket: str
    line: int
    text: str | None


def _dotted(node: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([node.id, *reversed(parts)])


def _bucket(name: str) -> str | None:
    if name in XFAIL_NAMES:
        return "xfail"
    if name in SKIP_NAMES or name.startswith("unittest.skip") or name.endswith(".skipTest"):
        return "skip"
    return None


def _reason(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == "reason" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value
    if name.endswith("importorskip"):  # its first positional argument is a module name
        return None
    texts = [a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    return texts[-1] if texts else None


def scan_source(source: str, path: str) -> list[Marker]:
    """Return the markers of one module: suppression comments and skip or xfail markers.

    Raises:
        UsageError: the source cannot be tokenized or parsed (exit 2).
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        tree = ast.parse(source, path)
    except (tokenize.TokenError, SyntaxError) as error:
        raise UsageError(f"cannot parse {path}: {error}") from error
    found = [
        Marker(bucket, token.start[0], token.string)
        for token in tokens
        if token.type == tokenize.COMMENT
        for bucket, pattern in COMMENT_BUCKETS
        if pattern.search(token.string)
    ]
    consumed: set[int] = set()
    for node in ast.walk(tree):  # a parent is visited before its children, so a call claims its function first
        call = node if isinstance(node, ast.Call) else None
        target = call.func if call is not None else node
        if id(target) in consumed or not isinstance(target, ast.Attribute):
            continue
        consumed.add(id(target))
        name = _dotted(target)
        bucket = _bucket(name) if name else None
        if name and bucket:
            found.append(Marker(bucket, target.lineno, _reason(call, name) if call is not None else None))
    return sorted(found, key=lambda marker: marker.line)


def marker_findings(markers: list[Marker], path: str, today: date) -> list[Finding]:
    """Return RT002, RT003, RT004 and RT006 for ``markers`` of the file ``path`` (spec 4.9)."""

    def error(code: str, marker: Marker, message: str) -> Finding:
        return Finding(code=code, severity=Severity.ERROR, path=path, line=marker.line, message=message)

    findings: list[Finding] = []
    for marker in markers:
        text = marker.text or ""
        if marker.bucket in ("noqa", "type_ignore") and not ISSUE.search(text):
            findings.append(
                error("RT006", marker, f"{marker.bucket} comment without an issue reference (#<n> or B-<n>)")
            )
        if marker.bucket not in ("skip", "xfail"):
            continue
        if not ISSUE.search(text):
            findings.append(error("RT002", marker, f"{marker.bucket} without an issue reference in its reason"))
        match = EXPIRES.search(text)
        try:
            expiry = date.fromisoformat(match.group(1)) if match else None
        except ValueError:
            expiry = None
        if expiry is None:
            findings.append(
                error("RT003", marker, f"{marker.bucket} without a valid 'expires <yyyy-mm-dd>' in its reason")
            )
        elif expiry < today:
            findings.append(error("RT004", marker, f"{marker.bucket} expired on {expiry.isoformat()}"))
    return findings


def load_recorded(path: Path) -> dict[str, dict[str, int]]:
    """Read ``.gate/ratchet.json``; a missing file records nothing (every count is zero).

    Raises:
        RatchetFileError: RT005, the file is unreadable or invalid (exit 2).
    """
    if not path.is_file():
        return {}
    try:
        parsed = RatchetFile.model_validate_json(path.read_text(encoding="utf-8"))
        return {package: {str(b): n for b, n in counts.items()} for package, counts in parsed.counts.items()}
    except (OSError, ValueError) as error:  # pydantic's ValidationError is a ValueError
        raise RatchetFileError(f"{path}: {error}") from error


def _files(member: Member) -> Iterator[Path]:
    for folder in ("src", "tests"):
        yield from sorted((member.directory / folder).rglob("*.py"))
    if (member.directory / "conftest.py").is_file():
        yield member.directory / "conftest.py"


def _scan(root: Path, members: list[Member], today: date) -> tuple[dict[str, dict[str, int]], list[Finding]]:
    actual: dict[str, dict[str, int]] = {}
    findings: list[Finding] = []
    for member in members:
        counts = dict.fromkeys(BUCKETS, 0)
        for file in _files(member):
            try:
                source = file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                raise UsageError(f"cannot read {file}: {error}") from error
            relative = file.relative_to(root).as_posix()
            markers = scan_source(source, relative)
            for marker in markers:
                counts[marker.bucket] += 1
            findings.extend(marker_findings(markers, relative, today))
        actual[member.path] = counts
    return actual, findings


def _compare(actual: dict[str, dict[str, int]], recorded: dict[str, dict[str, int]], notices: bool) -> list[Finding]:
    findings: list[Finding] = []
    for package, counts in actual.items():
        for bucket in BUCKETS:
            old, new = recorded.get(package, {}).get(bucket, 0), counts[bucket]
            if new > old:
                message = f"{package}: {bucket} count rose from {old} to {new}"
                findings.append(Finding(code="RT001", severity=Severity.ERROR, path=RATCHET_FILE, message=message))
            elif new < old and notices:
                message = f"{package}: {bucket} count fell from {old} to {new}; run `ratchet --update`"
                findings.append(Finding(code="RT001", severity=Severity.NOTICE, path=RATCHET_FILE, message=message))
    return findings


def _raised(recorded: dict[str, dict[str, int]], base: dict[str, dict[str, int]], config: GateConfig) -> list[Finding]:
    findings: list[Finding] = []
    for package, counts in sorted(recorded.items()):
        for bucket, new in sorted(counts.items()):
            old = base.get(package, {}).get(bucket, 0)
            if new <= old:
                continue
            message = f"{RATCHET_FILE}: {package} {bucket} raised from {old} to {new} against the base commit"
            if config.mode is Mode.BOOTSTRAP:
                findings.append(awaiting_finding(config, "AW05", message, RATCHET_FILE))
            else:
                text = f"{message}; the owner must approve the file"
                findings.append(Finding(code="AW05", severity=Severity.ERROR, path=RATCHET_FILE, message=text))
    return findings


def check_ratchet(root: Path, policy_root: Path, config: GateConfig, clock: Clock, update: bool) -> list[Finding]:
    """Count the markers of every workspace member and judge them; with ``update`` lower the recorded counts.

    ``policy_root`` is the gate root; when it differs from ``root`` its ``.gate/ratchet.json`` is the base for AW05.
    ``update`` writes the file only when no count rose; it never raises a count.

    Raises:
        RatchetFileError: RT005 (exit 2).
        UsageError: a source file cannot be read or parsed, or the file cannot be written.
    """
    actual, findings = _scan(root, discover_members(root), clock.today())
    recorded = load_recorded(root / RATCHET_FILE)
    comparison = _compare(actual, recorded, notices=not update)
    findings += comparison
    if policy_root.resolve() != root.resolve():
        findings += _raised(recorded, load_recorded(policy_root / RATCHET_FILE), config)
    if update and not comparison:
        text = json.dumps({"version": 1, "counts": actual}, indent=2, sort_keys=True) + "\n"
        try:
            (root / RATCHET_FILE).parent.mkdir(parents=True, exist_ok=True)
            (root / RATCHET_FILE).write_text(text, encoding="utf-8", newline="\n")
        except OSError as error:
            raise UsageError(f"cannot write {RATCHET_FILE}: {error}") from error
    return findings


def step(ctx: StepContext) -> list[Finding]:
    """The ``ratchet`` step of ``check`` (workspace level)."""
    return check_ratchet(ctx.root, ctx.gate_root, load_gate_config(ctx.gate_root), SystemClock(), update=False)


def make_handler(clock: Clock | None = None) -> Callable[[argparse.Namespace], Status]:
    """Return the ``ratchet`` command handler; ``clock`` defaults to the system date.

    Raises:
        UsageError: from the handler, see :func:`check_ratchet`.
    """

    def handler(args: argparse.Namespace) -> Status:
        context: GateContext = args.gate_context
        findings = check_ratchet(context.root, context.policy_root, context.config, clock or SystemClock(), args.update)
        result = CommandResult(
            command="ratchet", mode=context.config.mode.value, steps=[StepResult(name="ratchet", findings=findings)]
        )
        result = context.with_findings(result)
        render(result, args.format, sys.stdout, os.environ)
        return result.status

    return handler
