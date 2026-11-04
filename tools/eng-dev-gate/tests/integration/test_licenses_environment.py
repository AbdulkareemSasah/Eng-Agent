"""Regression tests of B-086: the ``licenses`` step reads the judged tree's environment in pull-request context.

In CI the gate runs from the environment of the base checkout (``--gate-root``), which holds the gate and its
dependencies only. A pull request that adds a dependency installs it in the judged tree's environment alone, so two
temporary directories stand for the two checkouts and the interpreter of this test session stands for the base
environment: it has no distribution ``dep`` (a local path dependency of the judged member, built from its lock file).
"""

from __future__ import annotations

import json
from pathlib import Path

from eng_dev_gate.checks.check import make_handler
from eng_dev_gate.toolrun import SubprocessToolRunner
from support.judged_tree import make_gate_root, make_judged_tree, member_pyproject
from support.repo import Repo

DEP_BUILD = '[build-system]\nrequires = ["uv_build>=0.11.32,<0.12"]\nbuild-backend = "uv_build"\n'


def _dep(license_line: str) -> dict[str, str]:
    """Files (relative to the member) of the path dependency ``dep`` and the member's use of it."""
    project = f'[project]\nname = "dep"\nversion = "1.0"\nrequires-python = ">=3.14"\n{license_line}dependencies = []\n'
    member = member_pyproject().replace("dependencies = []", 'dependencies = ["dep"]')
    return {
        "pyproject.toml": member + '[tool.uv.sources]\ndep = { path = "vendor/dep" }\n',
        "vendor/dep/pyproject.toml": project + DEP_BUILD,
        "vendor/dep/src/dep/__init__.py": "",
    }


def _judge(gate: Repo, head: Repo) -> tuple[int, list[tuple[str, str]], str]:
    argv = ["--gate-root", str(gate.root), "--format", "json", "check", "--only", "licenses"]
    result = head.run(argv, {"check": make_handler(SubprocessToolRunner())})
    assert result.out, f"no report (exit {result.code}): {result.err[:600]}"
    (step,) = json.loads(result.out)["steps"]
    return result.code, [(f["code"], f["message"]) for f in step["findings"]], step["status"]


def test_dependency_installed_only_in_the_judged_environment_is_judged(tmp_path: Path) -> None:
    """``dep`` is absent from the gate's interpreter; its license comes from the judged environment and passes."""
    gate = make_gate_root(tmp_path / "base")
    head = make_judged_tree(tmp_path / "head", extra_files=_dep('license = "MIT"\n'))
    code, findings, status = _judge(gate, head)
    assert (code, findings, status) == (0, [], "pass")


def test_license_of_the_judged_environment_is_enforced(tmp_path: Path) -> None:
    """A dependency of the judged tree with a license that is not allowed is LC001, not LC002."""
    gate = make_gate_root(tmp_path / "base")
    head = make_judged_tree(tmp_path / "head", extra_files=_dep('license = "GPL-3.0-only"\n'))
    code, findings, _ = _judge(gate, head)
    assert (code, [(c, m.split(":")[0]) for c, m in findings]) == (1, [("LC001", "dep")])


def test_dependency_without_license_metadata_is_still_lc002(tmp_path: Path) -> None:
    gate = make_gate_root(tmp_path / "base")
    head = make_judged_tree(tmp_path / "head", extra_files=_dep(""))
    code, findings, _ = _judge(gate, head)
    assert (code, [(c, m.split(":")[0]) for c, m in findings]) == (1, [("LC002", "dep")])


def test_stale_lock_is_st001_of_the_step(tmp_path: Path) -> None:
    """A member requirement the lock file lacks cannot be installed: ST001 of the step, not an environment fault."""
    gate, head = make_gate_root(tmp_path / "base"), make_judged_tree(tmp_path / "head")
    head.commit({"pkgs/a/pyproject.toml": _dep("")["pyproject.toml"]}, "chore: stale")
    code, findings, status = _judge(gate, head)
    assert (code, [c for c, _ in findings], status) == (1, ["ST001"], "fail")
    assert findings[0][1].startswith("licenses: uv.lock of the judged tree is not up to date")
