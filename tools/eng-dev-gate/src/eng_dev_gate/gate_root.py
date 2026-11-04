"""The gate of the base commit: gate root, provenance and head-run rules (spec 4.16, AC65 to AC67).

In pull-request context a judging command runs the code and the policy of the base commit against the head tree.
Every check reads its policy through :class:`GateContext`, never from the working tree directly.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import eng_dev_gate
from eng_dev_gate.config import ConfigError, GateConfig, Mode, awaiting_finding, load_gate_config
from eng_dev_gate.config.gate_config import parse_gate_config
from eng_dev_gate.event import event_path, read_event
from eng_dev_gate.gitio import GitError, PathNotFoundError, SubprocessGit
from eng_dev_gate.report import CommandResult, Finding, StepResult
from eng_dev_gate.results import ExitCode, GateError, UsageError

PACKAGE_SRC = "tools/eng-dev-gate/src"
ACTIONS_DIR = "tools/eng-dev-gate/actions"
GATE_YML = ".gate/gate.yml"

# Command to the CI job that runs it (spec 4.14). The steps of ``check`` run in the ``gate`` job.
# ``windows-tests`` (the ``windows`` job, head variant) and ``agents render|keys`` do not judge a pull request.
JOBS: Mapping[str, str] = {
    **dict.fromkeys(("check", "forbidden", "imports", "licenses", "ratchet", "workflows", "mutation"), "gate"),
    "gate-check": "gate-check", "risk-floor": "risk-floor", "test-first": "test-first", "review": "ci-review",
    "secrets": "security", "packages": "build",
}  # fmt: skip


class ProvenanceError(GateError):
    """CF009: the judging gate is not the gate of the base commit (exit 1)."""

    exit_code = ExitCode.FAILED

    def __init__(self, message: str) -> None:
        super().__init__(f"CF009 {message}")


@dataclass(frozen=True)
class GateContext:
    """What a judging command reads: the tree under check, where its policy comes from, and notices.

    ``root`` is the tree under check (the head); ``policy_root`` is the gate root (the base checkout) or, without one,
    ``root``. ``config`` is the ``gate.yml`` of the base commit in pull-request context. ``findings`` holds AW09 for a
    head run; a handler adds them to its result with :meth:`with_findings`.
    """

    root: Path
    policy_root: Path
    config: GateConfig
    findings: tuple[Finding, ...] = ()

    def read_policy(self, relative: str) -> str:
        """Read a policy file (``.gate/forbidden.yml``, the risk map, a prompt) below the policy root.

        Raises:
            UsageError: the path leaves the policy root or the file cannot be read.
        """
        base = self.policy_root.resolve()
        target = (base / relative).resolve()
        if not target.is_relative_to(base):
            raise UsageError(f"policy path {relative!r} leaves {self.policy_root}")
        try:
            return target.read_text(encoding="utf-8")
        except OSError as error:
            raise UsageError(f"cannot read policy file {target}: {error}") from error

    def with_findings(self, result: CommandResult) -> CommandResult:
        """Return ``result`` with a ``gate-root`` step holding this context's findings (unchanged if there are none)."""
        if not self.findings:
            return result
        return result.model_copy(
            update={"steps": [*result.steps, StepResult(name="gate-root", findings=list(self.findings))]}
        )


def running_package() -> Path:
    """Return the folder of the running ``eng_dev_gate`` package (a seam for tests)."""
    return Path(eng_dev_gate.__file__).resolve().parent


def job_for(args: argparse.Namespace) -> str | None:
    """Return the CI job of the command in ``args``, or None when the command does not judge a pull request."""
    if args.command == "agents":
        return "agents-drift" if getattr(args, "agents_command", None) == "drift" else None
    return JOBS.get(args.command)


def _verify_base_checkout(gate_root: Path, base_sha: str) -> None:
    try:
        checked_out = SubprocessGit(gate_root).rev_parse("HEAD")
    except GitError as error:
        raise ProvenanceError(f"gate root {gate_root} is not a git checkout: {error}") from error
    if checked_out != base_sha.lower():
        raise ProvenanceError(f"gate root {gate_root} is at {checked_out}, not at the base commit {base_sha}")
    if not running_package().is_relative_to((gate_root / PACKAGE_SRC).resolve()):
        raise ProvenanceError(f"the running package {running_package()} is not inside {gate_root / PACKAGE_SRC}")


def _head_run(root: Path, job: str, base_sha: str) -> GateContext:
    git = SubprocessGit(root)
    try:
        config = parse_gate_config(git.show(base_sha, GATE_YML), f"{base_sha}:{GATE_YML}")
    except PathNotFoundError as error:
        raise ConfigError("CF007", f"the base commit {base_sha} has no {GATE_YML}") from error
    try:
        git.show(base_sha, f"{ACTIONS_DIR}/{job}/action.yml")
    except PathNotFoundError:  # the base has no action for this job: the first pull request of the job
        if config.mode is Mode.NORMAL:
            raise ProvenanceError(f"head run of job {job!r} with bootstrap off") from None
        message = f"job {job!r} ran from the head tree because the base commit has no action for it"
        return GateContext(root, root, config, (awaiting_finding(config, "AW09", message),))
    raise ProvenanceError(f"head run of job {job!r}, but the base commit has its action: use --gate-root")


def resolve(root: Path, gate_root: Path | None, job: str, event_file: Path | None) -> GateContext:
    """Resolve the policy source and check the provenance of the judging gate.

    Args:
        root: the tree under check.
        gate_root: the ``--gate-root`` checkout of the base commit, if given.
        job: the CI job that runs the command (:func:`job_for`).
        event_file: the GitHub event file, if any; push events and no event have no provenance rule.

    Raises:
        ProvenanceError: CF009, see spec 4.16.
        ConfigError: CF007 or CF008 from the ``gate.yml`` that gives the mode.
        UsageError: the event file is unreadable.
        GitError: git failed in a head run.
    """
    event = read_event(event_file) if event_file is not None else None
    pull_request = event.pull_request if event is not None else None
    if pull_request is None:
        policy_root = gate_root or root
        return GateContext(root, policy_root, load_gate_config(policy_root))
    if gate_root is None:
        return _head_run(root, job, pull_request.base_sha)
    _verify_base_checkout(gate_root, pull_request.base_sha)
    return GateContext(root, gate_root, load_gate_config(gate_root))


def _tree_root(start: Path) -> Path:
    """Return ``start`` or its nearest ancestor that holds ``.gate/gate.yml``; ``start`` if none does."""
    resolved = start.resolve()
    return next((d for d in (resolved, *resolved.parents) if (d / GATE_YML).is_file()), start)


def resolve_for(args: argparse.Namespace, env: Mapping[str, str] | None = None) -> GateContext | None:
    """Resolve the context of the command in ``args``; None when the command does not judge a pull request."""
    job = job_for(args)
    if job is None:
        return None
    chosen = Path(args.gate_root) if args.gate_root else None
    return resolve(
        _tree_root(Path(args.root)), chosen, job, event_path(getattr(args, "event", None), env or os.environ)
    )
