"""Unit tests of the policy reader and the command-to-job table (spec 4.14, 4.16)."""

from __future__ import annotations

import argparse
from pathlib import Path

import eng_dev_gate
import pytest
from eng_dev_gate import gate_root
from eng_dev_gate.config.gate_config import parse_gate_config
from eng_dev_gate.gate_root import GateContext, job_for
from eng_dev_gate.report import CommandResult, Finding, Severity, StepResult
from eng_dev_gate.results import ExitCode, UsageError

GATE_YML = (
    "bootstrap: {enabled: true, gate_branch: build/v1}\nmain_branch: main\n"
    "spec_globs: []\nplan_globs: []\ntest_globs: []\ngenerated_globs: []\nspike_globs: []\n"
    "limits: {diff_lines: 200, test_run_seconds: 600, max_file_bytes: 1048576"
    ", mutation_run_seconds: 7200}\n"
)


def _context(tmp_path: Path) -> GateContext:
    (tmp_path / "policy").mkdir()
    (tmp_path / "policy" / "a.yml").write_text("a\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside\n", encoding="utf-8")
    return GateContext(tmp_path, tmp_path / "policy", parse_gate_config(GATE_YML, "test"))


def test_read_policy_stays_inside_the_policy_root(tmp_path: Path) -> None:
    context = _context(tmp_path)
    assert context.read_policy("a.yml") == "a\n"
    for bad in ("../secret.txt", str(tmp_path / "secret.txt"), "missing.yml"):
        with pytest.raises(UsageError):
            context.read_policy(bad)


def test_with_findings_adds_one_step_only_when_there_are_findings(tmp_path: Path) -> None:
    context = _context(tmp_path)
    result = CommandResult(command="x", mode="bootstrap", steps=[StepResult(name="s")])
    assert context.with_findings(result) == result
    finding = Finding(code="AW09", severity=Severity.AWAITING, message="m")
    judged = GateContext(context.root, context.policy_root, context.config, (finding,)).with_findings(result)
    assert [s.name for s in judged.steps] == ["s", "gate-root"]
    assert judged.steps[1].findings == [finding]


@pytest.mark.parametrize(
    ("argv", "job"),
    [
        (["check"], "gate"), (["forbidden"], "gate"), (["workflows"], "gate"), (["gate-check"], "gate-check"),
        (["risk-floor"], "risk-floor"), (["test-first"], "test-first"), (["review"], "ci-review"),
        (["secrets"], "security"), (["packages"], "build"), (["agents", "drift"], "agents-drift"),
        (["agents", "render"], None), (["agents", "keys"], None), (["windows-tests"], None),
    ],
)  # fmt: skip
def test_job_for(argv: list[str], job: str | None) -> None:
    """Spec 4.14: every judging command maps to its job; windows-tests and agents render and keys are not judging."""
    args = argparse.Namespace(command=argv[0], agents_command=argv[1] if len(argv) > 1 else None)
    assert job_for(args) == job


def test_provenance_error_is_cf009_and_exit_1() -> None:
    error = gate_root.ProvenanceError("running package outside the gate root")
    assert str(error).startswith("CF009 ")
    assert error.exit_code is ExitCode.FAILED


def test_running_package_is_the_imported_package() -> None:
    assert gate_root.running_package() == Path(eng_dev_gate.__file__).resolve().parent


def test_resolve_for_reads_the_policy_of_the_workspace_root_from_a_subdirectory(tmp_path: Path) -> None:
    """`eng-gate --root <member> check` judges the workspace: the policy is the workspace root's gate.yml, not CF007."""
    (tmp_path / ".gate").mkdir()
    (tmp_path / ".gate" / "gate.yml").write_text(GATE_YML, encoding="utf-8")
    member = tmp_path / "pkgs" / "a"
    member.mkdir(parents=True)
    args = argparse.Namespace(command="check", agents_command=None, gate_root=None, root=str(member), event=None)
    context = gate_root.resolve_for(args, {})
    assert context is not None
    assert context.root == tmp_path
    assert context.policy_root == tmp_path
    assert context.config.mode.value == "bootstrap"
