"""Tests of the ``licenses`` step (spec 4.12 license check; AC51) over fake installed distributions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eng_dev_gate.checks import licenses
from eng_dev_gate.checks.registry import StepContext
from eng_dev_gate.report import Finding
from eng_dev_gate.toolrun import SubprocessToolRunner
from eng_dev_gate.workspace import discover_members
from support.dists import add_dist
from support.repo import Repo
from support.toy import GATE_YML, make_workspace, member_pyproject

GPL = "License-Expression: GPL-3.0-only"
GPL_CLASSIFIER = "Classifier: License :: OSI Approved :: GNU General Public License v3 (GPLv3)"


def _setup(repo: Repo, dependencies: list[str], exceptions: str = "", extra_toml: str = "") -> StepContext:
    make_workspace(repo, ["a", "b"])
    deps = ", ".join(f'"{d}"' for d in dependencies)
    pyproject = member_pyproject("a").replace("dependencies = []", f"dependencies = [{deps}]") + extra_toml
    repo.write({"pkgs/a/pyproject.toml": pyproject, ".gate/gate.yml": GATE_YML + exceptions})
    member = next(m for m in discover_members(repo.root) if m.name == "a")
    return StepContext(repo.root, repo.root, member, SubprocessToolRunner())


def _run(ctx: StepContext, site: Path, monkeypatch: pytest.MonkeyPatch) -> list[Finding]:
    monkeypatch.setattr(licenses, "SEARCH_PATH", [str(site)])
    return licenses.licenses(ctx)


def _codes(findings: list[Finding]) -> list[tuple[str, str]]:
    return [(f.code, f.message.split(":")[0]) for f in findings]


def test_allowed_unknown_exception(repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC51: LC001 not allowed, LC002 unknown, LC003 excepted without its ADR; an excepted one with its ADR passes."""
    site = tmp_path / "site"
    add_dist(site, "fine", "License-Expression: MIT")
    add_dist(site, "bad", GPL)
    add_dist(site, "mystery")
    add_dist(site, "excepted", "License-Expression: LGPL-3.0-only")
    add_dist(site, "noadr", "License-Expression: LGPL-3.0-only")
    exceptions = (
        "license_exceptions:\n"
        "  - {distribution: excepted, license: LGPL-3.0-only, adr: docs/adr/0009-x.md}\n"
        "  - {distribution: noadr, license: LGPL-3.0-only, adr: docs/adr/0010-missing.md}\n"
    )
    ctx = _setup(repo, ["fine", "bad", "mystery", "excepted", "noadr"], exceptions)
    repo.write({"docs/adr/0009-x.md": "# ADR\n"})
    findings = _run(ctx, site, monkeypatch)
    assert _codes(findings) == [("LC001", "bad"), ("LC002", "mystery"), ("LC003", "noadr")]
    assert all(f.severity.value == "error" and f.path == "pkgs/a" for f in findings)


def test_exception_for_another_license_does_not_apply(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception names the license it accepts; a different license of the same distribution is LC001 again."""
    site = tmp_path / "site"
    add_dist(site, "excepted", GPL)
    exceptions = "license_exceptions:\n  - {distribution: excepted, license: LGPL-3.0-only, adr: docs/adr/0009-x.md}\n"
    ctx = _setup(repo, ["excepted"], exceptions)
    repo.write({"docs/adr/0009-x.md": "# ADR\n"})
    assert _codes(_run(ctx, site, monkeypatch)) == [("LC001", "excepted")]


@pytest.mark.parametrize(
    ("headers", "allowed"),
    [
        (["License-Expression: MIT OR GPL-3.0-only"], True),
        (["License-Expression: MIT AND GPL-3.0-only"], False),
        (["License-Expression: (MIT OR GPL-3.0-only) AND Apache-2.0"], True),
        (["License-Expression: Apache-2.0 OR BSD-2-Clause"], True),
        (["License-Expression: GPL-3.0-only WITH Classpath-exception-2.0"], False),
        (["License-Expression: ISC", "License-Expression-Unused: x"], True),
        (["License: MIT"], True),
        (["License: GPL-3.0-only"], False),
        (["Classifier: License :: OSI Approved :: MIT License"], True),
        ([GPL_CLASSIFIER], False),
        (
            [
                "Classifier: License :: OSI Approved :: BSD License",
                "Classifier: License :: OSI Approved :: MIT License",
            ],
            True,
        ),
        (["Classifier: License :: OSI Approved :: MIT License", GPL_CLASSIFIER], False),
        (["License-Expression: MIT", GPL_CLASSIFIER], True),
    ],
)
def test_expression_semantics(
    repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, headers: list[str], allowed: bool
) -> None:
    """Allowed: MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0; OR needs one allowed side, AND all; expression comes first."""
    site = tmp_path / "site"
    add_dist(site, "dep", *headers)
    findings = _run(_setup(repo, ["dep"]), site, monkeypatch)
    assert [f.code for f in findings] == ([] if allowed else ["LC001"])


def test_closure_groups_extras_markers_and_members(repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The closure follows requirements and groups; extras, uninstalled guarded requirements and members are skipped."""
    site = tmp_path / "site"
    add_dist(site, "top", "License-Expression: MIT", "Requires-Dist: deep", "Requires-Dist: opt; extra == 'x'")
    add_dist(site, "deep", GPL, "Requires-Dist: gone; sys_platform == 'nowhere'")
    add_dist(site, "opt", GPL)
    add_dist(site, "grouped", "License-Expression: AGPL-3.0-only")
    add_dist(site, "b", GPL)  # a workspace member: not checked
    groups = '[dependency-groups]\ndev = ["grouped>=1", {include-group = "more"}]\nmore = ["top"]\n'
    findings = _run(_setup(repo, ["top", "b>=0"], extra_toml=groups), site, monkeypatch)
    assert sorted(_codes(findings)) == [("LC001", "deep"), ("LC001", "grouped")]


def test_missing_distribution_is_lc002(repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A requirement without an installed distribution has no metadata: LC002."""
    (tmp_path / "site").mkdir()
    findings = _run(_setup(repo, ["absent"]), tmp_path / "site", monkeypatch)
    assert _codes(findings) == [("LC002", "absent")]


def test_licenses_command(repo: Repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``licenses`` command runs only the licenses step for ``--package`` or ``--all`` and exits 1 on a finding."""
    site = tmp_path / "site"
    add_dist(site, "bad", GPL)
    _setup(repo, ["bad"])
    monkeypatch.setattr(licenses, "SEARCH_PATH", [str(site)])
    handlers = {"licenses": licenses.make_handler()}
    failed = repo.run(["--format", "json", "licenses", "--all"], handlers)
    assert failed.code == 1
    assert [s["name"] for s in json.loads(failed.out)["steps"]] == ["licenses:a", "licenses:b"]
    assert repo.run(["licenses", "--package", "b"], handlers).code == 0
