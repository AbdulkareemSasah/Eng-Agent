"""IDEA argument models and builders (plan 0014 T3; spec 0014 AC4, AC15, section 4.4).

Purpose: validate and build host arguments for the 9 served tools. `confirm` is set only under an approval;
`idea_native_calculate` always sends `save: false` and never `out_path`; `idea_calculate` always sends
`connection_ids`; the design code is read from the basis field only (never the server default `ECEN`).
Errors: `ContractError` (`INVALID_ARGUMENT`).
"""

from collections.abc import Mapping, Sequence
from typing import Any

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import ParamModel
from pydantic import Field, JsonValue

__all__ = [
    "CalculateArgs",
    "CloseProjectArgs",
    "GetCheckResultsArgs",
    "ListConnectionsArgs",
    "NativeCalculateArgs",
    "NativeGetLoadsArgs",
    "NativeSetLoadsArgs",
    "OpenProjectArgs",
    "StatusArgs",
    "build_calculate_args",
    "build_native_calculate_args",
    "build_native_set_loads_args",
    "build_status_args",
    "design_code_from_basis",
]

_DESIGN_CODE = "connection.design_code"  # design basis field (spec 0014 AC15, 13 §2)


class StatusArgs(ParamModel):
    """`idea_status`: no arguments."""


class OpenProjectArgs(ParamModel):
    """`idea_open_project`: absolute path of the project file."""

    path: str = Field(min_length=1)


class CloseProjectArgs(ParamModel):
    """`idea_close_project`: no arguments."""


class ListConnectionsArgs(ParamModel):
    """`idea_list_connections`: optional page limit."""

    limit: int | None = Field(default=None, ge=1, le=2000)


class CalculateArgs(ParamModel):
    """`idea_calculate`: explicit connection ids (omitting them would calculate every connection)."""

    connection_ids: list[int] = Field(min_length=1)


class GetCheckResultsArgs(ParamModel):
    """`idea_get_check_results`: optional single connection id."""

    connection_id: int | None = None


class NativeGetLoadsArgs(ParamModel):
    """`idea_native_get_loads`: working-copy path and optional connection identifier."""

    path: str = Field(min_length=1)
    connection_id: str | None = None


class NativeSetLoadsArgs(ParamModel):
    """`idea_native_set_loads`: loads built by the adapter, written to a new out_path."""

    path: str = Field(min_length=1)
    loads: list[dict[str, Any]]
    connection_id: str = Field(min_length=1)
    out_path: str = Field(min_length=1)


class NativeCalculateArgs(ParamModel):
    """`idea_native_calculate`: path and optional connection; save is never a model field (builder fixes false)."""

    path: str = Field(min_length=1)
    connection_id: str | None = None


def build_status_args() -> dict[str, JsonValue]:
    """Host arguments for `idea_status`."""
    return {}


def build_calculate_args(*, connection_ids: Sequence[int] | None, approved: bool) -> dict[str, JsonValue]:
    """Host arguments for `idea_calculate`: `connection_ids` required; `confirm` only when approved."""
    if not connection_ids:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            "connection_ids must be an explicit non-empty list",
            field="connection_ids",
        )
    sent: dict[str, JsonValue] = {"connection_ids": [int(i) for i in connection_ids]}
    if approved:
        sent["confirm"] = True
    return sent


def build_native_set_loads_args(
    *,
    path: str,
    loads: Sequence[Mapping[str, Any]],
    connection_id: str,
    out_path: str,
    approved: bool,
) -> dict[str, JsonValue]:
    """Host arguments for `idea_native_set_loads`: out_path distinct; confirm only when approved."""
    if not path or not out_path:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "path and out_path are required", field="path")
    if path == out_path:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            "out_path must be a new file distinct from path",
            field="out_path",
        )
    if not connection_id:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "connection_id is required", field="connection_id")
    sent: dict[str, JsonValue] = {
        "path": path,
        "loads": [dict(item) for item in loads],
        "connection_id": connection_id,
        "out_path": out_path,
    }
    if approved:
        sent["confirm"] = True
    return sent


def build_native_calculate_args(*, path: str, connection_id: str | None = None) -> dict[str, JsonValue]:
    """Host arguments for `idea_native_calculate`: save always false; no out_path; no confirm."""
    if not path:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "path is required", field="path")
    sent: dict[str, JsonValue] = {"path": path, "save": False}
    if connection_id is not None:
        sent["connection_id"] = connection_id
    return sent


def design_code_from_basis(basis: Mapping[str, object]) -> str:
    """The design code from the basis field `connection.design_code` (AC15); never the server default ECEN."""
    raw = basis.get(_DESIGN_CODE)
    if not isinstance(raw, str) or not raw.strip():
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            f"{_DESIGN_CODE} is missing or blank in the design basis",
            field=_DESIGN_CODE,
        )
    return raw.strip()
