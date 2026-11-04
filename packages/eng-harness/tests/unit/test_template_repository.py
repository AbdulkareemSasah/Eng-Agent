"""Template repository: shipped and user folders, ambiguity, synthetic refusal (plan 0004 T4; spec 0004 AC12).

All templates are synthetic: every value is a placeholder, not an engineering value.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from eng_harness.templates import TemplateAmbiguous, TemplateInvalid, TemplateRepository, load_template, resolve

CITE = "Synthetic placeholder, not an engineering value"


def _write(folder: Path, name: str, version: str = "0.1.0", *, synthetic: bool = True, **meta: Any) -> Path:
    """Write a template file (JSON is YAML 1.2) with a single entry; returns its path."""
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        "schema": "eng-template/1",
        "meta": {"name": name, "version": version, "synthetic": synthetic, **meta},
        "limits": {"note": {"value": "x", "unit": None, "citation": CITE}},
    }
    path = folder / f"{name}-{version}.template.yaml"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_lookup_rules(tmp_path: Path) -> None:
    shipped, user = tmp_path / "shipped", tmp_path / "user"
    _write(shipped, "plain", synthetic=False, status="approved")
    _write(shipped, "synthetic-both")
    _write(user, "synthetic-both")
    _write(user, "synthetic-mine", status="draft")
    _write(user, "synthetic-child", extends="synthetic-mine@0.1.0")
    repository = TemplateRepository(shipped, user, allow_synthetic=True)

    # found in either folder; a missing name or version is None for find and not_found for get
    assert repository.find("plain", "0.1.0") is not None
    found = repository.find("synthetic-mine", "0.1.0")
    assert found is not None
    assert found.is_draft
    assert repository.find("plain", "9.9.9") is None
    with pytest.raises(TemplateInvalid) as missing:
        repository.get("plain", "9.9.9")
    assert missing.value.reason == "not_found"
    assert repository.find("../plain", "0.1.0") is None  # a name is never a path

    # the same name and version in both folders is ambiguous; nothing shadows silently
    with pytest.raises(TemplateAmbiguous) as ambiguous:
        repository.find("synthetic-both", "0.1.0")
    assert (ambiguous.value.name, ambiguous.value.version) == ("synthetic-both", "0.1.0")

    # the repository is the source of parents for resolve
    resolved = resolve(repository.get("synthetic-child", "0.1.0"), repository)
    assert [link.name for link in resolved.chain] == ["synthetic-child", "synthetic-mine"]

    # synthetic templates are refused unless the repository is built for tests
    strict = TemplateRepository(shipped, user)
    with pytest.raises(TemplateInvalid) as refused:
        strict.get("synthetic-mine", "0.1.0")
    assert refused.value.reason == "synthetic_not_allowed"
    assert strict.get("plain", "0.1.0").meta.synthetic is False
    with pytest.raises(TemplateInvalid) as direct:
        load_template(_write(tmp_path / "x", "synthetic-direct"))
    assert direct.value.reason == "synthetic_not_allowed"
    allowed = load_template(_write(tmp_path / "y", "synthetic-direct"), allow_synthetic=True)
    assert allowed.meta.name == "synthetic-direct"


def test_listing(tmp_path: Path) -> None:
    shipped, user = tmp_path / "shipped", tmp_path / "user"
    _write(shipped, "plain", synthetic=False)
    _write(user, "mine", synthetic=False)
    (user / "notes.txt").write_text("not a template", encoding="utf-8")
    listed = TemplateRepository(shipped, user).list()
    assert [(t.meta.name, t.meta.version) for t in listed] == [("mine", "0.1.0"), ("plain", "0.1.0")]
    assert TemplateRepository(tmp_path / "none", tmp_path / "absent").list() == ()
    _write(user, "plain", synthetic=False)
    with pytest.raises(TemplateAmbiguous):
        TemplateRepository(shipped, user).list()


def test_invalid_files_are_errors_not_skipped(tmp_path: Path) -> None:
    broken = tmp_path / "user"
    broken.mkdir()
    (broken / "bad-0.1.0.template.yaml").write_text("a: 1\na: 2\n", encoding="utf-8")
    repository = TemplateRepository(tmp_path / "shipped", broken)
    with pytest.raises(TemplateInvalid) as error:
        repository.find("bad", "0.1.0")
    assert error.value.reason == "yaml_invalid"
    with pytest.raises(TemplateInvalid):
        repository.list()
