"""The ``secrets`` command and the ``secrets`` step of ``check`` (spec 4.11, AC46).

A small pattern scan of added lines (a commit range) or of tracked text files (the tree). A finding names the rule, the
path, the line and a fingerprint (first 12 hexadecimal digits of the SHA-256 of the matched text); the matched text is
never printed, logged or put into a finding.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from eng_dev_gate import report
from eng_dev_gate.config import GateConfig, load_gate_config
from eng_dev_gate.report import CommandResult, Finding, Severity, StepResult
from eng_dev_gate.results import EnvironmentFaultError, Status, UsageError
from eng_dev_gate.toolrun import SubprocessToolRunner, ToolRunner

if TYPE_CHECKING:
    from eng_dev_gate.checks.registry import StepContext

FINGERPRINT_DIGITS = 12  # spec 4.11
COMMIT_MARK = "@@commit "
_GIT = ["git", "-c", "core.quotepath=off"]
_NAME = r"[A-Za-z0-9._-]+"  # a real user name; a placeholder such as <name> does not match
RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (rule, re.compile(pattern, re.IGNORECASE if rule == "credential-assignment" else 0))
    for rule, pattern in (
        ("github-token", r"ghp_[A-Za-z0-9]{36}"),
        ("github-fine-grained-token", r"github_pat_[A-Za-z0-9_]+"),
        ("aws-access-key-id", r"AKIA[0-9A-Z]{16}"),
        ("google-api-key", r"AIza[0-9A-Za-z_-]{35}"),
        ("slack-token", r"xox[abprs]-[A-Za-z0-9-]+"),
        ("anthropic-key", r"sk-ant-[A-Za-z0-9_-]+"),
        ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        ("credential-assignment", r"\w*(?:password|secret|token|api_key)\w*[\"']?\s*[:=]\s*([\"'])[^\"'\r\n]{8,}\1"),
        ("personal-path", rf"[A-Za-z]:\\Users\\{_NAME}|/home/{_NAME}/|/Users/{_NAME}/"),
    )
)  # fmt: skip
_HUNK = re.compile(r"^(@@+) ((?:-\d+(?:,\d+)? )+)\+(\d+)(?:,(\d+))? \1")  # "@@" per file, "@@@" and more per merge
_BINARY = re.compile(r"^Binary files .* and b/(.+) differ$")


def fingerprint(text: str) -> str:
    """Return the first 12 hexadecimal digits of the SHA-256 of ``text``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:FINGERPRINT_DIGITS]


def _clean_path(raw: str) -> str:
    raw = raw.rstrip("\t")  # git adds a tab after a name that has a space
    return raw.removeprefix('"').removesuffix('"').removeprefix("b/")


def _parse_log(log: str) -> tuple[dict[tuple[str, str], list[tuple[int, str]]], set[tuple[str, str]]]:
    """Parse ``git log -p -U0 --cc`` into added lines per (commit, path), and the (commit, path) pairs of binary files.

    The hunk header counts decide where a single-parent hunk ends, so an added line that reads like a header is still
    data. In a merge's combined diff each line has one marker column per parent: a line is in parent i unless column i
    is ``+``, and in the result unless some column is ``-``. Git's counts are unreliable there at ``-U0``, so a combined
    hunk lasts while lines keep the shape of N marker characters from `` +-``; headers never do.
    """
    added: dict[tuple[str, str], list[tuple[int, str]]] = {}
    binary: set[tuple[str, str]] = set()
    commit = path = ""
    old_left: list[int] = []
    new_left = line = 0
    combined = False
    for raw in log.split("\n"):
        marks = raw[: len(old_left)]
        in_hunk = combined or bool(new_left) or any(old_left)
        if in_hunk and not raw.startswith("\\") and (len(marks) < len(old_left) or set(marks) - set(" +-")):
            old_left, new_left, combined = [], 0, False  # not a hunk line: read this line as a header
            in_hunk = False
        if in_hunk and not raw.startswith("\\"):  # "\ No newline at end of file" is not a line
            old_left = [n if mark == "+" else n - 1 for n, mark in zip(old_left, marks, strict=True)]
            if "-" not in marks:  # the line is in the result
                if "+" in marks:
                    added.setdefault((commit, path), []).append((line, raw[len(old_left) :]))
                new_left -= 1
                line += 1
        elif raw.startswith(COMMIT_MARK):
            commit = raw.removeprefix(COMMIT_MARK)
        elif raw.startswith("+++ "):
            path = _clean_path(raw[4:])
        elif match := _BINARY.match(raw):
            binary.add((commit, _clean_path(match.group(1))))
        elif match := _HUNK.match(raw):
            old_left = [
                1 if c == "" else int(c) for c in re.findall(r"-\d+(?:,(\d*))?", match.group(2))
            ]  # no count: one
            line = int(match.group(3))
            new_left = 1 if match.group(4) is None else int(match.group(4))
            combined = len(old_left) > 1
    return added, binary


def _hits(text: str, allowed: set[tuple[str, str, str]], path: str) -> list[tuple[str, str]]:
    """Return ``(rule, fingerprint)`` for every match in ``text`` that the allowlist does not cover."""
    found = [(rule, fingerprint(m.group(0))) for rule, pattern in RULES for m in pattern.finditer(text)]
    return [(rule, fp) for rule, fp in found if (rule, path, fp) not in allowed]


def _finding(rule: str, fp: str, path: str, line: int, commit: str = "") -> Finding:
    where = f" in commit {commit[:FINGERPRINT_DIGITS]}" if commit else ""
    return Finding(
        code="SC001", severity=Severity.ERROR, path=path, line=line, message=f"{rule} fingerprint {fp}{where}"
    )


def _skipped(path: str, reason: str) -> Finding:
    return Finding(code="SC002", severity=Severity.NOTICE, path=path, message=f"file skipped: {reason}")


def _git(runner: ToolRunner, root: Path, *args: str) -> str:
    done = runner.run([*_GIT, *args], root)
    if done.exit_code != 0:
        raise EnvironmentFaultError(f"git {args[0]} exited {done.exit_code}: {done.output[:300]}")
    return done.output


def scan_range(runner: ToolRunner, root: Path, config: GateConfig, revisions: str) -> list[Finding]:
    """Scan the added lines of every commit in ``revisions`` (``<base>..<head>``).

    Raises:
        UsageError: ``revisions`` is not of the form ``a..b`` or starts with ``-``.
        EnvironmentFaultError: git failed (for example an unknown revision).
    """
    if ".." not in revisions or revisions.startswith("-"):
        raise UsageError(f"--range expects <base>..<head>, got {revisions!r}")
    log = _git(runner, root, "log", "-p", "-U0", "--cc", "--no-color", "--no-ext-diff",
               f"--format={COMMIT_MARK}%H", revisions, "--")  # fmt: skip
    allowed = {(a.rule, a.path, a.fingerprint) for a in config.secrets.allow}
    added, binary = _parse_log(log)
    findings = [_skipped(path, "binary") for _, path in sorted(binary)]
    for (commit, path), lines in added.items():
        if sum(len(text) + 1 for _, text in lines) > config.limits.max_file_bytes:
            findings.append(_skipped(path, "larger than limits.max_file_bytes"))
            continue
        findings += [
            _finding(rule, fp, path, number, commit)
            for number, text in lines
            for rule, fp in _hits(text, allowed, path)
        ]
    return findings


def scan_tree(runner: ToolRunner, root: Path, config: GateConfig) -> list[Finding]:
    """Scan every tracked regular text file at the checkout; symlinks and submodules are not followed.

    Raises:
        EnvironmentFaultError: git failed.
    """
    allowed = {(a.rule, a.path, a.fingerprint) for a in config.secrets.allow}
    findings: list[Finding] = []
    for name in sorted(n for n in _git(runner, root, "ls-files", "-z").split("\0") if n):
        target = root / name
        if target.is_symlink() or not target.is_file():
            continue
        try:
            if target.stat().st_size > config.limits.max_file_bytes:
                findings.append(_skipped(name, "larger than limits.max_file_bytes"))
                continue
            data = target.read_bytes()
        except OSError as error:
            raise EnvironmentFaultError(f"cannot read {name}: {error}") from error
        if b"\0" in data:
            findings.append(_skipped(name, "binary"))
            continue
        for number, text in enumerate(data.decode("utf-8", errors="replace").split("\n"), start=1):
            findings += [_finding(rule, fp, name, number) for rule, fp in _hits(text, allowed, name)]
    return findings


def step(ctx: StepContext) -> list[Finding]:
    """Step 9 of ``check``: scan ``<merge base with origin/<gate_branch>>..HEAD``.

    When ``origin/<gate_branch>`` does not exist (no remote, as in a fresh local clone) the whole tree is scanned
    instead, which is a superset of any range.

    Raises:
        EnvironmentFaultError: git failed, or the branches share no history.
    """
    config = load_gate_config(ctx.gate_root)
    ref = f"origin/{config.gate_branch}"
    if ctx.runner.run([*_GIT, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], ctx.root).exit_code != 0:
        return scan_tree(ctx.runner, ctx.root, config)
    base = _git(ctx.runner, ctx.root, "merge-base", ref, "HEAD").strip()
    return scan_range(ctx.runner, ctx.root, config, f"{base}..HEAD")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add ``--range`` and ``--tree`` (exactly one is required)."""
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--range", default=None, help="scan the added lines of <base>..<head>")
    mode.add_argument("--tree", action="store_true", help="scan every tracked text file")


def handle(args: argparse.Namespace) -> Status:
    """Run ``secrets --range|--tree`` and print the result; the policy comes from the gate context (spec 4.16)."""
    context = args.gate_context
    runner = SubprocessToolRunner()
    if args.range is not None:
        findings = scan_range(runner, context.root, context.config, args.range)
    else:
        findings = scan_tree(runner, context.root, context.config)
    result = context.with_findings(
        CommandResult(
            command="secrets", mode=context.config.mode.value, steps=[StepResult(name="secrets", findings=findings)]
        )
    )
    report.render(result, args.format, sys.stdout, os.environ)
    status: Status = result.status
    return status
