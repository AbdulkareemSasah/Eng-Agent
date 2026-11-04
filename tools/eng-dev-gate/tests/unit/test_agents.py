"""Tests of ``agents render`` and ``agents keys`` (spec 4.13, AC55, AC56, AC58)."""

from __future__ import annotations

import hashlib
import json
import re

import pytest
import yaml
from eng_dev_gate.agents import RenderError, keys_skeleton, render_template, template_version
from eng_dev_gate.results import ExitCode
from support.repo import Repo

TEMPLATE = "# {{name}}\n\nVersion {{template-version}}.\n{{optional rows}}\nEnd {{a\nb}}\n"


def _values(version: str, **extra: str) -> dict[str, str]:
    return {"name": "pkg", "template-version": version, "optional rows": "| row |", "a\nb": "multi", **extra}


def test_render_byte_exact() -> None:
    """AC55: plain substitution, verbatim values, LF, empty standalone placeholder drops its line."""
    version = template_version(TEMPLATE)
    out = render_template(TEMPLATE, _values(version))
    assert out == f"# pkg\n\nVersion {version}.\n| row |\nEnd multi\n"
    dropped = render_template(TEMPLATE, _values(version, **{"optional rows": ""}))
    assert dropped == f"# pkg\n\nVersion {version}.\nEnd multi\n"
    assert render_template("x {{name}} y\n{{name}} tail\n", {"name": ""}) == "x  y\n tail\n"
    assert render_template("a {{name}}", {"name": "v"}) == "a v"
    assert render_template("keep\n{{name}}", {"name": ""}) == "keep\n"


def test_render_normalizes_crlf_and_has_no_bom() -> None:
    crlf = TEMPLATE.replace("\n", "\r\n")
    version = template_version(TEMPLATE)
    out = render_template(crlf, _values(version))
    assert "\r" not in out
    assert not out.startswith("﻿")
    assert out == render_template(TEMPLATE, _values(version))


def test_placeholder_errors() -> None:
    """AC56: AG001 lists all missing, AG002 an unused value, AG003 a stale version, AG007 recursion (exit 2)."""
    version = template_version(TEMPLATE)
    good = _values(version)
    missing = {k: v for k, v in good.items() if k not in ("name", "optional rows")}
    with pytest.raises(RenderError) as error:
        render_template(TEMPLATE, missing)
    assert [c for c, _ in error.value.codes] == ["AG001"]
    assert "name" in error.value.codes[0][1]
    assert "optional rows" in error.value.codes[0][1]
    assert error.value.exit_code is ExitCode.FAILED
    with pytest.raises(RenderError) as error:
        render_template(TEMPLATE, {**good, "unused": "x"})
    assert [c for c, _ in error.value.codes] == ["AG002"]
    with pytest.raises(RenderError) as error:
        render_template(TEMPLATE, {**good, "template-version": "sha256:000000000000"})
    assert [c for c, _ in error.value.codes] == ["AG003"]
    with pytest.raises(RenderError) as error:
        render_template(TEMPLATE, {**good, "name": "{{name}}"})
    assert [c for c, _ in error.value.codes] == ["AG007"]
    assert error.value.exit_code is ExitCode.USAGE


def test_template_version() -> None:
    """The version is sha256: plus the first 12 hex digits of the SHA-256 of the LF-normalized template."""
    digest = hashlib.sha256(TEMPLATE.encode("utf-8")).hexdigest()
    assert template_version(TEMPLATE) == f"sha256:{digest[:12]}"
    assert template_version(TEMPLATE.replace("\n", "\r\n")) == template_version(TEMPLATE)
    assert re.fullmatch(r"sha256:[0-9a-f]{12}", template_version(""))


def test_keys_skeleton() -> None:
    """AC58: every placeholder is a correctly quoted key of a YAML values skeleton, in template order, once."""
    template = '{{plain}} {{say "hi": it\'s}} {{plain}} {{multi\nline}}\n'
    data = yaml.safe_load(keys_skeleton(template))
    assert list(data["values"]) == ["plain", 'say "hi": it\'s', "multi\nline"]
    assert all(isinstance(v, str) for v in data["values"].values())
    version = template_version(TEMPLATE)
    assert yaml.safe_load(keys_skeleton(TEMPLATE))["values"]["template-version"] == version


def _workspace(repo: Repo, template: str = TEMPLATE) -> None:
    version = template_version(template)
    repo.write(
        {
            "t/template.md": template,
            ".gate/agents.yml": yaml.safe_dump(
                {"template": "t/template.md", "output": "AGENTS.md", "values": _values(version)}
            ),
            "pyproject.toml": '[tool.uv.workspace]\nmembers = ["pkg"]\n',
            "pkg/pyproject.toml": '[project]\nname = "pkg"\n',
            "pkg/.gate/agents.yml": yaml.safe_dump(
                {"template": "../t/template.md", "output": "AGENTS.md", "values": _values(version, name="pkg-two")}
            ),
        }
    )


def test_render_command_writes_and_all(repo: Repo) -> None:
    _workspace(repo)
    assert repo.run(["agents", "render"]).code == 0
    assert (repo.root / "AGENTS.md").read_text(encoding="utf-8").startswith("# pkg\n")
    assert not (repo.root / "pkg/AGENTS.md").exists()
    assert repo.run(["agents", "render", "--package", "pkg"]).code == 0
    assert (repo.root / "pkg/AGENTS.md").read_text(encoding="utf-8").startswith("# pkg-two\n")
    (repo.root / "AGENTS.md").unlink()
    assert repo.run(["agents", "render", "--all"]).code == 0
    assert (repo.root / "AGENTS.md").is_file()


def test_render_command_writes_nothing_on_error(repo: Repo) -> None:
    _workspace(repo)
    broken = yaml.safe_load((repo.root / "pkg/.gate/agents.yml").read_text(encoding="utf-8"))
    broken["values"]["extra"] = "x"
    (repo.root / "pkg/.gate/agents.yml").write_text(yaml.safe_dump(broken), encoding="utf-8")
    result = repo.run(["agents", "render", "--all"])
    assert result.code == 1
    assert "AG002" in result.err
    assert not (repo.root / "AGENTS.md").exists()
    assert not (repo.root / "pkg/AGENTS.md").exists()


def test_render_rejects_template_outside_root(repo: Repo) -> None:
    _workspace(repo)
    config = yaml.safe_load((repo.root / ".gate/agents.yml").read_text(encoding="utf-8"))
    config["template"] = "../outside.md"
    (repo.root / ".gate/agents.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    assert repo.run(["agents", "render"]).code == 2
    assert not (repo.root / "AGENTS.md").exists()


def test_keys_command_prints_skeleton(repo: Repo) -> None:
    _workspace(repo)
    result = repo.run(["agents", "keys", "t/template.md"])
    assert result.code == 0
    assert list(yaml.safe_load(result.out)["values"]) == ["name", "template-version", "optional rows", "a\nb"]
    assert json.dumps("a\nb") in result.out
