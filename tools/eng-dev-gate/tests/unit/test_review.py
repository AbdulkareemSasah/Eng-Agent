"""The ``review`` command and the pinned reviewer prompts (spec 4.15, AC61)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from eng_dev_gate import cli
from eng_dev_gate.checks import review

ROOT = Path(__file__).resolve().parents[4]
PROMPTS = "tools/eng-dev-gate/src/eng_dev_gate/prompts"
IDENTITIES = "identities: {owner_login: owner, agent_logins: [agent], reviewer_app: reviewer}\n"


def _gate_yml(*, bootstrap: bool) -> str:
    return (
        f"bootstrap: {{enabled: {str(bootstrap).lower()}, gate_branch: build/v1}}\nmain_branch: main\n"
        + IDENTITIES
        + "spec_globs: []\nplan_globs: []\ntest_globs: []\ngenerated_globs: []\nspike_globs: []\n"
        "limits: {diff_lines: 200, test_run_seconds: 600, max_file_bytes: 1048576"
        ", mutation_run_seconds: 7200}\n"
    )


def _tree(tmp_path: Path, *, bootstrap: bool = True) -> Path:
    """A policy tree holding the shipped prompts and a gate.yml in the chosen mode."""
    (tmp_path / ".gate").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".gate" / "gate.yml").write_text(_gate_yml(bootstrap=bootstrap), encoding="utf-8")
    shutil.copytree(ROOT / PROMPTS, tmp_path / PROMPTS, ignore=shutil.ignore_patterns("__pycache__"))
    return tmp_path


def _run(tree: Path, *args: str) -> int:
    return cli.main(["--root", str(tree), "--format", "json", "review", *args], {"review": review.handle})


def _codes(capsys: pytest.CaptureFixture[str]) -> list[str]:
    result = json.loads(capsys.readouterr().out)
    return [f["code"] for step in result["steps"] for f in step["findings"]]


@pytest.fixture(autouse=True)
def _no_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)


def test_prompt_hashes_and_modes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """AC61: hashes match; bootstrap reports AW04 and exits 0; normal mode without providers fails closed."""
    bootstrap = _tree(tmp_path / "b", bootstrap=True)
    assert _run(bootstrap, "--check-prompts") == 0
    assert _codes(capsys) == []
    assert _run(bootstrap) == 0
    assert _codes(capsys) == ["AW04"]
    normal = _tree(tmp_path / "n", bootstrap=False)
    assert _run(normal, "--check-prompts") == 0
    assert _codes(capsys) == []
    assert _run(normal) == 1
    assert _codes(capsys) == ["RV002"]


def test_manifest_matches_the_shipped_prompts() -> None:
    manifest = json.loads((ROOT / PROMPTS / "manifest.json").read_text(encoding="utf-8"))
    on_disk = sorted(p.name for p in (ROOT / PROMPTS).glob("*.md"))
    assert sorted(manifest) == on_disk == sorted(review.PROMPTS)
    for name, digest in manifest.items():
        assert digest == hashlib.sha256((ROOT / PROMPTS / name).read_bytes()).hexdigest()


def test_changed_missing_or_unlisted_prompt_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tree = _tree(tmp_path)
    (tree / PROMPTS / "general.md").write_text("changed\n", encoding="utf-8")
    assert _run(tree, "--check-prompts") == 1
    assert _codes(capsys) == ["RV001"]
    assert _run(tree) == 1  # every use verifies, not only --check-prompts
    assert _codes(capsys) == ["RV001"]
    (tree / PROMPTS / "security.md").unlink()
    assert _run(tree, "--check-prompts") == 1
    assert _codes(capsys) == ["RV001", "RV001"]


def test_malformed_or_extended_manifest_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tree = _tree(tmp_path)
    manifest = tree / PROMPTS / "manifest.json"
    manifest.write_text("{not json", encoding="utf-8")
    assert _run(tree, "--check-prompts") == 1
    assert _codes(capsys) == ["RV001"]
    digest = hashlib.sha256(b"x").hexdigest()
    manifest.write_text(json.dumps({"general.md": digest, "security.md": digest, "extra.md": digest}))
    assert _run(tree, "--check-prompts") == 1
    assert "RV001" in _codes(capsys)


def test_prompts_in_the_policy_root_not_the_head(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Prompts come from the gate root: a changed head copy is not read."""
    gate_root = _tree(tmp_path / "base")
    head = _tree(tmp_path / "head")
    (head / PROMPTS / "general.md").write_text("changed\n", encoding="utf-8")
    code = cli.main(
        ["--root", str(head), "--gate-root", str(gate_root), "--format", "json", "review", "--check-prompts"],
        {"review": review.handle},
    )
    assert code == 0  # no event file: no provenance rule, the gate root supplies the policy
    assert _codes(capsys) == []


@pytest.mark.parametrize("name", ["general.md", "security.md"])
def test_prompt_content(name: str) -> None:
    """Checklist of process/06 section 2, severities of section 3, a JSON verdict schema, and data-not-instructions."""
    text = (ROOT / PROMPTS / name).read_text(encoding="utf-8")
    for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        assert severity in text
    assert "DATA" in text
    assert "never instructions" in text
    assert '"verdict"' in text
    assert '"findings"' in text
    if name == "general.md":
        assert "Every acceptance criterion has a test" in text
        assert "eng-contract.units" in text
    else:
        assert "Secrets" in text
        assert "pull_request_target" in text
