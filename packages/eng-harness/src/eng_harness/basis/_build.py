"""Basis draft: precedence, sources, citations, pending list and draft hash (spec 0004 section 4.4, AC14 to AC20).

Purpose: `build_draft` turns the workflow's `FieldSpec`s, a resolved template, the engineer's values file and detected
values into a `BasisDraft` that nothing has confirmed. Each declared field takes the first of the engineer value, the
detected value and the template value; a field with none is pending and absent; nothing is defaulted.
Units: values are canonical already; a unit other than the field's own is refused, never converted.
Errors: `BasisInvalid` with reason `unknown_field`, `field_invalid`, `confirmed_not_allowed` or `not_found`.
Identity: `sha256` is the canonical-JSON hash of the draft without itself (template, specs, fields, pending, warnings,
unused); no clock, previous basis or confirmation enters the build (AC20).
"""

import math
from collections.abc import Mapping, Sequence
from typing import Annotated, Literal, Self

from eng_contract.canonical import payload_sha256
from eng_contract.refs import RefString
from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    ModelWrapValidatorHandler,
    StringConstraints,
    ValidationError,
    model_validator,
)

from eng_harness.basis._fields import BasisInvalid, FieldSpec
from eng_harness.templates import Entry, ResolvedTemplate, Template, TemplateSource

_MODEL = ConfigDict(frozen=True, extra="forbid")


class EngineerEntry(BaseModel):
    """One value of the values file: the value and its unit (null for a count, choice or text)."""

    model_config = _MODEL
    value: JsonValue
    unit: str | None = None


class EngineerValues(BaseModel):
    """The engineer's values file (`--basis`): the proposed `name` and `values` by path. It cannot set `confirmed`."""

    model_config = _MODEL
    name: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]
    values: dict[str, EngineerEntry]

    @model_validator(mode="wrap")
    @classmethod
    def _guard(cls, data: object, handler: ModelWrapValidatorHandler[Self]) -> Self:
        """Refuse `confirmed` anywhere (`confirmed_not_allowed`) and turn any other failure into `field_invalid`."""
        if isinstance(data, Mapping):
            if "confirmed" in data:
                raise BasisInvalid("confirmed_not_allowed")
            entries = data.get("values")
            for path, entry in entries.items() if isinstance(entries, Mapping) else ():
                if isinstance(entry, Mapping) and "confirmed" in entry:
                    raise BasisInvalid("confirmed_not_allowed", str(path))
        try:
            return handler(data)
        except ValidationError as error:
            raise BasisInvalid("field_invalid") from error


class DetectedValue(BaseModel):
    """A value read from the model by the caller, already in canonical units; `ref` says where it came from."""

    model_config = _MODEL
    path: str
    value: JsonValue
    unit: str | None = None
    ref: RefString


class DraftField(BaseModel):
    """One draft value. `source` is null for a values-file value until `freeze`; `confirmed` is always false."""

    model_config = _MODEL
    value: JsonValue
    unit: str | None
    source: str | None
    origin: str | None
    citation: str | None
    confirmed: Literal[False] = False


class DraftWarning(BaseModel):
    """A detected value differs from the template's value for the same path; both are held."""

    model_config = _MODEL
    kind: Literal["detected_differs"]
    path: str
    detected: JsonValue
    template: JsonValue


class DraftTemplate(BaseModel):
    """The template the draft was built from: identity, resolved hash, chain (child first) and status."""

    model_config = _MODEL
    name: str
    version: str
    sha256: str
    chain: tuple[str, ...]
    status: Literal["draft", "approved"]
    synthetic: bool


class BasisDraft(BaseModel):
    """The unconfirmed basis: `fields` by path, `pending` required paths, `warnings`, `unused` template paths."""

    model_config = _MODEL
    template: DraftTemplate | None
    specs: tuple[FieldSpec, ...]
    fields: dict[str, DraftField]
    pending: tuple[str, ...]
    warnings: tuple[DraftWarning, ...]
    unused: tuple[str, ...]
    sha256: str


def _number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _check(spec: FieldSpec, value: JsonValue, unit: str | None) -> None:
    """Raise `field_invalid` unless `value` and `unit` fit the kind, unit, choices and cited bounds of `spec`."""
    if unit != spec.unit:
        raise BasisInvalid("field_invalid", spec.path)
    match spec.kind:
        case "quantity":
            fits = _number(value)
        case "count":
            fits = isinstance(value, int) and not isinstance(value, bool)
        case "choice":
            fits = isinstance(value, str) and value in (spec.choices or ())
        case "text":
            fits = isinstance(value, str)
    if not fits:
        raise BasisInvalid("field_invalid", spec.path)
    if isinstance(value, int | float) and (
        (spec.min is not None and value < spec.min.value) or (spec.max is not None and value > spec.max.value)
    ):
        raise BasisInvalid("field_invalid", spec.path)


def _entry(template: Template, path: str) -> Entry | None:
    """The template entry at the dotted `path`, or None when there is none (a group is not an entry)."""
    first, *rest = path.split(".")
    node: object = getattr(template, first, None)
    for key in rest:
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, Entry) else None


def _leaves(node: Mapping[str, object], path: str) -> list[str]:
    """Dotted paths of every entry under `node`."""
    found: list[str] = []
    for key, child in node.items():
        here = f"{path}.{key}"
        found += [here] if isinstance(child, Entry) else _leaves(child, here) if isinstance(child, dict) else []
    return found


def _definer(path: str, template: ResolvedTemplate, source: TemplateSource | None) -> str:
    """`template:<name>@<version>` of the nearest link of the chain that defines the entry at `path`."""
    for link in template.chain:
        parent = source.find(link.name, link.version) if source is not None else None
        if parent is None:
            raise BasisInvalid("not_found", path)
        if _entry(parent, path) is not None:
            return f"template:{link.name}@{link.version}"
    raise BasisInvalid("not_found", path)


def _check_asks(template: ResolvedTemplate, specs: Mapping[str, FieldSpec]) -> None:
    """The template's ask item cannot disagree with the workflow's `FieldSpec` on kind, unit or choices."""
    for ask in template.template.ask_each_run:
        spec = specs.get(ask.path)
        choices = tuple(ask.choices) if ask.choices is not None else None
        if spec is not None and (ask.kind, ask.unit, choices) != (spec.kind, spec.unit, spec.choices):
            raise BasisInvalid("field_invalid", ask.path)


def build_draft(
    fields: Sequence[FieldSpec],
    template: ResolvedTemplate | None,
    engineer: EngineerValues | None,
    detected: Sequence[DetectedValue],
    *,
    source: TemplateSource | None = None,
) -> BasisDraft:
    """Build the unconfirmed draft (AC14 to AC20); `source` holds the template chain for citations' defining link.

    Raises:
        BasisInvalid: `unknown_field` (a value for an undeclared path), `field_invalid` (kind, unit, choice, bounds,
            a repeated detected path, an ask item that contradicts a field), `not_found` (a template value whose
            defining link `source` cannot find).
    """
    specs = {spec.path: spec for spec in fields}
    given = engineer.values if engineer is not None else {}
    found: dict[str, DetectedValue] = {}
    for item in detected:
        if item.path in found:
            raise BasisInvalid("field_invalid", item.path)
        found[item.path] = item
    for path in (*given, *found):
        if path not in specs:
            raise BasisInvalid("unknown_field", path)
    if template is not None:
        _check_asks(template, specs)
    asked = {ask.path for ask in template.template.ask_each_run} if template is not None else set()
    rows: dict[str, DraftField] = {}
    warnings: list[DraftWarning] = []
    for path, spec in specs.items():
        entry = _entry(template.template, path) if template is not None and path not in asked else None
        if path in given:
            _check(spec, given[path].value, given[path].unit)
            rows[path] = DraftField(
                value=given[path].value,
                unit=given[path].unit,
                source=None,
                origin=f"values-file:{engineer.name if engineer else ''}",
                citation=None,
            )
        if path in found:
            _check(spec, found[path].value, found[path].unit)
            if path not in rows:
                rows[path] = DraftField(
                    value=found[path].value,
                    unit=found[path].unit,
                    source=f"model:{found[path].ref}",
                    origin=None,
                    citation=None,
                )
                if entry is not None and entry.value != found[path].value:
                    warnings.append(
                        DraftWarning(
                            kind="detected_differs", path=path, detected=found[path].value, template=entry.value
                        )
                    )
        if path not in rows and entry is not None and template is not None:
            _check(spec, entry.value, entry.unit)
            rows[path] = DraftField(
                value=entry.value,
                unit=entry.unit,
                source=_definer(path, template, source),
                origin=None,
                citation=entry.citation,
            )
    unused = (
        sorted(
            leaf
            for name in Template.model_fields
            if isinstance(node := getattr(template.template, name), dict)
            for leaf in _leaves(node, name)
            if leaf not in specs
        )
        if template is not None
        else []
    )
    head = template.template.meta if template is not None else None
    draft = BasisDraft(
        template=DraftTemplate(
            name=head.name,
            version=head.version,
            sha256=template.sha256,
            chain=tuple(f"{link.name}@{link.version}" for link in template.chain),
            status=head.status,
            synthetic=head.synthetic,
        )
        if template is not None and head is not None
        else None,
        specs=tuple(specs.values()),
        fields=rows,
        pending=tuple(path for path, spec in specs.items() if spec.required and path not in rows),
        warnings=tuple(warnings),
        unused=tuple(unused),
        sha256="0" * 64,
    )
    return draft.model_copy(update={"sha256": payload_sha256(draft.model_dump(mode="json", exclude={"sha256"}))})
