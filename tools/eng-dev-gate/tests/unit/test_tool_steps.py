"""Unit tests of how the format, lint and types steps build the tool command lines (B-058; spec 4.12, 4.16)."""

from __future__ import annotations

from pathlib import Path

import pytest
from eng_dev_gate.checks import tests_step, tool_steps
from eng_dev_gate.checks.registry import StepContext
from eng_dev_gate.results import EnvironmentFaultError, UsageError
from eng_dev_gate.workspace import Member
from support.scripted import EnvironmentRunner, environment_payload


class Recorder(EnvironmentRunner):
    """Records the command line and the working directory of each call; every call succeeds.

    A pull-request run of ``types`` also asks for the judged environment, which the base class answers.
    """


def _context(tmp_path: Path, gate_pyproject: str, member_pyproject: str = "") -> tuple[StepContext, Recorder]:
    gate, root = tmp_path / "gate", tmp_path / "root"
    directory = root / "pkgs" / "a"
    for folder in (gate, directory):
        folder.mkdir(parents=True)
    (gate / "pyproject.toml").write_text(gate_pyproject, encoding="utf-8")
    (directory / "pyproject.toml").write_text(member_pyproject, encoding="utf-8")
    runner = Recorder()
    member = Member(name="a", path="pkgs/a", directory=directory)
    return StepContext(root, gate, member, runner), runner


def _options(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, arg in enumerate(argv) if arg == "--config"]


def test_ruff_policy_is_passed_as_options_and_runs_in_the_judged_tree(tmp_path: Path) -> None:
    gate_pyproject = (
        '[tool.ruff]\nline-length = 100\nextend-exclude = ["spikes"]\ntarget-version = "py314"\n'
        '[tool.ruff.lint]\nselect = ["E", "S"]\n[tool.ruff.lint.per-file-ignores]\n"**/tests/**" = ["S101"]\n'
    )
    ctx, runner = _context(tmp_path, gate_pyproject)
    assert tool_steps.lint(ctx) == []
    ((argv, cwd),) = runner.calls
    assert cwd == ctx.root
    assert "--isolated" in argv
    assert argv[-1] == str(ctx.root / "pkgs" / "a")
    assert _options(argv) == [
        "line-length = 100",
        'extend-exclude = ["spikes"]',
        'target-version = "py314"',
        'lint = {select = ["E", "S"], per-file-ignores = {"**/tests/**" = ["S101"]}}',
    ]


def test_format_uses_the_same_policy_options(tmp_path: Path) -> None:
    ctx, runner = _context(tmp_path, "[tool.ruff]\nline-length = 90\n")
    assert tool_steps.format_(ctx) == []
    ((argv, cwd),) = runner.calls
    assert argv[3:6] == ["format", "--check", "--isolated"]
    assert _options(argv)[0] == "line-length = 90"
    assert cwd == ctx.root


def test_target_version_is_derived_from_requires_python_like_ruff(tmp_path: Path) -> None:
    ctx, runner = _context(tmp_path, '[project]\nrequires-python = ">=3.14,<3.15"\n[tool.ruff]\nline-length = 90\n')
    tool_steps.lint(ctx)
    assert 'target-version = "py314"' in _options(runner.calls[0][0])


def test_target_version_of_the_table_wins_and_none_is_invented(tmp_path: Path) -> None:
    ctx, runner = _context(tmp_path, '[project]\nrequires-python = ">=3.14"\n[tool.ruff]\ntarget-version = "py312"\n')
    tool_steps.lint(ctx)
    assert _options(runner.calls[0][0]) == ['target-version = "py312"']
    bare, bare_runner = _context(tmp_path / "bare", "[tool.ruff]\nline-length = 90\n")
    tool_steps.lint(bare)
    assert _options(bare_runner.calls[0][0]) == ["line-length = 90"]


def test_a_gate_root_without_a_ruff_table_gives_the_defaults(tmp_path: Path) -> None:
    ctx, runner = _context(tmp_path, "[tool.other]\nx = 1\n")
    tool_steps.lint(ctx)
    assert _options(runner.calls[0][0]) == []
    assert "--isolated" in runner.calls[0][0]


def test_the_members_own_ruff_table_configures_the_tool_in_its_directory(tmp_path: Path) -> None:
    ctx, runner = _context(tmp_path, "[tool.ruff]\nline-length = 90\n", "[tool.ruff]\nline-length = 80\n")
    tool_steps.lint(ctx)
    ((argv, cwd),) = runner.calls
    assert cwd == ctx.root / "pkgs" / "a"
    assert argv[-3:-1] == ["--config", "pyproject.toml"]
    assert "--isolated" not in argv


def test_extend_in_the_base_policy_is_refused(tmp_path: Path) -> None:
    ctx, runner = _context(tmp_path, '[tool.ruff]\nextend = "other.toml"\n')
    with pytest.raises(UsageError, match="extend"):
        tool_steps.lint(ctx)
    assert runner.calls == []


def test_an_unreadable_base_configuration_is_a_usage_error(tmp_path: Path) -> None:
    ctx, _ = _context(tmp_path, "[tool.ruff\n")
    with pytest.raises(UsageError, match="cannot read"):
        tool_steps.lint(ctx)


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (True, "true"),
        (False, "false"),
        (3, "3"),
        (1.5, "1.5"),
        ('a"b\\c', '"a\\"b\\\\c"'),
        (["x", 1], '["x", 1]'),
        ({"a b": [1], "c": {"d": True}}, '{"a b" = [1], c = {d = true}}'),
    ],
)
def test_toml_values(value: object, text: str) -> None:
    assert tool_steps._toml_value(value) == text


def test_an_unsupported_value_is_a_usage_error() -> None:
    with pytest.raises(UsageError, match="unsupported"):
        tool_steps._toml_value(None)


def test_mypy_gets_the_base_configuration_by_path_and_runs_in_the_judged_tree(tmp_path: Path) -> None:
    ctx, runner = _context(tmp_path, "[tool.mypy]\nstrict = true\n")
    assert ctx.member is not None
    (ctx.member.directory / "src").mkdir()
    tool_steps.types(ctx)
    argv, cwd = runner.calls[-1]
    assert cwd == ctx.root
    assert argv[argv.index("--config-file") + 1] == str(ctx.gate_root / "pyproject.toml")
    assert argv[-1] == str(ctx.member.directory / "src")


def test_mypy_uses_the_members_own_table_in_its_directory(tmp_path: Path) -> None:
    ctx, runner = _context(tmp_path, "[tool.mypy]\nstrict = true\n", "[tool.mypy]\nstrict = true\n")
    tool_steps.types(ctx)
    argv, cwd = runner.calls[-1]
    assert cwd == ctx.root / "pkgs" / "a"
    assert argv[argv.index("--config-file") + 1] == "pyproject.toml"


def _cache_dir(argv: list[str]) -> Path:
    return Path(argv[argv.index("--cache-dir") + 1])


def test_ruff_never_keeps_a_cache_in_the_judged_tree(tmp_path: Path) -> None:
    """A cache committed to the pull request must not be read, and none is written into its tree (spec 4.16)."""
    own, own_runner = _context(tmp_path / "own", "[tool.ruff]\nline-length = 90\n", "[tool.ruff]\nline-length = 80\n")
    base, base_runner = _context(tmp_path / "base", "[tool.ruff]\nline-length = 90\n")
    for ctx in (own, base):
        tool_steps.lint(ctx)
        tool_steps.format_(ctx)
    for runner in (own_runner, base_runner):
        assert len(runner.calls) == 2
        assert all("--no-cache" in argv for argv, _ in runner.calls)


def test_mypy_keeps_its_cache_outside_the_judged_tree(tmp_path: Path) -> None:
    """A forged ``.mypy_cache`` in the pull request could mark a badly typed module as clean (spec 4.16)."""
    for name, member_table in (("base", ""), ("own", "[tool.mypy]\nstrict = true\n")):
        ctx, runner = _context(tmp_path / name, "[tool.mypy]\nstrict = true\n", member_table)
        tool_steps.types(ctx)
        argv, _ = runner.calls[-1]
        cache = _cache_dir(argv)
        assert cache.is_absolute()
        assert not cache.is_relative_to(ctx.root)
        assert not cache.is_relative_to(ctx.gate_root)
        assert not cache.exists()  # removed after the run


def _judged_types(tmp_path: Path, runner: EnvironmentRunner) -> StepContext:
    ctx, _ = _context(tmp_path, "[tool.mypy]\nstrict = true\n")
    assert ctx.member is not None
    (ctx.member.directory / "src").mkdir()
    return StepContext(ctx.root, ctx.gate_root, ctx.member, runner)


def test_mypy_runs_with_the_interpreter_of_the_judged_environment(tmp_path: Path) -> None:
    """AC54a: the gate's own mypy, told where the judged environment's packages and stubs are."""
    runner = EnvironmentRunner(environment_payload(executable="/judged/bin/python"))
    ctx = _judged_types(tmp_path, runner)
    assert tool_steps.types(ctx) == []
    argv, cwd = runner.calls[-1]
    assert argv[1:3] == ["-m", "mypy"]  # the gate's mypy, not the judged environment's
    assert argv[argv.index("--python-executable") + 1] == "/judged/bin/python"
    assert cwd == ctx.root
    assert [a[:2] for a, _ in runner.calls[:2]] == [["uv", "lock"], ["uv", "run"]]


def test_mypy_with_a_stale_lock_is_st001_and_does_not_run(tmp_path: Path) -> None:
    runner = EnvironmentRunner(lock=2)
    ctx = _judged_types(tmp_path, runner)
    (finding,) = tool_steps.types(ctx)
    assert (finding.code, finding.path) == ("ST001", "pkgs/a")
    assert finding.message.startswith("types: uv.lock of the judged tree is not up to date")
    assert len(runner.calls) == 1


def test_mypy_without_uv_is_an_environment_fault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tests_step, "_uv_available", lambda: False)
    runner = EnvironmentRunner()
    with pytest.raises(EnvironmentFaultError, match="types: uv is not available"):
        tool_steps.types(_judged_types(tmp_path, runner))
    assert runner.calls == []


def test_head_run_keeps_the_interpreter_of_the_gate(tmp_path: Path) -> None:
    """Without a gate root other than the judged tree, mypy gets no ``--python-executable`` and uv is not asked."""
    runner = EnvironmentRunner()
    ctx = _judged_types(tmp_path, runner)
    head = StepContext(ctx.root, ctx.root, ctx.member, runner)
    (ctx.root / "pyproject.toml").write_text("[tool.mypy]\nstrict = true\n", encoding="utf-8")
    assert tool_steps.types(head) == []
    ((argv, _),) = runner.calls
    assert "--python-executable" not in argv


@pytest.mark.parametrize("payload", ["not json", '{"executable": "python"}'])
def test_unusable_environment_report_is_an_environment_fault(tmp_path: Path, payload: str) -> None:
    with pytest.raises(EnvironmentFaultError, match="types: unusable metadata"):
        tool_steps.types(_judged_types(tmp_path, EnvironmentRunner(payload)))
