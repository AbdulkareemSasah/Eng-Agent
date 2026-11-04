"""Unit tests of the pull-request path of the ``licenses`` step with a scripted runner (B-086)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from eng_dev_gate import judged_metadata
from eng_dev_gate.checks import licenses
from eng_dev_gate.checks.registry import StepContext
from eng_dev_gate.results import EnvironmentFaultError
from eng_dev_gate.toolrun import ToolResult
from eng_dev_gate.workspace import discover_members
from support.repo import Repo
from support.toy import GATE_YML, make_workspace, member_pyproject


class ScriptedRunner:
    """Answers ``uv lock --check`` and the metadata run; the latter writes ``payload`` to the output path argument."""

    def __init__(self, payload: str = "[]", lock: int = 0, run: int = 0) -> None:
        self.payload, self.lock, self.run_code = payload, lock, run
        self.calls: list[list[str]] = []

    def run(self, argv: Sequence[str], cwd: Path) -> ToolResult:
        self.calls.append(list(argv))
        if "lock" in argv:
            return ToolResult(exit_code=self.lock, output="lock output")
        if self.run_code == 0:
            Path(argv[-1]).write_text(self.payload, encoding="utf-8")
        return ToolResult(exit_code=self.run_code, output="run output")


def _ctx(repo: Repo, gate_root: Path, runner: ScriptedRunner) -> StepContext:
    make_workspace(repo, ["a", "b"])
    pyproject = member_pyproject("a").replace("dependencies = []", 'dependencies = ["dep"]')
    repo.write({"pkgs/a/pyproject.toml": pyproject, ".gate/gate.yml": GATE_YML})
    member = next(m for m in discover_members(repo.root) if m.name == "a")
    (gate_root / ".gate").mkdir()
    (gate_root / ".gate" / "gate.yml").write_text(GATE_YML, encoding="utf-8")
    return StepContext(repo.root, gate_root, member, runner)


def _entry(name: str, **fields: object) -> dict[str, object]:
    return {"name": name, "expression": "", "license": "", "classifiers": [], "requires": [], **fields}


def test_command_runs_the_base_file_in_the_judged_environment(repo: Repo, tmp_path: Path) -> None:
    runner = ScriptedRunner(json.dumps([_entry("dep", expression="MIT")]))
    assert licenses.licenses(_ctx(repo, tmp_path, runner)) == []
    command = runner.calls[-1]
    assert command[:3] == ["uv", "run", "--quiet"]
    assert command[command.index("--project") + 1] == str(repo.root)
    assert {"--locked", "--all-packages"} <= set(command)
    assert command[command.index("python") + 1 :][:2] == ["-I", str(Path(judged_metadata.__file__).resolve())]


def test_lock_check_failure_is_st001(repo: Repo, tmp_path: Path) -> None:
    runner = ScriptedRunner(lock=2)
    (finding,) = licenses.licenses(_ctx(repo, tmp_path, runner))
    assert (finding.code, finding.path) == ("ST001", "pkgs/a")
    assert finding.message.startswith("licenses: uv.lock of the judged tree is not up to date")
    assert len(runner.calls) == 1


def test_missing_uv_is_an_environment_fault(repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(licenses, "_uv_available", lambda: False)
    with pytest.raises(EnvironmentFaultError, match="uv is not available"):
        licenses.licenses(_ctx(repo, tmp_path, ScriptedRunner()))


def test_failed_metadata_run_is_an_environment_fault(repo: Repo, tmp_path: Path) -> None:
    with pytest.raises(EnvironmentFaultError, match="exited 1"):
        licenses.licenses(_ctx(repo, tmp_path, ScriptedRunner(run=1)))


@pytest.mark.parametrize("payload", ["not json", '{"name": "dep"}', '[{"name": 1}]'])
def test_unusable_metadata_is_an_environment_fault(repo: Repo, tmp_path: Path, payload: str) -> None:
    with pytest.raises(EnvironmentFaultError, match="unusable metadata"):
        licenses.licenses(_ctx(repo, tmp_path, ScriptedRunner(payload)))


def test_requires_of_the_judged_environment_extend_the_closure(repo: Repo, tmp_path: Path) -> None:
    payload = json.dumps(
        [_entry("dep", expression="MIT", requires=["deep"]), _entry("deep", expression="GPL-3.0-only")]
    )
    findings = licenses.licenses(_ctx(repo, tmp_path, ScriptedRunner(payload)))
    assert [(f.code, f.message.split(":")[0]) for f in findings] == [("LC001", "deep")]
