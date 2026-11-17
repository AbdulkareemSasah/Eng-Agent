"""Tests of bootstrap mode and the root gate.yml (spec 4.4; AC3, AC4, AC5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eng_dev_gate.config import ConfigError, GateConfig, Mode, awaiting_finding, load_gate_config
from eng_dev_gate.report import Severity
from eng_dev_gate.results import ExitCode, GateError
from support.pullrequest import (
    PLAN_TASK,
    SPEC_PATH,
    base_checkout,
    gate_check,
    make_gate_repo,
    plan_text,
    spec_text,
    write_event,
)
from support.repo import Repo

IDENTITIES = "identities:\n  owner_login: owner\n  agent_logins: [agent]\n  reviewer_app: reviewer\n"
BODY = (
    "main_branch: main\n"
    "spec_globs: ['**/docs/specs/*.md']\nplan_globs: ['**/docs/plans/*.md']\n"
    "test_globs: ['**/tests/**']\ngenerated_globs: ['uv.lock']\nspike_globs: ['spikes/**']\n"
    "agents:\n  unmanaged_ok: ['design/**']\n"
    "limits:\n  diff_lines: 200\n  test_run_seconds: 600\n  max_file_bytes: 1048576\n"
    "  mutation_run_seconds: 7200\n"
)


def _write(root: Path, enabled: str, identities: str = "", body: str = BODY) -> Path:
    (root / ".gate").mkdir(parents=True, exist_ok=True)
    text = f"bootstrap:\n  enabled: {enabled}\n  gate_branch: build/v1\n{identities}{body}"
    (root / ".gate" / "gate.yml").write_text(text, encoding="utf-8")
    return root


def test_mode_only_from_gate_yml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC4: the mode is read from the gate root's gate.yml; environment variables cannot change it."""
    on = _write(tmp_path / "on", "true")
    off = _write(tmp_path / "off", "false", IDENTITIES)
    for name in ("ENG_GATE_BOOTSTRAP", "BOOTSTRAP", "BOOTSTRAP_ENABLED", "ENG_GATE_MODE", "CI", "GITHUB_ACTIONS"):
        monkeypatch.setenv(name, "false")
    assert load_gate_config(on).mode is Mode.BOOTSTRAP
    monkeypatch.setenv("ENG_GATE_BOOTSTRAP", "true")
    assert load_gate_config(off).mode is Mode.NORMAL
    assert load_gate_config(on).gate_branch == "build/v1"
    assert load_gate_config(off).gate_branch == "main"


@pytest.mark.parametrize(
    "text",
    [
        None,  # file missing
        "bootstrap: [",  # YAML syntax error
        "- a list\n",  # not a mapping
        "bootstrap:\n  enabled: 'yes'\n  gate_branch: build/v1\n" + BODY,  # string, not a bool
        "bootstrap:\n  enabled: true\n  gate_branch: build/v1\nsurprise: 1\n" + BODY,  # unknown key
    ],
)
def test_missing_or_invalid_file_is_cf007(tmp_path: Path, text: str | None) -> None:
    """AC4: a missing or invalid gate.yml is CF007 and exits 2."""
    if text is not None:
        (tmp_path / ".gate").mkdir()
        (tmp_path / ".gate" / "gate.yml").write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError) as caught:
        load_gate_config(tmp_path)
    assert caught.value.code == "CF007"
    assert caught.value.exit_code is ExitCode.USAGE


def test_normal_mode_never_awaits(tmp_path: Path) -> None:
    """AC2, AC3: bootstrap gives an awaiting finding for an AW condition; normal mode refuses to create one."""
    bootstrap = load_gate_config(_write(tmp_path / "on", "true"))
    finding = awaiting_finding(bootstrap, "AW02", "CODEOWNERS review needed", path=".gate/gate.yml")
    assert finding.severity is Severity.AWAITING
    assert finding.code == "AW02"
    assert finding.path == ".gate/gate.yml"
    normal = load_gate_config(_write(tmp_path / "off", "false", IDENTITIES))
    with pytest.raises(GateError):
        awaiting_finding(normal, "AW02", "CODEOWNERS review needed")


def test_bootstrap_off_needs_identities(tmp_path: Path) -> None:
    """AC5: bootstrap off with an empty or incomplete identities block is CF008 (exit 2); complete loads."""
    for index, identities in enumerate(
        [
            "",
            "identities:\n  owner_login: ''\n  agent_logins: []\n  reviewer_app: ''\n",
            "identities:\n  owner_login: owner\n  agent_logins: [agent]\n  reviewer_app: ''\n",
            "identities:\n  owner_login: owner\n  agent_logins: ['']\n  reviewer_app: reviewer\n",
        ]
    ):
        root = _write(tmp_path / f"case{index}", "false", identities)
        with pytest.raises(ConfigError) as caught:
            load_gate_config(root)
        assert caught.value.code == "CF008"
        assert caught.value.exit_code is ExitCode.USAGE
    config = load_gate_config(_write(tmp_path / "ok", "false", IDENTITIES))
    assert isinstance(config, GateConfig)
    assert config.identities.agent_logins == ["agent"]
    assert load_gate_config(_write(tmp_path / "boot", "true")).mode is Mode.BOOTSTRAP  # identities not needed


def test_normal_mode_never_awaits_in_gate_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC3: with bootstrap off gate-check verifies every condition that is AW01, AW02, AW03 or AW08 in bootstrap."""
    files = {".github/CODEOWNERS": "/pkg/src/protected/ @owner\n", "pkg/src/protected/a.py": "a\n"}
    plan = plan_text(files=("pkg/src/**", ".github/**"), status="draft")
    repo = Repo(tmp_path / "normal")
    base = make_gate_repo(repo, bootstrap=False, plan=plan, base_files={**files, SPEC_PATH: spec_text("draft")})
    repo.commit({"pkg/src/protected/a.py": "b\n"}, "feat: change")
    gate = base_checkout(repo, base, tmp_path / "gate-base", monkeypatch)
    event = write_event(repo, base, f"Closes #1\n{PLAN_TASK}\n", base_ref="main")
    result, errors = gate_check(repo, event, gate=gate)
    data = json.loads(result.out)
    assert {f["severity"] for step in data["steps"] for f in step["findings"]} == {"error"}
    assert (result.code, data["status"]) == (1, "fail")
    assert {"GC006", "GC015"} <= set(errors)
    assert "not implemented" not in errors["GC015"]  # verified through the port, not failed closed
