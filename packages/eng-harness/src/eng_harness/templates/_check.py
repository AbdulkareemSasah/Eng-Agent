"""`check_template`: validate one template file and report every problem (spec 0004 AC13).

Purpose: the check behind template tooling. The file is split into pieces (head, each entry, each ask item) that are
validated on their own, so one report lists all errors; a file that cannot be read or parsed gives one error. It
raises nothing for a malformed file. Warnings: an entry or ask path not in `known_paths` (the paths the known
workflows declare); with `known_paths=None` there is no workflow knowledge and no warning. Nothing is converted or
defaulted; a path in the report is a dotted key path, the file is its base name.
"""

from collections.abc import Collection, Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from eng_harness.templates._model import SCHEMA, SECTIONS, Template, TemplateInvalid
from eng_harness.templates._resolve import TemplateSource, _check_asks, resolve
from eng_harness.templates._yaml import load_strict

_PLACEHOLDER = {"name": "synthetic-check", "version": "0.0.0", "synthetic": True}
_PROBE = {"value": "x", "unit": None, "citation": "Synthetic probe, not a template value"}  # makes a group non-empty


class TemplateIssue(BaseModel):
    """One error or warning: a reason key (a `TemplateInvalid` reason, or `unknown_path`) and the dotted path."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: str
    path: str


class TemplateReport(BaseModel):
    """Result of `check_template`; `ok` is true when there is no error (warnings do not fail a file)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    file: str
    errors: tuple[TemplateIssue, ...] = ()
    warnings: tuple[TemplateIssue, ...] = ()

    @property
    def ok(self) -> bool:
        """True when `errors` is empty."""
        return not self.errors


def _try(data: Mapping[str, object], file: str | None = None) -> TemplateIssue | None:
    """Validate `data` as a template (placeholder meta unless given); the issue it raises, or None."""
    try:
        Template.from_data({"schema": SCHEMA, "meta": _PLACEHOLDER, **data}, file_name=file)
    except TemplateInvalid as error:
        return TemplateIssue(reason=error.reason, path=error.path)
    return None


def _nest(keys: list[str], leaf: object) -> dict[str, object]:
    for key in reversed(keys[1:]):
        leaf = {key: leaf}
    return {keys[0]: leaf}


def _walk(node: object, keys: list[str], errors: list[TemplateIssue], leaves: list[str]) -> None:
    """Validate each entry below `keys` (section first) alone; a bad key or a non-mapping is reported where it is."""
    if not isinstance(node, Mapping):
        errors.append(TemplateIssue(reason="value_invalid", path=".".join(keys)))
        return
    if len(keys) > 1 and (issue := _try(_nest([*keys, "probe"], _PROBE))):
        errors.append(issue)  # a group key that breaks the key rule
    for key, child in node.items():
        below = [*keys, str(key)]
        if isinstance(child, Mapping) and not ("citation" in child or "value" in child):
            _walk(child, below, errors, leaves)
        elif isinstance(child, Mapping) and (issue := _try(_nest(below, child))):
            errors.append(issue)
        elif isinstance(child, Mapping):
            leaves.append(".".join(below))
        else:
            errors.append(TemplateIssue(reason="value_invalid", path=".".join(below)))


def _pieces(data: Mapping[str, object], file: str) -> tuple[list[TemplateIssue], list[str]]:
    """Errors found piece by piece, and the paths of the valid entries and ask items."""
    errors = [
        TemplateIssue(reason="unknown_key", path=str(key))
        for key in data
        if key not in ("schema", "meta", "ask_each_run", *SECTIONS)
    ]
    head = {key: data[key] for key in ("schema", "meta") if key in data}
    try:
        Template.from_data(head, file_name=file)
    except TemplateInvalid as error:
        errors.append(TemplateIssue(reason=error.reason, path=error.path))
    leaves: list[str] = []
    for section in SECTIONS:
        if data.get(section) is not None:
            _walk(data[section], [section], errors, leaves)
    asks = data.get("ask_each_run") or []
    if not isinstance(asks, list):
        return [*errors, TemplateIssue(reason="value_invalid", path="ask_each_run")], leaves
    for index, item in enumerate(asks):
        if issue := _try({"ask_each_run": [item]}):
            path = issue.path.replace("ask_each_run[0]", f"ask_each_run[{index}]", 1)
            errors.append(TemplateIssue(reason=issue.reason, path=path))
        elif isinstance(item, Mapping):
            leaves.append(str(item["path"]))
    return errors, leaves


def _whole(data: Mapping[str, object], file: str, source: TemplateSource | None) -> TemplateIssue | None:
    """Checks that need the whole template (ask paths, and the `extends` chain when a `source` is given)."""
    try:
        template = Template.from_data(data, file_name=file)
        if source is None:
            _check_asks(template)
        else:
            resolve(template, source)
    except TemplateInvalid as error:
        return TemplateIssue(reason=error.reason, path=error.path)
    return None


def check_template(
    path: Path, *, known_paths: Collection[str] | None = None, source: TemplateSource | None = None
) -> TemplateReport:
    """Check the file at `path`; never raises for its content.

    `known_paths`: paths the known workflows declare, for the warnings. `source`: where `extends` parents are found;
    without it the parent is not looked up. An `OSError` other than a missing file is not caught.
    """
    try:
        data = load_strict(path)
    except TemplateInvalid as error:
        return TemplateReport(file=path.name, errors=(TemplateIssue(reason=error.reason, path=error.path),))
    if not isinstance(data, Mapping):
        return TemplateReport(file=path.name, errors=(TemplateIssue(reason="value_invalid", path=""),))
    errors, leaves = _pieces(data, path.name)
    if not errors and (issue := _whole(data, path.name, source)):
        errors.append(issue)
    warnings = [] if known_paths is None else [p for p in leaves if p not in known_paths]
    return TemplateReport(
        file=path.name,
        errors=tuple(errors),
        warnings=tuple(TemplateIssue(reason="unknown_path", path=p) for p in warnings),
    )
