"""Arguments of a host call from neutral kinds and references (plan 0002 T8; spec 0002 section 4.5.2, AC18).

Purpose: the framework steps around a tool's builder: validate the canonical input before any host call (references
resolved through `eng_contract`, engineering quantities only as references), convert its quantities to the units of
the CSI units token the call passes, and add the explicit target, the token and `confirm` to the host arguments.
Units: canonical units in; the units of the CSI units system out (`eng_contract.units`, never by hand).
Errors: `ContractError` (`INVALID_ARGUMENT`, `REF_*`, `UNIT_MISMATCH`, `OUT_OF_RANGE`); `UnitError` and
`UnitGapError` (`UNIT_MISMATCH`) for a units system that is unknown, a gap (`Ton_*`) or does not fix a quantity.
"""

from collections.abc import Callable, Mapping

from eng_contract.envelope import LiteralInput, RefInput
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import InputPolicy, ParamModel, ParamSpec, ValidatedInput, validate_input
from eng_contract.quantity import Quantity
from eng_contract.refs import RecordSource, parse_ref
from eng_contract.units import QUANTITY_KINDS, UNITS, CsiUnitSystem, UnitError, convert, csi_unit_system
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from eng_harness.adapters._descriptors import ToolDescriptor

__all__ = ["HostTarget", "convert_quantities", "host_arguments", "referenced_results", "validate_call"]

_POLICY = InputPolicy(require_refs=True)  # engineering quantities are references (11 section 6 item 2)
_RESERVED = ("target", "confirm", "units")  # set by `host_arguments` only
# Quantity kind to the `CsiUnitSystem` member that fixes its unit; an area load is a stress (force per length squared).
_SYSTEM_MEMBER = {
    **{name: name for name in ("length", "area", "section_modulus", "second_moment", "force", "moment", "stress")},
    **{name: name for name in ("line_load", "unit_weight", "temperature")},
    "area_load": "stress",
}


class HostTarget(BaseModel):
    """The instance a call acts on: always sent, so the session's current target is never used (Sasaah
    `TargetResolver.cs` falls back to it when `target` is missing)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    product: str = Field(min_length=1)
    pid: int = Field(ge=1)


def referenced_results(inputs: Mapping[str, RefInput | LiteralInput]) -> tuple[str, ...]:
    """Result ids of the references among `inputs`, in input order and without repeats (the parents of a result)."""
    ids = (parse_ref(i.ref)[0] for i in inputs.values() if isinstance(i, RefInput))
    return tuple(dict.fromkeys(ids))


def validate_call[M: ParamModel](
    model_cls: type[M],
    raw: Mapping[str, object],
    *,
    source: RecordSource,
    current_revision: Callable[[str], int | None],
) -> ValidatedInput[M]:
    """Validate canonical arguments before any host call; values are never changed.

    `current_revision(model_id)` gives the adapter's revision of a model (`None` for one it does not track).

    Raises:
        ContractError: the first failure of the contract pipeline (shape, policy, references, units, bounds).
    """
    return validate_input(model_cls, raw, source=source, current_revision=current_revision, policy=_POLICY)


def _host_unit(field: str, unit: str, system: CsiUnitSystem) -> str:
    dimension = UNITS[unit].dimension
    kind = next((k for k in QUANTITY_KINDS.values() if k.dimension == dimension), None)
    if kind is not None and kind.name == "dimensionless":
        return unit
    member = _SYSTEM_MEMBER.get(kind.name) if kind else None
    if member is None:
        raise UnitError(f"units system {system.name} does not fix the unit of {field}", received=unit)
    return str(getattr(system, member))


def convert_quantities(model: ParamModel, units_system: str) -> dict[str, float]:
    """Every set quantity field of `model`, converted from its canonical unit to the units of `units_system`.

    Raises:
        UnitGapError: a `Ton_*` system (contract gap G-1).
        UnitError: the system is unknown, or it does not fix the unit of a quantity (an angle, a mass, a time).
    """
    system = csi_unit_system(units_system)
    converted: dict[str, float] = {}
    for name, info in type(model).model_fields.items():
        spec, value = info.json_schema_extra, getattr(model, name)
        if not isinstance(spec, ParamSpec) or spec.unit is None or value is None:
            continue
        number = value.value if isinstance(value, Quantity) else value
        converted[name] = convert(number, spec.unit, _host_unit(name, spec.unit, system))
    return converted


def host_arguments(
    descriptor: ToolDescriptor,
    args: Mapping[str, JsonValue],
    *,
    target: HostTarget,
    units_system: str | None = None,
    approved: bool = False,
    owned: bool = False,
) -> dict[str, JsonValue]:
    """The builder's host arguments plus `target`, `units` (a `token` tool always passes it) and `confirm`.

    `confirm: true` is set only for a tool that needs it, under an approval (`approved`), and for an `owned` tool
    also on an instance the harness launched (`owned`); otherwise it is left out and the host refuses.

    Raises:
        ContractError: `INVALID_ARGUMENT` when `args` sets a key of the framework or a `token` tool has no system.
        UnitGapError, UnitError: as for `convert_quantities`.
    """
    for key in _RESERVED:
        if key in args:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, f"{key} is set by the framework, not by a builder", field=key
            )
    sent: dict[str, JsonValue] = dict(args)
    if descriptor.units == "token":
        if units_system is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{descriptor.name} takes a units token", field="units")
        csi_unit_system(units_system)
        sent["units"] = units_system
    sent["target"] = {"product": target.product, "pid": target.pid}
    if approved and (descriptor.confirm == "approved" or (descriptor.confirm == "owned" and owned)):
        sent["confirm"] = True
    return sent
