"""The allowlist: reviewed data naming every host tool an adapter may call (spec 0002 section 4.5.1, AC16, AC38).

Purpose: refuse escape hatches (scripts, generic invoke, table writes) at load, before any server is started.
A header may declare `routes` and `[[unit]]` entries (AC41, AC42). Whether a name is excluded in the S-12 inventory
or absent from the pinned build is checked by the contract test against the inventory, which is not shipped.
Errors: `AllowlistError`; nothing is repaired or skipped.
"""

import re
import tomllib
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, model_validator

from eng_harness.adapters._descriptors import ToolDescriptor, UnitHeader
from eng_harness.servers._buildcheck import BuildExpectation

__all__ = ["Allowlist", "AllowlistError", "load_allowlist"]

# Names refused outright (spec 0002 section 4.5.1), including those of later adapters.
_DENY = re.compile(
    r"csi_(run_script|db_tables_apply|invoke|object_(add|delete|set|get))|idea_run_script|compile_and_run"
    r"|revit_send_code_to_revit|dev_hot_(run|unload)|run_baked_tool|batch_execute|run_synapse_command"
    r"|revit_(accept|dismiss)_bake_suggestion|revit_list_bake_suggestions"
)
_MARKERS = ("script", "invoke", "eval", "tables_apply")
_Commit = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]


class AllowlistError(Exception):
    """The allowlist file is unreadable, malformed or lists a refused tool; raised at load, never later."""


class Allowlist(BaseModel):
    """Header (the pinned server build) and entries of one adapter's allowlist.

    `tool_fingerprint` is checked against the server's live tool list by the build check (spec 0002 section 4.3.4).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter: str = Field(min_length=1)
    sasaah_commit: _Commit
    also_tested_commits: tuple[_Commit, ...] = ()
    tool_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    fingerprint_source: Literal["s12-inventory", "recording"]
    routes: tuple[str, ...] | None = None  # declared route names; absent when the server has one way (CSI)
    units: tuple[UnitHeader, ...] = Field(default=(), alias="unit")  # the `[[unit]]` array (AC42)
    tools: tuple[ToolDescriptor, ...] = Field(alias="tool", min_length=1)  # the `tool` array of the file
    # Every tool name in the file, set when `tools` is filtered to one route; empty means `tools` is the full list.
    _listed: frozenset[str] = PrivateAttr(default_factory=frozenset)

    @model_validator(mode="after")
    def _routes_and_units(self) -> Self:
        declared = self.routes
        if declared is not None and not declared:
            raise ValueError("routes must be non-empty when declared")
        names = {tool.name for tool in self.tools}
        for tool in self.tools:
            got = tool.routes
            if declared is None:
                if got is not None:
                    raise ValueError(f"{tool.name}: routes is refused when the header declares none")
            elif not got or any(name not in declared for name in got):
                raise ValueError(f"{tool.name}: routes must be a non-empty list drawn from the header")
        grouped: dict[str, tuple[UnitHeader, ...]] = {}
        for entry in self.units:
            if entry.unit_status != "missing" and entry.tool not in names:
                raise ValueError(f"{entry.tool}: a {entry.unit_status} unit must name an allowlisted tool")
            if entry.tool in names:
                grouped[entry.tool] = (*grouped.get(entry.tool, ()), entry)
        # Each descriptor's header is exactly that tool's [[unit]] rows, including when there are none (AC42).
        if all(tool.unit_header == grouped.get(tool.name, ()) for tool in self.tools):
            return self
        tools = tuple(tool.model_copy(update={"unit_header": grouped.get(tool.name, ())}) for tool in self.tools)
        return self.model_copy(update={"tools": tools})

    def descriptor(self, name: str) -> ToolDescriptor:
        """The entry of `name`; `KeyError` when this load does not serve the tool."""
        for entry in self.tools:
            if entry.name == name:
                return entry
        raise KeyError(name)

    @property
    def tool_names(self) -> frozenset[str]:
        """Every allowlisted tool name, whatever its route (spec 0002 section 4.3.4 item 4)."""
        return self._listed or frozenset(tool.name for tool in self.tools)

    def build_expectation(self) -> BuildExpectation:
        """What the build check compares a started server with (spec 0002 section 4.3.4)."""
        return BuildExpectation(self.sasaah_commit, self.also_tested_commits, self.tool_fingerprint, self.tool_names)

    def unreleased_tools(self) -> dict[str, str]:
        """`{name: release_record}` of the unreleased entries (AC38); empty when there are none."""
        return {t.name: t.release_record for t in self.tools if t.release_record and t.release == "unreleased"}


def _for_route(allowlist: Allowlist, route: str | None, source: str) -> Allowlist:
    """Serve the entries whose `routes` include `route`; the fingerprint still names every entry (AC41)."""
    declared = allowlist.routes
    if declared is None:
        if route is not None:
            raise AllowlistError(f"{source}: route {route!r} is refused when the allowlist declares no routes")
        return allowlist
    if route is None:
        raise AllowlistError(f"{source}: a route is required when the allowlist declares routes")
    if route not in declared:
        raise AllowlistError(f"{source}: route {route!r} is not declared")
    names = frozenset(tool.name for tool in allowlist.tools)
    served = tuple(tool for tool in allowlist.tools if tool.routes is not None and route in tool.routes)
    chosen = allowlist.model_copy(update={"tools": served})
    chosen._listed = names
    return chosen


def load_allowlist(text: str, source: str, *, route: str | None = None) -> Allowlist:
    """Parse and validate allowlist TOML, optionally for one server-section route (AC41).

    Args:
        text: The file's content.
        source: A name for messages.
        route: Required when the header declares `routes`, refused when it declares none.

    Raises:
        AllowlistError: Invalid TOML, a missing or invalid field, a duplicate name, an escape-hatch name (deny list or
            a name containing script, invoke, eval or tables_apply), an inconsistent release mark, a route the header
            does not allow, or a `[[unit]]` entry whose status and tool do not match (AC42).
    """
    try:
        data = tomllib.loads(text)
        entries = data.get("tool")
        names = [str(t.get("name")) for t in entries if isinstance(t, dict)] if isinstance(entries, list) else []
        units = data.get("unit")
        unit_rows = units if isinstance(units, list) else []
        unit_tools = [str(item.get("tool")) for item in unit_rows if isinstance(item, dict)]
        for name in (*names, *unit_tools):
            if _DENY.fullmatch(name) or any(marker in name for marker in _MARKERS):
                raise AllowlistError(f"{source}: {name} is an escape hatch and is never allowlisted")
        for name in sorted({n for n in names if names.count(n) > 1}):
            raise AllowlistError(f"{source}: {name} is listed twice")
        loaded = Allowlist.model_validate(data)
    except (tomllib.TOMLDecodeError, ValidationError) as error:
        raise AllowlistError(f"{source}: {error}") from error
    return _for_route(loaded, route, source)
