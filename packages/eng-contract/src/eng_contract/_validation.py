"""The validation pipeline of tool inputs, steps 1 to 5 of spec section 5 (internal; use `params.validate_input`).

Purpose: apply shape, policy, reference, unit and bounds checks in the order of 04 section 7 and return the values for
the model together with the provenance `inputs`. Nothing is clamped, rounded or converted.
Units: those of each parameter's `ParamSpec`. Errors: `ContractError` (`INVALID_ARGUMENT`, `REF_*`, `UNIT_MISMATCH`,
`OUT_OF_RANGE`).
"""

import json
import operator
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import TypeAdapter, ValidationError
from pydantic.fields import FieldInfo

from eng_contract._types import FieldPath
from eng_contract.envelope import LiteralInput, RefInput
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.quantity import Quantity
from eng_contract.refs import RecordSource, Ref, RefRule, resolve_ref
from eng_contract.units import UnitError

if TYPE_CHECKING:
    from eng_contract.params import ParamSpec

_PATH = TypeAdapter(FieldPath)


def _field_path(text: str) -> str | None:
    try:
        return _PATH.validate_python(text)
    except ValidationError:
        return None


def invalid_from(exc: ValidationError, prefix: str = "") -> ContractError:
    """`INVALID_ARGUMENT` for the first error of a Pydantic failure; `field` is `prefix` plus the error's location."""
    first = exc.errors(include_url=False, include_context=False, include_input=False)[0]
    path = prefix
    for part in first["loc"]:
        path += f"[{part}]" if isinstance(part, int) else (f".{part}" if path else str(part))
    return ContractError(ErrorCode.INVALID_ARGUMENT, first["msg"], field=_field_path(path))


def _shape(name: str, info: FieldInfo, value: Any, unit: str | None) -> Any:
    """Validate one value against the field's declared type, as strict JSON (no coercion: `"5"` and `true` are not
    numbers); the physical bounds and the model's validators are not applied here. A quantity with an unknown unit
    symbol is `UNIT_MISMATCH` naming the field and the parameter's `unit`."""
    declared: Any = Annotated[info.annotation, *info.metadata] if info.metadata else info.annotation
    try:
        return TypeAdapter(declared).validate_json(json.dumps(value), strict=True)
    except ValidationError as exc:
        raise invalid_from(exc, name) from exc
    except UnitError as exc:
        expected = {"unit": unit} if unit is not None else None
        raise ContractError(
            ErrorCode.UNIT_MISMATCH, exc.detail.message, field=name, expected=expected, received=exc.detail.received
        ) from exc
    except TypeError as exc:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{name} is not a JSON value", field=name) from exc


def _number(value: Any) -> float | None:
    if isinstance(value, Quantity):
        return value.value
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def _out_of_range(name: str, spec: ParamSpec, number: float) -> ContractError | None:
    bounds = [
        (key, bound, test)
        for key, bound, test in (
            ("min", spec.ge, operator.ge),
            ("exclusive_min", spec.gt, operator.gt),
            ("max", spec.le, operator.le),
            ("exclusive_max", spec.lt, operator.lt),
        )
        if bound is not None
    ]
    if all(test(number, bound) for _, bound, test in bounds):
        return None
    expected: dict[str, Any] = {key: bound for key, bound, _ in bounds}
    if spec.unit is not None:
        expected["unit"] = spec.unit
    return ContractError(
        ErrorCode.OUT_OF_RANGE, f"{name} is outside its physical bounds", field=name, expected=expected, received=number
    )


def run_pipeline(
    fields: Mapping[str, FieldInfo],
    specs: Mapping[str, ParamSpec],
    raw: Mapping[str, Any],
    source: RecordSource,
    current_revision: Callable[[str], int | None],
    require_refs: bool,
) -> tuple[dict[str, Any], dict[str, RefInput | LiteralInput]]:
    """Steps 1 to 5; returns the validated values by field and the provenance inputs of the fields given."""
    # 1. Shape: unknown and missing fields, types, well-formed references. Bounds and model validators come later.
    for key in raw:
        if key not in fields:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"unknown input {str(key)[:100]!r}",
                field=_field_path(str(key)),
                received=str(key)[:200],
            )
    for name, info in fields.items():
        if name not in raw and info.is_required():
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"missing required input {name}", field=name)
    given: dict[str, Any] = {}
    inputs: dict[str, RefInput | LiteralInput] = {}
    for name, info in fields.items():
        if name in raw:
            value = raw[name]
            if specs[name].ref_capable and isinstance(value, Mapping) and "$ref" in value:
                try:
                    given[name] = Ref.model_validate(value)
                except ValidationError as exc:
                    message = f"{name} is not a well-formed reference"
                    raise ContractError(ErrorCode.INVALID_ARGUMENT, message, field=name) from exc
            else:
                given[name] = _shape(name, info, value, specs[name].unit)
                try:
                    inputs[name] = LiteralInput(literal=value)
                except ValidationError as exc:  # NaN and infinity cannot be recorded, nor are they physical values
                    raise ContractError(
                        ErrorCode.INVALID_ARGUMENT, f"{name} is not a finite JSON value", field=name
                    ) from exc
    # 2. Policy: engineering quantities must be references.
    for name, value in given.items():
        if require_refs and specs[name].engineering_quantity and not isinstance(value, Ref):
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"{name} is an engineering quantity and must be given as a reference",
                field=name,
                hint=f"give {name} as a reference to a stored result",
            )
    # 3. References: resolved in field order, then checked like a literal.
    values: dict[str, Any] = {}
    for name, value in given.items():
        if isinstance(value, Ref):
            spec = specs[name]
            rule = RefRule(kinds=spec.ref_kinds, unit=spec.unit, stale_ok=spec.stale_ok, field=name)
            resolved = resolve_ref(value, rule, source, current_revision)
            inputs[name] = RefInput(ref=resolved.ref)
            values[name] = _shape(name, fields[name], resolved.value, spec.unit)
        else:
            values[name] = value
    # 4. Units: a quantity object must carry the parameter's unit exactly.
    for name, value in values.items():
        unit = specs[name].unit
        if isinstance(value, Quantity) and unit is not None and value.unit != unit:
            raise ContractError(
                ErrorCode.UNIT_MISMATCH,
                f"{name} must be in {unit}",
                field=name,
                expected={"unit": unit},
                received=value.unit,
            )
    # 5. Bounds on literal and resolved values.
    for name, value in values.items():
        number = _number(value)
        if number is not None and (error := _out_of_range(name, specs[name], number)):
            raise error
    return values, inputs
