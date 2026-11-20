"""Arguments of a host call from neutral kinds and references (plan 0002 T8; spec 0002 section 4.5.2, AC18).

Purpose: validate canonical input before any host call, convert its quantities to the units of the CSI units token,
add the explicit target, token and `confirm`. Units: canonical in, token units out (`eng_contract.units`).
Errors: `ContractError` (`INVALID_ARGUMENT`, `REF_*`, `OUT_OF_RANGE`); `UnitError`, `UnitGapError` (`UNIT_MISMATCH`).
"""

from collections.abc import Callable, Mapping

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import InputPolicy, ParamModel, ParamSpec, ValidatedInput, validate_input
from eng_contract.quantity import Quantity
from eng_contract.refs import RecordSource
from eng_contract.units import QUANTITY_KINDS, UNITS, UnitError, convert, csi_unit_system
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from eng_harness.adapters._descriptors import ToolDescriptor

_Revision = Callable[[str], int | None]  # the adapter's revision of a model id, None when not tracked
_RESERVED = ("target", "confirm", "units")  # set by `host_arguments` only


class HostTarget(BaseModel):
    """The instance a call acts on; always sent, because Sasaah `TargetResolver.cs` otherwise uses the session's."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    product: str = Field(min_length=1)
    pid: int = Field(ge=1)


def validate_call[M: ParamModel](
    model_cls: type[M], raw: Mapping[str, object], *, source: RecordSource, current_revision: _Revision
) -> ValidatedInput[M]:
    """Validate with engineering quantities required as references (11 section 6 item 2); `ContractError` on failure."""
    policy = InputPolicy(require_refs=True)
    return validate_input(model_cls, raw, source=source, current_revision=current_revision, policy=policy)


def convert_quantities(model: ParamModel, units_system: str) -> dict[str, float]:
    """Each set quantity field of `model` converted from its canonical unit to the units of `units_system`.

    Raises:
        UnitGapError: a `Ton_*` system (contract gap G-1).
        UnitError: the system is unknown or does not fix the unit of a field (an angle, a mass, a time).
    """
    system = csi_unit_system(units_system)
    converted: dict[str, float] = {}
    for name, info in type(model).model_fields.items():
        spec, value = info.json_schema_extra, getattr(model, name)
        if not isinstance(spec, ParamSpec) or spec.unit is None or value is None:
            continue
        kind = next((k for k in QUANTITY_KINDS.values() if k.dimension == UNITS[spec.unit].dimension), None)
        member = None if kind is None else "stress" if kind.name == "area_load" else kind.name
        target = spec.unit if member == "dimensionless" else getattr(system, member or "", None)
        if target is None:
            raise UnitError(f"units system {units_system} does not fix the unit of {name}", received=spec.unit)
        converted[name] = convert(value.value if isinstance(value, Quantity) else value, spec.unit, target)
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
    """`args` plus `target`, `units` (a `token` tool always passes it) and `confirm`.

    `confirm: true` only for a tool that needs it, under an approval, and for an `owned` tool on a launched instance.

    Raises:
        ContractError: `INVALID_ARGUMENT` when `args` sets a reserved key or a `token` tool has no units system.
        UnitGapError, UnitError: as for `convert_quantities`.
    """
    for key in _RESERVED:
        if key in args:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{key} is set by the framework, not a builder", field=key)
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
