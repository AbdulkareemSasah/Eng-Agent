"""AC54a: the ``imports`` step resolves third-party names in the judged tree's environment (pull-request context).

The interpreter of this test session stands for the base environment: it has no module ``depmod``, which only the
judged tree's lock file installs (distribution ``dep-dist``).
"""

from __future__ import annotations

import json
from pathlib import Path

from eng_dev_gate.checks.check import make_handler
from eng_dev_gate.toolrun import SubprocessToolRunner
from support.judged_tree import USES_DEPENDENCY, make_gate_root, make_judged_tree, stubbed_dependency
from support.repo import Repo


def _judge(gate: Repo, head: Repo) -> tuple[int, list[tuple[str, str | None]]]:
    argv = ["--gate-root", str(gate.root), "--format", "json", "check", "--only", "imports"]
    result = head.run(argv, {"check": make_handler(SubprocessToolRunner())})
    assert result.out, f"no report (exit {result.code}): {result.err[:600]}"
    (step,) = json.loads(result.out)["steps"]
    return result.code, [(f["code"], f["path"]) for f in step["findings"]]


def test_declared_dependency_installed_only_in_the_judged_environment_is_im006_free(tmp_path: Path) -> None:
    gate = make_gate_root(tmp_path / "base")
    head = make_judged_tree(tmp_path / "head", extra_files=stubbed_dependency(USES_DEPENDENCY))
    assert _judge(gate, head) == (0, [])


def test_undeclared_dependency_is_still_im006(tmp_path: Path) -> None:
    """A module of a distribution that the member does not declare stays IM006 in the judged environment."""
    gate = make_gate_root(tmp_path / "base")
    files = stubbed_dependency(USES_DEPENDENCY)
    files["pyproject.toml"] = files["pyproject.toml"].replace('["dep-dist", "types-dep-dist"]', '["types-dep-dist"]')
    head = make_judged_tree(tmp_path / "head", extra_files=files)
    assert _judge(gate, head) == (1, [("IM006", "pkgs/a/src/a/uses.py")])
