"""Template inheritance, merge rules, ask paths and the resolved hash (plan 0004 task T3; spec 0004 AC8 to AC11).

All templates are synthetic: every value is a placeholder, not an engineering value.
"""

from typing import Any

import pytest

from eng_harness.templates import Entry, Meta, Template, TemplateInvalid
from eng_harness.templates._resolve import resolve

CITE = "Synthetic placeholder, not an engineering value"
CITE_CHILD = "Synthetic child placeholder, not an engineering value"


def _entry(value: Any, citation: str = CITE, **extra: Any) -> dict[str, Any]:
    return {"value": value, "unit": None, "citation": citation, **extra}


def _ask(path: str, label: str = "Label") -> dict[str, Any]:
    return {"path": path, "label": label, "kind": "count"}


def _data(
    name: str,
    version: str = "0.1.0",
    extends: str | None = None,
    asks: list[dict[str, Any]] | None = None,
    **sections: Any,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"name": f"synthetic-{name}", "version": version, "synthetic": True}
    if extends is not None:
        meta["extends"] = extends
    return {"schema": "eng-template/1", "meta": meta, "ask_each_run": asks or [], **sections}


def _template(data: dict[str, Any]) -> Template:
    return Template.from_data(data)


class _Source:
    """In-memory template source keyed by name and version."""

    def __init__(self, *templates: Template) -> None:
        self._by_key = {(t.meta.name, t.meta.version): t for t in templates}

    def find(self, name: str, version: str) -> Template | None:
        return self._by_key.get((name, version))


def _leaf(node: Any, *keys: str) -> Entry:
    for key in keys:
        node = node[key]
    assert isinstance(node, Entry)
    return node


def _parent_data() -> dict[str, Any]:
    return _data(
        "parent",
        materials={
            "g": {
                "a": _entry(1),
                "b": _entry(2, bounds={"min": {"value": 0, "unit": "1", "source": "Synthetic bound"}}),
                "lst": _entry([1, 2, 3]),
            }
        },
        sections={"s": {"x": _entry(5)}},
        asks=[_ask("analysis.p1", "One"), _ask("analysis.p2", "Two")],
    )


def test_merge_rules() -> None:
    parent = _template(_parent_data())
    child = _template(
        _data(
            "child",
            extends="synthetic-parent@0.1.0",
            materials={"g": {"b": _entry(20, CITE_CHILD), "c": _entry(3), "lst": _entry([9])}},
            asks=[_ask("analysis.p2", "Two changed"), _ask("analysis.p3", "Three")],
        )
    )
    resolved = resolve(child, _Source(parent, child)).template
    group = resolved.materials["g"]
    assert _leaf(group, "a").value == 1  # inherited untouched
    replaced = _leaf(group, "b")
    assert (replaced.value, replaced.citation, replaced.bounds) == (20, CITE_CHILD, None)  # whole entry replaced
    assert _leaf(group, "c").value == 3
    assert _leaf(group, "lst").value == [9]  # lists replace as a whole
    assert _leaf(resolved.sections, "s", "x").value == 5
    assert [(a.path, a.label) for a in resolved.ask_each_run] == [
        ("analysis.p1", "One"),
        ("analysis.p2", "Two changed"),
        ("analysis.p3", "Three"),
    ]
    assert resolved.meta.name == "synthetic-child"
    assert isinstance(resolved.meta, Meta)


def test_merge_cannot_delete_an_inherited_key() -> None:
    parent = _template(_parent_data())
    child = _template(_data("child", extends="synthetic-parent@0.1.0", materials={"g": {"a": {"deeper": _entry(1)}}}))
    with pytest.raises(TemplateInvalid) as caught:
        resolve(child, _Source(parent, child))
    assert caught.value.reason == "extends_invalid"
    assert caught.value.path == "materials.g.a"


def test_resolving_a_template_without_extends_returns_it() -> None:
    parent = _template(_parent_data())
    resolved = resolve(parent, _Source(parent))
    assert resolved.template == parent
    assert [(link.name, link.version) for link in resolved.chain] == [("synthetic-parent", "0.1.0")]


def _chain(length: int) -> tuple[Template, list[Template]]:
    """Templates t0 (root) to t{length}; each extends the one before. Returns the last and all."""
    made = [_template(_data("t0", materials={"g": {"a": _entry(1)}}))]
    for index in range(1, length + 1):
        made.append(_template(_data(f"t{index}", extends=f"synthetic-t{index - 1}@0.1.0")))
    return made[-1], made


def test_extends_errors() -> None:
    child = _template(_data("child", extends="synthetic-parent@0.1.0"))
    other_version = _template(_data("parent", version="0.2.0"))

    def refused(start: Template, *known: Template) -> TemplateInvalid:
        with pytest.raises(TemplateInvalid) as caught:
            resolve(start, _Source(start, *known))
        return caught.value

    assert refused(child).reason == "extends_invalid"  # parent missing
    missing = refused(child, other_version)  # version not found
    assert (missing.reason, missing.path) == ("extends_invalid", "meta.extends")
    first = _template(_data("a", extends="synthetic-b@0.1.0"))
    second = _template(_data("b", extends="synthetic-a@0.1.0"))
    assert refused(first, second).reason == "extends_invalid"  # cycle
    selfish = _template(_data("a", extends="synthetic-a@0.1.0"))
    assert refused(selfish).reason == "extends_invalid"
    # No exact version: the model refuses it at load; resolve defends against a model built without validation.
    unpinned = Template.model_construct(
        meta=Meta.model_construct(name="synthetic-x", version="0.1.0", extends="synthetic-y")
    )
    assert refused(unpinned).reason == "extends_invalid"

    deepest_ok, all_ok = _chain(8)  # eight links of extends
    assert resolve(deepest_ok, _Source(*all_ok)).template.materials["g"]
    too_deep, all_deep = _chain(9)
    assert refused(too_deep, *all_deep).reason == "extends_invalid"


def test_ask_paths_carry_no_value() -> None:
    def refused(data: dict[str, Any], *known: Template) -> TemplateInvalid:
        template = _template(data)
        with pytest.raises(TemplateInvalid) as caught:
            resolve(template, _Source(template, *known))
        return caught.value

    valued = refused(_data("one", materials={"g": {"a": _entry(1)}}, asks=[_ask("materials.g.a")]))
    assert (valued.reason, valued.path) == ("ask_has_value", "materials.g.a")
    twice = refused(_data("two", asks=[_ask("analysis.n"), _ask("analysis.n", "Again")]))
    assert (twice.reason, twice.path) == ("ask_has_value", "analysis.n")
    parent = _template(_data("parent", asks=[_ask("analysis.n")]))
    # the child sets a value for a path the parent asks
    inherited = refused(_data("kid", extends="synthetic-parent@0.1.0", analysis={"n": _entry(4)}), parent)
    assert (inherited.reason, inherited.path) == ("ask_has_value", "analysis.n")
    fine = _template(_data("fine", analysis={"m": _entry(1)}, asks=[_ask("analysis.n")]))
    assert resolve(fine, _Source(fine)).template.ask_each_run[0].path == "analysis.n"


def _hash(data: dict[str, Any], *parents: dict[str, Any]) -> str:
    template = _template(data)
    return resolve(template, _Source(template, *(_template(p) for p in parents))).sha256


def test_content_hash_stable() -> None:
    parent = _parent_data()
    child = _data("child", extends="synthetic-parent@0.1.0", materials={"g": {"c": _entry(3)}})
    base = _hash(child, parent)
    assert len(base) == 64
    assert base == _hash(child, parent)

    reordered_parent = {key: parent[key] for key in reversed(list(parent))}
    reordered_parent["materials"] = {"g": {key: parent["materials"]["g"][key] for key in ("lst", "b", "a")}}
    reordered_child = {key: child[key] for key in reversed(list(child))}
    reordered_child["meta"] = dict(reversed(list(child["meta"].items())))
    assert _hash(reordered_child, reordered_parent) == base  # key order never changes identity

    changed_value = {**child, "materials": {"g": {"c": _entry(4)}}}
    changed_citation = {**child, "materials": {"g": {"c": _entry(3, CITE_CHILD)}}}
    changed_parent = {**parent, "sections": {"s": {"x": _entry(6)}}}
    hashes = {
        base,
        _hash(changed_value, parent),
        _hash(changed_citation, parent),
        _hash(child, changed_parent),
    }
    assert len(hashes) == 4

    chain = resolve(_template(child), _Source(_template(child), _template(parent))).chain
    assert [(link.name, link.version) for link in chain] == [
        ("synthetic-child", "0.1.0"),
        ("synthetic-parent", "0.1.0"),
    ]
    assert all(len(link.file_sha256) == 64 for link in chain)
