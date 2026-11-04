"""Integration tests of ``test-first`` part 2: the base worktree, the pytest runs, the classification, isolation.

Spec 4.7 step 4.3 to 4.5; AC23, AC24, AC27. The toy workspace of ``support.tfrepo`` has the package ``fixpkg`` with
``VALUE = 1`` at the base. The runs are real pytest subprocesses in the interpreter that runs these tests; a few cases
replace the probe or the pytest call to reach the exit-3 findings (TF009, TF011).
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from eng_dev_gate.checks.test_first_run import RunFaultError, Runner, SubprocessRunner
from eng_dev_gate.toolrun import ToolResult
from support.pullrequest import BODY, write_event
from support.repo import Repo
from support.tfrepo import LIB, head_of, tf_repo, tf_run

RED = "from fixpkg import VALUE\n\n\ndef test_value_is_two() -> None:\n    assert VALUE == 2\n"
WHERE = (
    "import fixpkg\n\n\ndef test_package_comes_from_the_checkout() -> None:\n"
    "    assert 'eng-gate-tf-' not in fixpkg.__file__\n"
)
GREEN = {LIB: "VALUE = 2\n"}


class Scripted:
    """A runner that runs the real one, except that the import probe or the pytest call can be replaced."""

    def __init__(self, probe: str | None = None, pytest_exit: int | None = None) -> None:
        self._real: Runner = SubprocessRunner()
        self._probe = probe
        self._pytest_exit = pytest_exit

    def run(self, argv: Sequence[str], cwd: Path, env: Mapping[str, str], timeout_seconds: float) -> ToolResult:
        if "-c" in argv and self._probe is not None:
            return ToolResult(exit_code=0, output=self._probe)
        if "pytest" in argv and self._pytest_exit is not None:
            return ToolResult(exit_code=self._pytest_exit, output="")
        return self._real.run(argv, cwd, env, timeout_seconds)


def _red_green(repo: Repo) -> str:
    base = tf_repo(repo)
    repo.commit({"pkg/tests/test_new.py": RED, "pkg/tests/test_where.py": WHERE}, "test(x): red")
    repo.commit(GREEN, "feat(x): green")
    return base


def test_red_green(repo: Repo) -> None:
    """AC23: tests that fail on the merge base and pass at the head pass; the base package is the one imported."""
    base = _red_green(repo)
    result, status, errors = tf_run(repo, base, "feat: x")
    assert (result.code, status, errors) == (0, "pass", {})
    # the same pull request from its event: the title and the plan task come from the event file and the gate branch
    event = write_event(repo, base, BODY)
    from_event = repo.run(["test-first", "--event", str(event)])
    assert (from_event.code, "test-first: pass" in from_event.out) == (0, True)


def test_collection_error_counts_as_failing(repo: Repo) -> None:
    """A module that cannot be imported at the base (a new name) fails every test of the module there."""
    base = tf_repo(repo)
    source = "from fixpkg import NEW_NAME\n\n\ndef test_a() -> None:\n    assert NEW_NAME == 3\n\n\n"
    repo.commit({"pkg/tests/test_new.py": source + "def test_b() -> None:\n    assert NEW_NAME > 0\n"}, "test: red")
    repo.commit({LIB: "VALUE = 1\nNEW_NAME = 3\n"}, "feat: green")
    result, status, errors = tf_run(repo, base, "feat: x")
    assert (result.code, status, errors) == (0, "pass", {})


def test_parametrized_test_is_red_when_one_case_fails(repo: Repo) -> None:
    """A changed parametrized test is red at the base when a case fails there (the added case), green when all pass."""
    head = "import pytest\nfrom fixpkg import VALUE\n\n\n@pytest.mark.parametrize('v', {cases})\n"
    head += "def test_value_at_least(v: int) -> None:\n    assert VALUE >= v\n"
    base = tf_repo(repo, base_files={"pkg/tests/test_p.py": head.format(cases="[1]")})
    repo.commit({"pkg/tests/test_p.py": head.format(cases="[1, 2]")}, "test: add a case")
    repo.commit(GREEN, "feat: green")
    result, status, errors = tf_run(repo, base, "feat: x")
    assert (result.code, status, errors) == (0, "pass", {})
    repo.git("reset", "-q", "--hard", "HEAD~1")  # without the implementation the added case still fails at the head
    result, _, errors = tf_run(repo, base, "feat: x")
    assert (result.code, list(errors)) == (1, ["TF005"])


def test_passes_at_base_and_fails_at_head(repo: Repo) -> None:
    """AC24: a test that passes (or is skipped) on the merge base is TF004; one that is not green at the head, TF005."""
    base = tf_repo(repo)
    tests = (
        "import pytest\nfrom fixpkg import VALUE\n\n\n"
        "def test_already_green() -> None:\n    assert VALUE == 1\n\n\n"
        "def test_never_green() -> None:\n    assert VALUE == 2\n\n\n"
        '@pytest.mark.skip(reason="B-046 expires 2099-01-01")\ndef test_skipped() -> None:\n    assert VALUE == 2\n'
    )
    repo.commit({"pkg/tests/test_new.py": tests}, "test: mixed")
    result, status, errors = tf_run(repo, base, "feat: x")
    assert (result.code, status) == (1, "fail")
    assert set(errors) == {"TF004", "TF005"}
    assert "test_already_green" in errors["TF004"]
    assert "test_skipped" in errors["TF004"]
    assert "test_never_green" not in errors["TF004"]
    assert errors["TF004"].startswith("pkg/tests/test_new.py ")
    assert "test_never_green" in errors["TF005"]
    assert "test_skipped" in errors["TF005"]
    assert "test_already_green" not in errors["TF005"]


def _snapshot(repo: Repo) -> dict[str, str]:
    return {
        "refs": repo.git("for-each-ref"),
        "worktrees": repo.git("worktree", "list", "--porcelain"),
        "status": repo.git("status", "--porcelain"),
        "head": repo.git("rev-parse", "HEAD"),
        "leftover": str(sorted((repo.root / ".git" / "worktrees").glob("*"))),
    }


@pytest.mark.parametrize("scripted", [None, Scripted(pytest_exit=5), Scripted(probe="fixpkg\t/elsewhere/fixpkg.py\n")])
def test_base_isolation_and_cleanup(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scripted: Scripted | None
) -> None:
    """AC27: the temporary worktree is removed whatever the outcome; refs, index and tree are unchanged."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    base = _red_green(repo)
    before = _snapshot(repo)
    result, _, errors = tf_run(repo, base, "feat: x", runner=scripted)
    assert _snapshot(repo) == before
    assert list(scratch.iterdir()) == []
    if scripted is None:
        assert (result.code, errors) == (0, {})  # the head package is not the one at the base (see test_red_green)
    else:
        assert (result.code, errors) == (3, {})


def test_exit_three_findings(repo: Repo) -> None:
    """TF009 for pytest exit 5 and for a missing result; TF011 when the package does not resolve in the worktree."""
    base = _red_green(repo)
    result, _, _ = tf_run(repo, base, "feat: x", runner=Scripted(pytest_exit=5))
    assert (result.code, "TF009" in result.err) == (3, True)
    result, _, _ = tf_run(repo, base, "feat: x", runner=Scripted(pytest_exit=1))  # exit 1 without a result file
    assert (result.code, "TF009" in result.err) == (3, True)
    result, _, _ = tf_run(repo, base, "feat: x", runner=Scripted(probe="fixpkg\t/elsewhere/fixpkg.py\n"))
    assert (result.code, "TF011" in result.err) == (3, True)
    result, _, _ = tf_run(repo, base, "feat: x", runner=Scripted(probe="fixpkg\t\n"))  # a name that does not resolve
    assert (result.code, "TF011" in result.err) == (3, True)


def test_no_owning_package(repo: Repo) -> None:
    """A test file that no workspace member owns cannot be run: TF009."""
    base = tf_repo(repo)
    repo.commit({"orphan/tests/test_o.py": "def test_o() -> None:\n    assert False\n"}, "test: orphan")
    result, _, _ = tf_run(repo, base, "feat: x")
    assert (result.code, "TF009" in result.err) == (3, True)


def test_new_package_has_no_probe(repo: Repo) -> None:
    """A package that does not exist at the base has nothing to resolve there: it is run without the probe, red."""
    base = tf_repo(repo)
    workspace = (repo.root / "pyproject.toml").read_text(encoding="utf-8").replace('"pkg"', '"pkg", "pkg2"')
    repo.commit(
        {
            "pkg2/pyproject.toml": (repo.root / "pkg/pyproject.toml").read_text(encoding="utf-8"),
            "pkg2/src/newpkg/__init__.py": "VALUE = 5\n",
            "pyproject.toml": workspace,
        },
        "feat: add package",
    )
    test = "from newpkg import VALUE\n\n\ndef test_n() -> None:\n    assert VALUE == 5\n"
    repo.commit({"pkg2/tests/test_n.py": test}, "test: red")
    result, status, errors = tf_run(repo, base, "feat: x")
    assert (result.code, status, errors) == (0, "pass", {})


def test_subprocess_runner_times_out() -> None:
    """A run over its time limit is TF009 (exit 3), never a pass."""
    with pytest.raises(RunFaultError, match="TF009") as raised:
        SubprocessRunner().run([sys.executable, "-c", "import time; time.sleep(30)"], Path.cwd(), {}, 0.2)
    assert raised.value.exit_code == 3


def test_head_unchanged_after_run(repo: Repo) -> None:
    """The head checkout is the tree of the run: the same commit, nothing written (no bytecode, no cache)."""
    base = _red_green(repo)
    tf_run(repo, base, "feat: x")
    assert repo.git("rev-parse", "HEAD").strip() == head_of(repo)
    assert repo.git("status", "--porcelain") == ""
