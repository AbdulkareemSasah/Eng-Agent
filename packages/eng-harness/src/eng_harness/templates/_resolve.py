"""Template inheritance, merge rules, ask paths and the resolved content hash (spec 0004 section 4.3, AC8 to AC11).

Purpose: turn a template and its `meta.extends` chain into one `ResolvedTemplate` with a stable identity.
Merge: mappings merge key by key; a child leaf replaces the parent's whole entry (value, unit, citation, bounds);
lists inside an entry replace as a whole; `ask_each_run` merges by `path`; a child cannot delete an inherited key.
Identity: `sha256 = payload_sha256({chain, resolved})` over the canonical JSON of the validated models, so
formatting, comments and key order never change it.
Units: none; nothing is converted. No value is added or defaulted here.
Errors: `TemplateInvalid` with reason `extends_invalid` (AC9) or `ask_has_value` (AC10).
"""

from collections.abc import Sequence
from typing import Final, Protocol

from eng_contract.canonical import payload_sha256
from pydantic import BaseModel, ConfigDict

from eng_harness.templates._model import SECTIONS, AskItem, Entry, Section, Template, TemplateInvalid

MAX_DEPTH: Final = 8  # at most eight `extends` links above the template being resolved


class TemplateSource(Protocol):
    """Where parents are found; the repository of plan task T4 implements it."""

    def find(self, name: str, version: str) -> Template | None:
        """Return the template `name@version`, or None when there is none."""
        ...


class ChainLink(BaseModel):
    """One template of the chain: its identity and the hash of its own validated model."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    version: str
    file_sha256: str


class ResolvedTemplate(BaseModel):
    """The merged template, the chain it came from (child first) and the `sha256` that identifies both."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    template: Template
    chain: tuple[ChainLink, ...]
    sha256: str


def _dump(template: Template) -> object:
    return template.model_dump(mode="json")


def _link(template: Template) -> ChainLink:
    return ChainLink(
        name=template.meta.name, version=template.meta.version, file_sha256=payload_sha256(_dump(template))
    )


def _parent_key(template: Template) -> tuple[str, str] | None:
    """The `(name, version)` named by `extends`; `extends_invalid` when it has no exact version."""
    extends = template.meta.extends
    if extends is None:
        return None
    name, separator, version = extends.partition("@")
    if not (name and separator and version):
        raise TemplateInvalid("extends_invalid", "meta.extends")
    return name, version


def _chain_of(template: Template, source: TemplateSource) -> list[Template]:
    """The template and its ancestors, child first; refuses a missing parent, a cycle and depth over `MAX_DEPTH`."""
    chain = [template]
    seen = {(template.meta.name, template.meta.version)}
    key = _parent_key(template)
    while key is not None:
        parent = source.find(*key)
        if parent is None or key in seen or len(chain) > MAX_DEPTH:
            raise TemplateInvalid("extends_invalid", "meta.extends")
        if (parent.meta.name, parent.meta.version) != key:
            raise TemplateInvalid("extends_invalid", "meta.extends")
        seen.add(key)
        chain.append(parent)
        key = _parent_key(parent)
    return chain


def _merge(parent: Section, child: Section, path: str) -> Section:
    """Merge two groups: the child's leaf replaces the parent's entry whole; a leaf and a group never swap."""
    merged = dict(parent)
    for key, node in child.items():
        here = f"{path}.{key}"
        inherited = parent.get(key)
        if inherited is None or (isinstance(inherited, Entry) and isinstance(node, Entry)):
            merged[key] = node
        elif isinstance(inherited, dict) and isinstance(node, dict):
            merged[key] = _merge(inherited, node, here)
        else:
            raise TemplateInvalid("extends_invalid", here)  # an entry and a group cannot replace each other
    return merged


def _merge_asks(parent: Sequence[AskItem], child: Sequence[AskItem]) -> list[AskItem]:
    """Merge by `path`: a child item replaces the parent's item in place; new items follow."""
    replaced = {item.path: item for item in child}
    merged = [replaced.pop(item.path, item) for item in parent]
    merged.extend(replaced.values())
    return merged


def _entry_at(template: Template, path: str) -> bool:
    """True when `path` (section first) leads to an entry."""
    node: object = {name: getattr(template, name) for name in SECTIONS}
    for part in path.split("."):
        if isinstance(node, Entry) or not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return isinstance(node, Entry)


def _check_asks(template: Template) -> None:
    """Refuse a path asked twice and a path that also has an entry with a value (AC10)."""
    paths = [item.path for item in template.ask_each_run]
    for index, path in enumerate(paths):
        if path in paths[:index] or _entry_at(template, path):
            raise TemplateInvalid("ask_has_value", path)


def resolve(template: Template, source: TemplateSource) -> ResolvedTemplate:
    """Resolve `template` against its `extends` chain found in `source`.

    Raises:
        TemplateInvalid: `extends_invalid` (missing parent, no exact version, cycle, depth over 8, an entry and a
            group in the same place) or `ask_has_value` (a path asked twice or also holding a value).
    """
    chain = _chain_of(template, source)
    for link in chain:
        _check_asks(link)  # a duplicate inside one file must be seen before the by-path merge hides it
    merged = chain[-1]
    for child in reversed(chain[:-1]):
        sections = {name: _merge(getattr(merged, name), getattr(child, name), name) for name in SECTIONS}
        asks = _merge_asks(merged.ask_each_run, child.ask_each_run)
        merged = Template.model_validate({"meta": child.meta, "ask_each_run": asks, **sections})
    _check_asks(merged)
    links = tuple(_link(item) for item in chain)
    identity = {"chain": [link.model_dump() for link in links], "resolved": _dump(merged)}
    return ResolvedTemplate(template=merged, chain=links, sha256=payload_sha256(identity))
