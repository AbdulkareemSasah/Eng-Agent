"""The ``workflows`` step (spec 4.14, AC60, AC68): WF001 to WF005 over workflow and action files in a toy repository."""

from __future__ import annotations

import json

import pytest
from eng_dev_gate.checks import workflows
from eng_dev_gate.checks.registry import STEP_ORDER, STEPS, StepContext
from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.toolrun import SubprocessToolRunner
from support.repo import Repo
from support.toy import make_workspace

SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
ACTIONS = "tools/eng-dev-gate/actions"
PR_JOBS = ("gate", "gate-check", "risk-floor", "test-first", "ci-review", "agents-drift", "security", "build")
HEAD_REF = "${{ github.event.pull_request.head.sha || github.sha }}"
BASE_REF = "${{ github.event.pull_request.base.sha }}"
CI = ".github/workflows/ci.yml"


def _guard(action: str) -> str:
    return f"hashFiles('.gate-base/{ACTIONS}/{action}/action.yml')"


def _pr_job(name: str) -> str:
    lines = [
        f"  {name}:", "    runs-on: ubuntu-latest", "    steps:",
        f"      - uses: actions/checkout@{SHA}", f'        with: {{ref: "{HEAD_REF}", fetch-depth: 0}}',
        "      - if: github.event_name == 'pull_request'", f"        uses: actions/checkout@{SHA}",
        f'        with: {{ref: "{BASE_REF}", path: .gate-base, persist-credentials: false}}',
    ]  # fmt: skip
    for action in ("setup", name):
        lines += [
            f"      - if: {_guard(action)} != ''", f"        uses: ./.gate-base/{ACTIONS}/{action}",
            "        with: {gate-root: .gate-base}",
            f"      - if: {_guard(action)} == ''", f"        uses: ./{ACTIONS}/{action}",
        ]  # fmt: skip
    return "\n".join(lines) + "\n"


WINDOWS_JOB = f"""  windows:
    if: github.event_name == 'push'
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@{SHA}
      - uses: ./{ACTIONS}/setup
      - run: uv run pytest -m windows
"""
HEADER = (
    "name: ci\non:\n  pull_request:\n    branches: [build/v1]\n  push:\n    branches: [build/v1]\n"
    "permissions:\n  contents: read\njobs:\n"
)


def _ci(**replaced: str) -> str:
    """The valid workflow; ``replaced`` maps a job id (underscores for hyphens) to its replacement text."""
    jobs = {n: _pr_job(n) for n in PR_JOBS} | {"windows": WINDOWS_JOB}
    jobs |= {name.replace("_", "-"): text for name, text in replaced.items()}
    return HEADER + "".join(jobs.values())


def _lint(repo: Repo, files: dict[str, str]) -> list[Finding]:
    make_workspace(repo, ["a"])
    repo.write({f"{ACTIONS}/{n}/action.yml": "runs: {using: composite, steps: []}\n" for n in PR_JOBS})
    repo.write(files)
    return workflows.workflows(StepContext(repo.root, repo.root, None, SubprocessToolRunner()))


def _summary(findings: list[Finding]) -> list[tuple[str, str | None, int | None]]:
    return [(f.code, f.path, f.line) for f in findings]


def test_pin_permissions_injection_trigger(repo: Repo) -> None:
    """AC60: WF001 unpinned or non-owner/repo actions, WF002 no permissions, WF003 injection in run, WF004 trigger."""
    bad = (
        "on: [push, pull_request_target]\n"  # 1
        "jobs:\n"  # 2
        "  a:\n"  # 3
        "    steps:\n"  # 4
        "      - uses: actions/checkout@v4\n"  # 5
        f"      - uses: actions/checkout@{SHA}\n"  # 6
        "      - uses: docker://alpine:3\n"  # 7
        "      - uses: ./local/action\n"  # 8
        "      - run: echo '${{ github.event.pull_request.title }}'\n"  # 9
        "      - run: echo ${{github.head_ref}} ${{ github.event.pull_request.head.ref }}\n"  # 10
        "      - run: echo ${{ github.event.pull_request.body }}\n"  # 11
        "      - run: echo ${{ github.sha }}\n"  # 12
        "      - name: ${{ github.event.pull_request.title }}\n"  # 13
        "        env: {TITLE: '${{ github.event.pull_request.title }}'}\n"  # 14
        "        run: echo ok\n"  # 15
    )
    action = (
        "runs:\n  using: composite\n  steps:\n"
        "    - uses: actions/setup-python@v5\n"
        "    - run: echo ${{ github.event.pull_request.title }}\n"
    )
    findings = _lint(repo, {CI: _ci(), ".github/workflows/x.yml": bad, f"{ACTIONS}/extra/action.yml": action})
    workflow = ".github/workflows/x.yml"
    assert _summary(findings) == [
        ("WF002", workflow, None), ("WF004", workflow, None), ("WF001", workflow, 5), ("WF001", workflow, 7),
        ("WF003", workflow, 9), ("WF003", workflow, 10), ("WF003", workflow, 11),
        ("WF001", f"{ACTIONS}/extra/action.yml", 4), ("WF003", f"{ACTIONS}/extra/action.yml", 5),
    ]  # fmt: skip
    assert {f.severity for f in findings} == {Severity.ERROR}
    clean = (
        "on: [push]\npermissions: {contents: read}\njobs:\n  a:\n    steps:\n"
        f"      - uses: actions/checkout@{SHA}\n      - uses: ./local/action\n      - run: echo ${{{{ github.sha }}}}\n"
        "      - name: ${{ github.event.pull_request.title }}\n"
        "        env: {TITLE: '${{ github.event.pull_request.title }}'}\n        run: echo ok\n"
    )
    again = _lint(repo, {CI: _ci(), ".github/workflows/x.yml": clean})
    assert [f for f in again if f.path == workflow] == []


@pytest.mark.parametrize("trigger", ["pull_request_target", "[push, pull_request_target]", "{pull_request_target: {}}"])
def test_pull_request_target_in_every_form(repo: Repo, trigger: str) -> None:
    """AC60: WF004 for the trigger as a string, a list or a mapping."""
    text = f"permissions: {{contents: read}}\non: {trigger}\njobs: {{}}\n"
    assert [f.code for f in _lint(repo, {CI: _ci(), ".github/workflows/t.yml": text})] == ["WF004"]


def test_ci_shape_base_first(repo: Repo) -> None:
    """AC68: the exact jobs, head checkout, base checkout into .gate-base, guarded variants only, no eng-gate run."""
    assert _lint(repo, {CI: _ci()}) == []
    spikes = _pr_job("gate") + "      - name: Spikes\n        run: uv run --script spikes/a/check.py\n"
    assert _lint(repo, {CI: _ci(gate=spikes)}) == []  # other steps are free


def test_ci_shape_violations(repo: Repo) -> None:
    """AC68: each departure from the shape is WF005 on ci.yml."""
    gate = _pr_job("gate")
    foreign = f"      - uses: ./{ACTIONS}/build\n"
    windows_base = WINDOWS_JOB.replace(f"./{ACTIONS}/setup", f"./.gate-base/{ACTIONS}/setup")
    cases = {
        "job with an action missing": _ci().replace(_pr_job("risk-floor"), ""),
        "unknown job": _ci().replace(WINDOWS_JOB, _pr_job("extra") + WINDOWS_JOB),
        "windows missing": _ci().replace(WINDOWS_JOB, ""),
        "no base checkout": _ci(gate=gate.replace("path: .gate-base", "path: elsewhere")),
        "base ref is the head": _ci(gate=gate.replace(BASE_REF, HEAD_REF)),
        "base checkout unguarded": _ci(gate=gate.replace("if: github.event_name == 'pull_request'", "name: base")),
        "head checkout without ref": _ci(gate=gate.replace(f'ref: "{HEAD_REF}", ', "")),
        "unguarded base variant": _ci(gate=gate.replace(f"if: {_guard('gate')} != ''", "name: x")),
        "guard flipped": _ci(gate=gate.replace(_guard("gate") + " ==", _guard("gate") + " !=")),
        "base variant without gate-root": _ci(gate=gate.replace("        with: {gate-root: .gate-base}\n", "", 1)),
        "foreign local action": _ci(gate=gate + foreign),
        "eng-gate in run": _ci(gate=gate + "      - run: uv run eng-gate check\n"),
        "windows with a base variant": _ci(windows=windows_base),
        "windows runs eng-gate": _ci(windows=WINDOWS_JOB + "      - run: eng-gate windows-tests\n"),
    }  # fmt: skip
    for label, text in cases.items():
        findings = _lint(repo, {CI: text})
        assert findings, label
        assert {f.code for f in findings} == {"WF005"}, label
        assert {f.path for f in findings} == {CI}, label


def test_missing_ci_file_and_unparsable_yaml(repo: Repo) -> None:
    """A repository without ci.yml is WF005; a file that does not parse is WF000."""
    assert [(f.code, f.path) for f in _lint(repo, {})] == [("WF005", CI)]
    findings = _lint(repo, {CI: _ci(), ".github/workflows/bad.yml": "a: [unclosed\n"})
    assert _summary(findings) == [("WF000", ".github/workflows/bad.yml", None)]


def test_registered_step_and_command(repo: Repo) -> None:
    """The step is the last of the 14 and the command ``workflows`` exits 1 on a finding, 0 on a clean tree."""
    assert STEP_ORDER[-1] == "workflows"
    assert [s.name for s in STEPS][-1] == "workflows"
    _lint(repo, {CI: _ci()})
    assert repo.run(["workflows"]).code == 0
    repo.write({".github/workflows/x.yml": "on: pull_request_target\njobs: {}\n"})
    out = repo.run(["--format", "json", "workflows"])
    assert out.code == 1
    codes = {f["code"] for step in json.loads(out.out)["steps"] for f in step["findings"]}
    assert codes == {"WF002", "WF004"}
