"""Input-parameter metadata and input validation (spec 4.1 and 5; 04 section 7).

Purpose: tool authors declare each parameter once (`eng_param`) and get the definition checks, the published JSON
Schema (`x-eng` annotations, bounds, reference alternative) and the validation pipeline (`validate_input`) from it.
Units: unit symbols of `units`; bounds are in the parameter's unit and are physical limits, not code limits.
Errors: `ContractDefinitionError` for a wrong definition (a programming error); `ContractError` from `validate_input`
(`INVALID_ARGUMENT`, `REF_*`, `UNIT_MISMATCH`, `OUT_OF_RANGE`).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from pydantic.fields import FieldInfo

from eng_contract._types import KindName
from eng_contract._validation import invalid_from, run_pipeline
from eng_contract.envelope import LiteralInput, RefInput
from eng_contract.refs import RecordSource, Ref
from eng_contract.units import UNITS, kind_for_field

__all__ = [
    "ContractDefinitionError",
    "InputPolicy",
    "ParamModel",
    "ParamSpec",
    "ValidatedInput",
    "eng_param",
    "validate_input",
]

_KIND = TypeAdapter(KindName)
# Pydantic refuses a `$ref` it did not generate, so `model_json_schema` swaps this placeholder for the real one.
_REF_PLACEHOLDER = {"x-eng-ref": True}
_SOURCE_LENGTH = range(8, 501)


class ContractDefinitionError(Exception):
    """An input model is defined wrongly (a programming error, not an `ErrorCode`)."""


@dataclass(frozen=True, slots=True)
class ParamSpec:
    """Metadata of one parameter (spec section 5); as the field's `json_schema_extra` it annotates the schema."""

    unit: str | None = None
    ge: float | None = None
    le: float | None = None
    gt: float | None = None
    lt: float | None = None
    bounds_source: str | None = None
    ref_capable: bool = False
    ref_kinds: frozenset[str] = field(default_factory=frozenset)
    engineering_quantity: bool = False
    stale_ok: bool = False

    def __call__(self, schema: dict[str, Any]) -> None:
        """Rewrite the field's JSON Schema in place: bounds, `x-eng`, and literal-or-`Ref` `anyOf` when ref-capable."""
        keep = {k: v for k, v in schema.items() if k in ("title", "description", "default")}
        literal = {k: v for k, v in schema.items() if k not in keep}
        bounds = {"minimum": self.ge, "maximum": self.le, "exclusiveMinimum": self.gt, "exclusiveMaximum": self.lt}
        given = {key: bound for key, bound in bounds.items() if bound is not None}
        # A Quantity is an object: its bounds belong to `value`, where the numeric keywords apply.
        (literal.setdefault("properties", {}).setdefault("value", {}) if "$ref" in literal else literal).update(given)
        schema.clear()
        schema.update(keep)
        if self.ref_capable:
            schema["anyOf"] = [literal, _REF_PLACEHOLDER]
        else:
            schema.update(literal)
        schema["x-eng"] = {
            "unit": self.unit,
            "ref_capable": self.ref_capable,
            "engineering_quantity": self.engineering_quantity,
            "stale_ok": self.stale_ok,
            "bounds_source": self.bounds_source,
            "ref_kinds": sorted(self.ref_kinds),
        }


def eng_param(
    default: Any = ...,  # pydantic's required-field marker; pydantic turns it into PydanticUndefined
    *,
    unit: str | None = None,
    ge: float | None = None,
    le: float | None = None,
    gt: float | None = None,
    lt: float | None = None,
    bounds_source: str | None = None,
    ref_capable: bool = False,
    ref_kinds: frozenset[str] | set[str] = frozenset(),
    engineering_quantity: bool = False,
    stale_ok: bool = False,
) -> Any:
    """Declare a parameter's metadata as the value of a `ParamModel` field (the field's own type is the literal type).

    Bounds are not enforced by Pydantic: `validate_input` applies them after references are resolved.
    """
    spec = ParamSpec(
        unit, ge, le, gt, lt, bounds_source, ref_capable, frozenset(ref_kinds), engineering_quantity, stale_ok
    )
    return Field(default, json_schema_extra=spec)


def _spec_of(info: FieldInfo) -> ParamSpec:
    extra = info.json_schema_extra
    return extra if isinstance(extra, ParamSpec) else ParamSpec()


def _specs(model_cls: type[BaseModel]) -> Mapping[str, ParamSpec]:
    """The metadata of every field, in definition order (a field without `eng_param` has the defaults)."""
    return {name: _spec_of(info) for name, info in model_cls.model_fields.items()}


def _check_definition(name: str, spec: ParamSpec) -> None:
    """The definition rules of spec section 5: suffix and unit, bounds and source, flag dependencies."""

    def fail(why: str) -> ContractDefinitionError:
        return ContractDefinitionError(f"{name}: {why}")

    kind = kind_for_field(name)
    if spec.unit is not None and spec.unit not in UNITS:
        raise fail(f"unknown unit {spec.unit!r}")
    if kind is not None and spec.unit != kind.canonical_unit:
        raise fail(f"the suffix of the name needs unit {kind.canonical_unit!r}, not {spec.unit!r}")
    if (spec.ge is not None and spec.gt is not None) or (spec.le is not None and spec.lt is not None):
        raise fail("give one lower and one upper bound at most")
    low = spec.ge if spec.gt is None else spec.gt
    high = spec.le if spec.lt is None else spec.lt
    if low is not None and high is not None and (low > high or (low == high and (spec.gt, spec.lt) != (None, None))):
        raise fail("the bounds leave no value")
    if (low, high) != (None, None) and spec.bounds_source is None:
        raise fail("bounds need a bounds_source")
    if spec.bounds_source is not None and len(spec.bounds_source) not in _SOURCE_LENGTH:
        raise fail("bounds_source must have 8 to 500 characters")
    if not spec.ref_capable and (spec.engineering_quantity or spec.stale_ok or spec.ref_kinds):
        raise fail("engineering_quantity, stale_ok and ref_kinds need ref_capable")
    for kind_name in spec.ref_kinds:
        try:
            _KIND.validate_python(kind_name)
        except ValidationError as exc:
            raise fail(f"{kind_name!r} is not a kind name") from exc


class ParamModel(BaseModel):
    """Base class of tool input models; it checks every field's definition when subclassed."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=False)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """Check the definition rules of every field (raises `ContractDefinitionError`)."""
        super().__pydantic_init_subclass__(**kwargs)
        for name, spec in _specs(cls).items():
            _check_definition(name, spec)

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """The JSON Schema, with the `Ref` definition that ref-capable parameters point to."""
        schema = super().model_json_schema(*args, **kwargs)
        refs = [name for name, spec in _specs(cls).items() if spec.ref_capable]
        if refs:
            schema.setdefault("$defs", {})["Ref"] = Ref.model_json_schema()
            for name in refs:
                choices = schema["properties"][name]["anyOf"]
                choices[choices.index(_REF_PLACEHOLDER)] = {"$ref": "#/$defs/Ref"}
        return schema


class InputPolicy(BaseModel):
    """Policy: `require_refs` rejects literals for `engineering_quantity` parameters (04 section 3.5)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    require_refs: bool = False


@dataclass(frozen=True, slots=True)
class ValidatedInput[M: ParamModel]:
    """A validated input model and the provenance `inputs` (a reference is recorded as such, never re-typed)."""

    model: M
    inputs: Mapping[str, RefInput | LiteralInput]


def validate_input[M: ParamModel](
    model_cls: type[M],
    raw: Mapping[str, Any],
    *,
    source: RecordSource,
    current_revision: Callable[[str], int | None],
    policy: InputPolicy,
) -> ValidatedInput[M]:
    """Validate a tool's raw input in the order of 04 section 7; the first failure is raised and nothing is fixed.

    Order: shape, policy, references, units, bounds, cross-field rules (host preconditions are the caller's).

    Raises:
        ContractError: `INVALID_ARGUMENT` (shape, policy, cross-field rule), `REF_*`, `UNIT_MISMATCH` or
            `OUT_OF_RANGE`, including a quantity literal with an unknown unit symbol (`field` and `expected.unit` set).
    """
    specs = _specs(model_cls)
    values, inputs = run_pipeline(model_cls.model_fields, specs, raw, source, current_revision, policy.require_refs)
    try:
        model = model_cls.model_validate(values)
    except ValidationError as exc:
        raise invalid_from(exc) from exc
    return ValidatedInput(model, inputs)
