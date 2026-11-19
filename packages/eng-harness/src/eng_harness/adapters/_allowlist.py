"""The allowlist: reviewed data naming every host tool an adapter may call (spec 0002 section 4.5.1, AC16, AC38).

Purpose: refuse escape hatches (scripts, generic invoke, table writes) at load, before any server is started.
The header pins one tool-list fingerprint per product (spec 0008 4.1) and a load for a product serves only the entries
that list it. A header may declare `routes` and `[[unit]]` entries (AC41, AC42). Whether a name is excluded in the
S-12 inventory or absent from the pinned build is checked by the contract test against the inventory, which is not
shipped.
Errors: `AllowlistError`; nothing is repaired or skipped.
"""

import re
import tomllib
from collections.abc import Mapping
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, model_validator

from eng_harness.adapters._descriptors import ToolDescriptor, UnitHeader
from eng_harness.servers._buildcheck import BuildExpectation

__all__ = ["Allowlist", "AllowlistError", "load_allowlist"]

# Names refused outright (spec 0002 section 4.5.1), including those of later adapters.
_DENY = re.compile(
    r"csi_(run_script|db_tables_apply|invoke|object_(add|delete|set|get))|idea_run_script"
    r"|(?:revit_)?(?:send_code_to_revit|compile_and_run|dev_hot_run|dev_hot_unload|dev_hot_sessions"
    r"|run_baked_tool|list_baked_tools|list_bake_suggestions|accept_bake_suggestion|dismiss_bake_suggestion"
    r"|batch_execute|run_synapse_command|shutdown_bridge|authenticate|prepare_destructive|switch_target"
    r"|get_change_records|record_change)"
)
_MARKERS = ("script", "invoke", "eval", "tables_apply")
_Commit = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
_Fingerprint = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class AllowlistError(Exception):
    """The allowlist file is unreadable, malformed or lists a refused tool; raised at load, never later."""


class Allowlist(BaseModel):
    """Header (the pinned server build) and entries of one adapter's allowlist.

    `fingerprint` maps each product to the fingerprint of the tools that list it; the one of the product this load
    serves (`tool_fingerprint`) is checked against the server's live tool list by the build check (spec 0002 section
    4.3.4 item 4, spec 0008 4.1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter: str = Field(min_length=1)
    sasaah_commit: _Commit
    also_tested_commits: tuple[_Commit, ...] = ()
    fingerprint: Mapping[str, _Fingerprint] = Field(min_length=1)  # product -> fingerprint of its tools
    fingerprint_source: Literal["s12-inventory", "recording"]
    routes: tuple[str, ...] | None = None  # declared route names; absent when the server has one way (CSI)
    units: tuple[UnitHeader, ...] = Field(default=(), alias="unit")  # the `[[unit]]` array (AC42)
    tools: tuple[ToolDescriptor, ...] = Field(alias="tool", min_length=1)  # the `tool` array of the file
    # Every tool name in the file, set when `tools` is filtered to one route; empty means `tools` is the full list.
    _listed: frozenset[str] = PrivateAttr(default_factory=frozenset)
    _product: str | None = PrivateAttr(default=None)  # the product this load serves, once chosen
    _catalog: tuple[ToolDescriptor, ...] = PrivateAttr(default=())  # every entry, set when `tools` is route-filtered

    @model_validator(mode="after")
    def _products_pinned(self) -> Self:
        listed = {product for tool in self.tools for product in tool.products}
        for product in sorted(listed - self.fingerprint.keys()):
            raise ValueError(f"fingerprint: no entry for product {product}, which an allowlist entry lists")
        for product in sorted(self.fingerprint.keys() - listed):
            raise ValueError(f"fingerprint: product {product} is listed by no allowlist entry")
        return self

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
    def product(self) -> str:
        """The product this load serves; without a choice, the only product the header pins.

        Raises:
            ValueError: No product was chosen and the header pins several (load it with `for_product`).
        """
        if self._product is not None:
            return self._product
        if len(self.fingerprint) == 1:
            return next(iter(self.fingerprint))
        raise ValueError("the header pins several products: load the allowlist for one")

    @property
    def tool_fingerprint(self) -> str:
        """The pinned fingerprint of the product this load serves."""
        return self.fingerprint[self.product]

    def for_product(self, product: str) -> Allowlist:
        """This allowlist reduced to the entries that list `product` (spec 0008 AC3).

        Raises:
            AllowlistError: The header pins no fingerprint for the product, no entry lists it, or the load already
                serves another product.
        """
        return _for_product(self, product, "allowlist")

    @property
    def tool_names(self) -> frozenset[str]:
        """Every allowlisted tool name, whatever its route (spec 0002 section 4.3.4 item 4)."""
        return self._listed or frozenset(tool.name for tool in self.tools)

    def build_expectation(self) -> BuildExpectation:
        """What the build check compares a started server with (spec 0002 section 4.3.4)."""
        return BuildExpectation(
            self.sasaah_commit, self.also_tested_commits, self.tool_fingerprint, self.tool_names, self.product
        )

    def unreleased_tools(self) -> dict[str, str]:
        """`{name: release_record}` of the unreleased entries (AC38); empty when there are none."""
        return {t.name: t.release_record for t in self.tools if t.release_record and t.release == "unreleased"}


def _for_product(allowlist: Allowlist, product: str, source: str) -> Allowlist:
    """Serve the entries that list `product`; the fingerprint is the one the header pins for it (spec 0008 AC3)."""
    if allowlist._product == product:
        return allowlist
    if allowlist._product is not None:
        raise AllowlistError(f"{source}: already loaded for product {allowlist._product}, not {product}")
    if product not in allowlist.fingerprint:
        raise AllowlistError(f"{source}: the header pins no fingerprint for product {product}")
    catalog = allowlist._catalog or allowlist.tools  # a route-filtered load still knows the entries it does not serve
    chosen = allowlist.model_copy(update={"tools": tuple(t for t in allowlist.tools if product in t.products)})
    chosen._product = product
    if allowlist._catalog:
        chosen._listed = frozenset(t.name for t in catalog if product in t.products)
    return chosen


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
    chosen._catalog = allowlist.tools
    return chosen


def load_allowlist(text: str, source: str, *, route: str | None = None, product: str | None = None) -> Allowlist:
    """Parse and validate allowlist TOML, optionally for one server-section route (AC41) and one product (AC3).

    Args:
        text: The file's content.
        source: A name for messages.
        route: Required when the header declares `routes`, refused when it declares none.
        product: Serve only the entries that list this product, under its pinned fingerprint; all entries when absent.

    Raises:
        AllowlistError: Invalid TOML, a missing or invalid field, a duplicate name, an escape-hatch name (deny list or
            a name containing script, invoke, eval or tables_apply), an inconsistent release mark, a route the header
            does not allow, a `[[unit]]` entry whose status and tool do not match (AC42), a product without a
            fingerprint entry or an entry that lists no tool, or a `product` the header does not pin.
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
    return _for_route(loaded if product is None else _for_product(loaded, product, source), route, source)
