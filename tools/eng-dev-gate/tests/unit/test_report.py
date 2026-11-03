"""Tests of result models and output (spec 4.2, 5; AC1, AC2)."""

from __future__ import annotations

import io
import json
from pathlib import Path

from eng_dev_gate.report import (
    CommandResult,
    Finding,
    Severity,
    StepResult,
    escape_data,
    escape_property,
    render,
)
from eng_dev_gate.results import Status
from hypothesis import given, settings
from hypothesis import strategies as st


def _finding(severity: Severity, code: str = "GC008", path: str | None = "a/b.py", line: int | None = 3) -> Finding:
    return Finding(code=code, severity=severity, path=path, line=line, message="msg")


def test_step_status_rules() -> None:
    """4.2: fail if any error, else awaiting-owner if any awaiting, else pass; skipped keeps its reason."""
    assert StepResult(name="s", findings=[]).status is Status.PASS
    assert StepResult(name="s", findings=[_finding(Severity.NOTICE)]).status is Status.PASS
    both = [_finding(Severity.AWAITING), _finding(Severity.ERROR)]
    assert StepResult(name="s", findings=both).status is Status.FAIL
    assert StepResult(name="s", findings=[_finding(Severity.AWAITING)]).status is Status.AWAITING_OWNER
    assert StepResult(name="s", skipped_reason="not applicable").status is Status.SKIPPED


def test_command_status_aggregates_steps() -> None:
    """The command status is the worst step status; all skipped is skipped."""
    ok = StepResult(name="a")
    bad = StepResult(name="b", findings=[_finding(Severity.ERROR)])
    wait = StepResult(name="c", findings=[_finding(Severity.AWAITING)])
    skip = StepResult(name="d", skipped_reason="x")
    assert CommandResult(command="check", mode="normal", steps=[ok, wait, bad]).status is Status.FAIL
    assert CommandResult(command="check", mode="normal", steps=[ok, wait]).status is Status.AWAITING_OWNER
    assert CommandResult(command="check", mode="normal", steps=[ok, skip]).status is Status.PASS
    assert CommandResult(command="check", mode="normal", steps=[skip]).status is Status.SKIPPED


def test_json_result_schema() -> None:
    """AC1 / spec 5: --format json prints {command, mode, status, steps:[{name, status, findings:[...]}]}."""
    result = CommandResult(
        command="gate-check",
        mode="bootstrap",
        steps=[StepResult(name="scope", findings=[_finding(Severity.ERROR)])],
    )
    out = io.StringIO()
    render(result, "json", out, env={})
    data = json.loads(out.getvalue())
    assert data == {
        "command": "gate-check",
        "mode": "bootstrap",
        "status": "fail",
        "steps": [
            {
                "name": "scope",
                "status": "fail",
                "findings": [{"code": "GC008", "severity": "error", "path": "a/b.py", "line": 3, "message": "msg"}],
            }
        ],
    }


def test_text_output_prints_mode_first() -> None:
    """4.2: every run prints its mode first."""
    out = io.StringIO()
    render(CommandResult(command="check", mode="normal", steps=[StepResult(name="lint")]), "text", out, env={})
    assert out.getvalue().splitlines()[0] == "mode: normal"
    assert "lint" in out.getvalue()


def test_awaiting_owner_notice_and_summary(tmp_path: Path) -> None:
    """AC2: bootstrap awaiting owner prints a ::notice titled awaiting owner, appends it to the summary, status passes."""
    summary = tmp_path / "summary.md"
    finding = Finding(code="AW02", severity=Severity.AWAITING, path=".gate/gate.yml", line=None, message="needs owner")
    result = CommandResult(
        command="gate-check", mode="bootstrap", steps=[StepResult(name="protected", findings=[finding])]
    )
    out = io.StringIO()
    render(result, "text", out, env={"GITHUB_ACTIONS": "true", "GITHUB_STEP_SUMMARY": str(summary)})
    assert "::notice title=awaiting owner::AW02 needs owner" in out.getvalue().splitlines()
    assert "AW02 needs owner" in summary.read_text(encoding="utf-8")
    assert result.status is Status.AWAITING_OWNER


def test_error_annotation_and_no_actions_outside_actions() -> None:
    """4.2: errors become ::error file=,line=,title=<code>:: only in GitHub Actions."""
    result = CommandResult(
        command="c", mode="normal", steps=[StepResult(name="s", findings=[_finding(Severity.ERROR)])]
    )
    on, off = io.StringIO(), io.StringIO()
    render(result, "text", on, env={"GITHUB_ACTIONS": "true"})
    render(result, "text", off, env={})
    assert "::error file=a/b.py,line=3,title=GC008::msg" in on.getvalue().splitlines()
    assert "::error" not in off.getvalue()


def test_escaping_examples() -> None:
    """The runner requires % CR LF escaped in data, and also : and , in properties."""
    assert escape_data("a%b\r\nc") == "a%25b%0D%0Ac"
    assert escape_property("a:b,c%") == "a%3Ab%2Cc%25"


@settings(derandomize=True, max_examples=100)
@given(st.text())
def test_escaped_data_has_no_raw_specials(text: str) -> None:
    """Property: escaped data never holds a raw CR or LF, and every % starts an escape."""
    escaped = escape_data(text)
    assert "\r" not in escaped
    assert "\n" not in escaped
    assert escaped.replace("%25", "").replace("%0D", "").replace("%0A", "").count("%") == 0
    assert escape_property(text).count(",") == 0
    assert escape_property(text).count(":") == 0
