"""The ``forbidden`` command and step of ``check`` on a toy workspace (spec 4.8, 4.12, AC29 to AC37)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eng_dev_gate.checks.check import make_handler
from support.repo import Repo, RunResult
from support.toy import POLICY_TEXT, make_workspace

BAD = 'def f() -> None:\n    print("x")\n    eval("1")\n'


def _json(result: RunResult) -> dict[str, Any]:  # Any: the JSON document is untyped data
    data: dict[str, Any] = json.loads(result.out)
    return data


def _steps(result: RunResult) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = _json(result)["steps"]
    return steps


def _findings(result: RunResult) -> list[dict[str, Any]]:
    return [f for s in _steps(result) for f in s["findings"]]


def test_command_reports_code_path_and_line(repo: Repo) -> None:
    make_workspace(repo, ["a", "b"], module=BAD)
    repo.commit({"pkgs/b/src/b/mod.py": "x = 1\n"})
    result = repo.run(["--format", "json", "forbidden", "--package", "a"])
    assert result.code == 1
    found = [(f["code"], f["path"], f["line"], f["severity"]) for f in _findings(result)]
    assert found == [
        ("FB007", "pkgs/a/src/a/mod.py", 2, "error"),
        ("FB002", "pkgs/a/src/a/mod.py", 3, "error"),
    ]
    assert _json(result)["command"] == "forbidden"
    text = repo.run(["forbidden", "--package", "a"])
    assert text.out.splitlines()[0] == "mode: bootstrap"
    assert "pkgs/a/src/a/mod.py:2: FB007" in text.out


def test_selection_and_clean_run(repo: Repo) -> None:
    make_workspace(repo, ["a", "b"], module=BAD)
    repo.commit({"pkgs/b/src/b/mod.py": "x = 1\n"})
    assert repo.run(["forbidden", "--package", "b"]).code == 0
    both = repo.run(["--format", "json", "forbidden", "--all"])
    assert both.code == 1
    assert [(s["name"], s["status"]) for s in _steps(both)] == [("forbidden:a", "fail"), ("forbidden:b", "pass")]
    assert repo.run(["forbidden", "--package", "missing"]).code == 2


def test_check_runs_the_step(repo: Repo) -> None:
    make_workspace(repo, ["a"], module=BAD)
    result = repo.run(["--format", "json", "check", "--only", "forbidden"], {"check": make_handler()})
    assert result.code == 1
    assert [(s["name"], s["status"]) for s in _steps(result)] == [("forbidden", "fail")]


def test_missing_or_invalid_policy_is_exit_2(repo: Repo) -> None:
    make_workspace(repo, ["a"])
    (repo.root / ".gate" / "forbidden.yml").write_text("escape_hatch: 1\n", encoding="utf-8")
    assert repo.run(["forbidden", "--all"]).code == 2
    (repo.root / ".gate" / "forbidden.yml").unlink()
    result = repo.run(["forbidden", "--all"])
    assert result.code == 2
    assert "forbidden.yml" in result.err


def test_policy_comes_from_the_gate_root(repo: Repo, tmp_path: Path) -> None:
    """A head tree that weakens ``.gate/forbidden.yml`` is judged by the policy of the gate root."""
    make_workspace(repo, ["a"], module="MARK = 'strict_marker'\n")
    gate = tmp_path / "gate-base"
    (gate / ".gate").mkdir(parents=True)
    (gate / ".gate" / "gate.yml").write_text((repo.root / ".gate" / "gate.yml").read_text(encoding="utf-8"))
    (gate / ".gate" / "forbidden.yml").write_text(
        POLICY_TEXT.replace("csi_run_script", "strict_marker", 1), encoding="utf-8"
    )
    assert repo.run(["forbidden", "--all"]).code == 0
    strict = repo.run(["--gate-root", str(gate), "--format", "json", "forbidden", "--all"])
    assert strict.code == 1
    assert [f["code"] for f in _findings(strict)] == ["FB001"]
