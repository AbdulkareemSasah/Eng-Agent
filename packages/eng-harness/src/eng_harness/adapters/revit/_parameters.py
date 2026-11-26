"""Revit parameter role map (plan 0011 T6; spec 0011 §4.8, AC33).

Purpose: load `[servers.revit.parameters.<family>]` with the six roles of the spec. Statuses are
`candidate` or `reference` (as 0008 §4.5 / 0011 §4.6). A role without a name or status, an unknown
status, an unknown role name, or two roles that share one GUID raises `ConfigError`.
Units: none (names and GUIDs only). Errors: `ConfigError`.
"""

from collections.abc import Mapping
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

__all__ = ["ROLE_NAMES", "ParameterRole", "RoleMap", "load_role_map"]

ROLE_NAMES = (
    "section_b",
    "section_h",
    "section_D",
    "material",
    "rotation",
    "etabs_link",
)
"""The six parameter roles of spec 0011 §4.8; names are not invented."""

RoleStatus = Literal["reference", "candidate"]
RoleMap = dict[str, dict[str, "ParameterRole"]]


class ParameterRole(BaseModel):
    """One role entry: display `name`, optional `guid` / `builtin`, and status (spec 0011 §4.8)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    guid: str | None = None
    builtin: str | None = None
    status: RoleStatus

    @model_validator(mode="after")
    def _guid_nonempty(self) -> Self:
        if self.guid is not None and not self.guid.strip():
            raise ValueError("guid must be non-empty when set")
        return self


def load_role_map(raw: Mapping[str, Mapping[str, Any]], *, key: str = "servers.revit.parameters") -> RoleMap:
    """Validate the role map; raise `ConfigError` naming `key` on any load-time rule breach (AC33)."""
    from eng_harness.servers._config import ConfigError

    if not isinstance(raw, Mapping):
        raise ConfigError(key, "parameters must be a table of families")

    result: RoleMap = {}
    seen_guids: dict[str, tuple[str, str]] = {}
    try:
        for family, roles in raw.items():
            if not isinstance(family, str) or not family:
                raise ValueError("family name must be a non-empty string")
            if not isinstance(roles, Mapping):
                raise ValueError(f"family {family!r} must be a table of roles")
            family_roles: dict[str, ParameterRole] = {}
            for role_name, entry in roles.items():
                if role_name not in ROLE_NAMES:
                    raise ValueError(f"unknown parameter role {role_name!r}")
                if not isinstance(entry, Mapping):
                    raise ValueError(f"{family}.{role_name} must be a table")
                if "name" not in entry:
                    raise ValueError(f"{family}.{role_name}: name is required")
                if "status" not in entry:
                    raise ValueError(f"{family}.{role_name}: status is required")
                role = ParameterRole.model_validate(dict(entry))
                if role.guid is not None:
                    prior = seen_guids.get(role.guid)
                    if prior is not None:
                        raise ValueError(
                            f"duplicate GUID {role.guid!r} on {family}.{role_name} and {prior[0]}.{prior[1]}"
                        )
                    seen_guids[role.guid] = (family, role_name)
                family_roles[role_name] = role
            result[family] = family_roles
    except ValidationError as error:
        first = error.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        msg = first["msg"].removeprefix("Value error, ")
        raise ConfigError(key, f"{field}: {msg}" if field else msg) from error
    except ValueError as error:
        raise ConfigError(key, str(error)) from error
    return result
