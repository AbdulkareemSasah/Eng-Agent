"""Shipped templates (spec 0004 AC29): no value, all load, hash pinned, none synthetic."""

import json
from pathlib import Path

import eng_harness.templates as templates_pkg
from eng_harness.templates import Entry, TemplateRepository, resolve
from eng_harness.templates._model import SECTIONS

SHIPPED = Path(templates_pkg.__file__).resolve().parent / "shipped"
PIN = Path(__file__).resolve().parents[1] / "data" / "golden" / "shipped_templates.json"


def _entries(node: object) -> list[Entry]:
    if isinstance(node, Entry):
        return [node]
    if isinstance(node, dict):
        return [e for child in node.values() for e in _entries(child)]
    return []


def test_shipped_templates_pinned() -> None:
    pinned = json.loads(PIN.read_text(encoding="utf-8"))["templates"]
    files = sorted(p.name for p in SHIPPED.glob("*.template.yaml"))
    assert files == sorted(pinned)
    repository = TemplateRepository(SHIPPED, SHIPPED.parent / "no-user-folder")
    listed = repository.list()  # every shipped file loads; a synthetic one would be refused here
    assert len(listed) == len(files)
    for template in listed:
        assert template.meta.synthetic is False
        assert template.meta.status == "draft"
        assert not any(_entries(getattr(template, name)) for name in SECTIONS)  # structure and asks only
        resolved = resolve(template, repository)
        assert resolved.sha256 == pinned[f"{template.meta.name}-{template.meta.version}.template.yaml"]
