"""Findings, step results and their output: text, JSON, GitHub Actions commands and the job summary (spec 4.2, 5).

Every run prints its mode first. The status of a step is ``fail`` if any error exists, else ``awaiting-owner`` if any
awaiting finding exists, else ``pass`` (``skipped`` when a reason is given).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import TextIO

from pydantic import BaseModel, ConfigDict, Field

from eng_dev_gate.results import Status, UsageError

AWAITING_TITLE = "awaiting owner"


class Severity(StrEnum):
    """Severity of a finding."""

    ERROR = "error"
    NOTICE = "notice"
    AWAITING = "awaiting"


class Finding(BaseModel):
    """One diagnostic: ``code`` (spec section 6), ``severity``, optional ``path`` and ``line``, ``message``."""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: Severity
    path: str | None = None
    line: int | None = Field(default=None, ge=1)
    message: str

    def text(self) -> str:
        """Return ``<code> <message>`` (the form used in the notice and the summary)."""
        return f"{self.code} {self.message}"


class StepResult(BaseModel):
    """Result of one check step; ``skipped_reason`` marks a step that does not apply."""

    name: str
    findings: list[Finding] = Field(default_factory=list)
    skipped_reason: str | None = Field(default=None, exclude=True)

    @property
    def status(self) -> Status:
        """Status by the rule of spec 4.2."""
        if self.skipped_reason is not None:
            return Status.SKIPPED
        severities = {f.severity for f in self.findings}
        if Severity.ERROR in severities:
            return Status.FAIL
        if Severity.AWAITING in severities:
            return Status.AWAITING_OWNER
        return Status.PASS


class CommandResult(BaseModel):
    """Result of a command: the schema of spec section 5 (``status`` is derived from the steps)."""

    command: str
    mode: str
    steps: list[StepResult] = Field(default_factory=list)

    @property
    def status(self) -> Status:
        """Worst step status; ``skipped`` only if every step is skipped (or there is none)."""
        statuses = {s.status for s in self.steps}
        for worst in (Status.FAIL, Status.AWAITING_OWNER, Status.PASS):
            if worst in statuses:
                return worst
        return Status.SKIPPED

    def to_json_data(self) -> dict[str, object]:
        """Return the JSON-ready structure ``{command, mode, status, steps:[{name, status, findings}]}``."""
        return {
            "command": self.command,
            "mode": self.mode,
            "status": self.status.value,
            "steps": [
                {
                    "name": s.name,
                    "status": s.status.value,
                    "findings": [f.model_dump(mode="json") for f in s.findings],
                }
                for s in self.steps
            ],
        }


def escape_data(text: str) -> str:
    """Escape ``%``, CR and LF in a workflow-command message, as the Actions runner requires."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(text: str) -> str:
    """Escape a workflow-command property value: as :func:`escape_data`, plus ``:`` and ``,``."""
    return escape_data(text).replace(":", "%3A").replace(",", "%2C")


def _annotation(finding: Finding) -> str | None:
    if finding.severity is Severity.AWAITING:
        return f"::notice title={AWAITING_TITLE}::{escape_data(finding.text())}"
    if finding.severity is Severity.ERROR:
        props = []
        if finding.path is not None:
            props.append(f"file={escape_property(finding.path)}")
            if finding.line is not None:
                props.append(f"line={finding.line}")
        props.append(f"title={escape_property(finding.code)}")
        return f"::error {','.join(props)}::{escape_data(finding.message)}"
    return None


def _location(finding: Finding) -> str:
    if finding.path is None:
        return ""
    return f"{finding.path}:{finding.line}: " if finding.line is not None else f"{finding.path}: "


def _text_lines(result: CommandResult) -> list[str]:
    lines = [f"mode: {result.mode}", f"{result.command}: {result.status.value}"]
    for step in result.steps:
        reason = f" ({step.skipped_reason})" if step.skipped_reason else ""
        lines.append(f"  {step.name}: {step.status.value}{reason}")
        lines.extend(f"    [{f.severity.value}] {_location(f)}{f.text()}" for f in step.findings)
    return lines


def _append_summary(path: Path, result: CommandResult) -> None:
    awaiting = [f for s in result.steps for f in s.findings if f.severity is Severity.AWAITING]
    if not awaiting:
        return
    body = "".join(f"- {AWAITING_TITLE}: {f.text()}\n" for f in awaiting)
    try:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
    except OSError as error:
        raise UsageError(f"cannot write the job summary {path}: {error}") from error


def render(result: CommandResult, output_format: str, out: TextIO, env: Mapping[str, str]) -> None:
    """Write the result to ``out`` and, in GitHub Actions, the annotations and the job summary.

    Args:
        result: the finished command.
        output_format: ``"text"`` or ``"json"``. JSON output is the schema of spec section 5 and nothing else.
        out: the text stream for standard output.
        env: the environment (``GITHUB_ACTIONS``, ``GITHUB_STEP_SUMMARY``).

    Raises:
        UsageError: the job summary file cannot be written.
    """
    in_actions = env.get("GITHUB_ACTIONS") == "true"
    if output_format == "json":
        out.write(json.dumps(result.to_json_data(), indent=2) + "\n")
    else:
        out.write("\n".join(_text_lines(result)) + "\n")
        if in_actions:
            for step in result.steps:
                out.writelines(f"{a}\n" for f in step.findings if (a := _annotation(f)) is not None)
    summary = env.get("GITHUB_STEP_SUMMARY")
    if in_actions and summary:
        _append_summary(Path(summary), result)
