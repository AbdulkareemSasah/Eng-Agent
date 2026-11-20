"""Revit argument models and builders (plan 0011 T3; spec 0011 AC2, AC8, AC14, AC15, section 4.4).

Purpose: validate and build host arguments for the 21 allowlisted tools. Writes use `confirm = host_dialog`
(the adapter sets no confirm flag; the server fetches the token). `valueType` is never `auto`; length GUID
writes require an explicit `unit` (`mm`); `expected_instances` is adapter-only for the shared-type rule.
Errors: `ContractError` (`INVALID_ARGUMENT`).
"""

from collections.abc import Sequence
from typing import Any, Literal

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import ParamModel
from pydantic import Field, JsonValue

__all__ = [
    "ChangeElementTypeArgs",
    "ConnectionStatusArgs",
    "DuplicateFamilyTypeArgs",
    "GetAvailableFamilyTypesArgs",
    "GetCurrentTargetArgs",
    "GetElementDetailsArgs",
    "GetElementParametersArgs",
    "GetModelMetadataArgs",
    "GetModelWarningsSummaryArgs",
    "GetTypeParametersArgs",
    "ListAvailableTargetsArgs",
    "ListElementsArgs",
    "ListFamilyTypesInFamilyArgs",
    "ListGridsArgs",
    "ListLevelsArgs",
    "ListWorksetsArgs",
    "OpenModelArgs",
    "PingArgs",
    "SetElementParameterValuesArgs",
    "SetParameterValueByGuidArgs",
    "SetTypeParameterValuesArgs",
    "build_set_element_parameter_values_args",
    "build_set_parameter_value_by_guid_args",
    "build_set_type_parameter_values_args",
]

# Host valueType values the adapter may send (spec 0011 AC8: never auto).
_ValueType = Literal["string", "integer", "double", "elementId"]
_VALUE_TYPES: frozenset[str] = frozenset({"string", "integer", "double", "elementId"})
# Length writes through the GUID tool use millimetres (spec 0011 section 4.6 rule 2); never auto.
_LengthUnit = Literal["mm", "internal"]
_LENGTH_UNITS: frozenset[str] = frozenset({"mm", "internal"})
_TARGETS: frozenset[str] = frozenset({"instance", "type"})


class ConnectionStatusArgs(ParamModel):
    """`revit_connection_status`: no arguments."""


class PingArgs(ParamModel):
    """`revit_ping`: no arguments."""


class GetCurrentTargetArgs(ParamModel):
    """`revit_get_current_target`: no arguments."""


class ListAvailableTargetsArgs(ParamModel):
    """`revit_list_available_targets`: no arguments."""


class GetModelMetadataArgs(ParamModel):
    """`revit_get_model_metadata`: no arguments."""


class ListLevelsArgs(ParamModel):
    """`revit_list_levels`: no arguments."""


class ListGridsArgs(ParamModel):
    """`revit_list_grids`: no arguments."""


class ListElementsArgs(ParamModel):
    """`revit_list_elements`: category filter, optional level and limit."""

    category: str = Field(min_length=1)
    level_id: int | None = None
    limit: int | None = Field(default=None, ge=1, le=1000)


class GetElementDetailsArgs(ParamModel):
    """`revit_get_element_details`: one or more element ids."""

    element_ids: list[int] = Field(min_length=1)


class GetElementParametersArgs(ParamModel):
    """`revit_get_element_parameters`: element ids and whether to include read-only parameters."""

    element_ids: list[int] = Field(min_length=1)
    include_read_only: bool = True


class GetTypeParametersArgs(ParamModel):
    """`revit_get_type_parameters`: element ids and/or type ids (inventory anyOf)."""

    element_ids: list[int] | None = None
    type_ids: list[int] | None = None


class GetAvailableFamilyTypesArgs(ParamModel):
    """`revit_get_available_family_types`: optional category filter."""

    category: str = ""


class ListFamilyTypesInFamilyArgs(ParamModel):
    """`revit_list_family_types_in_family`: family id or name and paging."""

    family_id: str | None = None
    family_name: str | None = None
    include_parameter_values: bool = True
    include_built_in_only: bool = False
    start_index: int = Field(default=0, ge=0)
    max_types: int = Field(default=100, ge=1, le=500)
    parameter_names: list[str] | None = None


class ListWorksetsArgs(ParamModel):
    """`revit_list_worksets`: optional element counts."""

    include_element_counts: bool = False


class GetModelWarningsSummaryArgs(ParamModel):
    """`revit_get_model_warnings_summary`: paging of warning types and examples."""

    include_examples: bool = True
    max_examples_per_type: int = Field(default=5, ge=0, le=100)
    max_warning_types: int = Field(default=200, ge=1, le=1000)


class OpenModelArgs(ParamModel):
    """`revit_open_model`: absolute path and open options."""

    path: str = Field(min_length=1)
    activate: bool = True
    audit: bool = False
    worksets: str | None = None
    allow_discard_unsaved_changes: bool = False


class DuplicateFamilyTypeArgs(ParamModel):
    """`revit_duplicate_family_type`: source type and new name; overrides are refused by the edit layer (T8)."""

    source_type_id: str = Field(min_length=1)
    new_type_name: str = Field(min_length=1)
    type_parameter_overrides: dict[str, Any] | None = None


class SetTypeParameterValuesArgs(ParamModel):
    """`revit_set_type_parameter_values`: one type, explicit valueType; expected_instances is adapter-only (AC15)."""

    parameter_name: str = Field(min_length=1)
    value: str
    value_type: _ValueType
    type_ids: list[int] | None = None
    element_ids: list[int] | None = None
    expected_instances: list[int] = Field(min_length=1)  # not sent to the host


class SetElementParameterValuesArgs(ParamModel):
    """`revit_set_element_parameter_values`: element ids, name, value and explicit valueType (lengths as double)."""

    element_ids: list[int] = Field(min_length=1)
    parameter_name: str = Field(min_length=1)
    value: str
    value_type: _ValueType


class SetParameterValueByGuidArgs(ParamModel):
    """`revit_set_parameter_value_by_guid`: GUID write with explicit valueType and length unit."""

    element_ids: list[int] = Field(min_length=1)
    guid: str = Field(min_length=1)
    value: str
    value_type: _ValueType
    unit: _LengthUnit | None = None
    target: Literal["instance", "type"] = "instance"
    all_or_nothing: bool = True


class ChangeElementTypeArgs(ParamModel):
    """`revit_change_element_type`: element ids and the target type id."""

    element_ids: list[int] = Field(min_length=1)
    type_id: int


def _value_type(field: str, value: str) -> _ValueType:
    if value == "auto" or value not in _VALUE_TYPES:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{field} must not be auto", field=field)
    if value == "string":
        return "string"
    if value == "integer":
        return "integer"
    if value == "double":
        return "double"
    return "elementId"


def _length_unit(value: str | None) -> _LengthUnit | None:
    if value is None:
        return None
    if value == "auto" or value not in _LENGTH_UNITS:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "unit must not be auto", field="unit")
    if value == "mm":
        return "mm"
    return "internal"


def _target(value: str) -> Literal["instance", "type"]:
    if value == "instance":
        return "instance"
    if value == "type":
        return "type"
    raise ContractError(ErrorCode.INVALID_ARGUMENT, "target must be instance or type", field="target")


def build_set_element_parameter_values_args(
    *,
    element_ids: Sequence[int],
    parameter_name: str,
    value: str,
    value_type: str,
) -> dict[str, JsonValue]:
    """Host arguments for `revit_set_element_parameter_values`; refuses `valueType: auto` (AC8)."""
    typed = _value_type("valueType", value_type)
    if not element_ids:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "elementIds must be non-empty", field="elementIds")
    if not parameter_name:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "parameterName is required", field="parameterName")
    model = SetElementParameterValuesArgs(
        element_ids=list(element_ids),
        parameter_name=parameter_name,
        value=value,
        value_type=typed,
    )
    return {
        "elementIds": list(model.element_ids),
        "parameterName": model.parameter_name,
        "value": model.value,
        "valueType": model.value_type,
    }


def build_set_type_parameter_values_args(
    *,
    type_ids: Sequence[int],
    parameter_name: str,
    value: str,
    value_type: str,
    expected_instances: Sequence[int],
    element_ids: Sequence[int] | None = None,
) -> dict[str, JsonValue]:
    """Host arguments for `revit_set_type_parameter_values`; drops `expected_instances` (AC15)."""
    typed = _value_type("valueType", value_type)
    if not type_ids:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "typeIds must be non-empty", field="typeIds")
    if not expected_instances:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT, "expected_instances must be non-empty", field="expected_instances"
        )
    model = SetTypeParameterValuesArgs(
        parameter_name=parameter_name,
        value=value,
        value_type=typed,
        type_ids=list(type_ids),
        element_ids=list(element_ids) if element_ids is not None else None,
        expected_instances=list(expected_instances),
    )
    sent: dict[str, JsonValue] = {
        "parameterName": model.parameter_name,
        "value": model.value,
        "valueType": model.value_type,
        "typeIds": list(model.type_ids or ()),
    }
    if model.element_ids is not None:
        sent["elementIds"] = list(model.element_ids)
    return sent


def build_set_parameter_value_by_guid_args(
    *,
    element_ids: Sequence[int],
    guid: str,
    value: str,
    value_type: str,
    unit: str | None,
    target: str = "instance",
    all_or_nothing: bool = True,
) -> dict[str, JsonValue]:
    """Host arguments for `revit_set_parameter_value_by_guid`; refuses auto valueType and unit (AC8)."""
    typed = _value_type("valueType", value_type)
    typed_unit = _length_unit(unit)
    typed_target = _target(target)
    if not element_ids:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "elementIds must be non-empty", field="elementIds")
    if not guid:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "guid is required", field="guid")
    model = SetParameterValueByGuidArgs(
        element_ids=list(element_ids),
        guid=guid,
        value=value,
        value_type=typed,
        unit=typed_unit,
        target=typed_target,
        all_or_nothing=all_or_nothing,
    )
    sent: dict[str, JsonValue] = {
        "elementIds": list(model.element_ids),
        "guid": model.guid,
        "value": model.value,
        "valueType": model.value_type,
        "target": model.target,
        "allOrNothing": model.all_or_nothing,
    }
    if model.unit is not None:
        sent["unit"] = model.unit
    return sent
