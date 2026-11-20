"""Tests of ``agents drift`` on temporary git repositories (spec 4.13, AC57) and of the committed AGENTS.md files."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from eng_dev_gate.agents import render_unit, template_version, units_of
from support.repo import Repo

TEMPLATE = "# {{name}}\n\nbody {{template-version}}\n"
GATE_YML = """\
bootstrap: {enabled: true, gate_branch: build/v1}
main_branch: main
identities: {owner_login: owner, agent_logins: [], reviewer_app: ""}
spec_globs: []
plan_globs: []
test_globs: []
generated_globs: []
spike_globs: []
agents: {unmanaged_ok: ["design/**"]}
limits: {diff_lines: 4, test_run_seconds: 600, max_file_bytes: 1048576, mutation_run_seconds: 7200}
license_exceptions: []
secrets: {allow: []}
"""


def _clean_repo(repo: Repo) -> None:
    version = template_version(TEMPLATE)

    def cfg(template: str, name: str) -> str:
        return yaml.safe_dump(
            {"template": template, "output": "AGENTS.md", "values": {"name": name, "template-version": version}}
        )

    repo.commit(
        {
            "t/template.md": TEMPLATE,
            ".gate/gate.yml": GATE_YML,
            ".gate/agents.yml": cfg("t/template.md", "root"),
            "AGENTS.md": f"# root\n\nbody {version}\n",
            "CLAUDE.md": "@AGENTS.md\n",
            "pyproject.toml": '[tool.uv.workspace]\nmembers = ["pkg"]\n',
            "pkg/pyproject.toml": '[project]\nname = "pkg"\n',
            "pkg/.gate/agents.yml": cfg("../t/template.md", "pkg"),
            "pkg/AGENTS.md": f"# pkg\n\nbody {version}\n",
            "pkg/CLAUDE.md": "@AGENTS.md\n",
            "design/AGENTS.md": "hub file, unmanaged but allowed\n",
        }
    )


def _findings(repo: Repo) -> list[dict[str, object]]:
    result = repo.run(["--format", "json", "agents", "drift"])
    data = json.loads(result.out)
    return [f for step in data["steps"] for f in step["findings"]]


def test_drift_unmanaged_and_pointer(repo: Repo) -> None:
    """AC57: AG004 for a differing file, AG005 for an unmanaged one, AG006 for a missing CLAUDE.md pointer."""
    _clean_repo(repo)
    assert repo.run(["agents", "drift"]).code == 0

    (repo.root / "AGENTS.md").write_text("# root\n" + "".join(f"line {i}\n" for i in range(20)), encoding="utf-8")
    findings = _findings(repo)
    assert [f["code"] for f in findings] == ["AG004"]
    assert findings[0]["path"] == "AGENTS.md"
    assert "@@" in str(findings[0]["message"])
    assert len(str(findings[0]["message"]).splitlines()) <= 4 + 1  # diff_lines plus the leading sentence
    assert repo.run(["agents", "drift"]).code == 1
    repo.run(["agents", "render"])
    assert repo.run(["agents", "drift"]).code == 0

    repo.commit({"other/AGENTS.md": "x\n"})
    findings = _findings(repo)
    assert [(f["code"], f["path"]) for f in findings] == [("AG005", "other/AGENTS.md")]
    repo.git("rm", "-q", "other/AGENTS.md")

    repo.git("rm", "-q", "pkg/CLAUDE.md")
    assert [(f["code"], f["path"]) for f in _findings(repo)] == [("AG006", "pkg/AGENTS.md")]
    repo.commit({"pkg/CLAUDE.md": "@AGENTS.md"})  # no trailing newline is not the pointer
    assert [f["code"] for f in _findings(repo)] == ["AG006"]


def test_drift_ignores_crlf_in_committed_file(repo: Repo) -> None:
    _clean_repo(repo)
    path = repo.root / "AGENTS.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    repo.git("add", "-A")
    assert repo.run(["agents", "drift"]).code == 0


def test_drift_reports_render_errors(repo: Repo) -> None:
    _clean_repo(repo)
    config = yaml.safe_load((repo.root / "pkg/.gate/agents.yml").read_text(encoding="utf-8"))
    config["values"]["extra"] = "x"
    (repo.root / "pkg/.gate/agents.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    findings = _findings(repo)
    assert [(f["code"], f["path"]) for f in findings] == [("AG002", "pkg/AGENTS.md")]


def test_committed_agents_files_equal_their_rendering() -> None:
    """The AGENTS.md files of the workspace root and of this package equal what the renderer produces."""
    root = Path(__file__).resolve().parents[4]
    assert (root / "design/process/templates/AGENTS.template.md").is_file(), "runs inside the workspace only"
    units = units_of(root)
    assert {u.output for u in units} >= {"AGENTS.md", "tools/eng-dev-gate/AGENTS.md"}
    for unit in units:
        committed = (root / unit.output).read_bytes().decode("utf-8")
        assert render_unit(root, unit) == committed, unit.output


def _shared_folder(repo: Repo) -> None:
    """A shared package folder (not a workspace member) with its own agents.yml, beside a member below it."""
    _clean_repo(repo)
    version = template_version(TEMPLATE)
    values = {"name": "shared", "template-version": version}
    repo.commit(
        {
            "pyproject.toml": '[tool.uv.workspace]\nmembers = ["pkg", "shared/core"]\n',
            "shared/.gate/agents.yml": yaml.safe_dump(
                {"template": "../t/template.md", "output": "AGENTS.md", "values": values}
            ),
            "shared/AGENTS.md": f"# shared\n\nbody {version}\n",
            "shared/CLAUDE.md": "@AGENTS.md\n",
            "shared/core/pyproject.toml": '[project]\nname = "core"\n',
        }
    )


def test_shared_package_folder_is_a_unit(repo: Repo) -> None:
    """B-026: a tracked agents.yml outside the root and the members manages its AGENTS.md (no AG005)."""
    _shared_folder(repo)
    assert [(u.name, u.path, u.output) for u in units_of(repo.root)] == [
        ("", ".", "AGENTS.md"),
        ("pkg", "pkg", "pkg/AGENTS.md"),
        ("shared", "shared", "shared/AGENTS.md"),
    ]
    assert _findings(repo) == []
    (repo.root / "shared/AGENTS.md").write_text("# edited\n", encoding="utf-8")
    assert [(f["code"], f["path"]) for f in _findings(repo)] == [("AG004", "shared/AGENTS.md")]
    assert repo.run(["agents", "render", "--package", "shared"]).code == 0
    assert _findings(repo) == []


def test_shared_package_folder_output_stays_inside_the_root(repo: Repo) -> None:
    _shared_folder(repo)
    config = yaml.safe_load((repo.root / "shared/.gate/agents.yml").read_text(encoding="utf-8"))
    config["output"] = "../../AGENTS.md"
    repo.commit({"shared/.gate/agents.yml": yaml.safe_dump(config)})
    result = repo.run(["agents", "drift"])
    assert result.code == 2
    assert "outside the workspace root" in result.err + result.out
