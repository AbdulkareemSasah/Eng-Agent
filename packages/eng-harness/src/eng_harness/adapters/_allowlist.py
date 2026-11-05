"""The allowlist: reviewed data naming every host tool an adapter may call (spec 0002 section 4.5.1, AC16, AC38).

Purpose: refuse escape hatches (scripts, generic invoke, table writes) at load, before any server is started.
Whether a name is excluded in the S-12 inventory or absent from the pinned build is checked by the contract test
against the inventory, which is not shipped. Errors: `AllowlistError`; nothing is repaired or skipped.
"""

import re
import tomllib
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from eng_harness.adapters._descriptors import ToolDescriptor
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
    tools: tuple[ToolDescriptor, ...] = Field(alias="tool", min_length=1)  # the `tool` array of the file

    def descriptor(self, name: str) -> ToolDescriptor:
        """The entry of `name`; `KeyError` when the tool is not on the allowlist."""
        for entry in self.tools:
            if entry.name == name:
                return entry
        raise KeyError(name)

    @property
    def tool_names(self) -> frozenset[str]:
        """Every allowlisted tool name, whatever its route."""
        return frozenset(t.name for t in self.tools)

    def build_expectation(self) -> BuildExpectation:
        """What the build check compares a started server with (spec 0002 section 4.3.4)."""
        return BuildExpectation(self.sasaah_commit, self.also_tested_commits, self.tool_fingerprint, self.tool_names)

    def unreleased_tools(self) -> dict[str, str]:
        """`{name: release_record}` of the unreleased entries (AC38); empty when there are none."""
        return {t.name: t.release_record for t in self.tools if t.release_record and t.release == "unreleased"}


def load_allowlist(text: str, source: str) -> Allowlist:
    """Parse and validate allowlist TOML.

    Args:
        text: The file's content.
        source: A name for messages.

    Raises:
        AllowlistError: Invalid TOML, a missing or invalid field, a duplicate name, an escape-hatch name (deny list or
            a name containing script, invoke, eval or tables_apply), or an inconsistent release mark.
    """
    try:
        data = tomllib.loads(text)
        entries = data.get("tool")
        names = [str(t.get("name")) for t in entries if isinstance(t, dict)] if isinstance(entries, list) else []
        for name in names:
            if _DENY.fullmatch(name) or any(marker in name for marker in _MARKERS):
                raise AllowlistError(f"{source}: {name} is an escape hatch and is never allowlisted")
        for name in sorted({n for n in names if names.count(n) > 1}):
            raise AllowlistError(f"{source}: {name} is listed twice")
        return Allowlist.model_validate(data)
    except (tomllib.TOMLDecodeError, ValidationError) as error:
        raise AllowlistError(f"{source}: {error}") from error
