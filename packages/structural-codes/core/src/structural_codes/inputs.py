"""Check inputs and the bounded and unbounded field helpers (spec 0001 section 4.3; 04-tool-contract section 7).

Purpose: `CheckInputs` is the base of a check's flat scalar input model. Every numeric field has physical bounds with
a source (`bounded`) or a stated reason for having none (`unbounded`). Bounds are physical limits, never code limits
(those are preconditions). Units: the field's unit; a `Cited` bound must carry the same unit.
Errors: `CheckDefinitionError` for a wrong definition; `validate_input` raises `OUT_OF_RANGE` and nothing is clamped.
"""

import dataclasses
import types
from enum import StrEnum
from typing import Any, Literal, Union, get_args, get_origin

from eng_contract.cited import Cited
from eng_contract.params import ContractDefinitionError, ParamModel, ParamSpec, eng_param
from eng_contract.verdicts import Verdict
from pydantic import Field

from structural_codes.errors import CheckDefinitionError

__all__ = ["CheckInputs", "bounded", "check_inputs_definition", "unbounded"]

# The bounds of the reserved `ratio_limit`: above zero, at most the contract default (04-tool-contract section 5.1).
_ZERO = Cited(value=0, unit="1", source="04-tool-contract section 5.1: ratio_limit is greater than zero")
_CONTRACT_DEFAULT = Cited(
    value=Verdict.model_fields["ratio_limit"].default,
    unit="1",
    source="04-tool-contract section 5.1: ratio_limit does not exceed the contract default",
)
_BOUND_KEYS = ("ge", "gt", "le", "lt")


@dataclasses.dataclass(frozen=True, slots=True)
class _UnboundedSpec(ParamSpec):
    """`ParamSpec` of an unbounded field; the schema gets `x-unbounded-reason`."""

    reason: str = ""

    def __call__(self, schema: dict[str, Any]) -> None:
        """Annotate the schema as `ParamSpec` does, then add the reason."""
        ParamSpec.__call__(self, schema)
        schema["x-unbounded-reason"] = self.reason


def bounded(
    *, ge: Cited | None = None, gt: Cited | None = None, le: Cited | None = None, lt: Cited | None = None, **kwargs: Any
) -> Any:
    """Declare a numeric field with cited physical bounds; `bounds_source` joins the citations' sources.

    `kwargs` go to `eng_param` (`unit`, `ref_capable`, a default, ...).

    Raises:
        CheckDefinitionError: no bound given, or a cited unit that differs from `unit` (a missing `unit` is none).
    """
    given = {key: c for key, c in {"ge": ge, "gt": gt, "le": le, "lt": lt}.items() if c is not None}
    if not given:
        raise CheckDefinitionError("bounded() needs at least one cited bound")
    for key, c in given.items():
        if c.unit != kwargs.get("unit"):
            raise CheckDefinitionError(f"bound {key} has unit {c.unit!r}, the field has {kwargs.get('unit')!r}")
    source = "; ".join(dict.fromkeys(c.source for c in given.values()))
    fields: dict[str, Any] = {key: float(c.value) for key, c in given.items()}
    return eng_param(**kwargs, bounds_source=source, **fields)


def unbounded(*, reason: str, **kwargs: Any) -> Any:
    """Declare a numeric field with no physical bound (for example a signed force); `reason` says why.

    Raises:
        CheckDefinitionError: `reason` is empty or blank.
    """
    if not reason.strip():
        raise CheckDefinitionError("unbounded() needs a non-blank reason")
    given = [key for key in (*_BOUND_KEYS, "bounds_source") if key in kwargs]
    if given:
        raise CheckDefinitionError(f"unbounded() takes no bounds, got {', '.join(given)}")
    default = kwargs.pop("default", ...)
    kwargs["ref_kinds"] = frozenset(kwargs.get("ref_kinds", ()))
    return Field(default, json_schema_extra=_UnboundedSpec(**kwargs, reason=reason))


def _scalar(annotation: Any) -> tuple[bool, bool]:
    """Return (is a scalar type, is numeric) for a field annotation; `X | None` counts as `X`."""
    if get_origin(annotation) in (Union, types.UnionType):
        parts = [a for a in get_args(annotation) if a is not type(None)]
        return _scalar(parts[0]) if len(parts) == 1 else (False, False)
    if get_origin(annotation) is Literal or annotation is bool:
        return True, False
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        return True, False
    numeric = annotation in (int, float)
    return numeric, numeric


def check_inputs_definition(model_cls: type) -> None:
    """Check the definition rules of AC3 for an input model.

    Raises:
        CheckDefinitionError: not a `CheckInputs` subclass, a non-scalar field, or a numeric field with neither
            bounds (with `bounds_source`) nor an `unbounded` reason.
    """
    if not (isinstance(model_cls, type) and issubclass(model_cls, CheckInputs)):
        raise CheckDefinitionError(f"{model_cls!r} is not a CheckInputs subclass")
    for name, info in model_cls.model_fields.items():
        scalar, numeric = _scalar(info.annotation)
        if not scalar:
            raise CheckDefinitionError(f"{name}: only float, int, bool, StrEnum and Literal fields are allowed")
        spec = info.json_schema_extra
        has_bounds = isinstance(spec, ParamSpec) and any(getattr(spec, k) is not None for k in _BOUND_KEYS)
        if numeric and not (isinstance(spec, _UnboundedSpec) or has_bounds):
            raise CheckDefinitionError(f"{name}: a numeric field needs bounds or an unbounded reason")


class CheckInputs(ParamModel):
    """Base of a check's inputs; `ratio_limit` is the reserved design-basis limit (null: the contract default)."""

    ratio_limit: float | None = eng_param(
        None,
        unit="1",
        gt=_ZERO.value,
        le=_CONTRACT_DEFAULT.value,
        bounds_source=f"{_ZERO.source}; {_CONTRACT_DEFAULT.source}",
        ref_capable=True,
        engineering_quantity=True,
    )

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """Check the definition rules when a subclass is created.

        Raises:
            CheckDefinitionError: a wrong field definition (see `check_inputs_definition`).
        """
        try:
            super().__pydantic_init_subclass__(**kwargs)
        except ContractDefinitionError as exc:
            raise CheckDefinitionError(str(exc)) from exc
        check_inputs_definition(cls)
