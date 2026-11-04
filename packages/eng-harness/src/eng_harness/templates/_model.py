"""Template model: sections, entries, citations, canonical units and bounds (spec 0004 section 4.2).

Purpose: validate the data of one `eng-template/1` file into frozen models. No YAML is read here and nothing is
evaluated; a string value is only a string. No engineering value, bound or default is held here: the checks are
structural (citation, unit suffix, finiteness, the entry's own bounds, key shapes).
Units: the unit of an entry is the canonical unit of its key's suffix (contract 4.7.2) or null; nothing is converted.
Errors: `TemplateInvalid` (contract code INVALID_ARGUMENT) with a `reason` key, the offending `path` and the `file`.
"""

import math
import re
from collections.abc import Mapping
from typing import Annotated, Final, Literal, Self, cast

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.units import UnitError, kind_for_field
from pydantic import BaseModel, ConfigDict, JsonValue, StrictBool, StringConstraints, ValidationError, model_validator

Reason = Literal[
    "yaml_invalid",
    "unknown_key",
    "meta_invalid",
    "citation_missing",
    "unit_mismatch",
    "value_invalid",
    "out_of_bounds",
    "bounds_invalid",
    "ask_has_value",
    "extends_invalid",
    "synthetic_not_allowed",
    "not_found",
]

SCHEMA: Final = "eng-template/1"
SECTIONS = ("materials", "sections", "loads", "combinations", "limits", "analysis", "modeling", "drawing")
_SEGMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")  # contract FieldPath name rule (spec Q1)
_NAME = r"^[a-z][a-z0-9_-]{0,63}$"
_SEMVER = (  # Semantic Versioning 2.0.0, section 2 of semver.org
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*)?"
    r"(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?"
)
_FILE = re.compile(rf"^({_NAME[1:-1]})-({_SEMVER})\.template\.yaml$")
_MODEL = ConfigDict(frozen=True, extra="forbid")


class TemplateInvalid(ContractError):  # noqa: N818  # B-155: the name is fixed by spec 0004 section 6
    """A template file or its data breaks a rule of spec 0004; `reason` is the key, `path` the offending entry."""

    def __init__(self, reason: Reason, path: str, file: str | None = None) -> None:
        """Build the error; the message holds only the reason key and the path, never file contents."""
        self.reason: Reason = reason
        self.path = path
        self.file = file
        super().__init__(ErrorCode.INVALID_ARGUMENT, f"template invalid: {reason} at {path or '<root>'}")


class Bounds(BaseModel):
    """Inclusive limits of a numeric entry; each limit is a `Cited` so it has its own source and unit."""

    model_config = _MODEL
    min: Cited | None = None
    max: Cited | None = None


class Entry(BaseModel):
    """A leaf: JSON `value` (never null), canonical `unit` or null, `citation` (8 to 500 characters), `bounds`."""

    model_config = _MODEL
    value: JsonValue
    unit: str | None
    citation: str
    bounds: Bounds | None = None


class CodePack(BaseModel):
    """Code pack the template is written for; recorded, not checked until phase 2."""

    model_config = _MODEL
    name: Annotated[str, StringConstraints(strict=True, max_length=200)]
    edition: Annotated[str, StringConstraints(strict=True, max_length=200)]


class Meta(BaseModel):
    """Identity and status of a template (spec 4.2); `synthetic` and the `synthetic-` name prefix imply each other."""

    model_config = _MODEL
    name: Annotated[str, StringConstraints(strict=True, pattern=_NAME)]
    version: Annotated[str, StringConstraints(strict=True, pattern=f"^{_SEMVER}$")]
    description: Annotated[str, StringConstraints(strict=True, max_length=500)] = ""
    author: Annotated[str, StringConstraints(strict=True, max_length=200)] = ""
    code_pack: CodePack | None = None
    status: Literal["draft", "approved"] = "draft"
    synthetic: StrictBool = False
    extends: Annotated[str, StringConstraints(strict=True, pattern=f"{_NAME[:-1]}@{_SEMVER}$")] | None = None

    @model_validator(mode="after")
    def _synthetic_matches_name(self) -> Self:
        if self.synthetic is not self.name.startswith("synthetic-"):
            raise ValueError("synthetic: true and the synthetic- name prefix go together")
        return self


class AskItem(BaseModel):
    """A value the engineer is asked for at each run; carries no value (rules as `FieldSpec`, spec 4.5)."""

    model_config = _MODEL
    path: Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")]
    label: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=120)]
    kind: Literal["quantity", "count", "choice", "text"]
    unit: str | None = None
    choices: list[str] | None = None
    bounds: Bounds | None = None

    @model_validator(mode="after")
    def _kind_rules(self) -> Self:
        if self.kind in ("count", "choice", "text") and self.unit is not None:
            raise ValueError("only a quantity has a unit")
        if (self.kind == "choice") is (self.choices is None) or (self.choices is not None and len(self.choices) < 2):
            raise ValueError("a choice has two or more choices and no other kind has any")
        return self


type Section = dict[str, Entry | Section]


class Template(BaseModel):
    """One validated template file. Build it with `from_data`, which applies the path-dependent rules."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)
    schema_id: Literal["eng-template/1"] = SCHEMA
    meta: Meta
    materials: Section = {}
    sections: Section = {}
    loads: Section = {}
    combinations: Section = {}
    limits: Section = {}
    analysis: Section = {}
    modeling: Section = {}
    drawing: Section = {}
    ask_each_run: list[AskItem] = []

    @property
    def is_draft(self) -> bool:
        """True when `meta.status` is `draft`."""
        return self.meta.status == "draft"

    @classmethod
    def from_data(cls, data: object, *, file_name: str | None = None) -> Self:
        """Validate parsed template data (spec AC1 to AC6); `file_name` is checked against name and version.

        Raises:
            TemplateInvalid: the first rule broken, with its reason and path.
        """
        try:
            return cls._parse(data, file_name)
        except TemplateInvalid as error:
            error.file = file_name
            raise

    @classmethod
    def _parse(cls, data: object, file_name: str | None) -> Self:
        if not isinstance(data, Mapping):
            raise TemplateInvalid("value_invalid", "")
        for key in data:
            if key not in ("schema", "meta", "ask_each_run", *SECTIONS):
                raise TemplateInvalid("unknown_key", str(key))
        if data.get("schema") != SCHEMA:
            raise TemplateInvalid("meta_invalid", "schema")
        meta = _build(Meta, data.get("meta"), "meta", "meta_invalid")
        if file_name is not None and file_name != f"{meta.name}-{meta.version}.template.yaml":
            raise TemplateInvalid("meta_invalid", "meta.name")
        trees = {name: {} if data.get(name) is None else _tree(data[name], name) for name in SECTIONS}
        raw_asks = data.get("ask_each_run") or []
        if not isinstance(raw_asks, list):
            raise TemplateInvalid("value_invalid", "ask_each_run")
        asks = [_ask(item, f"ask_each_run[{index}]") for index, item in enumerate(raw_asks)]
        return cls.model_validate({"meta": meta, "ask_each_run": asks, **trees})


def _join(path: str, key: object) -> str:
    return f"{path}.{key}" if path else str(key)


def _build[M: BaseModel](model: type[M], data: object, path: str, reason: Reason) -> M:
    """Validate `data` into `model`; an extra key gives `unknown_key`, any other failure gives `reason`."""
    try:
        return model.model_validate(data)
    except ValidationError as error:
        for found in error.errors():
            if found["type"] == "extra_forbidden":
                raise TemplateInvalid("unknown_key", ".".join([path, *map(str, found["loc"])])) from error
        raise TemplateInvalid(reason, path) from error
    except UnitError as error:
        raise TemplateInvalid(reason, path) from error


def _canonical_unit(key: str) -> str | None:
    kind = kind_for_field(key)
    return kind.canonical_unit if kind else None


def _ask(item: object, path: str) -> AskItem:
    ask = _build(AskItem, item, path, "value_invalid")
    if ask.kind == "quantity" and (ask.unit is None or ask.unit != _canonical_unit(ask.path.rpartition(".")[2])):
        raise TemplateInvalid("unit_mismatch", path)
    return ask


def _tree(node: object, path: str) -> Section:
    """Walk a group; a mapping with `citation` or `value` is an entry (spec 4.2 [added], widened to report AC2)."""
    if not isinstance(node, Mapping):
        raise TemplateInvalid("value_invalid", path)
    out: Section = {}
    for key, child in node.items():
        here = _join(path, key)
        if not (isinstance(key, str) and _SEGMENT.fullmatch(key)):
            raise TemplateInvalid("unknown_key", here)
        if not isinstance(child, Mapping):
            raise TemplateInvalid("value_invalid", here)
        out[key] = _entry(child, key, here) if "citation" in child or "value" in child else _tree(child, here)
    return out


def _json_ok(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(item is None or _json_ok(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and (v is None or _json_ok(v)) for k, v in value.items())
    return isinstance(value, bool | int | str)


def _entry(raw: Mapping[str, object], key: str, path: str) -> Entry:
    for name in raw:
        if name not in ("value", "unit", "citation", "bounds"):
            raise TemplateInvalid("unknown_key", _join(path, name))
    citation, unit, value = raw.get("citation"), raw.get("unit"), raw.get("value")
    if not isinstance(citation, str) or not 8 <= len(citation) <= 500 or not citation.strip():
        raise TemplateInvalid("citation_missing", path)
    if unit != _canonical_unit(key):
        raise TemplateInvalid("unit_mismatch", path)
    number = value if isinstance(value, int | float) and not isinstance(value, bool) else None
    if value is None or not _json_ok(value) or (kind_for_field(key) is not None and number is None):
        raise TemplateInvalid("value_invalid", path)
    bounds = None if "bounds" not in raw else _bounds(raw["bounds"], unit, number, path)
    return Entry(value=cast(JsonValue, value), unit=unit, citation=citation, bounds=bounds)


def _bounds(raw: object, unit: str | None, value: float | None, path: str) -> Bounds:
    """Validate the bounds of an entry: each limit `Cited` in the entry's unit, min <= max, value inside."""
    bounds = _build(Bounds, raw, path, "bounds_invalid")
    limits = [limit for limit in (bounds.min, bounds.max) if limit is not None]
    if value is None or not limits or any(limit.unit != (unit or "1") for limit in limits):
        raise TemplateInvalid("bounds_invalid", path)
    if bounds.min and bounds.max and bounds.min.value > bounds.max.value:
        raise TemplateInvalid("bounds_invalid", path)
    if (bounds.min and value < bounds.min.value) or (bounds.max and value > bounds.max.value):
        raise TemplateInvalid("out_of_bounds", path)
    return bounds
