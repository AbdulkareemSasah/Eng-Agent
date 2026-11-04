"""The ``check`` orchestrator: select members and steps, run them in spec order, report every step (spec 4.12, AC47)."""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path

from eng_dev_gate.checks.registry import STEP_ORDER, STEPS, Step, StepContext
from eng_dev_gate.config import load_gate_config
from eng_dev_gate.report import CommandResult, StepResult, render
from eng_dev_gate.results import Status, UsageError
from eng_dev_gate.toolrun import SubprocessToolRunner, ToolRunner
from eng_dev_gate.workspace import Member, discover_members

Handler = Callable[[argparse.Namespace], Status]  # same shape as cli.Handler; cli imports this module


def _is_workspace_root(directory: Path) -> bool:
    try:
        text = (directory / "pyproject.toml").read_text(encoding="utf-8")
        return "workspace" in tomllib.loads(text).get("tool", {}).get("uv", {})
    except OSError, tomllib.TOMLDecodeError:
        return False


def _workspace_root(start: Path) -> Path:
    """Return ``start`` or its nearest ancestor that holds ``[tool.uv.workspace]``."""
    start = start.resolve()
    for directory in (start, *start.parents):
        if _is_workspace_root(directory):
            return directory
    raise UsageError(f"{start} is not inside a uv workspace")


def _select_members(members: list[Member], start: Path, root: Path, args: argparse.Namespace) -> list[Member]:
    if args.package:
        chosen = [m for m in members if m.name == args.package]
        if not chosen:
            raise UsageError(f"no workspace member named {args.package!r}")
        return chosen
    if args.all or start == root:
        return members
    inside = [m for m in members if start == m.directory.resolve() or m.directory.resolve() in start.parents]
    if not inside:
        raise UsageError(f"{start} is not inside a workspace member; use --package or --all")
    return inside


def _names(values: Sequence[str]) -> set[str]:
    names = {n for value in values for n in value.split(",") if n}
    unknown = names - set(STEP_ORDER)
    if unknown:
        raise UsageError(f"unknown step(s): {', '.join(sorted(unknown))}")
    return names


def _selected_steps(args: argparse.Namespace) -> list[Step]:
    only, skip = _names(args.only), _names(args.skip)
    return [s for s in STEPS if (not only or s.name in only) and s.name not in skip]


def run_check(
    steps: Sequence[Step], root: Path, gate_root: Path, members: list[Member], runner: ToolRunner, fail_fast: bool
) -> list[StepResult]:
    """Run ``steps`` in order and return one result per step (per member for package steps).

    A failing step does not stop the others unless ``fail_fast``. Package step names carry ``:<member>`` when more
    than one member is selected.

    Raises:
        EnvironmentFaultError: a tool is missing, crashed or timed out (exit 3).
    """
    results: list[StepResult] = []
    for step in steps:
        targets: list[Member | None] = [None] if step.level == "root" else list(members)
        for member in targets:
            name = f"{step.name}:{member.name}" if member and len(members) > 1 else step.name
            result = StepResult(name=name, findings=step.run(StepContext(root, gate_root, member, runner)))
            results.append(result)
            if fail_fast and result.status is Status.FAIL:
                return results
    return results


def make_handler(runner: ToolRunner | None = None) -> Handler:
    """Return the ``check`` command handler; ``runner`` defaults to the subprocess adapter.

    The handler prints the result (text or JSON, mode first) and returns the worst step status.

    Raises:
        UsageError: unknown step or package, no workspace, bad gate configuration (exit 2).
    """
    tools = runner or SubprocessToolRunner()

    def handler(args: argparse.Namespace) -> Status:
        start = Path(args.root).resolve()
        root = _workspace_root(start)
        gate_root = Path(args.gate_root).resolve() if args.gate_root else root
        mode = load_gate_config(gate_root).mode
        members = _select_members(discover_members(root), start, root, args)
        steps = run_check(_selected_steps(args), root, gate_root, members, tools, args.fail_fast)
        result = CommandResult(command="check", mode=mode.value, steps=steps)
        render(result, args.format, sys.stdout, os.environ)
        return result.status

    return handler
